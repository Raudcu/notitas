# Aislar los tests de la configuración y las notas reales: GLib lee estas
# variables una sola vez, así que tienen que estar antes de cualquier import.
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="notitas-tests-")
for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
    os.environ[var] = os.path.join(_tmp, var.lower())
os.environ["HOME"] = _tmp
