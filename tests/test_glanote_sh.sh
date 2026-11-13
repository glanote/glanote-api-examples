#!/usr/bin/env bash
# Offline tests for shell/glanote.sh. HTTP stays on a local mock.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
CLIENT="$ROOT/shell/glanote.sh"
SECRET="unit-test-edit-key-9f3a"
VIEW="unit-test-view-pw-44c1"
TOKEN="unit-test-access-token-77ab"
TMP=$(mktemp -d)
LOG="$TMP/requests.jsonl"
REPLY="$TMP/reply.json"
PORTFILE="$TMP/port"
cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

python3 - "$LOG" "$REPLY" "$PORTFILE" <<'PY' &
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log_path, reply_path, port_path = map(Path, sys.argv[1:])

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._handle()

    do_POST = do_PUT = do_DELETE = do_GET

    def _handle(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        record = {
            "method": self.command,
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": body.decode("utf-8", "replace"),
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        spec = json.loads(reply_path.read_text(encoding="utf-8"))
        time.sleep(float(spec.get("delay") or 0))
        payload = spec.get("body", "{}")
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        self.send_response(int(spec.get("code", 200)))
        self.send_header("content-type", spec.get("type", "application/json; charset=utf-8"))
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port_path.write_text(f"http://127.0.0.1:{server.server_address[1]}", encoding="utf-8")
server.serve_forever()
PY
SERVER_PID=$!

for _ in $(seq 1 50); do
  if [[ -s "$PORTFILE" ]]; then
    break
  fi
  sleep 0.05
done
BASE=$(cat "$PORTFILE")
if [[ -z "$BASE" ]]; then
  echo "mock server did not start" >&2
  exit 1
fi

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_eq() {
  if [[ "$1" != "$2" ]]; then
    printf 'FAIL: expected %q got %q\n' "$2" "$1" >&2
    exit 1
  fi
}

run_cli() {
  set +e
  STDOUT_FILE="$TMP/stdout"
  STDERR_FILE="$TMP/stderr"
  bash "$CLIENT" --base-url "$BASE" "$@" >"$STDOUT_FILE" 2>"$STDERR_FILE"
  CODE=$?
  set -e
  STDOUT=$(cat "$STDOUT_FILE")
  STDERR=$(cat "$STDERR_FILE")
}

reset_reply() {
  printf '%s' "$1" >"$REPLY"
  : >"$LOG"
}

last_request() {
  python3 - "$LOG" <<'PY'
import json, sys
from pathlib import Path
lines = [line for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
print(lines[-1] if lines else "")
PY
}

# help and rejected base URLs do not touch the mock
bash "$CLIENT" --help >"$TMP/help.out" 2>"$TMP/help.err"
grep -q -- '--base-url' "$TMP/help.err"
grep -q -- '--timeout' "$TMP/help.err"
grep -q 'https://glanote.com/en/api' "$TMP/help.err"
set +e
bash "$CLIENT" --base-url 'https://user:pass@glanote.com' read f6a0b2 >"$TMP/o" 2>"$TMP/e"
status=$?
set -e
if [[ "$status" -eq 0 ]]; then
  fail "credential base URL was accepted"
fi
if [[ -s "$LOG" ]]; then
  fail "rejected base URL still made a request"
fi

reset_reply "{\"code\":200,\"body\":\"{\\\"url\\\":\\\"${BASE}/ab12cd\\\",\\\"edit_key\\\":\\\"${SECRET}\\\"}\"}"
KEY="$TMP/key.json"
run_cli publish --title '测试 café' --content '你好 🌟' --save-key "$KEY"
assert_eq "$CODE" "0"
assert_eq "$STDOUT" "${BASE}/ab12cd"
if [[ "$STDOUT$STDERR" == *"$SECRET"* ]]; then
  fail "edit key leaked during publish"
fi
python3 - "$LOG" "$KEY" "$SECRET" "$BASE" <<'PY'
import json, os, stat, sys
from pathlib import Path
log, key_path, secret, base = sys.argv[1:]
record = json.loads(Path(log).read_text(encoding="utf-8").splitlines()[-1])
body = json.loads(record["body"])
assert body == {"title": "测试 café", "content": "你好 🌟"}, body
assert "\\u00e9" not in record["body"]
assert record["headers"]["content-type"].startswith("application/json")
saved = json.loads(Path(key_path).read_text(encoding="utf-8"))
assert saved["edit_key"] == secret
assert saved["url"] == f"{base}/ab12cd"
mode = stat.S_IMODE(Path(key_path).stat().st_mode)
assert mode == 0o600, oct(mode)
PY

run_cli publish --title T --content body --show-key
assert_eq "$CODE" "0"
if [[ "$STDOUT" == *"$SECRET"* ]]; then
  fail "show-key put the key on stdout"
fi
if [[ "$STDERR" != *"$SECRET"* ]]; then
  fail "show-key did not print the key on stderr"
fi

run_cli publish --title T --content body
assert_eq "$CODE" "0"
if [[ "$STDOUT$STDERR" == *"$SECRET"* ]]; then
  fail "discarded key was printed"
fi
if [[ "$STDERR" != *"cannot be recovered"* ]]; then
  fail "missing discard warning: $STDERR"
fi

: >"$LOG"
run_cli publish --title T --content 'secret body' --view-password "$VIEW" --dry-run
assert_eq "$CODE" "0"
if [[ "$STDOUT$STDERR" == *"$VIEW"* ]]; then
  fail "view password leaked in dry-run"
fi
if [[ "$STDERR" != *'view_password":"REDACTED"'* ]]; then
  fail "view password was not redacted: $STDERR"
fi
if [[ -s "$LOG" ]]; then
  fail "dry-run contacted the server"
fi

reset_reply '{"code":200,"body":"{}"}'
run_cli delete ab12cd --edit-key "$SECRET"
if [[ "$CODE" -eq 0 ]]; then
  fail "delete without --yes succeeded"
fi
if [[ -s "$LOG" ]]; then
  fail "delete without --yes sent a request"
fi
run_cli delete ab12cd --edit-key "$SECRET" --yes --dry-run
assert_eq "$CODE" "0"
if [[ "$STDOUT$STDERR" == *"$SECRET"* ]]; then
  fail "delete dry-run leaked the key"
fi
if [[ "$STDERR" != *'edit_key":"REDACTED"'* ]]; then
  fail "delete dry-run did not redact: $STDERR"
fi
run_cli delete ab12cd --edit-key "$SECRET" --yes
assert_eq "$CODE" "0"
assert_eq "$STDOUT" "deleted ${BASE}/ab12cd"
if [[ "$STDOUT$STDERR" == *"$SECRET"* ]]; then
  fail "delete leaked the key"
fi
python3 - "$LOG" "$SECRET" <<'PY'
import json, sys
record = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[-1])
assert record["method"] == "DELETE"
assert json.loads(record["body"]) == {"edit_key": sys.argv[2]}
PY

reset_reply "{\"code\":400,\"body\":\"{\\\"edit_key\\\":\\\"${SECRET}\\\",\\\"password\\\":\\\"${VIEW}\\\",\\\"message\\\":\\\"no\\\"}\"}"
run_cli publish --title T --content body
if [[ "$CODE" -eq 0 ]]; then
  fail "HTTP 400 was treated as success"
fi
if [[ "$STDERR" != *"HTTP 400"* ]]; then
  fail "missing HTTP status: $STDERR"
fi
if [[ "$STDOUT$STDERR" == *"$SECRET"* || "$STDOUT$STDERR" == *"$VIEW"* ]]; then
  fail "HTTP error leaked a secret: $STDERR"
fi

reset_reply '{"code":200,"body":"{}","delay":1.5}'
start=$(date +%s)
run_cli --timeout 0.4 read f6a0b2
end=$(date +%s)
if [[ "$CODE" -eq 0 ]]; then
  fail "timeout returned success"
fi
if [[ "$STDERR" != *"timed out"* ]]; then
  fail "missing timeout message: $STDERR"
fi
if (( end - start >= 2 )); then
  fail "timeout waited too long"
fi

PNG="$TMP/demo.png"
printf '' >"$PNG"
python3 - "$PNG" <<'PY'
import pathlib, sys
pathlib.Path(sys.argv[1]).write_bytes(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
))
PY
printf 'nope' >"$TMP/clip.mp4"
: >"$LOG"
run_cli image "$TMP/clip.mp4"
if [[ "$CODE" -eq 0 ]]; then
  fail "video upload was accepted"
fi
reset_reply '{"code":200,"body":"![demo](https://example.test/demo.png)\n","type":"text/plain"}'
run_cli image "$PNG"
assert_eq "$CODE" "0"
if [[ "$STDOUT" != *'![demo]'* ]]; then
  fail "image response missing markdown: $STDOUT"
fi
if [[ "$STDERR" != *[Hh]otlinking* ]]; then
  fail "missing hotlink note"
fi
python3 - "$LOG" <<'PY'
import json, sys
record = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[-1])
assert record["path"] == "/api/images"
assert 'name="image"' in record["body"]
PY

reset_reply "{\"code\":200,\"body\":\"{\\\"url\\\":\\\"${BASE}/cd34ef\\\",\\\"edit_key\\\":\\\"${SECRET}\\\"}\"}"
run_cli new --text '一句话也能发布成文章'
assert_eq "$CODE" "0"
assert_eq "$STDOUT" "${BASE}/cd34ef"
if [[ "$STDOUT$STDERR" == *"$SECRET"* ]]; then
  fail "new leaked the edit key"
fi
python3 - "$LOG" <<'PY'
import json, sys
from urllib.parse import parse_qsl
record = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[-1])
assert "/api/new?format=json" in record["path"]
assert parse_qsl(record["body"]) == [("text", "一句话也能发布成文章")]
PY

run_cli --base-url 'http://127.0.0.1:9' telegraph list --token "$TOKEN" --dry-run
assert_eq "$CODE" "0"
if [[ "$STDOUT$STDERR" == *"$TOKEN"* ]]; then
  fail "telegraph dry-run leaked the token"
fi
if [[ "$STDERR" != *"access_token=REDACTED"* || "$STDERR" != *"/telegraph/getPageList"* ]]; then
  fail "telegraph dry-run was not redacted: $STDERR"
fi

if grep -q '/report' "$CLIENT" || grep -q 'api.telegram.org' "$CLIENT" || grep -q '/telegram/' "$CLIENT"; then
  fail "shell client references a report or telegram endpoint"
fi

printf 'shell tests passed\n'
