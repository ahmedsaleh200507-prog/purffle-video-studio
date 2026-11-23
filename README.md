# Purffle Video Studio V4

Mevcut Purffle ve sabitlenmiş `purffle-shorts` motoru üzerinde: konu → denetlenmiş senaryo → gerçek görüntü arama/doğrulama → sabit Piper sesi → zamanlı altyazı → render → çıktı kontrolü. Ücretli üretim API'si veya otomatik yayın yoktur.

## Kullanım

- [Shorts — 1–10 konu](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/workflows/videos.yml): `en|What Happens When Lava Hits the Ocean?` veya `de|Warum beschlägt der Badezimmerspiegel?`. 1080×1920, 9:16, 30 FPS.
- [Uzun video — 1–10 konu](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/workflows/long-batch.yml): İngilizce/Almanca, 14 bölüm, 9–11 dakika, 1920×1080, 30 FPS. Uzun video akışı deneysel; her konuda gerçek stok kapsamı garanti edilmez. Altyazıları zamanlı `captions.srt` olarak teslim eder; MP4'e yakmaz.

`INPUT_1`–`INPUT_10` korunur. Her konu bağımsız job; kota için aynı anda bir üretim. `fail-fast: false`: hata diğer konuları iptal etmez. Başarılı MP4'ler ve başarısızlık raporları Artifacts'ta 7 gün tutulur. Kısmi MP4 başarı sayılmaz. Shorts worker süresi 25 dakika, runner kurulum dahil 65 dakika; uzun runner sınırı 330 dakika. GitHub hesabının ücretsiz dakika/depolama sınırları geçerlidir.

## Video üretimi ve uzun belgesel kalite şartı

**Shorts (9:16):** Normal stok görüntülü üretim başarısız olursa ücretsiz,
çevrimdışı 2D açıklama videosu oluşturulabilir. Bu alternatif gerçek stok
çekim içermez ve teknik olarak oynatılabilir MP4 olması yayın kalitesini
garantilemez.

**Uzun video (16:9):** Gerçek 9–11 dakikalık belgesel ancak kapsamlı,
tekrarsız 14 bölüm ve en az 1200 konuşulan kelime, yeterince çeşitli
konuyla eşleşen gerçek video klipleri ve uzun ses sessizlikleri bulunmadan
**başarılı** sayılır. Hata olursa mevcut tamamlanmış gerçek görüntülü bölümler
`PARTIAL_REAL_CHAPTERS.mp4` adıyla korunabilir. Hiç içerik bulunamadıysa
başarılı video üretilmiş gibi gösterilmez.

Eski 2D yedek sistem 7 cümleyi tekrarlayıp her bölümü sessizlikle 43
saniyeye doldurarak sahte bir 10 dakikalık video çıkarıyordu; bu yol
**kapatıldı**. Kullanıcı örneğindeki gerçek hareketli görüntülü ve sürekli
anlatımlı belgesel hedeflenir, ancak kaynak/API/runner erişimi yoksa %100
başarı garanti edilemez.

## Görüntü eşleştirme

Her sahnenin konusu, nesnesi, eylemi, ortamı ve her anlatım cümlesi raporlanır. İngilizce sorgular ve sınırlı Almanca görsel sözlük desteklenir; bilinmeyen kelimelerde senaristin İngilizce görsel planı kullanılır. Tam çeviri modeli değildir.

Kaynaklar en fazla dört ağ isteği paralelliğiyle taranır. Önce kesin sorgu tüm kaynaklarda denenir; sonra alternatif eylem/nesne/ortam sorguları denenir. HTTP çağrıları kaynak başına hız sınırı, metadata cache, kota devre kesicisi ve sahne süresiyle sınırlıdır. İndirme, FFprobe ve CLIP incelemesi CPU/RAM için sırayla yapılır. Aynı gereksinim için reddedilmiş klip alias aramasında yeniden indirilmez.

Hafif CPU metadata elemesi nesne kapsamını ve bilinen çelişkileri inceler. Son karar ayrıca lisans, gerçek çözünürlük, süre, hareket ve kullanılan karelerde CPU CLIP gerektirir. **Metadata tek başına görsel doğrulama değildir.** CLIP yüklenemezse ilgisiz stokla devam edilmez. Çok cümleli sahnelerde sonraki cümlenin görünür eylemi de denetlenir. Lav–buz etkileşimi için her iki öznenin kaynak metadata'sında bulunması ve özel kare karşılaştırması gerekir.

`match.suitability` uygunluk indeksini, gerekçeleri ve güvenilirlik sınırını kaydeder. Bu indeks olasılık veya ölçülmüş doğruluk değildir; CLIP nedensellik/kimlik/tüm kısa eylemleri ispatlamaz. Düşük uygunluklu aday mevcut bağımsız eşiklerde reddedilir, sonraki aday/sorgu/kaynak denenir. Seçenekler tükenirse açık hata oluşur. Her konuda otomatik sahne yeniden yazımı uygulanmaz; ilgisiz görüntüyle boşluk doldurulmaz.

Kaynak kısa kenarı en az 720 px. Dikey kırpmanın gerçek ölçeği raporlanır, en fazla 1,20× büyütme kabul edilir. Full HD çıktı, kaynağın native Full HD olduğu anlamına gelmez. 1080p yatay klipler 9:16 Full HD kırpmada sıklıkla yetersizdir; native dikey veya 4K stok gerekir. Bu tercih bulunabilirliği azaltır. Aynı video içinde kaynak ID/URL/SHA256 tekrarı engellenir; ayrı runner'lar arasında ortak tekrar geçmişi yoktur.

## Ses ve kalite kontrolü

Yalnız `en_US-joe-medium` (rdh tabanlı CC0 checkpoint) ve `de_DE-thorsten-medium` (CC0) Piper kullanılır. Model revision/hash denetimi ve yerel fonem örneklerinden kelime hizalaması korunur. Ses başarısızsa başka kimliğe geçilmez. Eski özel İngilizce referans araçları geçmiş artefaktlar için depodadır; aktif üretim bunları çağırmaz ve özel kayıt Secret'ını gerektirmez.

FFprobe, boyut/FPS/ses/süre, kaynak hareket/CLIP ve ilk saniyelerin kalite kontrolüne ek olarak **tüm çıktı** decode edilir: siyah sahne ≥0,45 saniye, sessizlik ≥2,5 saniye, altyazı sınırları/sırası/kapsamı ve ses toplam süresi denetlenir. `output-qa.json` teknik sonucu kaydeder. Bunlar ASR veya bilimsel doğruluk kanıtı değildir. Shorts ekranında logo veya Purffle başlığı yoktur.

## Secrets ve kaynak durumu

`GROQ_API_KEY` / `GEMINI_API_KEY` mevcut ücretsiz kotalı senaryo servisleri içindir. Stok Secrets: `PIXABAY_API_KEY`, `PEXELS_API_KEY`, `NPS_API_KEY`, `EUROPEANA_API_KEY`, `COVERR_API_KEY` (yoksa `COVER2`). Eksik/geçersiz/kotası dolmuş kaynak diğerlerini durdurmaz. Anahtar değerleri rapora yazılmaz.

Wikimedia, NASA, Internet Archive, USGS ve Free Nature Stock anahtarsız adaptörlere sahiptir. Coverr resmi ücretsiz API adaptörü vardır; indirme sayımı PATCH isteği zorunludur. Vecteezy ücretsiz lisans/atıf koşulları nedeniyle kapalıdır. Shorts `PURFFLE_NO_ATTRIBUTION=1` ile atıf gerektiren varlıkları filtreler. Lisansın API'de listelenmesi tüm üçüncü kişi haklarını garanti etmez.

**Güncel ve kapsamı belirtilmiş kaynak/test sonuçları:** [V4 doğrulama ve lisans raporu](docs/V4_AUDIT.md). Yapılandırılmış kaynak, erişimi doğrulanmış kaynak ve indirilen/doğrulanmış klip ayrı durumlardır.

## Geliştirme

Python 3.12, FFmpeg/FFprobe, `pip install -r requirements-dev.txt`, ayrıca `torch==2.6.0+cpu` (resmi PyTorch CPU index). `python -m pytest -q` ve `python -m compileall -q scripts sitecustomize.py` çalıştırılır. Ağsız mock testler canlı API/üretim kanıtı değildir; sentetik FFmpeg dosyaları yalnız test fixture'ıdır.

Upstream commit `514fd2547227b98d951dfc1489fc8c7ce72f1b68` ve runtime SHA denetimi korunur. OpenMontage AGPL-3.0 kaynakları mimari inceleme içindir; kod veya bağımlılık kopyalanmadı. Eski `docs/` raporları tarihlerindeki durumu anlatır; V4 için bu README ve V4 raporu esas alınır.
