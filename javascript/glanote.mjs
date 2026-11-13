#!/usr/bin/env node
/**
 * Command-line client for the public Glanote article API.
 * Endpoints match https://glanote.com/en/api
 * This file is an example client. It is not the Glanote server.
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

export const VERSION = "0.1.0";
const DEFAULT_BASE_URL = "https://glanote.com";
const DEFAULT_TIMEOUT = 30;
const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const USER_AGENT = `glanote-api-examples/${VERSION}`;

const IMAGE_TYPES = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".gif": "image/gif",
};

const SECRET_FIELDS = new Set([
  "edit_key",
  "access_token",
  "view_password",
  "password",
  "token",
  "auth_url",
]);

const HELP = `glanote — publish and read Markdown with the public Glanote API
Docs: https://glanote.com/en/api

Usage:
  glanote publish [--file PATH | --content TEXT] [--title TEXT] [--author TEXT]
                  [--view-password TEXT | --view-password-file PATH]
                  [--save-key PATH | --show-key]
  glanote read SLUG [--markdown] [--view-password TEXT | --view-password-file PATH]
  glanote edit SLUG (--edit-key KEY | --edit-key-file PATH) --yes
                  (--file PATH | --content TEXT) [--title TEXT]
  glanote delete SLUG (--edit-key KEY | --edit-key-file PATH) --yes
  glanote image FILE
  glanote new --text TEXT
  glanote new --file PATH
  glanote new --title TEXT --text TEXT --image FILE
                  [--save-key PATH | --show-key]
  glanote preview [--file PATH | --content TEXT]
  glanote qr URL [--output PATH]
  glanote telegraph account --short-name NAME [--author-name TEXT]
                  [--save-token PATH | --show-token]
  glanote telegraph create (--token TOKEN | --token-file PATH) --title TEXT
                  (--text TEXT | --content JSON) [--return-content]
  glanote telegraph get PATH [--return-content]
  glanote telegraph edit (--token TOKEN | --token-file PATH) --path PATH
                  --title TEXT (--text TEXT | --content JSON) --yes
  glanote telegraph list (--token TOKEN | --token-file PATH)
  glanote telegraph info (--token TOKEN | --token-file PATH)

Global options:
  --base-url URL      Default: $GLANOTE_BASE_URL or https://glanote.com
  --timeout SECONDS   Default: $GLANOTE_TIMEOUT or 30
  --dry-run           Show the request and do not send it. Secrets are redacted.
  -h, --help
  --version

Publish reads stdin when --file and --content are both omitted and stdin is not
a terminal. A leading Markdown heading ("# title") becomes the title unless
--title is set. Stdout is the public URL only. The edit key is left out unless
you pass --show-key (printed on stderr) or --save-key (a new file, mode 0600).
Glanote stores only a hash of the key and cannot recover it. Edit and delete
always require that key and --yes.

The Telegraph commands call the six methods documented for
https://glanote.com/telegraph : createAccount, createPage, editPage, getPage,
getPageList, getAccountInfo. For getPage, PATH is the short code.
`;

class UsageError extends Error {}
class ClientError extends Error {}

function emptyArgs() {
  return {
    command: "",
    sub: "",
    baseUrl: undefined,
    timeout: undefined,
    dryRun: false,
    file: undefined,
    title: undefined,
    author: undefined,
    content: undefined,
    viewPassword: undefined,
    viewPasswordFile: undefined,
    showKey: false,
    saveKey: undefined,
    slug: undefined,
    markdown: false,
    editKey: undefined,
    editKeyFile: undefined,
    yes: false,
    image: undefined,
    text: undefined,
    output: undefined,
    url: undefined,
    shortName: undefined,
    authorName: undefined,
    showToken: false,
    saveToken: undefined,
    token: undefined,
    tokenFile: undefined,
    pagePath: undefined,
    returnContent: false,
    modeWarnings: [],
  };
}

const OPTION_MAP = {
  "--base-url": "baseUrl",
  "--timeout": "timeout",
  "--file": "file",
  "--title": "title",
  "--author": "author",
  "--content": "content",
  "--view-password": "viewPassword",
  "--view-password-file": "viewPasswordFile",
  "--save-key": "saveKey",
  "--edit-key": "editKey",
  "--edit-key-file": "editKeyFile",
  "--text": "text",
  "--image": "image",
  "--output": "output",
  "--short-name": "shortName",
  "--author-name": "authorName",
  "--save-token": "saveToken",
  "--token": "token",
  "--token-file": "tokenFile",
  "--path": "pagePath",
};

export function parseArgs(argv) {
  if (argv.length === 0 || ["-h", "--help", "help"].includes(argv[0])) {
    throw new UsageError(HELP);
  }
  if (["-V", "--version", "version"].includes(argv[0])) {
    throw new UsageError(`glanote ${VERSION}`);
  }
  const args = emptyArgs();
  const positional = [];
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--") {
      positional.push(...argv.slice(i + 1));
      break;
    }
    if (token === "-h" || token === "--help") throw new UsageError(HELP);
    if (token === "--version") throw new UsageError(`glanote ${VERSION}`);
    if (token === "--dry-run") {
      args.dryRun = true;
      continue;
    }
    if (token === "--show-key") {
      args.showKey = true;
      continue;
    }
    if (token === "--show-token") {
      args.showToken = true;
      continue;
    }
    if (token === "--yes") {
      args.yes = true;
      continue;
    }
    if (token === "--markdown") {
      args.markdown = true;
      continue;
    }
    if (token === "--return-content") {
      args.returnContent = true;
      continue;
    }
    if (token.startsWith("--")) {
      let name = token;
      let value;
      if (token.includes("=")) {
        const eq = token.indexOf("=");
        name = token.slice(0, eq);
        value = token.slice(eq + 1);
      } else {
        if (i + 1 >= argv.length) throw new UsageError(`${token} needs a value.`);
        i += 1;
        value = argv[i];
      }
      if (!Object.prototype.hasOwnProperty.call(OPTION_MAP, name)) {
        throw new UsageError(`Unknown option ${name}.`);
      }
      args[OPTION_MAP[name]] = value;
      continue;
    }
    positional.push(token);
  }
  if (positional.length === 0) throw new UsageError(`Missing command.\n\n${HELP}`);
  args.command = positional[0];
  let rest = positional.slice(1);
  const known = new Set(["publish", "read", "edit", "delete", "image", "new", "preview", "qr", "telegraph"]);
  if (!known.has(args.command)) throw new UsageError(`Unknown command ${JSON.stringify(args.command)}.\n\n${HELP}`);
  if (args.command === "telegraph") {
    if (rest.length === 0) throw new UsageError(`Missing telegraph method.\n\n${HELP}`);
    args.sub = rest[0];
    rest = rest.slice(1);
    const methods = new Set(["account", "create", "get", "edit", "list", "info"]);
    if (!methods.has(args.sub)) {
      throw new UsageError(`Unknown telegraph method ${JSON.stringify(args.sub)}.\n\n${HELP}`);
    }
  }
  if (["read", "edit", "delete"].includes(args.command) || (args.command === "telegraph" && args.sub === "get")) {
    if (rest.length !== 1) throw new UsageError(`${args.command} expects one slug or public URL.`);
    args.slug = rest[0];
    if (args.command === "telegraph") args.pagePath = rest[0];
  } else if (args.command === "image") {
    if (rest.length !== 1) throw new UsageError("image expects one image file.");
    args.image = rest[0];
  } else if (args.command === "qr") {
    if (rest.length !== 1) throw new UsageError("qr expects one URL.");
    args.url = rest[0];
  } else if (rest.length) {
    throw new UsageError(`Unexpected argument ${JSON.stringify(rest[0])}.`);
  }
  return args;
}

export function normalizeBaseUrl(value) {
  const raw = String(value ?? "").trim();
  if (!raw) throw new UsageError("Base URL is empty.");
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new UsageError("Base URL must start with https:// or http://.");
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new UsageError("Base URL must start with https:// or http://.");
  }
  if (parsed.username || parsed.password) throw new UsageError("Base URL must not contain credentials.");
  if (parsed.search || parsed.hash) throw new UsageError("Base URL must not contain a query or fragment.");
  if (!parsed.host) throw new UsageError("Base URL is missing a host.");
  const pathname = parsed.pathname.replace(/\/+$/, "");
  return `${parsed.protocol}//${parsed.host}${pathname}`;
}

export function normalizeSlug(value) {
  let raw = String(value ?? "").trim();
  if (raw.includes("://")) {
    let parsed;
    try {
      parsed = new URL(raw);
    } catch {
      throw new UsageError("Slug must be the short code or a public article URL.");
    }
    raw = parsed.pathname.replace(/\/+$/, "");
    if (raw.endsWith(".md")) raw = raw.slice(0, -3);
    raw = raw.split("/").pop() || "";
  }
  if (!raw || raw === "." || raw === ".." || raw.includes("/") || raw.includes("\\")) {
    throw new UsageError("Slug must be the short code or a public article URL.");
  }
  if ([...raw].some((ch) => /\s/.test(ch) || "?#&=".includes(ch))) {
    throw new UsageError("Slug contains characters that are not part of a short code.");
  }
  return raw;
}

function publicArticleUrl(baseUrl, slug) {
  return `${baseUrl}/${encodeURIComponent(slug)}`;
}

export function splitMarkdown(text, title) {
  if (title !== undefined && title !== null) {
    const cleaned = title.trim();
    if (!cleaned) throw new UsageError("Title is empty.");
    if (text.trim() === "") throw new UsageError("Content is empty.");
    return [cleaned, text];
  }
  const lines = text.split(/\r?\n/);
  let index = 0;
  while (index < lines.length && lines[index].trim() === "") index += 1;
  if (index < lines.length && lines[index].startsWith("# ")) {
    const derived = lines[index].slice(2).trim();
    let rest = lines.slice(index + 1);
    if (rest.length && rest[0].trim() === "") rest = rest.slice(1);
    let body = rest.join("\n");
    if (!body.endsWith("\n") && text.endsWith("\n")) body += "\n";
    if (derived && body.trim()) return [derived, body];
  }
  throw new UsageError('Pass --title, or start the Markdown with a "# title" heading and a body.');
}

function readTextFile(filePath) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    throw new UsageError(`File not found: ${filePath}`);
  }
  const raw = fs.readFileSync(filePath);
  if (raw.includes(0)) throw new UsageError(`${filePath} is not valid UTF-8.`);
  let text = raw.toString("utf8");
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  return text;
}

function loadSecretFile(filePath, field) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    throw new UsageError(`File not found: ${filePath}`);
  }
  const mode = fs.statSync(filePath).mode & 0o777;
  const raw = fs.readFileSync(filePath, "utf8");
  let value = "";
  const stripped = raw.trim();
  if (stripped.startsWith("{")) {
    let data;
    try {
      data = JSON.parse(stripped);
    } catch {
      throw new UsageError(`${filePath} is not valid JSON.`);
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new UsageError(`${filePath} must contain a JSON object.`);
    }
    const candidate = data[field] ?? "";
    if (typeof candidate !== "string") throw new UsageError(`${filePath} field ${field} must be a string.`);
    value = candidate;
  } else {
    const lines = raw.split(/\r?\n/).filter((line) => line.trim());
    if (lines.length !== 1) throw new UsageError(`${filePath} should be a single secret, or JSON with ${field}.`);
    value = lines[0].trim();
  }
  if (!value) throw new UsageError(`${filePath} does not contain ${field}.`);
  return [value, mode & 0o077 ? filePath : null];
}

function ensureSecretDestination(filePath) {
  if (filePath.includes("\n") || filePath.includes("\0")) {
    throw new UsageError("Secret file path contains a newline or NUL.");
  }
  if (fs.existsSync(filePath)) throw new UsageError(`${filePath} already exists. Choose a new path.`);
  const parent = path.dirname(filePath);
  if (parent && !fs.existsSync(parent)) throw new UsageError(`Directory does not exist: ${parent}`);
}

function writePrivateFile(filePath, payload) {
  ensureSecretDestination(filePath);
  const body = `${JSON.stringify(payload, null, 2)}\n`;
  const flags = fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | (fs.constants.O_NOFOLLOW || 0);
  let fd;
  try {
    fd = fs.openSync(filePath, flags, 0o600);
    fs.writeFileSync(fd, body);
    fs.fchmodSync(fd, 0o600);
  } catch (error) {
    if (fd !== undefined) fs.closeSync(fd);
    if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
    if (error && error.code === "EEXIST") throw new UsageError(`${filePath} already exists. Choose a new path.`);
    throw error;
  }
  fs.closeSync(fd);
  const info = fs.lstatSync(filePath);
  if (info.isSymbolicLink() || !info.isFile()) {
    fs.unlinkSync(filePath);
    throw new ClientError("Refusing to leave a secret on a non-regular file.");
  }
  if ((info.mode & 0o077) !== 0) {
    fs.unlinkSync(filePath);
    throw new ClientError("Refusing to leave a secret file that other users can read.");
  }
}

function warnIfUnignored(filePath, stderr) {
  let cursor = path.resolve(path.dirname(filePath));
  let gitRoot = null;
  while (true) {
    if (fs.existsSync(path.join(cursor, ".git"))) {
      gitRoot = cursor;
      break;
    }
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }
  if (!gitRoot) return;
  const result = spawnSync("git", ["check-ignore", "-q", "--", path.resolve(filePath)], { cwd: gitRoot });
  if (result.status !== 0) {
    stderr.write(`warning: ${filePath} is inside a git checkout and is not ignored. Do not commit it.\n`);
  }
}

function jsonBytes(payload) {
  return Buffer.from(JSON.stringify(payload), "utf8");
}

export function redactValue(value) {
  if (Array.isArray(value)) return value.map((item) => redactValue(item));
  if (value && typeof value === "object") {
    const cleaned = {};
    for (const [key, item] of Object.entries(value)) {
      cleaned[key] = SECRET_FIELDS.has(String(key).toLowerCase()) ? "REDACTED" : redactValue(item);
    }
    return cleaned;
  }
  return value;
}

function redactText(text, secrets = []) {
  let cleaned = text.replace(
    /("(?:edit_key|access_token|view_password|password|token|auth_url)"\s*:\s*")((?:[^"\\]|\\.)*)(")/gi,
    (_m, open, _value, close) => `${open}REDACTED${close}`,
  );
  cleaned = cleaned.replace(
    /\b(edit_key|access_token|view_password|password|token|auth_url)=([^\s&]+)/gi,
    (_m, key) => `${key}=REDACTED`,
  );
  for (const secret of secrets) {
    if (secret) cleaned = cleaned.split(secret).join("REDACTED");
  }
  return cleaned;
}

function redactUrl(url) {
  const parsed = new URL(url);
  const pairs = [...parsed.searchParams.entries()];
  parsed.search = "";
  const bits = pairs.map(([key, value]) => {
    if (SECRET_FIELDS.has(key.toLowerCase())) return `${encodeURIComponent(key)}=REDACTED`;
    return `${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
  });
  const query = bits.join("&");
  return `${parsed.origin}${parsed.pathname}${query ? `?${query}` : ""}`;
}

function encodeMultipart(parts) {
  const boundary = `glanoteBoundary${Buffer.from(Array.from({ length: 12 }, () => Math.floor(Math.random() * 256))).toString("hex")}`;
  const chunks = [];
  for (const part of parts) {
    if (part.data.includes(Buffer.from(boundary))) {
      throw new ClientError("Could not build a multipart body. Try the upload again.");
    }
    let disposition = `form-data; name="${part.name}"`;
    if (part.filename) disposition += `; filename="${part.filename}"`;
    chunks.push(Buffer.from(`--${boundary}\r\n`, "ascii"));
    chunks.push(Buffer.from(`Content-Disposition: ${disposition}\r\n`, "utf8"));
    if (part.contentType) chunks.push(Buffer.from(`Content-Type: ${part.contentType}\r\n`, "ascii"));
    chunks.push(Buffer.from("\r\n", "ascii"));
    chunks.push(part.data);
    chunks.push(Buffer.from("\r\n", "ascii"));
  }
  chunks.push(Buffer.from(`--${boundary}--\r\n`, "ascii"));
  return [Buffer.concat(chunks), `multipart/form-data; boundary=${boundary}`];
}

function formBytes(fields) {
  const params = new URLSearchParams();
  for (const [key, value] of fields) params.append(key, value);
  return Buffer.from(params.toString(), "utf8");
}

function buildImagePart(filePath) {
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) throw new UsageError(`File not found: ${filePath}`);
  const suffix = path.extname(filePath).toLowerCase();
  if ([".mp4", ".mov", ".webm", ".mkv", ".avi"].includes(suffix)) {
    throw new UsageError("Video files are not accepted. The limit covers JPG, PNG, WebP, and GIF.");
  }
  if (!IMAGE_TYPES[suffix]) throw new UsageError("Images must be JPG, PNG, WebP, or GIF.");
  const size = fs.statSync(filePath).size;
  if (size > MAX_IMAGE_BYTES) throw new UsageError("Image is larger than the documented 5 MB limit.");
  if (size === 0) throw new UsageError("Image file is empty.");
  const filename = path.basename(filePath).replaceAll('"', "");
  if (filename.includes('"') || filename.includes("\r") || filename.includes("\n") || filename.includes("\\")) {
    throw new UsageError("Image file name cannot include quotes, slashes, or newlines.");
  }
  return {
    name: "image",
    filename,
    contentType: IMAGE_TYPES[suffix],
    data: fs.readFileSync(filePath),
  };
}

function telegraphNodes(text, content) {
  if (text !== undefined && content !== undefined) throw new UsageError("Pass either --text or --content.");
  if (content !== undefined) {
    let parsed;
    try {
      parsed = JSON.parse(content);
    } catch {
      throw new UsageError("--content must be a JSON array of Telegraph nodes.");
    }
    if (!Array.isArray(parsed)) throw new UsageError("--content must be a JSON array of Telegraph nodes.");
    return JSON.stringify(parsed);
  }
  if (text !== undefined) {
    if (text === "") throw new UsageError("Telegraph text is empty.");
    return JSON.stringify([{ tag: "p", children: [text] }]);
  }
  throw new UsageError("Pass --text or --content for the Telegraph page.");
}

function resolveTimeout(raw, env) {
  const source = raw !== undefined ? raw : env.GLANOTE_TIMEOUT;
  if (source === undefined || source === "") return DEFAULT_TIMEOUT;
  const value = Number(source);
  if (!Number.isFinite(value)) throw new UsageError("Timeout must be a number of seconds.");
  if (value <= 0 || value > 300) throw new UsageError("Timeout must be greater than 0 and at most 300 seconds.");
  return value;
}

function resolveBase(raw, env) {
  const source = raw !== undefined ? raw : env.GLANOTE_BASE_URL || DEFAULT_BASE_URL;
  return normalizeBaseUrl(source);
}

function readStdin(io, label) {
  if (io.stdin !== undefined) return io.stdin;
  if (process.stdin.isTTY) throw new UsageError(`Pass --file or --content, or pipe ${label} on stdin.`);
  return fs.readFileSync(0, "utf8");
}

function viewPasswordFrom(args) {
  if (args.viewPassword !== undefined && args.viewPasswordFile) {
    throw new UsageError("Pass only one of --view-password and --view-password-file.");
  }
  if (args.viewPasswordFile) {
    const [value, warning] = loadSecretFile(args.viewPasswordFile, "view_password");
    if (warning) args.modeWarnings.push(warning);
    return value;
  }
  if (args.viewPassword !== undefined) {
    if (args.viewPassword === "") throw new UsageError("View password is empty.");
    return args.viewPassword;
  }
  return undefined;
}

function cliFlag(name) {
  return `--${name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
}

function managementKey(args, flag, fileFlag, field) {
  const inline = args[flag];
  const filePath = args[fileFlag];
  const option = cliFlag(flag);
  const fileOption = cliFlag(fileFlag);
  if (inline && filePath) throw new UsageError(`Pass only one of ${option} and ${fileOption}.`);
  if (filePath) {
    const [value, warning] = loadSecretFile(filePath, field);
    if (warning) args.modeWarnings.push(warning);
    return value;
  }
  if (inline !== undefined) {
    if (inline.trim() === "") throw new UsageError("Management key is empty.");
    return inline;
  }
  throw new UsageError("This call needs an edit key or access token. Pass it explicitly.");
}

function requireYes(args, action) {
  if (!args.yes) throw new UsageError(`${action} needs --yes in addition to the key.`);
}

function articleBody(title, content, author, viewPassword) {
  const ordered = { title };
  if (author !== undefined) {
    if (author.trim() === "") throw new UsageError("Author is empty.");
    ordered.author = author;
  }
  ordered.content = content;
  if (viewPassword !== undefined) ordered.view_password = viewPassword;
  return ordered;
}

function commandPublish(args, base, io) {
  if (args.file && args.content !== undefined) throw new UsageError("Pass only one of --file and --content.");
  let text;
  if (args.file) text = readTextFile(args.file);
  else if (args.content !== undefined) text = args.content;
  else text = readStdin(io, "Markdown");
  const [title, content] = splitMarkdown(text, args.title);
  const password = viewPasswordFrom(args);
  return request("POST", `${base}/api/articles`, {
    "content-type": "application/json",
    accept: "application/json",
    "user-agent": USER_AGENT,
  }, jsonBytes(articleBody(title, content, args.author, password)));
}

function commandRead(args, base) {
  const slug = normalizeSlug(args.slug || "");
  const headers = { "user-agent": USER_AGENT, accept: "*/*" };
  const password = viewPasswordFrom(args);
  if (args.markdown) {
    if (password) {
      throw new UsageError("The documented password header is for GET /api/articles/SLUG, not the .md URL.");
    }
    return request("GET", `${base}/${encodeURIComponent(slug)}.md`, headers, null);
  }
  if (password) headers["X-View-Password"] = password;
  headers.accept = "application/json";
  return request("GET", `${base}/api/articles/${encodeURIComponent(slug)}`, headers, null);
}

function editPayload(args, io) {
  requireYes(args, "edit");
  const key = managementKey(args, "editKey", "editKeyFile", "edit_key");
  if (args.file && args.content !== undefined) throw new UsageError("Pass only one of --file and --content.");
  let text;
  if (args.file) text = readTextFile(args.file);
  else if (args.content !== undefined) text = args.content;
  else text = readStdin(io, "Markdown");
  const [title, content] = splitMarkdown(text, args.title);
  return { edit_key: key, title, content };
}

function commandEdit(args, base, io) {
  const slug = normalizeSlug(args.slug || "");
  return request("PUT", `${base}/api/articles/${encodeURIComponent(slug)}`, {
    "content-type": "application/json",
    accept: "application/json",
    "user-agent": USER_AGENT,
  }, jsonBytes(editPayload(args, io)));
}

function commandDelete(args, base) {
  requireYes(args, "delete");
  const slug = normalizeSlug(args.slug || "");
  const key = managementKey(args, "editKey", "editKeyFile", "edit_key");
  return request("DELETE", `${base}/api/articles/${encodeURIComponent(slug)}`, {
    "content-type": "application/json",
    accept: "application/json",
    "user-agent": USER_AGENT,
  }, jsonBytes({ edit_key: key }));
}

function commandImage(args, base) {
  const [body, contentType] = encodeMultipart([buildImagePart(args.image || "")]);
  return request("POST", `${base}/api/images`, {
    "content-type": contentType,
    accept: "*/*",
    "user-agent": USER_AGENT,
  }, body);
}

function commandNew(args, base) {
  const hasText = args.text !== undefined;
  const hasFile = args.file !== undefined;
  const hasTitle = args.title !== undefined;
  const hasImage = args.image !== undefined;
  const url = `${base}/api/new?format=json`;
  const headers = { accept: "application/json", "user-agent": USER_AGENT };
  if (hasText && !hasFile && !hasTitle && !hasImage) {
    headers["content-type"] = "application/x-www-form-urlencoded";
    return request("POST", url, headers, formBytes([["text", args.text ?? ""]]));
  }
  if (hasFile && !hasText && !hasTitle && !hasImage) {
    const filename = path.basename(args.file || "note.md").replaceAll('"', "");
    if (filename.includes('"') || filename.includes("\r") || filename.includes("\n") || filename.includes("\\")) {
      throw new UsageError("Markdown file name cannot include quotes, slashes, or newlines.");
    }
    const [body, contentType] = encodeMultipart([{
      name: "file",
      filename,
      contentType: "text/markdown; charset=utf-8",
      data: Buffer.from(readTextFile(args.file || ""), "utf8"),
    }]);
    headers["content-type"] = contentType;
    return request("POST", url, headers, body);
  }
  if (hasTitle && hasText && hasImage && !hasFile) {
    const [body, contentType] = encodeMultipart([
      { name: "title", data: Buffer.from(args.title || "", "utf8") },
      { name: "text", data: Buffer.from(args.text || "", "utf8") },
      buildImagePart(args.image || ""),
    ]);
    headers["content-type"] = contentType;
    return request("POST", url, headers, body);
  }
  throw new UsageError("new accepts three documented forms: --text TEXT; --file PATH; or --title TEXT --text TEXT --image FILE.");
}

function commandPreview(args, base, io) {
  if (args.file && args.content !== undefined) throw new UsageError("Pass only one of --file and --content.");
  let content;
  if (args.file) content = readTextFile(args.file);
  else if (args.content !== undefined) content = args.content;
  else content = readStdin(io, "Markdown");
  if (content.trim() === "") throw new UsageError("Preview content is empty.");
  return request("POST", `${base}/api/preview`, {
    "content-type": "application/json",
    accept: "*/*",
    "user-agent": USER_AGENT,
  }, jsonBytes({ content }));
}

function commandQr(args, base) {
  let parsed;
  try {
    parsed = new URL(args.url || "");
  } catch {
    throw new UsageError("qr expects an http(s) URL.");
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") throw new UsageError("qr expects an http(s) URL.");
  const query = new URLSearchParams({ u: args.url });
  return request("GET", `${base}/api/qr?${query.toString()}`, {
    accept: "image/svg+xml, */*",
    "user-agent": USER_AGENT,
  }, null);
}

function commandTelegraph(args, base) {
  const root = `${base}/telegraph`;
  const headers = { accept: "application/json", "user-agent": USER_AGENT };
  if (args.sub === "account") {
    if (!args.shortName || args.shortName.trim() === "") throw new UsageError("telegraph account needs --short-name.");
    const query = new URLSearchParams();
    query.append("short_name", args.shortName);
    if (args.authorName !== undefined) query.append("author_name", args.authorName);
    return request("GET", `${root}/createAccount?${query.toString()}`, headers, null);
  }
  if (args.sub === "get") {
    const slug = normalizeSlug(args.pagePath || args.slug || "");
    const query = new URLSearchParams();
    query.append("path", slug);
    query.append("return_content", args.returnContent ? "true" : "false");
    return request("GET", `${root}/getPage?${query.toString()}`, headers, null);
  }
  let token = "";
  if (["create", "edit", "list", "info"].includes(args.sub)) {
    token = managementKey(args, "token", "tokenFile", "access_token");
  }
  if (args.sub === "list") {
    return request("GET", `${root}/getPageList?${new URLSearchParams({ access_token: token })}`, headers, null);
  }
  if (args.sub === "info") {
    return request("GET", `${root}/getAccountInfo?${new URLSearchParams({ access_token: token })}`, headers, null);
  }
  const nodes = telegraphNodes(args.text, args.content);
  if (!args.title || args.title.trim() === "") throw new UsageError("Telegraph page needs --title.");
  if (args.sub === "create") {
    const fields = [["access_token", token], ["title", args.title], ["content", nodes]];
    if (args.returnContent) fields.push(["return_content", "true"]);
    headers["content-type"] = "application/x-www-form-urlencoded";
    return request("POST", `${root}/createPage`, headers, formBytes(fields));
  }
  if (args.sub === "edit") {
    requireYes(args, "telegraph edit");
    const slug = normalizeSlug(args.pagePath || "");
    headers["content-type"] = "application/x-www-form-urlencoded";
    return request("POST", `${root}/editPage`, headers, formBytes([
      ["access_token", token],
      ["path", slug],
      ["title", args.title],
      ["content", nodes],
    ]));
  }
  throw new UsageError("Unknown telegraph method.");
}

function request(method, url, headers, body) {
  return { method, url, headers, body };
}

function buildRequest(args, base, io) {
  switch (args.command) {
    case "publish": return commandPublish(args, base, io);
    case "read": return commandRead(args, base);
    case "edit": return commandEdit(args, base, io);
    case "delete": return commandDelete(args, base);
    case "image": return commandImage(args, base);
    case "new": return commandNew(args, base);
    case "preview": return commandPreview(args, base, io);
    case "qr": return commandQr(args, base);
    case "telegraph": return commandTelegraph(args, base);
    default: throw new UsageError(`Unknown command ${args.command}.`);
  }
}

function secretsInRequest(req) {
  const found = [];
  if (req.headers["X-View-Password"]) found.push(req.headers["X-View-Password"]);
  const contentType = req.headers["content-type"] || "";
  if (!req.body) {
    const query = new URL(req.url).searchParams;
    for (const [key, value] of query.entries()) {
      if (SECRET_FIELDS.has(key.toLowerCase()) && value) found.push(value);
    }
    return found;
  }
  const text = req.body.toString("utf8");
  if (contentType.startsWith("application/json")) {
    try {
      const data = JSON.parse(text);
      if (data && typeof data === "object") {
        for (const [key, value] of Object.entries(data)) {
          if (SECRET_FIELDS.has(key.toLowerCase()) && typeof value === "string") found.push(value);
        }
      }
    } catch {
      // not JSON
    }
  } else if (contentType.startsWith("application/x-www-form-urlencoded")) {
    const params = new URLSearchParams(text);
    for (const [key, value] of params.entries()) {
      if (SECRET_FIELDS.has(key.toLowerCase()) && value) found.push(value);
    }
  }
  return found;
}

function dryText(req, secrets) {
  const lines = [`${req.method} ${redactUrl(req.url)}`];
  for (const [key, value] of Object.entries(req.headers)) {
    lines.push(key.toLowerCase() === "x-view-password" ? `${key}: REDACTED` : `${key}: ${value}`);
  }
  if (req.body) lines.push(redactText(req.body.toString("utf8"), secrets));
  return `${lines.join("\n")}\n`;
}

function decode(raw) {
  return Buffer.from(raw).toString("utf8");
}

function parseJson(raw) {
  if (raw.length > MAX_RESPONSE_BYTES) throw new ClientError("Response exceeded 2 MB and was not printed.");
  try {
    return JSON.parse(decode(raw));
  } catch {
    throw new ClientError("Response was not valid JSON.");
  }
}

function scrubbedPublicUrl(url, secrets) {
  if (typeof url !== "string" || !(url.startsWith("https://") || url.startsWith("http://"))) {
    throw new ClientError("Response JSON did not include a public http(s) url.");
  }
  for (const secret of secrets) {
    if (secret && url.includes(secret)) {
      throw new ClientError("Refusing to print a public URL that contains a management secret.");
    }
  }
  return url;
}

function emitKey({ kind, secret, url, show, savePath, stderr }) {
  if (!secret) throw new ClientError(`Response did not include ${kind}.`);
  const record = { [kind]: secret };
  if (url) record.url = url;
  if (savePath) {
    writePrivateFile(savePath, record);
    stderr.write(`Wrote ${kind} to ${savePath} with mode 600. Do not commit that file or put the key in a public URL.\n`);
    warnIfUnignored(savePath, stderr);
  }
  if (show) {
    const flag = kind === "access_token" ? "--show-token" : "--show-key";
    stderr.write(`${kind}=${secret}\nPrinted on stderr because ${flag} was set. Terminal scrollback and CI logs may keep it.\n`);
  }
  if (!savePath && !show) {
    if (kind === "access_token") {
      stderr.write("The access_token was not printed or saved. createAccount returns it once; later calls need the same token. Pass --save-token or --show-token to keep it.\n");
    } else {
      stderr.write("The edit_key was not printed or saved, and it cannot be recovered. Publishing again creates a different article. Pass --save-key or --show-key when you need to edit or delete.\n");
    }
  }
}

function finishArticlePublish(raw, args, stdout, stderr, secrets) {
  const payload = parseJson(raw);
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new ClientError("Publish response was not a JSON object.");
  }
  const secret = typeof payload.edit_key === "string" && payload.edit_key ? payload.edit_key : null;
  if (secret) secrets.push(secret);
  let url = "";
  let urlError = null;
  try {
    url = scrubbedPublicUrl(payload.url, secrets);
  } catch (error) {
    urlError = error;
  }
  if (secret || args.showKey || args.saveKey) {
    emitKey({
      kind: "edit_key",
      secret,
      url: url || null,
      show: args.showKey,
      savePath: args.saveKey,
      stderr,
    });
  } else if (args.command === "publish") {
    stderr.write("Response JSON did not include edit_key. Nothing secret was printed.\n");
  }
  if (urlError) {
    const redacted = redactText(JSON.stringify(redactValue(payload)).slice(0, 1000), secrets);
    throw new ClientError(`${urlError.message}\n${redacted}`);
  }
  stdout.write(`${url}\n`);
  return url;
}

function writeOpaque(raw, contentType, stdout) {
  if (raw.length > MAX_RESPONSE_BYTES) throw new ClientError("Response exceeded 2 MB and was not printed.");
  const text = decode(raw);
  if ((contentType || "").toLowerCase().includes("json") || /^\s*[{[]/.test(text)) {
    try {
      stdout.write(`${JSON.stringify(redactValue(JSON.parse(text)), null, 2)}\n`);
      return;
    } catch {
      stdout.write(redactText(text).endsWith("\n") ? redactText(text) : `${redactText(text)}\n`);
      return;
    }
  }
  stdout.write(text.endsWith("\n") || text === "" ? text : `${text}\n`);
}

function emitSuccess(args, req, raw, contentType, base, stdout, stderr) {
  const secrets = secretsInRequest(req);
  const bytes = Buffer.from(raw);
  if (args.command === "publish" || args.command === "new") {
    finishArticlePublish(bytes, args, stdout, stderr, secrets);
    return;
  }
  if (args.command === "delete") {
    stdout.write(`deleted ${publicArticleUrl(base, normalizeSlug(args.slug || ""))}\n`);
    return;
  }
  if (args.command === "edit") {
    stdout.write(`${publicArticleUrl(base, normalizeSlug(args.slug || ""))}\n`);
    return;
  }
  if (args.command === "qr") {
    if (bytes.length > MAX_RESPONSE_BYTES) throw new ClientError("Response exceeded 2 MB and was not printed.");
    if (args.output) {
      fs.writeFileSync(args.output, bytes);
      stderr.write(`Wrote ${args.output}\n`);
    } else {
      stdout.write(decode(bytes));
    }
    return;
  }
  if (args.command === "image") {
    stderr.write("Image upload response is below. The API page says to paste the returned Markdown into an article. Images are protected against hotlinking from other sites.\n");
    writeOpaque(bytes, contentType, stdout);
    return;
  }
  if (args.command === "preview") {
    stderr.write("Preview only. Nothing was published.\n");
    writeOpaque(bytes, contentType, stdout);
    return;
  }
  if (args.command === "read") {
    if (args.markdown) {
      const text = decode(bytes);
      stdout.write(text.endsWith("\n") || text === "" ? text : `${text}\n`);
      return;
    }
    stdout.write(`${JSON.stringify(redactValue(parseJson(bytes)), null, 2)}\n`);
    return;
  }
  if (args.command === "telegraph") {
    const payload = parseJson(bytes);
    if (!payload || payload.ok !== true) {
      const message = payload && typeof payload.error === "string" ? payload.error : "";
      throw new ClientError(`Telegraph response did not include ok: true.${message ? ` error=${message}` : ""}`);
    }
    if (!payload.result || typeof payload.result !== "object" || Array.isArray(payload.result)) {
      throw new ClientError("Telegraph response did not include a result object.");
    }
    if (args.sub === "account") {
      const secret = typeof payload.result.access_token === "string" ? payload.result.access_token : null;
      const redacted = redactValue(payload.result);
      stdout.write(typeof redacted.short_name === "string" ? `${redacted.short_name}\n` : `${JSON.stringify(redacted, null, 2)}\n`);
      emitKey({
        kind: "access_token",
        secret,
        url: null,
        show: args.showToken,
        savePath: args.saveToken,
        stderr,
      });
      return;
    }
    if (args.sub === "create") {
      stdout.write(`${scrubbedPublicUrl(payload.result.url, secrets)}\n`);
      return;
    }
    stdout.write(`${JSON.stringify(redactValue(payload.result), null, 2)}\n`);
  }
}

async function perform(req, timeout, fetchImpl, secrets) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout * 1000);
  try {
    const response = await fetchImpl(req.url, {
      method: req.method,
      headers: req.headers,
      body: req.body && req.body.length ? req.body : undefined,
      signal: controller.signal,
      redirect: "manual",
    });
    const raw = Buffer.from(await response.arrayBuffer());
    if (raw.length > MAX_RESPONSE_BYTES) throw new ClientError("Response exceeded 2 MB and was not printed.");
    if (response.status >= 300 && response.status < 400) {
      throw new ClientError(`HTTP ${response.status} redirect is not followed.`);
    }
    if (response.status < 200 || response.status >= 300) {
      throw new ClientError(`HTTP ${response.status}\n${redactText(decode(raw).slice(0, 2048), secrets)}`);
    }
    return [response.status, response.headers.get("content-type") || "", raw];
  } catch (error) {
    if (error instanceof ClientError) throw error;
    if (error && (error.name === "AbortError" || error.name === "TimeoutError")) {
      throw new ClientError(`Request timed out after ${timeout} seconds.`);
    }
    throw new ClientError(`Request failed: ${error.message || error}`);
  } finally {
    clearTimeout(timer);
  }
}

function writeStream(chunks) {
  return {
    chunks,
    write(text) {
      chunks.push(text);
    },
  };
}

export async function main(argv, io = {}) {
  const stdout = io.stdout || writeStreamTo(process.stdout);
  const stderr = io.stderr || writeStreamTo(process.stderr);
  const env = io.env || process.env;
  const fetchImpl = io.fetch || globalThis.fetch;
  try {
    const args = parseArgs(argv);
    const base = resolveBase(args.baseUrl, env);
    const timeout = resolveTimeout(args.timeout, env);
    const req = buildRequest(args, base, io);
    if (args.saveKey) ensureSecretDestination(args.saveKey);
    if (args.saveToken) ensureSecretDestination(args.saveToken);
    for (const warning of args.modeWarnings) {
      stderr.write(`warning: ${warning} is readable by other users. chmod 600 it.\n`);
    }
    const requestSecrets = secretsInRequest(req);
    if (args.dryRun) {
      stderr.write(dryText(req, requestSecrets));
      return 0;
    }
    const [_status, contentType, raw] = await perform(req, timeout, fetchImpl, requestSecrets);
    emitSuccess(args, req, raw, contentType, base, stdout, stderr);
    return 0;
  } catch (error) {
    if (error instanceof UsageError) {
      stderr.write(`${String(error.message).replace(/\s+$/, "")}\n`);
      const text = String(error.message);
      return text === HELP || text.startsWith("glanote ") ? 0 : 2;
    }
    if (error instanceof ClientError) {
      stderr.write(`${String(error.message).replace(/\s+$/, "")}\n`);
      return 1;
    }
    stderr.write(`Request failed: ${error && error.message ? error.message : error}\n`);
    return 1;
  }
}

function writeStreamTo(stream) {
  return {
    write(text) {
      stream.write(text);
    },
  };
}

const entry = process.argv[1] ? pathToFileURL(process.argv[1]).href : "";
if (import.meta.url === entry) {
  const code = await main(process.argv.slice(2));
  process.exit(code);
}

export { MAX_IMAGE_BYTES, UsageError };
