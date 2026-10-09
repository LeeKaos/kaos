# 📘 WioForge — Kullanım Talimatı

Bu belge, WioForge ile **WioLand'dan bağımsız** bir CloudStream deposu kurmayı,
onu **otomatik güncellemeyi** ve **kendi sitenizden eklenti üretmeyi** adım adım
anlatır.

---

## İçindekiler

1. [Genel Akış](#1-genel-akış)
2. [Orijinal Adresleri Bulma](#2-orijinal-adresleri-bulma-list)
3. [Depoları Aynalama](#3-depoları-aynalama-mirror)
4. [Otomatik Güncelleme](#4-otomatik-güncelleme-update)
5. [Kendi Sitenizden Eklenti Üretme](#5-kendi-sitenizden-eklenti-üretme-generate)
6. [GitHub'a Yükleme](#6-githuba-yükleme-publish)
7. [CloudStream'e Ekleme](#7-cloudstreame-ekleme)
8. [Web Panelleri](#8-web-panelleri)
9. [Kaynak Depo (Upstream) Analizi](#9-kaynak-depo-upstream-analizi)
10. [CloudStream-Builder Entegrasyonu](#10-cloudstream-builder-entegrasyonu)
11. [Seçicileri Düzeltme](#11-seçicileri-düzeltme)
12. [Otomatik Güncellemeyi Zamanlama](#12-otomatik-güncellemeyi-zamanlama)
13. [Sorun Giderme](#13-sorun-giderme)

---

## 1. Genel Akış

```
┌─────────────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│  WioLand        │───▶│   list       │───▶│   mirror      │───▶│   publish    │
│  (upstream)     │    │  adresleri   │    │  indir +      │    │  kendi       │
│                 │    │  bul         │    │  yeniden yaz  │    │  GitHub'a    │
└─────────────────┘    └──────────────┘    └───────────────┘    └──────┬───────┘
                                                                       │
                                    ┌──────────────────────────────────┘
                                    ▼
                          ┌──────────────────┐    ┌──────────────────┐
                          │ GitHub Actions   │───▶│  .cs3 dosyaları  │
                          │ bulutta derler   │    │  (builds dalı)   │
                          └──────────────────┘    └──────────────────┘
```

Kendi siteniz için akış:

```
generate <site>  ──▶  selector_config.json düzelt  ──▶  publish  ──▶  .cs3
```

---

## 2. Orijinal Adresleri Bulma (`list`)

WioLand'daki **tüm** depo ve eklenti adreslerini listeler.

```bash
python wioforge.py list
```

Çıktı örneği:

```
==============================================================
  WioLand — Tüm Orijinal Adresler
==============================================================

DEPOLAR (10)
  • MegaWio
      repo.json : https://raw.githubusercontent.com/Wiojelt/WioLand/main/repo.json
      liste     : https://raw.githubusercontent.com/Wiojelt/WioLand/builds/plugins.json?t=...
  • WioSinema
      ...

EKLENTİLER (103)
  • MegaWio v81  [wiojelt-auth.hdf-worker.workers.dev]
      indir : https://wiojelt-auth.hdf-worker.workers.dev/dl/megawio/MegaWio.cs3?v=...
  ...
```

Sonucu JSON olarak kaydetmek için:

```bash
python wioforge.py list --json adresler.json
```

Bu dosya, tüm orijinal adresleri içerir ve `mirror` komutunun temelini oluşturur.

---

## 3. Depoları Aynalama (`mirror`)

Bu komut **işin kalbidir**. Şunları yapar:

1. WioLand'ın `repos-db.json` dosyasını çeker → tüm alt depoları bulur.
2. Her deponun `repo.json` → `plugins.json` zincirini izler.
3. Tüm `.cs3` dosyalarını **indirir**.
4. İçindeki WioLand bağlantılarını **sizin deponuza göre yeniden yazar**.
5. Eklenti ikonlarını indirir.
6. Kendi `repo.json`, `plugins.json` ve `repos-db.json` dosyalarını üretir.

```bash
python wioforge.py mirror
```

Çıktı örneği:

```
==============================================================
  Ayna Özeti
==============================================================
  Toplam depo   : 10
  Toplam eklenti: 103
  İndirilen     : 102
  Atlanan       : 1
  Klasör        : wioforge_data/mirror
```

> **İndirilmeden yalnızca meta veri** görmek için: `python wioforge.py mirror --no-download`

Aynalama sonucu `wioforge_data/mirror/` altında oluşur:

```
wioforge_data/mirror/
├── repo.json          # Sizin depo manifestiniz
├── plugins.json       # Eklenti listesi (bağlantılar sizin adresinize yönlendirilmiş)
├── repos-db.json      # Alt depo listesi
├── plugins/           # İndirilen .cs3 dosyaları
│   ├── MegaWio.cs3
│   ├── DiziPal.cs3
│   └── ...
└── assets/            # İkonlar
```

### Yinelenen eklentiler

Aynı `internalName`'e sahip birden çok eklenti varsa WioForge **en yüksek
sürümü** tutar ve dosya adı çakışmalarını otomatik çözer.

---

## 4. Otomatik Güncelleme (`update`)

`update`, `mirror` ile aynı işi yapar ancak amacı **mevcut aynayı tazelemektir**.
Upstream'i yeniden çeker, yeni/değişen eklentileri indirir.

```bash
python wioforge.py update
```

Bu komutu bir **zamanlayıcıya** bağlayarak (bkz. [bölüm 12](#12-otomatik-güncellemeyi-zamanlama))
deponuzun her gün otomatik güncellenmesini sağlayabilirsiniz.

---

## 5. Kendi Sitenizden Eklenti Üretme (`generate`)

Verdiğiniz site adresini çözümler ve CloudStream eklentisi üretir.

```bash
python wioforge.py generate https://www.dizimom.wiki --name DiziMom
```

| Parametre | Açıklama |
|-----------|----------|
| `site` | Hedef site adresi (zorunlu) |
| `--name` | Sağlayıcı adı (ör. `DiziMom`) |
| `--types` | Türler: `Movie,TvSeries,Anime,Live` |
| `--query` | Analiz için örnek arama terimi (varsayılan: `breaking`) |
| `--icon` | Eklenti ikon URL'i (isteğe bağlı) |

### Çözümleme ne yapar?

1. **Ana sayfayı** çeker, başlığı ve dili tespit eder.
2. **Arama formunu** bulur (`?s=`, `/?q=`, `/search/` vb.).
3. **WordPress** olup olmadığını anlar.
4. Örnek bir arama yapar ve **sonuç kartı yapısını** (CSS sınıflarını) sezgisel
   olarak bulur (ör. `.poster`, `.episode-box`, `article`, `.post`).
5. **Detay ve bölüm** URL kalıplarını çıkarır.

Çıktı `wioforge_data/generated/<slug>/` altında oluşur:

```
wioforge_data/generated/dizimom/
├── build.gradle.kts              # Kök Gradle
├── settings.gradle.kts
├── gradle.properties
├── gradlew / gradlew.bat
├── .github/workflows/build.yml   # Bulut derleme
├── site_profile.json             # Çözümleme raporu
├── selector_config.json          # Düzenlenebilir seçiciler
├── README.md
└── DiziMom/
    ├── build.gradle.kts
    └── src/main/
        ├── AndroidManifest.xml
        └── kotlin/com/wioforge/dizimom/
            ├── DiziMomProvider.kt   # ← Ana mantık
            └── DiziMomPlugin.kt
```

### Üretilen kodu inceleme

`DiziMomProvider.kt` dosyasını açın. İçinde:

- `search()` — arama sorgusunu siteye gönderir.
- `load()` — detay sayfasını ve bölüm listesini okur.
- `loadLinks()` — oynatma (video) bağlantılarını çıkarır.

Dosyada `TODO` ile işaretli yerlere sitenin yapısına göre ekleme yapabilirsiniz.

---

## 6. GitHub'a Yükleme (`publish`)

### Aynayı yükleme

```bash
python wioforge.py publish --target mirror
```

Bu komut:
1. GitHub API ile depo yoksa **oluşturur**.
2. Yerel git deposu başlatır, `main` dalını hazırlar.
3. Boş bir `builds` dalı açar.
4. Her iki dalı GitHub'a gönderir.

Ardından **GitHub Actions** otomatik devreye girer ve `.cs3` dosyalarını
`builds` dalına derler.

### Üretilen eklentiyi yükleme

```bash
python wioforge.py publish --target generated
```

En son üretilen projeyi (veya `--path <klasör>` ile belirtileni) yükler.

> İlk yüklemeden sonra GitHub Actions'ın çalışması **2–5 dakika** sürer.
> İlerlemeyi GitHub'da **Actions** sekmesinden izleyebilirsiniz.

---

## 7. CloudStream'e Ekleme

GitHub Actions derlemeyi bitirdikten sonra CloudStream'e deponuzu ekleyin:

1. CloudStream uygulamasını açın.
2. **Ayarlar → Eklentiler (Extensions)**.
3. Sağ üstteki **“+ (Depo ekle)”** düğmesine basın.
4. Şu adresi yapıştırın:

```
https://raw.githubusercontent.com/KULLANICI_ADINIZ/WioRepo/builds/repo.json
```

5. **Ekle** → depo listelenir → istediğiniz eklentileri **Yükle**.

> `KULLANICI_ADINIZ` ve `WioRepo` yerine kendi değerlerinizi yazın.
> Bu adresi panelin “Durum” kartında da görebilirsiniz.

---

## 8. Web Panelleri

### Python Paneli (önerilen)

```bash
python wioforge.py panel
```

Tarayıcı otomatik açılır (http://localhost:8080). Panel dört sekmeye ayrılmıştır:

- **🏠 Genel** sekmesi:
  - **Durum** kartı: toplam/indirilen eklenti sayısı, son aynalama zamanı.
  - **GitHub Ayarları**: kullanıcı adı, token, depo adı, kaynak depo → **Kaydet**.
  - **İşlemler**: Orijinal adresleri bul, Aynala, Güncelle, GitHub'a yükle,
    Eklenti üret, Yerel test sunucusu.
- **🔎 Kaynak Depo Analizi** sekmesi: upstream linkini girip tüm eklentileri,
  sitelerini, ikonlarını, ayarlarını ve çalışma durumlarını görün (bkz. bölüm 9).
- **🧩 Builder** sekmesi: CloudStream-Builder kütüphanesini indirip içeriğini
  (extractor'lar, referanslar, script'ler) görüntüleyin (bkz. bölüm 10).
- **📜 Günlük** sekmesi: çalışan işin canlı çıktısı.

### PHP Paneli (alternatif)

```bash
php -S localhost:8080 -t php-panel
```

Tarayıcıda **http://localhost:8080** açın. Arayüz ve işlevler Python paneliyle
aynıdır; işleri arka planda Python CLI'ye devreder.

> PHP paneli, PHP + Python'un birlikte kurulu olduğu bir sunucuda çalışır.

---

## 9. Kaynak Depo (Upstream) Analizi

Bu özellik, **verdiğiniz bir CloudStream deposu (upstream) linkini** baştan sona
inceler ve içinizde ne olduğunu şeffaf biçimde gösterir. Örneğin
`https://github.com/Wiojelt/WioLand` adresini girdiğinizde:

- İçindeki **tüm alt depoları** (repos-db → repo.json → plugins.json zinciri) bulur.
- **Tüm eklentileri** listeler: ad, sürüm, dil, yazar, türler.
- Her eklentinin **resmini (ikonunu)** indirir ve panelde gösterir.
- Her eklentinin **.cs3 içeriğini** çözer: `manifest.json`, Kotlin **sınıfları**,
  içindeki **metinler/ayarlar** ve **tüm adresler**.
- Her eklentinin **sitelerini** çıkarır ve **çalışıp çalışmadığını** test eder
  (açık / korumalı / erişilemez).

### Komut satırından

```bash
python wioforge.py inspect --source https://github.com/Wiojelt/WioLand
```

| Parametre | Açıklama |
|-----------|----------|
| `--source` | İncelenecek upstream depo (GitHub repo, `repo.json` veya `raw` adresi) |
| `--no-download` | `.cs3` dosyalarını indirme (yalnızca meta veri) |
| `--no-icons` | İkonları indirme |
| `--no-sites` | Site erişilebilirlik testini atla (çok daha hızlı) |
| `--json` | Raporu belirtilen dosyaya kaydet |

Örnek çıktı:

```
==============================================================
  Kaynak Depo Analizi (Upstream Inspector)
==============================================================
  Depo sayısı      : 10
  Eklenti sayısı   : 103
  Çalışıyor        : 102
  Çalışmıyor       : 1
  İkon             : 93
  Site             : 1645/3240 erişilebilir

  Detaylı rapor  : wioforge_data/inspect/inspect.json
```

### Rapor nerede?

Analiz sonucu iki yere yazılır:

```
wioforge_data/inspect.json          # Panelin okuduğu özet rapor
wioforge_data/inspect/inspect.json  # Tam rapor
wioforge_data/inspect/cs3/          # İndirilen .cs3 dosyaları
wioforge_data/inspect/assets/       # İndirilen ikonlar (resimler)
```

### Site durumları ne anlama gelir?

| Durum | Anlamı |
|-------|--------|
| **açık (ok)** | Site HTTP 200–399 döndü, doğrudan erişilebilir |
| **korumalı (protected)** | HTTP 401/403/429/451/503 — Cloudflare/bot engeli. Site aslında **canlıdır**, yalnızca otomatik istekleri engeller |
| **erişilemez (dead)** | HTTP 0 veya diğer hatalar — site kapalı ya da taşınmış olabilir |

> **Not:** "korumalı" siteler CloudStream uygulamasında normalde çalışır; çünkü
> uygulama gerçek bir cihaz gibi davranır. Yalnızca analiz botu engellenir.

### Panelden

Her iki panelde de **🔎 Kaynak Depo Analizi** sekmesi vardır:

1. Üstteki kutuya upstream linkini yapıştırın (varsayılan: WioLand).
2. **🔎 Analiz Et** → tüm siteleri test eder (birkaç dakika sürebilir).
3. **⚡ Hızlı (site testi yok)** → yalnızca yapıyı çıkarır (saniyeler).
4. **🔄 Raporu Yenile** → daha önce kaydedilmiş raporu tekrar yükler.

Analiz bittiğinde:

- **Özet** kartında depo/eklenti/ikon/site sayıları görünür.
- **Eklentiler** tablosunda her satır: ikon, ad, sürüm, dil, ana site,
  `.cs3` durumu ve site durumu (ör. `5✓ 2🛡 / 7`).
- Bir satıra **tıklayınca** detay açılır: ayarlar, siteler, manifest,
  sınıflar, metinler ve tüm adresler.
- Tabloda **arama** ve **"Sadece çalışanlar" / "Sadece ana sitesi olanlar"**
  filtreleri vardır.

---

## 10. CloudStream-Builder Entegrasyonu

WioForge, eklenti üretimini güçlendirmek için
[CloudStream-Builder](https://github.com/Wiojelt/CloudStream-Builder) kütüphanesini
**isteğe bağlı** olarak indirip inceleyebilir. CloudStream-Builder, yarı otonom bir
CloudStream eklenti oluşturucudur; içinde hazır **extractor**'lar (site çözümleyici
modüller), **referans rehberleri**, **yardımcı script'ler** ve bir **workflow
(SKILL.md)** bulunur. WioForge bu depoyu indirir, çözümler ve kategorilere ayırarak
hem komut satırında hem de panelde görüntüler.

> Bu adım **zorunlu değildir**; WioForge CloudStream-Builder olmadan da tam
> çalışır. Builder yalnızca hazır desen ve extractor kütüphanesini görmek/ilham
> almak isteyenler içindir.

### Komut satırından

```bash
python wioforge.py builder
```

Bu komut depoyu indirir (zip arşivi olarak), açar ve aşağıdaki özeti yazdırır:

```
==============================================================
  CloudStream-Builder — Özet
==============================================================
  Kaynak depo : https://github.com/Wiojelt/CloudStream-Builder
  Dal (branch): main
  Dosya       : 160 (2.1 MB)
  JSON config : 43
  OCE Kotlin  : 50
  OCE çekirdek: 7
  Yerli       : 36
  Referans    : 7
  Script      : 4

  Rapor: wioforge_data/builder/builder.json
```

| Parametre | Açıklama |
|-----------|----------|
| `--source` | Builder depo adresi (varsayılan: `Wiojelt/CloudStream-Builder`) |
| `--show` | Builder içindeki bir dosyayı ekrana yazdır (ör. `cloudstream-builder/SKILL.md`) |
| `--json` | Raporu JSON olarak kaydet |

Örneğin workflow rehberini okumak için:

```bash
python wioforge.py builder --show cloudstream-builder/SKILL.md
```

### Builder içeriği (kategoriler)

| Kategori | İçerik |
|----------|--------|
| **OCE JSON Config** | Bildirimsel (kod yazmadan) extractor kuralları |
| **OCE Kotlin Extractor** | Kotlin ile yazılmış OCE extractor'ları |
| **OCE Çekirdek Motor** | `ConfigDrivenExtractor`, `Registry`, `Fallback` gibi motorlar |
| **Yerli (Türk) Extractor** | Türkçe sitelere özel hazır extractor'lar |
| **Referans Rehberi** | Kanıtlanmış depo desenleri, oynatma, HLS vb. |
| **Yardımcı Script** | `audit_job`, `verify_repo_integrity` vb. araçlar |
| **Skill / Katalog** | `SKILL.md`, `INDEX.md` — workflow ve extractor kataloğu |

### Dosyalar nerede?

```
wioforge_data/builder/src/          # İndirilip açılan Builder deposu
wioforge_data/builder/builder.json  # Kategori/katalog raporu
wioforge_data/builder.json          # Panelin okuduğu özet rapor
```

### Panelden

Her iki panelde de **🧩 Builder** sekmesi vardır:

1. Üstteki kutuya Builder depo adresini yapıştırın (varsayılan hazır gelir).
2. **İndir / Güncelle** → depoyu indirir ve raporu oluşturur.
3. **🔄 Raporu Yenile** → daha önce indirilmiş raporu tekrar yükler.
4. **Özet** kartında kategori sayıları (dosya, JSON config, OCE Kotlin, yerli
   extractor, referans, script) görünür.
5. **Extractor Kataloğu** tablosunda `INDEX.md`'den çıkarılan extractor listesi
   (host + not) yer alır.
6. Alttaki **Dosya** tablosunda tüm dosyalar kategoriye göre listelenir; bir
   satıra tıklayınca içerik görüntülenir.

---

## 11. Seçicileri Düzeltme

Bazı sitelerde otomatik çözümleme tam isabetli olmayabilir. Bu durumda
`selector_config.json` dosyasını düzenleyin:

```json
{
  "site_url": "https://www.dizimom.wiki",
  "search_url_template": "https://www.dizimom.wiki/?s={query}",
  "result_selector": ".list-episodes, article, .post",
  "result_link_selector": "a",
  "result_title_selector": "h2, h3, .title",
  "result_poster_selector": "img",
  "poster_attr": "src"
}
```

**Doğru seçiciyi nasıl bulurum?**

1. Tarayıcıda siteyi açın, arama yapın.
2. Sonuç öğesine sağ tıklayıp **İncele (Inspect)** seçin.
3. Öğenin `class` / `id` değerlerini not edin (ör. `class="poster"`).
4. CSS seçicisini yazın (ör. `.poster`).
5. Aynı değerleri `selector_config.json` **ve** `Provider.kt` içine yansıtın.

Değişiklikten sonra tekrar yükleyin:

```bash
python wioforge.py publish --target generated
```

---

## 12. Otomatik Güncellemeyi Zamanlama

Yayınlanan `builds` deposu varsayılan olarak yalnızca kendi GitHub deponuzdan
katalog ve `.cs3` dosyalarını sunar; kaynak depoya zamanlanmış görev kurulmaz.
Aşağıdaki adımlar bilerek etkinleştirilirse `update` kaynak depoyu yeniden
indirir ve aynayı günceller. Kaynağa hiç bağlanılmamasını istiyorsanız bu
zamanlayıcıları kurmayın. Eklentilerin kod içindeki yayın/API servisleri bu
aynalama işlemiyle GitHub'a taşınmaz.

### Linux / macOS (cron)

Her gün saat 04:00'te aynayı güncelleyip yüklemek için:

```bash
crontab -e
```

Şu satırı ekleyin (yolları kendinize göre düzeltin):

```cron
0 4 * * * cd /home/kullanici/WioForge && /usr/bin/python3 wioforge.py update >> guncelleme.log 2>&1 && /usr/bin/python3 wioforge.py publish --target mirror >> guncelleme.log 2>&1
```

### Windows (Task Scheduler)

1. **Görev Zamanlayıcı (Task Scheduler)** → **Temel Görev Oluştur**.
2. Tetikleyici: **Günlük**.
3. Eylem: **Program başlat** →
   - Program: `python`
   - Bağımsız değişken: `wioforge.py update`
   - Başlangıç klasörü: `C:\WioForge`
4. Aynı şekilde ikinci bir görevle `publish --target mirror` ekleyin.

### GitHub Actions ile otomatik güncelleme (en kolay)

Deponuza `.github/workflows/` altında bir zamanlanmış iş ekleyerek GitHub'ın
kendisinin günlük güncelleme yapmasını sağlayabilirsiniz. Böylece bilgisayarınız
kapalı olsa bile deponuz güncel kalır.

---

## 13. Sorun Giderme

| Belirti | Olası neden | Çözüm |
|---------|-------------|-------|
| `list` boş dönüyor | İnternet / upstream erişimi | Bağlantıyı kontrol edin; `source_repo` doğru mu? |
| `.cs3` indirilemiyor (403) | Worker koruması | `init` → politika `skip`/`keep`; veya `proxy` |
| Eklenti CloudStream'de görünmüyor | Actions henüz bitmedi | GitHub → Actions sekmesinden bekleyin |
| Eklenti açılıyor ama sonuç yok | Yanlış seçici | `selector_config.json` düzeltin (bölüm 11) |
| Analizde tüm siteler "erişilemez" | Site testi botu engellendi | Normal; "korumalı" siteler CloudStream'de çalışır |
| Analiz çok yavaş | Binlerce site test ediliyor | **⚡ Hızlı** modu kullanın (site testi yok) |
| Video oynamıyor | Özel oynatıcı | `Provider.kt` → `loadLinks` fonksiyonunu güncelleyin |
| `publish` “yetkisiz” | Token izni | Token'da `repo` izni olmalı |
| Türkçe karakter bozuk | Kodlama | Windows: `chcp 65001`; dosyaları UTF-8 kaydedin |
| Panelde `'charmap' codec can't encode` | Windows konsol kodlaması | Güncel sürümde otomatik düzeltilir; eski sürümde `set PYTHONUTF8=1` ve `chcp 65001` |

### Faydalı komutlar

```bash
python wioforge.py info                 # Durumu göster
python wioforge.py list --json a.json   # Adresleri JSON'a kaydet
python wioforge.py inspect --source https://github.com/Wiojelt/WioLand  # Upstream analizi
python wioforge.py inspect --source https://github.com/Wiojelt/WioLand --no-sites  # Hızlı analiz
python wioforge.py serve                # Yerel test sunucusu (ayna klasörü)
python wioforge.py serve --dir wioforge_data/generated/dizimom
```

---

## Özet: Tipik Bir Çalışma Günü

```bash
# 1) Sabah: aynayı güncelle
python wioforge.py update

# 2) Değişiklikleri GitHub'a gönder (Actions derler)
python wioforge.py publish --target mirror

# 3) Yeni bir site keşfettiniz: eklenti üretin
python wioforge.py generate https://yenisite.com --name YeniSite

# 4) Seçicileri kontrol edin, gerekirse düzeltin
#    wioforge_data/generated/yenisite/selector_config.json

# 5) Yükleyin
python wioforge.py publish --target generated
```

Hepsi bu! Deponuz artık **WioLand'dan tamamen bağımsız** olarak çalışır.
