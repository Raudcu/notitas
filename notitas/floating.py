"""Post-it flotante: una nota en una ventanita siempre encima.

Se puede hacer semitransparente, achicar a solo el título (doble clic en la
barra) y cambiar el tamaño de letra. Todo eso se recuerda junto con la posición.
"""

from gi.repository import GLib, Gtk, Pango

from . import style, x11
from .noteview import NoteView

DEFAULT_SIZE = (280, 280)
ZOOMS = [80, 90, 100, 115, 130, 150]  # % del tamaño de letra


class FloatingNote(Gtk.Window):
    def __init__(self, app, store, note_id, geometry=None):
        super().__init__(application=app)
        self.app = app
        self.store = store
        self.note_id = note_id
        geo = geometry or {}
        self._geometry = geo
        self.opacity = geo.get("opacity", 1.0)
        self.zoom = geo.get("zoom", 100)
        self.compact = False
        self._full_height = geo.get("h", DEFAULT_SIZE[1])
        note = store.note(note_id)

        self.set_default_size(geo.get("w", DEFAULT_SIZE[0]), self._full_height)
        self.add_css_class("floating")

        # Barra de título propia: se arrastra desde acá; GTK agrega bordes para redimensionar.
        bar = Gtk.Box(spacing=4)
        bar.add_css_class("floating-header")
        self.badge = Gtk.Label(valign=Gtk.Align.CENTER)
        self.badge.add_css_class("badge")
        self.title_label = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.title_label.add_css_class("title")
        self.edit = Gtk.ToggleButton(icon_name="document-edit-symbolic", tooltip_text="Editar como texto")
        options = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="Opciones",
                                 popover=self._build_options())
        close = Gtk.Button(icon_name="window-close-symbolic", tooltip_text="Despegar (cerrar)")
        close.connect("clicked", lambda *_: self.close())
        for btn in (self.edit, options, close):
            btn.add_css_class("flat")
            btn.add_css_class("circular")
        for w in (self.badge, self.title_label, self.edit, options, close):
            bar.append(w)
        handle = Gtk.WindowHandle(child=bar)
        # Doble clic = compacto. Se atrapa antes que la barra, que si no maximizaría la ventana.
        dbl = Gtk.GestureClick(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        dbl.connect("pressed", self._on_header_click)
        handle.add_controller(dbl)
        self.set_titlebar(handle)

        self.view = NoteView(store, note_id)
        self.view.set_margin_top(6)
        self.view.set_margin_start(10)
        self.view.set_margin_end(6)
        self.view.set_margin_bottom(6)
        self.edit.connect("toggled", lambda b: self.view.set_editing(b.get_active()))
        self.view.connect("notify::visible-child-name", lambda v, _p: self.edit.set_active(v.editing))
        self.set_child(self.view)

        self._handlers = [
            store.connect("note-changed", self._on_note_changed),
            store.connect("changed", self._on_structure_changed),
        ]
        self.connect("realize", self._on_realize)
        self.connect("destroy", lambda *_: [store.disconnect(h) for h in self._handlers])
        self._refresh_header(note)
        self._apply_zoom()
        self.set_opacity(self.opacity)
        if geo.get("compact"):
            self.set_compact(True)

    def _on_header_click(self, gesture, n_press, _x, _y):
        if n_press == 2:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.set_compact(not self.compact)

    # ---------- opciones ----------

    def _build_options(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(8)

        box.append(Gtk.Label(label="Opacidad", xalign=0))
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 30, 100, 5)
        scale.set_value(round(self.opacity * 100))
        scale.set_size_request(180, -1)
        scale.connect("value-changed", self._on_opacity)
        box.append(scale)

        box.append(Gtk.Label(label="Tamaño de letra", xalign=0))
        zoom = Gtk.Box(spacing=6, homogeneous=True)
        for icon, step in (("zoom-out-symbolic", -1), ("zoom-in-symbolic", 1)):
            btn = Gtk.Button(icon_name=icon)
            btn.connect("clicked", lambda _b, s=step: self._step_zoom(s))
            zoom.append(btn)
        box.append(zoom)

        compact = Gtk.Button(label="Achicar a solo el título")
        compact.set_tooltip_text("También con doble clic en la barra")
        compact.connect("clicked", lambda *_: self.set_compact(not self.compact))
        box.append(compact)

        open_btn = Gtk.Button(label="Abrir en Notitas")
        open_btn.connect("clicked", lambda *_: self.app.open_in_editor(self.note_id))
        box.append(open_btn)
        return Gtk.Popover(child=box)

    def _on_opacity(self, scale):
        self.opacity = scale.get_value() / 100
        self.set_opacity(self.opacity)

    def _step_zoom(self, step):
        index = ZOOMS.index(self.zoom) + step if self.zoom in ZOOMS else ZOOMS.index(100)
        self.zoom = ZOOMS[min(max(index, 0), len(ZOOMS) - 1)]
        self._apply_zoom()

    def _apply_zoom(self):
        for z in ZOOMS:
            self.view.remove_css_class(f"zoom-{z}")
        self.view.add_css_class(f"zoom-{self.zoom}")

    def set_compact(self, compact):
        if compact == self.compact:
            return
        if compact:
            self._full_height = self.get_height() or self._full_height
        self.compact = compact
        self.view.set_visible(not compact)
        # Sin contenido, la ventana se encoge a la altura de la barra.
        width = self.get_width() or self.get_default_size()[0]
        self.set_default_size(width, 1 if compact else self._full_height)

    # ---------- gestor de ventanas ----------

    def _on_realize(self, _win):
        # Recién cuando el gestor de ventanas la mapea acepta "siempre encima" y moverla.
        surface = self.get_surface()
        surface.connect("notify::mapped", self._on_mapped)

    def _on_mapped(self, surface, _pspec):
        # Mutter ignora estos pedidos si llegan en el mismo instante del mapeo: darle un respiro.
        if surface.get_mapped():
            GLib.timeout_add(250, self._apply_wm_hints)

    def _apply_wm_hints(self):
        xid = x11.xid_of(self)
        if xid:
            if "x" in self._geometry:
                x11.move(xid, self._geometry["x"], self._geometry["y"])
            x11.set_states(xid, "ABOVE", "STICKY", "SKIP_TASKBAR", "SKIP_PAGER")
        return GLib.SOURCE_REMOVE

    def geometry(self):
        height = self._full_height if self.compact else (self.get_height() or DEFAULT_SIZE[1])
        geo = {
            "w": self.get_width() or DEFAULT_SIZE[0],
            "h": height,
            "opacity": self.opacity,
            "zoom": self.zoom,
            "compact": self.compact,
        }
        xid = x11.xid_of(self)
        if xid:
            geo["x"], geo["y"] = x11.position(xid)
        return geo

    # ---------- nota ----------

    def _refresh_header(self, note):
        self.set_title(f"Notitas · {note.title or 'Sin título'}")
        style.set_color_class(self, "postit", note.color)
        style.set_color_class(self.badge, "badge", note.color)
        self.view.set_color(note.color)
        self.badge.set_visible(note.number is not None)
        self.badge.set_label(str(note.number or ""))
        self.title_label.set_label(note.title or "Sin título")

    def _on_note_changed(self, _store, note_id):
        note = self.store.note(note_id)
        if note_id == self.note_id and note:
            self._refresh_header(note)

    def _on_structure_changed(self, _store):
        note = self.store.note(self.note_id)
        if note is None:
            self.close()
        else:
            self._refresh_header(note)
