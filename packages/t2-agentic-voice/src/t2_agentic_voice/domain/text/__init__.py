"""domain/text: the rules for a speech text, with no IO.

The canonical Arabic normalizer (`arabic.py`), digit normalization (`digits.py`), whole-word
matching of normalized texts (`words.py`), the check of a team's spelling guide (`spelling.py`,
on the rulings of `rulings.py`), and the characters no one sees that a spoken phrase may hold,
with the text a provider is sent for one (`invisible.py`), the scripts a reply may hold, each
other script's characters taken out (`scripts.py`); and, as signatures so far, speaking
numbers and IDs (`speaking.py`), the clause splitter (`clauses.py`) and the pronunciation map
(`pronounce.py`). Apps reach them through the `languages` facade (D-021). The library's tables
of Arabic characters are written with `\\u` escapes, each character named in a comment.
"""
