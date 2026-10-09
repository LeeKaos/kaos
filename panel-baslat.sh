#!/usr/bin/env bash
# ============================================================================
#  WioForge — Web Panel Başlatıcı (Python, Linux / macOS)
#  Tarayıcıda http://localhost:8080 adresini açar.
#  Kullanım:  ./panel-baslat.sh [port]
# ============================================================================
set -e
cd "$(dirname "$0")"

PORT="${1:-8080}"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo "[HATA] Python bulunamadı. Lütfen Python 3.8+ kurun."
  exit 1
fi

echo "WioForge Web Paneli başlatılıyor: http://localhost:${PORT}"
echo "(Durdurmak için Ctrl+C)"
"$PY" wioforge.py panel --port "$PORT"
