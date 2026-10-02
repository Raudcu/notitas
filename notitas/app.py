import os
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, config, shortcuts, style, tray  # noqa: E402
from .floating import FloatingNote  # noqa: E402
from .picker import NotePicker  # noqa: E402
from .prefs import PreferencesDialog  # noqa: E402
from .quick import QuickCapture, QuickMessage, present  # noqa: E402
from .store import Store  # noqa: E402
from .window import NotesWindow  # noqa: E402


def launcher_command():
    """Comando con el que GNOME tiene que invocar a la app desde un atajo."""
    return os.path.abspath(sys.argv[0])


class NotitasApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.store = None
        self.window = None
        self.tray = None
        self.floating = {}  # note_id -> FloatingNote
        self._quitting = False
        opts = [
            ("quick", GLib.OptionArg.INT, "Captura rápida para la nota N", "N"),
            ("paste", GLib.OptionArg.INT, "Agregar lo seleccionado (o lo copiado) a la nota N", "N"),
            ("pick", GLib.OptionArg.NONE, "Abrir el selector de notas", None),
            ("preferences", GLib.OptionArg.NONE, "Abrir las preferencias", None),
            ("background", GLib.OptionArg.NONE, "Arrancar sin ventana (para el inicio de sesión)", None),
            ("notes-dir", GLib.OptionArg.STRING, "Guardar las notas en esta carpeta y salir", "CARPETA"),
            ("install-shortcuts", GLib.OptionArg.NONE, "Registrar los atajos en GNOME y salir", None),
            ("uninstall-shortcuts", GLib.OptionArg.NONE, "Quitar los atajos de GNOME y salir", None),
        ]
        for name, arg, desc, arg_desc in opts:
            self.add_main_option(name, 0, GLib.OptionFlags.NONE, arg, desc, arg_desc)

    # ---------- ciclo de vida ----------

    def do_handle_local_options(self, options):
        # Estas no necesitan la instancia principal.
        if options.contains("notes-dir"):
            config.set_notes_dir(options.lookup_value("notes-dir").get_string())
            print(f"Las notas se guardan en {config.notes_file()}")
            return 0
        try:
            if options.contains("install-shortcuts"):
                shortcuts.install(launcher_command())
                print("Atajos Ctrl+Alt+0…9 y Ctrl+Alt+Shift+1…9 registrados en GNOME.")
                return 0
            if options.contains("uninstall-shortcuts"):
                shortcuts.uninstall()
                print("Atajos quitados.")
                return 0
        except RuntimeError as e:
            print(e, file=sys.stderr)
            return 1
        return -1

    def do_startup(self):
        Adw.Application.do_startup(self)
        Gtk.Window.set_default_icon_name(APP_ID)
        style.install()
        self.store = Store()
        self.store.connect("error", lambda _s, msg: self._notify_error(msg))
        self.store.connect("changed", lambda *_: self._refresh_tray())

        # La app queda viva aunque no haya ventanas: es la que atiende los atajos.
        self.hold()
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self._on_quit)

        self._add_action("quick", self.quick_capture, "i")
        self._add_action("paste", self.paste_clipboard, "i")
        self._add_action("pick", self.show_picker)
        self._add_action("quit", self._on_quit)
        self._add_action("preferences", self.show_preferences)
        self._add_action("open-data", self._on_open_data)
        self._add_action("float", self.toggle_floating, "s")
        self._add_action("edit", self.open_in_editor, "s")
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("window.close", ["<Control>w"])

        try:
            self.tray = tray.TrayIcon(self.get_dbus_connection(), self._tray_menu, self.do_activate)
        except GLib.Error as e:
            print(f"Sin ícono en la barra: {e.message}", file=sys.stderr)

        self._fix_shortcuts_path()
        for note_id, geometry in config.load_state().get("floating", {}).items():
            if self.store.note(note_id):
                self._open_floating(note_id, geometry)

    def _add_action(self, name, callback, param_type=None):
        action = Gio.SimpleAction.new(name, GLib.VariantType.new(param_type) if param_type else None)
        action.connect("activate", lambda _a, p: callback(p.unpack()) if p is not None else callback())
        self.add_action(action)

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        if "quick" in options:
            self.quick_capture(options["quick"])
        elif "paste" in options:
            self.paste_clipboard(options["paste"])
        elif "pick" in options:
            self.show_picker()
        elif "preferences" in options:
            self.show_preferences(welcome=not config.setup_done())
        elif "background" not in options:
            self.activate()
        return 0

    def do_activate(self):
        if not self.window:
            self.window = NotesWindow(self, self.store)
        present(self.window)
        if not config.setup_done():
            GLib.idle_add(lambda: self.show_preferences(welcome=True) and False)

    def show_preferences(self, welcome=False):
        if not self.window:
            self.window = NotesWindow(self, self.store)
            present(self.window)
        PreferencesDialog(self, welcome=welcome).present(self.window)

    def _fix_shortcuts_path(self):
        """Si el programa cambió de lugar (p. ej. de ~/.local al .deb), actualizar los atajos."""
        current = shortcuts.installed_command()
        if current and current != launcher_command():
            try:
                shortcuts.install(launcher_command())
            except RuntimeError as e:
                print(e, file=sys.stderr)
        if config.autostart_enabled():
            config.set_autostart(True, launcher_command())

    def do_shutdown(self):
        if self.store:
            if not self._quitting:
                self._save_floating_state()
            self.store.save_now()
        Adw.Application.do_shutdown(self)

    def _on_quit(self):
        self._save_floating_state()
        self._quitting = True
        self.store.save_now()
        self.quit()
        return GLib.SOURCE_REMOVE

    # ---------- captura rápida y selector ----------

    def quick_capture(self, number):
        note = self.store.note_by_number(number)
        if not note:
            QuickMessage(self, f"No hay ninguna nota con el número {number}").present()
            return
        self.quick_capture_note(note.id)

    def quick_capture_note(self, note_id):
        # Si ya hay una ventanita abierta para esa nota, reusarla.
        for win in self.get_windows():
            if isinstance(win, QuickCapture) and win.note_id == note_id:
                win.show_focused()
                return
        QuickCapture(self, self.store, self.store.note(note_id)).show_focused()

    def paste_clipboard(self, number):
        """Agrega lo seleccionado (o, si no hay, lo copiado) a la nota N sin abrir nada."""
        note = self.store.note_by_number(number)
        if not note:
            QuickMessage(self, f"No hay ninguna nota con el número {number}").present()
            return
        display = Gdk.Display.get_default()
        # Primero la selección (lo que pega el clic del medio); si no hay, el portapapeles.
        sources = [display.get_primary_clipboard(), display.get_clipboard()]

        def read_next():
            sources.pop(0).read_text_async(None, on_text)

        def on_text(cb, result):
            try:
                text = (cb.read_text_finish(result) or "").strip()
            except GLib.Error:
                text = ""
            if not text and sources:
                read_next()
                return
            if not text:
                QuickMessage(self, "No hay texto seleccionado ni copiado", note.color).present()
                return
            # Un renglón entra como tarea; un bloque de varias líneas, tal cual.
            self.store.append(note.id, text, as_tasks=None if "\n" not in text else False)
            self.store.save_now()
            first = text.splitlines()[0]
            # Aviso sin robar el foco: seguís trabajando donde estabas.
            QuickMessage(self, f"Pegado en «{note.title or 'Sin título'}»", note.color, first).present()

        read_next()

    def show_picker(self):
        for win in self.get_windows():
            if isinstance(win, NotePicker):
                win.close()
        present(NotePicker(self, self.store, self._on_picked))

    def _on_picked(self, note_id, mode):
        if mode == "float":
            self.toggle_floating(note_id, force_open=True)
        elif mode == "edit":
            self.open_in_editor(note_id)
        else:
            self.quick_capture_note(note_id)

    def open_in_editor(self, note_id):
        self.do_activate()
        self.window.show_note(note_id)

    # ---------- post-its flotantes ----------

    def toggle_floating(self, note_id, force_open=False):
        win = self.floating.get(note_id)
        if win and not force_open:
            win.close()
        elif win:
            present(win)
        else:
            self._open_floating(note_id)

    def _open_floating(self, note_id, geometry=None):
        win = FloatingNote(self, self.store, note_id, geometry)
        self.floating[note_id] = win

        def on_close(_win):
            # Al salir de la app las ventanas se cierran solas: no olvidarlas.
            if not self._quitting:
                self.floating.pop(note_id, None)
                self._save_floating_state()
                self._refresh_tray()
            return False

        win.connect("close-request", on_close)
        win.present()
        self._save_floating_state()
        self._refresh_tray()

    def _save_floating_state(self):
        state = config.load_state()
        state["floating"] = {nid: w.geometry() for nid, w in self.floating.items()}
        config.save_state(state)

    # ---------- barra superior ----------

    def _tray_menu(self):
        notes = sorted(self.store.notes, key=lambda n: (n.number is None, n.number or 0, n.title))
        numbered = [n for n in notes if n.number is not None]
        add_items = [
            tray.item(f"{n.number} · {n.title or 'Sin título'}", lambda nid=n.id: self.quick_capture_note(nid))
            for n in numbered
        ]
        float_items = [
            tray.item(n.title or "Sin título", lambda nid=n.id: self.toggle_floating(nid),
                      toggled=n.id in self.floating)
            for n in notes
        ]
        paste_items = [
            tray.item(f"{n.number} · {n.title or 'Sin título'}", lambda num=n.number: self.paste_clipboard(num))
            for n in numbered
        ]
        return [
            tray.item("Abrir Notitas", self.do_activate),
            tray.item("Buscar nota…  (Ctrl+Alt+0)", self.show_picker),
            tray.separator(),
            tray.item("Agregar a…", children=add_items or [tray.item("(ninguna nota tiene número)")]),
            tray.item("Pegar lo seleccionado en…", children=paste_items or [tray.item("(ninguna nota tiene número)")]),
            tray.item("Post-its flotantes", children=float_items or [tray.item("(no hay notas)")]),
            tray.separator(),
            tray.item("Salir", self._on_quit),
        ]

    def _refresh_tray(self):
        if self.tray:
            self.tray.refresh()

    # ---------- varios ----------

    def _on_open_data(self):
        folder = Gio.File.new_for_path(os.path.dirname(self.store.path))
        Gtk.FileLauncher.new(folder).launch(self.window, None, None)

    def _notify_error(self, message):
        print(message, file=sys.stderr)
        notification = Gio.Notification.new("Notitas: problema con el archivo de notas")
        notification.set_body(message)
        notification.set_priority(Gio.NotificationPriority.URGENT)
        self.send_notification("store-error", notification)


def main(argv):
    # Que la ventana se presente con el mismo nombre que su .desktop (WM_CLASS):
    # así GNOME la asocia con su ícono en el Dash.
    GLib.set_prgname(APP_ID)
    return NotitasApp().run(argv)
