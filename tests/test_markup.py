import unittest

from notitas import markup


class MarkupTest(unittest.TestCase):
    def test_inline(self):
        self.assertEqual(markup.inline("**a** y *b* y ~~c~~"), "<b>a</b> y <i>b</i> y <s>c</s>")
        self.assertEqual(markup.inline("`x<y`"), "<tt>x&lt;y</tt>")

    def test_links(self):
        self.assertEqual(markup.inline("[doc](https://a.b/c?d=1&e=2)"),
                         '<a href="https://a.b/c?d=1&amp;e=2">doc</a>')
        self.assertEqual(markup.inline("ver https://ubuntu.com/docs."),
                         'ver <a href="https://ubuntu.com/docs">https://ubuntu.com/docs</a>.')

    def test_unbalanced_falls_back_to_text(self):
        self.assertEqual(markup.inline("**sin cerrar"), "**sin cerrar")
        self.assertEqual(markup.inline("2 ** 3 < 9"), "2 ** 3 &lt; 9")

    def test_highlight(self):
        self.assertIn("yer</span>ba", markup.inline("Yerba", highlight="yer").replace("Yer", "yer"))

    def test_classify(self):
        self.assertEqual(markup.classify("- [ ] a").kind, "task")
        self.assertTrue(markup.classify("[x] a").checked)
        self.assertEqual(markup.classify("  - b").indent, 1)
        self.assertEqual(markup.classify("2. c").marker, "2.")
        self.assertEqual(markup.classify("   ").kind, "blank")

    def test_as_task(self):
        self.assertEqual(markup.as_task("hola"), "- [ ] hola")
        self.assertEqual(markup.as_task("  - [ ] sub", checked=True), "  - [x] sub")


if __name__ == "__main__":
    unittest.main()
