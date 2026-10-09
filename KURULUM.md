# 🛠️ WioForge — Kurulum Talimatı

Bu belge, WioForge'u kendi bilgisayarınıza kurup ilk kez çalıştırmanız için
gereken **tüm adımları** içerir. Kurulum yaklaşık **5–10 dakika** sürer.

---

## 1. Gereksinimler

| Bileşen | Zorunlu mu? | Not |
|---------|-------------|-----|
| **Python 3.8+** | ✅ Evet | Ana araç seti |
| **git** | ✅ Evet | GitHub'a yükleme için |
| **İnternet** | ✅ Evet | Aynalama ve yükleme için |
| **GitHub hesabı** | ✅ Evet | Kendi deponuz için |
| **PHP 7.4+** | ⬜ İsteğe bağlı | Yalnızca PHP panelini kullanacaksanız |

> WioForge **harici Python kütüphanesi kullanmaz** — yalnızca standart kütüphane.
> Bu yüzden `pip install` gerekmez.

---

## 2. Python Kurulumu

### Windows
1. https://www.python.org/downloads/ adresinden Python 3 indirin.
2. Kurulum sırasında **“Add Python to PATH”** kutusunu mutlaka işaretleyin.
3. Kurulumu bitirin ve komut istemini (cmd) yeniden açın.
4. Doğrulayın:
   ```bat
   python --version
   ```

### macOS
```bash
brew install python git
python3 --version
```

### Linux (Debian / Ubuntu)
```bash
sudo apt update
sudo apt install -y python3 git
python3 --version
```

### git Kurulumu
- **Windows:** https://git-scm.com/download/win
- **macOS:** `brew install git`
- **Linux:** `sudo apt install -y git`

Doğrulayın:
```bash
git --version
```

---

## 3. WioForge'u Açma

Bu `.zip` dosyasını bilgisayarınıza çıkarın. Örneğin:

```
C:\WioForge\           (Windows)
~/WioForge/            (macOS / Linux)
```

Klasörün içinde `wioforge.py` dosyasını görmelisiniz.

Terminali (komut istemini) bu klasöre gelin:

```bash
cd /yol/WioForge
```

---

## 4. İlk Kurulum (`init`)

```bash
python wioforge.py init
```

> Windows'ta `python` yerine `py` kullanmanız gerekebilir: `py wioforge.py init`

Bu komut size şu soruları sorar:

| Soru | Açıklama | Örnek |
|------|----------|-------|
| **GitHub kullanıcı adınız** | GitHub kullanıcı adınız | `ahmet123` |
| **GitHub token** | Aşağıda nasıl alınacağı anlatılıyor | `ghp_xxxxxxxx` |
| **Depo adı** | Kendi deponuzun adı | `WioRepo` |
| **Eklenti yazar adı** | Eklentilerde görünecek isim | `Ahmet` |
| **Kaynak depo** | Aynalanacak upstream | `https://github.com/Wiojelt/WioLand` |
| **Korumalı politika** | 403 dönen `.cs3` için | `1` (skip) |

Ayarlar `wioforge.json` dosyasına kaydedilir. İstediğiniz zaman elle
düzenleyebilir veya `init` komutunu tekrar çalıştırabilirsiniz.

---

## 5. GitHub Token Nasıl Alınır?

`publish` (yükleme) komutu için **kişisel erişim token'ı** gerekir.

1. GitHub'da sağ üstteki profil resminize → **Settings**.
2. Sol menüden **Developer settings** (en altta).
3. **Personal access tokens** → **Tokens (classic)**.
4. **Generate new token (classic)** düğmesine basın.
5. **Note:** `WioForge` yazın.
6. **Expiration:** istediğiniz süre (ör. 90 gün veya “No expiration”).
7. **Scopes** bölümünde **`repo`** kutusunu işaretleyin (zorunlu).
8. **Generate token** → çıkan `ghp_...` ile başlayan anahtarı kopyalayın.
9. Bu anahtarı `init` sırasında veya panelde “GitHub Token” alanına yapıştırın.

> ⚠️ Token'ınızı kimseyle paylaşmayın. `wioforge.json` dosyasını herkese açık
> bir yere yüklemeyin.

---

## 6. Kurulumu Doğrulama

```bash
python wioforge.py info
```

Çıktıda GitHub kullanıcı adınızı ve depo adınızı görmelisiniz:

```
==============================================================
  WioForge — Durum
==============================================================
GitHub kullanıcı : ahmet123
Depo adı         : WioRepo
Kaynak depo      : https://github.com/Wiojelt/WioLand
Çalışma klasörü  : wioforge_data
Korumalı politika: skip
```

Ayrıca WioLand'daki adresleri test edin:

```bash
python wioforge.py list
```

Onlarca depo ve yüzden fazla eklenti listelenmelidir.

İsteğe bağlı olarak **Kaynak Depo analizini** de test edebilirsiniz (ek kurulum
gerektirmez):

```bash
python wioforge.py inspect --source https://github.com/Wiojelt/WioLand --no-sites
```

Bu komut, upstream içindeki tüm eklentileri, sitelerini ve `.cs3` içeriklerini
çıkarıp `wioforge_data/inspect.json` dosyasına kaydeder. Ayrıntılar için
**[KULLANIM.md](KULLANIM.md)** bölüm 9.

İsteğe bağlı olarak **CloudStream-Builder** kütüphanesini de indirebilirsiniz
(hazır extractor'lar, referanslar, script'ler):

```bash
python wioforge.py builder
```

Ayrıntılar için **[KULLANIM.md](KULLANIM.md)** bölüm 10.

---

## 7. (İsteğe Bağlı) PHP Paneli Kurulumu

PHP panelini kullanmak isterseniz PHP kurun:

- **Windows:** https://windows.php.net/download/ (Thread Safe sürüm) — klasörü
  PATH'e ekleyin.
- **macOS:** `brew install php`
- **Linux:** `sudo apt install -y php-cli`

Ardından paneli başlatın:

```bash
php -S localhost:8080 -t php-panel
```

Tarayıcıda **http://localhost:8080** adresini açın. Panel; **Genel**,
**Kaynak Depo Analizi**, **Builder** ve **Günlük** sekmelerinden oluşur.

> **Windows notu:** Panel, Python'u UTF-8 (`-X utf8`) modunda çalıştırır ve
> `PYTHONUTF8=1` ayarlar; böylece `'charmap' codec can't encode` hatası oluşmaz.
> İşler arka planda `start /B` ile başlatılır (Windows `cmd.exe` `&` operatörünü
> desteklemez).

---

## 8. Sorun Giderme

| Sorun | Çözüm |
|-------|-------|
| `python: command not found` | Python PATH'e ekli değil. Windows'ta kurulumda “Add to PATH” işaretleyin; Linux/macOS'ta `python3` deneyin. |
| `git: command not found` | git kurun (bkz. bölüm 2). |
| `403` / indirilemeyen `.cs3` | Normaldir; `init` sırasında “skip” veya “keep” seçin. |
| `publish` başarısız | Token'da `repo` izni var mı? Kullanıcı adı ve depo adı doğru mu? |
| Türkçe karakterler bozuk | Terminal kodlamasını UTF-8 yapın: `chcp 65001` (Windows). |
| Panelde `'charmap' codec can't encode` | Güncel sürümde otomatik düzeltilir (UTF-8). Eski sürümde: `set PYTHONUTF8=1` ve `chcp 65001`. |
| Panel açılmıyor | Port kullanımda olabilir; farklı port verin: `python wioforge.py panel --port 8090`. |

---

Kurulum tamamlandı! Şimdi **[KULLANIM.md](KULLANIM.md)** belgesine geçin.
