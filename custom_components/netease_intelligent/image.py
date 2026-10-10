"""扫地机器人地图 image 平台。

每台扫地机生成一个 ``image`` 实体，展示由 ``getDeviceData.mapUrl`` 指向的
二进制地图包渲染出的 PNG：

- ``mapUrl`` 为 NOS 公开资源（无需认证 Cookie），由
  :meth:`NeteaseIntelligentApiClient.download_map_package` 下载；
- 解析（``map_parser``）与渲染（``map_render``）均为阻塞操作，放在 executor 中执行；
- ``mapUrl`` 变化时重新下载渲染，否则复用上一次结果；
- 配色由配置项 ``map_theme`` 决定（``light``/``dark``/``auto``，默认 ``light``）：
  ``auto`` 时读取 Home Assistant 前端主题偏好，深色主题下渲染深色地图。

图片刷新时间戳（``image_last_updated``）仅在协调器更新时推进（不在地图读取
方法内推进），符合 Home Assistant 对 ``image`` 实体的约定。
"""

from __future__ import annotations

import logging
from functools import partial

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import ApiError, NeteaseIntelligentApiClient
from .const import (
    CONF_MAP_THEME,
    DEFAULT_MAP_THEME,
    DOMAIN,
    MANUFACTURER,
    MAP_THEME_AUTO,
    MAP_THEME_DARK,
    NAME,
)
from .coordinator import (
    NeteaseIntelligentData,
    NeteaseIntelligentSweeperCoordinator,
)
from .map_parser import MapParseError, parse_map
from .map_render import render_map
from .models import Equip, SweeperDeviceData

_LOGGER = logging.getLogger(__name__)


async def _frontend_theme_is_dark(hass: HomeAssistant) -> bool:
    """判断 Home Assistant 前端当前是否处于深色主题。

    后端无法得知发起图片请求的浏览器主题，这里取一个合理的近似：
    优先读 owner（首个拥有者）用户在前端存储中的主题偏好
    （前端 ``saveFrontendUserData("theme", {dark})``，存于 ``frontend.user_data_<id>``）；
    读不到时回退到后端默认深色主题（``frontend.set_theme`` 服务设置）。
    任何异常都回退到浅色。
    """
    try:
        from homeassistant.components import frontend
        from homeassistant.components.frontend.storage import async_user_store

        users = await hass.auth.async_get_users()
        owner = next((user for user in users if user.is_owner), None)
        if owner is not None:
            store = await async_user_store(hass, owner.id)
            theme = (store.data or {}).get("theme")
            if isinstance(theme, dict) and "dark" in theme:
                return bool(theme["dark"])
        if hass.data.get(frontend.DATA_DEFAULT_DARK_THEME):
            return True
    except Exception:  # noqa: BLE001 - 任何读取失败都回退到浅色
        _LOGGER.debug("读取前端主题失败，地图回退到浅色", exc_info=True)
    return False


async def _resolve_map_dark(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """按配置项 ``map_theme`` 决定是否使用深色地图。"""
    theme = entry.options.get(CONF_MAP_THEME, DEFAULT_MAP_THEME)
    if theme == MAP_THEME_DARK:
        return True
    if theme == MAP_THEME_AUTO:
        return await _frontend_theme_is_dark(hass)
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 网易智造扫地机器人地图实体。"""
    data: NeteaseIntelligentData = hass.data[DOMAIN][entry.entry_id]
    entities: list[NeteaseIntelligentMapImage] = []
    for equip in data.coordinator.sweeper_equips():
        coordinator = data.sweeper_coordinators.get(equip.id)
        if coordinator is None:
            continue
        entities.append(
            NeteaseIntelligentMapImage(data.client, equip, coordinator, entry)
        )
    async_add_entities(entities)


class NeteaseIntelligentMapImage(
    CoordinatorEntity[NeteaseIntelligentSweeperCoordinator], ImageEntity
):
    """网易智造扫地机器人实时地图实体。"""

    _attr_has_entity_name = True
    _attr_translation_key = "map"
    _attr_content_type = "image/png"

    def __init__(
        self,
        client: NeteaseIntelligentApiClient,
        equip: Equip,
        coordinator: NeteaseIntelligentSweeperCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        # ImageEntity 需要 hass 初始化内部 HTTP 客户端与访问令牌。
        ImageEntity.__init__(self, coordinator.hass)
        self._client = client
        self._equip = equip
        self._entry = entry
        self._rendered_url: str | None = None
        self._rendered_image: bytes | None = None
        self._rendered_dark: bool | None = None

        self._attr_unique_id = f"{equip.unique_identifier}_map"
        self._attr_image_last_updated = dt_util.utcnow()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, equip.unique_identifier)},
            manufacturer=MANUFACTURER,
            model=equip.model or None,
            name=equip.alias or equip.name or NAME,
            suggested_area=equip.room_name or None,
        )

    @property
    def _data(self) -> SweeperDeviceData | None:
        """最近一次刷新的扫地机数据（失败时为 ``None``）。"""
        if not self.coordinator.last_update_success:
            return None
        return self.coordinator.data

    @callback
    def _handle_coordinator_update(self) -> None:
        """协调器更新时推进图片时间戳，触发前端重新拉取。"""
        self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """返回渲染好的地图 PNG；无地图（``mapUrl`` 为空）时返回 ``None``。"""
        data = self._data
        if data is None or not data.map_url:
            return None
        dark = await _resolve_map_dark(self.hass, self._entry)
        if (
            self._rendered_url == data.map_url
            and self._rendered_dark == dark
            and self._rendered_image is not None
        ):
            return self._rendered_image
        try:
            raw = await self._client.download_map_package(data.map_url)
            package = await self.hass.async_add_executor_job(parse_map, raw)
            image = await self.hass.async_add_executor_job(
                partial(render_map, package, dark=dark)
            )
        except (ApiError, MapParseError, ValueError, OSError) as err:
            _LOGGER.warning(
                "扫地机 %s 地图获取/渲染失败：%s", self._equip.unique_identifier, err
            )
            return None
        self._rendered_url = data.map_url
        self._rendered_image = image
        self._rendered_dark = dark
        return image
