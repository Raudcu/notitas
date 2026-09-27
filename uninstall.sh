#!/usr/bin/env bash
# Desinstala la versión de ~/.local. No toca tus notas, ni las copias de seguridad,
# ni la configuración (~/.config/notitas).
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
APP_ID="io.github.notitas.Notitas"

"$PREFIX/bin/notitas" --uninstall-shortcuts 2>/dev/null || true
pkill -TERM -f "^/usr/bin/python3 $PREFIX/bin/notitas" 2>/dev/null || true
rm -f "$HOME/.config/autostart/$APP_ID.desktop"
make -C "$SRC" --no-print-directory uninstall PREFIX="$PREFIX" >/dev/null
echo "Notitas desinstalada de $PREFIX. Tus notas y la configuración siguen ahí."
