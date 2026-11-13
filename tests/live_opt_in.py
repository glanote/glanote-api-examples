#!/usr/bin/env python3
"""Opt-in live check against the public Glanote API.

Refuses to run unless GLANOTE_LIVE=1 and --confirm-live are both set.
Creates at most three articles, on the documented POST /api/articles call,
then soft-deletes each one with its edit key. Image upload and Telegraph
createPage are not called: the public docs do not describe a way to delete
those objects. Keys stay in a mode 0700 temp directory and are removed after
a successful delete. They are not printed.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://glanote.com"
MAX_ARTICLES = 3
CREATED = 0


def refuse(message: str) -> None:
    sys.stderr.write(message.rstrip() + "\n")
    raise SystemExit(2)


def require_opt_in() -> None:
    if os.environ.get("GLANOTE_LIVE") != "1" or "--confirm-live" not in sys.argv:
        refuse(
            "Refusing to publish. This check is off unless GLANOTE_LIVE=1 "
            "and --confirm-live are both set. It creates at most "
            f"{MAX_ARTICLES} public articles and then soft-deletes them."
        )


def run(args: list[str], secrets_to_hide: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    result.stdout = scrub(result.stdout, secrets_to_hide)
    result.stderr = scrub(result.stderr, secrets_to_hide)
    return result


def scrub(text: str, secrets_to_hide: list[str]) -> str:
    for secret in secrets_to_hide:
        if secret:
            text = text.replace(secret, "REDACTED")
    return text


def python_client() -> list[str]:
    return [sys.executable, str(ROOT / "python" / "glanote.py"), "--base-url", BASE, "--timeout", "45"]


def node_client() -> list[str]:
    return ["node", str(ROOT / "javascript" / "glanote.mjs"), "--base-url", BASE, "--timeout", "45"]


def shell_client() -> list[str]:
    return ["bash", str(ROOT / "shell" / "glanote.sh"), "--base-url", BASE, "--timeout", "45"]


def reserve_slot() -> None:
    global CREATED
    if CREATED >= MAX_ARTICLES:
        raise RuntimeError(f"Refusing to create more than {MAX_ARTICLES} articles.")
    CREATED += 1


def publish_file(client: list[str], note: Path, key_path: Path, extra: list[str], hidden: list[str]) -> str:
    reserve_slot()
    result = run(
        client + ["publish", "--file", str(note), "--save-key", str(key_path), *extra],
        hidden,
    )
    url = result.stdout.strip()
    if result.returncode != 0 or not url.startswith("https://"):
        raise RuntimeError(
            "Publish failed.\n"
            f"exit {result.returncode}\n{result.stderr}\n{result.stdout}"
        )
    if "REDACTED" in url or any(secret and secret in result.stdout for secret in hidden):
        raise RuntimeError("Publish stdout was not a public URL.")
    if not key_path.is_file():
        raise RuntimeError("Publish did not write the edit key file.")
    mode = stat.S_IMODE(key_path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError(f"Edit key file mode is {oct(mode)}, expected 0600.")
    return url


def slug_of(url: str) -> str:
    path = urllib.parse.urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    if not slug or "/" in slug:
        raise RuntimeError("Publish URL did not include a slug.")
    return slug


def load_key(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    key = data.get("edit_key", "")
    if not isinstance(key, str) or not key:
        raise RuntimeError("Saved management file has no edit_key.")
    return key


def delete_article(client: list[str], slug: str, key_path: Path, hidden: list[str]) -> None:
    result = run(
        client + ["delete", slug, "--edit-key-file", str(key_path), "--yes"],
        hidden,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Delete failed for {slug}.\nexit {result.returncode}\n{result.stderr}")


def read_public(slug: str) -> tuple[int, str]:
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "--max-redirs",
            "0",
            "--max-time",
            "30",
            "-w",
            "\n%{http_code}",
            f"{BASE}/api/articles/{slug}",
        ],
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not re-read {slug}: {result.stderr.strip()}")
    body, _, code = result.stdout.rpartition("\n")
    try:
        status = int(code.strip())
    except ValueError as exc:
        raise RuntimeError(f"Unexpected read status for {slug}.") from exc
    return status, body


def still_public(slug: str, nonce: str, hidden: list[str], password_file: Path | None = None) -> bool:
    args = python_client() + ["read", slug]
    if password_file is not None:
        args.extend(["--view-password-file", str(password_file)])
    result = run(args, hidden)
    if result.returncode == 0:
        text = result.stdout
        return nonce in text or "Transient API example" in text or slug in text
    status, body = read_public(slug)
    if nonce and nonce in body:
        return True
    if "Transient API example" in body:
        return True
    if status in {400, 401, 403, 404, 410}:
        return False
    if status == 200:
        return slug in body
    raise RuntimeError(f"After delete, {slug} returned HTTP {status}.")


def shred(path: Path) -> None:
    if path.exists():
        path.write_bytes(b"\0" * max(path.stat().st_size, 1))
        path.unlink()


def write_note(path: Path, title: str, nonce: str, extra: str) -> None:
    path.write_text(
        f"# {title}\n\n"
        "Transient page from the glanote-api-examples live check. "
        "It is removed at the end of the same run.\n\n"
        f"{extra}\n\nNonce: {nonce}\n",
        encoding="utf-8",
    )


def expect_ok(
    label: str,
    result: subprocess.CompletedProcess[str],
    problems: list[str],
    *,
    need_stdout: bool = True,
) -> None:
    if result.returncode != 0 or (need_stdout and not result.stdout.strip()):
        problems.append(f"{label} failed (exit {result.returncode}): {result.stderr.strip()[:300]}")


def main() -> int:
    require_opt_in()
    probe = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20", f"{BASE}/en/api"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "200":
        sys.stderr.write("The public API docs did not respond. No test article was created.\n")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="glanote-live-"))
    os.chmod(tmp, 0o700)
    hidden: list[str] = []
    created: list[dict[str, str]] = []
    problems: list[str] = []
    report: list[str] = []
    try:
        cases = [
            ("python", python_client(), "Transient API example 1", "Unicode: 测试 café かな"),
            ("node", node_client(), "Transient API example 2", "Created by the Node example client."),
            ("shell", shell_client(), "Transient API example 3", "Created by the curl example client."),
        ]
        for name, client, title, extra in cases:
            nonce = secrets.token_hex(8)
            note = tmp / f"{name}.md"
            key_path = tmp / f"{name}-edit-key.json"
            write_note(note, title, nonce, extra)
            extra_args: list[str] = []
            if name == "shell":
                password = secrets.token_urlsafe(12)
                hidden.append(password)
                password_path = tmp / "view-password"
                password_path.write_text(password + "\n", encoding="utf-8")
                os.chmod(password_path, 0o600)
                extra_args = ["--view-password-file", str(password_path)]
            try:
                url = publish_file(client, note, key_path, extra_args, hidden)
            except Exception as exc:
                problems.append(f"{name} publish: {exc}")
                break
            slug = slug_of(url)
            key = load_key(key_path)
            hidden.append(key)
            created.append({"name": name, "slug": slug, "key": str(key_path), "nonce": nonce, "deleted": ""})
            read = run(python_client() + ["read", slug], hidden)
            if name == "shell":
                # A view password was set, so a read without it is expected to fail.
                if read.returncode == 0 and (nonce in read.stdout or "Transient API example" in read.stdout):
                    problems.append("shell article was readable without the view password")
                unlocked = run(
                    python_client() + ["read", slug, "--view-password-file", str(tmp / "view-password")],
                    hidden,
                )
                if unlocked.returncode != 0:
                    problems.append(f"{name} password read failed: {unlocked.stderr.strip()[:300]}")
                elif nonce not in unlocked.stdout and "Transient API example" not in unlocked.stdout:
                    problems.append(f"{name} password read did not include the test note.")
            elif read.returncode != 0:
                problems.append(f"{name} read failed: {read.stderr.strip()[:300]}")
            if name == "python":
                edited = run(
                    python_client()
                    + [
                        "edit",
                        slug,
                        "--edit-key-file",
                        str(key_path),
                        "--yes",
                        "--title",
                        title + " updated",
                        "--content",
                        f"Updated by the live check.\n\nNonce: {nonce}\n",
                    ],
                    hidden,
                )
                if edited.returncode != 0:
                    problems.append(f"python edit failed: {edited.stderr.strip()[:300]}")
            try:
                delete_article(client, slug, key_path, hidden)
                password_file = tmp / "view-password" if name == "shell" else None
                if still_public(slug, nonce, hidden, password_file):
                    delete_article(client, slug, key_path, hidden)
                if still_public(slug, nonce, hidden, password_file):
                    problems.append(f"{name} article {slug} was still public after delete.")
                else:
                    created[-1]["deleted"] = "yes"
                    shred(key_path)
                    report.append(f"{name}: published {url} and soft-deleted {slug}")
            except Exception as exc:
                problems.append(str(exc))
                break

        readonly = [
            ("read f6a0b2", python_client() + ["read", "f6a0b2"]),
            ("markdown f6a0b2", python_client() + ["read", "f6a0b2", "--markdown"]),
            ("preview", python_client() + ["preview", "--content", "**live check**"]),
            ("telegraph getPage", python_client() + ["telegraph", "get", "f6a0b2"]),
        ]
        qr_path = tmp / "qr.svg"
        readonly.append(("qr", python_client() + ["qr", f"{BASE}/f6a0b2", "--output", str(qr_path)]))
        for label, args in readonly:
            result = run(args, hidden)
            expect_ok(label, result, problems, need_stdout=label != "qr")
        if not qr_path.is_file() or qr_path.stat().st_size == 0:
            problems.append("qr did not write an SVG.")

        print(f"Live integration against {BASE}")
        print(f"Articles created: {CREATED} (cap {MAX_ARTICLES})")
        for line in report:
            print(line)
        print("Not called: POST /api/images, POST /api/new, Telegraph createPage.")
        print("Reason: the public docs do not describe a delete for those responses.")
        print("Offline tests covered those requests against a mock.")
        leftover = [item for item in created if item["deleted"] != "yes"]
        if leftover:
            print("Cleanup incomplete. Key files remain in this private directory and were not printed:")
            print(tmp)
            for item in leftover:
                print(f"  {item['name']} slug={item['slug']} key_file={item['key']}")
        else:
            print("Cleanup: every created test article was soft-deleted. Keys were removed.")
            shred(tmp / "view-password")
            for child in tmp.iterdir():
                if child.is_file():
                    shred(child)
            tmp.rmdir()
        if problems:
            print("Problems:")
            for problem in problems:
                print(f"- {scrub(problem, hidden)}")
            return 1
        return 0
    except Exception as exc:
        sys.stderr.write(scrub(str(exc), hidden) + "\n")
        sys.stderr.write(f"Private files, if any, are in {tmp}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
