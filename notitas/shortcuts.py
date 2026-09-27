"""Registro de atajos globales como "atajos personalizados" de GNOME.

Así funcionan igual en X11 y en Wayland, y quedan visibles/editables en
Configuración → Teclado → Atajos personalizados.
"""

from gi.repository import Gio

from .store import MAX_NUMBER

MEDIA_KEYS = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
BASE_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
OUR_PREFIX = BASE_PATH + "notitas-"
DEFAULT_MODIFIERS = "<Control><Alt>"


def _available():
    source = Gio.SettingsSchemaSource.get_default()
    return source is not None and source.lookup(MEDIA_KEYS, True) is not None


def installed():
    if not _available():
        return False
    paths = Gio.Settings.new(MEDIA_KEYS).get_strv("custom-keybindings")
    return any(p.startswith(OUR_PREFIX) for p in paths)


def installed_command():
    """Programa al que apuntan los atajos registrados (o None)."""
    if not installed():
        return None
    s = Gio.Settings.new_with_path(CUSTOM_SCHEMA, f"{OUR_PREFIX}1/")
    return s.get_string("command").rsplit(" --quick", 1)[0] or None


def install(command, modifiers=DEFAULT_MODIFIERS):
    """<mod>N → --quick N, <Shift><mod>N → --paste N (N = 1..9) y <mod>0 → selector."""
    if not _available():
        raise RuntimeError("No se encontró la configuración de atajos de GNOME")
    uninstall()
    media = Gio.Settings.new(MEDIA_KEYS)
    paths = list(media.get_strv("custom-keybindings"))
    entries = [(str(n), f"{modifiers}{n}", f"Notitas: agregar a nota {n}", f"--quick {n}")
               for n in range(1, MAX_NUMBER + 1)]
    entries += [(f"paste{n}", f"<Shift>{modifiers}{n}", f"Notitas: pegar en nota {n}", f"--paste {n}")
                for n in range(1, MAX_NUMBER + 1)]
    entries.append(("0", f"{modifiers}0", "Notitas: buscar nota", "--pick"))
    for key, binding, name, args in entries:
        path = f"{OUR_PREFIX}{key}/"
        s = Gio.Settings.new_with_path(CUSTOM_SCHEMA, path)
        s.set_string("name", name)
        s.set_string("command", f"{command} {args}")
        s.set_string("binding", binding)
        paths.append(path)
    media.set_strv("custom-keybindings", paths)
    Gio.Settings.sync()


def uninstall():
    if not _available():
        return
    media = Gio.Settings.new(MEDIA_KEYS)
    paths = list(media.get_strv("custom-keybindings"))
    for path in [p for p in paths if p.startswith(OUR_PREFIX)]:
        s = Gio.Settings.new_with_path(CUSTOM_SCHEMA, path)
        for key in ("name", "command", "binding"):
            s.reset(key)
        paths.remove(path)
    media.set_strv("custom-keybindings", paths)
    Gio.Settings.sync()
