"""Contenido de una nota: vista con formato (tareas tildables, links…) o texto crudo.

Al tildar una tarea se tacha, y después de un momento se desliza hacia
"Archivadas", una sección plegada al final donde lo último archivado queda primero.
"""

from gi.repository import GLib, Gtk, Pango

from . import markup
from .blame import BlameHover, format_ts

STRIKE_DELAY_MS = 900  # cuánto se ve tachado antes de irse
SLIDE_MS = 250


class NoteView(Gtk.Stack):
    def __init__(self, store, note_id):
        super().__init__(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.store = store
        self.note_id = note_id
        self._pending = {}  # texto de la tarea tildada -> id del timeout
        self._syncing = False
        self._archive_open = False
        note = store.note(note_id)

        # ---- vista con formato ----
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.add_entry = Gtk.Entry(hexpand=True)
        self.add_entry.add_css_class("add-line")
        self.add_entry.connect("activate", self._on_add)
        self.archive = Gtk.Expander(margin_top=10)
        self.archive.add_css_class("archive")
        self.archive.connect("notify::expanded", lambda e, _p: setattr(self, "_archive_open", e.get_expanded()))
        self.archive_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=4)
        self.archive.set_child(self.archive_rows)

        view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        view.add_css_class("note-view")
        for w in (self.rows, self.add_entry, self.archive):
            view.append(w)
        self.add_named(Gtk.ScrolledWindow(child=view, hscrollbar_policy=Gtk.PolicyType.NEVER), "view")

        # ---- edición como texto ----
        self.text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=4, left_margin=2)
        self.text.add_css_class("note-text")
        self.text.get_buffer().connect("changed", self._on_text_changed)
        self.blame = BlameHover(self.text, self._line_ts, note.color)
        self.add_named(Gtk.ScrolledWindow(child=self.text), "edit")

        handler = store.connect("note-changed", self._on_note_changed)
        self.connect("destroy", lambda *_: store.disconnect(handler))
        self.render()

    # ---------- modo ----------

    @property
    def editing(self):
        return self.get_visible_child_name() == "edit"

    def set_editing(self, editing, line=None):
        note = self.store.note(self.note_id)
        if not note:
            return
        if editing:
            self._syncing = True
            self.text.get_buffer().set_text(note.content)
            self._syncing = False
            self.set_visible_child_name("edit")
            buf = self.text.get_buffer()
            it = buf.get_iter_at_line(line)[1] if line is not None else buf.get_end_iter()
            if line is not None:
                it.forward_to_line_end()
            buf.place_cursor(it)
            GLib.idle_add(lambda: self.text.grab_focus() and False)
        else:
            self.set_visible_child_name("view")
            self.render()

    def set_color(self, color):
        self.blame.set_color(color)

    def _line_ts(self, index):
        note = self.store.note(self.note_id)
        return note.line_ts(index) if note else None

    # ---------- render ----------

    def render(self):
        note = self.store.note(self.note_id)
        if not note:
            return
        self.add_entry.set_placeholder_text("Agregar tarea…" if note.tasks else "Agregar línea…")
        for box in (self.rows, self.archive_rows):
            while child := box.get_first_child():
                box.remove(child)
        for index, (raw, ts) in enumerate(note.lines):
            self.rows.append(self._row(raw, ts, index=index))
        for index, (raw, ts, done) in enumerate(note.archived):
            self.archive_rows.append(self._row(raw, ts, archived_index=index, done=done))
        self.archive.set_visible(bool(note.archived))
        self.archive.set_label("Archivadas")
        self.archive.set_expanded(self._archive_open)

    def _row(self, raw, ts, index=None, archived_index=None, done=None):
        line = markup.classify(raw)
        if line.kind == "blank":
            return Gtk.Box(height_request=8)
        archived = archived_index is not None
        pending = not archived and raw in self._pending

        box = Gtk.Box(spacing=6, margin_start=line.indent * 20)
        if line.kind == "task":
            check = Gtk.CheckButton(active=line.checked or archived or pending, valign=Gtk.Align.START)
            box.append(check)
        elif line.kind in ("bullet", "numbered"):
            bullet = Gtk.Label(label="•" if line.kind == "bullet" else line.marker, valign=Gtk.Align.START)
            bullet.add_css_class("bullet")
            box.append(bullet)
        label = Gtk.Label(
            use_markup=True, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
            xalign=0, hexpand=True, max_width_chars=1,
        )
        label.set_markup(markup.inline(line.text))
        if line.checked or archived or pending:
            label.add_css_class("done")
        box.append(label)

        # Hora al pasar el mouse, encima del final de la fila (no empuja el texto).
        overlay = Gtk.Overlay(child=box)
        overlay.add_css_class("note-row")
        when = f"hecha {format_ts(done)}" if done else format_ts(ts)
        if when:
            stamp = Gtk.Label(label=when, halign=Gtk.Align.END, valign=Gtk.Align.START,
                              visible=False, can_target=False)
            stamp.add_css_class("blame")
            stamp.add_css_class("row-stamp")
            overlay.add_overlay(stamp)
            motion = Gtk.EventControllerMotion()
            motion.connect("enter", lambda *_: stamp.set_visible(True))
            motion.connect("leave", lambda *_: stamp.set_visible(False))
            overlay.add_controller(motion)

        revealer = Gtk.Revealer(child=overlay, reveal_child=True,
                                transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
                                transition_duration=SLIDE_MS)
        if line.kind == "task":
            if archived:
                check.connect("toggled", self._on_unarchive, archived_index, raw)
            else:
                check.connect("toggled", self._on_task_toggled, raw, label, revealer)
        if not archived:
            # Doble clic: editar el texto con el cursor en esa línea.
            dbl = Gtk.GestureClick()
            dbl.connect("pressed", lambda _g, n, *_: n == 2 and self.set_editing(True, line=index))
            label.add_controller(dbl)
        return revealer

    # ---------- tareas ----------

    def _on_task_toggled(self, check, raw, label, revealer):
        if check.get_active():
            label.add_css_class("done")
            self._pending[raw] = GLib.timeout_add(STRIKE_DELAY_MS, self._slide_away, raw, revealer)
        else:
            label.remove_css_class("done")
            source = self._pending.pop(raw, None)
            if source:
                GLib.source_remove(source)

    def _slide_away(self, raw, revealer):
        revealer.set_reveal_child(False)
        self._pending[raw] = GLib.timeout_add(SLIDE_MS, self._archive, raw)
        return GLib.SOURCE_REMOVE

    def _archive(self, raw):
        self._pending.pop(raw, None)
        note = self.store.note(self.note_id)
        if note:
            index = next((i for i, (t, _ts) in enumerate(note.lines) if t == raw), None)
            if index is not None:
                self.store.archive_line(self.note_id, index, raw)
        return GLib.SOURCE_REMOVE

    def _on_unarchive(self, check, index, raw):
        if not check.get_active():
            self.store.unarchive(self.note_id, index, raw)

    def _on_add(self, entry):
        text = entry.get_text().strip()
        if text:
            self.store.append(self.note_id, text)
            entry.set_text("")

    # ---------- sincronización ----------

    def _on_text_changed(self, buf):
        if not self._syncing:
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            self.store.update_note(self.note_id, content=text)

    def _on_note_changed(self, _store, note_id):
        if note_id != self.note_id:
            return
        note = self.store.note(note_id)
        if not note:
            return
        if self.editing:
            buf = self.text.get_buffer()
            if buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False) != note.content:
                self._syncing = True
                buf.set_text(note.content)
                self._syncing = False
        else:
            self.render()
