# -*- coding: utf-8 -*-
"""
mirror.py — WioLand ve bağlı depoları bulur, aynalar ve otomatik günceller.

Akış:
  repos-db.json  ->  [repo.json ...]  ->  plugins.json  ->  kendi GitHub'ındaki .cs3

Kaynak bağlantıları yalnızca ilk aynalama sırasında girdi olarak kullanılır.
İndirilebilen .cs3 ve ikonlar kullanıcının kendi deposuna alınır; indirilemeyen
eklenti dış adresle kataloğa eklenmez. Eklenti kodunun çağırdığı video/API
servisleri ayrıca kaynak eklentiye bağlı kalabilir.

Böylece WioLand kapansa dahi bu ayna çalışmaya devam eder.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field, asdict, replace
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from . import utils
from .config import Config, WIO_URL_PATTERNS, DEFAULT_SOURCE_REPO


# ----------------------------------------------------------------------------
# Veri modeli
# ----------------------------------------------------------------------------

@dataclass
class PluginRef:
    """Bir eklenti kaydı ve kaynak bilgisi."""
    internal_name: str
    name: str
    version: int
    original_url: str          # .cs3 indirme adresi (orijinal)
    repo_html: str             # ait olduğu kaynak depo (orijinal)
    data: Dict[str, Any] = field(default_factory=dict)
    downloaded: bool = False
    local_file: str = ""
    sha256: str = ""
    file_size: int = 0
    note: str = ""


@dataclass
class RepoRef:
    """Bir upstream depo (repo.json) ve kaynak bilgisi."""
    repo_url: str              # orijinal repo.json adresi
    name: str = ""
    description: str = ""
    icon_url: str = ""
    plugin_list_urls: List[str] = field(default_factory=list)
    plugins: List[PluginRef] = field(default_factory=list)
    ok: bool = True
    note: str = ""


# ----------------------------------------------------------------------------
# Keşif (discovery)
# ----------------------------------------------------------------------------

def discover_repo_urls(cfg: Config) -> List[str]:
    """Seçilen kaynağın depo listesini veya doğrudan manifestini çözümler."""
    from .inspector import derive_source_urls

    db_url, manifest_url = cfg.repos_db_url, cfg.manifest_url
    if cfg.source_repo.strip().rstrip("/") != DEFAULT_SOURCE_REPO:
        db_url, manifest_url = derive_source_urls(cfg.source_repo)
    utils.step("1) Orijinal depo adresleri bulunuyor")
    utils.info(f"Kaynak: {db_url}")

    data = utils.http_get_json(db_url)
    urls: List[str] = []

    if isinstance(data, list):
        urls = [u for u in data if isinstance(u, str)]
    elif isinstance(data, dict):
        # Bazı depolar {"repos": [...]} biçiminde olabilir
        for key in ("repos", "urls", "repositories"):
            if isinstance(data.get(key), list):
                urls = [u for u in data[key] if isinstance(u, str)]
                break

        # Doğrudan repo.json verilmiş olabilir; pluginLists depo değil,
        # eklenti listesi adresleri içerir.
        if "pluginLists" in data or "plugins" in data:
            urls.insert(0, db_url)

    if manifest_url not in urls:
        manifest = data if manifest_url == db_url else utils.http_get_json(manifest_url)
        if isinstance(manifest, dict) and ("pluginLists" in manifest or "plugins" in manifest):
            urls.insert(0, manifest_url)

    if not urls:
        raise ValueError(f"Kaynakta okunabilir bir depo listesi veya repo.json bulunamadı: {cfg.source_repo}")

    # Tekrarları kaldır, sırayı koru
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    utils.ok(f"{len(unique)} orijinal depo adresi bulundu.")
    for u in unique:
        print(f"    • {u}")
    return unique


def discover_repo(cfg: Config, repo_url: str) -> RepoRef:
    """Tek bir repo.json'u çeker ve içindeki plugin listesi adreslerini bulur."""
    ref = RepoRef(repo_url=repo_url)
    manifest = utils.http_get_json(repo_url)
    if not isinstance(manifest, dict):
        ref.ok = False
        ref.note = "repo.json okunamadı"
        return ref

    ref.name = manifest.get("name", "") or ""
    ref.description = manifest.get("description", "") or ""
    ref.icon_url = manifest.get("iconUrl", "") or ""
    lists = manifest.get("pluginLists") or manifest.get("plugins") or []
    if isinstance(lists, str):
        lists = [lists]
    ref.plugin_list_urls = [u for u in lists if isinstance(u, str)]
    return ref


def discover_plugins(cfg: Config, repo: RepoRef) -> None:
    """Bir deponun plugin listelerini çeker ve eklenti kayıtlarını doldurur."""
    for plist_url in repo.plugin_list_urls:
        plugins = utils.http_get_json(plist_url)
        if not isinstance(plugins, list):
            continue
        for p in plugins:
            if not isinstance(p, dict):
                continue
            url = p.get("url", "")
            if not url:
                continue
            internal = p.get("internalName") or p.get("name") or "plugin"
            repo.plugins.append(
                PluginRef(
                    internal_name=internal,
                    name=p.get("name", internal),
                    version=int(p.get("version", 1) or 1),
                    original_url=url,
                    repo_html=p.get("repositoryUrl", "") or repo.repo_url,
                    data=dict(p),
                )
            )


# ----------------------------------------------------------------------------
# URL yeniden yazma
# ----------------------------------------------------------------------------

def is_wio_url(url: str) -> bool:
    return any(pat in url for pat in WIO_URL_PATTERNS)


def rewrite_url(cfg: Config, url: str, *, kind: str = "generic", local_name: str = "") -> str:
    """
    Orijinal URL'i kullanıcının KENDİ deposuna göre yeniden yazar.

    GitHub kullanıcı adı ayarlıysa mutlak raw adresi üretir:
        https://raw.githubusercontent.com/<user>/<repo>/<branch>/plugins/x.cs3
    Ayarlı değilse yerel test için göreli yol üretir:
        plugins/x.cs3

    kind:
      'icon'  -> ikonlar (assets/)
      'cs3'   -> eklenti dosyaları (plugins/)
      'other' -> diğer
    """
    if not url:
        return url

    # Ayna çıktısı 'builds' dalında yayınlanır; bağlantılar oraya işaret etmeli.
    base = cfg.raw_builds_base  # "" olabilir (yerel test)
    prefix = f"{base}/" if base else ""

    # İkonları kendi assets klasörüne yönlendir
    if kind == "icon" or re.search(r"\.(png|jpe?g|webp|svg|gif)(\?|$)", url, re.I):
        fname = os.path.basename(urlparse(url).path) or "icon.png"
        return f"{prefix}assets/{fname}"

    # .cs3 dosyalarını kendi plugins klasörüne yönlendir
    if kind == "cs3" or url.endswith(".cs3") or ".cs3?" in url:
        fname = local_name or os.path.basename(urlparse(url).path) or "plugin.cs3"
        return f"{prefix}plugins/{fname}"

    return url


# ----------------------------------------------------------------------------
# Aynalama
# ----------------------------------------------------------------------------

def _try_download_cs3(cfg: Config, url: str, dest: str) -> bool:
    """Bir .cs3 dosyasını indirmeyi dener (birden çok UA ile)."""
    for ua in (utils.DEFAULT_UA, utils.CLOUDSTREAM_UA):
        if utils.download_file(url, dest, ua=ua, timeout=60):
            # Geçerli bir zip mi? (.cs3 aslında bir zip arşividir)
            try:
                import zipfile
                if zipfile.is_zipfile(dest) and os.path.getsize(dest) > 200:
                    return True
            except Exception:  # noqa: BLE001
                pass
            # zip değilse sil
            try:
                os.remove(dest)
            except OSError:
                pass
    return False


def mirror_all(cfg: Config, *, download: bool = True, progress=print, selected_urls=None) -> Dict[str, Any]:
    """
    Tüm upstream depoları aynalar. Sonuç: yerel bağımsız depo yapısı.

    Dönen değer: ayna özeti (mirror.json içeriği).
    """
    if not cfg.github_user or not cfg.repo_name:
        raise ValueError("Aynalama için önce kendi GitHub kullanıcı adını ve depo adını kaydedin.")

    cfg.ensure_dirs()
    mirror_dir = cfg.data_dir("mirror")
    plugins_dir = os.path.join(mirror_dir, "plugins")
    assets_dir = os.path.join(mirror_dir, "assets")
    os.makedirs(plugins_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    repo_urls = discover_repo_urls(cfg)
    repos: List[RepoRef] = []
    all_plugins: List[PluginRef] = []
    downloaded_count = 0
    skipped_count = 0

    utils.step("2) Depolar ve eklentiler çözümleniyor")
    for repo_url in repo_urls:
        repo = discover_repo(cfg, repo_url)
        if not repo.ok:
            utils.warn(f"Atlandı: {repo_url} ({repo.note})")
            repos.append(repo)
            continue
        discover_plugins(cfg, repo)
        utils.ok(f"{repo.name or repo_url}: {len(repo.plugins)} eklenti")
        repos.append(repo)
        all_plugins.extend(repo.plugins)

    # ------------------------------------------------------------------
    # Yinelenenleri ayıkla: aynı internalName varsa en yüksek sürümü tut
    # (CloudStream aynı internalName'li iki eklentiyi kuramaz.)
    # ------------------------------------------------------------------
    if selected_urls is not None:
        selected = set(selected_urls)
        all_plugins = [p for p in all_plugins if p.original_url in selected]
        if not all_plugins:
            raise ValueError("Seçilen eklentiler kaynakta bulunamadı. Listeyi yenileyin.")
    dedup: Dict[str, PluginRef] = {}
    dropped = 0
    for pl in all_plugins:
        key = pl.internal_name
        if key in dedup:
            if pl.version > dedup[key].version:
                dedup[key] = pl
            dropped += 1
        else:
            dedup[key] = pl
    if dropped:
        utils.info(f"{dropped} yinelenen eklenti ayıklandı (aynı internalName).")
    all_plugins = list(dedup.values())

    utils.step("3) Eklenti dosyaları (.cs3) indiriliyor ve yeniden yazılıyor")
    used_names: set = set()
    for pl in all_plugins:
        base_name = os.path.basename(urlparse(pl.original_url).path) or f"{pl.internal_name}.cs3"
        if not base_name.endswith(".cs3"):
            base_name = f"{pl.internal_name}.cs3"
        # Benzersiz ad üret (çakışma olursa sonuna sayaç ekle)
        fname = base_name
        counter = 2
        while fname in used_names:
            stem = base_name[:-4]
            fname = f"{stem}-{counter}.cs3"
            counter += 1
        used_names.add(fname)
        dest = os.path.join(plugins_dir, fname)
        pl.local_file = fname

        if download:
            # Önbellek: dosya zaten varsa ve geçerli bir zip ise yeniden indirme
            if os.path.exists(dest) and os.path.getsize(dest) > 200:
                try:
                    import zipfile
                    if zipfile.is_zipfile(dest):
                        pl.downloaded = True
                        pl.sha256 = utils.sha256_file(dest)
                        pl.file_size = os.path.getsize(dest)
                        downloaded_count += 1
                        progress(f"    = {fname} (önbellekten)")
                        continue
                except Exception:  # noqa: BLE001
                    pass
            got = _try_download_cs3(cfg, pl.original_url, dest)
            if got:
                pl.downloaded = True
                pl.sha256 = utils.sha256_file(dest)
                pl.file_size = os.path.getsize(dest)
                downloaded_count += 1
                progress(f"    ↓ {fname} ({utils.human_size(pl.file_size)})")
                continue
            else:
                # İndirilemedi (ör. worker korumalı)
                pl.note = "indirilemedi; dış adres bırakmamak için atlandı"
                skipped_count += 1
                utils.warn(f"    ⚠ {fname}: {pl.note}")

    if not download:
        for pl in all_plugins:
            if not pl.downloaded:
                pl.note = "indirme kapalı; harici URL ile kataloğa eklenmedi"
                skipped_count += 1

    # ------------------------------------------------------------------
    # Kendi repo.json / plugins.json / repos-db.json dosyalarını üret
    # ------------------------------------------------------------------
    utils.step("4) Bağımsız depo dosyaları oluşturuluyor")

    out_plugins: List[Dict[str, Any]] = []
    icon_downloads: Dict[str, str] = {}  # yerel_ad -> orijinal_url
    icon_refs: List[tuple] = []
    for pl in all_plugins:
        d = dict(pl.data)

        if pl.downloaded:
            new_url = rewrite_url(cfg, pl.original_url, kind="cs3", local_name=pl.local_file)
            d["url"] = new_url
            d["fileSize"] = pl.file_size
            d["fileHash"] = f"sha256-{pl.sha256}"
        else:
            continue  # Yerel .cs3 yoksa kataloğa harici indirme adresi koyma.

        # İkonu kendine yönlendir (orijinal adresi indirme için sakla)
        if d.get("iconUrl"):
            orig_icon = d["iconUrl"]
            if orig_icon.startswith("http"):
                new_icon = rewrite_url(cfg, orig_icon, kind="icon")
                fname = os.path.basename(urlparse(new_icon).path) or "icon.png"
                icon_downloads[fname] = orig_icon
                icon_refs.append((d, fname, new_icon))
            else:
                d.pop("iconUrl", None)

        # Kaynak depo bilgisini kendine çevir
        if cfg.repo_html_url:
            d["repositoryUrl"] = cfg.repo_html_url

        out_plugins.append(d)

    # İkonları indir (bağımsız olsun)
    if icon_downloads:
        utils.info(f"{len(icon_downloads)} ikon indiriliyor...")
        for fname, iurl in icon_downloads.items():
            idest = os.path.join(assets_dir, fname)
            if not os.path.exists(idest):
                if not utils.download_file(iurl, idest, timeout=30):
                    utils.warn(f"    ⚠ İkon indirilemedi ve harici adres kaldırıldı: {fname}")
        for plugin, fname, local_url in icon_refs:
            if os.path.isfile(os.path.join(assets_dir, fname)):
                plugin["iconUrl"] = local_url
            else:
                plugin.pop("iconUrl", None)

    # Depo logosunu da indir
    logo_src = "https://raw.githubusercontent.com/Wiojelt/WioLand/main/assets/logo.png"
    logo_dest = os.path.join(assets_dir, "logo.png")
    if not os.path.exists(logo_dest):
        utils.download_file(logo_src, logo_dest, timeout=30)

    plugins_json_path = os.path.join(mirror_dir, "plugins.json")
    utils.write_json(plugins_json_path, out_plugins)

    # repo.json (kendi manifestimiz) — 'builds' dalına işaret eder
    manifest = {
        "name": cfg.repo_name,
        "description": cfg.repo_description,
        "manifestVersion": 1,
        "pluginLists": [f"{cfg.raw_builds_base}/plugins.json"] if cfg.raw_builds_base else ["plugins.json"],
    }
    if os.path.isfile(logo_dest):
        manifest["iconUrl"] = f"{cfg.raw_builds_base}/assets/logo.png"
    utils.write_json(os.path.join(mirror_dir, "repo.json"), manifest)

    # repos-db.json (kendi alt depolarımızın listesi — hepsi kendi adresimize işaret eder)
    own_repos_db = [f"{cfg.raw_builds_base}/repo.json"] if cfg.raw_builds_base else ["repo.json"]
    utils.write_json(os.path.join(mirror_dir, "repos-db.json"), own_repos_db)

    # ------------------------------------------------------------------
    # Özet kaydet
    # ------------------------------------------------------------------
    summary = {
        "generated_at": int(time.time()),
        "source_repo": cfg.source_repo,
        "source_repos_db": cfg.repos_db_url,
        "github_user": cfg.github_user,
        "repo_name": cfg.repo_name,
        "total_repos": len(repos),
        "total_plugins": len(all_plugins),
        "downloaded": downloaded_count,
        "skipped": skipped_count,
        "repos": [
            {
                "repo_url": r.repo_url,
                "name": r.name,
                "description": r.description,
                "icon_url": r.icon_url,
                "plugin_list_urls": r.plugin_list_urls,
                "plugin_count": len(r.plugins),
                "ok": r.ok,
                "note": r.note,
            }
            for r in repos
        ],
        "plugins": [
            {
                "internal_name": p.internal_name,
                "name": p.name,
                "version": p.version,
                "original_url": p.original_url,
                "local_file": p.local_file,
                "downloaded": p.downloaded,
                "sha256": p.sha256,
                "file_size": p.file_size,
                "repo_html": p.repo_html,
                "note": p.note,
            }
            for p in all_plugins
        ],
    }
    utils.write_json(os.path.join(mirror_dir, "mirror.json"), summary)
    utils.write_json(cfg.data_dir("mirror.json"), summary)

    utils.ok(
        f"Ayna tamamlandı: {downloaded_count} eklenti indirildi, "
        f"{skipped_count} atlandı, toplam {len(all_plugins)} eklenti."
    )
    utils.info(f"Ayna klasörü: {mirror_dir}")
    return summary


def load_mirror_summary(cfg: Config) -> Optional[Dict[str, Any]]:
    return utils.read_json(cfg.data_dir("mirror.json"))


def list_original_addresses(cfg: Config, source: Optional[str] = None) -> Dict[str, Any]:
    """
    Hiçbir şey indirmeden yalnızca TÜM orijinal adresleri listeler.
    (Kullanıcının 'orijinal adresleri bul' isteğine doğrudan yanıt.)
    """
    if source and source.strip():
        cfg = replace(cfg, source_repo=source.strip())
    repo_urls = discover_repo_urls(cfg)
    result: Dict[str, Any] = {"repos": [], "plugins": []}
    for repo_url in repo_urls:
        repo = discover_repo(cfg, repo_url)
        discover_plugins(cfg, repo)
        result["repos"].append(
            {
                "repo_json": repo.repo_url,
                "name": repo.name,
                "icon": repo.icon_url,
                "plugin_lists": repo.plugin_list_urls,
            }
        )
        for pl in repo.plugins:
            result["plugins"].append(
                {
                    "name": pl.name,
                    "internalName": pl.internal_name,
                    "version": pl.version,
                    "original_url": pl.original_url,
                    "repositoryUrl": pl.repo_html,
                    "host": urlparse(pl.original_url).netloc,
                }
            )
    return result
