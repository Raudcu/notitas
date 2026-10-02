"""Ventanita de captura rápida: un cuadrado del color de la nota con foco en el texto."""

from gi.repository import Gdk, GLib, Gtk, Pango

from . import style, x11


class QuickCapture(Gtk.Window):
    def __init__(self, app, store, note):
        super().__init__(application=app, title=f"Notitas · {note.title or 'Sin título'}")
        self.store = store
        self.note_id = note.id
        self._had_focus = False

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(300, 150)
        self.add_css_class("quick")
        style.set_color_class(self, "postit", note.color)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("quick-frame")
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_bottom(8)

        header = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        header.add_css_class("header")
        header.set_margin_top(6)
        category = store.category(note.category_id)
        header.set_label(f"{category.name if category else 'Sin categoría'} - {note.title or 'Sin título'}")
        box.append(header)

        self.view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, vexpand=True)
        self.view.add_css_class("note-text")
        scroller = Gtk.ScrolledWindow(child=self.view, vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.append(scroller)

        what = "agrega tarea" if note.tasks else "guarda"
        hint = Gtk.Label(label=f"Enter {what} · Shift+Enter otra línea · Esc cancela", xalign=0)
        hint.add_css_class("hint")
        box.append(hint)
        self.set_child(box)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("notify::is-active", self._on_active_changed)

    def show_focused(self):
        present(self)
        self.view.grab_focus()

    def _on_key(self, _ctrl, keyval, _code, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not state & Gdk.ModifierType.SHIFT_MASK:
            buf = self.view.get_buffer()
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            self.store.append(self.note_id, text)
            self.store.save_now()
            self.close()
            return True
        return False

    def _on_active_changed(self, *_):
        # Si pierde el foco estando vacía, se cierra sola (click afuera = cancelar).
        if self.is_active():
            self._had_focus = True
        elif self._had_focus:
            buf = self.view.get_buffer()
            if buf.get_char_count() == 0:
                self.close()


class QuickMessage(Gtk.Window):
    """Aviso breve que se cierra solo (p. ej. "no hay nota con ese número")."""

    def __init__(self, app, text, color="gris", detail=None):
        super().__init__(application=app)
        self.set_decorated(False)
        self.set_default_size(280, 70)
        self.add_css_class("quick")
        style.set_color_class(self, "postit", color)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(12)
        label = Gtk.Label(label=text, wrap=True, justify=Gtk.Justification.CENTER)
        label.add_css_class("header")
        box.append(label)
        if detail:
            sub = Gtk.Label(label=detail, ellipsize=Pango.EllipsizeMode.END, max_width_chars=36)
            sub.add_css_class("hint")
            box.append(sub)
        self.set_child(box)
        self.connect("realize", self._on_realize)
        GLib.timeout_add(2000, self._timeout)

    def _on_realize(self, _win):
        # Es sólo un aviso: no tiene que sacarle el foco a lo que estés usando.
        # En X11 se muestra fuera del gestor de ventanas y la centramos a mano.
        xid = x11.xid_of(self)
        if xid:
            x11.make_unmanaged(xid)
            self.get_surface().connect("notify::mapped", lambda s, _p: s.get_mapped() and self._center(xid))
            # Recién después del primer cuadro GTK sabe el tamaño real: centrar de nuevo.
            self.connect("notify::default-width", lambda *_: self._center(xid))
            GLib.timeout_add(60, lambda: self._center(xid) and False)

    def _center(self, xid):
        px, py = x11.pointer()
        monitors = self.get_display().get_monitors()
        area = None
        for i in range(monitors.get_n_items()):
            geo = monitors.get_item(i).get_geometry()
            if geo.x <= px < geo.x + geo.width and geo.y <= py < geo.y + geo.height:
                area = geo
        if area is None and monitors.get_n_items():
            area = monitors.get_item(0).get_geometry()
        if area:
            width = self.get_width() or self.get_default_size()[0]
            height = self.get_height() or self.get_default_size()[1]
            x = area.x + (area.width - width) // 2
            y = area.y + (area.height - height) // 2
            x11.place(xid, x, y)

    def _timeout(self):
        self.close()
        return GLib.SOURCE_REMOVE


def present(window):
    """present() que además se asegura de que la ventana reciba el foco.

    En X11, Mutter suele mostrar sin foco una ventana abierta desde un atajo
    global (prevención de robo de foco); ahí le pedimos el foco explícitamente.
    """
    window.present()
    xid = x11.xid_of(window)
    if xid:
        # Un toque de demora para que el gestor ya haya mapeado la ventana.
        GLib.timeout_add(40, lambda: x11.activate(xid) and False)
