"""The texts each language preset gives (domain/declaration.py's `Language.saudi_arabic`,
`arabic` and `english`): the echo's frame and the text of each notice, in the language's register
(plan 003, Q3 and Q5: Saudi for `ar-SA`, Modern Standard Arabic for `ar`). A team gives its own
greeting, and may give its own notices. The Arabic texts are written with `\\u` escapes, as the
library's tables of Arabic characters are (domain/text), each with its sound and meaning in a
comment.
"""

from __future__ import annotations

from collections.abc import Mapping

from t2_agentic_voice.core.settings.tts import LanguageTag

# The echo's frames (plan 003, Q3, in the Saudi register Q5 chose for the fixed phrases). The
# Arabic one, said for both Arabic presets, is «سمعتك تقول:»: seen, meem, ain, teh, kaf; a space;
# teh, qaf, waw, lam; a colon.
ARABIC_FRAME = "\u0633\u0645\u0639\u062a\u0643 \u062a\u0642\u0648\u0644:"
ECHO_FRAMES: Mapping[LanguageTag, str] = {
    "ar-SA": ARABIC_FRAME,
    "ar": ARABIC_FRAME,
    "en": "I heard:",
}
# Each preset's notices: `ar-SA`'s in the Saudi register Q5 chose for the fixed phrases, `ar`'s
# in Modern Standard Arabic. Each comment gives the text's sound, then its meaning.
NOTICES: Mapping[LanguageTag, Mapping[str, str]] = {
    "ar-SA": {
        # al-khutoot mashghoola al-heen, haawil marra thaanya ba'd shway: the lines are busy
        # now; try again in a little while.
        "busy": (
            "\u0627\u0644\u062e\u0637\u0648\u0637 \u0645\u0634\u063a\u0648\u0644\u0629 "
            "\u0627\u0644\u062d\u064a\u0646\u060c \u062d\u0627\u0648\u0644 \u0645\u0631\u0629 "
            "\u062b\u0627\u0646\u064a\u0629 \u0628\u0639\u062f \u0634\u0648\u064a."
        ),
        # saar 'indana khalal baseet, takallam marra thaanya law samaht: we had a small fault;
        # speak once more, please.
        "error": (
            "\u0635\u0627\u0631 \u0639\u0646\u062f\u0646\u0627 \u062e\u0644\u0644 "
            "\u0628\u0633\u064a\u0637\u060c \u062a\u0643\u0644\u0645 \u0645\u0631\u0629 "
            "\u062b\u0627\u0646\u064a\u0629 \u0644\u0648 \u0633\u0645\u062d\u062a."
        ),
        # intahat al-mukaalama, ya'teek al-'aafya: the call has ended; may you be well.
        "ended": (
            "\u0627\u0646\u062a\u0647\u062a \u0627\u0644\u0645\u0643\u0627\u0644\u0645\u0629\u060c "
            "\u064a\u0639\u0637\u064a\u0643 \u0627\u0644\u0639\u0627\u0641\u064a\u0629."
        ),
    },
    "ar": {
        # al-khutoot mashghoola al-aan, yurja al-muhaawala marra ukhra ba'd qaleel: the lines
        # are busy now; please try again shortly.
        "busy": (
            "\u0627\u0644\u062e\u0637\u0648\u0637 \u0645\u0634\u063a\u0648\u0644\u0629 "
            "\u0627\u0644\u0622\u0646\u060c \u064a\u0631\u062c\u0649 "
            "\u0627\u0644\u0645\u062d\u0627\u0648\u0644\u0629 \u0645\u0631\u0629 "
            "\u0623\u062e\u0631\u0649 \u0628\u0639\u062f \u0642\u0644\u064a\u0644."
        ),
        # hadath khalal ladayna, hal yumkinuka i'aadat ma qultah: a fault occurred on our side;
        # can you repeat what you said?
        "error": (
            "\u062d\u062f\u062b \u062e\u0644\u0644 \u0644\u062f\u064a\u0646\u0627\u060c "
            "\u0647\u0644 \u064a\u0645\u0643\u0646\u0643 \u0625\u0639\u0627\u062f\u0629 "
            "\u0645\u0627 \u0642\u0644\u062a\u0647\u061f"
        ),
        # intahat al-mukaalama, shukran li-ittisaalik: the call has ended; thank you for calling.
        "ended": (
            "\u0627\u0646\u062a\u0647\u062a \u0627\u0644\u0645\u0643\u0627\u0644\u0645\u0629\u060c "
            "\u0634\u0643\u0631\u0627 \u0644\u0627\u062a\u0635\u0627\u0644\u0643."
        ),
    },
    "en": {
        "busy": "All our lines are busy right now. Please try again in a little while.",
        "error": "Something went wrong on our side. Could you say that again?",
        "ended": "The call has ended. Thank you for calling.",
    },
}
