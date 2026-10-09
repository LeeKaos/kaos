# -*- coding: utf-8 -*-
"""builder.py — CloudStream-Builder entegrasyonu.

https://github.com/Wiojelt/CloudStream-Builder reposunu (yarı otonom açık
kaynak CloudStream eklenti oluşturucu) indirir, çözümler ve raporlar:

  * OCE JSON config'leri  (bildirimsel extractor kuralları)
  * OCE Kotlin extractor'ları
  * OCE çekirdek motorları (ConfigDrivenExtractor, Registry, Fallback ...)
  * Yerli (turk) extractor'lar
  * Referans rehberleri (kanıtlanmış depo desenleri, oynatma, HLS ...)
  * Yardımcı script'ler (audit_job, verify_repo_integrity ...)
  * SKILL.md / INDEX.md (workflow ve extractor kataloğu)

Böylece panel, hazır extractor kütüphanesini ve kanıtlanmış desenleri
görüntüleyebilir; eklenti üretirken bunlardan faydalanılabilir.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
import zipfile
from typing import Any, Dict, List, Optional

from . import utils

BUILDER_DEFAULT_REPO = "https://github.com/Wiojelt/CloudStream-Builder"
BUILDER_BRANCHES = ("main", "master")

# Kategori tanımları: (anahtar, etiket, yol deseni)
_CATEGORIES: List[tuple] = [
    ("oce_configs", "OCE JSON Config (bildirimsel extractor)", r"extractors/oce/configs/.*\.json$"),
    ("oce_kotlin", "OCE Kotlin Extractor", r"extractors/oce/kotlin/.*\.kt$"),
    ("oce_core", "OCE Çekirdek Motor", r"extractors/oce/core/.*\.kt$"),
    ("oce_docs", "OCE Dokümantasyon", r"extractors/oce/docs/.*"),
    ("turk", "Yerli (Türk) Extractor", r"extractors/turk/.*\.kt$"),
    ("references", "Referans Rehberi", r"references/.*\.md$"),
    ("scripts", "Yardımcı Script", r"scripts/.*"),
    ("skill", "Skill / Katalog", r"(SKILL\.md|agents/.*|extractors/INDEX\.md|README\.md)$"),
]

_INDEX_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.MULTILINE)


def _parse_owner_repo(url: str):
    m = re.search(r"github\.com/([^/]+)/([^/#?\s]+)", url or "")
    if not m:
        return None, None
    return m.group(1), m.group(2).replace(".git", "")


def _rel(path: str, base: str) -> str:
    return os.path.relpath(path, base).replace("\\", "/")


def _categorize(relpath: str) -> str:
    low = relpath.lower()
    for key, _label, pattern in _CATEGORIES:
        if re.search(pattern, low, re.IGNORECASE):
            return key
    return "other"


def _parse_index_md(text: str) -> List[Dict[str, Any]]:
    """INDEX.md tablolarından extractor → host eşlemesini çıkarır."""
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        m = _INDEX_ROW_RE.match(line.strip())
        if not m:
            continue
        c1, c2, c3 = m.group(1), m.group(2), m.group(3)
        if set(c1) <= set("-: "):  # başlık ayırıcı satırı
            continue
        names = [x for x in _BACKTICK_RE.findall(c1)]
        if not names:
            continue
        hosts = [x for x in _BACKTICK_RE.findall(c2)]
        if not hosts:
            hosts = [x.strip() for x in re.split(r"[,\s]+", c2) if "." in x and len(x) < 60]
        rows.append({
            "extractors": names,
            "hosts": [h for h in hosts if h],
            "note": re.sub(r"[*_`]", "", c3).strip(),
        })
    return rows


def _headings(text: str, limit: int = 20) -> List[str]:
    out = []
    for m in _HEADING_RE.finditer(text):
        out.append(m.group(2).strip())
        if len(out) >= limit:
            break
    return out


def _excerpt(text: str, limit: int = 4000) -> str:
    text = text.strip()
    return text[:limit] + ("\n..." if len(text) > limit else "")


def _extract_config_meta(path: str) -> Dict[str, Any]:
    data = utils.read_json(path, default=None)
    if not isinstance(data, dict):
        return {}
    return {
        "id": data.get("id") or os.path.splitext(os.path.basename(path))[0],
        "name": data.get("name") or data.get("id") or "",
        "main_url": data.get("mainUrl") or data.get("mainURL") or "",
        "steps": len(data.get("steps") or []),
        "variants": len(data.get("variants") or []),
    }


def fetch_builder(
    cfg,
    source_repo: Optional[str] = None,
    progress=print,
) -> Dict[str, Any]:
    """CloudStream-Builder deposunu indirir, çözümler ve rapor üretir."""
    source_repo = (source_repo or BUILDER_DEFAULT_REPO).strip()
    owner, repo = _parse_owner_repo(source_repo)
    if not owner or not repo:
        progress("[x] Geçersiz GitHub adresi: " + source_repo)
        return {"error": "invalid_url", "source_repo": source_repo}

    base = cfg.data_dir("builder")
    src_dir = os.path.join(base, "src")
    tmp_zip = os.path.join(base, "_download.zip")
    os.makedirs(base, exist_ok=True)

    progress(f"[i] CloudStream-Builder indiriliyor: {owner}/{repo}")
    ok = False
    used_branch = None
    for br in BUILDER_BRANCHES:
        url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{br}.zip"
        if utils.download_file(url, tmp_zip, timeout=180):
            ok = True
            used_branch = br
            break
    if not ok:
        progress("[x] Builder deposu indirilemedi (ağ/GitHub erişimi?).")
        return {"error": "download_failed", "source_repo": source_repo}

    progress("[i] Arşiv çıkarılıyor...")
    if os.path.isdir(src_dir):
        shutil.rmtree(src_dir, ignore_errors=True)
    os.makedirs(src_dir, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(tmp_zip) as z:
                z.extractall(tmp)
            entries = [e for e in os.listdir(tmp) if not e.startswith(".")]
            root = os.path.join(tmp, entries[0]) if len(entries) == 1 else tmp
            for item in os.listdir(root):
                shutil.move(os.path.join(root, item), os.path.join(src_dir, item))
    except Exception as e:  # noqa: BLE001
        progress(f"[x] Arşiv açılamadı: {e}")
        return {"error": "extract_failed", "message": str(e), "source_repo": source_repo}
    finally:
        try:
            os.remove(tmp_zip)
        except OSError:
            pass

    progress("[i] Dosyalar taranıyor ve sınıflandırılıyor...")
    report = _build_report(cfg, source_repo, owner, repo, used_branch, src_dir)
    utils.write_json(cfg.data_dir("builder", "builder.json"), report)
    utils.write_json(cfg.data_dir("builder.json"), report)
    progress(f"[+] Builder hazır: {report['total_files']} dosya, "
             f"{report['counts'].get('oce_configs', 0)} JSON config, "
             f"{report['counts'].get('turk', 0)} yerli extractor.")
    return report


def _build_report(cfg, source_repo, owner, repo, branch, src_dir) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    for dirpath, _dirs, filenames in os.walk(src_dir):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = _rel(full, src_dir)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            files.append({"path": rel, "size": size, "cat": _categorize(rel)})

    files.sort(key=lambda f: f["path"])
    counts: Dict[str, int] = {}
    cat_files: Dict[str, List[Dict[str, Any]]] = {}
    for f in files:
        counts[f["cat"]] = counts.get(f["cat"], 0) + 1
        cat_files.setdefault(f["cat"], []).append({"path": f["path"], "size": f["size"]})

    total_size = sum(f["size"] for f in files)

    # --- Extractor envanteri ---
    extractors: List[Dict[str, Any]] = []
    for f in files:
        if f["cat"] == "oce_configs":
            meta = _extract_config_meta(os.path.join(src_dir, f["path"]))
            extractors.append({
                "kind": "json-config",
                "name": meta.get("id") or os.path.splitext(os.path.basename(f["path"]))[0],
                "file": f["path"],
                "size": f["size"],
                "main_url": meta.get("main_url", ""),
                "steps": meta.get("steps", 0),
            })
        elif f["cat"] in ("oce_kotlin", "turk"):
            extractors.append({
                "kind": "kotlin" if f["cat"] == "oce_kotlin" else "turk",
                "name": os.path.splitext(os.path.basename(f["path"]))[0],
                "file": f["path"],
                "size": f["size"],
                "main_url": "",
                "steps": 0,
            })

    # --- Referans rehberleri ---
    references: List[Dict[str, Any]] = []
    for f in files:
        if f["cat"] == "references":
            text = utils.read_text(os.path.join(src_dir, f["path"]))
            references.append({
                "name": os.path.splitext(os.path.basename(f["path"]))[0],
                "file": f["path"],
                "size": f["size"],
                "headings": _headings(text),
            })

    # --- Script'ler ---
    scripts: List[Dict[str, Any]] = []
    for f in files:
        if f["cat"] == "scripts":
            ext = os.path.splitext(f["path"])[1].lstrip(".")
            scripts.append({"name": os.path.basename(f["path"]), "file": f["path"],
                            "size": f["size"], "lang": ext or "?"})

    # --- INDEX.md (extractor kataloğu) ---
    index_rows: List[Dict[str, Any]] = []
    index_file = None
    for f in files:
        if f["path"].lower().endswith("extractors/index.md"):
            index_file = f["path"]
            index_rows = _parse_index_md(utils.read_text(os.path.join(src_dir, f["path"])))
            break

    # --- README / SKILL özetleri ---
    readme_txt = ""
    skill_txt = ""
    for f in files:
        low = f["path"].lower()
        if low.endswith("readme.md") and not readme_txt:
            readme_txt = _excerpt(utils.read_text(os.path.join(src_dir, f["path"])))
        if low.endswith("skill.md") and not skill_txt:
            skill_txt = _excerpt(utils.read_text(os.path.join(src_dir, f["path"])))

    return {
        "source_repo": source_repo,
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "fetched_at": int(time.time()),
        "total_files": len(files),
        "total_size": total_size,
        "counts": counts,
        "categories": {k: {"label": label, "files": cat_files.get(k, [])}
                       for k, label, _p in _CATEGORIES},
        "files": files,
        "extractors": extractors,
        "references": references,
        "scripts": scripts,
        "index_rows": index_rows,
        "index_file": index_file,
        "readme_excerpt": readme_txt,
        "skill_excerpt": skill_txt,
    }


def load_builder_report(cfg) -> Optional[Dict[str, Any]]:
    """Kayıtlı builder raporunu okur (yoksa None)."""
    return (
        utils.read_json(cfg.data_dir("builder.json"), default=None)
        or utils.read_json(cfg.data_dir("builder", "builder.json"), default=None)
    )


def read_builder_file(cfg, relpath: str, max_bytes: int = 400_000) -> Optional[Dict[str, Any]]:
    """Builder kaynak klasöründeki bir dosyayı güvenle okur (path traversal korumalı)."""
    if not relpath:
        return None
    base = os.path.abspath(cfg.data_dir("builder", "src"))
    target = os.path.abspath(os.path.join(base, relpath))
    if target != base and not target.startswith(base + os.sep):
        return None
    if not os.path.isfile(target):
        return None
    try:
        size = os.path.getsize(target)
    except OSError:
        size = 0
    with open(target, "r", encoding="utf-8", errors="replace") as f:
        data = f.read(max_bytes)
    return {
        "path": relpath,
        "size": size,
        "truncated": size > max_bytes,
        "content": data,
    }
