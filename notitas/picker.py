"""Selector general (Ctrl+Alt+0): buscar cualquier nota y elegir qué hacer con ella."""

from gi.repository import Gdk, Gtk, Pango

from . import style

HINT = "Enter agregar · Ctrl+Enter post-it flotante · Alt+Enter abrir · Esc cerrar"


class NotePicker(Gtk.Window):
    def __init__(self, app, store, on_pick):
        """on_pick(note_id, modo) con modo en {"quick", "float", "edit"}."""
        super().__init__(application=app, title="Notitas · buscar")
        self.store = store
        self.on_pick = on_pick
        self._had_focus = False

        self.set_decorated(False)
        self.set_default_size(460, 400)
        self.add_css_class("picker")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(10)
        self.entry = Gtk.SearchEntry(placeholder_text="Buscar nota, o escribir el título de una nueva…")
        self.entry.connect("search-changed", lambda *_: self._populate())
        box.append(self.entry)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE)
        self.list.add_css_class("boxed-list")
        self.list.connect("row-activated", lambda _l, row: self._pick(row, "quick"))
        box.append(Gtk.ScrolledWindow(child=self.list, vexpand=True, propagate_natural_height=False))

        hint = Gtk.Label(label=HINT, xalign=0, wrap=True)
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        box.append(hint)
        self.set_child(box)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("notify::is-active", self._on_active_changed)
        self._populate()

    def _matches(self):
        query = self.entry.get_text().strip().casefold()
        cats = {c.id: c.name for c in self.store.categories}
        notes = sorted(self.store.notes, key=lambda n: n.updated, reverse=True)
        notes.sort(key=lambda n: (n.number is None, n.number or 0))
        if not query:
            return notes, cats
        in_title = [n for n in notes if query in f"{n.title} {cats.get(n.category_id, '')}".casefold()]
        in_body = [n for n in notes if n not in in_title and query in n.content.casefold()]
        return in_title + in_body, cats

    def _populate(self):
        self.list.remove_all()
        notes, cats = self._matches()
        for note in notes:
            self.list.append(self._note_row(note, cats.get(note.category_id, "")))
        query = self.entry.get_text().strip()
        if query and not any(n.title.casefold() == query.casefold() for n in notes):
            first = self.store.categories[0].name
            row = _action_row(f"Crear nota «{query}»", f"en {first}", "list-add-symbolic")
            row.note_id = None
            self.list.append(row)
        first_row = self.list.get_row_at_index(0)
        if first_row:
            self.list.select_row(first_row)

    def _note_row(self, note, cat_name):
        row = Gtk.ListBoxRow()
        row.note_id = note.id
        box = Gtk.Box(spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(6)
        dot = Gtk.Label(label=str(note.number or ""), valign=Gtk.Align.CENTER)
        dot.add_css_class("badge")
        style.set_color_class(dot, "badge", note.color)
        title = Gtk.Label(label=note.title or "Sin título", xalign=0, hexpand=True,
                          ellipsize=Pango.EllipsizeMode.END)
        cat = Gtk.Label(label=cat_name)
        cat.add_css_class("dim-label")
        for w in (dot, title, cat):
            box.append(w)
        row.set_child(box)
        return row

    def _on_key(self, _ctrl, keyval, _code, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Up):
            row = self.list.get_selected_row()
            index = (row.get_index() if row else -1) + (1 if keyval == Gdk.KEY_Down else -1)
            target = self.list.get_row_at_index(max(index, 0))
            if target:
                self.list.select_row(target)
                target.grab_focus()
                self.entry.grab_focus_without_selecting()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            mode = "quick"
            if state & Gdk.ModifierType.CONTROL_MASK:
                mode = "float"
            elif state & Gdk.ModifierType.ALT_MASK:
                mode = "edit"
            self._pick(self.list.get_selected_row(), mode)
            return True
        return False

    def _pick(self, row, mode):
        if row is None:
            return
        note_id = row.note_id
        if note_id is None:
            note = self.store.add_note(self.store.categories[0].id, title=self.entry.get_text().strip())
            note_id = note.id
        self.close()
        self.on_pick(note_id, mode)

    def _on_active_changed(self, *_):
        if self.is_active():
            self._had_focus = True
        elif self._had_focus:
            self.close()


def _action_row(title, subtitle, icon):
    row = Gtk.ListBoxRow()
    box = Gtk.Box(spacing=10)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(6)
    box.append(Gtk.Image(icon_name=icon))
    label = Gtk.Label(label=title, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
    box.append(label)
    sub = Gtk.Label(label=subtitle)
    sub.add_css_class("dim-label")
    box.append(sub)
    row.set_child(box)
    return row
