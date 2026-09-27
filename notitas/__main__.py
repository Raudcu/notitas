"""Punto de entrada.

`notitas --quick N`, `--paste N` y `--pick` intentan primero hablarle por D-Bus a la
instancia que ya está corriendo, sin importar GTK: así el atajo responde en
unos pocos ms. Si no hay instancia, arranca la app completa.
"""

import os
import sys

from . import APP_ID


def _remote_action(name, param=None):
    from gi.repository import Gio, GLib

    platform = {}
    token = os.environ.get("DESKTOP_STARTUP_ID")
    if token:
        platform["desktop-startup-id"] = GLib.Variant("s", token)
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            APP_ID,
            "/" + APP_ID.replace(".", "/"),
            "org.gtk.Actions",
            "Activate",
            GLib.Variant("(sava{sv})", (name, [param] if param else [], platform)),
            None,
            Gio.DBusCallFlags.NO_AUTO_START,
            2000,
            None,
        )
        return True
    except GLib.Error:
        return False


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] in ("--quick", "--paste") and args[1].isdigit():
        from gi.repository import GLib

        if _remote_action(args[0][2:], GLib.Variant("i", int(args[1]))):
            return 0
    elif args == ["--pick"]:
        if _remote_action("pick"):
            return 0

    from .app import main as app_main

    return app_main(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
