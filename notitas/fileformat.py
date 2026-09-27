"""Formato del archivo de notas: un único Markdown legible a mano.

    <!-- Notitas · ... -->

    # General                                   ← categoría

    ## Ideas                                    ← nota (título)
    <!-- nota 3f2a9c1b0d4e · número 1 · color amarillo · tareas -->
    - [ ] llamar a Juan <!-- 2026-09-26 15:10 -->   ← cada línea con su hora
    <!-- archivadas -->                         ← lo tildado, lo último primero
    - [x] comprar yerba <!-- 2026-09-26 14:32 · hecha 2026-09-27 10:02 -->

Los comentarios HTML no se ven si el archivo se abre con un visor de Markdown
(por ejemplo, la vista previa de Dropbox). Las líneas de texto que empiezan con
`#`, `\\` o `<!--` se guardan con una `\\` adelante para no confundirlas.
"""

import re

HEADER = (
    "<!-- Archivo de Notitas. Se puede leer y editar a mano: "
    "no toques los comentarios con los datos de cada nota. -->"
)

TS = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}"
TS_RE = re.compile(rf" ?<!-- ({TS})(?: · hecha ({TS}))? -->$")
ARCHIVE_MARK = "<!-- archivadas -->"
META_RE = re.compile(r"^<!-- nota ([0-9a-zA-Z]+)(.*?) -->$")
COMMENT_RE = re.compile(r"^<!--.*-->$")


def _escape(text):
    if text.startswith(("#", "\\", "<!--")):
        return "\\" + text
    return text


def _unescape(text):
    return text[1:] if text.startswith("\\") else text


def _strip_blank_edges(lines):
    while lines and not lines[0][0].strip():
        lines.pop(0)
    while lines and not lines[-1][0].strip():
        lines.pop()
    return lines


def parse(text):
    """Devuelve una lista de categorías: [{"name", "notes": [{...}]}]. Nunca falla."""
    categories = []
    cat = None
    note = None

    def ensure_category():
        nonlocal cat
        if cat is None:
            cat = {"name": "General", "notes": []}
            categories.append(cat)
        return cat

    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("# "):
            cat = {"name": line[2:].strip() or "Sin nombre", "notes": []}
            categories.append(cat)
            note = None
            continue
        if line.startswith("## ") or line == "##":
            note = {"id": None, "title": line[3:].strip(), "number": None, "color": None,
                    "tasks": False, "lines": [], "archived": []}
            target = note["lines"]
            ensure_category()["notes"].append(note)
            continue
        meta = META_RE.match(line)
        if meta and note is not None and note["id"] is None and not note["lines"]:
            note["id"] = meta.group(1)
            for part in meta.group(2).split("·"):
                key, _, value = part.strip().partition(" ")
                if key == "número" and value.strip().isdigit():
                    note["number"] = int(value)
                elif key == "color":
                    note["color"] = value.strip()
                elif key in ("tareas", "pendientes"):  # "pendientes": nombre anterior
                    note["tasks"] = True
            continue
        if line == ARCHIVE_MARK and note is not None:
            target = note["archived"]
            continue
        if note is None:
            # Texto suelto fuera de una nota (encabezado del archivo, etc.): se ignora.
            continue
        if COMMENT_RE.match(line) and not TS_RE.search(line):
            continue
        ts = done = None
        m = TS_RE.search(line)
        if m:
            ts, done = m.group(1), m.group(2)
            line = line[: m.start()]
        if target is note["archived"]:
            if line.strip():
                target.append([_unescape(line), ts, done])
        else:
            target.append([_unescape(line), ts])

    for c in categories:
        for n in c["notes"]:
            _strip_blank_edges(n["lines"])
    return categories


def dump(categories):
    """Inverso de parse(). `categories` tiene la misma forma que devuelve parse()."""
    out = [HEADER, ""]
    for cat in categories:
        out.append(f"# {cat['name']}")
        out.append("")
        for note in cat["notes"]:
            out.append(f"## {note['title']}".rstrip())
            meta = [f"nota {note['id']}"]
            if note.get("number") is not None:
                meta.append(f"número {note['number']}")
            if note.get("color"):
                meta.append(f"color {note['color']}")
            if note.get("tasks"):
                meta.append("tareas")
            out.append(f"<!-- {' · '.join(meta)} -->")
            for text, ts in note["lines"]:
                line = _escape(text)
                if ts and text.strip():
                    line += f" <!-- {ts} -->"
                out.append(line)
            if note.get("archived"):
                out.append(ARCHIVE_MARK)
                for text, ts, done in note["archived"]:
                    stamp = " · ".join(filter(None, [ts, f"hecha {done}" if done else None]))
                    out.append(_escape(text) + (f" <!-- {stamp} -->" if ts else ""))
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"
