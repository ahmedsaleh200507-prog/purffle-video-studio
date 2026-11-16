# Purffle Video Studio V2

Konu → senaryo → yapılandırılmış sahneler → lisanslı gerçek video araması → dosya ve sahne doğrulama → Almanca/İngilizce seslendirme → senkron altyazılı **1080×1920 MP4**.

[Actions: 1–10 video üret](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/workflows/videos.yml). `video_1` alanına `en|Ocean waves breaking on a rocky coast` veya `de|Ozeanwellen an einer felsigen Küste` yazıp **Run workflow** seçilir. Diğer dokuz alan isteğe bağlıdır. Ön ek yoksa İngilizce kullanılır. Kod, manuel görüntü arama/yükleme/indirme gerekmez. Çıktılar çalışmanın **Artifacts** bölümünde 7 gün saklanır.

## Ücretsiz erişim ve anahtarlar

Ücretli üretim API'si kullanılmaz. Senaryo için ücretsiz kota kapsamında `GROQ_API_KEY` gerekir. Stok için `PIXABAY_API_KEY` ve `PEXELS_API_KEY`, Europeana için `EUROPEANA_API_KEY` isteğe bağlıdır. Anahtarlar yalnız **GitHub Actions Secrets** üzerinden ortam değişkenlerine aktarılır; anahtarı eksik kaynak atlanır. Wikimedia, NASA ve Internet Archive anahtarsız çalışabilir. Yerelde Secrets değerlerini okumak veya dışa aktarmak gerekmez. Coverr ücretsiz üretim erişimi netleşene kadar anahtar bulunsa da engellidir.

GitHub standart Linux runner, Edge TTS, ücretsiz yerel Piper ses yedeği ve CPU CLIP kullanılır; kota/süre/hizmet erişilebilirliği sınırlıdır. Ücretsiz kota biterse iş hata verir; ücretli sağlayıcıya geçmez. Anahtar oluşturma veya ücretli plan kaydı otomatik yapılmaz.

## Kabul politikası

- Altı resmî API bağdaştırıcısı: Pixabay, Pexels, Wikimedia Commons, NASA, Internet Archive, Europeana. [29 kaynak araştırması ve resmî belgeler](docs/SOURCE_RESEARCH_V2.md).
- Her sahne karakter, nesne, eylem, mekân, zaman ve İngilizce görsel sorgusu taşır. Genel konuya genişletme ve rastgele stok yedeği yoktur.
- Metadata nesne/eylem kontrolü ve örnek karelerde yerel CLIP doğrulaması zorunludur. Model yüklenemezse sahne kabul edilmez. Model; aynı kişinin kimliğini, tam para kupürünü veya tüm eylem ayrıntılarını kesin ispatlayamaz. Bu sınırlama raporda bulunur; kaynaklarla birebir anlatım her konuda garanti edilmez.
- FFprobe gerçek boyut/FPS/süre/codec ölçer; kaynak kısa kenarı en az1080 olmalıdır. Siyah/boş/hareketsiz dosyalar ve kısa klip döngüsü reddedilir. Yatay1080p'nin dikey kırpılması büyütme gerektirebilir; `portrait_crop_scale` ve `upscaled_after_crop` bunu açıkça bildirir. Native1080p dikey veya4K kaynak tercih edilir.
- Fotoğraflar, gradyanlar, yapay2D yedekler ve açıkça animasyon/simülasyon olarak işaretlenen içerikler reddedilir. Kazıma veya toplu katalog indirmesi yoktur. Bilinmeyen lisanslar, CC BY-SA/NC/ND kabul edilmez. CC BY için yaratıcı/lisans/kaynak/değişiklik atfı artefakta dahil edilir; videoyu yayımlarken bu atıf da birlikte verilmelidir.
- Ses önce Edge üzerinden üretilir; erişim başarısızsa onaylanmış yerel Piper modelleri kullanılır (İngilizce public domain, Almanca CC0). Yalnız native veya gerçek fonem örneklerinden hizalanmış kelime zamanları kabul edilir. [Model lisansları ve ölçülmüş ses testleri](docs/LOCAL_VOICE_OPTIONS.md). Sessiz ya da tahminî zamanlamalı çıktı başarı sayılmaz.

## İşletim ve raporlar

Videolar sırayla işlenir. Her video en fazla25 dakika; hatalı video sonraki konuyu engellemez. Bir video bile başarısızsa iş akışı başarısız sonuçlanır; başarılı MP4'ler ve tüm hata raporları yine yüklenir. Bulunan kısmiMP4 dosyası başarı kanıtı değildir.

Her `finished/video_XX/` klasöründe `report.json`, `job-result.json`, `footage-report.json`, `voice-report.json`, `purffle.log`; başarılı üretimde ayrıca `render/.../short.mp4`, `script.json`, `metadata.json`, `captions.srt` bulunur. Raporlar kaynak URL'sini, SHA256'yı, lisans atfını, gerçek çözünürlüğü, hareket/uygunluk puanını ve reddetme nedenlerini içerir. `batch-results.json` toplu durumdur. Ses raporu denenen motoru, başarısızlıkları, kullanılan yerel modelin hash/lisansını ve zamanlama yöntemini kaydeder. Ses aşamasında başarısızlık gibi henüz kaynak aranmamış durumlarda footage raporu oluşmayabilir.

API yanıtları24 saat önbelleklenir; kota reddinde kaynak o video için devreden çıkar. İndirmeler HTTPS, boyut/zaman/özel-IP denetimi ve SHA256 ile sınırlıdır. Aynı çalışmadaki sahneler/videolar arasında kaynak anahtarı, URL ve içerik karmasıyla tekrar önlenir. Runner geçicidir; farklı Actions çalışmaları arasında tüm klip geçmişi saklanmaz. Render işleri temizlenir; indirilen klipler artefakta eklenmez.

Upstream [514fd254](https://github.com/Chamanrajragu/purffle-shorts/commit/514fd2547227b98d951dfc1489fc8c7ce72f1b68) sürümüne sabitlenmiştir. Runtime uyumluluğu SHA256 ile doğrulanır; bilinmeyen upstream sessizce yamalanmaz. İş akışında syntax, mock/API hata, lisans, medya, sahne ve toplu durum testleri çalışır.

Yerel geliştirici testleri: `pip install -r requirements-dev.txt`, CPU PyTorch (`torch==2.6.0+cpu`, resmî PyTorch CPU index), FFmpeg/FFprobe ardından `python -m pytest -q`. Bu testlerdeki sentetik dosyalar yalnız olumsuz kalite/render testleridir; gerçek kaynak veya uçtan uca üretim kanıtı değildir. [Doğrulama kaydı](docs/VALIDATION_V2.md).
