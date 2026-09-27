"""Modelo de categorías y notas, guardado en un único archivo Markdown.

- Cada línea de una nota guarda la hora en que se escribió (o se modificó por
  última vez), como un "blame".
- Guardado atómico, con copias de seguridad locales por hora.
- Si el archivo cambia desde afuera (Dropbox, otra máquina, edición a mano) se
  recarga solo.
"""

import difflib
import glob
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field

from gi.repository import Gio, GLib, GObject

from . import config, fileformat, markup

# Colores tipo post-it: nombre -> (fondo, borde/acento)
PALETTE = {
    "amarillo": ("#fff59d", "#f9a825"),
    "naranja": ("#ffcc80", "#ef6c00"),
    "rosa": ("#f8bbd0", "#d81b60"),
    "lila": ("#d1c4e9", "#5e35b1"),
    "celeste": ("#b3e5fc", "#0277bd"),
    "verde": ("#c5e1a5", "#558b2f"),
    "gris": ("#e0e0e0", "#616161"),
}
DEFAULT_COLOR = "amarillo"
MAX_NUMBER = 9
BACKUPS_KEPT = 72


def _new_id():
    return uuid.uuid4().hex[:12]


def now_ts():
    return time.strftime("%Y-%m-%d %H:%M")


@dataclass
class Category:
    id: str
    name: str


@dataclass
class Note:
    id: str
    category_id: str
    title: str = ""
    color: str = DEFAULT_COLOR
    number: int | None = None
    # Si es True, lo que llega por los atajos entra como tarea: "- [ ] …".
    tasks: bool = False
    # [texto, "AAAA-MM-DD HH:MM" | None] por cada línea
    lines: list = field(default_factory=list)
    # [texto, hora de escritura, hora en que se tildó]; lo último archivado primero
    archived: list = field(default_factory=list)

    @property
    def content(self):
        return "\n".join(text for text, _ts in self.lines)

    @property
    def updated(self):
        return max((ts for _t, ts in self.lines if ts), default="")

    def matches(self, query):
        q = query.casefold()
        texts = [self.title, self.content] + [t for t, _ts, _d in self.archived]
        return any(q in t.casefold() for t in texts)

    def line_ts(self, index):
        if 0 <= index < len(self.lines):
            return self.lines[index][1]
        return None


def _relabel(old_lines, new_text):
    """Asigna horas a las líneas de new_text conservando las de las que no cambiaron."""
    old_texts = [t for t, _ in old_lines]
    new_texts = new_text.split("\n") if new_text else []
    now = now_ts()
    result = []
    matcher = difflib.SequenceMatcher(a=old_texts, b=new_texts, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result.extend([new_texts[j1 + k], old_lines[i1 + k][1]] for k in range(i2 - i1))
        else:
            result.extend([t, now if t.strip() else None] for t in new_texts[j1:j2])
    return result


class Store(GObject.Object):
    __gsignals__ = {
        # Cambió la estructura: categorías, notas agregadas/borradas, números.
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
        # Cambió el contenido/metadatos de una nota puntual.
        "note-changed": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        # Error de lectura/escritura para mostrarle al usuario.
        "error": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, path=None):
        super().__init__()
        self.path = path or config.notes_file()
        self.categories: list[Category] = []
        self.notes: list[Note] = []
        self._save_source = 0
        self._reload_source = 0
        self._last_text = None
        self._monitor = None
        self.load()

    # ---------- disco ----------

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            # La nota de ejemplo se escribe recién con el primer cambio (o al elegir carpeta).
            self._seed()
        else:
            self._apply_text(text)
        self._watch()

    def _apply_text(self, text):
        # Conservar los ids de categoría por nombre para no romper la selección.
        old_ids = {c.name: c.id for c in self.categories}
        self.categories, self.notes = [], []
        used_numbers = set()
        for c in fileformat.parse(text):
            cat = Category(old_ids.get(c["name"]) or _new_id(), c["name"])
            self.categories.append(cat)
            for n in c["notes"]:
                number = n["number"]
                if number in used_numbers or not (number and 1 <= number <= MAX_NUMBER):
                    number = None
                used_numbers.add(number)
                self.notes.append(
                    Note(
                        id=n["id"] or _new_id(),
                        category_id=cat.id,
                        title=n["title"],
                        color=n["color"] if n["color"] in PALETTE else DEFAULT_COLOR,
                        number=number,
                        tasks=n["tasks"],
                        lines=n["lines"],
                        archived=n["archived"],
                    )
                )
        if not self.categories:
            self.categories.append(Category(_new_id(), "General"))
        self._last_text = text

    def _seed(self):
        cat = Category(_new_id(), "General")
        self.categories = [cat]
        self.notes = [
            Note(
                _new_id(),
                cat.id,
                title="Ideas",
                number=1,
                tasks=True,
                lines=[["- [ ] Apretá Ctrl+Alt+1 desde cualquier lado para agregar una tarea acá", now_ts()]],
            )
        ]

    def _serialize(self):
        cats = []
        for cat in self.categories:
            cats.append(
                {
                    "name": cat.name,
                    "notes": [
                        {"id": n.id, "title": n.title, "number": n.number, "color": n.color,
                         "tasks": n.tasks, "lines": n.lines, "archived": n.archived}
                        for n in self.notes_in(cat.id)
                    ],
                }
            )
        return fileformat.dump(cats)

    def save_now(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0
        text = self._serialize()
        if text == self._last_text:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self._backup()
            tmp = os.path.join(os.path.dirname(self.path), f".{os.path.basename(self.path)}.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            self._last_text = text
        except OSError as e:
            self.emit("error", f"No pude guardar las notas en {self.path}: {e.strerror}")

    def _backup(self):
        """Una copia por hora del archivo anterior (por defecto, fuera de la carpeta sincronizada)."""
        if not os.path.exists(self.path):
            return
        folder = config.backups_dir()
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, time.strftime("notitas-%Y-%m-%d_%H.md"))
        if not os.path.exists(target):
            shutil.copy2(self.path, target)
            for old in sorted(glob.glob(os.path.join(folder, "notitas-*.md")))[:-BACKUPS_KEPT]:
                os.remove(old)

    def _schedule_save(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(400, self._on_save_timeout)

    def _on_save_timeout(self):
        self._save_source = 0
        self.save_now()
        return GLib.SOURCE_REMOVE

    # ---------- cambios externos ----------

    def _watch(self):
        if self._monitor:
            self._monitor.cancel()
        self._monitor = Gio.File.new_for_path(self.path).monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
        self._monitor.connect("changed", self._on_file_event)

    def _on_file_event(self, *_):
        if self._reload_source:
            GLib.source_remove(self._reload_source)
        self._reload_source = GLib.timeout_add(300, self._reload_if_external)

    def _reload_if_external(self):
        self._reload_source = 0
        try:
            with open(self.path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return GLib.SOURCE_REMOVE
        if text == self._last_text:
            return GLib.SOURCE_REMOVE
        if self._save_source:
            # Hay cambios nuestros sin guardar: ganan los nuestros (queda la copia de seguridad).
            self.save_now()
            return GLib.SOURCE_REMOVE
        self._apply_text(text)
        self.emit("changed")
        for note in list(self.notes):
            self.emit("note-changed", note.id)
        return GLib.SOURCE_REMOVE

    # ---------- ubicación ----------

    def relocate(self, folder, adopt_existing):
        """Mueve el archivo de notas a otra carpeta.

        Si ahí ya hay un archivo y adopt_existing es True, pasa a usar ese.
        Si no hay, escribe las notas actuales ahí. El archivo viejo no se borra.
        """
        if os.path.exists(self.path):
            self.save_now()  # no crear un archivo en la ubicación vieja si nunca existió
        new_path = os.path.join(folder, config.NOTES_FILENAME)
        exists = os.path.exists(new_path)
        if exists and not adopt_existing:
            raise FileExistsError(new_path)
        self.path = new_path
        if exists:
            with open(new_path, encoding="utf-8") as f:
                self._apply_text(f.read())
        else:
            self._last_text = None
            self.save_now()
        config.set_notes_dir(folder)
        self._watch()
        self.emit("changed")

    # ---------- consultas ----------

    def category(self, cat_id):
        return next((c for c in self.categories if c.id == cat_id), None)

    def note(self, note_id):
        return next((n for n in self.notes if n.id == note_id), None)

    def notes_in(self, cat_id):
        # El orden es el del archivo, que se cambia arrastrando las tarjetas.
        return [n for n in self.notes if n.category_id == cat_id]

    def search(self, query):
        return [n for n in self.notes if n.matches(query)]

    def note_by_number(self, number):
        return next((n for n in self.notes if n.number == number), None)

    # ---------- categorías ----------

    def add_category(self, name):
        cat = Category(_new_id(), name.strip() or "Sin nombre")
        self.categories.append(cat)
        self._schedule_save()
        self.emit("changed")
        return cat

    def rename_category(self, cat_id, name):
        cat = self.category(cat_id)
        if cat and name.strip():
            cat.name = name.strip()
            self._schedule_save()
            self.emit("changed")

    def move_category(self, cat_id, target_id, after=False):
        """Reordena: pone la categoría antes (o después) de otra."""
        cat, target = self.category(cat_id), self.category(target_id)
        if not cat or not target or cat is target:
            return
        self.categories.remove(cat)
        self.categories.insert(self.categories.index(target) + (1 if after else 0), cat)
        self._schedule_save()
        self.emit("changed")

    def delete_category(self, cat_id):
        self.categories = [c for c in self.categories if c.id != cat_id]
        self.notes = [n for n in self.notes if n.category_id != cat_id]
        if not self.categories:
            self.categories.append(Category(_new_id(), "General"))
        self._schedule_save()
        self.emit("changed")

    # ---------- notas ----------

    def add_note(self, cat_id, title="Nota nueva"):
        used = {n.number for n in self.notes}
        free = next((i for i in range(1, MAX_NUMBER + 1) if i not in used), None)
        colors = list(PALETTE)
        color = colors[len(self.notes_in(cat_id)) % len(colors)]
        note = Note(_new_id(), cat_id, title=title, color=color, number=free, tasks=True)
        self.notes.append(note)  # orden de creación: la más nueva al final
        self._schedule_save()
        self.emit("changed")
        return note

    def update_note(self, note_id, **fields):
        note = self.note(note_id)
        if not note:
            return
        structural = False
        if "content" in fields:
            new_lines = _relabel(note.lines, fields.pop("content"))
            if new_lines == note.lines:
                if not fields:
                    return
            note.lines = new_lines
        if "number" in fields and fields["number"] != note.number:
            structural = True
            # Los números son únicos: se los saco a quien lo tuviera.
            if fields["number"] is not None:
                other = self.note_by_number(fields["number"])
                if other:
                    other.number = None
        if "category_id" in fields and fields["category_id"] != note.category_id:
            structural = True
        for k, v in fields.items():
            setattr(note, k, v)
        self._schedule_save()
        self.emit("note-changed", note_id)
        if structural:
            self.emit("changed")

    def move_note(self, note_id, target_id=None, after=False, category_id=None):
        """Mueve una nota antes/después de otra, o al final de una categoría."""
        note = self.note(note_id)
        if not note or note_id == target_id:
            return
        self.notes.remove(note)
        target = self.note(target_id) if target_id else None
        if target:
            note.category_id = target.category_id
            index = self.notes.index(target) + (1 if after else 0)
        else:
            note.category_id = category_id or note.category_id
            index = len(self.notes)
        self.notes.insert(index, note)
        self._schedule_save()
        self.emit("changed")

    def delete_note(self, note_id):
        self.notes = [n for n in self.notes if n.id != note_id]
        self._schedule_save()
        self.emit("changed")

    def append(self, note_id, text, as_tasks=None):
        """Agrega texto al final de la nota; cada línea nueva lleva la hora actual.

        En notas de tareas, cada línea entra como "- [ ] …" salvo as_tasks=False.
        """
        note = self.note(note_id)
        text = text.strip("\n")
        if not note or not text.strip():
            return
        if as_tasks is None:
            as_tasks = note.tasks
        now = now_ts()
        for t in text.split("\n"):
            if as_tasks and t.strip() and markup.classify(t).kind != "task":
                t = markup.as_task(t)
            note.lines.append([t, now if t.strip() else None])
        self._schedule_save()
        self.emit("note-changed", note_id)

    # ---------- tareas ----------

    def archive_line(self, note_id, index, expected_text):
        """Tilda una tarea y la pasa a "archivadas" (queda primero)."""
        note = self.note(note_id)
        if not note or index >= len(note.lines) or note.lines[index][0] != expected_text:
            return False
        text, ts = note.lines.pop(index)
        note.archived.insert(0, [markup.as_task(text, checked=True), ts, now_ts()])
        self._schedule_save()
        self.emit("note-changed", note_id)
        return True

    def unarchive(self, note_id, index, expected_text):
        """Destilda un archivado: vuelve al final de las tareas."""
        note = self.note(note_id)
        if not note or index >= len(note.archived) or note.archived[index][0] != expected_text:
            return False
        text, ts, _done = note.archived.pop(index)
        note.lines.append([markup.as_task(text, checked=False), ts])
        self._schedule_save()
        self.emit("note-changed", note_id)
        return True

    def set_line(self, note_id, index, text):
        note = self.note(note_id)
        if note and index < len(note.lines) and note.lines[index][0] != text:
            note.lines[index] = [text, now_ts()]
            self._schedule_save()
            self.emit("note-changed", note_id)

    def clear_archived(self, note_id):
        note = self.note(note_id)
        if note and note.archived:
            note.archived = []
            self._schedule_save()
            self.emit("note-changed", note_id)
