[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Ejemplos de la API de Glanote

Puedes publicar Markdown y recibir un enlace público sin crear una cuenta. Este repositorio tiene clientes en Python, Node y curl para la API de artículos de [Glanote](https://glanote.com/es). Las peticiones siguen la [documentación](https://glanote.com/es/api). Qué se guarda de la clave de edición está en la [política de privacidad](https://glanote.com/es/privacy).

La respuesta de publicación trae una `url` pública y una `edit_key`. El servicio solo guarda un hash de esa clave. Si la pierdes, no se puede recuperar y esa página no se podrá editar ni borrar.

La tabla completa de comandos y el subconjunto Telegraph están en el [README en inglés](README.md). Los tres clientes usan los mismos argumentos.

## Empieza leyendo

El artículo de ejemplo de la documentación es `f6a0b2`. Leerlo no publica nada:

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

Publicar sí crea una página pública y cuenta para el límite de 10 artículos por IP y hora. Edita `examples/note.md` antes. La salida estándar es solo la URL. La clave queda en un archivo nuevo con modo `0600`:

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

Para borrarla hacen falta la clave y `--yes`:

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` es el código corto al final del enlace. Si publicas sin `--save-key` ni `--show-key`, el cliente descarta la clave a propósito. Publicar otra vez crea una página distinta.

El script de shell necesita Bash, curl y `python3` (solo para el JSON). Node 18 o posterior, y Python 3.9 o posterior.

## Claves y límites

- 20 imágenes por IP y hora. JPG, PNG, WebP o GIF, hasta 5 MB. No se aceptan archivos de vídeo.
- `--show-key` escribe la clave en la salida de error. Puede quedar en el scrollback o en un registro de CI. `--save-key` es la opción más segura.
- Editar y borrar exigen la clave y `--yes`. La contraseña de lectura no es la clave de edición.
- Un artículo público puede aparecer en el mapa del sitio, en el RSS y en buscadores. Con contraseña de lectura, no entra en esas listas.
- Al borrar, la página pública desaparece enseguida. Puede quedar una copia oculta para tratar abusos. Para pedir el borrado completo, escribe a contact@glanote.com con el enlace.
- Las imágenes subidas por la API se guardan tal cual. En otros sitios, la protección contra hotlinking puede impedir que se vean.
- Este repositorio no llama al endpoint de denuncias ni envía mensajes de Telegram.

Las pruebas sin red son `make test`. La prueba en vivo crea como mucho 3 artículos y hay que pedirla:

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
