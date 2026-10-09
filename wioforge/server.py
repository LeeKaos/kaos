# -*- coding: utf-8 -*-
"""server.py — Yerel test sunucusu (üretilen depoyu CloudStream'e eklemeden önce dene)."""

from __future__ import annotations

import http.server
import os
import socketserver
import threading
from typing import Optional

from . import utils
from .config import Config


class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        # CORS + doğru içerik tipleri
        self.send_header("Access-Control-Allow-Origin", "*")
        if self.path.endswith(".cs3"):
            self.send_header("Content-Type", "application/octet-stream")
        super().end_headers()

    def log_message(self, fmt, *args):  # noqa: A003
        utils.info(f"[sunucu] {self.address_string()} - {fmt % args}")


def serve(cfg: Config, directory: Optional[str] = None, port: Optional[int] = None) -> None:
    """Belirtilen klasörü HTTP ile sunar (varsayılan: ayna klasörü)."""
    directory = directory or cfg.data_dir("mirror")
    port = port or cfg.server_port

    if not os.path.isdir(directory):
        utils.err(f"Sunulacak klasör yok: {directory}")
        return

    handler = lambda *a, **k: _Handler(*a, directory=directory, **k)  # noqa: E731

    utils.title("Yerel test sunucusu")
    utils.info(f"Klasör : {os.path.abspath(directory)}")
    utils.info(f"Adres  : http://localhost:{port}/repo.json")
    utils.info("Durdurmak için Ctrl+C")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            utils.info("Sunucu durduruldu.")


def serve_background(cfg: Config, directory: Optional[str] = None, port: Optional[int] = None):
    """Sunucuyu arka planda başlatır (panel için)."""
    directory = directory or cfg.data_dir("mirror")
    port = port or cfg.server_port
    handler = lambda *a, **k: _Handler(*a, directory=directory, **k)  # noqa: E731
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
