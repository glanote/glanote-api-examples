import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { VERSION, main, MAX_IMAGE_BYTES } from "../javascript/glanote.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SECRET = "unit-test-edit-key-9f3a";
const VIEW = "unit-test-view-pw-44c1";
const TOKEN = "unit-test-access-token-77ab";
const TINY_PNG = Buffer.from(
  "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082",
  "hex",
);

function capture() {
  const chunks = [];
  return {
    write(text) {
      chunks.push(text);
    },
    text() {
      return chunks.join("");
    },
  };
}

async function startServer() {
  const requests = [];
  const state = { requests, reply: { code: 200, body: "{}" }, delay: 0 };
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      const record = {
        method: req.method,
        path: req.url,
        headers: req.headers,
        body: Buffer.concat(chunks),
      };
      requests.push(record);
      const send = () => {
        if (res.writableEnded) return;
        const spec = state.reply;
        const body = Buffer.isBuffer(spec.body) ? spec.body : Buffer.from(String(spec.body));
        res.writeHead(spec.code || 200, { "content-type": spec.type || "application/json; charset=utf-8" });
        res.end(body);
      };
      if (state.delay) setTimeout(send, state.delay);
      else send();
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  return { server, state, base };
}

async function run(base, argv, stdin) {
  const stdout = capture();
  const stderr = capture();
  const code = await main(argv, {
    stdout,
    stderr,
    stdin,
    env: { GLANOTE_BASE_URL: base },
  });
  return [code, stdout.text(), stderr.text()];
}

test("javascript client", async (t) => {
  const { server, state, base } = await startServer();
  t.after(() => new Promise((resolve) => server.close(resolve)));

  await t.test("help, version, and base url", async () => {
    let [code, , err] = await run(base, ["--help"]);
    assert.equal(code, 0);
    assert.match(err, /--base-url/);
    assert.match(err, /--timeout/);
    assert.match(err, /https:\/\/glanote.com\/en\/api/);
    [code, , err] = await run(base, ["--version"]);
    assert.equal(code, 0);
    assert.match(err, new RegExp(VERSION));
    for (const value of ["file:///tmp/x", "https://user:pass@glanote.com", "https://glanote.com/?q=1"]) {
      [code] = await run(base, ["--base-url", value, "read", "f6a0b2"]);
      assert.equal(code, 2);
    }
    assert.equal(state.requests.length, 0);
  });

  await t.test("publish unicode and hide the edit key", async () => {
    state.requests.length = 0;
    state.reply = { code: 200, body: JSON.stringify({ url: `${base}/ab12cd`, edit_key: SECRET }) };
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "glanote-js-"));
    const keyPath = path.join(dir, "key.json");
    const [code, out, err] = await run(base, ["publish", "--title", "测试 café", "--content", "你好 🌟", "--save-key", keyPath]);
    assert.equal(code, 0, err);
    assert.equal(out, `${base}/ab12cd\n`);
    assert.equal(err.includes(SECRET), false);
    const sent = JSON.parse(state.requests[0].body.toString("utf8"));
    assert.deepEqual(sent, { title: "测试 café", content: "你好 🌟" });
    assert.equal(state.requests[0].body.includes(Buffer.from("\\u00e9")), false);
    const saved = JSON.parse(fs.readFileSync(keyPath, "utf8"));
    assert.equal(saved.edit_key, SECRET);
    assert.equal(fs.statSync(keyPath).mode & 0o777, 0o600);
    const shown = await run(base, ["publish", "--title", "T", "--content", "body", "--show-key"]);
    assert.equal(shown[1].includes(SECRET), false);
    assert.equal(shown[2].includes(SECRET), true);
    const hidden = await run(base, ["publish", "--title", "T", "--content", "body"]);
    assert.equal(hidden[1].includes(SECRET), false);
    assert.equal(hidden[2].includes(SECRET), false);
    assert.match(hidden[2], /cannot be recovered/);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  await t.test("view password is redacted and read sends the header", async () => {
    state.requests.length = 0;
    const [code, out, err] = await run(base, ["publish", "--title", "T", "--content", "body", "--view-password", VIEW, "--dry-run"]);
    assert.equal(code, 0);
    assert.equal(out.includes(VIEW), false);
    assert.equal(err.includes(VIEW), false);
    assert.match(err, /view_password":"REDACTED"/);
    state.reply = { code: 200, body: JSON.stringify({ slug: "f6a0b2", title: "Hi" }) };
    const read = await run(base, ["read", "https://glanote.com/f6a0b2.md", "--view-password", VIEW]);
    assert.equal(read[0], 0, read[2]);
    assert.equal(state.requests.at(-1).path, "/api/articles/f6a0b2");
    assert.equal(state.requests.at(-1).headers["x-view-password"], VIEW);
    assert.equal(read[2].includes(VIEW), false);
  });

  await t.test("edit and delete require the key and --yes", async () => {
    state.requests.length = 0;
    state.reply = { code: 200, body: "{}" };
    let [code, , err] = await run(base, ["delete", "ab12cd", "--edit-key", SECRET]);
    assert.equal(code, 2);
    assert.equal(state.requests.length, 0);
    const dry = await run(base, ["delete", "ab12cd", "--edit-key", SECRET, "--yes", "--dry-run"]);
    assert.equal(dry[1].includes(SECRET), false);
    assert.equal(dry[2].includes(SECRET), false);
    assert.match(dry[2], /edit_key":"REDACTED"/);
    const deleted = await run(base, ["delete", "ab12cd", "--edit-key", SECRET, "--yes"]);
    assert.equal(deleted[0], 0, deleted[2]);
    assert.equal(deleted[1], `deleted ${base}/ab12cd\n`);
    assert.equal(deleted[1].includes(SECRET), false);
    assert.deepEqual(JSON.parse(state.requests.at(-1).body.toString("utf8")), { edit_key: SECRET });
    assert.equal(state.requests.at(-1).method, "DELETE");
    const edited = await run(base, ["edit", "ab12cd", "--edit-key", SECRET, "--yes", "--title", "改过的标题", "--content", "改过的正文"]);
    assert.equal(edited[0], 0, edited[2]);
    assert.equal(edited[1].includes(SECRET), false);
    assert.deepEqual(JSON.parse(state.requests.at(-1).body.toString("utf8")), {
      edit_key: SECRET,
      title: "改过的标题",
      content: "改过的正文",
    });
  });

  await t.test("http errors redact secrets and timeouts abort", async () => {
    state.requests.length = 0;
    state.reply = { code: 400, body: JSON.stringify({ edit_key: SECRET, message: "no", password: VIEW }) };
    const [code, out, err] = await run(base, ["publish", "--title", "T", "--content", "body"]);
    assert.equal(code, 1);
    assert.equal(out, "");
    assert.match(err, /HTTP 400/);
    assert.equal(err.includes(SECRET), false);
    assert.equal(err.includes(VIEW), false);
    state.delay = 1500;
    const started = Date.now();
    const timed = await run(base, ["--timeout", "0.4", "read", "f6a0b2"]);
    state.delay = 0;
    assert.equal(timed[0], 1, timed[2]);
    assert.match(timed[2], /timed out/);
    assert.ok(Date.now() - started < 1300);
  });

  await t.test("image, new, preview, qr, and telegraph", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "glanote-js-"));
    const image = path.join(dir, "demo.png");
    fs.writeFileSync(image, TINY_PNG);
    const video = path.join(dir, "clip.mp4");
    fs.writeFileSync(video, Buffer.from("nope"));
    const big = path.join(dir, "big.png");
    const fd = fs.openSync(big, "w");
    fs.ftruncateSync(fd, MAX_IMAGE_BYTES + 1);
    fs.closeSync(fd);
    state.requests.length = 0;
    let [code, , err] = await run(base, ["image", video]);
    assert.equal(code, 2, err);
    [code, , err] = await run(base, ["image", big]);
    assert.equal(code, 2);
    assert.match(err, /5 MB/);
    state.reply = { code: 200, body: "![demo](https://example.test/demo.png)\n", type: "text/plain" };
    const uploaded = await run(base, ["image", image]);
    assert.equal(uploaded[0], 0, uploaded[2]);
    assert.match(uploaded[1], /!\[demo\]/);
    assert.match(uploaded[2], /hotlinking/i);
    assert.equal(state.requests.at(-1).path, "/api/images");
    assert.ok(state.requests.at(-1).body.includes(Buffer.from('name="image"')));

    state.reply = { code: 200, body: JSON.stringify({ url: `${base}/cd34ef`, edit_key: SECRET }) };
    const created = await run(base, ["new", "--text", "一句话也能发布成文章"]);
    assert.equal(created[0], 0, created[2]);
    assert.equal(created[1], `${base}/cd34ef\n`);
    assert.equal(created[1].includes(SECRET), false);
    assert.equal(created[2].includes(SECRET), false);
    assert.match(state.requests.at(-1).path, /\/api\/new\?format=json/);
    assert.equal(new URLSearchParams(state.requests.at(-1).body.toString("utf8")).get("text"), "一句话也能发布成文章");

    state.reply = { code: 200, body: "<p><strong>粗体</strong></p>", type: "text/html" };
    const preview = await run(base, ["preview", "--content", "**粗体**"]);
    assert.equal(preview[0], 0, preview[2]);
    assert.match(preview[1], /<strong>粗体<\/strong>/);
    assert.match(preview[2], /Nothing was published/);

    const svg = path.join(dir, "qr.svg");
    state.reply = { code: 200, body: "<svg>ok</svg>", type: "image/svg+xml" };
    const qr = await run(base, ["qr", "https://glanote.com/f6a0b2", "--output", svg]);
    assert.equal(qr[0], 0, qr[2]);
    assert.equal(fs.readFileSync(svg, "utf8"), "<svg>ok</svg>");

    const dry = await run("http://127.0.0.1:9", ["telegraph", "list", "--token", TOKEN, "--dry-run"]);
    assert.equal(dry[0], 0, dry[2]);
    assert.equal(`${dry[1]}${dry[2]}`.includes(TOKEN), false);
    assert.match(dry[2], /access_token=REDACTED/);
    assert.match(dry[2], /\/telegraph\/getPageList/);

    state.reply = { code: 200, body: JSON.stringify({ ok: true, result: { short_name: "myblog", access_token: TOKEN } }) };
    const tokenPath = path.join(dir, "token.json");
    const account = await run(base, ["telegraph", "account", "--short-name", "myblog", "--author-name", "Glanote Fan", "--save-token", tokenPath]);
    assert.equal(account[0], 0, account[2]);
    assert.equal(account[1], "myblog\n");
    assert.equal(account[2].includes(TOKEN), false);
    assert.equal(JSON.parse(fs.readFileSync(tokenPath, "utf8")).access_token, TOKEN);
    assert.equal(fs.statSync(tokenPath).mode & 0o777, 0o600);

    state.reply = { code: 200, body: JSON.stringify({ ok: true, result: { path: "ab12cd", url: `${base}/ab12cd` } }) };
    const page = await run(base, ["telegraph", "create", "--token", TOKEN, "--title", "来自 Telegraph 接口", "--text", "你好，Telegraph！"]);
    assert.equal(page[0], 0, page[2]);
    assert.equal(page[1], `${base}/ab12cd\n`);
    assert.equal(page[2].includes(TOKEN), false);
    const fields = new URLSearchParams(state.requests.at(-1).body.toString("utf8"));
    assert.equal(fields.get("access_token"), TOKEN);
    assert.deepEqual(JSON.parse(fields.get("content")), [{ tag: "p", children: ["你好，Telegraph！"] }]);
    const denied = await run(base, ["telegraph", "edit", "--token", TOKEN, "--path", "f6a0b2", "--title", "T", "--text", "x"]);
    assert.equal(denied[0], 2);
    assert.match(denied[2], /--yes/);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  await t.test("client source skips report and telegram endpoints", () => {
    const text = fs.readFileSync(path.join(ROOT, "javascript", "glanote.mjs"), "utf8");
    assert.equal(text.includes("/report"), false);
    assert.equal(text.includes("api.telegram.org"), false);
    assert.equal(text.includes("/telegram/"), false);
  });
});
