[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [العربية](README.ar.md) · [Bahasa Indonesia](README.id.md)

# أمثلة واجهة Glanote

يمكن نشر Markdown والحصول على رابط عام من غير حساب. هذا المستودع يضم عملاء Python وNode وcurl لواجهة المقالات في [Glanote](https://glanote.com/ar). شكل الطلبات يطابق [توثيق الواجهة](https://glanote.com/ar/api). ما يُحفظ من مفتاح التعديل موضح في [سياسة الخصوصية](https://glanote.com/ar/privacy).

رد النشر فيه `url` عام و`edit_key`. الخدمة تحتفظ بتجزئة المفتاح فقط. إذا ضاع المفتاح فلا يُسترجع، ولا يعود تعديل الصفحة أو حذفها ممكنًا.

جدول الأوامر ومجموعة Telegraph من ستة نداءات في [README الإنجليزي](README.md). الأوامر نفسها في العملاء الثلاثة.

## ابدأ بالقراءة

المقال الذي تستخدمه الوثائق مثالًا هو `f6a0b2`. قراءته لا تنشر شيئًا:

```bash
python3 python/glanote.py read f6a0b2
node javascript/glanote.mjs read f6a0b2
./shell/glanote.sh read f6a0b2
```

النشر ينشئ صفحة عامة ويُحتسب ضمن حد 10 مقالات لكل عنوان IP في الساعة. عدّل `examples/note.md` أولًا. المخرج القياسي هو الرابط العام فقط. مفتاح التعديل يُكتب في ملف جديد بصلاحية `0600`:

```bash
python3 python/glanote.py publish --file examples/note.md --save-key "$HOME/.glanote-edit-key.json"
```

الحذف يحتاج المفتاح و`--yes` معًا:

```bash
python3 python/glanote.py delete YOUR_SLUG --edit-key-file "$HOME/.glanote-edit-key.json" --yes
```

`YOUR_SLUG` هو الرمز القصير في آخر الرابط. من غير `--save-key` أو `--show-key` يتجاهل العميل المفتاح عمدًا. النشر مرة أخرى ينشئ صفحة مختلفة.

سكربت الصدفة يحتاج Bash وcurl و`python3` (لترميز JSON فقط). Node 18 أو أحدث، وPython 3.9 أو أحدث.

## المفاتيح والحدود

- 20 صورة لكل عنوان IP في الساعة. JPG أو PNG أو WebP أو GIF، حتى 5 ميغابايت. ملفات الفيديو غير مقبولة.
- `--show-key` يطبع المفتاح على مخرج الخطأ. قد يبقى في سجل الطرفية أو في سجل CI. `--save-key` أسلم.
- التعديل والحذف يطلبان المفتاح و`--yes`. كلمة مرور المشاهدة ليست مفتاح التعديل.
- المقال العام قد يظهر في خريطة الموقع وRSS ومحركات البحث. المقال المحمي بكلمة مرور يُستبعد من هذه القوائم.
- بعد الحذف تختفي الصفحة العامة فورًا. قد تُحفظ نسخة مخفية لمعالجة الإساءة. للمحو الكامل راسل contact@glanote.com مع رابط المقال.
- الصور المرفوعة عبر الواجهة تُخزَّن كما أُرسلت. الحماية من الربط المباشر قد تمنع ظهورها في موقع آخر.
- هذا المستودع لا يستدعي مسار الإبلاغ ولا يرسل رسائل Telegram.

الاختبارات من غير شبكة: `make test`. الفحص الحي ينشئ 3 مقالات على الأكثر ويجب طلبه صراحة:

```bash
GLANOTE_LIVE=1 python3 tests/live_opt_in.py --confirm-live
```
