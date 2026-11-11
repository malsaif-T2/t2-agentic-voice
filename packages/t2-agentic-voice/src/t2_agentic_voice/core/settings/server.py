"""The `server` group: how calls are served (the design's 5.5, 11): the public address, the
pages allowed to call it, the ICE servers and the TURN secret, the dev page and the test
console's dev caller, and which peers' proxy headers are trusted."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from pydantic import Field, SecretStr, field_validator

from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.core.settings.base import (
    PREFIX,
    Group,
    read_secret_file,
    secret,
    setting_name,
    shared_secret,
    url,
)

# A TURN credential lasts at most a day (coturn's REST scheme: the secret signs an expiry).
MAX_TURN_TTL_S = 86_400
_ICE_SCHEMES = ("stun:", "turn:", "turns:")
# The port a browser leaves out of an origin, by scheme.
_DEFAULT_PORTS = {"http": 80, "https": 443}
# A host name's label as a browser writes it in an origin: lowercase ASCII letters, digits and
# hyphens (a name in another script in its xn-- form); and a last label a browser reads as a
# number, which makes the whole host an IPv4 address to it.
_LABEL = re.compile(r"[a-z0-9-]+")
_NUMBER = re.compile(r"[0-9]+|0x[0-9a-f]*")
_IPV6_TEXT = frozenset("0123456789abcdef:")
# The widest network a trusted proxy entry may name, by IP version: a wider one trusts nearly
# every peer's X-Forwarded-For, as "*" does.
_WIDEST = {4: 8, 6: 32}
# The IPv6 ranges that carry IPv4 addresses, each with the bit its IPv4 address starts at: an
# entry that overlaps one is no wider than an IPv4 /8 past that bit, its widest. They are an
# IPv4 peer of a dual-stack socket, IPv4-mapped; SIIT's translated range (RFC 2765); NAT64's
# well-known prefix (RFC 6052) and its local-use one (RFC 8215), held to /104 whatever layout
# its operator gives it; the IPv4-compatible range; and 6to4's (RFC 3056).
_EMBEDDED = tuple(
    (ipaddress.IPv6Network(network), start + _WIDEST[4])
    for network, start in (
        ("::ffff:0:0/96", 96),
        ("::ffff:0:0:0/96", 96),
        ("64:ff9b::/96", 96),
        ("64:ff9b:1::/48", 96),
        ("::/96", 96),
        ("2002::/16", 16),
    )
)
# The rule the refusals and the setting's description state, whole.
_PROXY_RULE = (
    "an entry is no wider than /8 for IPv4 or /32 for IPv6, and no wider than /104 where it "
    "overlaps ::ffff:0:0/96, ::ffff:0:0:0/96, 64:ff9b::/96, 64:ff9b:1::/48 or ::/96, or /24 "
    "where it overlaps 2002::/16, the IPv6 ranges that carry IPv4 addresses"
)
Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class ServerSettings(Group):
    """Serving: the backend's address, the pages that may call it, how media finds a path, and
    the dev page with the test console's dev caller."""

    public_url: str | None = Field(
        default=None,
        description="The address callers reach the backend at, such as https://voice.example.",
    )
    allowed_origins: tuple[str, ...] = Field(
        default=(),
        description=(
            "The pages allowed to call the backend from a browser, as a JSON list of origins "
            "(scheme, host and port only, written as a browser sends them: lowercase; a host "
            "name of letters, digits and hyphens, in its xn-- form, or an IP address in its "
            'shortest form; no default port), such as ["https://www.example.com"]. Unset: '
            "none."
        ),
    )
    ice_servers: tuple[str, ...] = Field(
        default=(),
        description=(
            "The STUN and TURN servers a call is given, as a JSON list of stun:, turn: or "
            "turns: URLs with no credentials (TURN's are minted per call from turn_secret)."
        ),
    )
    turn_secret: SecretStr | None = Field(
        default=None,
        description=(
            "The secret shared with the TURN server, which signs each call's credentials: at "
            "least 32 bytes. Or give turn_secret_file instead."
        ),
    )
    turn_secret_file: Path | None = Field(
        default=None,
        description="Or the full path of a file that holds only the TURN secret.",
    )
    turn_ttl_s: int = Field(
        default=3600,
        gt=0,
        le=MAX_TURN_TTL_S,
        description="How long each call's TURN credentials last, at most 86400 (a day).",
    )
    dev_page: bool = Field(
        default=False,
        description="Whether the router serves its /dev page, to loopback clients; dev only.",
    )
    dev_caller: Caller | None = Field(
        default=None,
        description=(
            "The caller the test console's Start makes a signed join token for, under env dev "
            'with the dev page on: a JSON object, such as {"subject": "owner", "attributes": '
            '{"customer_email": "demo@example.com"}}, read as the library\'s Caller. An app '
            "usually sets it in code. Unset: the console makes none and joins as dev."
        ),
    )
    forwarded_allow_ips: tuple[str, ...] = Field(
        default=(),
        description=(
            "The proxies whose X-Forwarded-For headers are trusted, as a JSON list of IP "
            'addresses or networks, such as ["127.0.0.1"], a network by its own address '
            f'(10.0.0.0/24): {_PROXY_RULE}; "*" is refused. Unset: none.'
        ),
    )

    @field_validator("public_url")
    @classmethod
    def _public(cls, value: str | None) -> str | None:
        return None if value is None else url(value, frozenset({"http", "https"}))

    @field_validator("allowed_origins")
    @classmethod
    def _origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, origin in enumerate(value):
            try:
                parts = urlsplit(url(origin, frozenset({"http", "https"})))
            except ValueError:
                parts = None
            if parts is None or parts.path or parts.query or parts.fragment:
                raise ValueError(f"origin {index} must be a scheme, a host and a port only")
            if not _as_sent(origin, parts):
                raise ValueError(
                    f"origin {index} is not written as a browser sends it, and CORS compares "
                    "the two as text; write the scheme in lowercase; the host as a lowercase "
                    "name of letters, digits and hyphens between dots (a name in another "
                    "script in its xn-- form), an IPv4 address as four numbers from 0 to 255, "
                    "or an IPv6 address in brackets, its zeros shortened as a browser does "
                    "(::1); and no default port (:443 for https, :80 for http)"
                )
        return value

    @field_validator("ice_servers")
    @classmethod
    def _ice(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, server in enumerate(value):
            host = server.partition(":")[2]
            if not server.startswith(_ICE_SCHEMES) or not host or "@" in host or not _plain(host):
                raise ValueError(
                    f"server {index} must be a stun:, turn: or turns: URL with no credentials"
                )
        return value

    @field_validator("turn_secret")
    @classmethod
    def _long_enough(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None  # a blank value counts as unset
        return shared_secret(value.get_secret_value().strip())

    @field_validator("forwarded_allow_ips")
    @classmethod
    def _proxies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, entry in enumerate(value):
            if entry.strip() == "*":
                raise ValueError(
                    "must not hold *, which trusts every peer's X-Forwarded-For; name each proxy"
                )
            network = _network(entry)
            if network is None:
                raise ValueError(f"entry {index} is not an IP address or network")
            if isinstance(network, str):
                raise ValueError(f"entry {index} {network}")
            if (wide := _too_wide(network)) is not None:
                raise ValueError(f"entry {index} {wide}, as * does; name each proxy: {_PROXY_RULE}")
        return value

    def resolved_turn_secret(self, prefix: str = PREFIX) -> SecretStr | None:
        """The TURN secret: `turn_secret` when set, otherwise the contents of `turn_secret_file`;
        None when neither holds one. A file that cannot be read, or a secret shorter than 32
        bytes or holding a character no key holds, raises ConfigurationError naming the
        setting it came from under `prefix`, never its value or the file's path."""
        if self.turn_secret is not None:
            return self.turn_secret
        if self.turn_secret_file is None:
            return None
        setting = setting_name("server", "turn_secret_file", prefix=prefix)
        text = read_secret_file(self.turn_secret_file, setting)
        return None if text is None else secret(text, setting)


def _as_sent(origin: str, parts: SplitResult) -> bool:
    """Whether `origin` reads as a browser's `Origin` header does, which Starlette's CORS
    compares as text: the scheme and the host in lowercase, the host as a browser writes it,
    and no default port."""
    host = parts.hostname or ""  # `url` checked that there is one; urllib lowercases it
    port = "" if parts.port in (None, _DEFAULT_PORTS[parts.scheme]) else f":{parts.port}"
    netloc = f"[{host}]" if ":" in host else host
    return origin == f"{parts.scheme}://{netloc}{port}" and _host_as_sent(host)


def _host_as_sent(host: str) -> bool:
    """Whether `host` is one a browser's `Origin` can hold as written: a name of lowercase
    letters, digits and hyphens between dots; an IPv4 address as four numbers from 0 to 255, as
    a browser reads any host whose last label is a number (127.1, 0x7f.0.0.1 and 010.0.0.1 are
    other addresses to it); or an IPv6 address as a browser writes one. A percent-escape, a
    backslash, a control character or any other a browser would decode, cut at or refuse is
    none of these, so CORS would never find such an origin in the header."""
    if ":" in host:
        return _ipv6_as_sent(host)
    labels = host.split(".")
    if _NUMBER.fullmatch(labels[-1]):
        try:
            return str(ipaddress.IPv4Address(host)) == host
        except ValueError:
            return False
    return all(_LABEL.fullmatch(label) for label in labels)


def _ipv6_as_sent(host: str) -> bool:
    """Whether `host` is an IPv6 address as a browser writes it in an origin (the WHATWG URL
    standard's serializer): its eight pieces in lowercase hexadecimal with no leading zero, and
    the first longest run of two or more zero pieces written `::`; never a zone (`%eth0`) or a
    dotted IPv4 part, which Python's own text gives an IPv4-mapped address."""
    if not set(host) <= _IPV6_TEXT:
        return False
    number = int(ipaddress.IPv6Address(host))  # urllib refused a bracketed host that is none
    pieces = [f"{number >> (16 * (7 - index)) & 0xFFFF:x}" for index in range(8)]
    longest, run = (0, 0), 0  # the first longest run of zero pieces: its length and start
    for index, piece in enumerate(pieces):
        run = run + 1 if piece == "0" else 0
        if run > longest[0]:
            longest = (run, index - run + 1)
    length, start = longest
    if length < 2:
        return host == ":".join(pieces)
    return host == f"{':'.join(pieces[:start])}::{':'.join(pieces[start + length :])}"


def _network(text: str) -> Network | str | None:
    """`text` as the network uvicorn reads it (strictly, as it does); what is wrong with it, in
    fixed words, when it holds host bits, which uvicorn would keep as a name that matches no
    peer; None when it is no IP address or network. ipaddress's own error repeats the value, so
    it is caught here and in no chain."""
    try:
        return ipaddress.ip_network(text)
    except ValueError:
        pass
    try:
        ipaddress.ip_network(text, strict=False)
    except ValueError:
        return None
    return (
        "has host bits set, so uvicorn would match no peer with it; give the network's own "
        "address, such as 10.0.0.0/24 for 10.0.0.5/24"
    )


def _too_wide(network: Network) -> str | None:
    """Why `network` is too wide to trust, in fixed words: wider than its version's bound, or
    holding more of an IPv6 range that carries IPv4 addresses than IPv4's bound allows; None
    when it is neither."""
    if network.prefixlen < _WIDEST[network.version]:
        return (
            "is wider than /8 for IPv4 or /32 for IPv6, which trusts nearly every peer's "
            "X-Forwarded-For"
        )
    if isinstance(network, ipaddress.IPv6Network) and any(
        network.prefixlen < widest and network.overlaps(carrier) for carrier, widest in _EMBEDDED
    ):
        return (
            "holds more than an IPv4 /8 of an IPv6 range that carries IPv4 addresses, which "
            "trusts nearly every IPv4 peer's X-Forwarded-For"
        )
    return None


def _plain(text: str) -> bool:
    """Whether `text` holds only printable ASCII with no space."""
    return text.isascii() and text.isprintable() and not any(c.isspace() for c in text)
