"""What the adapters of the providers measured beside Groq share (adapters/provider_http.py): a
client that trusts no variable and follows no redirect, the failure mapping, and the keyterms a
prompt holds."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from t2_agentic_voice.adapters.provider_http import (
    AnswerError,
    http_client,
    http_failure,
    keyterms,
)

from tests.leaks import holding, shown


def test_the_client_trusts_no_proxy_variable_and_follows_no_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proxy or CA variable would send the key and the audio elsewhere (TD-004's kind)."""
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    client = http_client(timeout_s=3.0, transport=None)
    try:
        assert (client.trust_env, client.follow_redirects) == (False, False)
        assert client.timeout == httpx.Timeout(3.0)
    finally:
        asyncio.run(client.aclose())


def test_an_unknown_failure_and_an_unreadable_answer_are_server_errors_named_by_class() -> None:
    secret = "made-up-secret-text-889"
    for error, name in ((ValueError(secret), "ValueError"), (AnswerError("no_job"), "no_job")):
        failed = http_failure("speechmatics", error)
        assert (failed.kind, failed.retryable) == ("server_error", False)
        assert failed.details == {"provider": "speechmatics", "error": name}
        assert holding(secret, shown(failed)) == []


@pytest.mark.parametrize(
    ("prompt", "terms"),
    [
        (None, ()),
        ("", ()),
        (" , ,", ()),
        ("VPN, Outlook, VPN,  كلمة المرور ", ("VPN", "Outlook", "كلمة المرور")),
        ("a, bbbb, cc, d", ("a", "cc")),  # most 2, longest 2
    ],
)
def test_the_keyterms_are_the_prompts_terms_each_once(
    prompt: str | None, terms: tuple[str, ...]
) -> None:
    most, longest = (2, 2) if prompt and prompt.startswith("a,") else (100, 50)
    assert keyterms(prompt, most=most, longest=longest) == terms
