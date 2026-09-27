import os
import tempfile
import unittest

from notitas import store as st


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "notitas.md")
        self.store = st.Store(self.path)
        self.note = self.store.notes[0]

    def reload(self):
        self.store.save_now()
        return st.Store(self.path)

    def test_seed_is_written_only_on_first_change(self):
        self.assertFalse(os.path.exists(self.path))
        self.store.append(self.note.id, "algo")
        self.store.save_now()
        self.assertTrue(os.path.exists(self.path))

    def test_append_as_tasks(self):
        self.store.append(self.note.id, "uno\n- [ ] dos\n\ntres", as_tasks=True)
        self.assertEqual([t for t, _ in self.note.lines[-4:]], ["- [ ] uno", "- [ ] dos", "", "- [ ] tres"])
        self.store.append(self.note.id, "suelto", as_tasks=False)
        self.assertEqual(self.note.lines[-1][0], "suelto")

    def test_archive_newest_first_and_unarchive(self):
        self.note.lines = [["- [ ] a", "2026-01-01 10:00"], ["- [ ] b", "2026-01-01 11:00"]]
        self.assertTrue(self.store.archive_line(self.note.id, 0, "- [ ] a"))
        self.assertTrue(self.store.archive_line(self.note.id, 0, "- [ ] b"))
        self.assertEqual([t for t, _ts, _d in self.note.archived], ["- [x] b", "- [x] a"])
        self.assertEqual(self.note.archived[1][1], "2026-01-01 10:00")  # conserva cuándo se escribió
        self.assertFalse(self.store.archive_line(self.note.id, 0, "- [ ] ya no está"))
        self.assertTrue(self.store.unarchive(self.note.id, 1, "- [x] a"))
        self.assertEqual(self.note.lines[-1], ["- [ ] a", "2026-01-01 10:00"])
        again = self.reload().note(self.note.id)
        self.assertEqual([t for t, _ts, _d in again.archived], ["- [x] b"])

    def test_editing_keeps_times_of_unchanged_lines(self):
        self.note.lines = [["uno", "2026-01-01 10:00"], ["dos", "2026-01-01 11:00"]]
        self.store.update_note(self.note.id, content="uno\ndos cambiado\ntres")
        self.assertEqual(self.note.lines[0], ["uno", "2026-01-01 10:00"])
        self.assertNotEqual(self.note.lines[1][1], "2026-01-01 11:00")
        self.assertEqual(self.note.lines[2][0], "tres")

    def test_numbers_are_unique(self):
        other = self.store.add_note(self.store.categories[0].id)
        self.store.update_note(other.id, number=self.note.number)
        self.assertEqual(other.number, 1)
        self.assertIsNone(self.note.number)

    def test_new_notes_go_last(self):
        cat = self.store.categories[0].id
        a = self.store.add_note(cat, "A")
        b = self.store.add_note(cat, "B")
        self.assertEqual([n.id for n in self.store.notes_in(cat)], [self.note.id, a.id, b.id])

    def test_move_category(self):
        a = self.store.categories[0]
        b = self.store.add_category("B")
        c = self.store.add_category("C")
        self.store.move_category(c.id, a.id)
        self.assertEqual([x.name for x in self.store.categories], ["C", a.name, "B"])
        self.store.move_category(c.id, b.id, after=True)
        self.assertEqual([x.name for x in self.store.categories], [a.name, "B", "C"])
        self.assertEqual([x.name for x in self.reload().categories], [a.name, "B", "C"])

    def test_move_note(self):
        cat = self.store.add_category("Otra")
        a = self.store.add_note(self.store.categories[0].id, "A")
        b = self.store.add_note(cat.id, "B")
        self.store.move_note(a.id, category_id=cat.id)
        self.assertEqual([n.title for n in self.store.notes_in(cat.id)], ["B", "A"])  # llega al final
        self.store.move_note(a.id, target_id=self.note.id, after=True)
        self.assertEqual([n.id for n in self.store.notes_in(self.note.category_id)], [self.note.id, a.id])

    def test_relocate_adopts_existing_file(self):
        other_dir = tempfile.mkdtemp()
        other = st.Store(os.path.join(other_dir, "notitas.md"))
        other.notes[0].title = "De otra máquina"
        other.save_now()
        self.store.relocate(other_dir, adopt_existing=True)
        self.assertEqual(self.store.notes[0].title, "De otra máquina")

    def test_search(self):
        self.note.archived = [["- [x] yerba mate", None, None]]
        self.assertEqual(self.store.search("YERBA"), [self.note])
        self.assertEqual(self.store.search("inexistente"), [])


if __name__ == "__main__":
    unittest.main()
