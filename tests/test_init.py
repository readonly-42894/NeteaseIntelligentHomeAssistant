"""集成装配（``__init__.py``）在真实 Home Assistant 内核中的测试。

覆盖：配置项装载（API 客户端构造 → 家庭数据首次刷新 → 扫地机协调器 → 设备登记
→ 各平台实体）与卸载。API 客户端替换为最小替身，不产生任何网络请求。
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netease_intelligent.api import ApiError
from custom_components.netease_intelligent.const import (
    CONF_TOKEN,
    CONF_TOKEN_ID,
    DOMAIN,
)
from custom_components.netease_intelligent.models import (
    Equip,
    Family,
    FamilyEquip,
    FamilyInfo,
    Room,
    SweeperDeviceData,
)

SWEEPER_SN = "sn-test-0001"
SWEEPER_EQUIP_ID = "equip-0001"

# 各平台为单台扫地机创建的实体数量（vacuum / select / sensor / binary_sensor / image）。
EXPECTED_ENTITY_COUNTS = {
    "vacuum": 1,
    "select": 2,
    "sensor": 3,
    "binary_sensor": 1,
    "image": 1,
}


class _FakeApiClient:
    """集成启动路径所需的 API 客户端替身。

    ``error`` 非空时家庭数据与设备数据均抛错，用于验证 ``ConfigEntryNotReady``
    触发 HA 的重试；``get_account_info`` 恒定失败，使集成退回纯轮询（不建推送连接）。
    """

    def __init__(self, error: ApiError | None = None) -> None:
        self.error = error

    async def get_family_info(self) -> FamilyInfo:
        if self.error is not None:
            raise self.error
        equip = Equip(
            id=SWEEPER_EQUIP_ID,
            sn=SWEEPER_SN,
            name="扫地机",
            alias="Sweeper",
            product_id=9,
            room_name="客厅",
        )
        return FamilyInfo(
            family_list=[
                Family(
                    id=1,
                    name="我家",
                    room_list=[
                        Room(
                            id=11,
                            name="客厅",
                            family_equip_list=[
                                FamilyEquip(equip_info=equip, equip_id=equip.id),
                            ],
                        )
                    ],
                )
            ]
        )

    async def get_sweeper_data(self, equip_id: str) -> SweeperDeviceData:
        if self.error is not None:
            raise self.error
        return SweeperDeviceData(
            battery=180,
            work_mode="0",
            charge_status=1,
            wind_power=2,
            water_control=12,
            dust_box=2,
            mop_type=1,
            today_clean_size=1234,
            today_clean_time=7,
        )

    async def get_account_info(self) -> None:
        """推送通道依赖账号 ``pid``；测试环境不连接 Socket.IO。"""
        raise ApiError(401, "测试环境不连接推送服务")


def _make_entry() -> MockConfigEntry:
    """构造一个手动录入 Cookie 凭据的配置项。"""
    return MockConfigEntry(
        domain=DOMAIN,
        title="tid",
        unique_id="tid",
        data={CONF_TOKEN: "token", CONF_TOKEN_ID: "tid"},
    )


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """装载配置项：装配运行时数据、登记设备、创建全部实体；卸载后清理干净。"""
    entry = _make_entry()
    entry.add_to_hass(hass)
    client = _FakeApiClient()

    with patch(
        "custom_components.netease_intelligent.NeteaseIntelligentApiClient",
        return_value=client,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    runtime = hass.data[DOMAIN][entry.entry_id]
    assert runtime.client is client
    assert runtime.push_client is None  # 账号信息不可用 → 退回纯轮询
    assert list(runtime.sweeper_coordinators) == [SWEEPER_EQUIP_ID]

    # 设备登记以序列号 sn 作为唯一标识。
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, SWEEPER_SN), entry.entry_id
    )
    assert device is not None
    assert device.model == "RV02"

    for platform, expected in EXPECTED_ENTITY_COUNTS.items():
        entity_ids = hass.states.async_entity_ids(platform)
        assert len(entity_ids) == expected, f"{platform}: {entity_ids}"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data[DOMAIN]
    # 实体已退出运行态：HA 用 restored 占位状态保留 unavailable。
    vacuum_ids = hass.states.async_entity_ids("vacuum")
    assert vacuum_ids
    assert all(
        hass.states.get(entity_id).state == "unavailable"
        for entity_id in vacuum_ids
    )


async def test_setup_retries_when_api_unavailable(hass: HomeAssistant) -> None:
    """家庭数据首次刷新失败时应进入重试（而不是装载成功或崩溃）。"""
    entry = _make_entry()
    entry.add_to_hass(hass)
    client = _FakeApiClient(error=ApiError(500, "服务不可用"))

    with patch(
        "custom_components.netease_intelligent.NeteaseIntelligentApiClient",
        return_value=client,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
