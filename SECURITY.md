# Security

This repository holds example clients. It does not hold the Glanote server, admin paths, or real credentials.

## Keys

An edit key, a Telegraph `access_token`, and a view password are secrets. The public API returns the edit key once. Glanote stores a hash and cannot send the key again. The clients print the public URL only, unless you pass `--show-key` or `--show-token` (stderr) or `--save-key` / `--save-token` (a new file, mode `0600`).

Do not open a GitHub issue that contains a live key. If a key was committed, revoke it if you still can, and treat the page as something you may not be able to delete. Prefer `--edit-key-file` and `--token-file` so the secret is not in the shell history.

`--dry-run` redacts those fields. HTTP error bodies are redacted before they are printed. A public URL that itself contains the secret is not printed.

The Telegraph examples put `access_token` in the query string. The wrapper has to do the same for `getPageList`, `getAccountInfo`, and `createAccount`. Those URLs can show up in proxy logs.

## Reporting a problem in these clients

Open an issue on this repository if a client prints a secret it was supposed to hide, or follows a redirect with a request body. Do not include a real key in the report. A short description and the command line, with the secret replaced by `YOUR_EDIT_KEY`, is enough.

For the service itself, including abuse or a request to erase an article completely, use the address published on the contact page: contact@glanote.com. The public API also documents a report call. These clients do not wrap it.
