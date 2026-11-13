[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Exemples pour l'API Glanote

On peut publier du Markdown et recevoir un lien public sans créer de compte. Ce dépôt contient des clients Python, Node et curl pour l'API d'articles de [Glanote](https://glanote.com/fr). Les requêtes suivent la [documentation](https://glanote.com/fr/api). Le sort de la clé d'édition est décrit dans la [politique de confidentialité](https://glanote.com/fr/privacy).

La réponse contient une `url` publique et une `edit_key`. Le service n'en garde qu'un hash. Une clé perdue ne se récupère pas, et la page ne pourra plus être modifiée ni retirée.

Le tableau des commandes et le sous-ensemble Telegraph sont dans le [README anglais](README.md). Les trois clients prennent les mêmes arguments.

## Lire d'abord

L'article d'exemple de la documentation est `f6a0b2`. Le lire ne publie rien :

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

Publier crée une page publique et compte dans la limite de 10 articles par IP et par heure. Modifiez `examples/note.md` avant. La sortie standard est seulement l'URL. La clé va dans un fichier nouveau, mode `0600` :

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

La suppression demande la clé et `--yes` :

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` est le code court à la fin du lien. Sans `--save-key` ni `--show-key`, le client jette la clé. Publier à nouveau crée une autre page.

Le script shell a besoin de Bash, de curl et de `python3` (uniquement pour le JSON). Node 18 ou plus, Python 3.9 ou plus.

## Clés et limites

- 20 images par IP et par heure. JPG, PNG, WebP ou GIF, 5 Mo maximum. Les fichiers vidéo sont refusés.
- `--show-key` écrit la clé sur la sortie d'erreur. Elle peut rester dans l'historique du terminal ou dans un journal de CI. Préférez `--save-key`.
- Modifier et supprimer exigent la clé et `--yes`. Le mot de passe de lecture n'est pas la clé d'édition.
- Un article public peut apparaître dans le sitemap, le flux RSS et les moteurs de recherche. Avec un mot de passe de lecture, il en est exclu.
- Après suppression, la page publique disparaît tout de suite. Une copie cachée peut être conservée pour traiter un abus. Pour un effacement complet, écrivez à contact@glanote.com avec le lien.
- Les images envoyées par l'API sont stockées telles quelles. La protection contre le hotlinking peut empêcher leur affichage sur un autre site.
- Ce dépôt n'appelle pas l'endpoint de signalement et n'envoie pas de messages Telegram.

Les tests hors ligne : `make test`. Le contrôle en ligne crée au plus 3 articles et doit être demandé :

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
