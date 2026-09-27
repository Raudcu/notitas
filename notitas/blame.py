"""Muestra en gris, al final de la línea bajo el mouse, cuándo se escribió (tipo "blame")."""

import datetime

from gi.repository import Gtk

from . import style

MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def format_ts(ts):
    try:
        when = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return ts or ""
    today = datetime.date.today()
    hour = when.strftime("%H:%M")
    if when.date() == today:
        return f"hoy {hour}"
    if when.date() == today - datetime.timedelta(days=1):
        return f"ayer {hour}"
    day = f"{when.day} {MONTHS[when.month - 1]}"
    if when.year == today.year:
        return f"{day} {hour}"
    return f"{day} {when.year}"


class BlameHover:
    def __init__(self, view, lookup, color):
        """lookup(índice_de_línea) -> "AAAA-MM-DD HH:MM" | None"""
        self.view = view
        self.lookup = lookup
        self.label = Gtk.Label(can_target=False, visible=False)
        self.label.add_css_class("blame")
        self.set_color(color)
        view.add_overlay(self.label, 0, 0)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", lambda *_: self.label.set_visible(False))
        view.add_controller(motion)
        # Al escribir se esconde: molesta tenerlo encima del texto.
        view.get_buffer().connect("changed", lambda *_: self.label.set_visible(False))

    def set_color(self, color):
        style.set_color_class(self.label, "postit", color)

    def _on_motion(self, _ctrl, x, y):
        view = self.view
        bx, by = view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        it, _top = view.get_line_at_y(by)
        line_y, line_h = view.get_line_yrange(it)
        ts = self.lookup(it.get_line()) if line_y <= by < line_y + line_h else None
        if not ts:
            self.label.set_visible(False)
            return
        end = it.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        rect = view.get_iter_location(end)
        self.label.set_label(format_ts(ts))
        width = self.label.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
        visible = view.get_visible_rect()
        bx = min(rect.x + 16, visible.x + visible.width - width - 6)
        view.move_overlay(self.label, max(bx, 0), rect.y)
        self.label.set_visible(True)
