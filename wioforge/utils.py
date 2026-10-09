# -*- coding: utf-8 -*-
"""Yardımcı fonksiyonlar: HTTP, JSON, log, hash, renkli çıktı."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Optional

# ----------------------------------------------------------------------------
# G/Ç kodlaması (Windows 'charmap' hatasına karşı)
# ----------------------------------------------------------------------------

def _setup_io() -> None:
    """stdout/stderr akışlarını UTF-8'e zorla.

    Windows'ta PHP panel çıktıyı bir dosyaya yönlendirdiğinde (shell redirect),
    Python yerel kodlamayı (cp1254/cp1252 = 'charmap') kullanır. Bu durumda
    ▶ (U+25B6), ✓ (U+2713) gibi Unicode karakterler yazılamaz ve
    UnicodeEncodeError fırlatılır ("'charmap' codec can't encode character...").
    Bu fonksiyon akışları UTF-8'e (kodlanamayan karakterlerde '?' ile) çevirir;
    böylece çıktı dosyaya/boruya yönlendirilse bile çökme olmaz.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # StringIO vb. (reconfigure yok) — sorun değil
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


_setup_io()


# ----------------------------------------------------------------------------
# Renkli / biçimli konsol çıktısı
# ----------------------------------------------------------------------------

class C:
    """ANSI renk kodları (Windows'ta da çalışması için colorama gerekmez)."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"


def _supports_color() -> bool:
    """Renk desteği var mı?

    ÖNEMLİ: Çıktı bir dosyaya/boruya yönlendirilmişse (TTY değilse) renk KAPATILIR.
    Böylece PHP panelin günlük dosyasında ham ANSI kodları (\\033[91m ...) görünmez.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        if not sys.stdout.isatty():
            return False
    except Exception:  # noqa: BLE001
        return False
    if sys.platform == "win32":
        # Windows 10+ modern konsollarda ANSI desteği vardır
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:  # noqa: BLE001
            return False
    return True


_COLOR = _supports_color()


def _c(text: str, color: str) -> str:
    if not _COLOR:
        return text
    return f"{color}{text}{C.RESET}"


def _emit(text: str, *, stream=None) -> None:
    """Güvenli yazdırma: kodlama/hata durumunda asla çökmez."""
    stream = stream if stream is not None else sys.stdout
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "ascii"
        try:
            print(text.encode(enc, errors="replace").decode(enc, errors="replace"), file=stream)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass


def info(msg: str) -> None:
    _emit(f"{_c('[i]', C.CYAN)} {msg}")


def ok(msg: str) -> None:
    _emit(f"{_c('[+]', C.GREEN)} {msg}")


def warn(msg: str) -> None:
    _emit(f"{_c('[!]', C.YELLOW)} {msg}")


def err(msg: str) -> None:
    _emit(f"{_c('[x]', C.RED)} {msg}", stream=sys.stderr)


def step(msg: str) -> None:
    _emit(f"\n{_c('>', C.MAGENTA)} {_c(msg, C.BOLD)}")


def title(msg: str) -> None:
    line = "=" * 62
    _emit(f"\n{_c(line, C.BLUE)}")
    _emit(_c(f"  {msg}", C.BOLD + C.WHITE))
    _emit(_c(line, C.BLUE))


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# CloudStream uygulamasının kullandığı tipik başlıklar (worker'ları kandırmak için)
CLOUDSTREAM_UA = "Dalvik/2.1.0 (Linux; U; Android 11; CloudStream)"


def http_get(
    url: str,
    *,
    ua: str = DEFAULT_UA,
    timeout: int = 30,
    headers: Optional[dict] = None,
    retries: int = 2,
    binary: bool = False,
) -> Optional[bytes | str]:
    """Basit HTTP GET. binary=True ise bytes, değilse str döner. Hata olursa None."""
    h = {"User-Agent": ua, "Accept": "*/*", "Accept-Language": "tr,en;q=0.9"}
    if headers:
        h.update(headers)

    last_exc = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            return data if binary else data.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last_exc = e
            # 404 gibi kalıcı hatalarda tekrar denemeye gerek yok
            if e.code in (400, 401, 403, 404, 410):
                break
        except Exception as e:  # noqa: BLE001
            last_exc = e
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    if last_exc:
        warn(f"İndirilemedi: {url} ({last_exc})")
    return None


def http_get_json(url: str, **kwargs) -> Any:
    """JSON indir ve ayrıştır. Hata olursa None."""
    raw = http_get(url, **kwargs)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        err(f"Geçersiz JSON: {url} ({e})")
        return None


def http_get_status(url: str, *, ua: str = DEFAULT_UA, timeout: int = 25) -> int:
    """Yalnızca HTTP durum kodunu döndürür (0 = bağlantı hatası)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001
        return 0


def download_file(url: str, dest_path: str, *, ua: str = DEFAULT_UA, timeout: int = 60) -> bool:
    """Dosyayı diske indir. Başarılıysa True."""
    data = http_get(url, ua=ua, timeout=timeout, binary=True)
    if data is None:
        return False
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(data)
    return True


# ----------------------------------------------------------------------------
# JSON / dosya
# ----------------------------------------------------------------------------

def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: str, data: Any, *, indent: int = 2) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read_text(path: str, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return default


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024.0:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0  # type: ignore[assignment]
    return f"{num:.1f} TB"


def slugify(text: str) -> str:
    """Basit slug: yalnızca harf, rakam ve tire."""
    import re
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-") or "provider"


def domain_of(url: str) -> str:
    """URL'den alan adını çıkar (www. dahil)."""
    from urllib.parse import urlparse
    if not url.startswith("http"):
        url = "https://" + url
    net = urlparse(url).netloc
    return net or url
