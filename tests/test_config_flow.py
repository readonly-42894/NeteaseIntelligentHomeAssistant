"""配置流（``config_flow.py``）在真实 Home Assistant 内核中的测试。

覆盖：登录方式菜单、手动录入 Cookie 凭据建项、唯一 ID 去重、选项流（地图配色/朝向）。
配置项创建后 HA 会立即装载集成，这里替换 ``async_setup_entry`` 以免发起真实网络请求。
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netease_intelligent.const import (
    CONF_MAP_ROTATION,
    CONF_MAP_THEME,
    CONF_TOKEN,
    CONF_TOKEN_ID,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[AsyncMock]:
    """避免配置项创建后真实执行 ``async_setup_entry``（会访问 3c.163.com）。"""
    with patch(
        "custom_components.netease_intelligent.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


async def _start_flow(hass: HomeAssistant) -> dict:
    """从「添加集成」入口开启配置流。"""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def test_user_step_shows_login_menu(hass: HomeAssistant) -> None:
    """首步为登录方式菜单：短信 / 邮箱 / 手动 Cookie。"""
    result = await _start_flow(hass)

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    assert result["menu_options"] == ["phone", "email", "manual"]


async def test_manual_step_creates_entry(hass: HomeAssistant) -> None:
    """手动录入 Cookie 凭据 → 建项，唯一 ID 为 ONE_TOKEN_ID。"""
    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TOKEN: "token-value", CONF_TOKEN_ID: "token-id-value"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "token-id-value"
    assert result["data"] == {
        CONF_TOKEN: "token-value",
        CONF_TOKEN_ID: "token-id-value",
    }
    assert result["result"].unique_id == "token-id-value"


async def test_manual_step_aborts_on_duplicate(hass: HomeAssistant) -> None:
    """同一 ONE_TOKEN_ID 已配置时中止，避免重复建项。"""
    MockConfigEntry(
        domain=DOMAIN,
        title="token-id-value",
        unique_id="token-id-value",
        data={CONF_TOKEN: "old", CONF_TOKEN_ID: "token-id-value"},
    ).add_to_hass(hass)

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TOKEN: "token-value", CONF_TOKEN_ID: "token-id-value"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_save(hass: HomeAssistant) -> None:
    """选项流：保存地图配色与朝向后写入配置项选项。"""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="tid",
        unique_id="tid",
        data={CONF_TOKEN: "token", CONF_TOKEN_ID: "tid"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_MAP_THEME: "dark", CONF_MAP_ROTATION: "90"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_MAP_THEME: "dark", CONF_MAP_ROTATION: "90"}
