# -*- coding: utf-8 -*-
"""
publisher.py — Üretilen çıktıyı (ayna veya eklenti projesi) kendi GitHub hesabına yükler.

Yaptığı işler:
  1) GitHub API ile depo yoksa oluşturur (token ile).
  2) Yerelde git deposu başlatır, 'main' dalını hazırlar.
  3) Boş bir 'builds' dalı açar (Actions bu dala .cs3 dosyalarını yazar).
  4) Her iki dalı da GitHub'a gönderir.

Böylece GitHub Actions devreye girer ve .cs3 dosyaları bulutta derlenir.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Optional, Tuple

from . import utils
from .config import Config


# ----------------------------------------------------------------------------
# Git yardımcıları
# ----------------------------------------------------------------------------

def _run(args, cwd: str, *, check: bool = True, env: Optional[dict] = None) -> Tuple[int, str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, env=full_env
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if check and proc.returncode != 0:
        raise RuntimeError(f"Komut başarısız: {' '.join(args)}\n{out}")
    return proc.returncode, out


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:  # noqa: BLE001
        return False


# ----------------------------------------------------------------------------
# GitHub API
# ----------------------------------------------------------------------------

def _api_request(method: str, path: str, token: str, body: Optional[dict] = None) -> Tuple[int, dict]:
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "WioForge")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:  # noqa: BLE001
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def ensure_github_repo(cfg: Config, *, private: bool = False) -> bool:
    """Depo yoksa oluşturur. Başarılıysa True."""
    if not cfg.github_token:
        utils.warn("GitHub token ayarlı değil; depo otomatik oluşturulamaz.")
        return False
    if not cfg.github_user:
        utils.warn("GitHub kullanıcı adı ayarlı değil.")
        return False

    # Kullanıcı adını doğrula
    status, me = _api_request("GET", "/user", cfg.github_token)
    if status != 200 or not me.get("login"):
        utils.err("GitHub token doğrulanamadı.")
        return False
    if cfg.github_user.lower() != me["login"].lower():
        utils.err("GitHub kullanıcı adı token hesabıyla eşleşmiyor.")
        return False
    utils.ok(f"GitHub kullanıcısı doğrulandı: {me['login']}")

    # Depo var mı?
    status, existing = _api_request("GET", f"/repos/{cfg.github_user}/{cfg.repo_name}", cfg.github_token)
    if status == 200:
        if private and not existing.get("private"):
            utils.err("Bu depo herkese açık. Worker koruması için GitHub ayarlarından önce depoyu private yapın.")
            return False
        utils.info(f"Depo zaten var: {cfg.repo_html_url}")
        return True
    if status != 404:
        utils.err(f"GitHub deposu kontrol edilemedi (HTTP {status}).")
        return False

    # Oluştur
    utils.info(f"Depo oluşturuluyor: {cfg.repo_name}")
    status, resp = _api_request(
        "POST",
        "/user/repos",
        cfg.github_token,
        {
            "name": cfg.repo_name,
            "description": cfg.repo_description,
            "private": private,
            "auto_init": False,
            "has_issues": True,
        },
    )
    if status in (200, 201):
        utils.ok(f"Depo oluşturuldu: {cfg.repo_html_url}")
        return True
    utils.err(f"Depo oluşturulamadı: {resp.get('message', resp)}")
    return False


# ----------------------------------------------------------------------------
# Yerel git deposu hazırlama
# ----------------------------------------------------------------------------

def _prepare_local_repo(cfg: Config, project_dir: str) -> None:
    """project_dir içinde git deposu + main + builds dallarını hazırlar."""
    if not _git_available():
        raise RuntimeError("git bulunamadı. Lütfen git kurun (https://git-scm.com).")

    # git init
    if not os.path.isdir(os.path.join(project_dir, ".git")):
        _run(["git", "init", "-b", cfg.default_branch], project_dir, check=False)
        _run(["git", "config", "user.email", "wioforge@local"], project_dir, check=False)
        _run(["git", "config", "user.name", "WioForge"], project_dir, check=False)

    # main dalı: tüm proje
    _run(["git", "add", "-A"], project_dir)
    _run(["git", "commit", "-m", "WioForge: ilk sürüm"], project_dir, check=False)

    # builds dalı (orphan) — Actions'ın yazacağı dal
    rc, branches = _run(["git", "branch", "--list"], project_dir, check=False)
    if "builds" not in branches:
        utils.info("'builds' dalı oluşturuluyor (Actions çıktıları buraya yazılacak)")
        _run(["git", "checkout", "--orphan", "builds"], project_dir, check=False)
        _run(["git", "rm", "-rf", "--cached", "."], project_dir, check=False)
        # Başlangıç dosyaları
        assets = os.path.join(project_dir, "builds_assets")
        os.makedirs(assets, exist_ok=True)
        utils.write_text(os.path.join(project_dir, "README.md"), "# builds dalı\n\nBu dal GitHub Actions tarafından otomatik doldurulur.\n")
        # repo.json iskeleti
        repo_json = {
            "name": f"{cfg.repo_name}",
            "description": cfg.repo_description,
            "manifestVersion": 1,
            "iconUrl": f"{cfg.raw_builds_base}/assets/logo.png" if cfg.raw_builds_base else "",
            "pluginLists": [f"{cfg.raw_builds_base}/plugins.json"] if cfg.raw_builds_base else ["plugins.json"],
        }
        utils.write_json(os.path.join(project_dir, "repo.json"), repo_json)
        utils.write_json(os.path.join(project_dir, "plugins.json"), [])
        utils.write_json(os.path.join(project_dir, "repos-db.json"), [f"{cfg.raw_builds_base}/repo.json"] if cfg.raw_builds_base else ["repo.json"])
        _run(["git", "add", "-A"], project_dir)
        _run(["git", "commit", "-m", "WioForge: builds dalı başlangıcı"], project_dir, check=False)
        _run(["git", "checkout", cfg.default_branch], project_dir, check=False)


def _set_remote(cfg: Config, project_dir: str) -> None:
    if not cfg.github_user:
        return
    if cfg.github_token:
        remote = f"https://{cfg.github_user}:{cfg.github_token}@github.com/{cfg.github_user}/{cfg.repo_name}.git"
    else:
        remote = f"https://github.com/{cfg.github_user}/{cfg.repo_name}.git"
    _run(["git", "remote", "remove", "origin"], project_dir, check=False)
    _run(["git", "remote", "add", "origin", remote], project_dir, check=False)


def push_all(cfg: Config, project_dir: str) -> bool:
    """main ve builds dallarını GitHub'a gönderir."""
    if not cfg.github_user or not cfg.repo_name:
        utils.err("GitHub kullanıcı adı/depo adı eksik. Önce 'wioforge init' ile ayarla.")
        return False

    _set_remote(cfg, project_dir)
    ok_any = True
    for branch in (cfg.default_branch, cfg.builds_branch):
        rc, out = _run(
            ["git", "push", "-u", "origin", branch, "--force"],
            project_dir,
            check=False,
        )
        if rc == 0:
            utils.ok(f"'{branch}' dalı gönderildi.")
        else:
            ok_any = False
            utils.err(f"'{branch}' dalı gönderilemedi:\n{out.strip()[-400:]}")
    return ok_any


# ----------------------------------------------------------------------------
# Yüksek seviye yayınlama
# ----------------------------------------------------------------------------

def publish(cfg: Config, project_dir: str, *, create_repo: bool = True) -> bool:
    """Bir projeyi (ayna veya eklenti) GitHub'a yükler."""
    utils.title(f"GitHub'a yayınlanıyor: {cfg.repo_html_url or cfg.repo_name}")
    if not os.path.isdir(project_dir):
        utils.err(f"Klasör bulunamadı: {project_dir}")
        return False

    if create_repo and cfg.github_token:
        ensure_github_repo(cfg)

    _prepare_local_repo(cfg, project_dir)
    success = push_all(cfg, project_dir)

    if success:
        utils.ok("Yayınlama tamamlandı!")
        utils.info(f"Depo: {cfg.repo_html_url}")
        utils.info("GitHub Actions birkaç dakika içinde .cs3 dosyalarını derleyecek.")
        utils.info(
            f"CloudStream depo adresi (Actions bittikten sonra): "
            f"{cfg.raw_builds_base}/repo.json"
        )
    return success


TOOLKIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# main dalına kopyalanacak araç dosyaları/klasörleri
_TOOLKIT_ITEMS = [
    "wioforge.py",
    "wioforge",
    "templates",
    "README.md",
    "KURULUM.md",
    "KULLANIM.md",
    "baslat.sh",
    "baslat.bat",
    "panel-baslat.sh",
    "panel-baslat.bat",
]


def _stage_toolkit(dest: str, cfg: Config) -> None:
    """WioForge araç setini + yapılandırmayı main dalı için hazırlar."""
    import shutil

    os.makedirs(dest, exist_ok=True)
    for item in _TOOLKIT_ITEMS:
        src = os.path.join(TOOLKIT_ROOT, item)
        if not os.path.exists(src):
            continue
        target = os.path.join(dest, item)
        if os.path.isdir(src):
            shutil.copytree(
                src, target, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "jobs"),
            )
        else:
            shutil.copy2(src, target)

    # Yapılandırma (token'sız — Actions kendi GITHUB_TOKEN'ını kullanır)
    cfg_data = {
        "github_user": cfg.github_user,
        "github_token": "",
        "repo_name": cfg.repo_name,
        "repo_description": cfg.repo_description,
        "default_branch": cfg.default_branch,
        "builds_branch": cfg.builds_branch,
        "source_repo": cfg.source_repo,
        "repos_db_url": cfg.repos_db_url,
        "manifest_url": cfg.manifest_url,
        "work_dir": cfg.work_dir,
        "protected_policy": cfg.protected_policy,
        "proxy_base_url": cfg.proxy_base_url,
        "server_port": cfg.server_port,
        "plugin_author": cfg.plugin_author or cfg.github_user,
        "plugin_language": cfg.plugin_language,
        "plugin_status": cfg.plugin_status,
    }
    utils.write_json(os.path.join(dest, "wioforge.json"), cfg_data)

    # Aynalanan depo kendi kendine upstream çekmez. Kaynağı yeniden aynalamak
    # yalnızca kullanıcı panelden/CLI'dan açıkça istediğinde yapılır.


def _copy_mirror_to_builds(mirror_dir: str, dest: str) -> None:
    """Ayna çıktısını (repo.json, plugins.json, .cs3, assets) builds dalına kopyalar."""
    import shutil

    os.makedirs(dest, exist_ok=True)
    for item in ("repo.json", "plugins.json", "repos-db.json", "plugins", "assets"):
        src = os.path.join(mirror_dir, item)
        if not os.path.exists(src):
            continue
        target = os.path.join(dest, item)
        if os.path.isdir(src):
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            shutil.copy2(src, target)


def publish_mirror(cfg: Config) -> bool:
    """
    Aynalanan depoyu yayınlar.

    Yapı:
      * 'main'  dalı : araç seti + yapılandırma (upstream zamanlayıcısı yok)
      * 'builds' dalı: hazır (derlenmiş) .cs3 dosyaları + repo.json + plugins.json + assets

    Böylece:
      - CloudStream depo adresi : .../builds/repo.json
      - Yalnızca aynalanmış katalog ve dosyalar yayımlanır; upstream görevi eklenmez.
    """
    mirror_dir = cfg.data_dir("mirror")
    if not os.path.isdir(mirror_dir):
        utils.err("Önce 'wioforge mirror' çalıştırın (ayna yok).")
        return False
    if not os.path.exists(os.path.join(mirror_dir, "repo.json")):
        utils.err("Ayna eksik görünüyor (repo.json yok). 'wioforge mirror' çalıştırın.")
        return False

    if not _git_available():
        utils.err("git bulunamadı. Lütfen git kurun (https://git-scm.com).")
        return False

    utils.title(f"GitHub'a yayınlanıyor (ayna): {cfg.repo_html_url or cfg.repo_name}")

    if cfg.github_token:
        ensure_github_repo(cfg)

    # Geçici bir çalışma deposu kur
    import tempfile
    import shutil

    work = tempfile.mkdtemp(prefix="wioforge_publish_")
    try:
        # --- main dalı: araç seti ---
        _run(["git", "init", "-b", cfg.default_branch], work, check=False)
        _run(["git", "config", "user.email", "wioforge@local"], work, check=False)
        _run(["git", "config", "user.name", "WioForge"], work, check=False)
        _stage_toolkit(work, cfg)
        _run(["git", "add", "-A"], work)
        _run(["git", "commit", "-m", "WioForge: ayna kaynak deposu"], work, check=False)

        # --- builds dalı: hazır ayna çıktısı ---
        utils.info("'builds' dalı hazırlanıyor (hazır .cs3 dosyaları)")
        _run(["git", "checkout", "--orphan", cfg.builds_branch], work, check=False)
        _run(["git", "rm", "-rf", "--cached", "."], work, check=False)
        # main'den kalan dosyaları fiziksel olarak temizle
        for entry in os.listdir(work):
            if entry == ".git":
                continue
            p = os.path.join(work, entry)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except OSError:
                    pass
        _copy_mirror_to_builds(mirror_dir, work)
        utils.write_text(
            os.path.join(work, "README.md"),
            "# builds dalı\n\nBu dal WioForge tarafından oluşturulan bağımsız CloudStream deposudur.\n"
            "Hazır `.cs3` dosyaları ve `repo.json` burada barınır. WioLand kapansa dahi çalışır.\n",
        )
        _run(["git", "add", "-A"], work)
        _run(["git", "commit", "-m", "WioForge: ayna çıktısı (builds)"], work, check=False)

        # --- gönder ---
        _set_remote(cfg, work)
        ok = True
        for branch in (cfg.default_branch, cfg.builds_branch):
            rc, out = _run(["git", "push", "-u", "origin", branch, "--force"], work, check=False)
            if rc == 0:
                utils.ok(f"'{branch}' dalı gönderildi.")
            else:
                ok = False
                utils.err(f"'{branch}' dalı gönderilemedi:\n{out.strip()[-400:]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if ok:
        utils.ok("Ayna yayınlandı!")
        utils.info(f"Depo: {cfg.repo_html_url}")
        utils.info(f"CloudStream depo adresi: {cfg.raw_builds_base}/repo.json")
        utils.info("Yayınlanan katalog ve .cs3 dosyaları bu GitHub deposundan sunulur; otomatik upstream güncellemesi kurulmadı.")
    return ok
