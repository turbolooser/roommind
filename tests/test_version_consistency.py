"""manifest.json and const.VERSION must never drift apart.

RoomMind raises a "restart required" repair issue when the two disagree, and no
restart clears it — the check compares the running const.VERSION against the
manifest on disk. This bit the fork twice: once in v1.7.4 (fixed in v1.7.5) and
again in v1.7.8.3, both times because a release bumped only the manifest.

A release checklist is not enough. This test is.
"""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.roommind.const import VERSION

_MANIFEST = Path(__file__).parent.parent / "custom_components" / "roommind" / "manifest.json"


def test_manifest_version_matches_const_version():
    manifest_version = json.loads(_MANIFEST.read_text())["version"]
    assert manifest_version == VERSION, (
        f"manifest.json says {manifest_version!r} but const.VERSION is {VERSION!r}. "
        "Bump both together, or RoomMind will show a permanent 'restart required' "
        "repair issue that no restart can clear."
    )


def test_version_is_a_plausible_release_string():
    """Catches a stray 'v' prefix or a trailing space before it ships."""
    parts = VERSION.split(".")
    assert 3 <= len(parts) <= 4, f"unexpected version shape: {VERSION!r}"
    assert all(p.isdigit() for p in parts), f"non-numeric component in {VERSION!r}"
