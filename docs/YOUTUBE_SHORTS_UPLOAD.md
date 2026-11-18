# YouTube Shorts başlıkları — Purffle

**Otomatik. Manuel başlık yazmaya gerek yok.**

Her **başarılı, doğrulanmış** MP4 üretiminden sonra aynı video klasöründe
`YouTube_Title.txt` oluşturulur. Bu tek satırlık İngilizce/Almanca
başlığı YouTube Shorts yükleme ekranının **Title / Başlık** alanına
kopyalayabilirsin. Videonun kendisine yazı eklenmez.

Ayrıca ZIP'in ana dizininde `YOUTUBE_SHORTS_TITLES.txt` bulunur;
bu dosya tamamlanan videoları **VIDEO 01**, **VIDEO 02** ... olarak
numaralandırır, her başlıkla doğru MP4 yolunu eşleştirir.

Başarısız videoların başlığı yanlışlıkla yayın listesine yazılmaz.

## Örnek klasör

```text
purffle-videos-123.zip
├── YOUTUBE_SHORTS_TITLES.txt
└── finished/
    └── video_01/
        └── render/
            └── <video-adi>/
                ├── <video>.mp4
                └── YouTube_Title.txt
```

Mevcut `GROQ_API_KEY` ile konuya uygun, merak uyandıran bir başlık
oluşturulması denenir. Servis kota veya ağ nedeniyle yanıt vermezse
**video başarısız olmaz**; doğru konudan yola çıkan basit başlık
otomatik hazırlanır. İstersen `PURFFLE_SHORTS_TITLE_AI=0` ile
bu ek AI başlık isteğini tamamen kapatabilirsin.

Bu özellik Shorts'a otomatik video yüklemez ve YouTube hesabına
bağlantı gerektirmez.
