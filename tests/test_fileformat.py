import unittest

from notitas import fileformat

SAMPLE = """<!-- Archivo de Notitas. Se puede leer y editar a mano: no toques los comentarios con los datos de cada nota. -->

# Casa

## Pendientes
<!-- nota aaa111 · número 1 · color amarillo · tareas -->
- [ ] llamar al **plomero** <!-- 2026-09-25 09:15 -->
\\# esto no es un título <!-- 2026-09-25 09:16 -->

texto después de una línea en blanco <!-- 2026-09-25 09:17 -->
<!-- archivadas -->
- [x] comprar yerba <!-- 2026-09-24 10:00 · hecha 2026-09-26 19:13 -->

# Trabajo
"""


class FileFormatTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(fileformat.dump(fileformat.parse(SAMPLE)), SAMPLE)

    def test_parse(self):
        casa, trabajo = fileformat.parse(SAMPLE)
        self.assertEqual(casa["name"], "Casa")
        self.assertEqual(trabajo["notes"], [])
        note = casa["notes"][0]
        self.assertEqual((note["id"], note["number"], note["color"], note["tasks"]),
                         ("aaa111", 1, "amarillo", True))
        self.assertEqual(note["lines"][1], ["# esto no es un título", "2026-09-25 09:16"])
        self.assertEqual(note["lines"][2], ["", None])
        self.assertEqual(note["archived"], [["- [x] comprar yerba", "2026-09-24 10:00", "2026-09-26 19:13"]])

    def test_old_keyword(self):
        text = "# A\n\n## N\n<!-- nota x1 · color rosa · pendientes -->\n- [ ] a\n"
        self.assertTrue(fileformat.parse(text)[0]["notes"][0]["tasks"])

    def test_hand_written_note(self):
        # Una nota agregada a mano, sin comentario de datos, no se pierde.
        text = "# A\n\n## Nota a mano\nuna línea\n"
        note = fileformat.parse(text)[0]["notes"][0]
        self.assertIsNone(note["id"])
        self.assertEqual(note["lines"], [["una línea", None]])

    def test_escaping(self):
        cats = [{"name": "A", "notes": [{"id": "x", "title": "t", "lines": [
            ["# título falso", None], ["\\barra", None], ["<!-- comentario -->", None]]}]}]
        parsed = fileformat.parse(fileformat.dump(cats))
        self.assertEqual([t for t, _ in parsed[0]["notes"][0]["lines"]],
                         ["# título falso", "\\barra", "<!-- comentario -->"])


if __name__ == "__main__":
    unittest.main()
