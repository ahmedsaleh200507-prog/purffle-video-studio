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

## Doğrudan incelenen toplu tanılar (iki kullanıcı ZIP dosyası, 2026-11-18)

Bu bölüm önceki görev özetinin tersine gerçek üretim raporlarından çıkarılmıştır:
`PURFFLE_DIAGNOSTICS.json` ile `PURFFLE_DIAGNOSTICS.txt` aynı koşuya aittir.
`summary`: **10 istendi, 2 başarılı, 8 başarısız**. Başarılı video **3 ve 9**.
10 videonun **tamamında Edge TTS başarılı** (`voice.state=ready`).
Başarısız videolarda `RuntimeError: No suitable verified REAL VIDEO for scene N`
hatası bulunur. Bu koşuda görüntü kaynağı arama ve metadata eylem/nesne
uyumsuzluğu ana engeldir; `provider_rate_limit` etiketleri **yanlış pozitif**
çıkmıştır: kayıtlarda birçok `pixabay:ok` ve başka sonuçlar vardır,
başarısız sahnelerin büyük çoğunluğu
`Scene metadata lacks object/action grounding` veya
`Scene metadata does not describe the requested action` nedeniyle elenmiştir.

| Video | Sonuç | Somut başarısız sahne | Bulgular |
|---|---|---|---|
| 1 Bermuda | FAILED | 2, `naval planes departing port` | Çok özel tarihî uçak/eylem, metadata eşleşmedi |
| 2 Mağara | FAILED | 1, `deep cave exploration` | Eylem ve mağara meta verisi uyumsuz, bazı kaynaklar 720p altında |
| 3 Deniz altı şelale | OK | 5 doğrulanmış sahne | Pixabay / Edge TTS |
| 4 Mariana | FAILED | 3, `sonar light algae` | Algae/sonar görüntüsünün eylem/nesne tanımı çok dar |
| 5 Etiyopya | FAILED | 1, `harar national park` | Gerçek yeri kanıtlanmamış spesifik ad, meta eşleşmedi |
| 6 Göl gazı | FAILED | 2, `lake bottom sediment` | Tortu görünümü anlatılırken çekimde bulunmayan eylem aranıyor |
| 7 Çöl daireleri | FAILED | 1, `sand dunes circle` | 'Kumullar daire oluşturuyor' eylemi istenmiş, 1920x1080 kırpma da reddedilmiş |
| 8 Deniz parıltısı | FAILED | 2, `bioluminescent bacteria` | Bakteriyi görselde arama ve eylem metadata uyuşmazlığı |
| 9 Tunguska | OK | 5 doğrulanmış sahne | Pixabay / Edge TTS |
| 10 Kırmızı şelale | FAILED | 1, `glacier meltwater waterfall` | Buzul erime suyu eylem/nesne metadata uyuşmazlığı |

Bu kanıta dayanarak `contextual_scene_plans` eklendi. Önce birebir
eşleşen görüntüyü arar. Başarısızsa yalnızca tanımlanmış, **konuya
ilişkili** doğal manzara/tematik video alternatiflerini arar; özel
olayların gerçek kaydı olduklarını iddia etmez. Başarı halinde
`visual_mode=illustrative_context` ve
`illustrative_not_exact_event=true` şeklinde ayrı işaretlenir.
Görüntü her durumda lisans, yerel CLIP, hareket, benzersizlik, süre ve
dikey 720p doğal kırpma kontrollerini geçmelidir.

Kök-neden sınıflandırması artık asıl `No suitable verified REAL VIDEO`
hatada `provider_rate_limit` gibi önceki önemsiz kaynak olaylarına
bakmaz; başarısız sahnenin gerçek ret nedenlerini sayar.

**Gerçek üretim başarı garantisi yoktur:** Bu yeni değişiklikler ile aynı
10 videoluk batch **henüz yeniden üretilmemiştir**. Yeni tanı ZIP'i
alındığında başarı sayısı ve semantik uygunluk tekrar karşılaştırılmalıdır.


## Yeni onarım: cümle-birebir yerine konuya uygun B-roll (2026-11-18)

Kullanıcının paylaştığı `PURFFLE_CODEX_ONARIM_PAKETI(1).zip` içindeki
gerçek üretim tanıları: **10 deneme, 0 başarılı MP4, 10 hazır seslendirme**.
940 ret olayının **833'ü metadata eşleştirmesi**, 95'i native çözünürlük
nedeniyle. Bunlar **ret olaylarıdır**, tekil dosya sayısı değildir.
Yüksek sayıda reddin ana nedeni, stok videolarda indekslenmeyen aşırı dar
sahne/eylem sorguları (ör. `pressure gauge underwater`,
`dinoflagellate plankton light`, `spiral pine tree`).

Artık `thematic_scene_plans`, doğrulanmış tam sahne görüntüsü bulunamazsa
konu başlığına dayalı **görülebilir, gerçek, ilgili** alternatifler dener.
10 hata konusu için deniz, doğal gaz alevi/çöl, Antarktika buzu, yılanlar,
gece okyanusu, mağara, volkan, orman, deniz dibi ve Sibirya ormanı gibi
konuya özel ve denetlenebilir örnekler vardır. İlgisi kurulamayacak yeni
bir konu için rastgele görüntü kullanılmaz.

Başarılı tematik klip **`visual_mode=thematic_context`** ve
**`illustrative_not_exact_event=true`** ile işaretlenir; bu klibin
olayın özgün kaydı olduğu **iddia edilmez**. Metadata, lisans,
hareket, FPS/süre, kaynak dosyası ve yerel 9:16 720p boyut denetimi
değiştirilmemiştir. CLIP görsel doğrulaması da zorunlu olmaya devam eder.
Sadece, karakter içermeyen ve konusu bilinen `ambient` tematik
sahnelerde eylemin stok etiketinde birebir yazması artık şart değildir.
Görüntüdeki **nesnenin** metadata'da bulunması hâlâ şarttır.

`tests/test_thematic_broll.py`: 10 konuyu, gerçekten ilgili nesne eşleşmesini,
rastgele videonun reddini, tematik rapor kaydını ve başarısız üretimin yanlış
başarılı sayılmamasını test eder.

**Sınır:** Bu, gerçek klip erişimi olmadan 10/10 başarı kanıtı değildir.
Canlı üretim/YouTube Shorts testinden sonra kaç MP4 çıktığı ayrıca ölçülmelidir.
