"""`@action`'s declaration (the design's 4.4 and 6.4; plan 007): what it reads of the
function, the schema the talker sees, each boundary check, a ConfigurationError naming the
field, with a FIX line, never a value, and the order its texts are read in, an MSA text first
for `ar`. What an action does when it runs is tested with the action runner."""

from __future__ import annotations

from typing import Annotated, Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from t2_agentic_voice.actions.action import (
    Action,
    ActionContext,
    HeardConsent,
    action,
)
from t2_agentic_voice.actions.action_checks import named_like_consent
from t2_agentic_voice.actions.tools import CallContext, RecordedAction, tool
from t2_agentic_voice.core.conversation import ConversationLine
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say, Spoken, read_in
from t2_agentic_voice.domain.declaration import Language, VoiceAgent

ENGLISH = Language.english(greeting="Hi! How can I help?")
SAUDI = Language.saudi_arabic(greeting="هلا! وش أقدر أساعدك فيه؟")

Category = Annotated[
    Literal["hardware", "software"],
    Spoken({"hardware": {"ar": "أجهزة"}, "software": {"ar": "برامج"}}),
]


class OpenRequest(BaseModel):
    category: Category
    summary: Annotated[str, Field(max_length=200)]


class RequestOpened(BaseModel):
    id: str


READ_BACK = ReadBack(
    {
        "ar": ("بفتح طلب {category}: {summary}.", "أرسله؟"),
        "en": ("A {category}: {summary}.", "Send?"),
    },
)
DONE = Say({"ar": "تم، رقم الطلب {id:id}.", "en": "Done, number {id:id}."})
CLAIMS = Claims({"ar": ["فتحت الطلب"], "en": ["I've opened"]})


def _an_action(**changes: Any) -> Action:
    fields: dict[str, Any] = {
        "description": "Open a made-up request.",
        "read_back": READ_BACK,
        "done": DONE,
        "claims": CLAIMS,
    }

    @action(**fields | changes)
    async def open_request(ctx: ActionContext, draft: OpenRequest) -> RequestOpened:
        return RequestOpened(id=ctx.request_id)

    return open_request


def test_an_action_is_read_from_its_functions_signature() -> None:
    made = _an_action()
    assert isinstance(made, Action) and made.name == "open_request"
    assert made.draft is OpenRequest and made.result is RequestOpened
    assert (made.max_per_call, made.timeout_s, made.progress) == (1, 20.0, None)
    assert made.read_back.show_draft is False and made.read_back.max_attempts == 2
    assert made.finder is None and made.validate is None


def test_the_talker_sees_the_drafts_schema_and_nothing_more() -> None:
    schema = _an_action().tool_schema()
    assert schema.name == "open_request"
    parameters: Any = schema.parameters
    assert set(parameters["properties"]) == {"category", "summary"}
    assert parameters["additionalProperties"] is False
    assert "title" not in parameters


def test_a_key_the_draft_does_not_hold_is_refused_at_parsing() -> None:
    made = _an_action()
    valid = {"category": "software", "summary": "made up"}
    assert isinstance(made.parameters.model_validate(valid), OpenRequest)
    with pytest.raises(ValidationError):
        made.parameters.model_validate({**valid, "confirmed": True})


class _Inner(BaseModel):
    caller_said_yes: bool


class _TopLevel(BaseModel):
    confirmed: bool = False


class _Nested(BaseModel):
    inner: _Inner


class _Aliased(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    agreed_to: str = Field(alias="userConsent")


async def _with_top(draft: _TopLevel) -> RequestOpened:
    return RequestOpened(id="1")


async def _with_nested(draft: _Nested) -> RequestOpened:
    return RequestOpened(id="1")


async def _with_alias(draft: _Aliased) -> RequestOpened:
    return RequestOpened(id="1")


@pytest.mark.parametrize(
    "function", [_with_top, _with_nested, _with_alias], ids=["top level", "nested", "aliased"]
)
def test_a_field_named_like_consent_is_refused_at_any_depth(function: Any) -> None:
    with pytest.raises(ConfigurationError, match="named like the caller's consent") as caught:
        action(description="x", read_back=READ_BACK, done=DONE, claims=CLAIMS)(function)
    assert caught.value.details["field"] == "draft"
    assert "FIX:" in caught.value.message


@pytest.mark.parametrize(
    "name",
    [
        "confirmed",
        "user_confirmed",
        "isConfirmed",
        "consent",
        "approved_by",
        "authorized",
        "said_yes",
    ],
)
def test_names_that_read_as_consent(name: str) -> None:
    assert named_like_consent(name) is True


@pytest.mark.parametrize("name", ["summary", "agreement_id", "yesterday", "asset_tag", "category"])
def test_names_that_do_not_read_as_consent(name: str) -> None:
    assert named_like_consent(name) is False


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"read_back": ReadBack({"en": ("{missing}", "Send?")})}, "read_back"),
        ({"done": Say(en="{not_a_result}")}, "done"),
        ({"failed": Say(en="{not_a_field}")}, "failed"),
        ({"sending": Say(en="{not_a_field}")}, "sending"),
        ({"sending": Say(en="{id}")}, "sending"),
        ({"max_per_call": 0}, "max_per_call"),
        ({"timeout_s": 0}, "max_per_call"),
        ({"name": "has spaces"}, "name"),
        ({"description": "   "}, "description"),
    ],
    ids=[
        "read_back",
        "done",
        "failed",
        "sending",
        "sending names the result",
        "cap",
        "timeout",
        "name",
        "description",
    ],
)
def test_a_field_it_cannot_run_with_is_a_configuration_error(
    changes: dict[str, Any], field: str
) -> None:
    with pytest.raises(ConfigurationError) as caught:
        _an_action(**changes)
    assert caught.value.details["field"] == field and "FIX:" in caught.value.message


SENDING = Say({"ar": "لحظة، أفتح لك طلب {category}.", "en": "One moment, opening it."})


def test_an_action_takes_its_own_sending_line_or_leaves_it_to_the_library() -> None:
    """The line said while the write runs (the owner's ruling, plan 007): the action's own, from
    the draft's fields, a text each of the agent's languages must cover as the outcome lines'
    are; or None, for the library's."""
    plain = _an_action()
    assert plain.sending is None and "sending" not in plain.texts
    made = _an_action(sending=SENDING)
    assert made.sending is SENDING and made.texts["sending"] is SENDING


def test_a_sending_line_short_of_a_language_the_agent_speaks_is_refused() -> None:
    short = _an_action(sending=Say(en="One moment, opening it."))
    with pytest.raises(ConfigurationError, match="no text in a language") as caught:
        VoiceAgent(name="branch-helper", languages=[ENGLISH, SAUDI], tools=[short])
    assert caught.value.details["field"] == "tools" and "FIX:" in caught.value.message
    assert VoiceAgent(name="english-helper", languages=[ENGLISH], tools=[short]).tools == (short,)


class _NoLabels(BaseModel):
    kind: Literal["a", "b"]


class _SomeLabels(BaseModel):
    kind: Annotated[Literal["a", "b"], Spoken({"a": {"en": "A"}})]


class _Labelled(BaseModel):
    kind: Annotated[Literal["a", "b"], Spoken({"a": {"en": "A"}, "b": {"en": "B"}})]


async def _plain_kind(draft: _NoLabels) -> RequestOpened:
    return RequestOpened(id="1")


async def _some_kind(draft: _SomeLabels) -> RequestOpened:
    return RequestOpened(id="1")


async def _labelled_kind(draft: _Labelled) -> RequestOpened:
    return RequestOpened(id="1")


def test_a_fixed_value_read_back_needs_a_label_for_every_value() -> None:
    read_back = ReadBack({"en": ("{kind}", "Send?")})
    declare = action(description="x", read_back=read_back, done=DONE, claims=CLAIMS)
    for function in (_plain_kind, _some_kind):
        with pytest.raises(ConfigurationError, match="no label for each value"):
            declare(function)
    assert declare(_labelled_kind).draft is _Labelled


def test_a_function_it_cannot_read_is_refused() -> None:
    declare = action(description="x", read_back=READ_BACK, done=DONE, claims=CLAIMS)

    async def no_draft(ctx: ActionContext) -> RequestOpened:
        return RequestOpened(id="1")

    async def not_a_model(draft: dict[str, str]) -> RequestOpened:
        return RequestOpened(id="1")

    async def bad_return(draft: OpenRequest) -> dict[str, str]:
        return {}

    async def extra(draft: OpenRequest, other: str) -> RequestOpened:
        return RequestOpened(id="1")

    for function in (no_draft, not_a_model, bad_return, extra):
        with pytest.raises(ConfigurationError) as caught:
            declare(function)
        assert "FIX:" in caught.value.message


def test_lookup_is_registered_once_and_a_test_may_replace_the_functions() -> None:
    made = _an_action()

    @made.lookup
    async def find(ctx: ActionContext, request_id: str) -> RequestOpened | None:
        return None

    assert made.finder is find
    with pytest.raises(ConfigurationError, match="one lookup"):
        made.lookup(find)

    async def other(ctx: ActionContext, draft: OpenRequest) -> RequestOpened:
        return RequestOpened(id="9")

    replaced = made.replaced(execute=other)
    assert replaced.execute is other and replaced.finder is find and made.execute is not other


def test_a_template_key_serves_its_tag_then_its_primary_language() -> None:
    both = Say({"ar": "shared", "en": "english"})
    assert both.for_language("ar-SA") == "shared" and both.for_language("ar") == "shared"
    assert both.covers("ar-SA") and both.covers("en")
    saudi_only = Say({"ar-SA": "saudi"})
    assert saudi_only.covers("ar-SA") and not saudi_only.covers("ar")
    with_both = Say({"ar": "msa", "ar-SA": "saudi"})
    assert with_both.for_language("ar-SA") == "saudi" and with_both.for_language("ar") == "msa"
    assert Say(ar_SA="s", en="e").templates["ar-SA"] == "s"


def test_a_text_read_in_ar_is_its_msa_one_else_its_saudi_one_which_covers_no_msa() -> None:
    """A reply read in `ar` (agent/language.py's `wording`, an MSA caller's) says the `ar`
    text, and the `ar-SA` one when there is none; a label likewise. The declaration's
    `covers` stays its own: an `ar-SA` text never covers `ar`."""
    assert read_in("ar") == ("ar", "ar-SA") and read_in("ar-SA") == ("ar-SA", "ar")
    assert read_in("en") == ("en",)
    saudi = Say({"ar-SA": "saudi", "en": "english"})
    assert saudi.for_language("ar") == "saudi" and not saudi.covers("ar")
    pairs = ReadBack({"ar-SA": ("s {a}", "q?"), "ar": ("m {a}", "mq?")})
    assert pairs.for_language("ar") == ("m {a}", "mq?")
    assert pairs.for_language("ar-SA") == ("s {a}", "q?")
    assert ReadBack({"ar-SA": ("s {a}", "q?")}).for_language("ar") == ("s {a}", "q?")
    assert Claims({"ar-SA": ["saudi claim"]}).for_language("ar") == ("saudi claim",)
    labels = Spoken({"a": {"ar-SA": "سعودي", "ar": "فصيح"}, "b": {"ar-SA": "سعودي"}})
    assert labels.label("a", "ar") == "فصيح" and labels.label("b", "ar") == "سعودي"
    assert labels.label("a", "ar-SA") == "سعودي" and labels.label("b", "en") is None
    with pytest.raises(KeyError):
        Say({"en": "english"}).for_language("ar")


@pytest.mark.parametrize(
    "build",
    [
        lambda: Say({}),
        lambda: Say({"fr": "bonjour"}),
        lambda: Say({"en": "a brace {"}),
        lambda: Say({"en": "{a.b}"}),
        lambda: Say({"en": "{a!r}"}),
        lambda: Say({"en": "{a:>10}"}),
        lambda: Say({"en": "two\nlines"}),
        lambda: ReadBack({"en": ("only a summary",)}),
        lambda: ReadBack({"en": "one string"}),
        lambda: ReadBack({"en": ("s", "q")}, max_attempts=0),
        lambda: ReadBack({"en": ("s", "q")}, max_attempts=True),
        lambda: ReadBack("not a map"),  # type: ignore[arg-type]
        lambda: Say("not a map"),  # type: ignore[arg-type]
        lambda: Claims("not a map"),  # type: ignore[arg-type]
        lambda: Spoken({"a": "not a map"}),  # type: ignore[dict-item]
        lambda: ReadBack({"en": ("s", "q")}, send_words={"fr": ["x"]}),
        lambda: ReadBack({"en": ("s", "q")}, send_words={"en": "x"}),
        lambda: Claims({"en": []}),
        lambda: Claims({"en": "one phrase"}),
        lambda: Spoken({}),
    ],
)
def test_a_text_it_cannot_say_is_a_configuration_error_with_a_fix(build: Any) -> None:
    with pytest.raises(ConfigurationError) as caught:
        build()
    assert "FIX:" in caught.value.message


def test_a_read_back_is_a_summary_and_a_closing_question_apart() -> None:
    made = ReadBack({"ar": ("الملخص {a}", "أرسله {b}؟")}, send_words={"ar": ["افتحه"]})
    assert made.for_language("ar-SA") == ("الملخص {a}", "أرسله {b}؟")
    assert made.placeholders == {"a", "b"} and made.send_words["ar"] == ("افتحه",)
    assert made.show_draft is False


def test_a_spoken_label_is_read_by_tag_then_primary_language() -> None:
    labels = Spoken({"a": {"ar": "عربي", "en": "A"}, "b": {"en": "B"}})
    assert labels.label("a", "ar-SA") == "عربي" and labels.label("b", "en") == "B"
    assert labels.label("b", "ar-SA") is None and labels.label("c", "en") is None


def test_an_action_context_is_a_call_context_with_the_consent_and_the_request_id() -> None:
    ctx = ActionContext(
        caller=Caller(subject="made-up"),
        call_id="c-1",
        language="en",
        request_id="r-1",
        consent=HeardConsent(words="yes send it", source="speech_to_text", speech_at=3.0),
        conversation=(ConversationLine(speaker="caller", text="made up"),),
    )
    assert isinstance(ctx, CallContext) and ctx.record == ()
    with pytest.raises(ValidationError):
        ctx.request_id = "other"  # type: ignore[misc]
    seen = RecordedAction(action="open_request", request_id="r-1", result={"id": "1"})
    assert CallContext(
        caller=Caller(subject="m"), call_id="c", language="en", record=(seen,)
    ).record == (seen,)


def test_a_tool_declares_what_it_reports_on() -> None:
    @tool(description="Say the status of a made-up request.", reports_on=["open_request"])
    async def status() -> str:
        return "open"

    assert status.reports_on == ("open_request",)

    async def plain() -> str:
        return "x"

    with pytest.raises(ConfigurationError) as caught:
        tool(description="x", reports_on=["not a name"])(plain)
    assert caught.value.details["field"] == "reports_on" and "FIX:" in caught.value.message
    with pytest.raises(ConfigurationError):
        tool(description="x", reports_on="open_request")(plain)
