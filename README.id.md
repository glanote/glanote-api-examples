[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# Contoh API Glanote

Markdown bisa diterbitkan tanpa membuat akun, lalu Anda mendapat tautan publik. Repositori ini berisi klien Python, Node, dan curl untuk API artikel [Glanote](https://glanote.com/id). Bentuk permintaannya mengikuti [dokumentasi](https://glanote.com/id/api). Cara kunci suntingan disimpan ada di [kebijakan privasi](https://glanote.com/id/privacy).

Respons penerbitan berisi `url` publik dan `edit_key`. Layanan hanya menyimpan hash kunci itu. Kunci yang hilang tidak bisa dipulihkan, dan halaman itu tidak bisa diubah atau dihapus lagi.

Tabel perintah dan enam metode Telegraph ada di [README bahasa Inggris](README.md). Ketiga klien memakai argumen yang sama.

## Mulai dengan membaca

Artikel contoh di dokumentasi adalah `f6a0b2`. Membacanya tidak menerbitkan apa pun:

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

Menerbitkan membuat halaman publik dan dihitung dalam batas 10 artikel per IP per jam. Sunting `examples/note.md` lebih dulu. Keluaran standar hanya URL publik. Kunci suntingan masuk ke berkas baru dengan mode `0600`:

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

Menghapus butuh kunci dan `--yes`:

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` adalah kode pendek di ujung tautan. Tanpa `--save-key` atau `--show-key`, klien sengaja membuang kunci. Menerbitkan lagi membuat halaman lain.

Skrip shell butuh Bash, curl, dan `python3` (hanya untuk JSON). Node 18 atau lebih baru, Python 3.9 atau lebih baru.

## Kunci dan batas

- 20 gambar per IP per jam. JPG, PNG, WebP, atau GIF, paling besar 5 MB. Berkas video tidak diterima.
- `--show-key` menulis kunci ke keluaran galat. Kunci itu bisa tertinggal di guliran terminal atau log CI. `--save-key` lebih aman.
- Menyunting dan menghapus butuh kunci serta `--yes`. Kata sandi baca bukan kunci suntingan.
- Artikel publik bisa muncul di peta situs, RSS, dan mesin pencari. Artikel berkatasandi baca tidak masuk daftar itu.
- Setelah dihapus, halaman publik langsung hilang. Salinan tersembunyi bisa disimpan untuk menangani penyalahgunaan. Untuk penghapusan penuh, kirim tautannya ke contact@glanote.com.
- Gambar yang diunggah lewat API disimpan apa adanya. Perlindungan hotlink bisa membuatnya tidak tampil di situs lain.
- Repositori ini tidak memanggil endpoint laporan dan tidak mengirim pesan Telegram.

Uji luring: `make test`. Uji langsung membuat paling banyak 3 artikel dan harus diminta secara eksplisit:

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
