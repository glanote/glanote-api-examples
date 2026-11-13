#!/usr/bin/env python3
"""Command-line client for the public Glanote article API.

Endpoints match the public docs at https://glanote.com/en/api
This file is an example client. It is not the Glanote server.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "0.1.0"
DEFAULT_BASE_URL = "https://glanote.com"
DEFAULT_TIMEOUT = 30.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024
USER_AGENT = f"glanote-api-examples/{VERSION}"

IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

SECRET_FIELDS = {
    "edit_key",
    "access_token",
    "view_password",
    "password",
    "token",
    "auth_url",
}

SECRET_QUERY_KEYS = {"access_token", "edit_key", "view_password", "password", "token"}

HELP = """\
glanote — publish and read Markdown with the public Glanote API
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
"""


class UsageError(Exception):
    """The command line does not match the documented calls."""


class ClientError(Exception):
    """A request failed, or the response could not be used safely."""


class Args:
    def __init__(self) -> None:
        self.command = ""
        self.sub = ""
        self.base_url: str | None = None
        self.timeout: str | None = None
        self.dry_run = False
        self.file: str | None = None
        self.title: str | None = None
        self.author: str | None = None
        self.content: str | None = None
        self.view_password: str | None = None
        self.view_password_file: str | None = None
        self.show_key = False
        self.save_key: str | None = None
        self.slug: str | None = None
        self.markdown = False
        self.edit_key: str | None = None
        self.edit_key_file: str | None = None
        self.yes = False
        self.image: str | None = None
        self.text: str | None = None
        self.output: str | None = None
        self.url: str | None = None
        self.short_name: str | None = None
        self.author_name: str | None = None
        self.show_token = False
        self.save_token: str | None = None
        self.token: str | None = None
        self.token_file: str | None = None
        self.path: str | None = None
        self.return_content = False
        self.positional: list[str] = []
        self.mode_warnings: list[str] = []


def parse_args(argv: list[str]) -> Args:
    if not argv or argv[0] in ("-h", "--help", "help"):
        raise UsageError(HELP)
    if argv[0] in ("-V", "--version", "version"):
        raise UsageError(f"glanote {VERSION}")

    args = Args()
    tokens = list(argv)
    positional: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "--":
            positional.extend(tokens[i + 1 :])
            break
        if token in ("-h", "--help"):
            raise UsageError(HELP)
        if token == "--version":
            raise UsageError(f"glanote {VERSION}")
        if token == "--dry-run":
            args.dry_run = True
            i += 1
            continue
        if token == "--show-key":
            args.show_key = True
            i += 1
            continue
        if token == "--show-token":
            args.show_token = True
            i += 1
            continue
        if token == "--yes":
            args.yes = True
            i += 1
            continue
        if token == "--markdown":
            args.markdown = True
            i += 1
            continue
        if token == "--return-content":
            args.return_content = True
            i += 1
            continue
        if token.startswith("--"):
            name, value, consumed = _option(tokens, i)
            i += consumed
            _assign(args, name, value)
            continue
        positional.append(token)
        i += 1

    if not positional:
        raise UsageError("Missing command.\n\n" + HELP)
    args.command = positional[0]
    rest = positional[1:]
    known = {
        "publish",
        "read",
        "edit",
        "delete",
        "image",
        "new",
        "preview",
        "qr",
        "telegraph",
    }
    if args.command not in known:
        raise UsageError(f"Unknown command {args.command!r}.\n\n" + HELP)
    if args.command == "telegraph":
        if not rest:
            raise UsageError("Missing telegraph method.\n\n" + HELP)
        args.sub = rest[0]
        rest = rest[1:]
        methods = {"account", "create", "get", "edit", "list", "info"}
        if args.sub not in methods:
            raise UsageError(
                f"Unknown telegraph method {args.sub!r}. "
                "Documented methods: account, create, get, edit, list, info.\n\n"
                + HELP
            )
    if args.command in ("read", "edit", "delete") or (
        args.command == "telegraph" and args.sub == "get"
    ):
        if len(rest) != 1:
            raise UsageError(f"{args.command} expects one slug or public URL.")
        args.slug = rest[0]
        if args.command == "telegraph":
            args.path = rest[0]
    elif args.command == "image":
        if len(rest) != 1:
            raise UsageError("image expects one image file.")
        args.image = rest[0]
    elif args.command == "qr":
        if len(rest) != 1:
            raise UsageError("qr expects one URL.")
        args.url = rest[0]
    elif rest:
        raise UsageError(f"Unexpected argument {rest[0]!r}.")
    return args


def _option(tokens: list[str], index: int) -> tuple[str, str, int]:
    token = tokens[index]
    if "=" in token:
        name, value = token.split("=", 1)
        return name, value, 1
    if index + 1 >= len(tokens):
        raise UsageError(f"{token} needs a value.")
    return token, tokens[index + 1], 2


def _assign(args: Args, name: str, value: str) -> None:
    mapping = {
        "--base-url": "base_url",
        "--timeout": "timeout",
        "--file": "file",
        "--title": "title",
        "--author": "author",
        "--content": "content",
        "--view-password": "view_password",
        "--view-password-file": "view_password_file",
        "--save-key": "save_key",
        "--edit-key": "edit_key",
        "--edit-key-file": "edit_key_file",
        "--text": "text",
        "--image": "image",
        "--output": "output",
        "--short-name": "short_name",
        "--author-name": "author_name",
        "--save-token": "save_token",
        "--token": "token",
        "--token-file": "token_file",
        "--path": "path",
    }
    if name not in mapping:
        raise UsageError(f"Unknown option {name}.")
    setattr(args, mapping[name], value)


def normalize_base_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise UsageError("Base URL is empty.")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in ("https", "http"):
        raise UsageError("Base URL must start with https:// or http://.")
    if parsed.username or parsed.password:
        raise UsageError("Base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise UsageError("Base URL must not contain a query or fragment.")
    if not parsed.netloc:
        raise UsageError("Base URL is missing a host.")
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def normalize_slug(value: str) -> str:
    raw = value.strip()
    if "://" in raw:
        parsed = urllib.parse.urlparse(raw)
        raw = parsed.path.rstrip("/")
        if raw.endswith(".md"):
            raw = raw[: -len(".md")]
        raw = raw.rsplit("/", 1)[-1]
    if not raw or raw in (".", "..") or "/" in raw or "\\" in raw:
        raise UsageError("Slug must be the short code or a public article URL.")
    if any(ch.isspace() or ch in "?#&=" for ch in raw):
        raise UsageError("Slug contains characters that are not part of a short code.")
    return raw


def public_article_url(base_url: str, slug: str) -> str:
    return f"{base_url}/{urllib.parse.quote(slug)}"


def split_markdown(text: str, title: str | None) -> tuple[str, str]:
    if title is not None:
        cleaned = title.strip()
        if not cleaned:
            raise UsageError("Title is empty.")
        if text.strip() == "":
            raise UsageError("Content is empty.")
        return cleaned, text
    lines = text.splitlines()
    index = 0
    while index < len(lines) and lines[index].strip() == "":
        index += 1
    if index < len(lines) and lines[index].startswith("# "):
        derived = lines[index][2:].strip()
        rest = lines[index + 1 :]
        if rest and rest[0].strip() == "":
            rest = rest[1:]
        body = "\n".join(rest)
        if body.endswith("\n") is False and text.endswith("\n"):
            body += "\n"
        if derived and body.strip():
            return derived, body
    raise UsageError(
        'Pass --title, or start the Markdown with a "# title" heading and a body.'
    )


def read_text_file(path: str) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise UsageError(f"File not found: {path}")
    try:
        return file_path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise UsageError(f"{path} is not valid UTF-8.") from exc


def load_secret_file(path: str, field: str) -> tuple[str, str | None]:
    """Return the secret and, if the file is group/world readable, its path."""
    file_path = Path(path)
    if not file_path.is_file():
        raise UsageError(f"File not found: {path}")
    mode = stat.S_IMODE(file_path.stat().st_mode)
    raw = file_path.read_text(encoding="utf-8")
    value = ""
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise UsageError(f"{path} is not valid JSON.") from exc
        if not isinstance(data, dict):
            raise UsageError(f"{path} must contain a JSON object.")
        candidate = data.get(field, "")
        if not isinstance(candidate, str):
            raise UsageError(f"{path} field {field} must be a string.")
        value = candidate
    else:
        lines = [line for line in raw.splitlines() if line.strip()]
        if len(lines) != 1:
            raise UsageError(f"{path} should be a single secret, or JSON with {field}.")
        value = lines[0].strip()
    if not value:
        raise UsageError(f"{path} does not contain {field}.")
    warning = path if mode & 0o077 else None
    return value, warning


def ensure_secret_destination(path: str) -> None:
    """Reject a save path before any article is created."""
    if "\n" in path or "\x00" in path:
        raise UsageError("Secret file path contains a newline or NUL.")
    destination = Path(path)
    if destination.exists() or destination.is_symlink():
        raise UsageError(f"{path} already exists. Choose a new path.")
    parent = destination.parent
    if parent and not parent.exists():
        raise UsageError(f"Directory does not exist: {parent}")


def write_private_file(path: str, payload: dict[str, str]) -> None:
    ensure_secret_destination(path)
    destination = Path(path)
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(destination, flags, 0o600)
    except FileExistsError as exc:
        raise UsageError(f"{path} already exists. Choose a new path.") from exc
    try:
        os.write(fd, body.encode("utf-8"))
        os.fchmod(fd, 0o600)
    except Exception:
        os.close(fd)
        destination.unlink(missing_ok=True)
        raise
    else:
        os.close(fd)
    info = destination.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        destination.unlink(missing_ok=True)
        raise ClientError("Refusing to leave a secret on a non-regular file.")
    if stat.S_IMODE(info.st_mode) & 0o077:
        destination.unlink(missing_ok=True)
        raise ClientError("Refusing to leave a secret file that other users can read.")


def warn_if_unignored(path: str, stderr) -> None:
    destination = Path(path).resolve()
    directory = destination.parent
    git_root = None
    cursor = directory
    while True:
        if (cursor / ".git").exists():
            git_root = cursor
            break
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    if git_root is None:
        return
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--", str(destination)],
            cwd=git_root,
            check=False,
            capture_output=True,
        )
    except OSError:
        return
    if result.returncode != 0:
        stderr.write(
            f"warning: {path} is inside a git checkout and is not ignored. Do not commit it.\n"
        )


def json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def redact_value(value):
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if str(key).lower() in SECRET_FIELDS:
                cleaned[key] = "REDACTED"
            else:
                cleaned[key] = redact_value(item)
        return cleaned
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value


_SECRET_JSON_RE = re.compile(
    r'("(?:edit_key|access_token|view_password|password|token|auth_url)"\s*:\s*")((?:[^"\\]|\\.)*)(")',
    re.IGNORECASE,
)
_SECRET_PAIR_RE = re.compile(
    r"(?i)\b(edit_key|access_token|view_password|password|token|auth_url)=([^\s&]+)"
)


def redact_text(text: str, secrets: list[str] | None = None) -> str:
    def replace_json(match: re.Match[str]) -> str:
        return match.group(1) + "REDACTED" + match.group(3)

    def replace_pair(match: re.Match[str]) -> str:
        return match.group(1) + "=REDACTED"

    cleaned = _SECRET_JSON_RE.sub(replace_json, text)
    cleaned = _SECRET_PAIR_RE.sub(replace_pair, cleaned)
    for secret in secrets or []:
        if secret:
            cleaned = cleaned.replace(secret, "REDACTED")
    return cleaned


def redact_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    bits = []
    for key, value in pairs:
        if key.lower() in SECRET_QUERY_KEYS:
            bits.append(urllib.parse.quote(key, safe="") + "=REDACTED")
        else:
            bits.append(urllib.parse.urlencode([(key, value)]))
    query = "&".join(bits)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def encode_multipart(parts: list[dict]) -> tuple[bytes, str]:
    boundary = "glanoteBoundary" + os.urandom(12).hex()
    chunks: list[bytes] = []
    for part in parts:
        data: bytes = part["data"]
        if boundary.encode("ascii") in data:
            raise ClientError("Could not build a multipart body. Try the upload again.")
        disposition = f'form-data; name="{part["name"]}"'
        filename = part.get("filename")
        if filename:
            disposition += f'; filename="{filename}"'
        chunks.append(f"--{boundary}\r\n".encode("ascii"))
        chunks.append(f"Content-Disposition: {disposition}\r\n".encode("utf-8"))
        content_type = part.get("content_type")
        if content_type:
            chunks.append(f"Content-Type: {content_type}\r\n".encode("ascii"))
        chunks.append(b"\r\n")
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    body = b"".join(chunks)
    return body, f"multipart/form-data; boundary={boundary}"


def form_bytes(fields: list[tuple[str, str]]) -> bytes:
    return urllib.parse.urlencode(fields).encode("utf-8")


class Request:
    def __init__(self, method: str, url: str, headers: dict[str, str], body: bytes | None):
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body

    def dry_text(self, secrets: list[str]) -> str:
        lines = [f"{self.method} {redact_url(self.url)}"]
        for key, value in self.headers.items():
            if key.lower() == "x-view-password":
                lines.append(f"{key}: REDACTED")
            else:
                lines.append(f"{key}: {value}")
        if self.body is not None:
            preview = self.body.decode("utf-8", errors="replace")
            lines.append(redact_text(preview, secrets))
        return "\n".join(lines) + "\n"


def build_image_part(path: str) -> dict:
    file_path = Path(path)
    if not file_path.is_file():
        raise UsageError(f"File not found: {path}")
    suffix = file_path.suffix.lower()
    if suffix in (".mp4", ".mov", ".webm", ".mkv", ".avi"):
        raise UsageError("Video files are not accepted. The limit covers JPG, PNG, WebP, and GIF.")
    if suffix not in IMAGE_TYPES:
        raise UsageError("Images must be JPG, PNG, WebP, or GIF.")
    size = file_path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise UsageError("Image is larger than the documented 5 MB limit.")
    if size == 0:
        raise UsageError("Image file is empty.")
    filename = file_path.name.replace('"', "")
    if any(ch in filename for ch in '"\r\n\\'):
        raise UsageError("Image file name cannot include quotes, slashes, or newlines.")
    return {
        "name": "image",
        "filename": filename,
        "content_type": IMAGE_TYPES[suffix],
        "data": file_path.read_bytes(),
    }


def telegraph_nodes(text: str | None, content: str | None) -> str:
    if text is not None and content is not None:
        raise UsageError("Pass either --text or --content.")
    if content is not None:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise UsageError("--content must be a JSON array of Telegraph nodes.") from exc
        if not isinstance(parsed, list):
            raise UsageError("--content must be a JSON array of Telegraph nodes.")
        nodes = parsed
    elif text is not None:
        if text == "":
            raise UsageError("Telegraph text is empty.")
        nodes = [{"tag": "p", "children": [text]}]
    else:
        raise UsageError("Pass --text or --content for the Telegraph page.")
    return json.dumps(nodes, ensure_ascii=False, separators=(",", ":"))


def resolve_timeout(raw: str | None, env: dict[str, str]) -> float:
    source = raw if raw is not None else env.get("GLANOTE_TIMEOUT")
    if source is None or source == "":
        return DEFAULT_TIMEOUT
    try:
        value = float(source)
    except ValueError as exc:
        raise UsageError("Timeout must be a number of seconds.") from exc
    if value <= 0 or value > 300:
        raise UsageError("Timeout must be greater than 0 and at most 300 seconds.")
    return value


def resolve_base(raw: str | None, env: dict[str, str]) -> str:
    source = raw if raw is not None else env.get("GLANOTE_BASE_URL", DEFAULT_BASE_URL)
    return normalize_base_url(source)


def read_stdin(stdin, label: str) -> str:
    isatty = getattr(stdin, "isatty", None)
    if callable(isatty) and isatty():
        raise UsageError(f"Pass --file or --content, or pipe {label} on stdin.")
    data = stdin.read()
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return data


def view_password_from(args: Args) -> str | None:
    if args.view_password and args.view_password_file:
        raise UsageError("Pass only one of --view-password and --view-password-file.")
    if args.view_password_file:
        value, warning = load_secret_file(args.view_password_file, "view_password")
        if warning:
            args.mode_warnings.append(warning)
        return value
    if args.view_password is not None:
        if args.view_password == "":
            raise UsageError("View password is empty.")
        return args.view_password
    return None


def management_key(args: Args, flag: str, file_flag: str, field: str) -> str:
    inline = getattr(args, flag)
    file_path = getattr(args, file_flag)
    option = "--" + flag.replace("_", "-")
    file_option = "--" + file_flag.replace("_", "-")
    if inline and file_path:
        raise UsageError(f"Pass only one of {option} and {file_option}.")
    if file_path:
        value, warning = load_secret_file(file_path, field)
        if warning:
            args.mode_warnings.append(warning)
        return value
    if inline:
        if inline.strip() == "":
            raise UsageError("Management key is empty.")
        return inline
    raise UsageError("This call needs an edit key or access token. Pass it explicitly.")


def require_yes(args: Args, action: str) -> None:
    if not args.yes:
        raise UsageError(f"{action} needs --yes in addition to the key.")


def article_body(title: str, content: str, author: str | None, view_password: str | None) -> dict:
    payload = {"title": title, "content": content}
    if author is not None:
        if author.strip() == "":
            raise UsageError("Author is empty.")
        payload["author"] = author
    if view_password is not None:
        payload["view_password"] = view_password
    # title, optional author, content, optional view password — documented fields only.
    ordered = {}
    ordered["title"] = payload["title"]
    if "author" in payload:
        ordered["author"] = payload["author"]
    ordered["content"] = payload["content"]
    if "view_password" in payload:
        ordered["view_password"] = payload["view_password"]
    return ordered


def perform(request: Request, timeout: float, opener=None, secrets: list[str] | None = None) -> tuple[int, str, bytes]:
    call = opener or urllib.request.urlopen
    req = urllib.request.Request(
        request.url,
        data=request.body,
        headers=request.headers,
        method=request.method,
    )
    try:
        with call(req, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            content_type = ""
            headers = getattr(response, "headers", None)
            if headers is not None:
                content_type = headers.get("content-type", "")
            return status, content_type, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        raise ClientError(
            f"HTTP {exc.code}\n" + redact_text(_decode(raw)[:2048], secrets)
        ) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if _is_timeout(reason):
            raise ClientError(f"Request timed out after {timeout:g} seconds.") from exc
        raise ClientError(f"Request failed: {reason}") from exc
    except TimeoutError as exc:
        raise ClientError(f"Request timed out after {timeout:g} seconds.") from exc


def _is_timeout(reason: object) -> bool:
    if isinstance(reason, TimeoutError):
        return True
    name = reason.__class__.__name__.lower()
    if "timeout" in name:
        return True
    return "timed out" in str(reason).lower()


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _too_large(raw: bytes) -> None:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ClientError("Response exceeded 2 MB and was not printed.")


def parse_json(raw: bytes) -> object:
    _too_large(raw)
    try:
        return json.loads(_decode(raw))
    except json.JSONDecodeError as exc:
        raise ClientError("Response was not valid JSON.") from exc


def scrubbed_public_url(url: object, secrets: list[str]) -> str:
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise ClientError("Response JSON did not include a public http(s) url.")
    for secret in secrets:
        if secret and secret in url:
            raise ClientError("Refusing to print a public URL that contains a management secret.")
    return url


def emit_key(
    *,
    kind: str,
    secret: str | None,
    url: str | None,
    show: bool,
    save_path: str | None,
    stderr,
) -> None:
    """Print the public URL on stdout. Keep the management secret off stdout."""
    if not secret:
        raise ClientError(f"Response did not include {kind}.")
    record: dict[str, str] = {kind: secret}
    if url:
        record["url"] = url
    if save_path:
        write_private_file(save_path, record)
        stderr.write(
            f"Wrote {kind} to {save_path} with mode 600. "
            "Do not commit that file or put the key in a public URL.\n"
        )
        warn_if_unignored(save_path, stderr)
    if show:
        flag = "--show-token" if kind == "access_token" else "--show-key"
        stderr.write(
            f"{kind}={secret}\n"
            f"Printed on stderr because {flag} was set. "
            "Terminal scrollback and CI logs may keep it.\n"
        )
    if not save_path and not show:
        if kind == "access_token":
            stderr.write(
                "The access_token was not printed or saved. createAccount returns it once; "
                "later calls need the same token. Pass --save-token or --show-token to keep it.\n"
            )
        else:
            stderr.write(
                "The edit_key was not printed or saved, and it cannot be recovered. "
                "Publishing again creates a different article. "
                "Pass --save-key or --show-key when you need to edit or delete.\n"
            )


def finish_article_publish(raw: bytes, args: Args, stdout, stderr, secrets: list[str]) -> str:
    payload = parse_json(raw)
    if not isinstance(payload, dict):
        raise ClientError("Publish response was not a JSON object.")
    key = payload.get("edit_key")
    secret = key if isinstance(key, str) and key else None
    if secret:
        secrets.append(secret)
    url_error = None
    url = ""
    try:
        url = scrubbed_public_url(payload.get("url"), secrets)
    except ClientError as exc:
        url_error = exc
    # Persist or reveal the key before printing the URL, so a later print error
    # cannot be the reason a requested key file was skipped.
    if secret or args.show_key or args.save_key:
        emit_key(
            kind="edit_key",
            secret=secret,
            url=url or None,
            show=args.show_key,
            save_path=args.save_key,
            stderr=stderr,
        )
    elif args.command == "publish":
        stderr.write(
            "Response JSON did not include edit_key. Nothing secret was printed.\n"
        )
    if url_error:
        redacted = redact_text(
            json.dumps(redact_value(payload), ensure_ascii=False)[:1000],
            secrets,
        )
        raise ClientError(f"{url_error}\n{redacted}")
    stdout.write(url + "\n")
    return url


def command_publish(args: Args, base: str, stdin) -> Request:
    if args.file and args.content is not None:
        raise UsageError("Pass only one of --file and --content.")
    if args.file:
        text = read_text_file(args.file)
    elif args.content is not None:
        text = args.content
    else:
        text = read_stdin(stdin, "Markdown")
    title, content = split_markdown(text, args.title)
    password = view_password_from(args)
    payload = article_body(title, content, args.author, password)
    return Request(
        "POST",
        f"{base}/api/articles",
        {
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": USER_AGENT,
        },
        json_bytes(payload),
    )


def command_read(args: Args, base: str) -> Request:
    slug = normalize_slug(args.slug or "")
    headers = {"user-agent": USER_AGENT, "accept": "*/*"}
    password = view_password_from(args)
    if args.markdown:
        if password:
            raise UsageError(
                "The documented password header is for GET /api/articles/SLUG, not the .md URL."
            )
        return Request("GET", f"{base}/{urllib.parse.quote(slug)}.md", headers, None)
    if password:
        headers["X-View-Password"] = password
    headers["accept"] = "application/json"
    return Request("GET", f"{base}/api/articles/{urllib.parse.quote(slug)}", headers, None)


def edit_payload(args: Args, stdin) -> dict:
    require_yes(args, "edit")
    key = management_key(args, "edit_key", "edit_key_file", "edit_key")
    if args.file and args.content is not None:
        raise UsageError("Pass only one of --file and --content.")
    if args.file:
        text = read_text_file(args.file)
    elif args.content is not None:
        text = args.content
    else:
        text = read_stdin(stdin, "Markdown")
    title, content = split_markdown(text, args.title)
    return {"edit_key": key, "title": title, "content": content}


def command_edit(args: Args, base: str, stdin) -> Request:
    slug = normalize_slug(args.slug or "")
    payload = edit_payload(args, stdin)
    return Request(
        "PUT",
        f"{base}/api/articles/{urllib.parse.quote(slug)}",
        {
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": USER_AGENT,
        },
        json_bytes(payload),
    )


def command_delete(args: Args, base: str) -> Request:
    require_yes(args, "delete")
    slug = normalize_slug(args.slug or "")
    key = management_key(args, "edit_key", "edit_key_file", "edit_key")
    return Request(
        "DELETE",
        f"{base}/api/articles/{urllib.parse.quote(slug)}",
        {
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": USER_AGENT,
        },
        json_bytes({"edit_key": key}),
    )


def command_image(args: Args, base: str) -> Request:
    part = build_image_part(args.image or "")
    body, content_type = encode_multipart([part])
    return Request(
        "POST",
        f"{base}/api/images",
        {
            "content-type": content_type,
            "accept": "*/*",
            "user-agent": USER_AGENT,
        },
        body,
    )


def command_new(args: Args, base: str) -> Request:
    has_text = args.text is not None
    has_file = args.file is not None
    has_title = args.title is not None
    has_image = args.image is not None
    url = f"{base}/api/new?format=json"
    headers = {"accept": "application/json", "user-agent": USER_AGENT}
    if has_text and not has_file and not has_title and not has_image:
        headers["content-type"] = "application/x-www-form-urlencoded"
        return Request("POST", url, headers, form_bytes([("text", args.text or "")]))
    if has_file and not has_text and not has_title and not has_image:
        data = read_text_file(args.file or "").encode("utf-8")
        filename = Path(args.file or "note.md").name.replace('"', "")
        if any(ch in filename for ch in '"\r\n\\'):
            raise UsageError("Markdown file name cannot include quotes, slashes, or newlines.")
        body, content_type = encode_multipart(
            [
                {
                    "name": "file",
                    "filename": filename,
                    "content_type": "text/markdown; charset=utf-8",
                    "data": data,
                }
            ]
        )
        headers["content-type"] = content_type
        return Request("POST", url, headers, body)
    if has_title and has_text and has_image and not has_file:
        image = build_image_part(args.image or "")
        parts = [
            {"name": "title", "data": (args.title or "").encode("utf-8")},
            {"name": "text", "data": (args.text or "").encode("utf-8")},
            image,
        ]
        body, content_type = encode_multipart(parts)
        headers["content-type"] = content_type
        return Request("POST", url, headers, body)
    raise UsageError(
        "new accepts three documented forms: --text TEXT; --file PATH; "
        "or --title TEXT --text TEXT --image FILE."
    )


def command_preview(args: Args, base: str, stdin) -> Request:
    if args.file and args.content is not None:
        raise UsageError("Pass only one of --file and --content.")
    if args.file:
        content = read_text_file(args.file)
    elif args.content is not None:
        content = args.content
    else:
        content = read_stdin(stdin, "Markdown")
    if content.strip() == "":
        raise UsageError("Preview content is empty.")
    return Request(
        "POST",
        f"{base}/api/preview",
        {
            "content-type": "application/json",
            "accept": "*/*",
            "user-agent": USER_AGENT,
        },
        json_bytes({"content": content}),
    )


def command_qr(args: Args, base: str) -> Request:
    target = args.url or ""
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise UsageError("qr expects an http(s) URL.")
    query = urllib.parse.urlencode({"u": target})
    return Request(
        "GET",
        f"{base}/api/qr?{query}",
        {"accept": "image/svg+xml, */*", "user-agent": USER_AGENT},
        None,
    )


def command_telegraph(args: Args, base: str) -> Request:
    root = f"{base}/telegraph"
    headers = {"accept": "application/json", "user-agent": USER_AGENT}
    if args.sub == "account":
        if not args.short_name or args.short_name.strip() == "":
            raise UsageError("telegraph account needs --short-name.")
        pairs = [("short_name", args.short_name)]
        if args.author_name is not None:
            pairs.append(("author_name", args.author_name))
        return Request("GET", f"{root}/createAccount?{urllib.parse.urlencode(pairs)}", headers, None)
    if args.sub == "get":
        slug = normalize_slug(args.path or args.slug or "")
        query = urllib.parse.urlencode(
            [("path", slug), ("return_content", "true" if args.return_content else "false")]
        )
        return Request("GET", f"{root}/getPage?{query}", headers, None)
    token = ""
    if args.sub in ("create", "edit", "list", "info"):
        token = management_key(args, "token", "token_file", "access_token")
    if args.sub == "list":
        query = urllib.parse.urlencode([("access_token", token)])
        return Request("GET", f"{root}/getPageList?{query}", headers, None)
    if args.sub == "info":
        query = urllib.parse.urlencode([("access_token", token)])
        return Request("GET", f"{root}/getAccountInfo?{query}", headers, None)
    nodes = telegraph_nodes(args.text, args.content)
    if not args.title or args.title.strip() == "":
        raise UsageError("Telegraph page needs --title.")
    if args.sub == "create":
        fields = [
            ("access_token", token),
            ("title", args.title),
            ("content", nodes),
        ]
        if args.return_content:
            fields.append(("return_content", "true"))
        headers["content-type"] = "application/x-www-form-urlencoded"
        return Request("POST", f"{root}/createPage", headers, form_bytes(fields))
    if args.sub == "edit":
        require_yes(args, "telegraph edit")
        slug = normalize_slug(args.path or "")
        fields = [
            ("access_token", token),
            ("path", slug),
            ("title", args.title),
            ("content", nodes),
        ]
        headers["content-type"] = "application/x-www-form-urlencoded"
        return Request("POST", f"{root}/editPage", headers, form_bytes(fields))
    raise UsageError("Unknown telegraph method.")


def build_request(args: Args, base: str, stdin) -> Request:
    if args.command == "publish":
        return command_publish(args, base, stdin)
    if args.command == "read":
        return command_read(args, base)
    if args.command == "edit":
        return command_edit(args, base, stdin)
    if args.command == "delete":
        return command_delete(args, base)
    if args.command == "image":
        return command_image(args, base)
    if args.command == "new":
        return command_new(args, base)
    if args.command == "preview":
        return command_preview(args, base, stdin)
    if args.command == "qr":
        return command_qr(args, base)
    if args.command == "telegraph":
        return command_telegraph(args, base)
    raise UsageError(f"Unknown command {args.command}.")


def secrets_in_request(request: Request) -> list[str]:
    found: list[str] = []
    header = request.headers.get("X-View-Password")
    if header:
        found.append(header)
    if not request.body:
        query = urllib.parse.urlsplit(request.url).query
        for key, value in urllib.parse.parse_qsl(query):
            if key.lower() in SECRET_QUERY_KEYS and value:
                found.append(value)
        return found
    text = request.body.decode("utf-8", errors="replace")
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            data = json.loads(text)
            if isinstance(data, dict):
                for key, value in data.items():
                    if str(key).lower() in SECRET_FIELDS and isinstance(value, str):
                        found.append(value)
        elif request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
            for key, value in urllib.parse.parse_qsl(text):
                if key.lower() in SECRET_QUERY_KEYS and value:
                    found.append(value)
    except json.JSONDecodeError:
        pass
    return found


def emit_success(args: Args, request: Request, raw: bytes, content_type: str, base: str, stdout, stderr) -> None:
    secrets = secrets_in_request(request)
    if args.command in ("publish", "new"):
        finish_article_publish(raw, args, stdout, stderr, secrets)
        return
    if args.command == "delete":
        slug = normalize_slug(args.slug or "")
        stdout.write(f"deleted {public_article_url(base, slug)}\n")
        return
    if args.command == "edit":
        slug = normalize_slug(args.slug or "")
        stdout.write(public_article_url(base, slug) + "\n")
        return
    if args.command == "qr":
        _too_large(raw)
        if args.output:
            destination = Path(args.output)
            destination.write_bytes(raw)
            stderr.write(f"Wrote {args.output}\n")
        elif hasattr(stdout, "buffer"):
            stdout.buffer.write(raw)
        else:
            stdout.write(_decode(raw))
        return
    if args.command == "image":
        _too_large(raw)
        stderr.write(
            "Image upload response is below. The API page says to paste the returned "
            "Markdown into an article. Images are protected against hotlinking from other sites.\n"
        )
        _write_opaque(raw, content_type, stdout)
        return
    if args.command == "preview":
        _too_large(raw)
        stderr.write("Preview only. Nothing was published.\n")
        _write_opaque(raw, content_type, stdout)
        return
    if args.command == "read":
        _too_large(raw)
        if args.markdown:
            stdout.write(_decode(raw))
            if raw and not raw.endswith(b"\n"):
                stdout.write("\n")
            return
        payload = parse_json(raw)
        stdout.write(json.dumps(redact_value(payload), ensure_ascii=False, indent=2) + "\n")
        return
    if args.command == "telegraph":
        payload = parse_json(raw)
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            message = ""
            if isinstance(payload, dict) and isinstance(payload.get("error"), str):
                message = payload["error"]
            raise ClientError(
                "Telegraph response did not include ok: true."
                + (f" error={message}" if message else "")
            )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ClientError("Telegraph response did not include a result object.")
        if args.sub == "account":
            token = result.get("access_token")
            secret = token if isinstance(token, str) and token else None
            redacted = redact_value(result)
            short_name = redacted.get("short_name")
            if isinstance(short_name, str):
                stdout.write(short_name + "\n")
            else:
                stdout.write(json.dumps(redacted, ensure_ascii=False, indent=2) + "\n")
            emit_key(
                kind="access_token",
                secret=secret,
                url=None,
                show=args.show_token,
                save_path=args.save_token,
                stderr=stderr,
            )
            return
        if args.sub == "create":
            url = scrubbed_public_url(result.get("url"), secrets)
            stdout.write(url + "\n")
            return
        stdout.write(json.dumps(redact_value(result), ensure_ascii=False, indent=2) + "\n")
        return
    _write_opaque(raw, content_type, stdout)


def _write_opaque(raw: bytes, content_type: str, stdout) -> None:
    text = _decode(raw)
    if "json" in content_type.lower() or text.lstrip().startswith(("{", "[")):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            stdout.write(redact_text(text))
            if not text.endswith("\n"):
                stdout.write("\n")
            return
        stdout.write(json.dumps(redact_value(payload), ensure_ascii=False, indent=2) + "\n")
        return
    stdout.write(text)
    if text and not text.endswith("\n"):
        stdout.write("\n")


def main(argv: list[str] | None = None, *, stdin=None, stdout=None, stderr=None, env=None, opener=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    env = os.environ if env is None else env
    try:
        args = parse_args(argv)
        base = resolve_base(args.base_url, env)
        timeout = resolve_timeout(args.timeout, env)
        request = build_request(args, base, stdin)
        if args.save_key:
            ensure_secret_destination(args.save_key)
        if args.save_token:
            ensure_secret_destination(args.save_token)
        for warning in args.mode_warnings:
            stderr.write(
                f"warning: {warning} is readable by other users. chmod 600 it.\n"
            )
        request_secrets = secrets_in_request(request)
        if args.dry_run:
            stderr.write(request.dry_text(request_secrets))
            return 0
        _status, content_type, raw = perform(request, timeout, opener, request_secrets)
        emit_success(args, request, raw, content_type, base, stdout, stderr)
        return 0
    except UsageError as exc:
        stderr.write(str(exc).rstrip() + "\n")
        text = str(exc)
        return 0 if text == HELP or text.startswith("glanote ") else 2
    except ClientError as exc:
        stderr.write(str(exc).rstrip() + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
