"""How the flight app reads the register of a caller's Arabic, for settings.py's `for_the_app`:
Saudi first (the library's `words.saudi_first`), so a Najdi caller whose turns hold no form of
the library's list is answered in Saudi, and the app's own Saudi forms added to that list
(`words.dialect`), each unless the environment sets it.

The owner's call of 2026-11-18 (05:57) greeted «السلام عليكم. كيف الحال؟» and went on «شوف يا
طويل العمر، ودي أروح من الرياض إلى القاهرة», «امم، شوف لي الأسبوع الجاي» and «إي نعم»: the
library read every turn as MSA, since none held a form of its list, and Saad answered in MSA
throughout ("it is only standard Arabic"). The library's own list stays as it was, so Ole5's
reading does not move (GP-18): the app adds its forms through the setting.

Arabic is written plainly, as the app's other word modules write it.
"""

from __future__ import annotations

from typing import Final

# The Saudi forms the app adds, each a word or a phrase heard as its words in a row.
DIALECT: Final = (
    "ودي",  # wuddi, I would like
    "الجاي",  # al-jay, next («الأسبوع الجاي», next week)
    "بكرة",  # bukra, tomorrow
    "نبي",  # nabi, we want
    "تبغى",  # tabgha, you want
    "حقت",  # haggat, of (belonging to)
    "خلها",  # khallha, leave it, make it
    "طويل العمر",  # taweel al-omr, sir (long of life)
    "شوف",  # shoof, look, see
)
# The `words` settings the app sets for either agent, each unless the environment sets it:
# the register held fixed for the whole call, Najdi by default (the owner, 2026-11-18: "make a
# switch for Nadji and Arabic, don't make them change during the call");
# T2V_WORDS__FIXED_REGISTER=msa holds a call in MSA instead.
REGISTER_WORDS: Final[dict[str, object]] = {
    "fixed_register": "saudi",
    "saudi_first": True,
    "dialect": DIALECT,
}
