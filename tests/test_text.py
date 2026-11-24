"""Run with: python -m unittest discover -s tests"""
import io, os, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.clean import Normaliser, ordinal, roman_value, titlecase
from app.readers import BookError, read_book, read_html, read_text
from app.structure import build, looks_english
from app.author import by_title, plain_name
from app.job import TAG, safe_name
from app.speech import sentences

N = Normaliser(["He knew the marley and ebenezer Scrooge of London.", "Marley was dead.", "It was the best of times."])


class Clean(unittest.TestCase):
    def check(self, *pairs):
        for a, b in pairs:
            with self.subTest(a): self.assertEqual(N(a), b)

    def test_pronoun_i_is_never_a_number(self):
        self.check(("In this case I found it.", "In this case I found it."), ("The letter I wrote, the day I grew.", "The letter I wrote, the day I grew."), ("Henry I know well.", "Henry I know well."), ("a question I put", "a question I put"))

    def test_numerals(self):
        self.check(("See Chapter IV.", "See Chapter 4."), ("Louis XIV of France", "Louis the Fourteenth of France"), ("in Book II, Chapter I,", "in Book 2, Chapter 1,"), ("class C and letter D", "class C and letter D"), ("a MIX of XII men", "a MIX of 12 men"))

    def test_abbreviations(self):
        self.check(("Mr. and Mrs. Bennet met Dr. Watson.", "Mister and Missus Bennet met Doctor Watson."), ("St. James's, near Baker St. and beyond", "Saint James's, near Baker Street and beyond"),
                   ("cakes, etc. Then he left.", "cakes, etcetera. Then he left."), ("i.e. the end", "that is, the end"), ("No. 5", "number 5"), ("J. Smith, Esq.", "J. Smith, Esquire."), ("Capt. Ahab", "Captain Ahab"), ("at 6 p.m. sharp", "at 6 PM sharp"))

    def test_dashes(self):
        self.check(("in the year 18—, London", "in the year eighteen hundred and something, London"), ("the ——shire Militia", "the blankshire Militia"), ("Mr. B—— came", "Mister B came"), ("d—d fool", "damned fool"), ("yes--no", "yes—no"), ("1801—I have", "1801—I have"), ("pages 4-6", "pages 4 to 6"))

    def test_quotes(self):
        self.check(('"Go," he said, "now."', "“Go,” he said, “now.”"), ("“He said, ‘Go away,’ and left.”", "“He said, Go away, and left.”"), ("don’t, o’clock, the boys’ books", "don't, o'clock, the boys' books"), ("’Tis true", "'Tis true"), ("th’ owd man", "th' owd man"), ("“nothing.’ ‘And you?’”", "“nothing. And you?”"), ("give ’em some", "give 'em some"))

    def test_single_quote_dialogue(self):
        M = Normaliser([f"‘Hello, it’s number {i},’ he said. ‘Go.’" for i in range(20)])
        self.assertEqual(M("‘Don’t go,’ said Tom. ‘It’s late.’"), "“Don't go,” said Tom. “It's late.”")

    def test_capitals(self):
        self.check(("IT was the best", "It was the best"), ("MARLEY was dead", "Marley was dead"), ("STAVE ONE BEGINS HERE", "Stave One Begins Here"), ("the U.S.A. and the FBI", "the U.S.A. and the FBI"), ("I am A man", "I am A man"))

    def test_marks(self):
        self.check(("_very_ good", "very good"), ("10_th December_", "10th December"), ("wait . . . .", "wait…"), ("£4 10s. 6d. each", "4 pounds, 10 shillings and 6 pence each"), ("2½ miles", "2 and a half miles"), ("word[12] next", "word next"), ("to-day and to-morrow", "today and tomorrow"))

    def test_helpers(self):
        self.assertEqual([roman_value(x) for x in ("IV", "XIX", "MCMX", "IIX", "")], [4, 19, 1910, 0, 0])
        self.assertEqual([ordinal(x) for x in (1, 12, 20, 21, 33)], ["first", "twelfth", "twentieth", "twenty-first", "thirty-third"])
        self.assertEqual(titlecase("THE ADVENTURE OF THE BLUE CARBUNCLE"), "The Adventure of the Blue Carbuncle")
        self.assertEqual(N.heading("CHAPTER XIV. THE MAIL"), "Chapter 14. The Mail")
        self.assertEqual(N.heading("CHAPTER I. The Period"), "Chapter 1. The Period")
        self.assertEqual(N.heading("II. THE RED-HEADED LEAGUE"), "2. The Red-Headed League")
        self.assertEqual(N.heading("SEARCH FOR MR. HYDE"), "Search for Mr. Hyde")

    def test_sentences(self):
        self.assertEqual(sentences("One. Two! “Three?” he said. Four"), ["One.", "Two!", "“Three?” he said.", "Four"])


PARA = "It was a bright cold day in spring, and the people of the town were out in the streets to see what had come with the tide. " * 4


class Books(unittest.TestCase):
    def test_mini_html(self):
        b = build(read_book(os.path.join(os.path.dirname(__file__), "mini.html"))); text = " ".join(t for c in b.chapters for _, t in c.blocks)
        self.assertEqual([c.title for c in b.chapters], ["Chapter 1", "Chapter 2"]); self.assertEqual((b.title, b.author), ("Pride and Prejudice (Opening)", "Jane Austen"))
        for bad in ("caption", "footnote", "Licence", "Gutenberg", "[Pg", "CONTENTS"): self.assertNotIn(bad, text)
        for good in ("It is a truth universally", "daughters.", "Mister Bennet was among", "blankshire", "eighteen hundred and something"): self.assertIn(good, text)
        self.assertTrue(looks_english(b))

    def test_text_with_contents(self):
        s = "Title: A Book\n\nAuthor: Ann Other\n\nLanguage: English\n\n*** START OF THE PROJECT GUTENBERG EBOOK A BOOK ***\n\n\nA BOOK\n\nby Ann Other\n\n\nCONTENTS\n\n\n     BOOK ONE\n\n     CHAPTER I    Beginnings\n     CHAPTER II   Endings\n\n\n\n\nBOOK ONE\n\n\n\nCHAPTER I\nBeginnings\n\n\n" + PARA + "\n\nMore of it.[1]\n\n\n\nCHAPTER II\nEndings\n\n\n" + PARA + "\n\nTHE END\n\nPRINTED BY SOMEONE, LONDON\n\n*** END OF THE PROJECT GUTENBERG EBOOK A BOOK ***\n\nlicence"
        b = build(read_text(s.encode()))
        self.assertEqual([(c.part, c.title) for c in b.chapters], [("Book One", "Chapter 1. Beginnings"), ("", "Chapter 2. Endings")])
        text = " ".join(t for c in b.chapters for _, t in c.blocks)
        for bad in ("licence", "PRINTED", "[1]", "THE END"): self.assertNotIn(bad, text)

    def epub(self, files, opf_extra="", spine=("a", "b")):
        f = tempfile.NamedTemporaryFile(suffix=".epub", delete=False); z = zipfile.ZipFile(f, "w")
        z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="O/c.opf"/></rootfiles></container>')
        items = "".join(f'<item id="{k}" href="{k}.xhtml" media-type="application/xhtml+xml"/>' for k in files)
        z.writestr("O/c.opf", f'<package xmlns:dc="d" xmlns:opf="o"><metadata><dc:title>T</dc:title><dc:creator opf:role="aut">Jane Roe</dc:creator><dc:language>en</dc:language>{opf_extra}</metadata><manifest>{items}</manifest><spine>' + "".join(f'<itemref idref="{k}"/>' for k in spine) + "</spine></package>")
        for k, v in files.items(): z.writestr(f"O/{k}.xhtml", f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{v}</body></html>')
        z.close(); f.close(); self.addCleanup(os.remove, f.name); return f.name

    def test_epub_chapters(self):
        p = self.epub({"a": f"<h2>CHAPTER I</h2><p><span class='dropcap'>I</span>T began.</p><p>{PARA}</p>", "b": f"<h2>CHAPTER II</h2><p>{PARA}</p><p>a<a id='x'/>b &mdash; c&nbsp;d</p>"})
        b = build(read_book(p)); self.assertEqual([c.title for c in b.chapters], ["Chapter 1", "Chapter 2"])
        self.assertEqual(b.chapters[0].blocks[0][1], "It began."); self.assertEqual(b.chapters[1].blocks[-1][1], "ab — c d")

    def test_not_english(self):
        s = "Il était une fois une princesse qui vivait dans un château avec son père et ses frères, et tous les jours elle allait dans la forêt pour chercher des fleurs. " * 20
        self.assertFalse(looks_english(build(read_text(s.encode()))))

    def test_rejections(self):
        for name, data in (("x.epub", b"not a zip"), ("x.pdf", b"%PDF"), ("x.mobi", b"BOOK"), ("x.txt", b"  \n\n ")):
            p = os.path.join(tempfile.mkdtemp(), name)
            with open(p, "wb") as f: f.write(data)
            with self.subTest(name), self.assertRaises(BookError): read_book(p)

    def test_drm(self):
        p = self.epub({"a": "<p>x</p>"}, spine=("a",))
        with zipfile.ZipFile(p, "a") as z: z.writestr("META-INF/encryption.xml", '<encryption><CipherReference URI="O/a.xhtml"/></encryption>')
        with self.assertRaises(BookError): read_book(p)

    def test_external_entities_are_not_read(self):
        secret = os.path.join(tempfile.mkdtemp(), "s.txt")
        with open(secret, "w") as f: f.write("SECRET" * 10)
        doc = f'<!DOCTYPE html [<!ENTITY e SYSTEM "file:///{secret.replace(os.sep, "/")}">]><html xmlns="http://www.w3.org/1999/xhtml"><body><p>&e; text</p></body></html>'
        self.assertNotIn("SECRET", str(read_html(doc.encode()).blocks))


class Names(unittest.TestCase):
    def test_author_names(self):
        self.assertEqual(plain_name("Austen, Jane, 1775-1817"), ("Jane Austen", (1775, 1817)))
        self.assertEqual(plain_name("Leo Tolstoy, graf")[0], "Leo Tolstoy"); self.assertEqual(plain_name("L. Frank (Lyman Frank) Baum")[0], "L. Frank Baum")
        self.assertEqual([by_title(x) for x in ("Mrs. Gaskell", "Sir Walter Scott", "Jane Austen")], ["female", "male", ""])

    def test_file_names(self):
        self.assertEqual(safe_name('A: B/C? "D"'), "A - B C D"); self.assertEqual(safe_name("../../x"), "x"); self.assertEqual(safe_name("..."), "Untitled")
        self.assertEqual([m.group(1) for m in (TAG.search(x) for x in ("Emma [female]", "Emma [bm_fable]", "Emma [1815]")) if m], ["female", "bm_fable"])


if __name__ == "__main__": unittest.main()
