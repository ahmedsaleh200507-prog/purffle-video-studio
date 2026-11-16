# Ücretsiz yerel ses: doğrulanan Piper yolu

Tarih:2026-11-16 UTC. Edge TTS erişilemezse ağsız yerel sinirsel ses ve gerçek zamanlama için Piper1.8.0 araştırıldı ve çalıştırıldı. Ücretli API, anahtar, kredi kartı veya Whisper modeli gerekmez.

## Resmî API ve lisanslar

- [Piper resmî proje](https://github.com/OHF-Voice/piper1-gpl): yerel CPU sentezi; yazılım GPL-3.0-or-later.
- [Resmî alignment API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/ALIGNMENTS.md): modelin fonem kimliği başına ürettiği gerçek ses örneği sayıları açılabilir. `piper-tts[alignment]==1.8.0` ONNX paketini içerir; model bellekte yamalanır, diskteki orijinal değiştirilmez.
- [Ses modeli deposu README](https://huggingface.co/rhasspy/piper-voices/blob/e9ab671f2a0e50a701b34361136ba3e6a3a9eb0c/README.md): MIT deposu; her modelin veri lisansı ayrıca incelendi.
- İngilizce `en_US-ljspeech-high`: [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/e9ab671f2a0e50a701b34361136ba3e6a3a9eb0c/en/en_US/ljspeech/high/MODEL_CARD), [LJ Speech veri seti](https://keithito.com/LJ-Speech-Dataset/): public domain. Model114.2MB,22.05kHz tek kadın ses.
- Almanca `de_DE-thorsten-medium`: [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/e9ab671f2a0e50a701b34361136ba3e6a3a9eb0c/de/de_DE/thorsten/medium/MODEL_CARD), [Thorsten Voice](https://github.com/thorstenMueller/Thorsten-Voice): CC0; taban model de CC0 olarak açıklanıyor. Model63.2MB,22.05kHz tek erkek ses.
- `ryan-high` ve `hfc_female-medium` modelleri NC-SA veri lisanslarından dolayı seçilmedi. `lessac` özel veri koşulları nedeniyle varsayılan kabul edilmedi. Bütün Piper sesleri serbest ticari kullanılabilir varsayımı yapılmadı.

## Zamanlama yöntemi

Orijinal altyazı kelimelerinin her biri eSpeak ile fonemlere çevrilir. Fonemler birleştirilip birlikte tek sinirsel model çağrısında sentezlenir. Her orijinal kelimenin fonem-ID aralığı sentezden önce bilinir; sentezin döndürdüğü gerçek fonem örnek sayıları bu aralıklarda toplanır. Böylece `100` gibi bir kelime konuşmada birden fazla kelimeye açılsa bile tek orijinal altyazı öğesi gerçek ses aralığını taşır. Süreyi metin uzunluğuna bölme veya sessiz tahmin yedeği yoktur.

Model her ID için örnek sayısı döndürmezse, toplam örnek sayısı gerçek WAV'a eşit değilse, fonem kaybolursa veya bir kelimenin süresi sıfırsa işlem hata verir. Bu yöntem `aligned` olarak raporlanır; kaynağı `native_phoneme_samples` olarak belirtilir. Kelimeleri tek tek fonemleştirme, tam cümlenin bağlama bağlı fonemleştirmesinden farklı olabilir; ses doğallığı bu smoke testinde insan dinlemesiyle puanlanmadı.

## Gerçek test ve kaynak sınırları

[local-voice-live-test.json](local-voice-live-test.json): iki gerçek model indirilip SHA256 ile sabitlendi. Production `local_voice.synthesize` ile İngilizce ve Almanca, sayısal `100` içeren metinler seslendirildi. Gerçek WAV dosyaları FFprobe ile PCM16bit,22050Hz,mono olarak doğrulandı.

- İngilizce:10altyazı öğesi,3.123s ses,4.128s model yükleme+sentez.
- Almanca:9altyazı öğesi,2.984s ses.
- Her iki ses için native fonem örnek sayıları gerçek ses örneği toplamına birebir eşit; tüm orijinal kelimeler süre aldı.

ONNX CPU işçi sayısı2 ve ara-op1 ile sınırlıdır. Model URL'leri sabit bir Hugging Face commit'ine ve altı beklenen dosya SHA256/boyutuna bağlanır. Model dosyaları bir kere indirildikten sonra ses aşaması ağ erişimi gerektirmez. İndirmeler dosya başına120s ile sınırlıdır; gerçek model olmadan mock test sonucu gerçek sentez olarak sayılmaz. Tüm video işindeki toplam ses süresi üst sınırı ayrıca strict runtime tarafından uygulanır.
