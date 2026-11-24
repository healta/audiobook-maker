"""Pronunciations on top of misaki's dictionary: fixes for its known slips, names from the classics, Slavic names, the user's own list.

Phonemes are misaki/Kokoro American symbols (A=ay, I=eye, O=oh, W=ow, Y=oy); they are converted for British voices.
"""
import json, os, re
from collections import Counter

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# words misaki gets wrong or lacks
FIXES = {
    "tis": "tˈɪz", "twas": "twˈʌz", "twere": "twˈɜɹ", "twould": "twˈʊd", "shan't": "ʃˈænt", "mustn't": "mˈʌsᵊnt", "etcetera": "ɛtsˈɛtəɹə", "ay": "ˈI", "Ay": "ˈI", "aye": "ˈI", "Aye": "ˈI",
    "messers": "mˈɛsəɹz", "Messers": "mˈɛsəɹz", "blankshire": "blˈæŋkʃəɹ", "withdrew": "wɪðdɹˈu", "halloa": "həlˈO", "Halloa": "həlˈO", "gipsy": "ʤˈɪpsi", "gipsies": "ʤˈɪpsiz",
    "rouble": "ɹˈubᵊl", "roubles": "ɹˈubᵊlz", "tête": "tˈɛt", "naïve": "nɑˈiv", "naïveté": "nɑˌivətˈA", "protégé": "pɹˈOtəʒA", "façade": "fəsˈɑd", "fiancé": "fˌiɑnsˈA", "fiancée": "fˌiɑnsˈA",
    "née": "nˈA", "propos": "pɹəpˈO", "cheval": "ʃəvˈæl", "daren't": "dˈɛɹᵊnt", "humourous": "hjˈuməɹəs", "à": "ɑ", "sha'n't": "ʃˈænt", "ma'am": "mˈæm", "victuals": "vˈɪtᵊlz", "boatswain": "bˈOsᵊn", "coxswain": "kˈɑksᵊn", "forecastle": "fˈOksᵊl", "gunwale": "ɡˈʌnᵊl",
    "Mademoiselle": "mˌædəmwəzˈɛl", "mademoiselle": "mˌædəmwəzˈɛl", "Monsieur": "məsjˈɜ", "monsieur": "məsjˈɜ", "Messieurs": "mAsjˈɜz", "Madame": "mədˈɑm",
}

# names that turn up again and again in public-domain books
CLASSICS = {
    "Brontë": "bɹˈɑnti", "Bronte": "bɹˈɑnti", "Goethe": "ɡˈɜɹtə", "Quixote": "kihˈOti", "Dulcinea": "dˌʌlsɪnˈAə", "Sancho": "sˈɑnʧO", "Panza": "pˈɑnzə", "Dumas": "dumˈɑ", "Proust": "pɹˈust",
    "Antoine": "ɑntwˈɑn", "Defarge": "dəfˈɑɹʒ", "Defarges": "dəfˈɑɹʒɪz", "Evrémonde": "ˈɛvɹəmɑnd", "Evremonde": "ˈɛvɹəmɑnd", "Beauvais": "bOvˈA", "Conciergerie": "kɔnsjɛɹʒəɹˈi", "Abbaye": "æbˈA",
    "Carmagnole": "kˌɑɹmənjˈOl", "Artagnan": "ɑɹtˈænjən", "Athos": "ˈæθOs", "Porthos": "pˈɔɹθOs", "Aramis": "ˈæɹəmɪs", "Richelieu": "ɹˌiʃəljˈu", "Mazarin": "mˈæzəɹæn",
    "Villefort": "vilfˈɔɹ", "Dantès": "dɑntˈɛs", "Dantes": "dɑntˈɛs", "Danglars": "dɑŋɡlˈɑɹ", "Caderousse": "kædəɹˈus", "Valjean": "vɑlʒˈɑn", "Javert": "ʒɑvˈɛɹ", "Cosette": "kOzˈɛt", "Marius": "mˈæɹiəs",
    "Thénardier": "tənɑɹdjˈA", "Thenardier": "tənɑɹdjˈA", "Gavroche": "ɡævɹˈɔʃ", "Fantine": "fɑntˈin", "Enjolras": "ˌɑnʒɔlɹˈɑs", "Esmeralda": "ˌɛzməɹˈældə", "Quasimodo": "kwˌɑzɪmˈOdO", "Frollo": "fɹˈOlO",
    "Bovary": "bˈOvəɹi", "Emma": "ˈɛmə", "Passepartout": "pˌæspɑɹtˈu", "Aouda": "ɑˈudə", "Aronnax": "ˈæɹənæks", "Conseil": "kɔnsˈA", "Nemo": "nˈimO", "Nautilus": "nˈɔtᵊləs", "Verne": "vˈɜɹn",
    "Candide": "kændˈid", "Cunégonde": "kˈunəɡɑnd", "Cunegonde": "kˈunəɡɑnd", "Pangloss": "pˈæŋɡlɔs", "Voltaire": "vOltˈɛɹ", "Rousseau": "ɹusˈO", "Lecoq": "ləkˈɔk", "Dupin": "dupˈæn", "Rue": "ɹˈu",
    "Bourgh": "bˈɜɹ", "Wickham": "wˈɪkəm", "Hertfordshire": "hˈɑɹtfəɹdʃəɹ", "Derbyshire": "dˈɑɹbiʃəɹ", "Berkshire": "bˈɑɹkʃəɹ", "Worcester": "wˈʊstəɹ", "Worcestershire": "wˈʊstəɹʃəɹ", "Leicester": "lˈɛstəɹ",
    "Leicestershire": "lˈɛstəɹʃəɹ", "Gloucester": "ɡlˈɔstəɹ", "Gloucestershire": "ɡlˈɔstəɹʃəɹ", "Warwick": "wˈɔɹɪk", "Warwickshire": "wˈɔɹɪkʃəɹ", "Norwich": "nˈɔɹɪʤ", "Greenwich": "ɡɹˈɛnɪʧ",
    "Woolwich": "wˈʊlɪʤ", "Southwark": "sˈʌðəɹk", "Marylebone": "mˈæɹᵊləbən", "Cholmondeley": "ʧˈʌmli", "Pall": "pˈæl", "Beaulieu": "bjˈuli", "Salisbury": "sˈɔlzbəɹi", "Shrewsbury": "ʃɹˈOzbəɹi",
    "Edinburgh": "ˈɛdᵊnbəɹə", "Thames": "tˈɛmz", "Holborn": "hˈObəɹn", "Magdalen": "mˈɔdlɪn", "Grosvenor": "ɡɹˈOvnəɹ", "Cadogan": "kədˈʌɡən", "Launceston": "lˈɔnstən", "Alnwick": "ˈænɪk", "Berwick": "bˈɛɹɪk",
    "Ingolstadt": "ˈɪŋɡəlʃtɑt", "Chamounix": "ʃˈæmuni", "Chamonix": "ʃˈæmuni", "Clerval": "klˈɛɹvəl", "Safie": "sˈɑfi", "Plainpalais": "plˌænpəlˈA", "Krempe": "kɹˈɛmpə", "Hareton": "hˈɛɹtən",
    "Earnshaw": "ˈɜɹnʃɔ", "Rochester": "ɹˈɑʧɛstəɹ", "Eyre": "ˈɛɹ", "Adèle": "ədˈɛl", "Adele": "ədˈɛl", "Pip": "pˈɪp", "Magwitch": "mˈæɡwɪʧ", "Estella": "ɛstˈɛlə", "Havisham": "hˈævɪʃəm", "Peggotty": "pˈɛɡəti",
    "Micawber": "mɪkˈɔbəɹ", "Traddles": "tɹˈædᵊlz", "Steerforth": "stˈɪɹfɔɹθ", "Barkis": "bˈɑɹkɪs", "Trotwood": "tɹˈɑtwʊd", "Queequeg": "kwˈikwɛɡ", "Ahab": "ˈAhæb", "Pequod": "pˈikwɑd", "Ishmael": "ˈɪʃmAl",
    "Starbuck": "stˈɑɹbʌk", "Nantucket": "næntˈʌkɪt", "Tashtego": "tæʃtˈiɡO", "Hester": "hˈɛstəɹ", "Prynne": "pɹˈɪn", "Dimmesdale": "dˈɪmzdAl", "Chillingworth": "ʧˈɪlɪŋwɜɹθ", "Dracula": "dɹˈækjələ",
    "Seward": "sˈuəɹd", "Harker": "hˈɑɹkəɹ", "Helsing": "hˈɛlsɪŋ", "Renfield": "ɹˈɛnfild", "Carfax": "kˈɑɹfæks", "Bistritz": "bˈɪstɹɪts", "Holmwood": "hˈOmwʊd", "Kurtz": "kˈɜɹts", "Moreau": "mɔɹˈO",
    "Phileas": "fˈɪliəs", "Jekyll": "ʤˈɛkᵊl", "Lanyon": "lˈænjən", "Utterson": "ˈʌtəɹsən", "Hyde": "hˈId", "Enfield": "ˈɛnfild", "Carew": "kəɹˈu", "Coutts": "kˈuts", "Wollstonecraft": "wˈʊlstənkɹæft", "Stevenson": "stˈivənsən", "Penelope": "pənˈɛləpi", "Telemachus": "təlˈɛməkəs", "Ulysses": "julˈɪsiz", "Odysseus": "Odˈɪsiəs",
    "Achilles": "əkˈɪliz", "Agamemnon": "ˌæɡəmˈɛmnɑn", "Menelaus": "mˌɛnəlˈAəs", "Priam": "pɹˈIəm", "Hecuba": "hˈɛkjubə", "Patroclus": "pətɹˈOkləs", "Andromache": "ændɹˈɑməki", "Alcinous": "ælsˈɪnOəs",
    "Calypso": "kəlˈɪpsO", "Circe": "sˈɜɹsi", "Polyphemus": "pˌɑlɪfˈiməs", "Laertes": "lAˈɜɹtiz", "Nausicaa": "nɔsˈɪkAə", "Eumaeus": "jumˈiəs", "Antinous": "æntˈɪnOəs", "Zarathustra": "zˌæɹəθˈustɹə",
    "Nietzsche": "nˈiʧə", "Schopenhauer": "ʃˈOpənhWəɹ", "Kant": "kˈɑnt", "Hegel": "hˈAɡᵊl", "Plato": "plˈAtO", "Socrates": "sˈɑkɹətiz", "Alcibiades": "ˌælsɪbˈIədiz", "Thrasymachus": "θɹəsˈɪməkəs", "Glaucon": "ɡlˈɔkɑn",
    "Adeimantus": "ˌædɪmˈæntəs", "Beowulf": "bˈAəwʊlf", "Hrothgar": "hɹˈɔθɡɑɹ", "Grendel": "ɡɹˈɛndᵊl", "Faust": "fˈWst", "Mephistopheles": "mˌɛfɪstˈɑfəliz", "Gretchen": "ɡɹˈɛʧən", "Siddhartha": "sɪdˈɑɹtə",
    "Govinda": "ɡOvˈɪndə", "Gotama": "ɡˈOtəmə", "Gautama": "ɡˈWtəmə", "Krishna": "kɹˈɪʃnə", "Arjuna": "ˈɑɹʤunə", "Samsa": "sˈɑmzə", "Gregor": "ɡɹˈɛɡəɹ", "Grete": "ɡɹˈAtə", "Boccaccio": "bOkˈɑʧiO",
    "Machiavelli": "mˌɑkiəvˈɛli", "Borgia": "bˈɔɹʤə", "Medici": "mˈɛdɪʧi", "Cesare": "ʧˈAzəɹA", "Beatrice": "bˈiətɹɪs", "Virgil": "vˈɜɹʤᵊl", "Ibsen": "ˈɪbsən", "Helmer": "hˈɛlməɹ", "Torvald": "tˈɔɹvɑld",
    "Zola": "zˈOlə", "Maupassant": "mˈOpəsɑnt", "Balzac": "bˈælzæk", "Flaubert": "flObˈɛɹ", "Molière": "mOljˈɛɹ", "Moliere": "mOljˈɛɹ", "Racine": "ɹəsˈin", "Montaigne": "mɑntˈAn", "Descartes": "dAkˈɑɹt",
    "Cervantes": "səɹvˈæntiz", "Wodehouse": "wˈʊdhWs", "Pepys": "pˈips", "Maugham": "mˈɔm", "Cthulhu": "kəθˈulu", "Arkham": "ˈɑɹkəm", "Miskatonic": "mˌɪskətˈɑnɪk", "Yog": "jˈɔɡ", "Sothoth": "sˈɔθɔθ", "Hermione": "həɹmˈIəni",
}

RUSSIAN = {
    "Raskolnikov": "ɹəskˈOlnɪkəf", "Razumihin": "ɹəzumˈihɪn", "Razumikhin": "ɹəzumˈikɪn", "Svidrigailov": "svɪdɹɪɡˈIləf", "Svidrigaïlov": "svɪdɹɪɡˈIləf", "Marmeladov": "mɑɹmɪlˈɑdəf", "Sonia": "sˈOnjə", "Sonya": "sˈOnjə",
    "Dounia": "dˈunjə", "Dunya": "dˈunjə", "Porfiry": "pɔɹfˈiɹi", "Pyotr": "pjˈOtəɹ", "Rodya": "ɹˈOdjə", "Rodion": "ɹədiˈOn", "Pulcheria": "pulkˈɛɹiə", "Alexandrovna": "ɑlɪksˈɑndɹəvnə", "Alexandrovitch": "ɑlɪksˈɑndɹəvɪʧ",
    "Avdotya": "əvdˈOtjə", "Luzhin": "lˈuʒɪn", "Zossimov": "zˈOsɪməf", "Nastasya": "nəstˈɑsjə", "Zametov": "zəmˈɛtəf", "Marfa": "mˈɑɹfə", "Sofya": "sˈOfjə", "Lebeziatnikov": "lɪbɪzjˈɑtnɪkəf", "Amalia": "əmˈɑljə",
    "Nikolay": "nɪkəlˈI", "Nikolai": "nɪkəlˈI", "Lizaveta": "lɪzəvˈɛtə", "Polenka": "pəljˈɛŋkə", "Ilya": "ɪljˈɑ", "Nikodim": "nɪkədˈim", "Andrey": "ɑndɹˈA", "Katerina": "kətəɹˈinə", "Karenina": "kəɹˈɛnɪnə", "Karenin": "kəɹˈɛnɪn",
    "Levin": "ljˈɛvɪn", "Oblonsky": "əblˈɔnski", "Stepan": "stɪpˈɑn", "Arkadyevitch": "ɑɹkˈɑdjəvɪʧ", "Arkadyevich": "ɑɹkˈɑdjəvɪʧ", "Darya": "dˈɑɹjə", "Shtcherbatsky": "ʃʧɛɹbˈɑtski", "Shcherbatsky": "ʃʧɛɹbˈɑtski", "Varenka": "vˈɑɹɪŋkə",
    "Ivanitch": "ivˈɑnɪʧ", "Alexey": "əlɪksˈA", "Konstantin": "kənstəntˈin", "Karamazov": "kɛɹəmˈɑzəf", "Alyosha": "əljˈOʃə", "Mitya": "mˈitjə", "Fyodor": "fjˈOdəɹ", "Smerdyakov": "smɛɹdjəkˈɔf", "Grushenka": "ɡɹˈuʃɪŋkə",
    "Zossima": "zˈOsɪmə", "Grigory": "ɡɹɪɡˈɔɹi", "Katya": "kˈɑtjə", "Bolkonsky": "bəlkˈɔnski", "Bolkonski": "bəlkˈɔnski", "Rostov": "ɹəstˈɔf", "Natasha": "nətˈɑʃə", "Bezukhov": "bɪzˈukəf", "Kutuzov": "kutˈuzəf", "Vasili": "vəsˈili",
    "Denisov": "dɪnˈisəf", "Dolokhov": "dˈɔləkəf", "Drubetskoy": "dɹubɪtskˈY", "Karataev": "kəɹətˈIəf", "Bazarov": "bəzˈɑɹəf", "Kirsanov": "kɪɹsˈɑnəf", "Oblomov": "əblˈOməf", "Chichikov": "ʧˈiʧɪkəf", "Akaky": "əkˈɑki",
    "Myshkin": "mˈɪʃkɪn", "Rogozhin": "ɹəɡˈOʒɪn", "Aglaya": "əɡlˈIə", "Nevsky": "nˈɛvski", "Dostoevsky": "dˌɔstəjˈɛfski", "Dostoyevsky": "dˌɔstəjˈɛfski", "Tolstoy": "tˈOlstY", "Tolstoi": "tˈOlstY", "Turgenev": "tuɹɡˈAnjəf",
    "Chekhov": "ʧˈɛkɔf", "Tchekhov": "ʧˈɛkɔf", "Gogol": "ɡˈOɡɔl", "Pushkin": "pˈuʃkɪn", "Gorky": "ɡˈɔɹki", "Gorki": "ɡˈɔɹki", "Petya": "pˈɛtjə", "Vanya": "vˈɑnjə", "Masha": "mˈɑʃə", "Dasha": "dˈɑʃə", "Mishka": "mˈiʃkə",
    "Prokofitch": "pɹəkˈOfɪʧ", "Fomitch": "fəmˈiʧ", "Ilyinitch": "ɪljˈinɪʧ", "Kuzma": "kuzmˈɑ", "Nikita": "nɪkˈitə", "Anisya": "ənˈisjə", "Praskovya": "pɹəskˈOvjə", "Lebedev": "lˈɛbɪdjəf", "Gavrila": "ɡəvɹˈilə", "Varvara": "vəɹvˈɑɹə",
}

V = "ɑɛiɔuəOAIYWɪæʌʊɜ"
SLAV = re.compile(r"(ov|ev|yov|iov|off|eff|ovich|evich|ovitch|evitch|itch|ovna|evna|inichna|sky|ski|skaya|skoy|enko|insk|ansk|insky|itsyn|tsin|yev|iev)$")
SLAV_LOOSE = re.compile(r"(ov|ev|in|yn|ova|eva|ina|ka|ko|ya|ia|asha|usha|osha|enka|oy|aya|yi|ky|ik|ok|ich|itch|na|vna|ovo|evo|gorsk|grad|insk|ansk|ovsk|yor|yr|mir|slav)$")


def slav(w):
    """rule-based English reading of a Russian-looking name"""
    s = w.lower().replace("'", "").replace("ï", "i").replace("ö", "yo").replace("é", "e").replace("ë", "yo")
    m = re.match(r"^(.*?)(ovich|evich|ovitch|evitch|ovna|evna)$", s)
    table = [("shtch", "ʃʧ"), ("shch", "ʃʧ"), ("tch", "ʧ"), ("sch", "ʃ"), ("zh", "ʒ"), ("kh", "k"), ("ch", "ʧ"), ("sh", "ʃ"), ("ts", "ts"), ("ph", "f"), ("ff", "f"), ("ss", "s"), ("ay", "I"), ("ai", "I"), ("ei", "A"), ("ey", "A"),
             ("oi", "Y"), ("oy", "Y"), ("ou", "u"), ("ya", "jɑ"), ("ia", "jɑ"), ("yu", "ju"), ("iu", "ju"), ("yo", "jɔ"), ("ye", "jɛ"), ("ck", "k"), ("x", "ks"), ("a", "ɑ"), ("e", "ɛ"), ("i", "i"), ("o", "O"), ("u", "u"), ("y", "i"),
             ("g", "ɡ"), ("r", "ɹ"), ("j", "j"), ("c", "k"), ("w", "v"), ("q", "k")]
    out, i = [], 0
    while i < len(s):
        for a, b in table:
            if s.startswith(a, i): out.append(b); i += len(a); break
        else: out.append(s[i]); i += 1
    vi = [k for k, p in enumerate(out) if any(c in V for c in p)]
    if not vi: return None
    st = vi[-3] if m and len(vi) >= 3 else vi[-2] if len(vi) >= 2 else vi[-1]
    red = {"ɑ": "ə", "O": "ə", "ɛ": "ɪ", "i": "ɪ", "jɑ": "jə", "jɛ": "jɪ"}
    for k in vi:
        if k == st:
            p = out[k]; out[k] = p[0] + "ˈ" + p[1:] if p[0] == "j" and len(p) > 1 else "ˈ" + p
        elif k == vi[-1] and k == len(out) - 1 and out[k] == "i": pass
        else: out[k] = red.get(out[k], out[k])
    r = "".join(out)
    r = re.sub(r"ɪv$|əv$", "əf", r); r = re.sub(r"v(?=sk)", "f", r)
    return re.sub(r"v$", "f", r)


def possessive(ps):
    if ps[-1] in "szʃʒʧʤ": return ps + "ɪz"
    return ps + ("s" if ps[-1] in "ptkfθ" else "z")


def british(ps):
    v = "ɑɛiɔuəQAIYWɪaʌʊɜ"
    ps = ps.replace("O", "Q").replace("æ", "a")
    for a, b in (("ɔɹ", "ɔː"), ("ɑɹ", "ɑː"), ("əɹ", "ə"), ("ɜɹ", "ɜː"), ("ɛɹ", "ɛː"), ("ɪɹ", "ɪə")): ps = re.sub(a + rf"(?![{v}])", b, ps)
    ps = re.sub(r"ɜ(?!ː)", "ɜː", ps)
    for c in "ɑiu": ps = re.sub(rf"ˈ{c}(?!ː)", f"ˈ{c}ː", ps)
    return ps


def deaccent(w):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c))


class Lexicon:
    """extends a misaki G2P in place"""

    def __init__(self, g2p, texts, is_british, vocab, user=None, slavic="auto"):
        self.g2p, self.lx, self.brit, self.vocab = g2p, g2p.lexicon, is_british, vocab
        self.words = Counter(w.strip("'") for t in texts for w in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ']*", t))
        self.respell, self.added = {}, {}
        for w, p in FIXES.items(): self.add(w, p)
        for w, p in CLASSICS.items(): self.add(w, p)
        hits = {w for w in self.words if w[0].isupper() and len(w) > 4 and SLAV.search(w) and not self.known(w)} | (set(RUSSIAN) & set(self.words))
        self.slavic = slavic is True or (slavic == "auto" and len(hits) >= 8)
        if self.slavic: self.load_slavic()
        self.derive()
        for w, p in (user or {}).items():
            w, p = str(w).strip(), str(p).strip()
            if not w or not p: continue
            if p.startswith("/") and p.endswith("/") and len(p) > 2:
                ps = p[1:-1]
                if all(c in vocab for c in ps): self.add(w, ps, convert=False)
            else: self.respell[w] = p
        self.respell_re = re.compile(r"(?<!\w)(" + "|".join(sorted(map(re.escape, self.respell), key=len, reverse=True)) + r")(?=('s)?(?!\w))") if self.respell else None

    def known(self, w):
        g, s = self.lx.golds, self.lx.silvers
        return w in g or w in s or w.lower() in g or w.lower() in s

    def add(self, w, ps, convert=True):
        if convert and self.brit: ps = british(ps)
        if not all(c in self.vocab for c in ps): return
        self.lx.golds[w] = ps
        if w.isalpha(): self.lx.golds[w + "'s"] = possessive(ps)
        self.added[w] = ps

    def load_slavic(self):
        with open(os.path.join(DATA, "slavic.json"), encoding="utf-8") as f: names = json.load(f)
        names = {**names, **RUSSIAN}
        for w, p in list(names.items()):
            if w.endswith(("ovich", "evich")): names.setdefault(w[:-2] + "tch", p); names.setdefault(w[:-4] + w[-4:-2] + "itch", p)
        for w, p in names.items(): self.add(w, p)
        for w, n in self.words.items():
            b = w[:-2] if w.endswith("'s") else w
            if len(b) < 4 or not b[0].isupper() or not b[1:].islower() or b in self.added or self.known(b) or b.lower() in self.words: continue
            if SLAV.search(b) or (n >= 2 and SLAV_LOOSE.search(b) and not re.search(r"w|q|th|gh|ee|oo|ck", b.lower())):
                p = slav(b)
                if p: self.add(b, p)

    def derive(self):
        """words built from ones the dictionary knows"""
        g, s = self.lx.golds, self.lx.silvers
        def get(w):
            p = g.get(w) or s.get(w)
            if isinstance(p, dict): p = p.get("DEFAULT") or p.get("VERB")
            return p if isinstance(p, str) else None
        for w in list(self.words):
            l = w.lower(); base = l[:-2] if l.endswith("'s") else l
            if l.endswith("ied") and l not in g and get(l[:-3] + "y"): g[l] = get(l[:-3] + "y") + "d"; continue
            if self.known(base): continue
            if re.search(r"[^\x00-\x7f]", base):
                d = deaccent(base); p = get(d) or get(d.capitalize())
                if p: g[w] = p if base == l else possessive(p); continue
            for a in ("ae", "oe"):
                if a in base:
                    p = get(base.replace(a, "e"))
                    if p: g[w] = g[base] = p if base == l else possessive(p); break

    def respelled(self, t):
        return self.respell_re.sub(lambda m: self.respell[m.group(1)], t) if self.respell_re else t

    def unknown(self, limit=40):
        """words read by guesswork, most frequent first (for the report)"""
        out, total = [], Counter()
        for w, n in self.words.items(): total[w[:-2] if w.endswith("'s") else w] += n
        for b, n in total.most_common():
            if len(b) < 3 or self.known(b) or b in self.added: continue
            if any(x and x[0] for x in (self._stem(b), self._stem(b.lower()))): continue
            out.append((b, n))
            if len(out) >= limit: break
        return out

    def _stem(self, w):
        for f in (self.lx.stem_s, self.lx.stem_ed, self.lx.stem_ing):
            try:
                r = f(w, None, None, None)
                if r and r[0]: return r
            except Exception: pass
        return None
