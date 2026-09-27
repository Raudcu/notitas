#!/usr/bin/env bash
# Prepara una versión nueva en un solo paso:
#   packaging/release.sh 0.4.0 "Qué cambió" ["Otro cambio" ...]
#
# Actualiza la versión en los tres lugares donde vive (notitas/__init__.py,
# debian/changelog y el metainfo), hace el commit y crea el tag v0.4.0.
# No pushea: revisá y después `git push origin main v0.4.0`. Al llegar el tag,
# GitHub Actions arma el .deb y publica el Release.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:-}"
shift || true
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Uso: $0 X.Y.Z \"cambio\" [\"otro cambio\" ...]" >&2
  exit 1
fi
if [ $# -eq 0 ]; then
  echo "Falta al menos una línea que diga qué cambió (va al changelog y al Release)." >&2
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Hay cambios sin commitear: commitealos antes de sacar la versión." >&2
  exit 1
fi
if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
  echo "El tag v$VERSION ya existe." >&2
  exit 1
fi

python3 - "$VERSION" "$@" <<'PY'
import datetime, email.utils, re, sys

version, changes = sys.argv[1], sys.argv[2:]

path = "notitas/__init__.py"
text = open(path, encoding="utf-8").read()
open(path, "w", encoding="utf-8").write(re.sub(r'VERSION = ".*"', f'VERSION = "{version}"', text))

maintainer = re.search(r"^Maintainer: (.+)$", open("debian/control", encoding="utf-8").read(), re.M).group(1)
entry = (f"notitas ({version}) noble; urgency=medium\n\n"
         + "".join(f"  * {c}\n" for c in changes)
         + f"\n -- {maintainer}  {email.utils.formatdate(localtime=True)}\n\n")
path = "debian/changelog"
open(path, "w", encoding="utf-8").write(entry + open(path, encoding="utf-8").read())

path = "data/io.github.notitas.Notitas.metainfo.xml"
text = open(path, encoding="utf-8").read()
text = text.replace("<releases>\n", f'<releases>\n    <release version="{version}" date="{datetime.date.today()}"/>\n', 1)
open(path, "w", encoding="utf-8").write(text)
PY

git add notitas/__init__.py debian/changelog data/io.github.notitas.Notitas.metainfo.xml
git commit -q -m "Versión $VERSION"
git tag -a "v$VERSION" -m "Notitas $VERSION"
echo "Listo: commit y tag v$VERSION creados. Para publicar:"
echo "  git push origin main v$VERSION"
