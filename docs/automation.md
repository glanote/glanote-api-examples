# Scripts and CI

[Back to the English README](../README.md).

The offline test workflow in `.github/workflows/ci.yml` runs on every push and pull request. It does not call Glanote. The live workflow, `.github/workflows/live.yml`, runs only when someone starts it by hand. It publishes at most three test articles and soft-deletes them.

## Publish one note from a shell script

```bash
#!/usr/bin/env bash
set -euo pipefail
url=$(python3 python/glanote.py publish \
  --file "$1" \
  --save-key "$HOME/.glanote-edit-key.json")
printf '%s\n' "$url"
```

The command substitution captures the public URL. The edit key stays in the file. Do not add `--show-key` here: stderr would contain the key, and many runners save both streams.

This is one file per run. The service allows 10 articles per IP per hour. A loop that walks a directory will trip that limit and will also leave a trail of public pages. This repository does not include a bulk publisher.

## A manual GitHub Actions publish

Push events should not publish. If you want a button in the Actions tab, start from a `workflow_dispatch` job and keep the key off the log:

```yaml
name: Publish one note
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Publish
        run: |
          python3 python/glanote.py publish \
            --file examples/note.md \
            --save-key "$RUNNER_TEMP/edit-key.json"
          echo "The edit key is only in the runner temp directory. It is not uploaded."
```

The log receives stdout, which is the public URL. That URL is already public. Do not pass `--show-key`, and do not upload the key file as an artifact. The file disappears when the runner does. Unless you copy it out through a channel you trust, you will not be able to edit or delete the page later. For a note you may want to remove, publish from your own machine and keep the key file.

## A program that posts one message

Any bot can call the REST API. The API page says the site's own Telegram bot is not configured, and this repository does not speak Telegram's bot protocol.

```python
import subprocess
import sys

note = sys.stdin.read()
if not note.strip():
    sys.exit("empty note")
result = subprocess.run(
    [
        sys.executable,
        "python/glanote.py",
        "publish",
        "--title",
        "Status",
        "--content",
        note,
        "--save-key",
        "/tmp/glanote-edit-key.json",
    ],
    check=True,
    text=True,
    capture_output=True,
)
print(result.stdout.strip())
```

Read one message, publish once, print the URL. Store the key file somewhere private if you need to delete the page. Do not log `result.stderr` blindly if you also passed `--show-key`.

## What CI should not do

- Do not put a real edit key, access token, or view password in the workflow file or in the repository.
- Do not run `tests/live_opt_in.py` on push. It creates public pages on purpose, and only after `GLANOTE_LIVE=1` and `--confirm-live`.
- Do not add a report call or a Telegram send method to the clients. Those are outside this repository.
