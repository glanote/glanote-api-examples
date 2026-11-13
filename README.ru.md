[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Примеры API Glanote

Markdown можно опубликовать без учётной записи и получить короткую публичную ссылку. В этом репозитории клиенты на Python, Node и curl для API статей [Glanote](https://glanote.com/ru). Запросы совпадают с [документацией](https://glanote.com/ru/api). Как хранится ключ правки, описано в [политике конфиденциальности](https://glanote.com/ru/privacy).

В ответе есть публичный `url` и `edit_key`. Сервис хранит только хеш ключа. Потерянный ключ не восстановить, и страницу уже нельзя изменить или удалить.

Полная таблица команд и шесть методов Telegraph — в [английском README](README.md). У трёх клиентов одни и те же аргументы.

## Сначала чтение

В документации примером служит статья `f6a0b2`. Чтение ничего не публикует:

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

Публикация создаёт открытую страницу и учитывается в лимите 10 статей на IP в час. Сначала поправьте `examples/note.md`. На стандартный вывод попадает только URL. Ключ записывается в новый файл с правами `0600`:

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

Для удаления нужны и ключ, и `--yes`:

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` — короткий код в конце ссылки. Без `--save-key` и `--show-key` клиент специально выбрасывает ключ. Повторная публикация создаёт другую страницу.

Скрипту на shell нужны Bash, curl и `python3` (только для JSON). Node 18 или новее, Python 3.9 или новее.

## Ключи и ограничения

- 20 изображений на IP в час. JPG, PNG, WebP или GIF, до 5 МБ. Видеофайлы не принимаются.
- `--show-key` печатает ключ в stderr. Он может остаться в прокрутке терминала или в логе CI. Надёжнее `--save-key`.
- Правка и удаление требуют ключ и `--yes`. Пароль на просмотр — не ключ правки.
- Открытая статья может попасть в карту сайта, RSS и поиск. С паролем на просмотр она туда не попадает.
- После удаления публичная страница исчезает сразу. Скрытая копия может остаться для разбора жалоб. Полное удаление: contact@glanote.com и ссылка на статью.
- Картинки, загруженные через API, сохраняются как есть. Из-за защиты от хотлинка они могут не открываться на другом сайте.
- Этот репозиторий не вызывает endpoint жалоб и не отправляет сообщения в Telegram.

Офлайн-тесты: `make test`. Живая проверка создаёт не больше 3 статей и запускается только явно:

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
