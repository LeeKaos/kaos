# -*- coding: utf-8 -*-
"""
generator.py — Verilen site adresinden tam bir CloudStream eklenti projesi üretir.

Üretilen proje:
  * Kotlin + Gradle tabanlıdır (CloudStream resmi şablonu ile uyumlu).
  * GitHub Actions ile BULUTTA derlenir (yerel Android SDK gerekmez).
  * Derlenince .cs3 dosyası + plugins.json + repo.json üretir.

Kullanıcı yalnızca:
  1) `wioforge generate https://site.com` çalıştırır,
  2) gerekirse seçicileri (selector_config.json / Provider.kt) düzeltir,
  3) `wioforge publish` ile kendi GitHub hesabına yükler,
  4) GitHub Actions otomatik olarak .cs3'ü derler.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import utils
from .analyzer import SiteProfile, analyze_site, profile_to_selector_config
from .config import Config

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")


@dataclass
class GeneratedProject:
    name: str
    output_dir: str
    site_url: str
    provider_class: str
    plugin_class: str
    package: str
    profile: Dict[str, Any]


def _read_template(name: str) -> str:
    return utils.read_text(os.path.join(TEMPLATES_DIR, name))


def _fmt(template: str, mapping: Dict[str, str]) -> str:
    """{anahtar} yer tutucularını güvenle değiştirir (Kotlin süslü parantezlerini korur)."""
    out = template
    for k, v in mapping.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _kotlin_tv_types(types: List[str]) -> str:
    return ", ".join(f"TvType.{t}" for t in types)


def generate_project(
    cfg: Config,
    site_url: str,
    *,
    provider_name: Optional[str] = None,
    output_dir: Optional[str] = None,
    tv_types: Optional[List[str]] = None,
    sample_query: str = "breaking",
    icon_url: str = "",
) -> GeneratedProject:
    """Site adresinden tam bir CloudStream eklenti projesi üretir."""
    utils.title(f"CloudStream eklentisi üretiliyor: {site_url}")

    prof: SiteProfile = analyze_site(site_url, sample_query=sample_query)

    # İsimlendirme
    if not provider_name:
        provider_name = prof.domain.replace("www.", "").split(".")[0].capitalize() or "Provider"
    slug = utils.slugify(provider_name)
    provider_class = f"{provider_name}Provider"
    plugin_class = f"{provider_name}Plugin"
    package = f"com.wioforge.{slug}"

    if output_dir is None:
        output_dir = cfg.data_dir("generated", slug)
    os.makedirs(output_dir, exist_ok=True)

    if tv_types is None:
        tv_types = ["Movie", "TvSeries"]

    # ------------------------------------------------------------------
    # 1) Gradle iskeleti
    # ------------------------------------------------------------------
    utils.step("Gradle iskeleti oluşturuluyor")
    utils.write_text(os.path.join(output_dir, "build.gradle.kts"), _read_template("root_build.gradle.kts"))
    utils.write_text(os.path.join(output_dir, "settings.gradle.kts"), _read_template("settings.gradle.kts"))
    utils.write_text(os.path.join(output_dir, "gradle.properties"), _read_template("gradle.properties"))
    utils.write_text(os.path.join(output_dir, ".gitignore"), _read_template("gitignore.txt"))

    # gradlew + wrapper
    for f in ("gradlew", "gradlew.bat"):
        src = os.path.join(TEMPLATES_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(output_dir, f))
    os.chmod(os.path.join(output_dir, "gradlew"), 0o755)
    wrapper_dir = os.path.join(output_dir, "gradle", "wrapper")
    os.makedirs(wrapper_dir, exist_ok=True)
    for f in ("gradle-wrapper.jar", "gradle-wrapper.properties"):
        src = os.path.join(TEMPLATES_DIR, "gradle", "wrapper", f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(wrapper_dir, f))

    # GitHub Actions
    wf_dir = os.path.join(output_dir, ".github", "workflows")
    os.makedirs(wf_dir, exist_ok=True)
    utils.write_text(os.path.join(wf_dir, "build.yml"), _read_template("workflow_build.yml"))

    # ------------------------------------------------------------------
    # 2) Sağlayıcı (provider) modülü
    # ------------------------------------------------------------------
    utils.step("Sağlayıcı kodu oluşturuluyor")
    module_dir = os.path.join(output_dir, provider_name)
    kotlin_dir = os.path.join(module_dir, "src", "main", "kotlin", *package.split("."))
    os.makedirs(kotlin_dir, exist_ok=True)
    os.makedirs(os.path.join(module_dir, "src", "main"), exist_ok=True)

    # AndroidManifest
    utils.write_text(os.path.join(module_dir, "src", "main", "AndroidManifest.xml"), _read_template("AndroidManifest.xml"))

    # build.gradle.kts
    icon = icon_url or f"https://www.google.com/s2/favicons?domain={prof.domain}&sz=128"
    module_gradle = _fmt(
        _read_template("provider_build.gradle.kts.tmpl"),
        {
            "provider_name": provider_name,
            "version": "1",
            "description": f"{provider_name} — {prof.title or prof.domain} (WioForge ile üretildi)",
            "author": cfg.plugin_author or cfg.github_user or "WioForge",
            "status": str(cfg.plugin_status),
            "tv_types": ", ".join(f'"{t}"' for t in tv_types),
            "language": cfg.plugin_language,
            "icon_url": icon,
        },
    )
    utils.write_text(os.path.join(module_dir, "build.gradle.kts"), module_gradle)

    # Provider.kt
    provider_kt = _fmt(
        _read_template("Provider.kt.tmpl"),
        {
            "package": package,
            "class_name": provider_class,
            "provider_name": provider_name,
            "main_url": prof.url,
            "lang": cfg.plugin_language,
            "supported_types": _kotlin_tv_types(tv_types),
            "search_url_template": prof.search_url_template or (prof.url + "/?s={query}"),
            "result_selector": prof.result_selector_hint or "article, .post, .result-item",
            "result_link_selector": "a",
            "result_title_selector": prof.result_title_selector or "h2, h3, .title, .name",
            "result_poster_selector": "img",
            "poster_attr": prof.poster_attr or "src",
        },
    )
    utils.write_text(os.path.join(kotlin_dir, f"{provider_class}.kt"), provider_kt)

    # Plugin.kt
    plugin_kt = _fmt(
        _read_template("Plugin.kt.tmpl"),
        {"package": package, "plugin_class": plugin_class, "class_name": provider_class},
    )
    utils.write_text(os.path.join(kotlin_dir, f"{plugin_class}.kt"), plugin_kt)

    # ------------------------------------------------------------------
    # 3) Çözümleme raporu + düzenlenebilir seçici ayarı
    # ------------------------------------------------------------------
    utils.write_json(os.path.join(output_dir, "site_profile.json"), prof.to_dict())
    utils.write_json(os.path.join(output_dir, "selector_config.json"), profile_to_selector_config(prof))

    # ------------------------------------------------------------------
    # 4) README
    # ------------------------------------------------------------------
    readme = _provider_readme(provider_name, prof, provider_class, plugin_class, package)
    utils.write_text(os.path.join(output_dir, "README.md"), readme)

    utils.ok(f"Proje üretildi: {output_dir}")
    if prof.notes:
        for n in prof.notes:
            utils.warn(f"Not: {n}")
    utils.info(
        "Sonraki adım: seçicileri gözden geçir (selector_config.json / Provider.kt), "
        "ardından 'wioforge publish' ile GitHub'a yükle."
    )

    return GeneratedProject(
        name=provider_name,
        output_dir=output_dir,
        site_url=prof.url,
        provider_class=provider_class,
        plugin_class=plugin_class,
        package=package,
        profile=prof.to_dict(),
    )


def _provider_readme(name: str, prof: SiteProfile, pclass: str, plclass: str, package: str) -> str:
    samples = "\n".join(
        f"  - {s['title'][:70]} -> {s['url']}" for s in prof.sample_results[:5]
    ) or "  (örnek sonuç bulunamadı)"
    return f"""# {name} — CloudStream Eklentisi

WioForge tarafından üretildi.

- **Site:** {prof.url}
- **Başlık:** {prof.title}
- **Arama kalıbı:** `{prof.search_url_template}`
- **Önerilen seçici:** `{prof.result_selector_hint}`
- **Paket:** `{package}`
- **Sağlayıcı sınıfı:** `{pclass}`
- **Eklenti sınıfı:** `{plclass}`

## Çözümlenen örnek sonuçlar
{samples}

## Notlar
{chr(10).join('  - ' + n for n in prof.notes) if prof.notes else '  - (not yok)'}

## Nasıl derlenir?
Bu proje GitHub Actions ile **bulutta** derlenir. Yerel bilgisayarında Android SDK
kurmana gerek yoktur. `wioforge publish` komutuyla GitHub'a yükle; `builds` dalında
`.cs3` dosyası otomatik oluşur.

## Seçicileri düzeltme
`selector_config.json` ve `{pclass}.kt` içindeki seçicileri sitenin gerçek HTML
yapısına göre güncelle. Tarayıcıda F12 ile öğeleri inceleyerek doğru CSS
seçicilerini bulabilirsin.
"""
