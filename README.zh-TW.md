[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Glanote API 範例

不必註冊帳號，就能把一篇 Markdown 發出去，拿回一個公開連結。這裡是 [Glanote](https://glanote.com/zh-tw) 文章介面的 Python、Node 與 curl 用戶端，請求格式以 [介面說明](https://glanote.com/zh-tw/api) 為準。編輯金鑰如何保存，寫在 [隱私權政策](https://glanote.com/zh-tw/privacy)。

發布成功時，回應裡有公開的 `url`，以及一把 `edit_key`。服務端只留這把鑰匙的雜湊，弄丟了就無法再改、再刪這篇文章。

完整說明、指令表和 Telegraph 子集見 [英文 README](README.md)。下面的指令在三個用戶端裡相同。

## 先讀一篇，再決定要不要發

文件中的範例文章是 `f6a0b2`，讀取不會發布新內容：

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

發布會產生一篇公開文章，並計入每 IP 每小時 10 篇的上限。請先改 `examples/note.md`。標準輸出只有公開連結，編輯金鑰寫進權限為 `0600` 的新檔案：

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

刪除時要同時給金鑰和 `--yes`：

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` 是公開連結末尾的短碼。若發布時沒有 `--save-key` 或 `--show-key`，用戶端會故意丟掉金鑰。再發一次只會得到另一篇文章。

Shell 腳本需要 Bash、curl 和 `python3`（只用來處理 JSON）。Node 需 18 以上，Python 需 3.9 以上。

## 金鑰與限制

- 每 IP 每小時 10 篇文章、20 張圖片。圖片只接受 JPG、PNG、WebP、GIF，最大 5 MB。不能上傳影片檔。
- `--show-key` 會把金鑰印到標準錯誤，終端機回捲和 CI 日誌都可能留下它。較穩妥的是 `--save-key`。
- 修改和刪除都必須帶金鑰，並且加上 `--yes`。閱讀密碼不是編輯金鑰。
- 公開文章可能進入網站地圖、RSS 和搜尋引擎。設了閱讀密碼的文章不會進入這些清單。
- 刪除後，公開頁面會立刻消失。服務方可能為了處理濫用而保留一份隱藏副本。若要徹底刪除，請把文章連結寄到 contact@glanote.com。
- 經 API 上傳的圖片會照原檔保存，其他網站可能因為防盜鏈而無法直接顯示。
- 這個儲存庫不呼叫檢舉介面，也不傳送 Telegram 訊息。

離線測試是 `make test`。若要對正式環境發測試文章，最多 3 篇，而且必須手動打開：

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
