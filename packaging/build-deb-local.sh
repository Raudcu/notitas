#!/usr/bin/env bash
# Arma el .deb sin debhelper, sólo con dpkg-deb (viene con Ubuntu).
# El contenido sale del mismo `make install` y los datos de debian/control,
# así que es equivalente a `make deb`. Sirve para probar sin instalar nada.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(python3 -c "import notitas; print(notitas.VERSION)")
CHANGELOG=$(dpkg-parsechangelog -S Version)
if [ "$VERSION" != "$CHANGELOG" ]; then
  echo "La versión no coincide: notitas/__init__.py dice $VERSION y debian/changelog $CHANGELOG" >&2
  exit 1
fi

STAGE=build/deb
rm -rf build
mkdir -p "$STAGE/DEBIAN" dist
make --no-print-directory install DESTDIR="$PWD/$STAGE" PREFIX=/usr >/dev/null

python3 - "$VERSION" "$(du -sk "$STAGE" | cut -f1)" > "$STAGE/DEBIAN/control" <<'PY'
import re, sys
version, size = sys.argv[1], sys.argv[2]
source, binary = open("debian/control", encoding="utf-8").read().split("\n\n")[:2]

def fields(par):
    out, key = {}, None
    for line in par.splitlines():
        if line.startswith((" ", "\t")):
            out[key] += "\n" + line
        elif ":" in line:
            key, value = line.split(":", 1)
            out[key] = value.strip()
    return out

src, pkg = fields(source), fields(binary)
def deps(value):
    items = [d.strip() for d in value.replace("\n", " ").split(",")]
    return ", ".join(d for d in items if d and not d.startswith("${"))

print(f"Package: {pkg['Package']}")
print(f"Version: {version}")
print(f"Architecture: {pkg['Architecture']}")
print(f"Maintainer: {src['Maintainer']}")
print(f"Installed-Size: {size}")
print(f"Depends: {deps(pkg['Depends'])}")
if "Recommends" in pkg:
    print(f"Recommends: {deps(pkg['Recommends'])}")
print(f"Section: {src['Section']}")
print(f"Priority: {src['Priority']}")
print(f"Description: {pkg['Description']}")
PY

for script in postinst prerm; do
  sed '/#DEBHELPER#/d' "debian/notitas.$script" > "$STAGE/DEBIAN/$script"
  chmod 755 "$STAGE/DEBIAN/$script"
done

chmod -R u=rwX,go=rX "$STAGE"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"
dpkg-deb --root-owner-group --build "$STAGE" "dist/notitas_${VERSION}_all.deb"
