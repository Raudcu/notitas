from gi.repository import Gdk, Gtk

from .store import PALETTE

BASE_CSS = """
.postit {
  border-radius: 3px;
  padding: 12px;
  color: #2b2b2b;
  box-shadow: 0 2px 5px alpha(black, 0.25);
}
.postit label.title { font-weight: bold; font-size: 1.05em; }
.postit label.preview { font-size: 0.95em; }
.postit label.dim { opacity: 0.6; }

.badge {
  border-radius: 999px;
  min-width: 24px;
  min-height: 24px;
  padding: 0 6px;
  color: white;
  font-weight: bold;
}
.badge.empty { background: alpha(black, 0.12); color: alpha(black, 0.45); }

flowboxchild { padding: 6px; border-radius: 4px; }
flowboxchild:focus-visible { outline: 2px solid alpha(black, 0.4); }

textview.note-text, textview.note-text text {
  background: transparent;
  color: #2b2b2b;
  caret-color: #2b2b2b;
  font-size: 1.05em;
}
entry.note-title {
  background: alpha(black, 0.06);
  color: #2b2b2b;
  font-weight: bold;
}

.swatch {
  min-width: 26px; min-height: 26px;
  padding: 0; border-radius: 999px;
  border: 2px solid alpha(black, 0.15);
}
.swatch.selected { border: 3px solid alpha(black, 0.65); }

label.blame {
  font-size: 0.8em;
  color: alpha(#2b2b2b, 0.55);
  padding: 0 4px;
  border-radius: 3px;
}

window.floating .floating-header {
  background: alpha(black, 0.07);
  padding: 4px 4px 4px 10px;
  min-height: 30px;
  color: #2b2b2b;
}
window.floating .floating-header label.title { font-weight: bold; }
window.floating .floating-header > button,
window.floating .floating-header > menubutton > button { color: #2b2b2b; min-width: 24px; min-height: 24px; }

/* vista de nota */
.note-view label, .note-view check { color: #2b2b2b; }
.note-view label.done { color: alpha(#2b2b2b, 0.45); text-decoration: line-through; }
.note-view label.bullet { min-width: 14px; }
.note-view label link, .postit label link { color: #1a56b0; }
.note-view check { margin-top: 1px; }
.note-view check:checked { background: alpha(#2b2b2b, 0.45); }
label.row-stamp { background: alpha(white, 0.75); }
button.row-trash { color: alpha(#2b2b2b, 0.45); min-width: 24px; min-height: 24px; padding: 0; }
button.row-trash:hover { color: #2b2b2b; }
entry.add-line {
  background: alpha(black, 0.05);
  color: #2b2b2b;
  box-shadow: none;
  border: 1px dashed alpha(black, 0.18);
}
expander.archive title label { color: alpha(#2b2b2b, 0.6); font-size: 0.9em; }
expander.archive arrow { color: alpha(#2b2b2b, 0.6); }
.postit label.dim { color: alpha(#2b2b2b, 0.55); }

/* arrastrar y soltar */
flowboxchild.dragging { opacity: 0.35; }
flowboxchild.drop-before { box-shadow: inset 4px 0 0 @accent_bg_color; }
flowboxchild.drop-after { box-shadow: inset -4px 0 0 @accent_bg_color; }
row.drop-above { box-shadow: inset 0 3px 0 @accent_bg_color; }
row.drop-below { box-shadow: inset 0 -3px 0 @accent_bg_color; }
.note-row.dragging { opacity: 0.35; }
.note-row.drop-above { box-shadow: inset 0 3px 0 alpha(#2b2b2b, 0.5); }
.note-row.drop-below { box-shadow: inset 0 -3px 0 alpha(#2b2b2b, 0.5); }

window.quick { border-radius: 0; }
window.quick .quick-frame { border-top: 6px solid alpha(black, 0.15); }
window.quick label.hint { font-size: 0.8em; opacity: 0.55; color: #2b2b2b; }
window.quick label.header { font-weight: bold; color: #2b2b2b; }
"""


def _zoom_css():
    return "\n".join(f".zoom-{z} {{ font-size: {z / 100:.2f}em; }}" for z in (80, 90, 100, 115, 130, 150))


def _palette_css():
    rules = []
    for name, (bg, accent) in PALETTE.items():
        rules.append(f".postit-{name}, window.quick.postit-{name} {{ background: {bg}; }}")
        rules.append(f".badge-{name} {{ background: {accent}; }}")
        rules.append(f".swatch-{name} {{ background: {bg}; }}")
    return "\n".join(rules)


def install():
    provider = Gtk.CssProvider()
    provider.load_from_string(BASE_CSS + _palette_css() + _zoom_css())
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def set_color_class(widget, prefix, color):
    for name in PALETTE:
        widget.remove_css_class(f"{prefix}-{name}")
    widget.add_css_class(f"{prefix}-{color}")
