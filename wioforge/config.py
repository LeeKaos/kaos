# -*- coding: utf-8 -*-
"""Yapılandırma yönetimi (wioforge.json)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

from . import utils

CONFIG_FILENAME = "wioforge.json"

# WioLand kaynak sabitleri (varsayılan; kullanıcı değiştirebilir)
DEFAULT_SOURCE_REPO = "https://github.com/Wiojelt/WioLand"
DEFAULT_REPOS_DB = "https://raw.githubusercontent.com/Wiojelt/WioLand/main/repos-db.json"
DEFAULT_MANIFEST = "https://raw.githubusercontent.com/Wiojelt/WioLand/main/repo.json"

# WioLand'ın kendi barındırdığı / yönlendirdiği alan adları.
# Aynalama sırasında bu adresler kullanıcının kendi deposuna göre yeniden yazılır.
WIO_URL_PATTERNS = [
    "wiojelt-auth.hdf-worker.workers.dev",
    "raw.githubusercontent.com/Wiojelt/",
    "github.com/Wiojelt/",
]


@dataclass
class Config:
    # --- GitHub / yayın ---
    github_user: str = ""
    github_token: str = ""
    repo_name: str = "WioRepo"          # Kendi depo adın
    repo_description: str = "Benim bağımsız CloudStream depom (WioForge ile üretildi)"
    default_branch: str = "main"
    builds_branch: str = "builds"

    # --- Kaynak (upstream) ---
    source_repo: str = DEFAULT_SOURCE_REPO
    repos_db_url: str = DEFAULT_REPOS_DB
    manifest_url: str = DEFAULT_MANIFEST

    # --- Yerel çalışma alanı ---
    work_dir: str = "wioforge_data"

    # --- Ayna davranışı ---
    # Worker ile korunan .cs3 dosyaları indirilemezse ne yapılsın:
    #   "skip"   -> atla (yalnızca indirilebilenleri aynala)
    #   "keep"   -> orijinal URL'i koru (bağımsız olmaz ama çalışır)
    #   "proxy"  -> kendi worker/proxy adresinle değiştir (proxy_base_url gerekir)
    protected_policy: str = "skip"
    proxy_base_url: str = ""

    # --- Sunucu ---
    server_port: int = 8080

    # --- Üretilen eklenti varsayılanları ---
    plugin_author: str = ""
    plugin_language: str = "tr"
    plugin_status: int = 1

    # Aynalanan depoların son durumu (mirror.json'dan yüklenir)
    extra: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Yükle / kaydet
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str = CONFIG_FILENAME) -> "Config":
        data = utils.read_json(path, default=None)
        if not data:
            cfg = cls()
            return cfg
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        cfg = cls(**kwargs)
        return cfg

    def save(self, path: str = CONFIG_FILENAME) -> None:
        utils.write_json(path, asdict(self))
        utils.ok(f"Yapılandırma kaydedildi: {path}")

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------
    @property
    def raw_base(self) -> str:
        """Kendi deponun raw.githubusercontent taban adresi."""
        if not self.github_user:
            return ""
        return (
            f"https://raw.githubusercontent.com/{self.github_user}/"
            f"{self.repo_name.lower()}/{self.default_branch}"
        )

    @property
    def raw_builds_base(self) -> str:
        if not self.github_user:
            return ""
        return (
            f"https://raw.githubusercontent.com/{self.github_user}/"
            f"{self.repo_name.lower()}/{self.builds_branch}"
        )

    @property
    def repo_html_url(self) -> str:
        if not self.github_user:
            return ""
        return f"https://github.com/{self.github_user}/{self.repo_name.lower()}"

    def data_dir(self, *parts: str) -> str:
        return os.path.join(self.work_dir, *parts)

    def ensure_dirs(self) -> None:
        for p in (
            self.data_dir(),
            self.data_dir("mirror"),
            self.data_dir("mirror", "plugins"),
            self.data_dir("mirror", "assets"),
            self.data_dir("generated"),
        ):
            os.makedirs(p, exist_ok=True)

    def is_configured(self) -> bool:
        return bool(self.github_user and self.repo_name)

    def summary(self) -> str:
        lines = [
            f"GitHub kullanıcı : {self.github_user or '(ayarlanmadı)'}",
            f"Depo adı         : {self.repo_name}",
            f"Kaynak depo      : {self.source_repo}",
            f"Çalışma klasörü  : {self.work_dir}",
            f"Korumalı politika: {self.protected_policy}",
        ]
        return "\n".join(lines)


def default_config_path() -> str:
    return os.path.join(os.getcwd(), CONFIG_FILENAME)
