"""Preferencias. La primera vez se muestra como bienvenida, con un botón "Empezar".

Todo lo que es de cada usuario (carpeta de las notas, atajos, arranque
automático) se configura acá y no en la instalación, así el paquete .deb no
tiene que preguntar nada.
"""

import os

from gi.repository import Adw, Gio, GLib, Gtk

from . import config, shortcuts

SHORTCUTS_HELP = "Ctrl+Alt+1…9 agregar · Ctrl+Alt+Shift+1…9 pegar lo copiado · Ctrl+Alt+0 buscar"


def _pretty(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path


class PreferencesDialog(Adw.Dialog):
    def __init__(self, app, welcome=False):
        super().__init__(title="Bienvenida a Notitas" if welcome else "Preferencias",
                         content_width=600, content_height=680)
        self.app = app
        self.store = app.store
        self.welcome = welcome
        # En la bienvenida nada se aplica hasta "Empezar"; después, al instante.
        self.notes_dir = config.notes_dir()
        self.backups_dir = config.backups_dir()

        page = Adw.PreferencesPage()

        # ---- notas ----
        notes = Adw.PreferencesGroup(
            title="Notas",
            description="Todas las notas van en un único archivo, notitas.md. Conviene una carpeta "
                        "sincronizada (Dropbox, Nextcloud…) para tener respaldo automático.",
        )
        self.notes_row = Adw.ActionRow(title="Carpeta de las notas", subtitle=_pretty(self.notes_dir))
        self.notes_row.add_suffix(self._button("Cambiar…", lambda: self._pick(self._on_notes_dir)))
        if not welcome:
            self.notes_row.add_suffix(self._icon_button("folder-open-symbolic", "Abrir carpeta",
                                                        lambda: self._open(self.notes_dir)))
        notes.add(self.notes_row)
        page.add(notes)

        # ---- copias ----
        backups = Adw.PreferencesGroup(
            title="Copias de seguridad",
            description="Una por hora (quedan las últimas 72). Mejor fuera de la carpeta "
                        "sincronizada, así no dependen de Dropbox.",
        )
        self.backups_row = Adw.ActionRow(title="Carpeta de las copias", subtitle=_pretty(self.backups_dir))
        self.backups_row.add_suffix(self._button("Cambiar…", lambda: self._pick(self._on_backups_dir)))
        self.backups_row.add_suffix(self._icon_button("folder-open-symbolic", "Abrir carpeta",
                                                      lambda: self._open(self.backups_dir)))
        backups.add(self.backups_row)
        page.add(backups)

        # ---- sistema ----
        system = Adw.PreferencesGroup(title="Sistema")
        self.shortcuts_row = Adw.SwitchRow(title="Atajos de teclado", subtitle=SHORTCUTS_HELP,
                                           active=welcome or shortcuts.installed())
        self.autostart_row = Adw.SwitchRow(
            title="Abrir al iniciar sesión",
            subtitle="En segundo plano, para que los atajos funcionen siempre",
            active=welcome or config.autostart_enabled(),
        )
        if not welcome:
            self.shortcuts_row.connect("notify::active", lambda *_: self._apply_shortcuts())
            self.autostart_row.connect("notify::active", lambda *_: self._apply_autostart())
        system.add(self.shortcuts_row)
        system.add(self.autostart_row)
        page.add(system)

        # El contenido se desplaza; la barra de arriba y el botón de abajo quedan siempre a la vista.
        self.toasts = Adw.ToastOverlay(child=page)
        view = Adw.ToolbarView(content=self.toasts)
        view.add_top_bar(Adw.HeaderBar())
        if welcome:
            start = Gtk.Button(label="Empezar", halign=Gtk.Align.CENTER, margin_top=10, margin_bottom=10,
                               tooltip_text="Después se cambia desde el menú → Preferencias")
            start.add_css_class("suggested-action")
            start.add_css_class("pill")
            start.connect("clicked", self._on_start)
            view.add_bottom_bar(start)
            view.set_bottom_bar_style(Adw.ToolbarStyle.RAISED)
        self.set_child(view)

    # ---------- helpers ----------

    def _button(self, label, callback):
        btn = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
        btn.connect("clicked", lambda *_: callback())
        return btn

    def _icon_button(self, icon, tooltip, callback):
        btn = Gtk.Button(icon_name=icon, tooltip_text=tooltip, valign=Gtk.Align.CENTER)
        btn.add_css_class("flat")
        btn.connect("clicked", lambda *_: callback())
        return btn

    def _open(self, folder):
        os.makedirs(folder, exist_ok=True)
        Gtk.FileLauncher.new(Gio.File.new_for_path(folder)).launch(self.get_root(), None, None)

    def _pick(self, on_folder):
        chooser = Gtk.FileDialog(title="Elegir carpeta", modal=True)
        parent = os.path.dirname(self.notes_dir)
        if os.path.isdir(parent):
            chooser.set_initial_folder(Gio.File.new_for_path(parent))

        def on_done(_chooser, result):
            try:
                folder = chooser.select_folder_finish(result)
            except GLib.Error:
                return  # cancelado
            on_folder(folder.get_path())

        chooser.select_folder(self.get_root(), None, on_done)

    # ---------- cambios ----------

    def _on_notes_dir(self, folder):
        self.notes_dir = folder
        self.notes_row.set_subtitle(_pretty(folder))
        if not self.welcome:
            self._apply_notes_dir()

    def _on_backups_dir(self, folder):
        self.backups_dir = folder
        self.backups_row.set_subtitle(_pretty(folder))
        if not self.welcome:
            config.set_backups_dir(folder)

    def _apply_notes_dir(self):
        target = os.path.join(self.notes_dir, config.NOTES_FILENAME)
        if os.path.abspath(target) == os.path.abspath(self.store.path):
            config.set_notes_dir(self.notes_dir)
            self.store.save_now()  # la primera vez, crea el archivo con la nota de ejemplo
            return
        old = self.store.path
        existed = os.path.exists(target)
        os.makedirs(self.notes_dir, exist_ok=True)
        # Si ya hay un notitas.md ahí (otra máquina, una instalación anterior), se usa ese.
        self.store.relocate(self.notes_dir, adopt_existing=True)
        if existed:
            msg = f"Usando las notas que ya había en {_pretty(self.notes_dir)}"
        else:
            msg = f"Notas guardadas en {_pretty(self.notes_dir)}"
        if os.path.exists(old) and not self.welcome:
            msg += f". El archivo anterior quedó en {_pretty(old)}"
        self.toasts.add_toast(Adw.Toast(title=msg, timeout=6))

    def _apply_shortcuts(self):
        from .app import launcher_command

        try:
            if self.shortcuts_row.get_active():
                shortcuts.install(launcher_command())
            else:
                shortcuts.uninstall()
        except RuntimeError as e:
            self.toasts.add_toast(Adw.Toast(title=str(e), timeout=8))

    def _apply_autostart(self):
        from .app import launcher_command

        config.set_autostart(self.autostart_row.get_active(), launcher_command())

    def _on_start(self, _btn):
        self._apply_notes_dir()
        if self.backups_dir != config.default_backups_dir():
            config.set_backups_dir(self.backups_dir)
        self._apply_shortcuts()
        self._apply_autostart()
        config.mark_setup_done()
        self.close()
