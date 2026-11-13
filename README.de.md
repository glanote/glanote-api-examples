[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Beispiele für die Glanote-API

Markdown lässt sich ohne Konto veröffentlichen. Zurück kommt ein öffentlicher Link. Dieses Repository enthält Python-, Node- und curl-Clients für die Artikel-API von [Glanote](https://glanote.com/de). Die Aufrufe entsprechen der [Dokumentation](https://glanote.com/de/api). Was mit dem Bearbeitungsschlüssel geschieht, steht in der [Datenschutzerklärung](https://glanote.com/de/privacy).

Die Antwort enthält eine öffentliche `url` und einen `edit_key`. Der Dienst speichert nur einen Hash. Ein verlorener Schlüssel kommt nicht zurück, und die Seite lässt sich dann nicht mehr ändern oder löschen.

Die Befehlstabelle und die sechs Telegraph-Methoden stehen in der [englischen README](README.md). Alle drei Clients nutzen dieselben Argumente.

## Zuerst lesen

Der Beispielartikel in der Dokumentation heißt `f6a0b2`. Ihn zu lesen veröffentlicht nichts:

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

Veröffentlichen legt eine öffentliche Seite an und zählt zum Limit von 10 Artikeln pro IP und Stunde. `examples/note.md` vorher anpassen. Die Standardausgabe ist nur die URL. Der Schlüssel landet in einer neuen Datei mit Modus `0600`:

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

Zum Löschen braucht es den Schlüssel und `--yes`:

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` ist der kurze Code am Ende des Links. Ohne `--save-key` oder `--show-key` verwirft der Client den Schlüssel. Ein erneutes Veröffentlichen erzeugt eine andere Seite.

Das Shell-Skript braucht Bash, curl und `python3` (nur für JSON). Node 18 oder neuer, Python 3.9 oder neuer.

## Schlüssel und Grenzen

- 20 Bilder pro IP und Stunde. JPG, PNG, WebP oder GIF, höchstens 5 MB. Videodateien werden nicht angenommen.
- `--show-key` schreibt den Schlüssel auf die Fehlerausgabe. Er kann in der Terminal-Historie oder in CI-Logs landen. `--save-key` ist die ruhigere Variante.
- Ändern und Löschen verlangen den Schlüssel und `--yes`. Ein Lesepasswort ist kein Bearbeitungsschlüssel.
- Ein öffentlicher Artikel kann in der Sitemap, im RSS-Feed und in Suchmaschinen erscheinen. Mit Lesepasswort fehlt er dort.
- Nach dem Löschen ist die öffentliche Seite sofort weg. Eine versteckte Kopie kann für die Missbrauchsbehandlung bleiben. Für eine vollständige Löschung: contact@glanote.com, mit dem Link.
- Über die API hochgeladene Bilder werden so gespeichert, wie sie ankommen. Hotlink-Schutz kann sie auf anderen Websites unsichtbar machen.
- Dieses Repository ruft weder die Melde-Schnittstelle auf noch sendet es Telegram-Nachrichten.

Offline-Tests: `make test`. Der Live-Lauf legt höchstens 3 Artikel an und muss ausdrücklich gestartet werden:

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
