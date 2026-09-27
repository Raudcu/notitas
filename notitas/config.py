"""Configuración local de cada usuario (no se sincroniza).

~/.config/notitas/config.json: carpeta de las notas, carpeta de las copias de
seguridad y si ya se hizo la configuración inicial.
~/.config/notitas/state.json: estado de las ventanas (post-its flotantes).
"""

import json
import os

from gi.repository import GLib

from . import APP_ID

NOTES_FILENAME = "notitas.md"


def config_dir():
    return os.path.join(GLib.get_user_config_dir(), "notitas")


def data_dir():
    """Carpeta local de la app. Nunca se sincroniza."""
    return os.path.join(GLib.get_user_data_dir(), "notitas")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _config_path():
    return os.path.join(config_dir(), "config.json")


def _get(key):
    return _read(_config_path()).get(key)


def _set(key, value):
    data = _read(_config_path())
    data[key] = value
    _write(_config_path(), data)


# ---------- notas ----------


def suggested_notes_dir():
    """Para la primera vez: Dropbox si existe (respaldo automático), si no Documentos."""
    dropbox = os.path.expanduser("~/Dropbox")
    if os.path.isdir(dropbox):
        return os.path.join(dropbox, "Notitas")
    docs = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or os.path.expanduser("~")
    return os.path.join(docs, "Notitas")


def notes_dir():
    folder = _get("notes_dir")
    return os.path.expanduser(folder) if folder else suggested_notes_dir()


def notes_file():
    return os.path.join(notes_dir(), NOTES_FILENAME)


def set_notes_dir(folder):
    _set("notes_dir", os.path.abspath(os.path.expanduser(folder)))


# ---------- copias de seguridad ----------


def default_backups_dir():
    return os.path.join(data_dir(), "backups")


def backups_dir():
    folder = _get("backups_dir")
    return os.path.expanduser(folder) if folder else default_backups_dir()


def set_backups_dir(folder):
    _set("backups_dir", os.path.abspath(os.path.expanduser(folder)))


# ---------- configuración inicial ----------


def setup_done():
    return bool(_get("setup_done"))


def mark_setup_done():
    _set("setup_done", True)


# ---------- arranque automático ----------


def _autostart_file():
    return os.path.join(GLib.get_user_config_dir(), "autostart", f"{APP_ID}.desktop")


def autostart_enabled():
    return os.path.exists(_autostart_file())


def set_autostart(enabled, command):
    path = _autostart_file()
    if not enabled:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Notitas\n"
            "Comment=Notitas en segundo plano, para que funcionen los atajos\n"
            f"Exec={command} --background\n"
            f"Icon={APP_ID}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )


# ---------- estado de ventanas ----------


def load_state():
    return _read(os.path.join(config_dir(), "state.json"))


def save_state(state):
    _write(os.path.join(config_dir(), "state.json"), state)
