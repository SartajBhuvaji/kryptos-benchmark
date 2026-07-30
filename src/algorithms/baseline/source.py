"""Canonical text of the four Kryptos passages, exactly as carved.

The sculpture's left panel carries 869 characters across 28 lines. Those characters
are reproduced here verbatim, including the literal ``?`` marks that appear in K2 and
K3. ``?`` is a pass-through: it is not enciphered and does not advance the key.

Provenance
----------
Transcribed from the ``<pre>`` left-panel block of the English Wikipedia "Kryptos"
article (retrieved 2026-07-30 via the MediaWiki ``action=parse`` API, which returns
raw wikitext and therefore avoids the transcription corruption that HTML-to-text
conversion introduces). Plaintexts come from the same article's "Solution of passage N"
blockquotes.

The transcription is verified four independent ways in ``tests/test_baseline.py``:
length checksums (63/372/337/97 = 869), plaintext/ciphertext length preservation,
the K3 anagram identity, and Quagmire III periodic consistency at periods 10 and 8.
Those checks fail on a single altered character, so they are the real guarantee here --
not the source URL.
"""

RETRIEVED = "2026-07-30"

SOURCE_URLS = (
    "https://en.wikipedia.org/wiki/Kryptos",
    "https://en.wikipedia.org/w/api.php?action=parse&page=Kryptos&prop=wikitext",
)

#: The left panel as carved, one string per physical line.
CARVED_LINES = (
    "EMUFPHZLRFAXYUSDJKZLDKRNSHGNFIVJ",
    "YQTQUXQBQVYUVLLTREVJYQTMKYRDMFD",
    "VFPJUDEEHZWETZYVGWHKKQETGFQJNCE",
    "GGWHKK?DQMCPFQZDQMMIAGPFXHQRLG",
    "TIMVMZJANQLVKQEDAGDVFRPJUNGEUNA",
    "QZGZLECGYUXUEENJTBJLBQCRTBJDFHRR",
    "YIZETKZEMVDUFKSJHKFWHKUWQLSZFTI",
    "HHDDDUVH?DWKBFUFPWNTDFIYCUQZERE",
    "EVLDKFEZMOQQJLTTUGSYQPFEUNLAVIDX",
    "FLGGTEZ?FKZBSFDQVGOGIPUFXHHDRKF",
    "FHQNTGPUAECNUVPDJMQCLQUMUNEDFQ",
    "ELZZVRRGKFFVOEEXBDMVPNFQXEZLGRE",
    "DNQFMPNZGLFLPMRJQYALMGNUVPDXVKP",
    "DQUMEBEDMHDAFMJGZNUPLGEWJLLAETG",
    "ENDYAHROHNLSRHEOCPTEOIBIDYSHNAIA",
    "CHTNREYULDSLLSLLNOHSNOSMRWXMNE",
    "TPRNGATIHNRARPESLNNELEBLPIIACAE",
    "WMTWNDITEENRAHCTENEUDRETNHAEOE",
    "TFOLSEDTIWENHAEIOYTEYQHEENCTAYCR",
    "EIFTBRSPAMHHEWENATAMATEGYEERLB",
    "TEEFOASFIOTUETUAEOTOARMAEERTNRTI",
    "BSEDDNIAAHTTMSTEWPIEROAGRIEWFEB",
    "AECTDDHILCEIHSITEGOEAOSDDRYDLORIT",
    "RKLMLEHAGTDHARDPNEOHMGFMFEUHE",
    "ECDMRIPFEIMEHNLSSTTRTVDOHW?OBKR",
    "UOXOGHULBSOLIFBBWFLRVQQPRNGKSSO",
    "TWTQSJQSSEKZZWATJKLUDIAWINFBNYP",
    "VTTMZFPKWGDKZXTJCDIGKUHUAUEKCAR",
)

# --- ciphertexts (exact, including literal '?') ---------------------------------

K1_CIPHERTEXT = (
    "EMUFPHZLRFAXYUSDJKZLDKRNSHGNFIVJYQTQUXQBQVYUVLLTREVJYQTMKYRDMF"
    "D"
)

K2_CIPHERTEXT = (
    "VFPJUDEEHZWETZYVGWHKKQETGFQJNCEGGWHKK?DQMCPFQZDQMMIAGPFXHQRLGT"
    "IMVMZJANQLVKQEDAGDVFRPJUNGEUNAQZGZLECGYUXUEENJTBJLBQCRTBJDFHRR"
    "YIZETKZEMVDUFKSJHKFWHKUWQLSZFTIHHDDDUVH?DWKBFUFPWNTDFIYCUQZERE"
    "EVLDKFEZMOQQJLTTUGSYQPFEUNLAVIDXFLGGTEZ?FKZBSFDQVGOGIPUFXHHDRK"
    "FFHQNTGPUAECNUVPDJMQCLQUMUNEDFQELZZVRRGKFFVOEEXBDMVPNFQXEZLGRE"
    "DNQFMPNZGLFLPMRJQYALMGNUVPDXVKPDQUMEBEDMHDAFMJGZNUPLGEWJLLAETG"
)

K3_CIPHERTEXT = (
    "ENDYAHROHNLSRHEOCPTEOIBIDYSHNAIACHTNREYULDSLLSLLNOHSNOSMRWXMNE"
    "TPRNGATIHNRARPESLNNELEBLPIIACAEWMTWNDITEENRAHCTENEUDRETNHAEOET"
    "FOLSEDTIWENHAEIOYTEYQHEENCTAYCREIFTBRSPAMHHEWENATAMATEGYEERLBT"
    "EEFOASFIOTUETUAEOTOARMAEERTNRTIBSEDDNIAAHTTMSTEWPIEROAGRIEWFEB"
    "AECTDDHILCEIHSITEGOEAOSDDRYDLORITRKLMLEHAGTDHARDPNEOHMGFMFEUHE"
    "ECDMRIPFEIMEHNLSSTTRTVDOHW?"
)

K4_CIPHERTEXT = (
    "OBKRUOXOGHULBSOLIFBBWFLRVQQPRNGKSSOTWTQSJQSSEKZZWATJKLUDIAWINF"
    "BNYPVTTMZFPKWGDKZXTJCDIGKUHUAUEKCAR"
)

# --- plaintexts (readable form, spaces for legibility) ---------------------------

K1_PLAINTEXT = (
    "BETWEEN SUBTLE SHADING AND THE ABSENCE OF LIGHT LIES THE NUANC"
    "E OF IQLUSION"
)

#: The carved K2 ciphertext decrypts to an ending of "WEST ID BY ROWS". Sanborn has
#: said he omitted a ciphertext character during fabrication and that the intended
#: reading is "WEST X LAYER TWO" -- one character longer than the ciphertext supports.
#: Ground truth here is what the given ciphertext actually yields; the intended
#: reading is recorded as an anomaly instead.
K2_PLAINTEXT = (
    "IT WAS TOTALLY INVISIBLE HOWS THAT POSSIBLE ? THEY USED THE EA"
    "RTHS MAGNETIC FIELD X THE INFORMATION WAS GATHERED AND TRANSMI"
    "TTED UNDERGRUUND TO AN UNKNOWN LOCATION X DOES LANGLEY KNOW AB"
    "OUT THIS ? THEY SHOULD ITS BURIED OUT THERE SOMEWHERE X WHO KN"
    "OWS THE EXACT LOCATION ? ONLY WW THIS WAS HIS LAST MESSAGE X T"
    "HIRTY EIGHT DEGREES FIFTY SEVEN MINUTES SIX POINT FIVE SECONDS"
    " NORTH SEVENTY SEVEN DEGREES EIGHT MINUTES FORTY FOUR SECONDS "
    "WEST ID BY ROWS"
)

K2_INTENDED_ENDING = "WEST X LAYER TWO"

K3_PLAINTEXT = (
    "SLOWLY DESPARATLY SLOWLY THE REMAINS OF PASSAGE DEBRIS THAT EN"
    "CUMBERED THE LOWER PART OF THE DOORWAY WAS REMOVED WITH TREMBL"
    "ING HANDS I MADE A TINY BREACH IN THE UPPER LEFT HAND CORNER A"
    "ND THEN WIDENING THE HOLE A LITTLE I INSERTED THE CANDLE AND P"
    "EERED IN THE HOT AIR ESCAPING FROM THE CHAMBER CAUSED THE FLAM"
    "E TO FLICKER BUT PRESENTLY DETAILS OF THE ROOM WITHIN EMERGED "
    "FROM THE MIST X CAN YOU SEE ANYTHING Q ?"
)

#: K4 is unsolved. No plaintext exists.
K4_PLAINTEXT = None

# --- cipher parameters -----------------------------------------------------------

#: KRYPTOS with duplicate letters removed, then the rest of the alphabet appended.
#: Carved into the sculpture's right-hand panel and used by both K1 and K2.
KEYED_ALPHABET = "KRYPTOSABCDEFGHIJLMNQUVWXZ"

K1_ALPHABET_KEYWORD = "KRYPTOS"
K1_INDICATOR_KEYWORD = "PALIMPSEST"
K1_PERIOD = 10

K2_ALPHABET_KEYWORD = "KRYPTOS"
K2_INDICATOR_KEYWORD = "ABSCISSA"
K2_PERIOD = 8

# --- K4 cribs --------------------------------------------------------------------

#: Plaintext fragments released by Jim Sanborn, with 1-indexed inclusive positions.
#: EAST/NORTHEAST were released in 2014, BERLIN in 2010, CLOCK in 2014/2020.
K4_CRIBS = (
    {"plaintext": "EAST", "start": 22, "end": 25},
    {"plaintext": "NORTHEAST", "start": 26, "end": 34},
    {"plaintext": "BERLIN", "start": 64, "end": 69},
    {"plaintext": "CLOCK", "start": 70, "end": 74},
)
