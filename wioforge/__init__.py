# -*- coding: utf-8 -*-
"""
WioForge — Bağımsız CloudStream Depo & Eklenti Yönetim Aracı
=============================================================

WioLand (https://github.com/Wiojelt/WioLand) deposundan BAĞIMSIZ çalışır.

Yeteneği:
  * WioLand ve bağlı depoların "orijinal adreslerini" bulur (repos-db.json, repo.json,
    plugins.json içindeki tüm URL'ler).
  * Bu adresleri kendi GitHub hesabına göre yeniden yazar (rewrite) ve yerel bir
    bağımsız ayna (mirror) oluşturur.
  * Tüm uzantıları (.cs3) indirip yeniden barındırır; WioLand kapansa dahi çalışır.
  * Verdiğin site adresini (ör. https://www.dizimom.wiki) çözümleyip CloudStream
    eklentisi (Kotlin + Gradle projesi) üretir.
  * Üretilen çıktıyı kendi GitHub hesabına yükler.
"""

__version__ = "1.0.0"
__author__ = "WioForge"
__all__ = ["config", "utils", "mirror", "analyzer", "generator", "publisher", "server", "cli"]
