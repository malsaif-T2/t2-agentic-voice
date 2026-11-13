"""What the Ole5 app's server and settings tests share: a made-up access code and join key, the
values the `environment` fixture (tests/ole5_voice/conftest.py) sets."""

from __future__ import annotations

from typing import Final

CODE: Final = "made-up-access-code-0123"  # 24 characters
KEY: Final = "a-made-up-join-key-of-forty-bytes-0123456"
