"""Markdown mínimo → Pango markup: tareas, listas, **negrita**, *cursiva*,
~~tachado~~, `código` y links ([texto](url) o URLs sueltas)."""

import re
from dataclasses import dataclass

import gi

gi.require_version("Pango", "1.0")
from gi.repository import GLib, Pango  # noqa: E402

TASK_RE = re.compile(r"^(\s*)(?:[-*+] )?\[( |x|X)\] ?(.*)$")
BULLET_RE = re.compile(r"^(\s*)[-*+] (.*)$")
NUMBERED_RE = re.compile(r"^(\s*)(\d+[.)]) (.*)$")

TOKEN_RE = re.compile(
    r"`([^`]+)`"                                    # código
    r"|\[([^\]]+)\]\((https?://[^)\s]+)\)"          # [texto](url)
    r"|(https?://[^\s<>()]*[^\s<>().,;:!?'\"])"     # URL suelta
)
INLINE = [
    (re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])"), r"<i>\1</i>"),
    (re.compile(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)"), r"<i>\1</i>"),
    (re.compile(r"~~(?=\S)(.+?)(?<=\S)~~"), r"<s>\1</s>"),
]
HIGHLIGHT = '<span background="#ff8f00" bgalpha="35%">'


@dataclass
class Line:
    kind: str  # "task", "bullet", "numbered", "plain", "blank"
    text: str  # el texto sin el marcador
    indent: int = 0
    checked: bool = False
    marker: str = ""  # "1." para listas numeradas


def classify(raw):
    if not raw.strip():
        return Line("blank", "")
    m = TASK_RE.match(raw)
    if m:
        return Line("task", m.group(3), len(m.group(1)) // 2, m.group(2) != " ")
    m = BULLET_RE.match(raw)
    if m:
        return Line("bullet", m.group(2), len(m.group(1)) // 2)
    m = NUMBERED_RE.match(raw)
    if m:
        return Line("numbered", m.group(3), len(m.group(1)) // 2, marker=m.group(2))
    return Line("plain", raw)


def is_list_line(raw):
    return classify(raw).kind in ("task", "bullet", "numbered")


def as_task(raw, checked=False):
    """Convierte una línea en tarea (respetando la sangría)."""
    line = classify(raw)
    indent = "  " * line.indent
    return f"{indent}- [{'x' if checked else ' '}] {line.text}"


def _escape(text, highlight):
    if not highlight:
        return GLib.markup_escape_text(text)
    parts = re.split(f"({re.escape(highlight)})", text, flags=re.IGNORECASE)
    return "".join(
        f"{HIGHLIGHT}{GLib.markup_escape_text(p)}</span>" if i % 2 else GLib.markup_escape_text(p)
        for i, p in enumerate(parts)
    )


def _format(escaped):
    for regex, repl in INLINE:
        escaped = regex.sub(repl, escaped)
    return escaped


def inline(text, highlight=None):
    """Texto de una línea → Pango markup válido (si algo no cierra, cae a texto plano)."""
    out, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        out.append(_format(_escape(text[pos : m.start()], highlight)))
        if m.group(1):
            out.append(f"<tt>{_escape(m.group(1), highlight)}</tt>")
        else:
            url = m.group(3) or m.group(4)
            label = _format(_escape(m.group(2), highlight)) if m.group(2) else _escape(url, highlight)
            out.append(f'<a href="{GLib.markup_escape_text(url)}">{label}</a>')
        pos = m.end()
    out.append(_format(_escape(text[pos:], highlight)))
    result = "".join(out)
    try:
        # <a> es de Gtk.Label, no de Pango: se saca solo para validar.
        Pango.parse_markup(re.sub(r"</?a\b[^>]*>", "", result), -1, "\0")
        return result
    except GLib.Error:
        return _escape(text, highlight)


def preview(raw, highlight=None):
    """Una línea lista para el resumen de una tarjeta (con ☐/• en vez de widgets)."""
    line = classify(raw)
    pad = "   " * line.indent
    if line.kind == "task":
        return f"{pad}{'☑' if line.checked else '☐'} {inline(line.text, highlight)}"
    if line.kind == "bullet":
        return f"{pad}• {inline(line.text, highlight)}"
    if line.kind == "numbered":
        return f"{pad}{line.marker} {inline(line.text, highlight)}"
    return inline(raw, highlight)
