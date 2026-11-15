# Purffle Video Studio — 10 Video

GitHub Actions üzerinde çalışan ücretsiz kota sınırlı toplu video üretim sistemi.

## İlk kurulum (bir defa)
1. [Actions secrets](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/settings/secrets/actions) sayfasında **New repository secret** ile iki gizli anahtar ekle: `GROQ_API_KEY` ve `PIXABAY_API_KEY`. Bunları kod dosyasına veya mesajlara yazma.
2. [10 Video Üret](https://github.com/ahmedsaleh200507-prog/purffle-video-studio/actions/workflows/videos.yml) sayfasına git. **Run workflow** düğmesine bas.
3. 1–10 alanlarına ayrı konular yaz. İngilizce için `en|Why is the sky blue?`, Almanca için `de|Warum ist der Himmel blau?`. Boş bıraktığın satırlar atlanır.
4. **Run workflow** ile başlat. GitHub sunucusu çalışmayı sürdürebilir; telefon açık olmak zorunda değildir.
5. İş tamamlanınca workflow çalışmasının **Artifacts** bölümündeki `purffle-videos-...` ZIP dosyasını indir. İçinde ayrı MP4 dosyaları ve durum raporu bulunur.

## Hız ve sınırlar
- 10 konu tek seferde başlatılır, işler **sırayla** üretilir (aynı anda 10 video render edilmez).
- Varsayılan hedef 25 saniye, 540×960, 24 FPS, ücretsiz Edge seslendirme, Pixabay görüntüleri ve altyazı.
- Her video için 12 dakika zaman aşımı var; takılan video atlanıp sıradakine geçilir. Başarısız video otomatik başarı sayılmaz.
- Ücretsiz GitHub Actions kullanım kotası, servis politikaları, API kotaları ve geçici hatalar geçerlidir. Üretim hızı garanti edilmez.
- GitHub Actions arka planda çalışır ancak **kalıcı bir sunucu değildir**. İş tamamlanınca çıktıları 7 gün saklarız.
- İlk sürümün GitHub Actions üzerinde uçtan uca üretim testi henüz yapılmadı.
