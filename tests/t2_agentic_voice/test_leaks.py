"""tests/leaks.py, the shared check of what an error, a log line, an output or a warning may
show: it finds a value on every surface it names, so a test that relies on it is never blind to
one."""

from __future__ import annotations

import logging
import sys
import warnings

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import get_logger

from tests.leaks import holding, shown

VALUE = "made-up-value-0123"


def test_an_error_shows_its_text_repr_traceback_attributes_and_details() -> None:
    assert holding(VALUE, shown(ValueError(VALUE))) == ["text", "repr", "traceback"]
    error = ConfigurationError("fixed text", details={"setting": VALUE})
    assert holding(VALUE, shown(error)) == ["attributes", "details"]


def test_a_note_shows_in_the_traceback_and_the_attributes() -> None:
    error = ValueError("fixed text")
    error.add_note(VALUE)
    assert holding(VALUE, shown(error)) == ["traceback", "attributes"]


def test_a_cause_shows_and_a_suppressed_context_is_still_reached() -> None:
    caused = ValueError("fixed text")
    caused.__cause__ = KeyError(VALUE)
    assert holding(VALUE, shown(caused)) == ["traceback", "chain"]
    suppressed = ValueError("fixed text")  # as `raise ... from None` inside a handler leaves it
    suppressed.__context__, suppressed.__suppress_context__ = KeyError(VALUE), True
    assert holding(VALUE, shown(suppressed)) == ["chain"]  # Python's traceback hides it


def test_a_validation_errors_input_shows_in_its_errors_and_its_json() -> None:
    """Its text and repr leave the input out under `hide_input_in_errors`; FastAPI's own 422
    sends `errors()` to the client, input and all."""

    class Body(BaseModel):
        model_config = ConfigDict(strict=True, hide_input_in_errors=True)
        token: int

    with pytest.raises(ValidationError) as raised:
        Body.model_validate({"token": VALUE})
    assert holding(VALUE, shown(raised.value)) == ["errors", "errors json"]
    wrapped = ValueError("fixed text")  # as `raise ... from error` leaves it
    wrapped.__cause__ = raised.value
    assert holding(VALUE, shown(wrapped)) == ["chain"]


def test_a_log_record_and_each_output_show(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    logging.getLogger("some.library").warning("quoted %s", VALUE)
    assert holding(VALUE, shown(caplog=caplog)) == ["log records"]
    get_logger("t2_agentic_voice.tests").info("event", value=VALUE)  # a library line
    sys.stderr.write(VALUE)
    assert holding(VALUE, shown(capsys=capsys)) == ["stdout", "stderr"]
    assert shown(capsys=capsys) == {"stdout": "", "stderr": ""}  # read once, by `shown`


def test_a_library_lines_field_shows_in_the_log_records(caplog: pytest.LogCaptureFixture) -> None:
    """A field is in neither the record's message nor caplog's text: only in `record.fields`."""
    caplog.set_level(logging.WARNING)
    get_logger("t2_agentic_voice.tests").warning("event", value=VALUE)
    assert (caplog.records[0].getMessage(), VALUE in caplog.text) == ("event", False)
    assert holding(VALUE, shown(caplog=caplog)) == ["log records"]


def test_a_warning_shows(recwarn: pytest.WarningsRecorder) -> None:
    """As pydantic's serializer warnings quoted a refused value: under pytest a warning reaches
    neither stderr nor `capsys`, only the recorder."""
    warnings.warn(f"serialized {VALUE}", UserWarning, stacklevel=1)
    assert holding(VALUE, shown(recwarn=recwarn)) == ["warnings"]
    assert shown(recwarn=recwarn)["warnings"].startswith("UserWarning: ")
