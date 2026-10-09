# -*- coding: utf-8 -*-
"""
inspector.py — Kaynak Depo (upstream) Analiz Motoru
===================================================

Kullanıcının verdiği Kaynak Depo (upstream) linkini (örn.
https://github.com/Wiojelt/WioLand) alır ve İÇİNDEKİ HER ŞEYİ çözümler:

  repos-db.json  ->  repo.json ...  ->  plugins.json  ->  [.cs3 ...]

Her eklenti için:
  • Ayarları / bilgileri (ad, sürüm, dil, durum, tvTypes, yazarlar, sınıf)
  • Resmi (ikon) — indirilir ve yerel olarak sunulur
  • .cs3 İÇERİĞİ — manifest.json + classes.dex'ten çıkarılan SİTE adresleri,
    sınıf adları ve okunabilir metinler
  • ÇALIŞIYOR MU? — .cs3 indirilebiliyor mu + her sitenin HTTP durumu

Sonuç `wioforge_data/inspect/inspect.json` olarak kaydedilir ve panel/CLI
tarafından gösterilir. Bu analiz WioLand'den BAĞIMSIZ çalışır; yalnızca
kullanıcının verdiği linki okur.
"""

from __future__ import annotations

import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from . import utils
from .config import Config, DEFAULT_SOURCE_REPO, DEFAULT_REPOS_DB, DEFAULT_MANIFEST
from . import mirror as mirror_mod


# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

# "Site" sayılmayan altyapı / genel alan adları (URL çıkarımında elenir)
INFRA_HOSTS = {
    "github.com", "raw.githubusercontent.com", "githubusercontent.com",
    "objects.githubusercontent.com", "codeload.github.com",
    "google.com", "www.google.com", "googleapis.com", "gstatic.com",
    "googleusercontent.com", "googletagmanager.com", "google-analytics.com",
    "cloudflare.com", "cloudflareinsights.com", "jsdelivr.net", "unpkg.com",
    "w3.org", "www.w3.org", "schemas.android.com", "developer.android.com",
    "kotlinlang.org", "jetbrains.com", "apache.org", "oracle.com",
    "json-schema.org", "recloudstream.github.io", "cloudstream",
    "maven.org", "gradle.org", "squareup.com", "bumptech.github.io",
    "schema.org", "ns.adobe.com", "purl.org", "example.com",
    "localhost", "127.0.0.1", "0.0.0.0",
}

# Yardımcı / sosyal / destek adresleri (ana içerik sitesi DEĞİL)
AUX_HOSTS = {
    "t.me", "telegram.me", "telegram.org", "kreosus.com", "patreon.com",
    "strawpoll.com", "ornekadres.com", "discord.gg", "discord.com",
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "youtube.com", "youtu.be", "youtube-nocookie.com", "vimeo.com",
    "nadeko.net", "nerdvpn.de", "f5.si", "invidious.io", "piped.video",
    "buymeacoffee.com", "ko-fi.com", "paypal.com", "github.io",
}

# Okunabilir metin çıkarımında elenecek gürültülü desenler
_NOISE_RE = re.compile(
    r"^(L?[a-z0-9_/]+;?|\(.*\)|\[.*\]|<.*>|[A-Za-z0-9_]+/[A-Za-z0-9_/]+)$"
)
_URL_RE = re.compile(rb"https?://[A-Za-z0-9._~:/?#@!$&*+,;=%-]+")
_CLASS_RE = re.compile(rb"(?:dev|com|org|net|io|me|tv|app|xyz)\.[A-Za-z0-9_.$]{4,80}")
_STR_RE = re.compile(rb"[\x20-\x7e\xc0-\xff]{4,80}")


# ---------------------------------------------------------------------------
# Kaynak URL türetme
# ---------------------------------------------------------------------------

def derive_source_urls(source_repo: str) -> Tuple[str, str]:
    """
    Kullanıcının verdiği upstream linkinden (repos-db.json, repo.json) adreslerini
    türetir. Şu girdileri destekler:

      • https://github.com/OWNER/REPO
      • https://github.com/OWNER/REPO/tree/BRANCH
      • https://raw.githubusercontent.com/OWNER/REPO/BRANCH/repos-db.json
      • doğrudan bir repos-db.json adresi
    """
    src = (source_repo or "").strip().rstrip("/")
    if not src:
        return DEFAULT_REPOS_DB, DEFAULT_MANIFEST

    # GitHub dosya sayfasını indirilebilir raw adresine dönüştür.
    src = re.sub(r"^https?://github\.com/([^/]+)/([^/]+)/blob/", r"https://raw.githubusercontent.com/\1/\2/", src)

    # Doğrudan bir json adresi verilmişse
    if src.endswith(".json"):
        base = src.rsplit("/", 1)[0]
        return src, f"{base}/repo.json"

    # raw.githubusercontent.com/OWNER/REPO/BRANCH[/...]
    m = re.match(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)", src)
    if m:
        owner, repo, branch = m.group(1), m.group(2), m.group(3)
        base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
        return f"{base}/repos-db.json", f"{base}/repo.json"

    # github.com/OWNER/REPO[/tree/BRANCH]
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+))?", src)
    if m:
        owner, repo = m.group(1), m.group(2)
        branch = m.group(3) or "main"
        base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
        return f"{base}/repos-db.json", f"{base}/repo.json"

    # Bilinmeyen biçimde de yalnızca kullanıcının verdiği kaynağı dene.
    return src, src


# ---------------------------------------------------------------------------
# .cs3 içerik çözümleme
# ---------------------------------------------------------------------------

def _read_uleb128(data: bytes, off: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    while off < len(data):
        b = data[off]
        off += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, off


def _dex_strings(blob: bytes) -> List[str]:
    """
    Bir .dex dosyasının string tablosunu (string_ids) doğru biçimde okur.
    Ham regex'ten çok daha temiz, gerçek metinler verir.
    """
    strings: List[str] = []
    try:
        if blob[:4] != b"dex\n" or len(blob) < 0x40:
            return strings
        string_ids_size = int.from_bytes(blob[0x38:0x3C], "little")
        string_ids_off = int.from_bytes(blob[0x3C:0x40], "little")
        if string_ids_off <= 0 or string_ids_size <= 0 or string_ids_size > 5_000_000:
            return strings
        for i in range(string_ids_size):
            p = string_ids_off + i * 4
            if p + 4 > len(blob):
                break
            str_off = int.from_bytes(blob[p:p + 4], "little")
            if str_off <= 0 or str_off >= len(blob):
                continue
            _, q = _read_uleb128(blob, str_off)
            end = blob.find(b"\x00", q)
            if end < 0:
                continue
            raw = blob[q:end]
            if not raw:
                continue
            s = raw.decode("utf-8", errors="replace")
            strings.append(s)
    except Exception:  # noqa: BLE001
        pass
    return strings


def _clean_url(raw: bytes) -> str:
    u = raw.decode("latin1").strip()
    # Sondaki ayraç/parantez gibi artıkları temizle
    u = u.rstrip(".,;:)'\"\\]}>")
    return u


def _host_of(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:  # noqa: BLE001
        return ""


def _is_site_url(url: str) -> bool:
    """Altyapı olmayan, gerçek bir hedef site adresi mi?"""
    # Regex/şablon artıklarını ele
    if any(ch in url for ch in "(){}[]|^\\$*<>\"' "):
        return False
    if url.startswith(("about:", "javascript:", "data:")):
        return False
    host = _host_of(url)
    if not host or "." not in host:
        return False
    for bad in INFRA_HOSTS:
        if host == bad or host.endswith("." + bad):
            return False
    # Dosya uzantılı kaynaklar (css/js/png) site değildir
    path = urlparse(url).path.lower()
    if re.search(r"\.(png|jpe?g|gif|webp|svg|css|js|ico|woff2?|ttf|json|xml)(\?|$)", path):
        return False
    return True


def _dedupe_sites_by_host(urls: List[str]) -> List[str]:
    """Aynı alan adına ait adreslerden en kısa/temel olanı tutar."""
    best: Dict[str, str] = {}
    for u in urls:
        h = _host_of(u)
        if h not in best or len(u) < len(best[h]):
            best[h] = u
    return sorted(best.values())


def _site_role(host: str) -> str:
    """'main' = ana içerik sitesi, 'aux' = sosyal/destek/yardımcı adres."""
    for a in AUX_HOSTS:
        if host == a or host.endswith("." + a):
            return "aux"
    return "main"


def extract_cs3_contents(cs3_path: str) -> Dict[str, Any]:
    """
    Bir .cs3 arşivini (zip) açar ve içeriğini çıkarır:
      manifest.json, classes.dex'ten site adresleri, sınıf adları ve metinler.
    """
    out: Dict[str, Any] = {
        "manifest": {},
        "urls": [],
        "sites": [],
        "classes": [],
        "strings": [],
        "entries": [],
        "ok": False,
        "note": "",
    }
    if not cs3_path or not os.path.isfile(cs3_path):
        out["note"] = "dosya yok"
        return out
    if not zipfile.is_zipfile(cs3_path):
        out["note"] = "geçerli bir zip değil"
        return out

    try:
        with zipfile.ZipFile(cs3_path) as z:
            out["entries"] = z.namelist()
            out["ok"] = True

            # manifest.json
            for cand in ("manifest.json", "META-INF/manifest.json"):
                if cand in z.namelist():
                    try:
                        out["manifest"] = utils.json.loads(
                            z.read(cand).decode("utf-8", errors="replace")
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    break

            # classes.dex -> URL / sınıf / metin
            dex_names = [n for n in z.namelist() if n.endswith(".dex")]
            blob = b""
            for dn in dex_names:
                blob += z.read(dn)

            if blob:
                # 1) DEX string tablosundan temiz metinler
                dex_strs = _dex_strings(blob)

                # URL'ler: string tablosundan + güvenlik için ham tarama
                raw_urls = set()
                for s in dex_strs:
                    if "http://" in s or "https://" in s:
                        for m in re.findall(r"https?://[^\s\"'<>]+", s):
                            raw_urls.add(m.rstrip(".,;:)'\"\\]}>"))
                for u in _URL_RE.findall(blob):
                    raw_urls.add(_clean_url(u))
                urls = sorted(u for u in raw_urls if len(u) > 8)
                out["urls"] = urls
                out["sites"] = _dedupe_sites_by_host([u for u in urls if _is_site_url(u)])

                # 2) Sınıf adları
                classes = set()
                for s in dex_strs:
                    if re.match(r"^L?[a-z][a-z0-9_]*(\.[a-z0-9_]+)+\.[A-Z][A-Za-z0-9_$]*;$", s):
                        classes.add(s.lstrip("L").rstrip(";").replace("/", "."))
                    elif re.match(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+){2,}\.[A-Z][A-Za-z0-9_$]*$", s):
                        if not s.startswith("android.intent"):
                            classes.add(s)
                for c in _CLASS_RE.findall(blob):
                    s = c.decode("latin1").strip(".")
                    if re.match(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+){2,}\.[A-Z][A-Za-z0-9_$]*$", s) \
                            and not s.startswith("android.intent"):
                        classes.add(s)
                out["classes"] = sorted(classes)[:80]

                # 3) Okunabilir metinler (ayar etiketleri, başlıklar, mesajlar)
                strings: List[str] = []
                seen = set()
                for s in dex_strs:
                    s = s.strip()
                    if len(s) < 4 or len(s) > 90 or s in seen:
                        continue
                    if s.startswith("L") and s.endswith(";") and "/" in s:
                        continue  # sınıf tanımlayıcısı
                    if "://" in s:
                        continue  # URL
                    if _NOISE_RE.match(s):
                        continue
                    # en az bir harf + bir sesli harf
                    if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", s):
                        continue
                    if not re.search(r"[aeıioöuüAEIİOÖUÜ]", s):
                        continue
                    # harf/rakam/boşluk oranı yüksek olsun (okunabilir)
                    if sum(ch.isalnum() or ch.isspace() for ch in s) / len(s) < 0.8:
                        continue
                    # tek karakterli parçalardan oluşan gürültüyü ele
                    if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]{2,}", s):
                        continue
                    seen.add(s)
                    strings.append(s)
                # Anlamlı olanları öne al (boşluk içerenler / büyük harfle başlayanlar)
                strings.sort(key=lambda x: (0 if " " in x else 1, -len(x)))
                out["strings"] = strings[:50]
    except Exception as e:  # noqa: BLE001
        out["note"] = f"çözümleme hatası: {e}"
    return out


# ---------------------------------------------------------------------------
# Erişilebilirlik testleri
# ---------------------------------------------------------------------------

def _test_site(url: str, timeout: int = 12) -> Dict[str, Any]:
    status = utils.http_get_status(url, timeout=timeout)
    if 200 <= status < 400:
        state = "ok"
    elif status in (401, 403, 429, 451, 503):
        state = "protected"   # erişilebilir ama bot korumalı (Cloudflare vb.)
    else:
        state = "dead"        # 0 (bağlantı yok) veya 4xx/5xx
    return {
        "url": url, "host": _host_of(url), "http_status": status,
        "ok": state == "ok", "state": state,
    }


# ---------------------------------------------------------------------------
# Ana analiz
# ---------------------------------------------------------------------------

def _download_cs3_cached(cfg: Config, url: str, dest: str) -> bool:
    if os.path.exists(dest) and os.path.getsize(dest) > 200 and zipfile.is_zipfile(dest):
        return True
    for ua in (utils.CLOUDSTREAM_UA, utils.DEFAULT_UA):
        if utils.download_file(url, dest, ua=ua, timeout=45):
            if zipfile.is_zipfile(dest) and os.path.getsize(dest) > 200:
                return True
            try:
                os.remove(dest)
            except OSError:
                pass
    return False


def inspect_upstream(
    cfg: Config,
    source_repo: Optional[str] = None,
    *,
    download_cs3: bool = True,
    download_icons: bool = True,
    test_sites: bool = True,
    max_workers: int = 12,
    progress: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """
    Verilen upstream linkini baştan sona analiz eder ve kapsamlı bir rapor döner.

    Hiçbir şeyi DEĞİŞTİRMEZ; yalnızca okur/indirir ve rapor üretir.
    """
    source_repo = source_repo or cfg.source_repo or DEFAULT_SOURCE_REPO
    repos_db_url, manifest_url = derive_source_urls(source_repo)

    inspect_dir = cfg.data_dir("inspect")
    cs3_dir = os.path.join(inspect_dir, "cs3")
    assets_dir = os.path.join(inspect_dir, "assets")
    os.makedirs(cs3_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    utils.title("Kaynak Depo Analizi (Upstream Inspector)")
    utils.info(f"Kaynak depo : {source_repo}")
    utils.info(f"repos-db    : {repos_db_url}")
    utils.info(f"repo.json   : {manifest_url}")

    # --- 1) Depo adreslerini bul -----------------------------------------
    utils.step("1) Depo adresleri bulunuyor")
    repo_urls: List[str] = []
    db = utils.http_get_json(repos_db_url)
    if isinstance(db, list):
        repo_urls = [u for u in db if isinstance(u, str)]
    elif isinstance(db, dict):
        for key in ("repos", "urls", "pluginLists", "repositories"):
            if isinstance(db.get(key), list):
                repo_urls = [u for u in db[key] if isinstance(u, str)]
                break
    # Manifest'i de ekle
    if manifest_url not in repo_urls:
        repo_urls.insert(0, manifest_url)
    # Tekilleştir
    seen = set()
    repo_urls = [u for u in repo_urls if not (u in seen or seen.add(u))]
    utils.ok(f"{len(repo_urls)} depo adresi bulundu.")

    # --- 2) Depoları ve eklentileri çöz ----------------------------------
    utils.step("2) Depolar ve eklenti listeleri çözümleniyor")
    repos_out: List[Dict[str, Any]] = []
    plugin_refs: List[mirror_mod.PluginRef] = []
    for rurl in repo_urls:
        ref = mirror_mod.discover_repo(cfg, rurl)
        if ref.ok:
            mirror_mod.discover_plugins(cfg, ref)
            utils.ok(f"{ref.name or rurl}: {len(ref.plugins)} eklenti")
        else:
            utils.warn(f"Atlandı: {rurl} ({ref.note})")
        repos_out.append({
            "repo_json": ref.repo_url,
            "name": ref.name,
            "description": ref.description,
            "icon_url": ref.icon_url,
            "plugin_list_urls": ref.plugin_list_urls,
            "plugin_count": len(ref.plugins),
            "ok": ref.ok,
            "note": ref.note,
        })
        plugin_refs.extend(ref.plugins)

    # internalName ile tekilleştir (en yüksek sürüm)
    dedup: Dict[str, mirror_mod.PluginRef] = {}
    for p in plugin_refs:
        k = p.internal_name
        if k not in dedup or p.version > dedup[k].version:
            dedup[k] = p
    plugin_refs = list(dedup.values())
    utils.ok(f"Toplam {len(plugin_refs)} benzersiz eklenti analiz edilecek.")

    # --- 3) Her eklentiyi incele -----------------------------------------
    utils.step("3) Eklentiler inceleniyor (.cs3 içeriği + çalışma testi)")
    plugins_out: List[Dict[str, Any]] = []

    for i, pl in enumerate(plugin_refs, 1):
        d = dict(pl.data)
        entry: Dict[str, Any] = {
            "internal_name": pl.internal_name,
            "name": pl.name,
            "version": pl.version,
            "plugin_class_name": d.get("pluginClassName", ""),
            "description": d.get("description", ""),
            "authors": d.get("authors", []) or [],
            "language": d.get("language", ""),
            "status": d.get("status", 0),
            "tv_types": d.get("tvTypes", []) or [],
            "api_version": d.get("apiVersion", 0),
            "icon_url": d.get("iconUrl", ""),
            "icon_local": "",
            "icon_ok": False,
            "url": pl.original_url,
            "file_size": d.get("fileSize", 0),
            "file_hash": d.get("fileHash", ""),
            "repository_url": pl.repo_html,
            "cs3_ok": False,
            "cs3_note": "",
            "manifest": {},
            "requires_resources": False,
            "primary_site": "",
            "sites": [],
            "all_urls": [],
            "classes": [],
            "strings": [],
            "entries": [],
        }

        # .cs3 indir + içerik çöz
        if download_cs3 and pl.original_url:
            fname = os.path.basename(urlparse(pl.original_url).path) or f"{pl.internal_name}.cs3"
            if not fname.endswith(".cs3"):
                fname = f"{pl.internal_name}.cs3"
            dest = os.path.join(cs3_dir, fname)
            got = _download_cs3_cached(cfg, pl.original_url, dest)
            if got:
                entry["cs3_ok"] = True
                entry["file_size"] = os.path.getsize(dest)
                contents = extract_cs3_contents(dest)
                entry["manifest"] = contents["manifest"]
                entry["requires_resources"] = bool(contents["manifest"].get("requiresResources"))
                entry["all_urls"] = contents["urls"]
                entry["classes"] = contents["classes"]
                entry["strings"] = contents["strings"]
                entry["entries"] = contents["entries"]
                entry["sites"] = [
                    {"url": u, "host": _host_of(u), "role": _site_role(_host_of(u)),
                     "ok": None, "state": "untested", "http_status": 0}
                    for u in contents["sites"]
                ]
                mains = [s["url"] for s in entry["sites"] if s["role"] == "main"]
                entry["primary_site"] = mains[0] if mains else (entry["sites"][0]["url"] if entry["sites"] else "")
            else:
                entry["cs3_note"] = "indirilemedi (korumalı/erişilemez)"
        else:
            entry["cs3_note"] = "indirme kapalı"

        # İkon indir
        if download_icons and entry["icon_url"]:
            iurl = entry["icon_url"]
            if iurl.startswith("http"):
                iname = os.path.basename(urlparse(iurl).path) or f"{pl.internal_name}.png"
                idest = os.path.join(assets_dir, iname)
                if os.path.exists(idest) or utils.download_file(iurl, idest, timeout=25):
                    entry["icon_local"] = iname
                    entry["icon_ok"] = os.path.exists(idest) and os.path.getsize(idest) > 0

        plugins_out.append(entry)
        mark = "✓" if entry["cs3_ok"] else "✗"
        nsites = len(entry["sites"])
        progress(f"    [{i}/{len(plugin_refs)}] {mark} {pl.name} — {nsites} site")

    # --- 4) Siteleri toplu test et (paralel) -----------------------------
    site_total = 0
    site_working = 0
    site_protected = 0
    if test_sites:
        utils.step("4) Siteler erişilebilirlik açısından test ediliyor")
        tasks: List[Tuple[int, int, str]] = []
        for pi, entry in enumerate(plugins_out):
            for si, s in enumerate(entry["sites"]):
                tasks.append((pi, si, s["url"]))
        site_total = len(tasks)
        if tasks:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futs = {ex.submit(_test_site, u): (pi, si) for (pi, si, u) in tasks}
                done = 0
                for fut in as_completed(futs):
                    pi, si = futs[fut]
                    res = fut.result()
                    plugins_out[pi]["sites"][si]["ok"] = res["ok"]
                    plugins_out[pi]["sites"][si]["state"] = res["state"]
                    plugins_out[pi]["sites"][si]["http_status"] = res["http_status"]
                    if res["state"] == "ok":
                        site_working += 1
                    elif res["state"] == "protected":
                        site_protected += 1
                    done += 1
                    if done % 50 == 0 or done == site_total:
                        progress(f"    site testi: {done}/{site_total}")
        utils.ok(
            f"{site_working} açık + {site_protected} korumalı / {site_total} site test edildi."
        )

    # --- 5) Özet ve kayıt ------------------------------------------------
    working = sum(1 for e in plugins_out if e["cs3_ok"])
    icons = sum(1 for e in plugins_out if e["icon_ok"])
    report: Dict[str, Any] = {
        "generated_at": int(time.time()),
        "source_repo": source_repo,
        "repos_db_url": repos_db_url,
        "manifest_url": manifest_url,
        "summary": {
            "total_repos": len(repos_out),
            "total_plugins": len(plugins_out),
            "working": working,
            "broken": len(plugins_out) - working,
            "icons": icons,
            "sites_total": site_total,
            "sites_working": site_working,
            "sites_protected": site_protected,
        },
        "repos": repos_out,
        "plugins": plugins_out,
    }

    utils.step("5) Rapor kaydediliyor")
    utils.write_json(os.path.join(inspect_dir, "inspect.json"), report)
    utils.write_json(cfg.data_dir("inspect.json"), report)
    utils.ok(
        f"Analiz tamamlandı: {len(plugins_out)} eklenti, {working} çalışıyor, "
        f"{icons} ikon, {site_working} açık + {site_protected} korumalı site."
    )
    return report


def load_inspect_report(cfg: Config) -> Optional[Dict[str, Any]]:
    return utils.read_json(cfg.data_dir("inspect.json"))
