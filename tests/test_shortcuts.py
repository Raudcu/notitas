import unittest

from notitas import shortcuts


class ShortcutsGuardTest(unittest.TestCase):
    def test_refuses_without_session_config(self):
        # Los tests corren con un XDG_CONFIG_HOME aislado (ver tests/__init__.py):
        # justo el caso en que escribir los atajos borraría los de otros programas.
        self.assertFalse(shortcuts.reads_session_config())
        with self.assertRaises(RuntimeError):
            shortcuts.install("/usr/bin/notitas")
        if shortcuts._available():  # sin GNOME (p. ej. en CI) no hay nada que quitar
            with self.assertRaises(RuntimeError):
                shortcuts.uninstall()


if __name__ == "__main__":
    unittest.main()
