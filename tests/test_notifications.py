"""通知分发测试：事件总线 + 持久通知（``persistent_notification``）。

覆盖 ``__init__.py._handle_notification``：事件始终触发；持久通知默认写入，
可在选项里关闭；正文回退与链接追加、每条通知独立 id。
"""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.netease_intelligent import _handle_notification
from custom_components.netease_intelligent.const import (
    CONF_SHOW_NOTIFICATIONS,
    CONF_TOKEN,
    CONF_TOKEN_ID,
    DOMAIN,
    EVENT_NOTIFICATION,
)
from custom_components.netease_intelligent.push_protocol import NotificationPacket


def _make_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    """构造配置项并加入 hass（选项流开关决定是否写持久通知）。"""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="tid",
        unique_id="tid",
        data={CONF_TOKEN: "token", CONF_TOKEN_ID: "tid"},
        options=options,
    )
    entry.add_to_hass(hass)
    return entry


def _make_packet(**overrides: object) -> NotificationPacket:
    """构造一条可展示的通知（默认非设备事件、标题非空）。"""
    fields: dict = {
        "id": "noti-1",
        "timestamp": 1700000000000,
        "title": "测试通知",
        "message": "通知正文",
    }
    fields.update(overrides)
    return NotificationPacket(**fields)


def _notifications(hass: HomeAssistant) -> dict:
    """当前持久通知集合（未创建时为空字典）。"""
    return hass.data.get(persistent_notification.DOMAIN, {})


async def test_notification_creates_event_and_persistent_notification(
    hass: HomeAssistant,
) -> None:
    """默认开启：事件总线触发，同时写入一条带链接的持久通知。"""
    entry = _make_entry(hass)
    events = async_capture_events(hass, EVENT_NOTIFICATION)
    packet = _make_packet(url="https://example.com/detail")

    _handle_notification(hass, entry, packet)
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["title"] == "测试通知"
    assert events[0].data["id"] == "noti-1"

    notification_id = f"{DOMAIN}_notification_noti-1"
    notification = _notifications(hass)[notification_id]
    assert notification["title"] == "测试通知"
    assert "通知正文" in notification["message"]
    assert "[查看详情](https://example.com/detail)" in notification["message"]


async def test_notification_without_url_has_no_link(hass: HomeAssistant) -> None:
    """没有 url 时不追加链接。"""
    entry = _make_entry(hass)

    _handle_notification(hass, entry, _make_packet())
    await hass.async_block_till_done()

    notification = _notifications(hass)[f"{DOMAIN}_notification_noti-1"]
    assert notification["message"] == "通知正文"


async def test_notification_message_falls_back_to_content(
    hass: HomeAssistant,
) -> None:
    """``android.message`` 为空时正文回退 ``NotificationData.content``。"""
    entry = _make_entry(hass)

    _handle_notification(
        hass, entry, _make_packet(message="", content="消息中心内容")
    )
    await hass.async_block_till_done()

    notification = _notifications(hass)[f"{DOMAIN}_notification_noti-1"]
    assert notification["message"] == "消息中心内容"


async def test_notification_disabled_by_option(hass: HomeAssistant) -> None:
    """选项关闭时只触发事件，不写持久通知。"""
    entry = _make_entry(hass, {CONF_SHOW_NOTIFICATIONS: False})
    events = async_capture_events(hass, EVENT_NOTIFICATION)

    _handle_notification(hass, entry, _make_packet())
    await hass.async_block_till_done()

    assert len(events) == 1
    assert _notifications(hass) == {}


async def test_notifications_are_independent(hass: HomeAssistant) -> None:
    """不同通知 id 各自成条，互不覆盖。"""
    entry = _make_entry(hass)

    _handle_notification(hass, entry, _make_packet(id="noti-1"))
    _handle_notification(hass, entry, _make_packet(id="noti-2", title="第二条"))
    await hass.async_block_till_done()

    notifications = _notifications(hass)
    assert set(notifications) == {
        f"{DOMAIN}_notification_noti-1",
        f"{DOMAIN}_notification_noti-2",
    }
    assert notifications[f"{DOMAIN}_notification_noti-2"]["title"] == "第二条"
