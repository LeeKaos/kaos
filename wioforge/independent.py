"""Panelden kişisel depo hazırlama, bağımlılık raporu ve ayrı depoya yayınlama."""
import base64
import json
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from . import mirror, publisher, utils, builder_publish


def root(cfg):
    return Path(cfg.data_dir("independent"))


def report_path(cfg, ident):
    if not re.fullmatch(r"[a-f0-9]{32}", ident or ""):
        raise ValueError("Geçersiz hazırlık kimliği.")
    return root(cfg) / ident / "report.json"


def catalog(cfg, source):
    if urlparse(source).scheme not in ("http", "https"):
        raise ValueError("Geçerli kaynak adresi girin.")
    data = mirror.list_original_addresses(cfg, source=source)
    unique = {}
    for plugin in data["plugins"]:
        key = plugin["internalName"] or plugin["original_url"]
        if key not in unique or plugin["version"] > unique[key]["version"]:
            unique[key] = plugin
    return {"kind": "catalog", "source": source, "plugins": list(unique.values())}


def prepare(cfg, request):
    name = str(request.get("name", "")).strip()
    repo = str(request.get("repo", "")).strip()
    source = str(request.get("source", "")).strip()
    worker_url = str(request.get("worker_url", "")).strip().rstrip("/")
    selected = request.get("selected")
    if not isinstance(selected, list) or not selected or not all(isinstance(x, str) for x in selected):
        raise ValueError("Kaynağı listeleyip en az bir eklenti seçin.")
    if not name or len(name) > 80:
        raise ValueError("1–80 karakterlik görünen depo adı girin.")
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}", repo):
        raise ValueError("GitHub depo adı geçersiz (örnek: kaos).")
    if not cfg.github_user:
        raise ValueError("Önce Genel bölümünde GitHub kullanıcı adını kaydedin.")
    if urlparse(source).scheme not in ("http", "https"):
        raise ValueError("Geçerli bir kaynak depo adresi girin.")
    parsed_worker = urlparse(worker_url)
    if parsed_worker.scheme != "https" or not parsed_worker.netloc or parsed_worker.query or parsed_worker.fragment:
        raise ValueError("Cloudflare Worker için HTTPS ana adresi girin (örnek: https://kaos-auth.example.workers.dev).")
    ident = uuid.uuid4().hex
    folder = root(cfg) / ident
    local = replace(cfg, repo_name=repo, source_repo=source, protected_policy="skip",
                    work_dir=str(folder / "download"), builds_branch="builds")
    summary = mirror.mirror_all(local, selected_urls=selected)
    catalog = utils.read_json(local.data_dir("mirror", "plugins.json"), default=[])
    output = folder / "output"
    (output / "plugins").mkdir(parents=True)
    kept, findings, credits = [], [], []
    strict = bool(request.get("exclude_dependencies", True))
    marker = re.compile(rb"wiojelt|wioland|megawio|wiojelt-auth", re.I)
    for plugin in catalog:
        filename = plugin["url"].rsplit("/", 1)[-1]
        path = Path(local.data_dir("mirror", "plugins", filename))
        hits = []
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.file_size > 32 * 1024 * 1024:
                    hits.append("Büyük dosya taranamadı: " + member.filename)
                    continue
                if marker.search(member.filename.encode()) or marker.search(archive.read(member)):
                    hits.append(member.filename)
        if hits:
            findings.append({"plugin": plugin.get("name", filename), "files": hits,
                             "excluded": strict})
            if strict:
                continue
        shutil.copy2(path, output / "plugins" / filename)
        credits.append({"name": plugin.get("name", ""), "authors": plugin.get("authors", [])})
        # Derlenmiş kod ve internalName korunur; yalnızca katalogdaki görünen ad düzenlenir.
        cleaned = re.sub(r"wiojelt|wioland|megawio|^wio", "", plugin.get("name", ""), flags=re.I).strip(" -_")
        plugin["name"] = name + " · " + (cleaned or "Eklenti")
        plugin["description"] = str(request.get("description", ""))[:1000]
        plugin.pop("iconUrl", None)
        plugin["url"] = local.raw_builds_base + "/plugins/" + filename
        plugin["repositoryUrl"] = local.repo_html_url
        kept.append(plugin)
    manifest = {"name": name, "description": str(request.get("description", ""))[:1000],
                "manifestVersion": 1, "pluginLists": [local.raw_builds_base + "/plugins.json"]}
    logo = str(request.get("logo", "")).strip()
    if logo:
        if urlparse(logo).scheme not in ("http", "https"):
            raise ValueError("Logo için http/https adresi girin.")
        data = utils.http_get(logo, binary=True)
        if not data or len(data) > 5 * 1024 * 1024:
            raise ValueError("Logo indirilemedi veya 5 MB sınırını aşıyor.")
        ext = "png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "jpg" if data.startswith(b"\xff\xd8\xff") else None
        if not ext:
            raise ValueError("Logo PNG veya JPEG olmalıdır.")
        (output / "assets").mkdir()
        (output / "assets" / ("logo." + ext)).write_bytes(data)
        manifest["iconUrl"] = local.raw_builds_base + "/assets/logo." + ext
        for plugin in kept:
            plugin["iconUrl"] = manifest["iconUrl"]
    utils.write_json(str(output / "repo.json"), manifest)
    utils.write_json(str(output / "plugins.json"), kept)
    utils.write_json(str(output / "repos-db.json"), [local.raw_builds_base + "/repo.json"])
    utils.write_json(str(output / "AUTHORS.json"), credits)
    utils.write_text(str(output / "README.md"), "# " + name + "\n\n" + manifest["description"] +
                     "\n\nEklentilerin yazar bilgileri AUTHORS.json dosyasındadır. Derlenmiş eklentiler yeniden yazılmamıştır.\n")
    hashes = {p.relative_to(output).as_posix(): utils.sha256_file(str(p)) for p in output.rglob("*") if p.is_file()}
    report = {"id": ident, "state": "ready" if kept else "empty", "name": name, "repo": repo,
              "description": manifest["description"],
              "worker_url": worker_url,
              "owner": cfg.github_user, "source": source, "downloaded": summary["downloaded"],
              "skipped": summary["skipped"], "included": len(kept), "findings": findings,
              "excluded": sum(x["excluded"] for x in findings), "hashes": hashes,
              "repo_url": local.repo_html_url, "manifest_url": local.raw_builds_base + "/repo.json",
              "note": "Tarama bilinen marka metinlerini arar; kod içindeki tüm servis bağımlılıklarını kanıtlamaz. Yazar bilgileri korunur. Otomatik kaynak güncellemesi eklenmez."}
    utils.write_json(str(report_path(cfg, ident)), report)
    utils.ok(f"Hazır: {len(kept)} eklenti; {report['excluded']} bağımlılık şüphesiyle dışarıda bırakıldı.")
    return report


def verify_shortcode(cfg, ident, code):
    path = report_path(cfg, ident)
    report = utils.read_json(str(path), default=None)
    if not report or report.get("state") != "published":
        raise ValueError("Önce bu depoyu GitHub'a yükleyin.")
    report["shortcode"] = builder_publish.check_shortcode(code, report["manifest_url"])
    utils.write_json(str(path), report)
    utils.info(report["shortcode"]["message"])
    return report


def publish(cfg, ident):
    path = report_path(cfg, ident)
    report = utils.read_json(str(path), default=None)
    if not report or report["state"] != "ready" or not report["included"]:
        raise ValueError("Yayınlanabilir hazırlık bulunamadı. Önce depoyu hazırlayın.")
    if report["owner"].lower() != cfg.github_user.lower():
        raise ValueError("Hazırlıktan sonra GitHub hesabı değişmiş. Yeniden hazırlayın.")
    output = path.parent / "output"
    actual = {p.relative_to(output).as_posix(): utils.sha256_file(str(p)) for p in output.rglob("*") if p.is_file()}
    if actual != report["hashes"]:
        raise ValueError("Hazırlanan dosyalar değişmiş. Yeniden hazırlayın.")
    if not cfg.github_token or not publisher._git_available():
        raise ValueError("Git ve Genel bölümünde kayıtlı GitHub token gerekli.")
    description = utils.read_json(str(output / "repo.json"), default={}).get("description", "")
    target = replace(cfg, repo_name=report["repo"], repo_description=description)
    if not publisher.ensure_github_repo(target, private=True):
        raise RuntimeError("GitHub deposuna erişilemedi.")
    auth = base64.b64encode(("x-access-token:" + cfg.github_token).encode()).decode()
    env = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
           "GIT_CONFIG_VALUE_0": "Authorization: Basic " + auth, "GIT_TERMINAL_PROMPT": "0"}
    with tempfile.TemporaryDirectory(prefix="independent_publish_") as work:
        def git(*args):
            rc, out = publisher._run(["git", *args], work, check=False, env=env)
            if rc:
                raise RuntimeError(out.replace(cfg.github_token, "***").replace(auth, "***")[-1200:])
            return out
        git("init", "-b", "builds")
        git("remote", "add", "origin", target.repo_html_url + ".git")
        if git("ls-remote", "origin").strip():
            raise ValueError("Bu depo boş değil. Mevcut dosyaları korumak için yeni veya boş bir depo adıyla hazırlayın.")
        shutil.copytree(output, work, dirs_exist_ok=True)
        git("config", "user.name", cfg.github_user)
        git("config", "user.email", cfg.github_user + "@users.noreply.github.com")
        git("add", ".")
        git("commit", "-m", "Initial release")
        git("push", "origin", "HEAD:refs/heads/builds")
    report["state"] = "published"
    report["access_portal"] = report["worker_url"]
    report["manifest_url"] = report["worker_url"]
    utils.write_json(str(path), report)
    utils.ok("Özel depo yayımlandı. Worker erişim ekranı: " + report["access_portal"])
    return report
