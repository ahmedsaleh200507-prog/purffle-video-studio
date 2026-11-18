# Purffle V3 — gerçek görüntü önce, senaryo ve ses sonra

## Neden bu değişiklik?

Önceki Purffle, LLM senaryosunu ve seslendirmeyi tamamladıktan
sonra sahne videosu arıyordu. "tree roots moist soil" gibi görüntüler
için arama başarısız olduğunda bitmiş seslendirme boşa gidiyordu.

## V3 başlangıç akışı (bu PR)

1. Gerçek video konusu alınır. Daha önce tanımlı, çekilebilir tematik
   görüntü aileleriyle bir arama listesi oluşturulur; ek alternatifler
   için mevcut ücretsiz Groq modeli kullanılır. Rastgele video alınmaz.
2. En az **üç farklı** hareketli klip indirilip aynı StrictVisuals
   mekanizmasında lisans, metadata, kaynak boyutu, duration, duplicate SHA256,
   gerçek hareket ve yerel CLIP eşleşmesinden geçirilir. En fazla dört
   klip seçilir. Bir klip yetmezse önce farklı kaynak ve sorgu denenir.
3. Onaylanmış klip başlıkları, varlıkları, çözünürlükleri ve
   kimlikleri `media-first-plan.json` dosyasına kaydedilir.
4. **Ancak bu adım başarılı olduktan sonra** LLM senaryo yazar.
   Prompt doğrulanmış sahneleri listeler. Normalize aşaması, LLM'nin
   önermiş olduğu farklı stok sorgularını reddederek gerçek klip planını
   kilitler. Narration gerçek bilgilerle konuyu anlatır; klipler birebir
   olay kaydı olarak gösterilmez.
5. Edge/Piper seslendirmesi, altyazılar ve mevcut Remotion/FFmpeg
   altyapısı çalışır. Yukarıdaki klipler tekrar aranmadan mevcut
   `Studio.produce(media_map=...)` yoluyla MP4'e dönüştürülür.
6. Son MP4 yine 720×1280 ve ses/altyazı/lisans/scene-count
   denetimlerinden geçer. `YouTube_Title.txt` ve toplu
   `YOUTUBE_SHORTS_TITLES.txt` oluşturulur.

## Hata davranışı

Üç doğrulanmış ve farklı klip bulunamazsa `media_preflight`
aşamasında **erken** hata verilir: doğru olmayan görüntüyle video
üretilmez, **seslendirme üretimine henüz başlanmaz**.
`media-first-plan.json` ve `footage-report.json` hata sebebini
belgeler. Önceki sürümdeki gibi görüntüleri ancak sonunda aramak yerine
bu test daha erken yapılır.

## Parametreler

- `PURFFLE_MEDIA_FIRST=1` varsayılan; `0` eski iş akışını geri açar.
- `MEDIA_FIRST_REPORT` paket içindeki görüntü kanıtı manifestidir.
- `MEDIA_FIRST_WORK_DIR` geçici katalog arama klasörüdür.
- Her klip 10 saniyelik sahneye göre doğrulanır.
- Önceki tek ZIP, 10 bağımsız görev, en fazla iki paralel görev,
  gerçeğe uygun B-roll ve minimum 720p kuralları korunur.

## Henüz çözülmemiş sınırlar

Bu **V3 altyapısının ilk uygulanmış aşamasıdır**, tamamlanmış yüzde yüz
başarı garantisi değildir. İndekslenen **API yanıtları** GitHub
Actions önbelleğinde tutulabilir fakat runner'lar geçici olduğundan
videonun ham dosyaları bütün çalışmalar arasında kalıcı değildir.
Yeni bir konuda yeterli lisanslı video olmayabilir.
Klipleri önceden doğrulamak da seslendirme süresinin sonradan klibi
aşmasını tamamen engellemez. Film kalitesi için renk/kurgu sürekliliği,
sahne-içi anlam doğrulaması, kalıcı kaynak kütüphanesi ve genel bilimsel
kaynak doğrulaması sonraki aşamalarda geliştirilmeli.

**Testler** `tests/test_media_first.py`, eski tüm regresyonlar ve
Actions CI. E2E üretim başarı yüzdesi gerçek video üretilmeden
kanıtlanamaz.
