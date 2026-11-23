# V4 audit — 2026-11-23

## İncelenen mevcut durum

Başlangıç commit: `c66aae3` (son üretim #94: `7e55e34`). Önceki #57–#59 görüntü düzeltmeleri, mevcut testler ve Shorts/uzun workflow'ları incelendi. Başlangıç testi temiz worktree'de **800 geçti, 9 subtest geçti**. İnceleme başlangıcındaki son gerçek üretim #94 üç istekten birini tamamlamış; İngilizce yıldırım ve aurora işleri görsel ön kontrolde durmuş. Başarı dosyasını var sayan bir toplu rapor hatası görülmedi.

Kaynak: https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/runs/45157102393 (job `137632738813`). Özellikle ilk sağlayıcının altı sorgusu, aynı reddedilen klipler ve sonraki kaynaklara geç ulaşılması görüldü. Konu dışı gökyüzü sorguları ve eski referans ses kurulumu maliyeti de mevcuttu.

## Uygulanan değişiklikler

- `footage_search.py`: aynı anda en fazla dört kaynak; kesin sorgu turu, sonra alias turları; hazır sonuçlar işlenir. Ağ host kilitleri birbirini engellemez. Host hız sınırı, cache, devre kesicisi ve deadline korunur.
- `scene_relevance.py`: CPU sözlük/nesne elemesi; her cümle için ihtiyaç kaydı, sınırlı DE→EN sözlüğü, kaynak metninden kanıt ve kalibre edilmemiş uygunluk indeksi. Lav–buz için çift özne gereksinimi. Eski CLIP kaldırılmadı; metadata başarı kanıtı sayılmaz.
- `visual_director.py`: ikinci/sonraki cümledeki görünür eylemler de ayrı sözleşmelerle kontrol edilir. Aynı klibin tüm cümlelere uygunluğu gerekir; çok cümleli tek klibin cümle içi kesin eylem zamanlaması henüz garanti edilmez.
- `studio_runtime.py`: aynı nesne/eylem/sözleşme için reddedilen aday yeniden indirilmez. Kaynak ID/URL/hash tekrarı kontrolü korunur. Gemini anahtarı da redaksiyona eklendi.
- Kullanıcının V4 talebine göre İngilizce özel referans yerine depodaki önceki **rdh CC0 Joe** checkpoint'i geri getirildi. Joe/Thorsten her çağrıda sabit; Edge/özel referans geçişi yok. Piper model oturumları süreçte önbelleklenir, tam senaryo token kapsamı kontrol edilir. Aktif workflow'lardan Chatterbox/Whisper/Resemblyzer/PyAV kurulumu çıkarıldı. Eski özel ses araçları silinmedi.
- Shorts workflow hedefi 1080×1920; 30 FPS. Kaynak büyütme sınırı gevşetilmedi. Uzun video 1920×1080 ve mevcut 14 bölüm/9–11 dakika korunur.
- `output_qa.py`: tüm timeline decode, 30 FPS, çözünürlük, ses, Piper WAV süresiyle eşleme ve tam senaryo–SRT metin karşılaştırması, siyah ≥0,45s, sessizlik ≥2,5s, SRT sınır/sıra/kapsam kontrolü. Kısa örnekleme yerine tüm çıktı teknik olarak incelenir. ASR doğrulaması değildir.
- INPUT_1–INPUT_10, ayrı durumlar, hata izolasyonu ve artefakt toplama korundu. Uzun video için model cache ve QA rapor artefaktı eklendi.

## Gerçek kaynak denetimi

Aşağıdaki tüm kaynakların depoda adapter kodu vardır. Liste, API'nin her konu için görüntü döndüreceği veya her adayın kullanılabileceği anlamına gelmez. Canlı yerel test `ocean waves` araması + lisans metadata filtresidir; klip indirme/render kanıtı değildir. #94 kayıtları GitHub Secrets kullanılan runner'dan alınmıştır; metadata cache kullanılmış olabileceğinden bunlar yeni HTTP sağlığı kanıtı değildir. V4 sağlık komutu artık cache'i atlar. Secrets değerleri okunmadı/dışa aktarılmadı.

| Kaynak | Anahtar | Gözlenen API durumu | Ücretsiz/lisans ve otomasyon koşulu |
|---|---|---|---|
| Pixabay | PIXABAY_API_KEY | #96 taze HTTP: 60 aday; #95 üç gerçek 4K dosya indirme/render | Resmi API; Content License, hak/marka kısıtları; toplu katalog kopyalama yok, cache/hız sınırı |
| Pexels | PEXELS_API_KEY | #94: eksik; canlı doğrulanamadı | Resmi Video API; ücretsiz kota ve Pexels License; API/publikasyon koşulları geçerli |
| Wikimedia | Yok | Yeni yerel test: 14 aday; #96 taze HTTP: 13 | Resmi MediaWiki API; dosya bazında CC0/PDM/CC BY; BY atfı zorunlu, SA/NC/ND reddedilir |
| NASA | Yok | Yeni test ve #96 taze HTTP: 2 aday | Resmi images API ve asset manifest; NASA media policy, üçüncü taraf kredileri dışlanır |
| Internet Archive | Yok | Yeni test ve #96 taze HTTP: 6 aday | Advanced Search/metadata API; yalnız doğrulanabilir dosya lisansı, her yükleme kamu malı değildir |
| Europeana | EUROPEANA_API_KEY | #94: eksik; canlı doğrulanamadı | Resmi Search API; rights alanı ve doğrudan video URL'si gerekir |
| NPS | NPS_API_KEY | #96 taze HTTP sağlık sorgusu boş; #94 yıldırım aramasında 2–4 aday | Resmi multimedia/videos API; özgün NPS kredili ve hak taramasını geçen HD MP4 |
| USGS | Yok | #96: dört statik aday, iki gerçek 1920×1080 dosya; dikey kırpma yetersiz, iki dosya siyah/boş açılış nedeniyle reddedildi | Genel arama API'si değil, küratörlü USGS ScienceBase kayıtları ve resmi dosyalar; PDM/orijinal kredi doğrulaması |
| Vecteezy | VECTEEZY_API_KEY bağlı | Lisans nedeniyle kapalı; API başarısı iddiası yok | Free atıf zorunluluğu ile mevcut no-attribution politikası uyuşmuyor; ücretli plan kullanılmaz |
| Coverr | COVERR_API_KEY / COVER2 | #96 taze HTTP: boş; yerelde anahtar yok | Resmi ücretsiz API bağlantısı mevcut; indirme sayımı PATCH, en fazla 5 çağrı, atıf gerekiyorsa no-attribution filtresi |
| Free Nature Stock | Yok | 1 statik aday; ayrıca gerçek CC0 MP4 indirme/FFprobe/hareket/CLIP geçti (3840×2160, 15,057s, CLIP 0,3045); uzak API yok | Statik, önceden denetlenmiş CC0 manifest adaptörü; API/HTML/feed çağrısı yapmaz |

Resmi koşul bağlantıları: [Pixabay API](https://pixabay.com/api/docs/), [Pixabay lisans](https://pixabay.com/service/license-summary/), [Pexels API](https://www.pexels.com/api/documentation/), [Pexels lisans](https://www.pexels.com/license/), [Wikimedia reuse](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia), [NASA](https://www.nasa.gov/nasa-brand-center/images-and-media/), [Archive](https://archive.org/about/terms.php), [Europeana](https://pro.europeana.eu/page/apis), [NPS](https://www.nps.gov/subjects/digital/nps-data-api.htm), [USGS](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits), [Coverr](https://coverr.co/license), [Vecteezy](https://www.vecteezy.com/licensing-agreement), [Free Nature Stock](https://freenaturestock.com/).

API istemcisi ücretsiz GitHub Linux runner'da çalışır (#94 kanıtı). Bugünkü her resmi hizmetin koşullarının hukuki incelemesinin tamamlandığı veya gelecekte değişmeyeceği iddia edilmez; mevcut asset allowlist ve katı atıf politikası korundu. Yeni ücretli veya doğrulanmamış entegrasyon açılmadı.

## OpenMontage ve bağımlılık lisansları

https://github.com/OpenMontageInc/OpenMontage içindeki LICENSE, requirements, `lib/clip_embedder.py`, `tools/video/clip_search.py`, `lib/verify_scene_pacing.py` okundu. AGPL-3.0, ağ üzerinden kullanılan türevlerde kaynak paylaşımı yükümlülükleri doğurabilir. Purffle için uyumluluk netleştirilmediğinden **kod/bağımlılık kopyalanmadı**.

Mimari gözlemler: ayrı metadata + görsel skorları, normalize CLIP embeddingleri, klip kayıtlarında kaynak geçmişi, çeşitlilik seçimi, sahne zamanlarının üretim sonrası kontrolü. OpenMontage clip search yerel corpus içindir; internette ücretsiz stok bulma çözümü değildir. Mevcut Purffle CLIP ViT-B/32 ve hash kontrolü üzerine bağımsız küçük modüller eklendi. Yeni medya modeli bağımlılığı yoktur.

Mevcut Piper 1.8 yazılımı GPL-3.0-or-later, ONNX Runtime MIT, Transformers Apache-2.0, PyTorch BSD, CLIP kod/model kartı MIT; ses veri/model lisansları ayrıca kontrol edilir. Joe rdh tabanlı CC0 checkpoint'i `0ca208afc2a2ee102b1e961e72e0a7e4907be3d0`, ONNX SHA256 `abf4b998e34045cbd00eaf050de2de620f81ded6eb8b85a24b022a1c2b3f08d2`; eski lessac tabanlı Joe kullanılmaz. Thorsten model/hash daha önceki sabitlemeyle aynıdır. FFmpeg dağıtımının derleme seçeneklerine göre LGPL/GPL yükümlülükleri olabilir. Bu inceleme bütün bağımlılık ağacının hukuki sertifikasyonu değildir.

## Test ve canlı üretim kanıtı

- Başlangıç: 800 test ve 9 subtest geçti (temiz worktree).
- V4 regresyon: 823 test, 9 subtest geçti; üç Pillow deprecation uyarısı. Sabit Joe/Thorsten isteğiyle çelişen eski reference-only/Edge varsayımları yeni sözleşmeye uyarlandı; eski referans araçlarının kendi birim testleri korundu.
- Yeni paralel kaynak/arıza/deadline, DE sorgu, lav-buz çelişkisi ve sonraki cümle eylemi testleri geçti.
- Gerçek FFmpeg fixture testleri: tüm dosya decode, siyah video, sessiz ses, yanlış FPS, kesilmiş MP4 ve yanlış altyazı zamanları. Sentetik fixture'lar üretim videosu değildir.
- Gerçek Joe: 16 kelime, 5,492s; gerçek Thorsten: 13 kelime, 5,050s. Hash doğrulanmış indirme, ONNX inference, native phoneme timing ve ses sözleşmesi geçti. Bunlar tam stok video üretimi değildir.
- EN/DE Shorts, uzun bölüm/al­t­yazı sözleşmesi, 10 konu hata izolasyonu, eksik anahtar/kapalı kaynak/görüntüsüzlük/bozuk medya mevcut mock regresyonlarında sınanır. 10 gerçek konu ve tam 10 dakikalık V4 video üretimi bu yerel testlerden çıkarılamaz.
- Gerçek #95 denemesi (commit `8e7740a`): İngilizce MP4 1080×1920/30 FPS, 17,2s, üç farklı 4K Pixabay kaynağı ve Joe ile teknik olarak üretildi. İndirilen artefakt son kodun tam SRT/senaryo + Piper süre + decode QA kontrollerinden de geçti (17 cue). **Kare incelemesinde okyanus/gerçek kıyı çökmesi açıkça görünmedi; semantik kabul başarısı sayılmadı.** Lav akışı ailesi daha özel okyanusa giriş gereksinimini bastırıyordu. Bunun üzerine birleşik lav–okyanus ve kıyı çökmesi sözleşmeleri, zorunlu çift metadata grupları ve en az iki destekleyici kare/0,04 margin kuralı eklendi; inland lav/fıskiye negatif regresyonları eklendi. Almanca #95 işi sahne 2 için uygun ikinci klip bulamayınca **başarısız** oldu (1/2 doğrulanmış sahne). Alakasız görüntüye düşmedi. Düzeltilmiş birleşik sözleşmeyle [#96](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/runs/45167354410) (`0553a5c`) tekrarlandı: **1/3 sahne doğrulanabildi, üretim açıkça başarısız oldu; MP4 başarı iddiası yoktur.** Gerçek USGS klipleri 1920×1080 ölçüldü, 1080×1920 dikey kırpmada 1,20× sınırına uymadı. İki USGS dosyası siyah/boş açılış nedeniyle reddedildi. Kıyı çökmesi koşulunu karşılayan yeterli materyal bulunamadı. Eski inland lav/fıskiye görüntüleri bu sahneleri doldurmadı. Bir seferlik branch launcher'ı iki denemeden sonra kaldırıldı. Kod commit `7bcbad3` için Actions [45165717956](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/runs/45165717956) hızlı test ve tam regresyonu geçti. Statik katalog sağlık/cache düzeltmesi `d4af7f7` de [45166326933](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/runs/45166326933) hızlı ve tam Actions regresyonundan geçti; birleşik olay düzeltmesi `0553a5c` de [45167339392](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/runs/45167339392) altında 820 test + 9 subtest ve gerçek Thorsten testiyle geçti. Son teknik red cache/test düzeltmesi yerelde 823 test ile doğrulandı. CI başarısı, gerçek üretim başarısı değildir.

## Kalan sınırlar / kullanıcı işlemi

Pexels ve Europeana kullanılacaksa ilgili ücretsiz API anahtarlarının Secrets'a eklenmesi gerekir; diğer kaynaklar için zorunlu değildir. Yeni ücretli anahtar gerekmez. CLIP uygunluğu kalibre edilmemiş örnekleme sezgisidir; insan görsel denetiminin yerini tamamen tutmaz. Her konuda yeterli lisanslı native dikey/4K stok bulunmayabilir. Otomatik sahne yeniden planlama ve uzun videoda cümle başına kesin eşleme henüz tam değildir. Uzun kliplerin tekrar kullanımı yalnız daha önce oynatılmamış, yeniden doğrulanmış aralıklarla sınırlıdır. Runner'lar arasında ortak görüntü geçmişi yoktur.
