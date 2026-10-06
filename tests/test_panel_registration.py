"""Tests for the sidebar panel registration.

Fork change: the panel's js_url carries a ?v=<VERSION> cache buster. Without it
the URL is byte-identical across releases, so the Home Assistant Companion app's
WebView keeps serving its cached bundle and new panel features stay invisible
until the user clears the app cache by hand. Pinned here because it is a single
easily-lost line that only shows up as "the app does not update" in the field.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.roommind import _async_register_panel
from custom_components.roommind.const import DOMAIN, VERSION


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    hass.http.async_register_static_paths = AsyncMock()
    return hass


async def _register(hass) -> dict:
    """Run the registration and return the config passed to the panel helper."""
    with (
        patch("custom_components.roommind.async_register_built_in_panel") as reg,
        patch("custom_components.roommind.Path") as path_cls,
    ):
        path_cls.return_value.parent.__truediv__.return_value.__truediv__.return_value.exists.return_value = True
        await _async_register_panel(hass)
        assert reg.called, "panel was not registered"
        return reg.call_args.kwargs["config"]["_panel_custom"]


@pytest.mark.asyncio
async def test_panel_js_url_carries_version_cache_buster():
    """js_url ends with ?v=<current version> so an update invalidates the cache."""
    panel = await _register(_hass())
    assert panel["js_url"] == f"/roommind/roommind-panel.js?v={VERSION}"


@pytest.mark.asyncio
async def test_panel_js_url_changes_between_versions():
    """Two different versions must produce two different URLs.

    The whole point: an unchanged URL is what let the WebView keep its stale copy.
    """
    panel_a = await _register(_hass())
    with patch("custom_components.roommind.VERSION", "9.9.9.9"):
        panel_b = await _register(_hass())
    assert panel_a["js_url"] != panel_b["js_url"]
    assert panel_b["js_url"].endswith("?v=9.9.9.9")


@pytest.mark.asyncio
async def test_panel_static_path_stays_unversioned():
    """The served file path keeps no query string — only the panel URL carries it."""
    hass = _hass()
    await _register(hass)
    static_cfg = hass.http.async_register_static_paths.call_args[0][0][0]
    assert static_cfg.url_path == "/roommind/roommind-panel.js"


@pytest.mark.asyncio
async def test_panel_registered_only_once():
    """A second call is a no-op, so the registration stays idempotent."""
    hass = _hass()
    await _register(hass)
    assert hass.data[DOMAIN]["panel_registered"] is True

    with patch("custom_components.roommind.async_register_built_in_panel") as reg:
        await _async_register_panel(hass)
        assert not reg.called
