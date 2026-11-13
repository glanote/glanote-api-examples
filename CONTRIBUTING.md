# Contributing

These are example clients for the public Glanote API. They are not the website and not the server.

Run the offline tests before sending a change:

```bash
make test
```

`GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live` publishes up to three real articles and deletes them. Do not run it from CI on every push, and do not point it at someone else's article. It only deletes slugs it just created.

Keep the three clients on the same flags: `python/glanote.py`, `javascript/glanote.mjs`, and `shell/glanote.sh`. If a call is not on [the API page](https://glanote.com/en/api), do not add it. In particular, do not add the article-report endpoint, a Telegram sender, or a tool that publishes a directory of files.

Translations in `README.*.md` stay shorter than the English README. Commands and flag names stay in English so they can be copied. Link the localized site, API, and privacy pages, and link back to `README.md`.

Do not commit edit keys, Telegraph access tokens, view passwords, or files produced by `--save-key`. If a test needs a secret, use an obvious fake value and assert that it does not appear on stdout.
