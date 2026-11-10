"""What Ole5's actions say, in Saudi Arabic and English, the two languages Ole5 speaks (agent.py),
and in MSA (`ar`), which an `ar-SA` reply says to a caller who speaks MSA, in the Saudi voice
(the library's `wording`; the owner's ruling of 2026-11-10): for each action its read-back, a
summary and a closing question; `done`, filled from the ticket system's real reply; `sending`,
said while the write runs, which never says it is done; the `failed`, `unknown` and `declined`
lines; and the phrases that would claim it (`claims`), which the output guard blocks unless the
record or a status result holds the action (the design's 6.4 and 8.2).

In the register of Ole5's other lines (agent.py): short, plain, friendly, Saudi for `ar-SA`;
formal and as short for `ar`, with no dialect form. A read-back states every field that is
sent, the handoff's attached conversation too (invariant 1); `done` says a ticket's whole
number digit by digit in groups of four (plan 007's Q6); no line says a person is joining or
will call (D-009), and `unknown` gives no number (invariant 6). No line but a closing question
holds a word the caller commands with (a stop, a wait, a repeat, a listening sound, a yes or a
send), so its echo is never heard as the caller's; each closing question holds its action's own
send word (`SEND_WORDS`), so a yes said over it with that word counts (the design's 8.3). No
line holds a phrase the guard reads as a claim, any action's own, the library's defaults or
`NUMBER_CLAIMS`, since the talker reads the lines in the call's history and copies their words:
`done` says a ticket's number in other words than «رقم تذكرتك» and "your ticket number is". The
ask-again line is the library's, in MSA for an MSA caller.
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice import Claims, ReadBack, Say

# The send word each closing question holds, in Saudi Arabic and MSA alike, added to the
# language presets' (by primary code).
SEND_WORDS: Final = {"ar": ["أرسلها"], "en": ["send it"]}
# What says a number is the caller's ticket number, which claims any of the three actions (the
# owner's ruling of 2026-11-10), by primary code: the guard reads them with its default phrases
# (`guard.claims`, tickets/tools.py's `with_ticket_claims`), so a number said so passes only on
# an action done in this call or a status that found the ticket, and its number must be theirs.
NUMBER_CLAIMS: Final = {
    # raqm tadhkirtak: your ticket's number; in MSA the same words, raqmu tadhkiratika
    "ar": ["رقم تذكرتك"],
    "en": ["your ticket number is"],
}
_ASK_AR: Final = "تبيني أرسلها؟"  # tabeeni arsilha: do you want me to send it?
_ASK_MSA: Final = "هل أرسلها؟"  # hal ursiluha: shall I send it?
_ASK_EN: Final = "Shall I send it?"

# create_ticket
TICKET_READ_BACK: Final = ReadBack(
    {
        # I'll open you a ticket, its type ..., its priority ...: ...
        "ar-SA": ("بفتح لك تذكرة نوعها {type} وأولويتها {priority}: {summary}", _ASK_AR),
        # sa-aftahu laka tadhkiratan naw'uha ... wa-awlawiyyatuha ...: I will open you a
        # ticket, its type ..., its priority ...: ...
        "ar": ("سأفتح لك تذكرة نوعها {type} وأولويتها {priority}: {summary}", _ASK_MSA),
        "en": ("I'll open a ticket, type {type}, priority {priority}: {summary}", _ASK_EN),
    },
    send_words=SEND_WORDS,
)
TICKET_DONE: Final = Say(
    {
        # tamm, tadhkirtak raqmha ...: done, your ticket, its number is ...
        "ar-SA": "تم، تذكرتك رقمها {part_1:id}، {part_2:id}، {part_3:id}، {part_4:id}.",
        # tamma, raqmu at-tadhkira ...: done, the ticket's number is ...
        "ar": "تم، رقم التذكرة {part_1:id}، {part_2:id}، {part_3:id}، {part_4:id}.",
        "en": "Done. The ticket number is {part_1:id}, {part_2:id}, {part_3:id}, {part_4:id}.",
    }
)
TICKET_SENDING: Final = Say(
    {
        "ar-SA": "أفتح لك التذكرة الحين.",  # I'm opening the ticket for you now.
        "ar": "أفتح لك التذكرة الآن.",  # aftahu laka at-tadhkira al-aan: the same, in MSA
        "en": "I'm opening the ticket now.",
    }
)
TICKET_FAILED: Final = Say(
    {
        # Sorry, the ticket system refused the ticket, so there is no ticket and no number.
        "ar-SA": "للأسف نظام التذاكر رفض التذكرة، فما فيه تذكرة ولا رقم.",
        # lil-asaf rafada nidhaamu at-tadhaakir at-tadhkira, fa-la tujadu tadhkiratun wa-la
        # raqm: the same, in MSA
        "ar": "للأسف رفض نظام التذاكر التذكرة، فلا توجد تذكرة ولا رقم.",
        "en": "Unfortunately the ticket system refused the ticket, so there is no ticket and no "
        "number.",
    }
)
TICKET_UNKNOWN: Final = Say(
    {
        # I could not make sure of the ticket, so I have no number to give you.
        "ar-SA": "ما قدرت أتأكد من التذكرة، فما عندي رقم أعطيك إياه.",
        # lam atamakkan min at-ta'akkud min at-tadhkira, fa-laysa ladayya raqmun u'teeka
        # iyyaah: the same, in MSA
        "ar": "لم أتمكن من التأكد من التذكرة، فليس لدي رقم أعطيك إياه.",
        "en": "I can't tell whether the ticket went through, so I have no number to give you.",
    }
)
TICKET_DECLINED: Final = Say(
    {
        # I did not send the ticket. If you want to open it later, tell me.
        "ar-SA": "ما أرسلت التذكرة. إذا تبي تفتحها بعدين قل لي.",
        # lam yatimm irsaalu at-tadhkira. in aradta fathaha laahiqan fa-akhbirni: the ticket
        # was not sent. If you want to open it later, tell me.
        "ar": "لم يتم إرسال التذكرة. إن أردت فتحها لاحقا فأخبرني.",
        "en": "I haven't sent the ticket. Tell me if you want to open it later.",
    }
)
TICKET_CLAIMS: Final = Claims(
    {
        "ar-SA": [
            "فتحت لك تذكرة",  # I opened you a ticket
            "فتحت لك التذكرة",
            "فتحت التذكرة",
            "تم فتح التذكرة",  # the ticket was opened
            "تم فتح تذكرة",
            "انفتحت التذكرة",
            "سجلت لك تذكرة",  # I logged you a ticket
            "سجلت التذكرة",
            "رفعت لك تذكرة",  # I raised you a ticket
            "رفعت التذكرة",
            "تم رفع التذكرة",
            "أنشأت التذكرة",  # I created the ticket
            "تم إنشاء التذكرة",
            "تم تسجيل التذكرة",
        ],
        "en": [
            "I've opened",
            "I have opened",
            "I opened a ticket",
            "I opened the ticket",
            "ticket opened",
            "ticket has been opened",
            "ticket was opened",
            "I've created",
            "I have created",
            "ticket created",
            "ticket has been created",
            "ticket was created",
            "I've raised",
            "I raised a ticket",
            "ticket raised",
            "I've logged",
            "ticket logged",
        ],
    }
)

# add_ticket_note
NOTE_READ_BACK: Final = ReadBack(
    {
        # I'll add to your ticket that ends in the digits ... this note: ...
        "ar-SA": (
            "بضيف على تذكرتك اللي تنتهي بالأرقام {ticket_ends_in:id} هالملاحظة: {note}",
            _ASK_AR,
        ),
        # sa-udeefu ila tadhkiratika allati tantahi bil-arqaam ... hadhihi al-mulaahadha: I will
        # add to your ticket that ends in the digits ... this note: ...
        "ar": (
            "سأضيف إلى تذكرتك التي تنتهي بالأرقام {ticket_ends_in:id} هذه الملاحظة: {note}",
            _ASK_MSA,
        ),
        "en": ("I'll add this note to your ticket ending {ticket_ends_in:id}: {note}", _ASK_EN),
    },
    send_words=SEND_WORDS,
)
NOTE_DONE: Final = Say(
    {
        # Done, the note is now on the ticket that ends in the digits ...
        "ar-SA": "تم، الملاحظة صارت على التذكرة اللي تنتهي بالأرقام {last_four:id}.",
        # tamma, wal-mulaahadha al-aan 'ala at-tadhkira allati tantahi bil-arqaam ...: the same,
        # in MSA
        "ar": "تم، والملاحظة الآن على التذكرة التي تنتهي بالأرقام {last_four:id}.",
        "en": "Done. The note is on your ticket ending {last_four:id}.",
    }
)
NOTE_SENDING: Final = Say(
    {
        "ar-SA": "أضيف الملاحظة الحين.",  # I'm adding the note now.
        "ar": "أضيف الملاحظة الآن.",  # udeefu al-mulaahadha al-aan: the same, in MSA
        "en": "I'm adding the note now.",
    }
)
NOTE_FAILED: Final = Say(
    {
        # Sorry, the ticket system refused the note, so it is not on the ticket.
        "ar-SA": "للأسف نظام التذاكر رفض الملاحظة، فما صارت على التذكرة.",
        # lil-asaf rafada nidhaamu at-tadhaakir al-mulaahadha, fa-hiya laysat 'ala at-tadhkira:
        # the same, in MSA
        "ar": "للأسف رفض نظام التذاكر الملاحظة، فهي ليست على التذكرة.",
        "en": "Unfortunately the ticket system refused the note, so it is not on the ticket.",
    }
)
NOTE_UNKNOWN: Final = Say(
    {
        # I could not make sure the note reached the ticket.
        "ar-SA": "ما قدرت أتأكد إن الملاحظة وصلت للتذكرة.",
        # lam atamakkan min at-ta'akkud min wusooli al-mulaahadha ila at-tadhkira: the same, in
        # MSA
        "ar": "لم أتمكن من التأكد من وصول الملاحظة إلى التذكرة.",
        "en": "I can't tell whether the note reached the ticket.",
    }
)
NOTE_DECLINED: Final = Say(
    {
        "ar-SA": "الملاحظة ما أرسلتها.",  # The note, I did not send it.
        "ar": "لم يتم إرسال الملاحظة.",  # lam yatimm irsaalu al-mulaahadha: the note was not sent
        "en": "I haven't sent the note.",
    }
)
NOTE_CLAIMS: Final = Claims(
    {
        "ar-SA": [
            "أضفت الملاحظة",  # I added the note
            "ضفت الملاحظة",
            "أضفت ملاحظة",
            "تمت إضافة الملاحظة",  # the note was added
            "انضافت الملاحظة",
        ],
        "en": [
            "I've added the note",
            "I have added the note",
            "I added the note",
            "I've added a note",
            "I added a note",
            "note added",
            "note has been added",
            "note was added",
        ],
    }
)

# hand_off
HANDOFF_READ_BACK: Final = ReadBack(
    {
        # I'll pass your request to the support team in a ticket, and with it what we said in
        # this call: ...
        "ar-SA": (
            "بحوّل طلبك لفريق الدعم في تذكرة، ومعها كلامنا في هالمكالمة: {summary}",
            _ASK_AR,
        ),
        # sa-uheelu talabaka ila fareeqi ad-da'm fi tadhkira, wa-ma'aha muhaadathatuna fi
        # hadhihi al-mukaalama: I will pass your request to the support team in a ticket, and
        # with it our conversation in this call: ...
        "ar": (
            "سأحيل طلبك إلى فريق الدعم في تذكرة، ومعها محادثتنا في هذه المكالمة: {summary}",
            _ASK_MSA,
        ),
        "en": (
            "I'll pass your request to the support team as a ticket, with what we said in this "
            "call: {summary}",
            _ASK_EN,
        ),
    },
    send_words=SEND_WORDS,
)
HANDOFF_DONE: Final = Say(
    {
        # Done, your request is with the support team, and the ticket's number is ...
        "ar-SA": (
            "تم، طلبك عند فريق الدعم، ورقم التذكرة {part_1:id}، {part_2:id}، {part_3:id}، "
            "{part_4:id}."
        ),
        # tamma, asbaha talabuka lada fareeqi ad-da'm, wa-raqmu at-tadhkira ...: the same, in
        # MSA
        "ar": (
            "تم، أصبح طلبك لدى فريق الدعم، ورقم التذكرة {part_1:id}، {part_2:id}، "
            "{part_3:id}، {part_4:id}."
        ),
        "en": (
            "Done. The support team has your request, as ticket number {part_1:id}, "
            "{part_2:id}, {part_3:id}, {part_4:id}."
        ),
    }
)
HANDOFF_SENDING: Final = Say(
    {
        "ar-SA": "أحوّل طلبك لفريق الدعم الحين.",  # I'm passing your request to support now.
        # uheelu talabaka ila fareeqi ad-da'm al-aan: the same, in MSA
        "ar": "أحيل طلبك إلى فريق الدعم الآن.",
        "en": "I'm passing your request to the support team now.",
    }
)
HANDOFF_FAILED: Final = Say(
    {
        # Sorry, the ticket system refused the request, so it did not reach the support team.
        "ar-SA": "للأسف نظام التذاكر رفض الطلب، فما وصل لفريق الدعم.",
        # lil-asaf rafada nidhaamu at-tadhaakir at-talab, fa-lam yasil ila fareeqi ad-da'm: the
        # same, in MSA
        "ar": "للأسف رفض نظام التذاكر الطلب، فلم يصل إلى فريق الدعم.",
        "en": "Unfortunately the ticket system refused it, so the support team did not get your "
        "request.",
    }
)
HANDOFF_UNKNOWN: Final = Say(
    {
        # I could not make sure your request reached the support team, so I have no number.
        "ar-SA": "ما قدرت أتأكد إن طلبك وصل لفريق الدعم، فما عندي رقم أعطيك إياه.",
        # lam atamakkan min at-ta'akkud min wusooli talabika ila fareeqi ad-da'm, fa-laysa
        # ladayya raqmun u'teeka iyyaah: the same, in MSA
        "ar": "لم أتمكن من التأكد من وصول طلبك إلى فريق الدعم، فليس لدي رقم أعطيك إياه.",
        "en": "I can't tell whether the support team got your request, so I have no number to "
        "give you.",
    }
)
HANDOFF_DECLINED: Final = Say(
    {
        "ar-SA": "طلبك ما أرسلته لفريق الدعم.",  # Your request, I did not send it to support.
        # lam yatimm irsaalu talabika ila fareeqi ad-da'm: your request was not sent to support
        "ar": "لم يتم إرسال طلبك إلى فريق الدعم.",
        "en": "I haven't sent your request to the support team.",
    }
)
HANDOFF_CLAIMS: Final = Claims(
    {
        "ar-SA": [
            "حولت طلبك",  # I passed your request on
            "حولت الطلب",
            "حولتك",  # I transferred you
            "تم تحويل طلبك",
            "تم تحويلك",
            "تم التحويل",
            "رفعت طلبك",  # I raised your request
            "وصلت طلبك",  # I delivered your request
            "صعدت طلبك",  # I escalated your request
        ],
        "en": [
            "I've passed",
            "I have passed",
            "I passed your request",
            "I've handed",
            "I have handed",
            "handed over",
            "I've transferred",
            "I have transferred",
            "transferred you",
            "I've escalated",
            "I have escalated",
            "escalated your request",
            "passed to the support team",
            "passed on to the support team",
        ],
    }
)
