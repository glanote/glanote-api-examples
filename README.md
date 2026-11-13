[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Glanote API examples

Publish a Markdown note and get a public link back, without creating an account. This repository is a small set of Python, Node, and curl clients for the article API on [Glanote](https://glanote.com/). The request shapes match the public docs at [glanote.com/en/api](https://glanote.com/en/api). What the service stores, and what happens to an edit key, is covered in the [privacy policy](https://glanote.com/en/privacy).

There is no API key. A publish response contains a public `url` and an `edit_key`. The key is the only credential that can change or remove that page. Glanote stores a hash of it and cannot show it to you again.

These are example clients. They are not the Glanote server, and they are not published to npm or PyPI.

## Quick start

Reading the article used in the docs does not publish anything:

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

Publishing does create a public page, and it counts toward the limit of 10 articles per IP per hour. Edit `examples/note.md` first if you do not want the sample text online. The next command prints only the public URL. The edit key goes into a new file, mode `0600`:

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

`node javascript/glanote.mjs` and `./shell/glanote.sh` take the same arguments. The shell script needs Bash, curl, and `python3` (used only to encode JSON). Node 18 or newer, and Python 3.9 or newer, are enough for the other two.

To remove the page:

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` is the short code at the end of the public link. The docs use `f6a0b2` as the example. You can pass that code or the whole article URL.

If you publish without `--save-key` or `--show-key`, the client drops the edit key on purpose. That page cannot be edited or deleted afterward. Publishing again creates a different page; it does not bring the key back.

## Commands

| Task | Command |
| --- | --- |
| Publish a file or stdin | `publish --file note.md --save-key "$HOME/.glanote-edit-key.json"` |
| Read JSON | `read YOUR_SLUG` |
| Read Markdown | `read YOUR_SLUG --markdown` |
| Read with a view password | `read YOUR_SLUG --view-password-file ./view-password` |
| Replace title and body | `edit YOUR_SLUG --edit-key-file ./key.json --yes --file note.md` |
| Soft-delete | `delete YOUR_SLUG --edit-key-file ./key.json --yes` |
| Upload an image | `image photo.png` |
| One-line publish | `new --text "A single line"` |
| Publish a file through `/api/new` | `new --file note.md --save-key ./key.json` |
| Title, text, and image | `new --title "With a picture" --text "Below" --image photo.png --save-key ./key.json` |
| Preview, no publish | `preview --file note.md` |
| QR SVG | `qr https://glanote.com/f6a0b2 --output qr.svg` |

Global flags, in any position:

| Flag | Meaning |
| --- | --- |
| `--base-url URL` | Default `https://glanote.com`, or `$GLANOTE_BASE_URL` |
| `--timeout SECONDS` | Default 30, or `$GLANOTE_TIMEOUT`. Must be greater than 0 and at most 300 |
| `--dry-run` | Print the request and do not send it. Secrets are redacted |
| `--help`, `--version` | Usage, or `0.1.0` |

Stdout for publish is the public URL and nothing else, so `url=$(python3 python/glanote.py publish …)` is safe. `--show-key` prints the edit key on stderr. Terminal scrollback and CI logs will keep it. `--save-key` is the better default: the file is created with mode `0600`, the path must not already exist, and the client refuses to leave it group-readable. The same rules apply to a Telegraph `access_token` via `--save-token` and `--show-token`.

Edit and delete always need the key (`--edit-key` or `--edit-key-file`) and `--yes`. A view password is not the edit key. Pass it with `--view-password` or `--view-password-file`. It is sent as the documented `view_password` field, or as the `X-View-Password` header on `GET /api/articles/SLUG`. The header is not sent to the `/{slug}.md` URL, because the docs show it only on the JSON read.

A leading `# title` becomes the title when you use `publish` or `edit` without `--title`. The `/api/new` forms are separate and follow the three shapes on the API page: a `text` field, a `file` field, or `title` + `text` + `image` together.

The image command accepts JPG, PNG, WebP, and GIF up to 5 MB. Other types, including video files, are rejected before the request. Paste the returned Markdown into an article. Glanote protects images against hotlinking, so that URL may not render on another website.

## A curl call, if you want the raw request

This is the publish call from the API page. curl writes the whole JSON response, **including the edit key**, to your terminal:

```bash
curl -X POST https://glanote.com/api/articles \
  -H 'content-type: application/json' \
  -d '{"title":"A note","content":"Hello from the terminal."}'
```

Use `shell/glanote.sh` when you want curl to do the HTTP and still keep the key out of stdout. Reading does not return an edit key:

```bash
curl https://glanote.com/api/articles/f6a0b2
curl https://glanote.com/f6a0b2.md
```

## Telegraph-compatible calls

Glanote documents six methods at `https://glanote.com/telegraph`: `createAccount`, `createPage`, `editPage`, `getPage`, `getPageList`, and `getAccountInfo`. A program written for `https://api.telegra.ph` can switch the host. `getPage` takes the short code, not a `Title-12-31` path. `editPage` only works for pages created with the same `access_token`.

```bash
python3 python/glanote.py telegraph account \
  --short-name myblog --author-name "Glanote Fan" \
  --save-token "$HOME/.glanote-telegraph-token.json"

python3 python/glanote.py telegraph create \
  --token-file "$HOME/.glanote-telegraph-token.json" \
  --title "From the Telegraph API" \
  --text "Hello."

python3 python/glanote.py telegraph get f6a0b2
```

The official Telegraph docs also describe `editAccountInfo`, `revokeAccessToken`, and `getViews`. Glanote's API page does not list those, so this client does not call them. Optional parameters that do not appear in Glanote's examples (`author_url`, `offset`, `limit`, `fields`) are not sent either.

`createAccount` and `getPageList` put `access_token` in the query string, because that is how the examples are written. Proxy logs can record it. Prefer `--token-file` over pasting the token into a shell that saves history.

There is no documented Telegraph delete in this six-method set. A page created that way is not removed by `delete`, which only sends an `edit_key` to the REST API.

## Practical uses

- Leave a note on another device. Publish from the laptop, open the URL on a phone, delete it later with the key file.
- Read `https://glanote.com/YOUR_SLUG.md` when you want the source, including from a small script. The site also links that form from [llms.txt](https://glanote.com/llms.txt).
- Run `preview` before `publish` if you want to see HTML without creating a page.
- Point an existing Telegraph client at `https://glanote.com/telegraph` and keep using the six methods above.

[How a Markdown file is split into a title and a body](docs/markdown-note.md). [A release script and a manual CI job](docs/automation.md).

## Limits and looking after keys

From the API page, each IP can publish **10 articles and 20 images per hour**. Images are JPG, PNG, WebP, or GIF, up to **5 MB**. Video uploads are not accepted. A YouTube, TikTok, Bilibili, Vimeo, or direct `.mp4` link on its own line may still become a player when the site can do that; that is a help-page behavior, not an upload.

There is no signup and no key recovery. Losing the edit key means you cannot edit or delete the page. The terms also allow Glanote to revoke a key. Do not put a real key in git, an issue, a screenshot, or a query string. This repo's `.gitignore` ignores a few obvious filenames; a key saved inside the checkout still needs you not to commit it. The client warns when the path is inside a git tree and not ignored.

A public article can show up in the sitemap, the RSS feed, and search engines. A view password keeps the article out of the sitemap and search. The service stores a salted hash of that password, not the password itself. Readers need it. The operator can still open the page for moderation.

Deleting a page takes it off the public site immediately. The privacy policy says a record may be kept for abuse handling. To ask for complete erasure, write to contact@glanote.com with the article link. That address is the one published on the [contact page](https://glanote.com/en/contact).

Images uploaded through the API are stored as sent, so embedded metadata can remain. The web editor is described separately and usually re-encodes photos; the API path does not make that claim.

Articles that look like they contain passwords or API keys can be kept out of search. This client will not stop you from publishing a secret by accident.

No parameter is documented for the optional AI summary opt-out, for tags, or for a language field. The clients do not invent those fields.

This repository does not call the article-report endpoint, and it does not send Telegram messages. The API page says a Telegram bot exists in the site's codebase and is not configured.

## Tests

Offline tests build requests, check Unicode JSON, HTTP errors, and that edit keys do not land on stdout:

```bash
make test
```

A live check is off unless you opt in. It creates at most three articles on `POST /api/articles`, then soft-deletes them. It does not upload an image or create a Telegraph page, because those responses have no documented delete:

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```

GitHub Actions runs the offline suite on push and pull request. The live workflow is `workflow_dispatch` only.

## Layout

| Path | What it is |
| --- | --- |
| `python/glanote.py` | Python client, standard library only |
| `javascript/glanote.mjs` | Node client, built-in `fetch` |
| `shell/glanote.sh` | curl client |
| `examples/note.md` | A sample note to edit and publish |
| `docs/markdown-note.md` | Title rule, stdin, passwords, preview |
| `docs/automation.md` | One-shot script and a manual CI job |
| `CONTRIBUTING.md`, `SECURITY.md` | How to change the examples, and how keys are handled |

The license is MIT for the clients, tests, and docs in this repository. It does not license the Glanote service or site content.
