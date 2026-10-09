#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WioForge — Bağımsız CloudStream Depo & Eklenti Yönetim Aracı
=============================================================

WioLand (https://github.com/Wiojelt/WioLand) deposundan BAĞIMSIZ çalışır.

Kullanım:
    python wioforge.py init
    python wioforge.py list
    python wioforge.py mirror
    python wioforge.py generate https://www.dizimom.wiki --name DiziMom
    python wioforge.py publish --target generated
    python wioforge.py panel
"""

import os
import sys

# Paket yolunu ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wioforge.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
