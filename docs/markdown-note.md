# Publishing a Markdown note

[Back to the English README](../README.md). The commands below are the same in `python/glanote.py`, `javascript/glanote.mjs`, and `shell/glanote.sh`.

## Title and body

`publish` and `edit` call `POST` and `PUT /api/articles`. Those calls take a `title` and Markdown `content`. If you pass `--title`, the file or stdin is the body. If you do not, the first `# heading` is the title and the lines under it are the body. A file that is only a heading is rejected locally, because the body would be empty.

```bash
python3 python/glanote.py publish --save-key "$HOME/.glanote-edit-key.json" <<'EOF'
# Water test

The sample from the north tap was clearer than last week.
EOF
```

`/api/new` is a different call. `new --text` sends one form field, and the service uses the first line as the title. `new --file` uploads the file as the `file` field. `new --title --text --image` is the third form on the API page. The clients do not mix those forms.

## See the HTML first

`preview` posts `{"content": "..."}` to `/api/preview` and prints the body it gets back. The docs say that body is rendered HTML. Nothing is published.

```bash
python3 python/glanote.py preview --file examples/note.md > /tmp/preview.html
```

## Who can read it

Without a view password, the page is public. It can appear in the sitemap, the RSS feed, and search. Add a password only when you mean to:

```bash
python3 python/glanote.py publish \
  --file examples/note.md \
  --view-password-file "$HOME/.glanote-view-password" \
  --save-key "$HOME/.glanote-edit-key.json"
```

The password file can be one line, or JSON with a `view_password` field. Readers send it back as the `X-View-Password` header:

```bash
python3 python/glanote.py read YOUR_SLUG --view-password-file "$HOME/.glanote-view-password"
```

The password is not the edit key. You still need the key file to change or delete the page. Password-protected articles are left out of the sitemap and search. The operator can open them for moderation.

## Images

```bash
python3 python/glanote.py image photo.png
```

Use the Markdown the server returns inside an article. The upload limit is 5 MB, and the types are JPG, PNG, WebP, and GIF. The API stores the file as sent, so camera metadata can remain. Hotlink protection can stop the image from loading on another site.

## After it is up

Keep the key file. Mode `0600` means your user can read it and other accounts on the machine cannot. There is no recovery form. Delete with:

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

That removes the public page. A hidden copy may be kept for abuse handling. The contact address for a full erasure request is contact@glanote.com, as published on [the contact page](https://glanote.com/en/contact).
