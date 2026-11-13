[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Exemplos da API Glanote

Dá para publicar Markdown e receber um link público sem criar uma conta. Este repositório tem clientes em Python, Node e curl para a API de artigos do [Glanote](https://glanote.com/pt). Os pedidos seguem a [documentação](https://glanote.com/pt/api). O que acontece com a chave de edição está na [política de privacidade](https://glanote.com/pt/privacy).

A resposta traz uma `url` pública e uma `edit_key`. O serviço guarda só um hash. A chave perdida não volta, e a página deixa de poder ser editada ou apagada.

A tabela de comandos e o subconjunto Telegraph estão no [README em inglês](README.md). Os três clientes usam os mesmos argumentos.

## Comece pela leitura

O artigo de exemplo da documentação é `f6a0b2`. Lê-lo não publica nada:

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

Publicar cria uma página pública e conta no limite de 10 artigos por IP por hora. Edite `examples/note.md` antes. A saída padrão é só o URL. A chave fica num ficheiro novo, modo `0600`:

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

Apagar pede a chave e `--yes`:

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` é o código curto no fim do link. Sem `--save-key` nem `--show-key`, o cliente descarta a chave. Publicar de novo cria outra página.

O script de shell precisa de Bash, curl e `python3` (só para o JSON). Node 18 ou mais recente, Python 3.9 ou mais recente.

## Chaves e limites

- 20 imagens por IP por hora. JPG, PNG, WebP ou GIF, até 5 MB. Ficheiros de vídeo não são aceites.
- `--show-key` escreve a chave no erro padrão. Ela pode ficar no scrollback ou num log de CI. `--save-key` é a opção mais segura.
- Editar e apagar exigem a chave e `--yes`. A senha de leitura não é a chave de edição.
- Um artigo público pode aparecer no sitemap, no RSS e nos motores de busca. Com senha de leitura, fica de fora dessas listas.
- Depois de apagar, a página pública some logo. Uma cópia oculta pode ficar para tratar abuso. Para apagamento completo, escreva a contact@glanote.com com o link.
- Imagens enviadas pela API são guardadas como chegaram. A proteção contra hotlink pode impedir que apareçam noutro site.
- Este repositório não chama o endpoint de denúncia nem envia mensagens no Telegram.

Testes offline: `make test`. O teste ao vivo cria no máximo 3 artigos e tem de ser pedido:

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
