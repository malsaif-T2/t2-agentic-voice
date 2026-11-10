"""The texts each language preset gives (domain/declaration.py's `Language.saudi_arabic`,
`arabic` and `english`): the echo's frame and the text of each notice, in the language's register
(plan 003, Q3 and Q5: Saudi for `ar-SA`, Modern Standard Arabic for `ar`), and the lines an
action may leave to the library (plan 007). A team gives its own greeting, and may give its own
notices and an action its own lines. The Arabic texts are written with `\\u` escapes, as the
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
        # ma'aleesh, inqata' al-jawab. tabeeh min al-bidaaya: sorry, the answer was cut off; do
        # you want it from the start?
        "cut_off": (
            "\u0645\u0639\u0644\u064a\u0634\u060c \u0627\u0646\u0642\u0637\u0639 "
            "\u0627\u0644\u062c\u0648\u0627\u0628. \u062a\u0628\u064a\u0647 \u0645\u0646 "
            "\u0627\u0644\u0628\u062f\u0627\u064a\u0629\u061f"
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
        # 'udhran, inqata'at al-ijaaba. hal tureeduha min al-bidaaya: sorry, the answer was cut
        # off; do you want it from the start?
        "cut_off": (
            "\u0639\u0630\u0631\u0627\u060c \u0627\u0646\u0642\u0637\u0639\u062a "
            "\u0627\u0644\u0625\u062c\u0627\u0628\u0629. \u0647\u0644 "
            "\u062a\u0631\u064a\u062f\u0647\u0627 \u0645\u0646 "
            "\u0627\u0644\u0628\u062f\u0627\u064a\u0629\u061f"
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
        "cut_off": "Sorry, that answer got cut off. Do you want it from the start?",
        "ended": "The call has ended. Thank you for calling.",
    },
}
# The library's lines for an action that leaves them out (plan 007; domain/action_lines.py's
# `ActionLines`), by its field: `sending`, said while the write runs, a progress line that never
# says it is done; `failed`, definitely not done; `unknown`, no reply and no lookup hit, with no
# number; `declined`, nothing usable heard after the last ask-again; and `asked_again`, after an
# unclear answer. Each fits any action ("your request"), and none holds a yes word, a listening
# sound or a stop, wait or repeat word, so its echo neither confirms nor stops anything.
ACTION_LINES: Mapping[LanguageTag, Mapping[str, str]] = {
    "ar-SA": {
        # thawaani, jaalis asajjil talabak: seconds, I'm registering your request.
        "sending": (
            "\u062b\u0648\u0627\u0646\u064a\u060c \u062c\u0627\u0644\u0633 "
            "\u0623\u0633\u062c\u0644 \u0637\u0644\u0628\u0643."
        ),
        # al-ma'dhira, ma gidart asajjil talabak, w ma taghayyar shay: sorry, I couldn't register
        # your request, and nothing has changed.
        "failed": (
            "\u0627\u0644\u0645\u0639\u0630\u0631\u0629\u060c \u0645\u0627 "
            "\u0642\u062f\u0631\u062a \u0623\u0633\u062c\u0644 \u0637\u0644\u0628\u0643\u060c "
            "\u0648\u0645\u0627 \u062a\u063a\u064a\u0631 \u0634\u064a."
        ),
        # al-ma'dhira, ma gidart at'akkad idha wasal talabak, w fareeqna bitaab'ah: sorry, I
        # couldn't make sure your request got through, and our team will follow it up.
        "unknown": (
            "\u0627\u0644\u0645\u0639\u0630\u0631\u0629\u060c \u0645\u0627 "
            "\u0642\u062f\u0631\u062a \u0623\u062a\u0623\u0643\u062f \u0625\u0630\u0627 "
            "\u0648\u0635\u0644 \u0637\u0644\u0628\u0643\u060c "
            "\u0648\u0641\u0631\u064a\u0642\u0646\u0627 "
            "\u0628\u064a\u062a\u0627\u0628\u0639\u0647."
        ),
        # ma wadah li raddak, fa ma sajjalt shay: your answer wasn't clear to me, so I registered
        # nothing.
        "declined": (
            "\u0645\u0627 \u0648\u0636\u062d \u0644\u064a \u0631\u062f\u0643\u060c "
            "\u0641\u0645\u0627 \u0633\u062c\u0644\u062a \u0634\u064a."
        ),
        # al-ma'dhira, ma wadah li raddak. asajjil at-talab: sorry, your answer wasn't clear to
        # me. Shall I register the request?
        "asked_again": (
            "\u0627\u0644\u0645\u0639\u0630\u0631\u0629\u060c \u0645\u0627 \u0648\u0636\u062d "
            "\u0644\u064a \u0631\u062f\u0643. \u0623\u0633\u062c\u0644 "
            "\u0627\u0644\u0637\u0644\u0628\u061f"
        ),
    },
    "ar": {
        # yajri al-aan tasjeel talabik: your request is being registered now.
        "sending": (
            "\u064a\u062c\u0631\u064a \u0627\u0644\u0622\u0646 \u062a\u0633\u062c\u064a\u0644 "
            "\u0637\u0644\u0628\u0643."
        ),
        # 'udhran, ta'adhdhar tasjeel talabik, wa lam yataghayyar shay': sorry, your request
        # could not be registered, and nothing has changed.
        "failed": (
            "\u0639\u0630\u0631\u0627\u060c \u062a\u0639\u0630\u0631 "
            "\u062a\u0633\u062c\u064a\u0644 \u0637\u0644\u0628\u0643\u060c \u0648\u0644\u0645 "
            "\u064a\u062a\u063a\u064a\u0631 \u0634\u064a\u0621."
        ),
        # 'udhran, lam atamakkan min at-ta'akkud min wusool talabik, wa sa-yutaabi'uhu
        # fareequna: sorry, I could not make sure your request got through, and our team will
        # follow it up.
        "unknown": (
            "\u0639\u0630\u0631\u0627\u060c \u0644\u0645 \u0623\u062a\u0645\u0643\u0646 "
            "\u0645\u0646 \u0627\u0644\u062a\u0623\u0643\u062f \u0645\u0646 "
            "\u0648\u0635\u0648\u0644 \u0637\u0644\u0628\u0643\u060c "
            "\u0648\u0633\u064a\u062a\u0627\u0628\u0639\u0647 "
            "\u0641\u0631\u064a\u0642\u0646\u0627."
        ),
        # lam yattadih li raddak, li-dhaa lam usajjil shay'an: your answer was not clear to me,
        # so I registered nothing.
        "declined": (
            "\u0644\u0645 \u064a\u062a\u0636\u062d \u0644\u064a \u0631\u062f\u0643\u060c "
            "\u0644\u0630\u0627 \u0644\u0645 \u0623\u0633\u062c\u0644 \u0634\u064a\u0626\u0627."
        ),
        # 'udhran, lam yattadih li raddak. hal usajjil at-talab: sorry, your answer was not
        # clear to me. Shall I register the request?
        "asked_again": (
            "\u0639\u0630\u0631\u0627\u060c \u0644\u0645 \u064a\u062a\u0636\u062d \u0644\u064a "
            "\u0631\u062f\u0643. \u0647\u0644 \u0623\u0633\u062c\u0644 "
            "\u0627\u0644\u0637\u0644\u0628\u061f"
        ),
    },
    "en": {
        "sending": "Sending it now, just a few seconds.",
        "failed": "Sorry, I couldn't get that done. Nothing has changed.",
        "unknown": "Sorry, I can't tell yet whether it went through. Our team will check on it.",
        "declined": "I couldn't get a clear answer, so I haven't sent anything.",
        "asked_again": "Sorry, I didn't catch that. Shall I go ahead?",
    },
}
