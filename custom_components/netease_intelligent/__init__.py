"""The 网易智造 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NeteaseIntelligentApiClient
from .const import CONF_TOKEN, CONF_TOKEN_ID, CONF_UA_INFO, DOMAIN
from .coordinator import NeteaseIntelligentCoordinator

PLATFORMS: list[str] = []


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 网易智造 from a config entry."""
    client = NeteaseIntelligentApiClient(
        async_get_clientsession(hass),
        token=entry.data[CONF_TOKEN],
        token_id=entry.data[CONF_TOKEN_ID],
        ua_info=entry.data.get(CONF_UA_INFO, ""),
    )
    coordinator = NeteaseIntelligentCoordinator(hass, client)
    # 首次刷新即校验凭据；失败会抛 ConfigEntryNotReady 由 HA 自动重试。
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
