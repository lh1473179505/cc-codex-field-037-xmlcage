"""Safe XML document builder. Not implemented in this snapshot."""

from __future__ import annotations

from typing import Any

from xmlcage.lex import Event


def build(
    events: list[Event],
    policy: dict[str, Any],
    dtd_dir: str | None,
) -> dict[str, Any]:
    raise NotImplementedError("build is not implemented in this snapshot")
