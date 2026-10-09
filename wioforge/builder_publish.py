"""Builder projelerini GitHub'a yayınlar ve CloudStream kısa kodunu doğrular."""
from __future__ import annotations

import base64
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

from . import publisher, utils


def projects(cfg):
    root = Path(cfg.data_dir("generated"))
    return sorted(p.name for p in root.iterdir() if p.is_dir() and
                  (p / "build.gradle.kts").is_file()) if root.is_dir() else []


def normalize_shortcode(value):
    value = (value or "").strip().removeprefix("!")
    if value and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("Kısa kod harf, rakam, alt çizgi ve tire içerebilir. Örnek: !kaos")
    return "!" + value if value else ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_shortcode(code, target):
    code = normalize_shortcode(code)
    result = {"code": code, "target": target, "verified": False,
              "registration_url": "https://py.md/"}
    if not code:
        result["message"] = "Kısa kod belirtilmedi; doğrudan depo adresini kullanabilirsiniz."
        return result
    req = urllib.request.Request("https://py.md/" + code[1:], headers={"User-Agent": "WioForge"})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=20):
            location = ""
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location", "") if exc.code in (301, 302, 303, 307, 308) else ""
    except OSError:
        result["message"] = "Kısa kod servisine ulaşılamadı. Doğrulama daha sonra yeniden denenebilir."
        return result
    result["verified"] = location == target
    result["message"] = ("Kısa kod hedef depo adresiyle eşleşiyor." if result["verified"] else
                         "Kısa kod doğrulanmadı. py.md üzerinde bu kodu hedef depo adresine kaydedin; ardından tekrar doğrulayın.")
    return result


def status(cfg):
    return {"projects": projects(cfg), "publication": utils.read_json(
        cfg.data_dir("builder", "publication.json"), default=None)}


def verify_published_shortcode(cfg, code):
    report = status(cfg)["publication"]
    if not report:
        raise ValueError("Önce Builder projesini yayınlayın.")
    report["shortcode"] = check_shortcode(code, report["manifest_url"])
    utils.write_json(cfg.data_dir("builder", "publication.json"), report)
    return report


def publish_project(cfg, project, repo_name, shortcode=""):
    repo_name = (repo_name or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}", repo_name):
        raise ValueError("Geçerli bir GitHub depo adı girin (örnek: kaos).")
    shortcode = normalize_shortcode(shortcode)
    if project not in projects(cfg):
        raise ValueError("Yayınlanacak üretilmiş projeyi seçin.")
    source = Path(cfg.data_dir("generated", project)).resolve()
    if source.parent != Path(cfg.data_dir("generated")).resolve():
        raise ValueError("Proje çalışma klasörü dışında olamaz.")
    if not cfg.github_token or not cfg.github_user:
        raise ValueError("Genel sekmesinde GitHub kullanıcı adını ve token'ı kaydedin.")
    if not publisher._git_available():
        raise ValueError("Yayınlama için Git kurulmalı.")
    target = replace(cfg, repo_name=repo_name, default_branch="main", builds_branch="builds")
    if not publisher.ensure_github_repo(target):
        raise RuntimeError("GitHub deposu oluşturulamadı veya erişim sağlanamadı.")
    # Token yalnızca alt işlemin ortamında bulunur; remote URL'ye yazılmaz.
    auth = base64.b64encode(("x-access-token:" + cfg.github_token).encode()).decode()
    env = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
           "GIT_CONFIG_VALUE_0": "Authorization: Basic " + auth, "GIT_TERMINAL_PROMPT": "0"}
    with tempfile.TemporaryDirectory(prefix="wioforge_builder_") as work:
        def git(*args, check=True):
            rc, out = publisher._run(["git", *args], work, check=False, env=env)
            if rc and check:
                raise RuntimeError("Git işlemi başarısız: " + out.replace(cfg.github_token, "***").replace(auth, "***")[-1500:])
            return rc, out

        git("init", "-b", "main")
        git("config", "user.name", "WioForge")
        git("config", "user.email", "wioforge@local")
        git("remote", "add", "origin", target.repo_html_url + ".git")
        git("fetch", "origin")
        _, refs = git("branch", "-r")
        # Ayrı çalışma klasörü: indirilen Builder kütüphanesi yayınlanmaz.
        if "origin/builds" not in refs.split():
            manifest = {"name": repo_name, "description": target.repo_description,
                        "manifestVersion": 1, "pluginLists": [target.raw_builds_base + "/plugins.json"]}
            utils.write_json(os.path.join(work, "repo.json"), manifest)
            utils.write_json(os.path.join(work, "plugins.json"), [])
            utils.write_json(os.path.join(work, "repos-db.json"), [target.raw_builds_base + "/repo.json"])
            git("add", ".")
            git("commit", "-m", "Initialize CloudStream repository")
            git("push", "origin", "HEAD:refs/heads/builds")
            for name in ("repo.json", "plugins.json", "repos-db.json"):
                os.remove(os.path.join(work, name))
        if "origin/main" in refs.split():
            git("checkout", "-B", "main", "origin/main")
        else:
            git("checkout", "--orphan", "builder-main")
            git("rm", "-rf", "--cached", ".", check=False)
        shutil.copytree(source, work, dirs_exist_ok=True, ignore=shutil.ignore_patterns(
            ".git", ".gradle", "build", "__pycache__", "local.properties", "wioforge.json", ".env"))
        # Güncel yayın iş akışı; eski üretilmiş projelere de uygulanır.
        workflow = Path(publisher.TOOLKIT_ROOT, "templates", "workflow_build.yml").read_text(encoding="utf-8")
        utils.write_text(os.path.join(work, ".github", "workflows", "build.yml"), workflow)
        git("add", "-A")
        if (Path(work) / "gradlew").is_file():
            git("update-index", "--chmod=+x", "gradlew")
        rc, _ = git("diff", "--cached", "--quiet", check=False)
        if rc:
            git("commit", "-m", "Publish Builder project")
        git("push", "origin", "HEAD:refs/heads/main")
    report = {"project": project, "repo_url": target.repo_html_url,
              "manifest_url": target.raw_builds_base + "/repo.json",
              "actions_url": target.repo_html_url + "/actions",
              "message": "Proje yüklendi. Eklentiler GitHub Actions derlemesi başarıyla tamamlandığında hazır olacak."}
    report["shortcode"] = check_shortcode(shortcode, report["manifest_url"])
    utils.write_json(cfg.data_dir("builder", "publication.json"), report)
    utils.ok(report["message"])
    utils.info(report["repo_url"])
    utils.info(report["manifest_url"])
    utils.info(report["shortcode"]["message"])
    return report
