[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Glanote API 예제

계정을 만들지 않고 Markdown을 올려 공개 링크를 받을 수 있습니다. 이 저장소는 [Glanote](https://glanote.com/ko) 글 API용 Python, Node, curl 클라이언트입니다. 요청 형식은 [API 문서](https://glanote.com/ko/api)를 따릅니다. 편집 키를 어떻게 다루는지 포함한 데이터 설명은 [개인정보 처리방침](https://glanote.com/ko/privacy)에 있습니다.

게시 응답에는 공개 `url`과 그 글의 `edit_key`가 있습니다. 서버는 키의 해시만 저장하므로, 잃어버린 키는 다시 받을 수 없습니다.

명령 표와 Telegraph 여섯 메서드는 [영어 README](README.md)에 있습니다. 세 클라이언트의 인자는 같습니다.

## 먼저 읽어 보기

문서의 예시 글 `f6a0b2`를 읽는 것은 새 글을 올리지 않습니다.

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

게시하면 공개 페이지가 생기고, IP당 시간당 10편 제한에 포함됩니다. `examples/note.md`를 먼저 고치세요. 표준 출력은 공개 URL만입니다. 편집 키는 모드 `0600`인 새 파일에 저장됩니다.

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

지울 때는 키와 `--yes`가 둘 다 필요합니다.

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG`는 공개 링크 끝의 짧은 코드입니다. `--save-key`나 `--show-key` 없이 게시하면 클라이언트는 키를 버립니다. 다시 게시하면 다른 글이 됩니다.

셸 스크립트에는 Bash, curl, JSON용 `python3`가 필요합니다. Node는 18 이상, Python은 3.9 이상입니다.

## 키와 제한

- 이미지는 시간당 20장까지입니다. JPG, PNG, WebP, GIF, 최대 5 MB. 동영상 파일은 받지 않습니다.
- `--show-key`는 키를 표준 오류로 출력합니다. 터미널 기록과 CI 로그에 남을 수 있습니다. 남기려면 `--save-key`를 쓰세요.
- 수정과 삭제에는 키와 `--yes`가 필요합니다. 열람 비밀번호는 편집 키가 아닙니다.
- 공개 글은 사이트맵, RSS, 검색에 나올 수 있습니다. 열람 비밀번호가 있는 글은 그 목록에서 빠집니다.
- 삭제하면 공개 페이지는 바로 사라집니다. 남용 대응을 위해 숨은 사본이 남을 수 있습니다. 완전 삭제는 글 링크와 함께 contact@glanote.com 으로 요청합니다.
- API로 올린 이미지는 보낸 그대로 저장됩니다. 다른 사이트에서는 핫링크 차단 때문에 보이지 않을 수 있습니다.
- 이 저장소는 신고 엔드포인트와 Telegram 전송을 호출하지 않습니다.

오프라인 테스트는 `make test`입니다. 실제 서비스에 테스트 글을 만들 때는 최대 3편이며, 직접 켜야 합니다.

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
