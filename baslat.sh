#!/usr/bin/env bash
# ============================================================================
#  WioForge — Başlatıcı (Linux / macOS)
#  Bu betik Python'u bulur ve WioForge menüsünü açar.
#  Kullanım:  ./baslat.sh
# ============================================================================
set -e
cd "$(dirname "$0")"

# Python bul
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo "[HATA] Python bulunamadı. Lütfen Python 3.8+ kurun: https://www.python.org/downloads/"
  exit 1
fi

echo "WioForge başlatılıyor ($PY)..."
"$PY" wioforge.py "$@"
