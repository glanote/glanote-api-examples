#!/usr/bin/env python3
"""Offline tests for the Python Glanote client."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import glanote  # noqa: E402


TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)
SECRET = "unit-test-edit-key-9f3a"
VIEW = "unit-test-view-pw-44c1"
TOKEN = "unit-test-access-token-77ab"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_GET(self):  # noqa: N802
        self._handle()

    do_POST = do_PUT = do_DELETE = do_GET

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        record = {
            "method": self.command,
            "path": self.path,
            "headers": {key.lower(): value for key, value in self.headers.items()},
            "body": body,
        }
        self.server.requests.append(record)
        delay = getattr(self.server, "delay", 0)
        if delay:
            time.sleep(delay)
        spec = self.server.reply
        payload = spec.get("body", b"{}")
        if callable(payload):
            payload = payload(record)
        data = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
        try:
            self.send_response(spec.get("code", 200))
            self.send_header("content-type", spec.get("type", "application/json; charset=utf-8"))
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, fmt: str, *args) -> None:
        return


class ApiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.daemon_threads = True
        cls.server.requests = []
        cls.server.reply = {"code": 200, "body": b"{}"}
        cls.server.delay = 0
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.server.requests = []
        self.server.delay = 0
        self.server.reply = {
            "code": 200,
            "body": json.dumps({"url": f"{self.base}/ab12cd", "edit_key": SECRET}),
        }

    def run_cli(self, argv, stdin=""):
        stdout = StringIO()
        stderr = StringIO()
        code = glanote.main(
            argv,
            stdin=StringIO(stdin),
            stdout=stdout,
            stderr=stderr,
            env={"GLANOTE_BASE_URL": self.base},
        )
        return code, stdout.getvalue(), stderr.getvalue()

    def test_help_and_version(self) -> None:
        code, _out, err = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("--base-url", err)
        self.assertIn("--timeout", err)
        self.assertIn("https://glanote.com/en/api", err)
        code, _out, err = self.run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(glanote.VERSION, err)

    def test_base_url_rejects_secrets_and_non_http(self) -> None:
        for value in (
            "file:///tmp/x",
            "https://user:pass@glanote.com",
            "https://glanote.com/?q=1",
            "https://glanote.com/#frag",
            "javascript:alert(1)",
        ):
            code, _out, err = self.run_cli(["--base-url", value, "read", "f6a0b2"])
            self.assertEqual(code, 2, err)
            self.assertEqual(self.server.requests, [])

    def test_publish_unicode_hides_key_and_can_save_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "key.json")
            code, out, err = self.run_cli(
                ["publish", "--title", "测试 café", "--content", "你好 🌟", "--save-key", key_path]
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(out, f"{self.base}/ab12cd\n")
            self.assertNotIn(SECRET, out)
            self.assertNotIn(SECRET, err)
            saved = json.loads(Path(key_path).read_text(encoding="utf-8"))
            self.assertEqual(saved["edit_key"], SECRET)
            self.assertEqual(saved["url"], f"{self.base}/ab12cd")
            mode = stat.S_IMODE(Path(key_path).stat().st_mode)
            self.assertEqual(mode, 0o600)
        body = json.loads(self.server.requests[0]["body"].decode("utf-8"))
        self.assertEqual(body, {"title": "测试 café", "content": "你好 🌟"})
        self.assertIn("测试 café".encode("utf-8"), self.server.requests[0]["body"])
        self.assertNotIn(b"\\u00e9", self.server.requests[0]["body"])
        self.assertEqual(self.server.requests[0]["headers"]["content-type"], "application/json")

    def test_show_key_is_stderr_only(self) -> None:
        code, out, err = self.run_cli(
            ["publish", "--title", "T", "--content", "body", "--show-key"]
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"{self.base}/ab12cd\n")
        self.assertNotIn(SECRET, out)
        self.assertIn(SECRET, err)

    def test_discarded_key_is_not_echoed(self) -> None:
        code, out, err = self.run_cli(["publish", "--title", "T", "--content", "body"])
        self.assertEqual(code, 0, err)
        self.assertNotIn(SECRET, out)
        self.assertNotIn(SECRET, err)
        self.assertIn("cannot be recovered", err)

    def test_view_password_stays_out_of_output_and_key_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "key.json")
            code, out, err = self.run_cli(
                [
                    "publish",
                    "--title", "T",
                    "--content", "secret body",
                    "--view-password", VIEW,
                    "--save-key", key_path,
                    "--dry-run",
                ]
            )
            self.assertEqual(code, 0, err)
            self.assertNotIn(VIEW, out)
            self.assertNotIn(VIEW, err)
            self.assertIn('"view_password":"REDACTED"', err)
            self.assertEqual(self.server.requests, [])
            code, out, err = self.run_cli(
                [
                    "publish",
                    "--title", "T",
                    "--content", "secret body",
                    "--view-password", VIEW,
                    "--save-key", key_path,
                ]
            )
            self.assertEqual(code, 0, err)
            self.assertNotIn(VIEW, out)
            self.assertNotIn(VIEW, err)
            saved = Path(key_path).read_text(encoding="utf-8")
            self.assertNotIn(VIEW, saved)
        body = json.loads(self.server.requests[0]["body"].decode("utf-8"))
        self.assertEqual(body["view_password"], VIEW)

    def test_markdown_file_and_stdin_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            note.write_text("# 見出し\n\n本文 café\n", encoding="utf-8")
            code, out, err = self.run_cli(["publish", "--file", str(note), "--dry-run"])
        self.assertEqual(code, 0, err)
        self.assertIn("見出し", err)
        self.assertIn("本文 café", err)
        code, _out, err = self.run_cli(["publish"], stdin="# Piped\n\nfrom stdin\n")
        self.assertEqual(code, 0, err)
        body = json.loads(self.server.requests[0]["body"].decode("utf-8"))
        self.assertEqual(body["title"], "Piped")
        self.assertIn("from stdin", body["content"])

    def test_read_json_markdown_and_password_header(self) -> None:
        self.server.reply = {"code": 200, "body": json.dumps({"slug": "f6a0b2", "title": "Hi"})}
        code, out, err = self.run_cli(["read", "https://glanote.com/f6a0b2.md"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.server.requests[0]["path"], "/api/articles/f6a0b2")
        self.assertIn("Hi", out)
        self.server.requests.clear()
        self.server.reply = {"code": 200, "body": "# source\n", "type": "text/markdown"}
        code, out, _err = self.run_cli(["read", "f6a0b2", "--markdown"])
        self.assertEqual(code, 0)
        self.assertEqual(self.server.requests[0]["path"], "/f6a0b2.md")
        self.assertIn("# source", out)
        self.server.requests.clear()
        self.server.reply = {"code": 200, "body": json.dumps({"ok": True})}
        code, out, err = self.run_cli(
            ["read", "f6a0b2", "--view-password", VIEW, "--dry-run"]
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn(VIEW, out)
        self.assertNotIn(VIEW, err)
        self.assertIn("X-View-Password: REDACTED", err)
        code, _out, err = self.run_cli(["read", "f6a0b2", "--view-password", VIEW])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.server.requests[0]["headers"].get("x-view-password"), VIEW)
        self.assertNotIn(VIEW, err)

    def test_edit_and_delete_require_key_and_confirmation(self) -> None:
        code, _out, err = self.run_cli(["delete", "ab12cd", "--edit-key", SECRET])
        self.assertEqual(code, 2, err)
        self.assertEqual(self.server.requests, [])
        code, _out, err = self.run_cli(["delete", "ab12cd", "--yes"])
        self.assertEqual(code, 2, err)
        code, out, err = self.run_cli(
            ["delete", f"{self.base}/ab12cd", "--edit-key", SECRET, "--yes", "--dry-run"]
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn(SECRET, out)
        self.assertNotIn(SECRET, err)
        self.assertIn('"edit_key":"REDACTED"', err)
        code, out, err = self.run_cli(
            ["delete", "ab12cd", "--edit-key", SECRET, "--yes"]
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"deleted {self.base}/ab12cd\n")
        self.assertNotIn(SECRET, out)
        self.assertNotIn(SECRET, err)
        sent = json.loads(self.server.requests[-1]["body"].decode("utf-8"))
        self.assertEqual(sent, {"edit_key": SECRET})
        self.assertEqual(self.server.requests[-1]["method"], "DELETE")
        code, out, err = self.run_cli(
            [
                "edit",
                "ab12cd",
                "--edit-key", SECRET,
                "--yes",
                "--title", "改过的标题",
                "--content", "改过的正文",
            ]
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"{self.base}/ab12cd\n")
        self.assertNotIn(SECRET, out)
        sent = json.loads(self.server.requests[-1]["body"].decode("utf-8"))
        self.assertEqual(
            sent,
            {"edit_key": SECRET, "title": "改过的标题", "content": "改过的正文"},
        )
        self.assertEqual(self.server.requests[-1]["method"], "PUT")

    def test_http_error_redacts_secrets(self) -> None:
        self.server.reply = {
            "code": 400,
            "body": json.dumps({"edit_key": SECRET, "message": "no", "password": VIEW}),
        }
        code, out, err = self.run_cli(["publish", "--title", "T", "--content", "body"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("HTTP 400", err)
        self.assertNotIn(SECRET, err)
        self.assertNotIn(VIEW, err)
        self.assertIn("REDACTED", err)

    def test_timeout(self) -> None:
        self.server.delay = 1.5
        started = time.monotonic()
        code, _out, err = self.run_cli(
            ["--timeout", "0.4", "read", "f6a0b2"]
        )
        elapsed = time.monotonic() - started
        self.server.delay = 0
        self.assertEqual(code, 1, err)
        self.assertIn("timed out", err)
        self.assertLess(elapsed, 1.3)

    def test_refuses_url_that_contains_the_key(self) -> None:
        self.server.reply = {
            "code": 200,
            "body": json.dumps({"url": f"http://127.0.0.1/{SECRET}", "edit_key": SECRET}),
        }
        code, out, err = self.run_cli(["publish", "--title", "T", "--content", "body"])
        self.assertEqual(code, 1, err)
        self.assertNotIn(SECRET, out)
        self.assertNotIn(SECRET, err)

    def test_image_upload_limits_and_field_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "demo.png"
            image.write_bytes(TINY_PNG)
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"nope")
            big = Path(tmp) / "big.png"
            with big.open("wb") as handle:
                handle.truncate(glanote.MAX_IMAGE_BYTES + 1)
            code, _out, err = self.run_cli(["image", str(video)])
            self.assertEqual(code, 2, err)
            self.assertEqual(self.server.requests, [])
            code, _out, err = self.run_cli(["image", str(big)])
            self.assertEqual(code, 2, err)
            self.assertIn("5 MB", err)
            self.server.reply = {"code": 200, "body": "![demo](https://example.test/demo.png)\n", "type": "text/plain"}
            code, out, err = self.run_cli(["image", str(image)])
        self.assertEqual(code, 0, err)
        self.assertIn("![demo]", out)
        self.assertIn("hotlinking", err.lower())
        self.assertEqual(self.server.requests[0]["path"], "/api/images")
        self.assertIn(b'name="image"', self.server.requests[0]["body"])
        self.assertIn(b"filename=\"demo.png\"", self.server.requests[0]["body"])
        self.assertIn(TINY_PNG, self.server.requests[0]["body"])

    def test_new_forms_match_the_docs(self) -> None:
        self.server.reply = {
            "code": 200,
            "body": json.dumps({"url": f"{self.base}/cd34ef", "edit_key": SECRET}),
        }
        code, out, err = self.run_cli(["new", "--text", "一句话也能发布成文章"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"{self.base}/cd34ef\n")
        self.assertNotIn(SECRET, out)
        self.assertNotIn(SECRET, err)
        self.assertIn("/api/new?format=json", self.server.requests[0]["path"])
        pairs = urllib.parse.parse_qsl(self.server.requests[0]["body"].decode("utf-8"))
        self.assertEqual(pairs, [("text", "一句话也能发布成文章")])
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "note.md"
            note.write_text("# 从文件发布\n\n正文\n", encoding="utf-8")
            image = Path(tmp) / "demo.png"
            image.write_bytes(TINY_PNG)
            self.server.requests.clear()
            code, _out, err = self.run_cli(["new", "--file", str(note)])
            self.assertEqual(code, 0, err)
            self.assertIn(b'name="file"', self.server.requests[0]["body"])
            self.assertIn("从文件发布".encode("utf-8"), self.server.requests[0]["body"])
            self.server.requests.clear()
            code, _out, err = self.run_cli(
                ["new", "--title", "带图片", "--text", "下面是一张图片", "--image", str(image)]
            )
            self.assertEqual(code, 0, err)
            raw = self.server.requests[0]["body"]
            self.assertIn(b'name="title"', raw)
            self.assertIn(b'name="text"', raw)
            self.assertIn(b'name="image"', raw)
            code, _out, err = self.run_cli(["new", "--title", "only title"])
            self.assertEqual(code, 2, err)

    def test_preview_and_qr(self) -> None:
        self.server.reply = {"code": 200, "body": "<p><strong>粗体</strong></p>", "type": "text/html"}
        code, out, err = self.run_cli(["preview", "--content", "**粗体** 和 `代码`"])
        self.assertEqual(code, 0, err)
        self.assertIn("<strong>粗体</strong>", out)
        self.assertIn("Nothing was published", err)
        sent = json.loads(self.server.requests[0]["body"].decode("utf-8"))
        self.assertEqual(sent, {"content": "**粗体** 和 `代码`"})
        self.assertEqual(self.server.requests[0]["path"], "/api/preview")
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "qr.svg"
            self.server.reply = {"code": 200, "body": "<svg>ok</svg>", "type": "image/svg+xml"}
            code, _out, err = self.run_cli(
                ["qr", "https://glanote.com/f6a0b2", "--output", str(svg)]
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(svg.read_text(encoding="utf-8"), "<svg>ok</svg>")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.server.requests[-1]["path"]).query)
        self.assertEqual(query["u"], ["https://glanote.com/f6a0b2"])

    def test_telegraph_subset_and_token_redaction(self) -> None:
        code, out, err = self.run_cli(
            [
                "--base-url", "http://127.0.0.1:9",
                "telegraph", "list",
                "--token", TOKEN,
                "--dry-run",
            ]
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn(TOKEN, out)
        self.assertNotIn(TOKEN, err)
        self.assertIn("/telegraph/getPageList", err)
        self.assertIn("access_token=REDACTED", err)
        self.server.reply = {
            "code": 200,
            "body": json.dumps({"ok": True, "result": {"short_name": "myblog", "access_token": TOKEN}}),
        }
        with tempfile.TemporaryDirectory() as tmp:
            token_path = str(Path(tmp) / "token.json")
            code, out, err = self.run_cli(
                [
                    "telegraph", "account",
                    "--short-name", "myblog",
                    "--author-name", "Glanote Fan",
                    "--save-token", token_path,
                ]
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(out, "myblog\n")
            self.assertNotIn(TOKEN, out)
            self.assertNotIn(TOKEN, err)
            saved = json.loads(Path(token_path).read_text(encoding="utf-8"))
            self.assertEqual(saved["access_token"], TOKEN)
            self.assertEqual(stat.S_IMODE(Path(token_path).stat().st_mode), 0o600)
        parsed = urllib.parse.urlparse(self.server.requests[0]["path"])
        self.assertEqual(parsed.path, "/telegraph/createAccount")
        self.assertEqual(
            urllib.parse.parse_qsl(parsed.query),
            [("short_name", "myblog"), ("author_name", "Glanote Fan")],
        )
        self.server.requests.clear()
        self.server.reply = {
            "code": 200,
            "body": json.dumps(
                {"ok": True, "result": {"path": "ab12cd", "url": f"{self.base}/ab12cd", "title": "T"}}
            ),
        }
        code, out, err = self.run_cli(
            [
                "telegraph", "create",
                "--token", TOKEN,
                "--title", "来自 Telegraph 接口",
                "--text", "你好，Telegraph！",
            ]
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"{self.base}/ab12cd\n")
        self.assertNotIn(TOKEN, out)
        self.assertNotIn(TOKEN, err)
        pairs = urllib.parse.parse_qsl(self.server.requests[0]["body"].decode("utf-8"))
        fields = dict(pairs)
        self.assertEqual(fields["access_token"], TOKEN)
        self.assertEqual(fields["title"], "来自 Telegraph 接口")
        self.assertEqual(
            json.loads(fields["content"]),
            [{"tag": "p", "children": ["你好，Telegraph！"]}],
        )
        self.assertNotIn("return_content", fields)
        self.assertEqual(self.server.requests[0]["path"], "/telegraph/createPage")
        self.server.requests.clear()
        self.server.reply = {
            "code": 200,
            "body": json.dumps({"ok": True, "result": {"path": "f6a0b2", "title": "AI"}}),
        }
        code, out, err = self.run_cli(["telegraph", "get", "https://glanote.com/f6a0b2"])
        self.assertEqual(code, 0, err)
        self.assertIn("f6a0b2", out)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.server.requests[0]["path"]).query)
        self.assertEqual(query["path"], ["f6a0b2"])
        self.assertEqual(query["return_content"], ["false"])
        code, _out, err = self.run_cli(
            ["telegraph", "edit", "--token", TOKEN, "--path", "f6a0b2", "--title", "T", "--text", "x"]
        )
        self.assertEqual(code, 2, err)
        self.assertIn("--yes", err)

    def test_loose_key_file_warns_without_printing_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "loose.json"
            key_path.write_text(json.dumps({"edit_key": SECRET}), encoding="utf-8")
            os.chmod(key_path, 0o644)
            code, out, err = self.run_cli(
                ["delete", "ab12cd", "--edit-key-file", str(key_path), "--yes", "--dry-run"]
            )
        self.assertEqual(code, 0, err)
        self.assertIn("chmod 600", err)
        self.assertNotIn(SECRET, out)
        self.assertNotIn(SECRET, err)

    def test_env_timeout_and_existing_secret_file(self) -> None:
        code, _out, err = self.run_cli(["--timeout", "0", "read", "f6a0b2"])
        self.assertEqual(code, 2, err)
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "key.json"
            key_path.write_text("{}", encoding="utf-8")
            code, _out, err = self.run_cli(
                ["publish", "--title", "T", "--content", "body", "--save-key", str(key_path)]
            )
        self.assertEqual(code, 2, err)
        self.assertIn("already exists", err)
        self.assertEqual(self.server.requests, [])

    def test_live_script_is_opt_in(self) -> None:
        env = {key: value for key, value in os.environ.items() if key != "GLANOTE_LIVE"}
        result = subprocess.run(
            [sys.executable, str(ROOT / "tests" / "live_opt_in.py")],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("GLANOTE_LIVE", result.stderr)
        self.assertEqual(self.server.requests, [])

    def test_client_source_skips_report_and_telegram(self) -> None:
        text = (ROOT / "python" / "glanote.py").read_text(encoding="utf-8")
        self.assertNotIn("/report", text)
        self.assertNotIn("api.telegram.org", text)
        self.assertNotIn("/telegram/", text)


if __name__ == "__main__":
    unittest.main()
