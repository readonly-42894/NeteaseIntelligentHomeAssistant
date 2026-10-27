"""扫地机器人地图 image 平台。

每台扫地机生成一个 ``image`` 实体，展示由 ``getDeviceData.mapUrl`` 指向的
二进制地图包渲染出的 PNG：

- ``mapUrl`` 为 NOS 公开资源（无需认证 Cookie），由
  :meth:`NeteaseIntelligentApiClient.download_map_package` 下载；
- 解析（``map_parser``）与渲染（``map_render``）均为阻塞操作，放在 executor 中执行；
- ``mapUrl`` 变化、或收到 subtype 2（地图）推送（``coordinator.map_revision`` 自增）
  时重新下载渲染，否则复用上一次结果；``mapUrl`` 常为固定 URL、服务端在其上覆盖
  写入新内容，故不能只按 URL 相等判定缓存；
- 清扫中的实时轨迹由 subtype 3 推送（``SweeperDeviceData.map_history``）增量提供，
  经 :func:`map_parser.apply_trajectory` 标进栅格后重渲染（与官方 App 一致）；累计
  轨迹点，同 URL 刷新时经 :func:`map_parser.trim_baked_history` 裁掉服务端已烘焙的
  点再重放，仅 ``mapUrl`` 变化才视为新地图并清空累计；
- 配色由配置项 ``map_theme`` 决定（``light``/``dark``，默认 ``light``）；整幅地图的
  朝向由配置项 ``map_rotation`` 决定（``0``/``90``/``180``/``270`` 逆时针，默认 ``0``）。

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
    CONF_MAP_ROTATION,
    CONF_MAP_THEME,
    DEFAULT_MAP_ROTATION,
    DEFAULT_MAP_THEME,
    DOMAIN,
    MANUFACTURER,
    MAP_THEME_DARK,
    NAME,
    map_rotation_degrees,
)
from .coordinator import (
    NeteaseIntelligentData,
    NeteaseIntelligentSweeperCoordinator,
)
from .map_parser import (
    MapPackage,
    MapParseError,
    TrajectoryPoint,
    apply_trajectory,
    parse_map,
    parse_trajectory,
    trim_baked_history,
)
from .map_render import render_map
from .models import Equip, SweeperDeviceData

_LOGGER = logging.getLogger(__name__)


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
        self._base_package: MapPackage | None = None
        self._package: MapPackage | None = None
        # 自最近一次地图基准（URL 变化）以来累计的轨迹点。
        self._history_points: list[TrajectoryPoint] = []
        self._rendered_url: str | None = None
        self._rendered_revision: int | None = None
        self._applied_history: tuple[int, ...] | None = None
        self._rendered_image: bytes | None = None
        self._rendered_dark: bool | None = None
        self._rendered_rotation: int | None = None

        self._attr_unique_id = f"{equip.unique_identifier}_map"
        self._attr_image_last_updated = dt_util.utcnow()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, equip.unique_identifier)},
            manufacturer=MANUFACTURER,
            model=equip.sweeper_model,
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
        dark = (
            self._entry.options.get(CONF_MAP_THEME, DEFAULT_MAP_THEME)
            == MAP_THEME_DARK
        )
        rotation = map_rotation_degrees(
            self._entry.options.get(CONF_MAP_ROTATION, DEFAULT_MAP_ROTATION)
        )
        uid = self._equip.unique_identifier
        revision = self.coordinator.map_revision
        _LOGGER.debug(
            "扫地机 %s 地图请求：map_url=%s revision=%s 轨迹长=%s dark=%s rotation=%s",
            uid,
            data.map_url,
            revision,
            len(data.map_history) if data.map_history else 0,
            dark,
            rotation,
        )

        if (
            self._base_package is None
            or self._rendered_url != data.map_url
            or self._rendered_revision != revision
        ):
            # 新地图（URL 变化）或 subtype 2 推送刷新：重新下载解析整包。服务端会
            # 以同一 mapUrl 覆盖写入新内容（包内 history 已烘焙最新轨迹与位姿），
            # 故每次刷新都以下载到的包为基准。
            try:
                raw = await self._client.download_map_package(data.map_url)
                base = await self.hass.async_add_executor_job(parse_map, raw)
            except (ApiError, MapParseError, ValueError, OSError) as err:
                _LOGGER.warning("扫地机 %s 地图获取/解析失败：%s", uid, err)
                return None
            if self._rendered_url != data.map_url:
                # URL 变化 = 新地图：累计轨迹作废。
                self._history_points = []
            elif self._history_points:
                # 同 URL 刷新：裁掉服务端已烘焙的点，保留更新的点重放。
                self._history_points = trim_baked_history(
                    self._history_points, base
                )
            self._base_package = base
            self._package = await self.hass.async_add_executor_job(
                apply_trajectory, base, self._history_points
            )
            self._rendered_url = data.map_url
            self._rendered_revision = revision
            self._rendered_image = None

        if data.map_history is not None and data.map_history != self._applied_history:
            # subtype 3 推送的新轨迹：增量标进栅格并强制重渲染。
            try:
                points = await self.hass.async_add_executor_job(
                    parse_trajectory, data.map_history
                )
                if points:
                    self._history_points.extend(points)
                    self._package = await self.hass.async_add_executor_job(
                        apply_trajectory, self._package, points
                    )
                    _LOGGER.debug("扫地机 %s 应用轨迹点 %d 个", uid, len(points))
                else:
                    _LOGGER.debug("扫地机 %s 轨迹记录宽度无法识别，已忽略", uid)
                self._applied_history = data.map_history
            except (ValueError, IndexError) as err:
                _LOGGER.warning("扫地机 %s 轨迹解析/应用失败：%s", uid, err)
            self._rendered_image = None

        if (
            self._rendered_image is not None
            and self._rendered_dark == dark
            and self._rendered_rotation == rotation
        ):
            return self._rendered_image
        try:
            image = await self.hass.async_add_executor_job(
                partial(render_map, self._package, dark=dark, rotation=rotation)
            )
        except (ValueError, OSError) as err:
            _LOGGER.warning("扫地机 %s 地图渲染失败：%s", uid, err)
            return None
        self._rendered_image = image
        self._rendered_dark = dark
        self._rendered_rotation = rotation
        return image
