# ⚡ WioForge — Bağımsız CloudStream Depo & Eklenti Yönetimi

**WioForge**, CloudStream için *tamamen bağımsız* bir depo (repository) ve eklenti
üretim aracıdır. Amaçları şunlardır:

1. **`github.com/Wiojelt/WioLand`** deposundaki **tüm orijinal adresleri** (repolar,
   eklenti listeleri, `.cs3` indirme bağlantıları) otomatik olarak bulur.
2. Bu eklentilerin **tamamını indirip kendi deponuza aynalar** ve bağlantıları
   **kendi adreslerinize göre yeniden yazar**.
3. Verdiğiniz **herhangi bir site adresini** (örnek: `https://www.dizimom.wiki`)
   çözümler ve ondan **CloudStream eklentisi** (Kotlin + Gradle projesi) üretir.
4. Üretilen çıktıyı **kendi GitHub hesabınıza** yükler; GitHub Actions bulutta
   `.cs3` dosyalarını derler.
5. **WioLand kapansa dahi** sizin dosyalarınız çalışmaya devam eder.
6. **`github.com/Wiojelt/CloudStream-Builder`** eklenti oluşturucu kütüphanesini
   indirir; OCE JSON config'lerini, OCE/yerli Kotlin extractor'larını, referans
   rehberlerini ve yardımcı script'leri panelde görüntüler.

> 🔒 **Bağımsızlık ilkesi:** WioForge, WioLand'a yalnızca *ilk kurulumda* ve
> *güncelleme çekerken* bağlanır. Aynalama bittikten sonra tüm `.cs3` dosyaları
> sizin deponuzda barınır. WioLand silinse bile sizin deponuz ve eklentileriniz
> çalışır.

---

## 🚀 Hızlı Başlangıç (3 adım)

```bash
# 1) İlk kurulum (GitHub kullanıcı adı, token, depo adı)
python wioforge.py init

# 2) WioLand'daki tüm eklentileri aynala (indir + bağlantıları yeniden yaz)
python wioforge.py mirror

# 3) Aynayı kendi GitHub hesabına yükle (Actions .cs3'leri derler)
python wioforge.py publish --target mirror
```

Bitti! CloudStream'e ekleyeceğiniz depo adresi:

```
https://raw.githubusercontent.com/KULLANICI_ADINIZ/WioRepo/builds/repo.json
```

---

## 🧩 Kendi Sitenizden Eklenti Üretme

```bash
# Siteyi çözümle ve eklenti projesini üret
python wioforge.py generate https://www.dizimom.wiki --name DiziMom

# Gerekirse seçicileri düzelt: wioforge_data/generated/dizimom/selector_config.json

# GitHub'a yükle (Actions bulutta derler)
python wioforge.py publish --target generated
```

---

## 🖥️ Web Panelleri

WioForge iki farklı web paneli sunar:

| Panel | Komut | Gereksinim |
|-------|-------|-----------|
| **Python paneli** (önerilen) | `python wioforge.py panel` | Python 3.8+ |
| **PHP paneli** (alternatif) | `php -S localhost:8080 -t php-panel` | PHP 7.4+ ve Python |

Her iki panel de aynı işlevleri sunar ve dört sekmeye ayrılmıştır:

- **🏠 Genel** — orijinal adresleri bulma, aynalama, isteğe bağlı kaynak yenileme,
  eklenti üretme ve GitHub'a yükleme.
- **🔎 Kaynak Depo Analizi** — bir upstream linkini girip içindeki tüm
  eklentileri, sitelerini, ikonlarını, ayarlarını ve çalışma durumlarını görme;
  her `.cs3` içeriğini (manifest, sınıflar, metinler) inceleme.
- **🧩 Builder** — `Wiojelt/CloudStream-Builder` kütüphanesini indirip
  içeriğini (OCE JSON config'leri, Kotlin/yerli extractor'lar, referans
  rehberleri, script'ler) listeleme ve dosya içeriklerini okuma.
- **📜 Günlük** — çalışan işin canlı çıktısı.

---

## 📁 Klasör Yapısı

```
wioforge/
├── wioforge.py              # Ana giriş noktası
├── wioforge/                # Python paketi (modüller)
│   ├── config.py            # Yapılandırma
│   ├── utils.py             # HTTP / JSON / log yardımcıları
│   ├── mirror.py            # WioLand aynalama + bağlantı yeniden yazma
│   ├── inspector.py         # Kaynak Depo (upstream) analizi + .cs3 çözümleme
│   ├── builder.py           # CloudStream-Builder entegrasyonu (extractor kütüphanesi)
│   ├── analyzer.py          # Site çözümleme (arama formu, kart yapısı)
│   ├── generator.py         # CloudStream eklenti projesi üretimi
│   ├── publisher.py         # GitHub'a yükleme
│   ├── server.py            # Yerel test sunucusu
│   ├── panel.py             # Python web paneli
│   └── cli.py               # Türkçe komut satırı arayüzü
├── templates/               # Kotlin + Gradle şablonları
├── php-panel/               # PHP web paneli (alternatif)
├── ornek/                   # Örnek dosyalar ve çıktılar
├── baslat.sh / baslat.bat   # Menülü başlatıcı
├── panel-baslat.sh / .bat   # Web panel başlatıcı
├── README.md                # Bu dosya
├── KURULUM.md               # Kurulum talimatı
└── KULLANIM.md              # Kullanım talimatı
```

Çalışma sırasında oluşan dosyalar `wioforge_data/` altında tutulur:

```
wioforge_data/
├── mirror/                  # Aynalanan depo (repo.json, plugins.json, .cs3'ler)
├── generated/               # Üretilen eklenti projeleri
├── inspect/                 # Kaynak Depo analiz raporu + indirilen ikonlar
├── builder/                 # CloudStream-Builder kaynakları (extractor kütüphanesi)
└── mirror.json              # Son aynalama özeti
```

---

## ⚙️ Komutlar

| Komut | Açıklama |
|-------|----------|
| `init` | İlk kurulum (GitHub bilgileri, korumalı politika) |
| `list` | WioLand'daki tüm orijinal adresleri bul |
| `mirror` | Tüm depoları aynala (indir + bağlantıları yeniden yaz) |
| `update` | Kaynağı yeniden indirip aynayı güncelle (upstream'e bağlanır) |
| `generate <site>` | Site adresinden CloudStream eklentisi üret |
| `inspect` | Kaynak Depo (upstream) analizi: eklentiler, siteler, ikonlar, .cs3 içeriği |
| `builder` | CloudStream-Builder kütüphanesini indir/incele (extractor'lar, referanslar) |
| `publish` | Üretilen çıktıyı GitHub'a yükle |
| `serve` | Yerel test sunucusu başlat |
| `panel` | Web panelini aç |
| `info` | Durumu göster |

Detaylı kullanım için: **[KULLANIM.md](KULLANIM.md)**
Kurulum için: **[KURULUM.md](KURULUM.md)**

---

## 🔐 Korumalı Eklentiler (`.cs3` 403 hatası)

WioLand'daki bazı eklentiler bir **Cloudflare Worker** üzerinden korunur
(`wiojelt-auth.hdf-worker.workers.dev`). Bu dosyalar tarayıcıdan `403` dönebilir.
WioForge, bu dosyaları **Python `urllib` ile indirmeyi** dener (çoğu zaman başarılı
olur). İndirilemeyen dosyalar için `init` sırasında seçtiğiniz politika uygulanır:

- **skip** — atla (yalnızca indirilebilenleri aynala) *(varsayılan)*
- **keep** — orijinal adresi koru (bağımsız olmaz ama çalışır)
- **proxy** — kendi proxy/worker adresinizle değiştir

---

## ❓ Sık Sorulan Sorular

**WioLand kapanırsa ne olur?**
Hiçbir şey. Aynalama tamamlandıktan sonra tüm `.cs3` dosyaları ve meta veriler
sizin deponuzda bulunur. WioLand'a bağımlılık kalmaz.

**Yerel bilgisayarımda Android SDK gerekli mi?**
Hayır. Derleme işini **GitHub Actions** bulutta yapar. Sizin yalnızca Python ve
git'e ihtiyacınız var.

**GitHub token'ı zorunlu mu?**
Yalnızca `publish` (yükleme) için gereklidir. `list`, `mirror`, `generate`
komutları token olmadan da çalışır.

**Üretilen eklenti her sitede çalışır mı?**
Sezgisel çözümleme çoğu WordPress/dizi sitesinde çalışır. Bazı siteler özel
oynatıcı API'si kullanıyorsa `Provider.kt` içindeki `loadLinks` fonksiyonunu elle
güncellemeniz gerekebilir (dosyada `TODO` işaretleri vardır).

---

## 📜 Lisans & Sorumluluk

Bu araç yalnızca **kişisel kullanım** ve **eğitim** amaçlıdır. Aynaladığınız
içeriklerin telif haklarına ve ilgili sitelerin kullanım şartlarına uymak
sizin sorumluluğunuzdadır. WioForge hiçbir içeriği barındırmaz; yalnızca açıkça
erişilebilen dosyaları kopyalar ve bağlantıları yeniden düzenler.
