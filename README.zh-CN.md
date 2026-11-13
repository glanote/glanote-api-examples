[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Glanote API 示例

不用注册账号，也可以把一篇 Markdown 发出去，拿回一个公开链接。这里是 [Glanote](https://glanote.com/zh-cn) 文章接口的 Python、Node 和 curl 客户端，请求格式以 [接口说明](https://glanote.com/zh-cn/api) 为准。编辑密钥怎么保存，写在 [隐私政策](https://glanote.com/zh-cn/privacy) 里。

发布成功时，响应里有公开的 `url`，还有一把 `edit_key`。服务端只存这把钥匙的哈希，丢了就找不回来，这篇文章以后也不能再改、再删。

完整说明、命令表和 Telegraph 子集见 [英文 README](README.md)。下面的命令在三个客户端里是一样的。

## 先读一篇，再决定要不要发

文档里的示例文章是 `f6a0b2`，读它不会发布新内容：

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

发布会生成一篇公开文章，并计入每 IP 每小时 10 篇的限制。先改好 `examples/note.md`。标准输出只有公开链接，编辑密钥写进权限为 `0600` 的新文件：

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

删除时要同时给出密钥和 `--yes`：

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` 是公开链接最后那一截短码。不带 `--save-key` 或 `--show-key` 时，客户端会故意丢掉密钥。再发一次只会得到另一篇文章。

Shell 脚本需要 Bash、curl 和 `python3`（只用来处理 JSON）。Node 要 18 或更新，Python 要 3.9 或更新。

## 密钥和限制

- 每 IP 每小时 10 篇文章、20 张图片。图片只接受 JPG、PNG、WebP、GIF，最大 5 MB。视频文件不能上传。
- `--show-key` 把密钥打到标准错误，终端回滚和 CI 日志都可能留下它。更稳妥的是 `--save-key`。
- 修改和删除都必须带密钥，并且加上 `--yes`。阅读密码不是编辑密钥。
- 公开文章可能进入站点地图、RSS 和搜索引擎。设了阅读密码的文章不会进入这些列表。
- 删除后，公开页面会马上消失。服务方可能为处理滥用保留一份隐藏副本。要彻底删除，把文章链接寄到 contact@glanote.com。
- 通过 API 上传的图片按原文件保存，其他网站可能因为防盗链而无法直接显示。
- 本仓库不调用举报接口，也不发送 Telegram 消息。

离线测试是 `make test`。真的对线上发测试文章时，最多 3 篇，而且必须手动打开：

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
