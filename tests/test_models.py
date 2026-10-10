"""家庭域数据模型（``models.py``）单元测试。

覆盖：DTO 反序列化（camelCase → snake_case）、嵌套模型、列表展开（``Family.equips``）、
缺字段 / ``None`` 容错。

导入方式见 ``conftest.py``（合成包名 ``netease_intelligent``，避免引入 homeassistant 依赖）。
"""

from __future__ import annotations

import netease_intelligent.models as m

_SAMPLE = {
    "familyList": [{
        "id": 100, "name": "我家", "ownerPid": 7, "type": 1, "theme": 2,
        "roomList": [{
            "icon": 3, "familyId": 100, "id": 11, "name": "客厅", "createTime": 111,
            "familyEquipList": [{
                "equipId": "sn-abc", "familyId": 100, "id": 1, "roomId": 11,
                "equipInfo": {"sn": "sn-abc", "name": "扫地机", "productId": 5,
                              "isDeleted": False, "bluetoothMacAddr": "AA:BB", "roomName": "客厅"},
            }],
        }],
        "memberList": [{"type": 1, "familyId": 100, "pid": 7, "name": "张三",
                        "headPic": "http://x", "uid": "u1", "inviteTime": 222}],
        "shareEquipList": [{"sn": "sn-share", "name": "分享灯", "productId": 9}],
    }],
    "sortInfo": "100", "unread": 3,
}


def test_family_info_roundtrip() -> None:
    info = m.FamilyInfo.from_dict(_SAMPLE)
    assert info.sort_info == "100" and info.unread == 3

    family = info.family_list[0]
    assert family.id == 100 and family.name == "我家" and family.owner_pid == 7

    room = family.room_list[0]
    assert room.name == "客厅" and room.family_equip_list[0].equip_id == "sn-abc"

    equip = room.family_equip_list[0].equip_info
    assert equip is not None
    assert equip.sn == "sn-abc"
    assert equip.bluetooth_mac_addr == "AA:BB"
    assert equip.room_name == "客厅"
    assert equip.is_deleted is False

    member = family.member_list[0]
    assert member.head_pic == "http://x" and member.invite_time == 222

    # Family.equips 汇总各房间设备 + 分享设备
    assert [e.sn for e in family.equips] == ["sn-abc", "sn-share"]


def test_family_env() -> None:
    env = m.FamilyEnv.from_dict({
        "list": [{"roomId": 11, "roomName": "客厅", "statusText": "ok", "familyId": 100}],
        "familyId": 100,
    })
    assert env.family_id == 100
    assert env.list[0].status_text == "ok"


def test_missing_fields_tolerated() -> None:
    empty = m.Family.from_dict(None)
    assert empty.room_list == [] and empty.share_equip_list == []

    assert m.FamilyEquip.from_dict({"equipInfo": None}).equip_info is None