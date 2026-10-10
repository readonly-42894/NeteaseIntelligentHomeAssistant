"""The 网易智造 integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NeteaseIntelligentApiClient
from .const import (
    CONF_TOKEN,
    CONF_TOKEN_ID,
    CONF_UA_INFO,
    DOMAIN,
    MANUFACTURER,
    NAME,
)
from .coordinator import (
    NeteaseIntelligentCoordinator,
    NeteaseIntelligentData,
    NeteaseIntelligentSweeperCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["vacuum", "sensor", "image"]


def _register_sweeper_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: NeteaseIntelligentCoordinator,
) -> None:
    """把家庭数据中的扫地机器人登记进设备注册表。

    设备标识优先用序列号 ``sn``，缺失时回退到 ``id``（equipId）；
    均缺失则跳过（无法唯一标识）。
    """
    device_registry = dr.async_get(hass)
    for equip in coordinator.sweeper_equips():
        identifier = equip.unique_identifier
        if not identifier:
            continue
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, identifier)},
            manufacturer=MANUFACTURER,
            model=equip.model or None,
            name=equip.alias or equip.name or NAME,
            suggested_area=equip.room_name or None,
        )


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """选项更新后重载集成，使新配置（如地图配色）立即生效。"""
    await hass.config_entries.async_reload(entry.entry_id)


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

    # 为每台扫地机建立独立的数据协调器（equipId 为空则只登记设备、不建实体）。
    sweeper_coordinators: dict[str, NeteaseIntelligentSweeperCoordinator] = {}
    for equip in coordinator.sweeper_equips():
        if not equip.id:
            continue
        sweeper_coordinator = NeteaseIntelligentSweeperCoordinator(
            hass, client, equip.id
        )
        try:
            await sweeper_coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady:
            _LOGGER.warning(
                "扫地机 %s 首次数据刷新失败，实体将保持不可用",
                equip.unique_identifier,
            )
        sweeper_coordinators[equip.id] = sweeper_coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = NeteaseIntelligentData(
        client=client,
        coordinator=coordinator,
        sweeper_coordinators=sweeper_coordinators,
    )

    # 登记扫地机器人设备；后续每次家庭数据刷新同步一次，覆盖新增/移除的扫地机。
    _register_sweeper_devices(hass, entry, coordinator)
    coordinator.async_add_listener(
        lambda: _register_sweeper_devices(hass, entry, coordinator)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok