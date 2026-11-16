# V2 doğrulama kaydı

Tarih: 2026-11-16 UTC. Başlangıç depo: `9f943e73254179ac6bb40d24e2bcffd15c379306`.

## İncelenen geçmiş

[Önceki Actions çalışması43776014445](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/runs/43776014445), commit `d294e155`: `create-videos` job133002373183 günlükleri bağlantı üzerinden okundu. de/en para hikâyesi için iki `ok` sonucu mevcut; ortam `RESOLUTION=540x960`. Bu eski başarı durumları görüntü uygunluğu/gerçek1080p kanıtı değildir. Artefakt videoları bu incelemede izlenmedi.

Kod bulguları: NASA seçicisi `~small`/`~mobile` tercih ediyor ve ölçmeden1280×720 iddia ediyordu; seçici metadata eşiği25%'e düşürülmüştü; “scene-only” yaması gerçekte aynı sorgu dizisini bırakıyordu. Anahtarsız `topic_footage` yolu yapay2D sahneler ve döngüler üretiyordu; CC lisans kontrolünü de atlıyordu. batch araMP4 bulunca başarısız işlem durumunu `ok` yapabiliyordu. Workflow değişkenupstream `main` yüklüyor ve kısa ses zaman aşımıyla sağlıklı işleri kesebiliyordu.

## Kanıt düzeyleri

- [Araştırma:29 kaynak](SOURCE_RESEARCH_V2.md); [resmî kamuAPI denemeleri](source-probes-research.json), [stokAPI yetkisiz denemeler](stock-probes.json).
- [Üretim bağdaştırıcı gerçekAPI testleri](provider-live-tests.json): NASA, Wikimedia ve Internet Archive veri döndürdü. Bu sayım dosya/kalite/MP4 başarısı değildir. Pixabay/Pexels/Europeana anahtarları yerelde yok; atlandı. Coverr izin nedeniyle engelli.
- Yerel CPU CLIP (`openai/clip-vit-base-patch32`) ağırlıkları resmî model dağıtımından yüklendi. Model yükleme başarısı semantik doğruluk kanıtı değildir.
- Otomatik testler: Python syntax, pinnedupstream uyumu, bağımsız mockJSON yanıtları, eksik anahtarlar, boş sonuç, HTTP403/404/429/500, HTTP200 içindekiAPI hatası, lisans/atıf, gerçekFFprobe/FFmpeg ile düşükçözünürlük/statik/siyah dosya reddi, indirme boyut/redirect/özelIP/kesikdosya, sahne nesne/eylem/CLIP hataları, toplu işte hata devamlılığı ve işakışı sözleşmesi.
- Testlerde kullanılan lavfi/sentetik dosyalar yalnız yazılım doğrulamasıdır; kullanıcının gerçekgörüntü kuralını karşılayan üretim olarak sayılmaz.

GitHub Actions yeni çalışma ve gerçekMP4 sonucu, çalıştırma tamamlandığında aşağıya kaydedilecek. Test edilmemiş anahtarlı bir kaynak veya uçtanuca akış bu kayıtla “çalışıyor” ilan edilmez.

## Gerçek yerel görsel testi

[visual-live-test.json](visual-live-test.json): Wikimedia PDM-1.0 gerçekdosya66.1MB indirildi; FFprobe1920×1080,VP8,29.97FPS,45.045s. YerelCLIP doğru balık-yüzme sorgusunu0.291 benzerlikle kabul etti; yanıltıcı uygunmetadata verilmesine rağmen aynı videoyu eurobulma sahnesi için0.205 ile reddetti. Yataykaynak dikeykırpma sonrası1.7778× büyütme gerektirir; rapor bu durumu açıkça ayırır. Bu birsemantik smoke testidir; tam konu→MP4 denemesi değildir.

## Actions ilk V2 denemesi

[43936028564](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/runs/43936028564), commit368de7e: gerçekGitHub runner kurulumu,regresyonlar,modelyükleme veupstreamkontrolü geçti. Üretimdeki sesbeklemesi incelenirken edge-tts7.3.1 `stream_sync` hatailetiminde deadlock bulundu: işçiparçacığı hatada kuyruğa sonlandırma işareti yazmıyor, `queue.get()` sonsuza dek bekleyebiliyor. Yerelde aynıbelirti gözlendi. Harcanan süreyi sınırlamak için ilkdeneme iptaledildi; bu deneme başarılıMP4 olarak sayılmaz. Güvenli doğrudanasync sesadaptörü ve süre sınırıyla düzeltme eklendi.
