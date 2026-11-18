# Purffle V3 — Sabit Erkek Anlatıcı

## Kullanıcının referans videosu

Kullanıcının 47 saniyelik, 512×910 çözünürlüklü dış MP4 dosyası
erkek anlatım tarzı için **referanstır**. Dosyada ses üretim modelinin
kimliğini veren metadata bulunmamaktadır. Bu değişiklik, o sesin
birebir klonu/aynı kişi olduğunu iddia etmez.

## Otomatik, ücret gerektirmeyen sabit ses

GitHub Actions üretiminde `PURFFLE_NARRATOR_LOCK=1`:

- İngilizce bütün Shorts: **Piper en_US-joe-medium**, tek, erkek anlatıcı
- Almanca bütün Shorts: **Piper de_DE-thorsten-medium**, tek, erkek anlatıcı
- Edge/Azure çevrim içi TTS yok; kadın LJSpeech'e otomatik geçiş yok
- Yerel model başarısız olursa sessiz veya farklı sesli MP4 yayımlanmaz;
  `voice-report.json` ile açık hata kaydedilir
- WAV sesli, doğrulanmış kelime eşlemeli; normal video ses/altyazı/MP4
  kontrolleri devam eder
- Pinned `en_US-joe-medium` ONNX SHA256:
  `abf4b998e34045cbd00eaf050de2de620f81ded6eb8b85a24b022a1c2b3f08d2`
- Sabit model revizyonu:
  `0ca208afc2a2ee102b1e961e72e0a7e4907be3d0`
- Piper Joe'nun güncel **rdh CC0 tabanlı** sürümü seçildi; eski
  lessac üzerine eğitilmiş Joe varyantı kullanılmıyor.
- Kaynak: https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/joe/medium
- Lisans: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/joe/medium/MODEL_CARD
- Pinned erkek sesi model dosyası indirirken hash ile doğrulanır.
  Küçük JSON/Model Card yardımcı dosyaları da aynı değişmez repo
  revizyonundan alınarak yapı/lisans bakımından doğrulanır.

## Geriye dönük uyumluluk

Diğer test ve eski iş akışları `PURFFLE_NARRATOR_LOCK=0`
ayarına sahiptir. Yeni GitHub video workflow'u varsayılan olarak
erkek kilidi ile çalışır. Eski sonuç ZIP'leri değiştirilmez.

## Sınırlar

Kullanıcının MP4'ündeki sesin gerçek adı veya hangi platformda
üretildiği video metadata'sından saptanamadı; bu yüzden *aynı*
orijinal sesin birebir eşlenmesi doğrulanmış değildir.
Kullanıcının ses sahibinden aldığı açık izin ve referans model
bulunmadan üçüncü taraf videodan otomatik ses klonlama yapılmaz.
Kilitli TTS, sabit erkek sesinin kullanılmasını sağlar; bir
sesi dinleyip birebir eşleştirdiği iddiası yoktur.

Gerçek GitHub Actions işinde modelin indirildiği ve
WAV+MP4 üretiminin başarılı olduğu ilk canlı çalışmayla
ayrıca doğrulanmalıdır. CI sahte konuşma nesneleriyle
ses kimliği ve güvenli çıkış sözleşmesini test eder.
