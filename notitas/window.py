"""Ventana principal: categorías a la izquierda, post-its a la derecha."""

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from . import markup, style
from .noteview import NoteView
from .store import MAX_NUMBER, PALETTE

CARD_SIZE = 190


class NotesWindow(Adw.ApplicationWindow):
    def __init__(self, app, store):
        super().__init__(application=app, title="Notitas")
        self.store = store
        self.current_cat = store.categories[0].id if store.categories else None
        self.set_default_size(1000, 720)
        self.set_size_request(360, 320)
        # Cerrar la ventana no mata la app: sigue escuchando los atajos.
        self.set_hide_on_close(True)

        self.split = Adw.NavigationSplitView()
        self.split.set_sidebar(self._build_sidebar())
        self.split.set_content(self._build_content())
        self.toasts = Adw.ToastOverlay(child=self.split)
        self.set_content(self.toasts)

        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 600sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)

        self._install_actions()
        store.connect("changed", lambda *_: self.refresh())
        store.connect("note-changed", lambda _s, nid: self._refresh_card(nid))
        self.refresh()

    # ---------- construcción ----------

    def _build_sidebar(self):
        header = Adw.HeaderBar()
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Nueva categoría")
        add.connect("clicked", lambda *_: self._ask_name("Nueva categoría", "", self.store.add_category))
        header.pack_start(add)

        menu = Gio.Menu()
        menu.append("Buscar nota…", "app.pick")
        menu.append("Preferencias…", "app.preferences")
        menu.append("Abrir carpeta de las notas", "app.open-data")
        menu.append("Salir (dejar de escuchar atajos)", "app.quit")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu))

        self.cat_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.cat_list.add_css_class("navigation-sidebar")
        self.cat_list.connect("row-selected", self._on_cat_selected)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(Gtk.ScrolledWindow(child=self.cat_list, vexpand=True))
        return Adw.NavigationPage(title="Notitas", child=view)

    def _build_content(self):
        header = Adw.HeaderBar()
        add = Gtk.Button(label="Nueva nota")
        add.add_css_class("suggested-action")
        add.set_action_name("win.new-note")
        header.pack_start(add)

        cat_menu = Gio.Menu()
        cat_menu.append("Renombrar categoría", "win.rename-category")
        cat_menu.append("Eliminar categoría", "win.delete-category")
        self.cat_menu_button = Gtk.MenuButton(icon_name="view-more-symbolic", menu_model=cat_menu)
        header.pack_end(self.cat_menu_button)
        self.search_toggle = Gtk.ToggleButton(icon_name="system-search-symbolic",
                                              tooltip_text="Buscar en todas las notas (Ctrl+F)")
        header.pack_end(self.search_toggle)

        self.search_entry = Gtk.SearchEntry(placeholder_text="Buscar en todas las notas…", hexpand=True)
        self.search_entry.connect("search-changed", lambda *_: self.refresh())
        self.search_entry.connect("stop-search", lambda *_: self.search_bar.set_search_mode(False))
        clamp = Adw.Clamp(child=self.search_entry, maximum_size=500)
        self.search_bar = Gtk.SearchBar(child=clamp)
        self.search_bar.connect_entry(self.search_entry)
        self.search_bar.bind_property("search-mode-enabled", self.search_toggle, "active",
                                      GObject.BindingFlags.BIDIRECTIONAL)
        self.search_bar.connect("notify::search-mode-enabled", self._on_search_mode)

        self.flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            max_children_per_line=12,
            min_children_per_line=1,
            row_spacing=8,
            column_spacing=8,
            valign=Gtk.Align.START,
        )
        for side in ("top", "bottom", "start", "end"):
            getattr(self.flow, f"set_margin_{side}")(18)
        self.flow.connect("child-activated", lambda _f, child: self.open_editor(child.note_id))

        self.empty = Adw.StatusPage(
            icon_name="document-new-symbolic",
            title="Sin notas",
            description="Creá una con «Nueva nota».",
        )
        self.stack = Gtk.Stack()
        self.stack.add_named(Gtk.ScrolledWindow(child=self.flow, vexpand=True), "notes")
        self.stack.add_named(self.empty, "empty")

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.add_top_bar(self.search_bar)
        view.set_content(self.stack)
        self.content_page = Adw.NavigationPage(title="", child=view)
        return self.content_page

    def _install_actions(self):
        def add(name, cb):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_: cb())
            self.add_action(action)

        add("new-note", self._new_note)
        add("search", lambda: self.search_bar.set_search_mode(True))
        shortcuts_ctl = Gtk.ShortcutController(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        shortcuts_ctl.add_shortcut(Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string("<Control>f"),
                                                action=Gtk.NamedAction.new("win.search")))
        self.add_controller(shortcuts_ctl)
        add("rename-category", self._rename_category)
        add("delete-category", self._delete_category)

    # ---------- refresco ----------

    def refresh(self):
        store = self.store
        if not store.category(self.current_cat):
            self.current_cat = store.categories[0].id if store.categories else None

        self.cat_list.remove_all()
        for cat in store.categories:
            count = len(store.notes_in(cat.id))
            row = Adw.ActionRow(title=cat.name, subtitle=f"{count} nota{'s' if count != 1 else ''}")
            row.cat_id = cat.id
            drop = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)
            drop.connect("drop", self._on_drop_on_category, cat.id)
            row.add_controller(drop)
            self.cat_list.append(row)
            if cat.id == self.current_cat:
                self.cat_list.select_row(row)

        cat = store.category(self.current_cat)
        query = self.search_entry.get_text().strip() if self.search_bar.get_search_mode() else ""
        self.lookup_action("new-note").set_enabled(cat is not None and not query)
        self.cat_menu_button.set_sensitive(not query)

        self.flow.remove_all()
        self._cards = {}
        if query:
            self.content_page.set_title("Resultados")
            names = {c.id: c.name for c in store.categories}
            notes = store.search(query)
            cards = [NoteCard(n, self, highlight=query, category_name=names.get(n.category_id)) for n in notes]
            self.empty.set_title("Nada por acá")
            self.empty.set_description(f"Ninguna nota contiene «{query}».")
        else:
            self.content_page.set_title(cat.name if cat else "Notitas")
            notes = store.notes_in(self.current_cat) if cat else []
            cards = [NoteCard(n, self) for n in notes]
            self.empty.set_title("Sin notas")
            self.empty.set_description("Creá una con «Nueva nota».")
        for card in cards:
            self._cards[card.note_id] = card
            self.flow.append(card)
        self.stack.set_visible_child_name("notes" if cards else "empty")

    def _refresh_card(self, note_id):
        card = getattr(self, "_cards", {}).get(note_id)
        note = self.store.note(note_id)
        if card and note:
            card.update(note)

    def _on_drop_on_category(self, _target, note_id, _x, _y, cat_id):
        # Se difiere: mover la nota reconstruye la lista mientras termina el arrastre.
        GLib.idle_add(lambda: self.store.move_note(note_id, category_id=cat_id) and False)
        return True

    def _on_search_mode(self, bar, _pspec):
        if not bar.get_search_mode():
            self.search_entry.set_text("")
        self.refresh()

    def _on_cat_selected(self, _list, row):
        if row and row.cat_id != self.current_cat:
            self.current_cat = row.cat_id
            if self.search_bar.get_search_mode():
                self.search_bar.set_search_mode(False)  # esto ya refresca
            else:
                self.refresh()
        if row:
            self.split.set_show_content(True)

    # ---------- acciones ----------

    def _new_note(self):
        note = self.store.add_note(self.current_cat)
        self.open_editor(note.id)

    def open_editor(self, note_id):
        NoteEditor(self.store, note_id).present(self)

    def show_note(self, note_id):
        """Ir a la categoría de la nota y abrirla."""
        note = self.store.note(note_id)
        if not note:
            return
        if note.category_id != self.current_cat and not self.search_bar.get_search_mode():
            self.current_cat = note.category_id
            self.refresh()
        self.split.set_show_content(True)
        self.open_editor(note_id)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))

    def _rename_category(self):
        cat = self.store.category(self.current_cat)
        if cat:
            self._ask_name(
                "Renombrar categoría", cat.name, lambda name: self.store.rename_category(cat.id, name)
            )

    def _delete_category(self):
        cat = self.store.category(self.current_cat)
        if not cat:
            return
        count = len(self.store.notes_in(cat.id))
        dialog = Adw.AlertDialog(
            heading=f"¿Eliminar «{cat.name}»?",
            body=f"Se borran también sus {count} notas." if count else "La categoría está vacía.",
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("delete", "Eliminar")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect(
            "response", lambda _d, r: r == "delete" and self.store.delete_category(cat.id)
        )
        dialog.present(self)

    def _ask_name(self, heading, initial, on_ok):
        entry = Gtk.Entry(text=initial, activates_default=True)
        dialog = Adw.AlertDialog(heading=heading, extra_child=entry)
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("ok", "Aceptar")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")
        dialog.connect(
            "response", lambda _d, r: r == "ok" and entry.get_text().strip() and on_ok(entry.get_text())
        )
        dialog.present(self)
        entry.grab_focus()


class NoteCard(Gtk.FlowBoxChild):
    """Un post-it en la grilla. Se puede arrastrar para reordenar o mover de categoría."""

    def __init__(self, note, window, highlight=None, category_name=None):
        super().__init__()
        self.note_id = note.id
        self.window = window
        self.highlight = highlight
        self.category_name = category_name
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.add_css_class("postit")
        self.box.set_size_request(CARD_SIZE, CARD_SIZE)

        top = Gtk.Box(spacing=8)
        self.badge = Gtk.Label(valign=Gtk.Align.CENTER)
        self.badge.add_css_class("badge")
        self.title = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END, use_markup=True)
        self.title.add_css_class("title")
        top.append(self.badge)
        top.append(self.title)

        self.preview = Gtk.Label(
            xalign=0, yalign=0, vexpand=True, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
            lines=8, ellipsize=Pango.EllipsizeMode.END, max_width_chars=1, hexpand=True, use_markup=True,
        )
        self.preview.add_css_class("preview")
        self.footer = Gtk.Label(xalign=0)
        self.footer.add_css_class("dim")
        self.footer.add_css_class("caption")

        self.box.append(top)
        self.box.append(self.preview)
        self.box.append(self.footer)
        self.set_child(self.box)
        self.update(note)

        menu = Gio.Menu()
        menu.append("Abrir", f"app.edit::{note.id}")
        menu.append("Post-it flotante (mostrar/ocultar)", f"app.float::{note.id}")
        self.popover = Gtk.PopoverMenu(menu_model=menu, has_arrow=False)
        self.popover.set_parent(self)
        self.connect("destroy", lambda *_: self.popover.unparent())
        click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        click.connect("pressed", self._on_right_click)
        self.add_controller(click)

        if highlight is None:  # en los resultados de búsqueda no se reordena
            self._setup_dnd()

    # ---------- arrastrar y soltar ----------

    def _setup_dnd(self):
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect("prepare", lambda *_: Gdk.ContentProvider.new_for_value(self.note_id))
        source.connect("drag-begin", self._on_drag_begin)
        source.connect("drag-end", lambda *_: self.remove_css_class("dragging"))
        self.add_controller(source)

        target = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)
        target.connect("motion", self._on_drag_motion)
        target.connect("leave", lambda *_: self._mark_drop(None))
        target.connect("drop", self._on_drop)
        self.add_controller(target)

    def _on_drag_begin(self, source, _drag):
        source.set_icon(Gtk.WidgetPaintable(widget=self.box), CARD_SIZE // 2, 20)
        self.add_css_class("dragging")

    def _on_drag_motion(self, _target, x, _y):
        self._mark_drop("after" if x > self.get_width() / 2 else "before")
        return Gdk.DragAction.MOVE

    def _mark_drop(self, side):
        for s in ("before", "after"):
            self.remove_css_class(f"drop-{s}")
        if side:
            self.add_css_class(f"drop-{side}")

    def _on_drop(self, _target, note_id, x, _y):
        self._mark_drop(None)
        after = x > self.get_width() / 2
        GLib.idle_add(lambda: self.window.store.move_note(note_id, self.note_id, after=after) and False)
        return True

    # ---------- contenido ----------

    def _on_right_click(self, _gesture, _n, x, y):
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self.popover.set_pointing_to(rect)
        self.popover.popup()

    def update(self, note):
        hl = self.highlight
        style.set_color_class(self.box, "postit", note.color)
        if note.number is None:
            self.badge.set_label("–")
            self.badge.add_css_class("empty")
            self.badge.set_tooltip_text("Sin atajo")
        else:
            self.badge.set_label(str(note.number))
            self.badge.remove_css_class("empty")
            self.badge.set_tooltip_text(f"Ctrl+Alt+{note.number}")
        style.set_color_class(self.badge, "badge", note.color)
        self.title.set_markup(markup.inline(note.title or "Sin título", hl))

        lines = [raw for raw, _ts in note.lines]
        if hl:
            # En una búsqueda, mostrar primero las líneas que coinciden (incluidas archivadas).
            archived = [raw for raw, _ts, _d in note.archived]
            hits = [raw for raw in lines + archived if hl.casefold() in raw.casefold()]
            lines = hits + [raw for raw in lines if raw not in hits]
        self.preview.set_markup("\n".join(markup.preview(raw, hl) for raw in lines) or "…")
        self.preview.set_opacity(1 if lines else 0.5)

        # En los resultados de búsqueda, de qué categoría es la nota.
        self.footer.set_label(self.category_name or "")
        self.footer.set_visible(bool(self.category_name))


class NoteEditor(Adw.Dialog):
    """Una nota abierta: título, color, número, categoría y contenido. Guarda solo."""

    def __init__(self, store, note_id):
        super().__init__(title="Nota", content_width=540, content_height=600)
        self.store = store
        self.note_id = note_id
        note = store.note(note_id)

        header = Adw.HeaderBar()
        delete = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Eliminar nota")
        delete.connect("clicked", self._on_delete)
        header.pack_start(delete)
        pin = Gtk.Button(icon_name="view-pin-symbolic", tooltip_text="Post-it flotante (siempre encima)")
        pin.set_action_name("app.float")
        pin.set_action_target_value(GLib.Variant("s", note_id))
        header.pack_end(pin)
        self.edit_toggle = Gtk.ToggleButton(icon_name="document-edit-symbolic",
                                            tooltip_text="Editar como texto (Markdown)")
        header.pack_end(self.edit_toggle)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.add_css_class("postit")
        for side in ("start", "end", "bottom"):
            getattr(body, f"set_margin_{side}")(12)
        self.body = body

        self.title = Gtk.Entry(text=note.title, placeholder_text="Título")
        self.title.add_css_class("note-title")
        self.title.connect("changed", lambda e: self.store.update_note(note_id, title=e.get_text()))
        body.append(self.title)

        # Fila de colores + tareas + número + categoría
        row = Gtk.Box(spacing=6)
        self.swatches = {}
        for name in PALETTE:
            btn = Gtk.Button(tooltip_text=name.capitalize(), valign=Gtk.Align.CENTER)
            btn.add_css_class("swatch")
            btn.add_css_class(f"swatch-{name}")
            btn.connect("clicked", lambda _b, c=name: self._set_color(c))
            self.swatches[name] = btn
            row.append(btn)
        row.append(Gtk.Box(hexpand=True))

        tasks = Gtk.ToggleButton(icon_name="checkbox-checked-symbolic", active=note.tasks,
                                 tooltip_text="Lo que agregues entra como tarea (con casilla)")
        tasks.add_css_class("flat")
        tasks.connect("toggled", lambda b: (self.store.update_note(note_id, tasks=b.get_active()),
                                            self.view.render()))
        row.append(tasks)

        numbers = ["Sin nº"] + [str(i) for i in range(1, MAX_NUMBER + 1)]
        self.number = Gtk.DropDown.new_from_strings(numbers)
        self.number.set_tooltip_text("Número del atajo Ctrl+Alt+N")
        self.number.set_selected(note.number or 0)
        self.number.connect("notify::selected", lambda d, _p: self.store.update_note(
            note_id, number=d.get_selected() or None))
        row.append(self.number)

        self.cats = list(store.categories)
        self.category = Gtk.DropDown.new_from_strings([c.name for c in self.cats])
        self.category.set_selected(next(i for i, c in enumerate(self.cats) if c.id == note.category_id))
        self.category.connect("notify::selected", lambda d, _p: self.store.update_note(
            note_id, category_id=self.cats[d.get_selected()].id))
        row.append(self.category)
        body.append(row)

        self.view = NoteView(store, note_id)
        body.append(self.view)
        self.edit_toggle.connect("toggled", lambda b: self.view.set_editing(b.get_active()))
        self.view.connect("notify::visible-child-name",
                          lambda v, _p: self.edit_toggle.set_active(v.editing))

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(body)
        self.set_child(toolbar)
        self._apply_color(note.color)

        handler = store.connect("changed", self._on_structure_changed)
        self.connect("closed", lambda *_: store.disconnect(handler))

    def _set_color(self, color):
        self._apply_color(color)
        self.store.update_note(self.note_id, color=color)

    def _apply_color(self, color):
        style.set_color_class(self.body, "postit", color)
        self.view.set_color(color)
        for name, btn in self.swatches.items():
            (btn.add_css_class if name == color else btn.remove_css_class)("selected")

    def _on_structure_changed(self, _store):
        note = self.store.note(self.note_id)
        if note is None:
            self.close()
        elif self.number.get_selected() != (note.number or 0):
            self.number.set_selected(note.number or 0)

    def _on_delete(self, _btn):
        dialog = Adw.AlertDialog(heading="¿Eliminar esta nota?")
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("delete", "Eliminar")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(_d, response):
            if response == "delete":
                self.close()
                GLib.idle_add(lambda: self.store.delete_note(self.note_id))

        dialog.connect("response", on_response)
        dialog.present(self)
