#!/usr/bin/env bash
# Command-line client for the public Glanote article API.
# HTTP is curl. python3 encodes and decodes JSON so Unicode stays intact.
# Endpoints match https://glanote.com/en/api
# This file is an example client. It is not the Glanote server.

set -euo pipefail

VERSION="0.1.0"
DEFAULT_BASE="https://glanote.com"
DEFAULT_TIMEOUT="30"
USER_AGENT="glanote-api-examples/${VERSION}"
MAX_IMAGE_BYTES=$((5 * 1024 * 1024))

HELP=$(cat <<'EOF'
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

Requires bash, curl, and python3. Publish reads stdin when --file and --content
are both omitted and stdin is not a terminal. A leading Markdown heading
("# title") becomes the title unless --title is set. Stdout is the public URL
only. The edit key is left out unless you pass --show-key (stderr) or
--save-key (a new file, mode 0600). Glanote stores only a hash of the key and
cannot recover it. Edit and delete always require that key and --yes.

The Telegraph commands call the six methods documented for
https://glanote.com/telegraph : createAccount, createPage, editPage, getPage,
getPageList, getAccountInfo. For getPage, PATH is the short code.
EOF
)

TMPS=()
cleanup() {
  local file
  for file in "${TMPS[@]+"${TMPS[@]}"}"; do
    if [[ -f "$file" ]]; then
      : >"$file" 2>/dev/null || true
      rm -f "$file"
    fi
  done
}
trap cleanup EXIT

tmpdir() {
  local file
  file=$(mktemp)
  chmod 600 "$file"
  TMPS+=("$file")
  printf '%s\n' "$file"
}

die() {
  local code=$1
  shift
  printf '%s\n' "$*" >&2
  exit "$code"
}

need_tools() {
  command -v curl >/dev/null 2>&1 || die 1 "curl is required."
  command -v python3 >/dev/null 2>&1 || die 1 "python3 is required to encode JSON. Install Python 3, or use python/glanote.py."
}

gl_py() {
  python3 - "$@" <<'PY'
import json, os, stat, sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

SECRET_FIELDS = {"edit_key", "access_token", "view_password", "password", "token", "auth_url"}

def fail(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    raise SystemExit(code)

def redact_text(text):
    import re
    text = re.sub(
        r'("(?:edit_key|access_token|view_password|password|token|auth_url)"\s*:\s*")((?:[^"\\]|\\.)*)(")',
        r"\1REDACTED\3",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(?i)\b(edit_key|access_token|view_password|password|token|auth_url)=([^\s&]+)",
        r"\1=REDACTED",
        text,
    )
    return text

def read_secret(path, field):
    file_path = Path(path)
    if not file_path.is_file():
        fail(f"File not found: {path}")
    mode = stat.S_IMODE(file_path.stat().st_mode)
    raw = file_path.read_text(encoding="utf-8")
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            fail(f"{path} is not valid JSON.")
        if not isinstance(data, dict):
            fail(f"{path} must contain a JSON object.")
        value = data.get(field, "")
        if not isinstance(value, str):
            fail(f"{path} field {field} must be a string.")
    else:
        lines = [line for line in raw.splitlines() if line.strip()]
        if len(lines) != 1:
            fail(f"{path} should be a single secret, or JSON with {field}.")
        value = lines[0].strip()
    if not value:
        fail(f"{path} does not contain {field}.")
    if mode & 0o077:
        sys.stderr.write(f"warning: {path} is readable by other users. chmod 600 it.\n")
    return value

def write_secret_file(path, payload):
    if "\n" in path or "\x00" in path:
        fail("Secret file path contains a newline or NUL.")
    dest = Path(path)
    if dest.exists() or dest.is_symlink():
        fail(f"{path} already exists. Choose a new path.")
    if not dest.parent.exists():
        fail(f"Directory does not exist: {dest.parent}")
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(dest, flags, 0o600)
    try:
        os.write(fd, body.encode("utf-8"))
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    info = dest.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        dest.unlink(missing_ok=True)
        fail("Refusing to leave a secret file that other users can read.", 1)

def split_markdown(text, title):
    if title is not None:
        cleaned = title.strip()
        if not cleaned:
            fail("Title is empty.")
        if text.strip() == "":
            fail("Content is empty.")
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
        if text.endswith("\n") and not body.endswith("\n"):
            body += "\n"
        if derived and body.strip():
            return derived, body
    fail('Pass --title, or start the Markdown with a "# title" heading and a body.')

def normalize_base(value):
    raw = value.strip()
    if not raw:
        fail("Base URL is empty.")
    parsed = urlparse(raw)
    if parsed.scheme not in ("https", "http"):
        fail("Base URL must start with https:// or http://.")
    if parsed.username or parsed.password:
        fail("Base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        fail("Base URL must not contain a query or fragment.")
    if not parsed.netloc:
        fail("Base URL is missing a host.")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))

def normalize_slug(value):
    raw = value.strip()
    if "://" in raw:
        parsed = urlparse(raw)
        raw = parsed.path.rstrip("/")
        if raw.endswith(".md"):
            raw = raw[: -len(".md")]
        raw = raw.rsplit("/", 1)[-1]
    if not raw or raw in (".", "..") or "/" in raw or "\\" in raw:
        fail("Slug must be the short code or a public article URL.")
    if any(ch.isspace() or ch in "?#&=" for ch in raw):
        fail("Slug contains characters that are not part of a short code.")
    return raw

def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        fail("Response was not valid JSON.", 1)

def redact_obj(value):
    if isinstance(value, dict):
        return {key: ("REDACTED" if str(key).lower() in SECRET_FIELDS else redact_obj(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_obj(item) for item in value]
    return value

cmd = sys.argv[1]
rest = sys.argv[2:]

if cmd == "normalize-base":
    sys.stdout.write(normalize_base(rest[0]))
elif cmd == "normalize-slug":
    sys.stdout.write(normalize_slug(rest[0]))
elif cmd == "public-url":
    base = normalize_base(rest[0])
    slug = normalize_slug(rest[1])
    sys.stdout.write(f"{base}/{quote(slug)}")
elif cmd == "split-markdown":
    content = Path(rest[0]).read_text(encoding="utf-8-sig")
    title = None if rest[1] == "-" else Path(rest[1]).read_text(encoding="utf-8")
    derived, body = split_markdown(content, title)
    Path(rest[2]).write_text(derived, encoding="utf-8")
    Path(rest[3]).write_text(body, encoding="utf-8")
elif cmd == "article-json":
    title = Path(rest[0]).read_text(encoding="utf-8")
    content = Path(rest[1]).read_text(encoding="utf-8")
    payload = {"title": title, "content": content}
    if rest[2] != "-":
        author = Path(rest[2]).read_text(encoding="utf-8")
        if author.strip() == "":
            fail("Author is empty.")
        payload = {"title": title, "author": author, "content": content}
    if rest[3] != "-":
        payload["view_password"] = Path(rest[3]).read_text(encoding="utf-8")
    Path(rest[4]).write_bytes(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
elif cmd == "edit-json":
    key = Path(rest[0]).read_text(encoding="utf-8")
    title = Path(rest[1]).read_text(encoding="utf-8")
    content = Path(rest[2]).read_text(encoding="utf-8")
    payload = {"edit_key": key, "title": title, "content": content}
    Path(rest[3]).write_bytes(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
elif cmd == "delete-json":
    key = Path(rest[0]).read_text(encoding="utf-8")
    Path(rest[1]).write_bytes(json.dumps({"edit_key": key}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
elif cmd == "load-secret":
    value = read_secret(rest[0], rest[1])
    dest = Path(rest[2])
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(dest, flags, 0o600)
    try:
        os.write(fd, value.encode("utf-8"))
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
elif cmd == "nodes":
    if rest[0] == "text":
        text = Path(rest[1]).read_text(encoding="utf-8")
        if text == "":
            fail("Telegraph text is empty.")
        nodes = [{"tag": "p", "children": [text]}]
    else:
        try:
            nodes = json.loads(Path(rest[1]).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            fail("--content must be a JSON array of Telegraph nodes.")
        if not isinstance(nodes, list):
            fail("--content must be a JSON array of Telegraph nodes.")
    Path(rest[2]).write_text(json.dumps(nodes, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
elif cmd == "redact-file":
    text = Path(rest[0]).read_text(encoding="utf-8", errors="replace")
    sys.stdout.write(redact_text(text[:2048]))
elif cmd == "extract-article":
    data = load_json(rest[0])
    if not isinstance(data, dict):
        fail("Publish response was not a JSON object.", 1)
    key = data.get("edit_key")
    secret = key if isinstance(key, str) and key else ""
    if secret:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(rest[2], flags, 0o600)
        try:
            os.write(fd, secret.encode("utf-8"))
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
    url = data.get("url")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")) or (secret and secret in url):
        redacted = redact_text(json.dumps(redact_obj(data), ensure_ascii=False)[:1000])
        if secret and isinstance(url, str) and secret in url:
            fail("Refusing to print a public URL that contains a management secret.\n" + redacted, 1)
        fail("Response JSON did not include a public http(s) url.\n" + redacted, 1)
    Path(rest[1]).write_text(url, encoding="utf-8")
elif cmd == "save-record":
    payload = {}
    url = Path(rest[2]).read_text(encoding="utf-8") if rest[2] != "-" else ""
    secret = Path(rest[3]).read_text(encoding="utf-8")
    if not secret:
        fail(f"Response did not include {rest[1]}.", 1)
    if url:
        payload["url"] = url
    payload[rest[1]] = secret
    # Keep url first when present, matching the other clients.
    if url:
        payload = {"url": url, rest[1]: secret}
    write_secret_file(rest[0], payload)
elif cmd == "warn-git":
    dest = Path(rest[0]).resolve()
    cursor = dest.parent
    git_root = None
    while True:
        if (cursor / ".git").exists():
            git_root = cursor
            break
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    if git_root is None:
        raise SystemExit(0)
    import subprocess
    result = subprocess.run(["git", "check-ignore", "-q", "--", str(dest)], cwd=git_root)
    if result.returncode != 0:
        sys.stderr.write(f"warning: {rest[0]} is inside a git checkout and is not ignored. Do not commit it.\n")
elif cmd == "extract-account":
    data = load_json(rest[0])
    if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("result"), dict):
        message = ""
        if isinstance(data, dict) and isinstance(data.get("error"), str):
            message = data["error"]
        fail("Telegraph response did not include ok: true." + (f" error={message}" if message else ""), 1)
    result = data["result"]
    token = result.get("access_token")
    if isinstance(token, str) and token:
        Path(rest[1]).write_text(token, encoding="utf-8")
        os.chmod(rest[1], 0o600)
    short_name = result.get("short_name")
    if isinstance(short_name, str):
        sys.stdout.write(short_name)
    else:
        sys.stdout.write(json.dumps(redact_obj(result), ensure_ascii=False, indent=2))
elif cmd == "extract-page-url":
    data = load_json(rest[0])
    if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("result"), dict):
        message = ""
        if isinstance(data, dict) and isinstance(data.get("error"), str):
            message = data["error"]
        fail("Telegraph response did not include ok: true." + (f" error={message}" if message else ""), 1)
    url = data["result"].get("url")
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        fail("Response JSON did not include a public http(s) url.", 1)
    Path(rest[1]).write_text(url, encoding="utf-8")
elif cmd == "print-result":
    data = load_json(rest[0])
    if not isinstance(data, dict) or data.get("ok") is not True or not isinstance(data.get("result"), dict):
        message = ""
        if isinstance(data, dict) and isinstance(data.get("error"), str):
            message = data["error"]
        fail("Telegraph response did not include ok: true." + (f" error={message}" if message else ""), 1)
    sys.stdout.write(json.dumps(redact_obj(data["result"]), ensure_ascii=False, indent=2) + "\n")
elif cmd == "opaque":
    raw = Path(rest[0]).read_bytes()
    text = raw.decode("utf-8", errors="replace")
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            sys.stdout.write(redact_text(text))
        else:
            sys.stdout.write(json.dumps(redact_obj(parsed), ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(text if text.endswith("\n") or text == "" else text + "\n")
else:
    fail(f"Internal helper {cmd} is not implemented.", 1)
PY
}

run_py() {
  set +e
  gl_py "$@"
  local status=$?
  set -e
  return "$status"
}

must_py() {
  set +e
  gl_py "$@"
  local status=$?
  set -e
  if [[ "$status" -ne 0 ]]; then
    exit "$status"
  fi
}

# --- parse -----------------------------------------------------------------

BASE_URL="${GLANOTE_BASE_URL:-$DEFAULT_BASE}"
TIMEOUT="${GLANOTE_TIMEOUT:-$DEFAULT_TIMEOUT}"
DRY=0
COMMAND=""
SUB=""
FILE=""
TITLE=""
AUTHOR=""
CONTENT=""
VIEW_PASSWORD=""
VIEW_PASSWORD_FILE=""
SHOW_KEY=0
SAVE_KEY=""
SLUG=""
MARKDOWN=0
EDIT_KEY=""
EDIT_KEY_FILE=""
YES=0
IMAGE=""
TEXT=""
OUTPUT=""
QR_URL=""
SHORT_NAME=""
AUTHOR_NAME=""
SHOW_TOKEN=0
SAVE_TOKEN=""
TOKEN=""
TOKEN_FILE=""
PAGE_PATH=""
RETURN_CONTENT=0
POSITIONAL=()

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "help" ]]; then
  printf '%s\n' "$HELP" >&2
  exit 0
fi
if [[ "${1:-}" == "--version" || "${1:-}" == "-V" || "${1:-}" == "version" ]]; then
  printf 'glanote %s\n' "$VERSION" >&2
  exit 0
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --)
      shift
      POSITIONAL+=("$@")
      break
      ;;
    -h|--help)
      printf '%s\n' "$HELP" >&2
      exit 0
      ;;
    --version)
      printf 'glanote %s\n' "$VERSION" >&2
      exit 0
      ;;
    --dry-run) DRY=1; shift ;;
    --show-key) SHOW_KEY=1; shift ;;
    --show-token) SHOW_TOKEN=1; shift ;;
    --yes) YES=1; shift ;;
    --markdown) MARKDOWN=1; shift ;;
    --return-content) RETURN_CONTENT=1; shift ;;
    --base-url|--timeout|--file|--title|--author|--content|--view-password|--view-password-file|--save-key|--edit-key|--edit-key-file|--text|--image|--output|--short-name|--author-name|--save-token|--token|--token-file|--path|--base-url=*|--timeout=*|--file=*|--title=*|--author=*|--content=*|--view-password=*|--view-password-file=*|--save-key=*|--edit-key=*|--edit-key-file=*|--text=*|--image=*|--output=*|--short-name=*|--author-name=*|--save-token=*|--token=*|--token-file=*|--path=*)
      opt=${1%%=*}
      if [[ "$1" == *=* ]]; then
        val=${1#*=}
        shift
      else
        if [[ $# -lt 2 ]]; then
          die 2 "$opt needs a value."
        fi
        val=$2
        shift 2
      fi
      case "$opt" in
        --base-url) BASE_URL=$val ;;
        --timeout) TIMEOUT=$val ;;
        --file) FILE=$val ;;
        --title) TITLE=$val ;;
        --author) AUTHOR=$val ;;
        --content) CONTENT=$val ;;
        --view-password) VIEW_PASSWORD=$val ;;
        --view-password-file) VIEW_PASSWORD_FILE=$val ;;
        --save-key) SAVE_KEY=$val ;;
        --edit-key) EDIT_KEY=$val ;;
        --edit-key-file) EDIT_KEY_FILE=$val ;;
        --text) TEXT=$val ;;
        --image) IMAGE=$val ;;
        --output) OUTPUT=$val ;;
        --short-name) SHORT_NAME=$val ;;
        --author-name) AUTHOR_NAME=$val ;;
        --save-token) SAVE_TOKEN=$val ;;
        --token) TOKEN=$val ;;
        --token-file) TOKEN_FILE=$val ;;
        --path) PAGE_PATH=$val ;;
      esac
      ;;
    --*=*)
      die 2 "Unknown option ${1%%=*}."
      ;;
    --*)
      die 2 "Unknown option $1."
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done

if [[ ${#POSITIONAL[@]} -eq 0 ]]; then
  die 2 "Missing command."
fi
COMMAND=${POSITIONAL[0]}
rest=("${POSITIONAL[@]:1}")
case "$COMMAND" in
  publish|read|edit|delete|image|new|preview|qr|telegraph) ;;
  *) die 2 "Unknown command ${COMMAND}." ;;
esac
if [[ "$COMMAND" == "telegraph" ]]; then
  if [[ ${#rest[@]} -eq 0 ]]; then
    die 2 "Missing telegraph method."
  fi
  SUB=${rest[0]}
  rest=("${rest[@]:1}")
  case "$SUB" in
    account|create|get|edit|list|info) ;;
    *) die 2 "Unknown telegraph method ${SUB}." ;;
  esac
fi
if [[ "$COMMAND" == "read" || "$COMMAND" == "edit" || "$COMMAND" == "delete" || ( "$COMMAND" == "telegraph" && "$SUB" == "get" ) ]]; then
  if [[ ${#rest[@]} -ne 1 ]]; then
    die 2 "$COMMAND expects one slug or public URL."
  fi
  SLUG=${rest[0]}
  if [[ "$COMMAND" == "telegraph" ]]; then
    PAGE_PATH=$SLUG
  fi
elif [[ "$COMMAND" == "image" ]]; then
  if [[ ${#rest[@]} -ne 1 ]]; then
    die 2 "image expects one image file."
  fi
  IMAGE=${rest[0]}
elif [[ "$COMMAND" == "qr" ]]; then
  if [[ ${#rest[@]} -ne 1 ]]; then
    die 2 "qr expects one URL."
  fi
  QR_URL=${rest[0]}
elif [[ ${#rest[@]} -ne 0 ]]; then
  die 2 "Unexpected argument ${rest[0]}."
fi

need_tools
BASE_URL=$(must_py normalize-base "$BASE_URL")

if ! awk -v t="$TIMEOUT" 'BEGIN { if (t ~ /^[0-9]+([.][0-9]+)?$/ && t+0 > 0 && t+0 <= 300) exit 0; exit 1 }'; then
  die 2 "Timeout must be a number of seconds, greater than 0 and at most 300."
fi

preflight_save() {
  local dest=$1
  if [[ "$dest" == *$'\n'* ]]; then
    die 2 "Secret file path contains a newline or NUL."
  fi
  if [[ -e "$dest" ]]; then
    die 2 "$dest already exists. Choose a new path."
  fi
  local parent
  parent=$(dirname "$dest")
  if [[ ! -d "$parent" ]]; then
    die 2 "Directory does not exist: $parent"
  fi
}

if [[ -n "$SAVE_KEY" ]]; then
  preflight_save "$SAVE_KEY"
fi
if [[ -n "$SAVE_TOKEN" ]]; then
  preflight_save "$SAVE_TOKEN"
fi

write_text() {
  local dest=$1
  local value=$2
  printf '%s' "$value" >"$dest"
}

stage_secret_arg() {
  local value=$1
  local dest
  dest=$(tmpdir)
  printf '%s' "$value" >"$dest"
  chmod 600 "$dest"
  printf '%s\n' "$dest"
}

load_user_secret() {
  local inline=$1
  local file=$2
  local field=$3
  local which=$4
  if [[ -n "$inline" && -n "$file" ]]; then
    die 2 "Pass only one of --${which} and --${which}-file."
  fi
  local dest
  dest=$(tmpdir)
  if [[ -n "$file" ]]; then
    must_py load-secret "$file" "$field" "$dest"
  elif [[ -n "$inline" ]]; then
    if [[ -z "${inline// /}" ]]; then
      die 2 "Management key is empty."
    fi
    printf '%s' "$inline" >"$dest"
    chmod 600 "$dest"
  else
    die 2 "This call needs an edit key or access token. Pass it explicitly."
  fi
  printf '%s\n' "$dest"
}

read_content() {
  local dest
  dest=$(tmpdir)
  if [[ -n "$FILE" && -n "$CONTENT" ]]; then
    die 2 "Pass only one of --file and --content."
  fi
  if [[ -n "$FILE" ]]; then
    if [[ ! -f "$FILE" ]]; then
      die 2 "File not found: $FILE"
    fi
    cp "$FILE" "$dest"
  elif [[ -n "$CONTENT" ]]; then
    printf '%s' "$CONTENT" >"$dest"
  else
    if [[ -t 0 ]]; then
      die 2 "Pass --file or --content, or pipe Markdown on stdin."
    fi
    cat >"$dest"
  fi
  printf '%s\n' "$dest"
}

derive_title_body() {
  local content_file=$1
  local title_file body_file marker
  title_file=$(tmpdir)
  body_file=$(tmpdir)
  marker="-"
  if [[ -n "$TITLE" ]]; then
    marker=$(tmpdir)
    printf '%s' "$TITLE" >"$marker"
  fi
  must_py split-markdown "$content_file" "$marker" "$title_file" "$body_file"
  printf '%s\n%s\n' "$title_file" "$body_file"
}

check_image() {
  local file=$1
  if [[ ! -f "$file" ]]; then
    die 2 "File not found: $file"
  fi
  local base ext
  base=$(basename "$file")
  ext=${base##*.}
  ext=$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')
  case "$ext" in
    mp4|mov|webm|mkv|avi)
      die 2 "Video files are not accepted. The limit covers JPG, PNG, WebP, and GIF."
      ;;
    jpg|jpeg|png|webp|gif) ;;
    *) die 2 "Images must be JPG, PNG, WebP, or GIF." ;;
  esac
  if [[ "$base" == *'"'* || "$base" == *$'\n'* || "$base" == *'\'* || "$base" == *';'* || "$base" == *','* ]]; then
    die 2 "Image file name cannot include quotes, slashes, or newlines."
  fi
  local bytes
  bytes=$(wc -c <"$file")
  bytes=${bytes//[[:space:]]/}
  if [[ "$bytes" -eq 0 ]]; then
    die 2 "Image file is empty."
  fi
  if [[ "$bytes" -gt "$MAX_IMAGE_BYTES" ]]; then
    die 2 "Image is larger than the documented 5 MB limit."
  fi
  case "$ext" in
    jpg|jpeg) printf 'image/jpeg\n' ;;
    png) printf 'image/png\n' ;;
    webp) printf 'image/webp\n' ;;
    gif) printf 'image/gif\n' ;;
  esac
}

curl_send() {
  local method=$1
  local url=$2
  shift 2
  local resp code status
  resp=$(tmpdir)
  set +e
  code=$(curl -sS --http1.1 --proto '=http,https' --max-redirs 0 --max-time "$TIMEOUT" \
    -A "$USER_AGENT" -H 'Expect:' -o "$resp" -w '%{http_code}' -X "$method" "$url" "$@")
  status=$?
  set -e
  if [[ "$status" -ne 0 ]]; then
    if [[ "$status" -eq 28 ]]; then
      die 1 "Request timed out after ${TIMEOUT} seconds."
    fi
    if [[ "$status" -eq 47 ]]; then
      die 1 "HTTP redirect is not followed."
    fi
    die 1 "Request failed."
  fi
  if [[ "$code" -lt 200 || "$code" -ge 300 ]]; then
    printf 'HTTP %s\n' "$code" >&2
    gl_py redact-file "$resp" >&2 || true
    printf '\n' >&2
    exit 1
  fi
  printf '%s\n' "$resp"
}

dry_print() {
  local method=$1
  local url=$2
  shift 2
  python3 - "$method" "$url" "$@" <<'PY'
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit, unquote_plus
method, url = sys.argv[1], sys.argv[2]
parts = urlsplit(url)
bits = []
for key, value in parse_qsl(parts.query, keep_blank_values=True):
    if key.lower() in {"access_token", "edit_key", "view_password", "password", "token"}:
        bits.append(f"{key}=REDACTED")
    else:
        bits.append(f"{key}={value}")
query = "&".join(bits)
safe = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
sys.stderr.write(f"{method} {safe}\n")
args = sys.argv[3:]
index = 0
while index < len(args):
    item = args[index]
    if item == "--header":
        header = args[index + 1]
        name, _, value = header.partition(":")
        if name.lower().strip() == "x-view-password":
            sys.stderr.write(f"{name}: REDACTED\n")
        else:
            sys.stderr.write(header + "\n")
        index += 2
        continue
    if item == "--body-file":
        text = Path(args[index + 1]).read_text(encoding="utf-8", errors="replace")
        import re
        text = re.sub(r'("(?:edit_key|access_token|view_password|password|token|auth_url)"\s*:\s*")((?:[^"\\]|\\.)*)(")', r"\1REDACTED\3", text, flags=re.I)
        sys.stderr.write(text + "\n")
        index += 2
        continue
    if item == "--form-file":
        name = args[index + 1]
        value = Path(args[index + 2]).read_text(encoding="utf-8", errors="replace")
        if name.lower() in {"access_token", "edit_key", "view_password", "password", "token"}:
            value = "REDACTED"
        sys.stderr.write(f"{name}={value}\n")
        index += 3
        continue
    index += 1
PY
}

finish_article() {
  local resp=$1
  local url_file key_file
  url_file=$(tmpdir)
  key_file=$(tmpdir)
  set +e
  gl_py extract-article "$resp" "$url_file" "$key_file"
  local status=$?
  set -e
  local url=""
  if [[ -s "$url_file" ]]; then
    url=$(cat "$url_file")
  fi
  if [[ -s "$key_file" ]]; then
    if [[ -n "$SAVE_KEY" ]]; then
      local url_arg="-"
      if [[ -n "$url" ]]; then
        url_arg=$url_file
      fi
      must_py save-record "$SAVE_KEY" "edit_key" "$url_arg" "$key_file"
      printf 'Wrote edit_key to %s with mode 600. Do not commit that file or put the key in a public URL.\n' "$SAVE_KEY" >&2
      gl_py warn-git "$SAVE_KEY" >&2 || true
    fi
    if [[ "$SHOW_KEY" -eq 1 ]]; then
      printf 'edit_key=%s\nPrinted on stderr because --show-key was set. Terminal scrollback and CI logs may keep it.\n' "$(cat "$key_file")" >&2
    fi
    if [[ -z "$SAVE_KEY" && "$SHOW_KEY" -eq 0 ]]; then
      printf '%s\n' "The edit_key was not printed or saved, and it cannot be recovered. Publishing again creates a different article. Pass --save-key or --show-key when you need to edit or delete." >&2
    fi
  elif [[ "$COMMAND" == "publish" && "$SHOW_KEY" -eq 0 && -z "$SAVE_KEY" ]]; then
    printf '%s\n' "Response JSON did not include edit_key. Nothing secret was printed." >&2
  elif [[ -n "$SAVE_KEY" || "$SHOW_KEY" -eq 1 ]]; then
    die 1 "Response did not include edit_key."
  fi
  if [[ "$status" -ne 0 ]]; then
    exit "$status"
  fi
  printf '%s\n' "$url"
}

require_yes() {
  local action=$1
  if [[ "$YES" -ne 1 ]]; then
    die 2 "$action needs --yes in addition to the key."
  fi
}

# --- commands --------------------------------------------------------------

case "$COMMAND" in
  publish)
    content_file=$(read_content)
    split_text=$(derive_title_body "$content_file")
    title_file=${split_text%%$'\n'*}
    body_file=${split_text#*$'\n'}
    author_file="-"
    view_file="-"
    if [[ -n "$AUTHOR" ]]; then
      author_file=$(tmpdir)
      printf '%s' "$AUTHOR" >"$author_file"
    fi
    if [[ -n "$VIEW_PASSWORD" && -n "$VIEW_PASSWORD_FILE" ]]; then
      die 2 "Pass only one of --view-password and --view-password-file."
    fi
    if [[ -n "$VIEW_PASSWORD_FILE" ]]; then
      view_file=$(tmpdir)
      must_py load-secret "$VIEW_PASSWORD_FILE" view_password "$view_file"
    elif [[ -n "$VIEW_PASSWORD" ]]; then
      if [[ -z "$VIEW_PASSWORD" ]]; then
        die 2 "View password is empty."
      fi
      view_file=$(stage_secret_arg "$VIEW_PASSWORD")
    fi
    body=$(tmpdir)
    must_py article-json "$title_file" "$body_file" "$author_file" "$view_file" "$body"
    url="${BASE_URL}/api/articles"
    if [[ "$DRY" -eq 1 ]]; then
      dry_print POST "$url" --header "content-type: application/json" --body-file "$body" >&2
      exit 0
    fi
    resp=$(curl_send POST "$url" -H "content-type: application/json" -H "accept: application/json" --data-binary @"$body")
    finish_article "$resp"
    ;;
  read)
    slug=$(must_py normalize-slug "$SLUG")
    if [[ -n "$VIEW_PASSWORD" && -n "$VIEW_PASSWORD_FILE" ]]; then
      die 2 "Pass only one of --view-password and --view-password-file."
    fi
    view_value=""
    if [[ -n "$VIEW_PASSWORD_FILE" ]]; then
      view_file=$(tmpdir)
      must_py load-secret "$VIEW_PASSWORD_FILE" view_password "$view_file"
      view_value=$(cat "$view_file")
    elif [[ -n "$VIEW_PASSWORD" ]]; then
      view_value=$VIEW_PASSWORD
    fi
    if [[ "$MARKDOWN" -eq 1 ]]; then
      if [[ -n "$view_value" ]]; then
        die 2 "The documented password header is for GET /api/articles/SLUG, not the .md URL."
      fi
      url="${BASE_URL}/${slug}.md"
      if [[ "$DRY" -eq 1 ]]; then
        dry_print GET "$url" >&2
        exit 0
      fi
      resp=$(curl_send GET "$url" -H "accept: */*")
      cat "$resp"
      if [[ -s "$resp" && $(tail -c 1 "$resp" | wc -l) -eq 0 ]]; then
        printf '\n'
      fi
    else
      url="${BASE_URL}/api/articles/${slug}"
      if [[ "$DRY" -eq 1 ]]; then
        if [[ -n "$view_value" ]]; then
          dry_print GET "$url" --header "X-View-Password: ${view_value}" >&2
        else
          dry_print GET "$url" >&2
        fi
        exit 0
      fi
      if [[ -n "$view_value" ]]; then
        resp=$(curl_send GET "$url" -H "accept: application/json" -H "X-View-Password: ${view_value}")
      else
        resp=$(curl_send GET "$url" -H "accept: application/json")
      fi
      gl_py opaque "$resp"
    fi
    ;;
  edit)
    require_yes "edit"
    slug=$(must_py normalize-slug "$SLUG")
    key_file=$(load_user_secret "$EDIT_KEY" "$EDIT_KEY_FILE" edit_key "edit-key")
    content_file=$(read_content)
    split_text=$(derive_title_body "$content_file")
    body=$(tmpdir)
    must_py edit-json "$key_file" "${split_text%%$'\n'*}" "${split_text#*$'\n'}" "$body"
    url="${BASE_URL}/api/articles/${slug}"
    if [[ "$DRY" -eq 1 ]]; then
      dry_print PUT "$url" --header "content-type: application/json" --body-file "$body" >&2
      exit 0
    fi
    curl_send PUT "$url" -H "content-type: application/json" -H "accept: application/json" --data-binary @"$body" >/dev/null
    must_py public-url "$BASE_URL" "$slug"
    printf '\n'
    ;;
  delete)
    require_yes "delete"
    slug=$(must_py normalize-slug "$SLUG")
    key_file=$(load_user_secret "$EDIT_KEY" "$EDIT_KEY_FILE" edit_key "edit-key")
    body=$(tmpdir)
    must_py delete-json "$key_file" "$body"
    url="${BASE_URL}/api/articles/${slug}"
    if [[ "$DRY" -eq 1 ]]; then
      dry_print DELETE "$url" --header "content-type: application/json" --body-file "$body" >&2
      exit 0
    fi
    curl_send DELETE "$url" -H "content-type: application/json" -H "accept: application/json" --data-binary @"$body" >/dev/null
    printf 'deleted '
    must_py public-url "$BASE_URL" "$slug"
    printf '\n'
    ;;
  image)
    mime=$(check_image "$IMAGE")
    url="${BASE_URL}/api/images"
    if [[ "$DRY" -eq 1 ]]; then
      printf 'POST %s\nmultipart field image filename=%s content-type=%s\n' "$url" "$(basename "$IMAGE")" "$mime" >&2
      exit 0
    fi
    resp=$(curl_send POST "$url" -H "accept: */*" -F "image=@${IMAGE};type=${mime}")
    printf '%s\n' "Image upload response is below. The API page says to paste the returned Markdown into an article. Images are protected against hotlinking from other sites." >&2
    gl_py opaque "$resp"
    ;;
  new)
    url="${BASE_URL}/api/new?format=json"
    has_text=0; has_file=0; has_title=0; has_image=0
    [[ -n "$TEXT" ]] && has_text=1
    [[ -n "$FILE" ]] && has_file=1
    [[ -n "$TITLE" ]] && has_title=1
    [[ -n "$IMAGE" ]] && has_image=1
    if [[ "$has_text" -eq 1 && "$has_file" -eq 0 && "$has_title" -eq 0 && "$has_image" -eq 0 ]]; then
      text_file=$(tmpdir)
      printf '%s' "$TEXT" >"$text_file"
      if [[ "$DRY" -eq 1 ]]; then
        dry_print POST "$url" --form-file text "$text_file" >&2
        exit 0
      fi
      resp=$(curl_send POST "$url" -H "accept: application/json" --data-urlencode "text@${text_file}")
      finish_article "$resp"
    elif [[ "$has_file" -eq 1 && "$has_text" -eq 0 && "$has_title" -eq 0 && "$has_image" -eq 0 ]]; then
      if [[ ! -f "$FILE" ]]; then
        die 2 "File not found: $FILE"
      fi
      if [[ "$DRY" -eq 1 ]]; then
        printf 'POST %s\nmultipart field file filename=%s\n' "$url" "$(basename "$FILE")" >&2
        exit 0
      fi
      resp=$(curl_send POST "$url" -H "accept: application/json" -F "file=@${FILE};type=text/markdown;charset=utf-8")
      finish_article "$resp"
    elif [[ "$has_title" -eq 1 && "$has_text" -eq 1 && "$has_image" -eq 1 && "$has_file" -eq 0 ]]; then
      mime=$(check_image "$IMAGE")
      if [[ "$DRY" -eq 1 ]]; then
        printf 'POST %s\nmultipart fields title, text, image filename=%s\n' "$url" "$(basename "$IMAGE")" >&2
        exit 0
      fi
      resp=$(curl_send POST "$url" -H "accept: application/json" \
        --form-string "title=${TITLE}" --form-string "text=${TEXT}" -F "image=@${IMAGE};type=${mime}")
      finish_article "$resp"
    else
      die 2 "new accepts three documented forms: --text TEXT; --file PATH; or --title TEXT --text TEXT --image FILE."
    fi
    ;;
  preview)
    content_file=$(read_content)
    if [[ ! -s "$content_file" ]]; then
      die 2 "Preview content is empty."
    fi
    body=$(tmpdir)
    python3 - "$content_file" "$body" <<'PY'
import json, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8-sig")
if text.strip() == "":
    sys.stderr.write("Preview content is empty.\n")
    raise SystemExit(2)
Path(sys.argv[2]).write_bytes(json.dumps({"content": text}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
PY
    url="${BASE_URL}/api/preview"
    if [[ "$DRY" -eq 1 ]]; then
      dry_print POST "$url" --header "content-type: application/json" --body-file "$body" >&2
      exit 0
    fi
    resp=$(curl_send POST "$url" -H "content-type: application/json" -H "accept: */*" --data-binary @"$body")
    printf '%s\n' "Preview only. Nothing was published." >&2
    gl_py opaque "$resp"
    ;;
  qr)
    python3 - "$QR_URL" <<'PY'
import sys
from urllib.parse import urlparse
parsed = urlparse(sys.argv[1])
if parsed.scheme not in ("https", "http") or not parsed.netloc:
    sys.stderr.write("qr expects an http(s) URL.\n")
    raise SystemExit(2)
PY
    url="${BASE_URL}/api/qr?u=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$QR_URL")"
    if [[ "$DRY" -eq 1 ]]; then
      dry_print GET "$url" >&2
      exit 0
    fi
    resp=$(curl_send GET "$url" -H "accept: image/svg+xml, */*")
    if [[ -n "$OUTPUT" ]]; then
      cp "$resp" "$OUTPUT"
      printf 'Wrote %s\n' "$OUTPUT" >&2
    else
      cat "$resp"
    fi
    ;;
  telegraph)
    case "$SUB" in
      account)
        if [[ -z "$SHORT_NAME" || -z "${SHORT_NAME// /}" ]]; then
          die 2 "telegraph account needs --short-name."
        fi
        url="${BASE_URL}/telegraph/createAccount?short_name=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$SHORT_NAME")"
        if [[ -n "$AUTHOR_NAME" ]]; then
          url="${url}&author_name=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$AUTHOR_NAME")"
        fi
        if [[ "$DRY" -eq 1 ]]; then
          dry_print GET "$url" >&2
          exit 0
        fi
        resp=$(curl_send GET "$url" -H "accept: application/json")
        token_file=$(tmpdir)
        short_name=$(must_py extract-account "$resp" "$token_file")
        printf '%s\n' "$short_name"
        if [[ ! -s "$token_file" ]]; then
          die 1 "Response did not include access_token."
        fi
        if [[ -s "$token_file" ]]; then
          if [[ -n "$SAVE_TOKEN" ]]; then
            must_py save-record "$SAVE_TOKEN" access_token - "$token_file"
            printf 'Wrote access_token to %s with mode 600. Do not commit that file or put the key in a public URL.\n' "$SAVE_TOKEN" >&2
            gl_py warn-git "$SAVE_TOKEN" >&2 || true
          fi
          if [[ "$SHOW_TOKEN" -eq 1 ]]; then
            printf 'access_token=%s\nPrinted on stderr because --show-token was set. Terminal scrollback and CI logs may keep it.\n' "$(cat "$token_file")" >&2
          fi
          if [[ -z "$SAVE_TOKEN" && "$SHOW_TOKEN" -eq 0 ]]; then
            printf '%s\n' "The access_token was not printed or saved. createAccount returns it once; later calls need the same token. Pass --save-token or --show-token to keep it." >&2
          fi
        fi
        ;;
      get)
        slug=$(must_py normalize-slug "${PAGE_PATH:-$SLUG}")
        flag=false
        if [[ "$RETURN_CONTENT" -eq 1 ]]; then
          flag=true
        fi
        url="${BASE_URL}/telegraph/getPage?path=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$slug")&return_content=${flag}"
        if [[ "$DRY" -eq 1 ]]; then
          dry_print GET "$url" >&2
          exit 0
        fi
        resp=$(curl_send GET "$url" -H "accept: application/json")
        gl_py print-result "$resp"
        ;;
      list|info)
        token_file=$(load_user_secret "$TOKEN" "$TOKEN_FILE" access_token "token")
        method_name=getPageList
        if [[ "$SUB" == "info" ]]; then
          method_name=getAccountInfo
        fi
        encoded=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(open(sys.argv[1], encoding="utf-8").read(), safe=""))' "$token_file")
        url="${BASE_URL}/telegraph/${method_name}?access_token=${encoded}"
        if [[ "$DRY" -eq 1 ]]; then
          dry_print GET "$url" >&2
          exit 0
        fi
        resp=$(curl_send GET "$url" -H "accept: application/json")
        gl_py print-result "$resp"
        ;;
      create|edit)
        token_file=$(load_user_secret "$TOKEN" "$TOKEN_FILE" access_token "token")
        if [[ "$SUB" == "edit" ]]; then
          require_yes "telegraph edit"
          if [[ -z "$PAGE_PATH" ]]; then
            die 2 "Telegraph edit needs --path."
          fi
        fi
        if [[ -z "$TITLE" || -z "${TITLE// /}" ]]; then
          die 2 "Telegraph page needs --title."
        fi
        if [[ -n "$TEXT" && -n "$CONTENT" ]]; then
          die 2 "Pass either --text or --content."
        fi
        nodes=$(tmpdir)
        if [[ -n "$TEXT" ]]; then
          text_file=$(tmpdir)
          printf '%s' "$TEXT" >"$text_file"
          must_py nodes text "$text_file" "$nodes"
        elif [[ -n "$CONTENT" ]]; then
          content_file=$(tmpdir)
          printf '%s' "$CONTENT" >"$content_file"
          must_py nodes json "$content_file" "$nodes"
        else
          die 2 "Pass --text or --content for the Telegraph page."
        fi
        title_file=$(tmpdir)
        printf '%s' "$TITLE" >"$title_file"
        endpoint=createPage
        if [[ "$SUB" == "edit" ]]; then
          endpoint=editPage
        fi
        url="${BASE_URL}/telegraph/${endpoint}"
        if [[ "$DRY" -eq 1 ]]; then
          dry_print POST "$url" --form-file access_token "$token_file" --form-file title "$title_file" --form-file content "$nodes" >&2
          exit 0
        fi
        if [[ "$SUB" == "create" ]]; then
          extra=()
          if [[ "$RETURN_CONTENT" -eq 1 ]]; then
            extra+=(--data-urlencode "return_content=true")
          fi
          resp=$(curl_send POST "$url" -H "accept: application/json" \
            --data-urlencode "access_token@${token_file}" \
            --data-urlencode "title@${title_file}" \
            --data-urlencode "content@${nodes}" \
            "${extra[@]+"${extra[@]}"}")
          url_file=$(tmpdir)
          must_py extract-page-url "$resp" "$url_file"
          cat "$url_file"
          printf '\n'
        else
          path_file=$(tmpdir)
          must_py normalize-slug "$PAGE_PATH" >"$path_file"
          resp=$(curl_send POST "$url" -H "accept: application/json" \
            --data-urlencode "access_token@${token_file}" \
            --data-urlencode "path@${path_file}" \
            --data-urlencode "title@${title_file}" \
            --data-urlencode "content@${nodes}")
          gl_py print-result "$resp" >/dev/null
          must_py public-url "$BASE_URL" "$(cat "$path_file")"
          printf '\n'
        fi
        ;;
    esac
    ;;
esac
