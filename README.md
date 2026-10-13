# beltur — CloudStream Eklentisi

- **Site:** https://duzcebeltur.com
- **Başlık:** Düzce Beltur – Yöresel Ürünler
- **Arama kalıbı:** `https://duzcebeltur.com/?s={query}`
- **Önerilen seçici:** `article, .post, .result-item`
- **Paket:** `com.wioforge.beltur`
- **Sağlayıcı sınıfı:** `belturProvider`
- **Eklenti sınıfı:** `belturPlugin`

## Çözümlenen örnek sonuçlar
  (örnek sonuç bulunamadı)

## Notlar
  - WordPress tespit edildi (arama parametresi genelde 's').
  - Kart yapısı otomatik bulunamadı; seçiciyi elle ayarla.

## Nasıl derlenir?
Bu proje GitHub Actions ile **bulutta** derlenir. Yerel bilgisayarında Android SDK
kurmana gerek yoktur. `wioforge publish` komutuyla GitHub'a yükle; `builds` dalında
`.cs3` dosyası otomatik oluşur.

## Seçicileri düzeltme
`selector_config.json` ve `belturProvider.kt` içindeki seçicileri sitenin gerçek HTML
yapısına göre güncelle. Tarayıcıda F12 ile öğeleri inceleyerek doğru CSS
seçicilerini bulabilirsin.
