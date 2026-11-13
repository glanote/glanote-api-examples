[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Glanote API の使用例

アカウントを作らずに Markdown を公開し、短い URL を受け取れます。ここにあるのは [Glanote](https://glanote.com/ja) の記事 API 向け Python、Node、curl クライアントです。リクエストの形は [API ドキュメント](https://glanote.com/ja/api) に合わせています。編集キーの扱いを含むデータの説明は [プライバシーポリシー](https://glanote.com/ja/privacy) にあります。

公開応答には誰でも開ける `url` と、その記事だけの `edit_key` が入ります。サーバが保存するのはキーのハッシュだけなので、無くしたキーは再発行されません。

コマンド一覧と Telegraph の 6 メソッドは [英語版 README](README.md) にまとめてあります。三つのクライアントは同じ引数です。

## まず読む

ドキュメントが例にしている記事 `f6a0b2` は、読むだけでは何も投稿しません。

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

投稿すると公開ページができ、IP ごとに 1 時間 10 本の制限に数えます。`examples/note.md` は先に書き換えてください。標準出力は公開 URL だけです。編集キーはモード `0600` の新しいファイルに入ります。

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

消すときはキーと `--yes` の両方が必要です。

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` は公開リンク末尾の短いコードです。`--save-key` も `--show-key` も付けずに投稿すると、クライアントはキーを捨てます。同じ記事はもう編集できません。もう一度投稿すると別のページになります。

シェルスクリプトには Bash、curl、JSON 用の `python3` が要ります。Node は 18 以降、Python は 3.9 以降です。

## キーと制限

- 画像は 1 時間に 20 枚まで。JPG / PNG / WebP / GIF、5 MB まで。動画ファイルは受け付けません。
- `--show-key` はキーを標準エラーに出します。ターミナルの履歴や CI ログに残ります。残すなら `--save-key` にしてください。
- 編集と削除にはキーと `--yes` が必要です。閲覧パスワードは編集キーではありません。
- 公開記事はサイトマップ、RSS、検索に載ることがあります。閲覧パスワード付きの記事はそこから外れます。
- 削除すると公開ページはすぐ消えます。不正利用への対応のため、非公開の控えが残ることがあります。完全な消去は、記事のリンクを添えて contact@glanote.com へ連絡します。
- API から上げた画像は送ったまま保存されます。他のサイトではホットリンク防止で表示できないことがあります。
- このリポジトリは通報エンドポイントも Telegram 送信も呼び出しません。

オフラインのテストは `make test` です。本番へテスト記事を出す場合は最大 3 本で、明示したときだけ動きます。

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
