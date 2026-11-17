# Purffle Video Studio — toplu kök neden / düzeltme raporu

## Kanıt ve kapsam (2026-11-17)

Kullanıcının sağladığı görev özetine göre 10 videonun 4'ü (1, 4, 7, 10) başarılı,
6'sı (2, 3, 5, 6, 8, 9) başarısız olmuştur. Bu sayı **ham Actions logları veya
PURFFLE_DIAGNOSTICS.txt incelenerek bağımsız doğrulanmış değildir**; eklenen
dosya bir Codex görev özeti, ham tanı çıktısı değildir.

Kaynak kodunda doğrulanan hata: `StrictVisuals.for_scenes()` retry sırasında
hem `failed` hem `selected` kayıtlarını `report.scenes` içinde tutuyordu.
Ayrıca önceki klibin tekrar kullanımı için `thematic_broll` durumu
oluşturuluyordu. `render_job.validate_result()` ise **her** kaydın `selected`
olmasını zorunlu kılıyordu. Dolayısıyla doğrulanmış bir sahneyle biten retry
bile `Not every scene has verified moving footage` hatası üretebiliyordu.
Bu kod-seviyesi mekanizma doğrulanmıştır; altı hatanın her birinin kök nedeni
henüz ayrı ayrı kanıtlanmış değildir.

## Bu dalda uygulanan düzeltmeler

1. Yeniden denemelerde her mantıksal sahne için tek bir **nihai**
   `selected` kaydı bırakılır. Önceki başarısız denemeler
   `search_attempts` altında korunur.
2. Başka sahnenin aynı videosunu semantik doğrulama olmadan tekrarlayan
   `thematic_broll` kestirmesi kaldırılır; o sahne için yeni, lisanslı,
   hareketli görüntü bulunamazsa dürüst ve açık hata verilir.
3. Kaynak kısa kenarının 720px olması artık tek başına yeterli sayılmaz.
   9:16 kırpma sonrası yerel piksel sayısı `720x1280` için yetersizse
   seçim ve render reddedilir. Örneğin 1920x1080 yatay videonun
   yaklaşık 608x1080 doğal dikey kırpması **yerel 720p değildir**.
4. Çıktı doğrulaması nihai sahnelerin sırasını, kaynak/provenance
   alanlarını, benzersiz dosya hash'lerini ve yerel kırpma kalitesini denetler.
5. `Worker exited with status 1` altındaki `job-result.json`
   hata mesajı, aşama, exception tipi, sahne, sağlayıcı ve ret nedenleri
   toplu rapora taşınır. `unknown` sınıflandırmasının hatalı sebeplerinden
   biri olan kısa üst hata metni önceliği giderilir.
6. `PURFFLE_DIAGNOSTICS.json` eklendi. `PURFFLE_DIAGNOSTICS.txt`
   ile aynı GitHub Actions artifact'ine dahil edilir. Bilinen
   API anahtarı ortam değişkenleri dosya yazımında maskelenir.
7. Önceden tamamlanan aynı girdi, aynı çıktı çözünürlüğü,
   ses/video stream'leri ve pozitif süreyle yeniden `ffprobe`
   doğrulanabiliyorsa yerel dosya üzerinden resume yapılır.
   Yeni bir GitHub Actions çalışması başka bir runner'da başlarsa
   önceki çıktı otomatik taşınmaz.
8. Sahne retry, yinelenen video, 9:16 upscale, tanı sınıflandırma,
   JSON redaksiyonu ve sesli MP4 raporu için regresyon testleri eklendi.

## Sağlayıcı denetimi

| Sağlayıcı | Kaynak kodundaki durum | Canlı erişim |
| --- | --- | --- |
| Pixabay | `PIXABAY_API_KEY` gerekir | Bu değişiklik sırasında test edilmedi |
| Pexels | `PEXELS_API_KEY` gerekir | Kullanıcı özetine göre anahtar eksik; canlı test yok |
| Wikimedia | Açık video kaynağı | Bu değişiklik sırasında test edilmedi |
| NASA | Açık medya kaynağı, lisans/uygunluk filtresi var | Bu değişiklik sırasında test edilmedi |
| Internet Archive | Açık arşiv kaynağı, lisans filtresi var | Bu değişiklik sırasında test edilmedi |
| Europeana | `EUROPEANA_API_KEY` gerekir | Kullanıcı özetine göre anahtar eksik; canlı test yok |
| Coverr | Üretim API kullanım izni doğrulanmadığı için engelli | Bilerek etkinleştirilmedi |

`scripts/provider_health.py` mevcut ve GitHub Actions üzerinden sınırlı
sağlayıcı denemesi yapar. Gerçek sonuçlar `finished/provider-health.json`
dosyasında görülür. Bu dosyada yeni bir gerçek API testi yapılmış sayılmaz.

## Testler ve doğrulama durumu

- Kaynağı incelemek ve kod düzeltmelerini commit etmek: **uygulandı**.
- `python -m compileall -q scripts sitecustomize.py`: **henüz koşulmadı**.
- `python -m pytest -q`: **henüz koşulmadı**.
- Canlı kaynak API testleri: **henüz koşulmadı**.
- Gerçek 10 video yeniden üretimi: **henüz koşulmadı**.
- Önceki 4 başarılı videoda regresyon yokluğu: **henüz doğrulanmadı**.

Test komutları:

```bash
python -m compileall -q scripts sitecustomize.py
python -m pytest -q
python scripts/provider_health.py
# GitHub Actions workflow_dispatch ile aynı 10 başlıkla üretim testi
```

**Önemli:** Yerel 720p kırpma kontrolü daha sıkı olduğundan, mevcut 1080p
yatay klipler daha sık elenebilir; bunlar otomatik upscale ile başarılı
gösterilmez. Gerçek üretim başarı oranı yalnızca yeni bir Actions koşusuyla
bilinebilir. Kaynağın bulunamaması, doğrulanamaması veya lisans sorunu
dürüstçe başarısızlık olarak raporlanır; baştan sona tüm problemlerin
çözüldüğü iddia edilmez.

## Beklenen tanılar

GitHub Actions artifact içeriğinde:
- `PURFFLE_DIAGNOSTICS.txt`: okunabilir toplu rapor
- `PURFFLE_DIAGNOSTICS.json`: yapılandırılmış rapor
- `finished/video_XX/footage-report.json`: sahne ve kaynak reddi
- `finished/video_XX/voice-report.json`: ses denemeleri
- `finished/provider-health.json`: sağlayıcı sağlık yoklaması

**Sonraki kanıt adımı:** Aynı 10 başlıkla yeni `workflow_dispatch` çalıştırıp
özellikle başarısız video 2, 3, 5, 6, 8, 9'un yeni tanı kayıtlarını,
başarılı videoların ses/süre/çözünürlük çıktılarını karşılaştırmak.
