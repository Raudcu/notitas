#!/usr/bin/env bash
# Instala Notitas sólo para tu usuario, sin sudo, en ~/.local.
# (Para todo el sistema está el paquete .deb: ver README.)
# La carpeta de las notas, los atajos y el arranque automático se configuran
# en la app: la primera vez aparece una bienvenida.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
APP_ID="io.github.notitas.Notitas"

python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" 2>/dev/null || {
  echo "Faltan dependencias. Instalalas con:"
  echo "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1"
  exit 1
}

echo "→ Instalando en $PREFIX"
pkill -TERM -f "^/usr/bin/python3 $PREFIX/bin/notitas" 2>/dev/null && sleep 1 || true
make -C "$SRC" --no-print-directory uninstall install PREFIX="$PREFIX" >/dev/null
# En ~/.local el Dash no siempre tiene ~/.local/bin en el PATH: usar la ruta completa.
sed -i "s|^Exec=notitas|Exec=$PREFIX/bin/notitas|" "$PREFIX/share/applications/$APP_ID.desktop"
python3 -m compileall -q "$PREFIX/lib/notitas"
gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true
update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true

if grep -q '"setup_done": true' "${XDG_CONFIG_HOME:-$HOME/.config}/notitas/config.json" 2>/dev/null; then
  setsid "$PREFIX/bin/notitas" --background >/dev/null 2>&1 < /dev/null &
  echo "Listo: Notitas actualizada y corriendo en segundo plano."
else
  setsid "$PREFIX/bin/notitas" >/dev/null 2>&1 < /dev/null &
  echo "Listo: se abrió Notitas con la bienvenida para configurarla."
fi
