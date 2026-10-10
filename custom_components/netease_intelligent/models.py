"""网易智造家庭域数据模型。

对应 App API ``ResponseWrapper.result`` 中的家庭相关 DTO（见 docs/openapi.yaml）：

- ``FamilyInfo`` —— ``GET /ai-app/family/info`` 的返回，含 ``familyList`` 与排序/未读信息；
- ``Family`` —— 单个家庭，含房间（``Room``）、成员（``Member``）与分享设备（``Equip``）；
- ``FamilyEnv`` / ``EnvInfo`` —— ``GET /ai-app/family/env/info/homepage`` 的家庭环境信息；
- ``Equip`` —— 设备。

设计约定：

- Python 侧字段为 ``snake_case``，解析时按 ``camelCase`` 映射回 API 的 JSON 键
  （例如 ``family_id`` ← ``familyId``，``is_deleted`` ← ``isDeleted``）。
- 所有字段都有默认值；接口缺字段时保持默认，便于接口版本演进时容错。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Self, get_args, get_origin, get_type_hints

from .const import SWEEPER_PRODUCT_IDS

__all__ = [
    "Equip",
    "EnvInfo",
    "Family",
    "FamilyEnv",
    "FamilyEquip",
    "FamilyInfo",
    "Member",
    "Room",
    "SweeperDeviceData",
]


def _camel_case(snake: str) -> str:
    """把 ``snake_case`` 字段名转成 API 的 ``camelCase`` JSON 键。"""
    head, *rest = snake.split("_")
    return head + "".join(word.title() for word in rest)


def _convert(value: Any, target: Any) -> Any:
    """按类型注解把原始 JSON 值转换为目标类型（支持嵌套模型与列表）。"""
    if value is None:
        return None

    origin = get_origin(target)
    if origin is list:
        (element_type,) = get_args(target)
        return [_convert(item, element_type) for item in value]
    if origin is not None:
        # Optional[X] / Union[...]：取唯一的非 None 成员继续转换。
        members = [arg for arg in get_args(target) if arg is not type(None)]
        if len(members) == 1:
            return _convert(value, members[0])
    if isinstance(target, type) and issubclass(target, _Model):
        return target.from_dict(value)
    return value


class _Model:
    """家庭域 DTO 基类：按注解从 API 的 JSON dict 反序列化。"""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self:
        """从接口返回的 dict 构造实例；缺字段保持默认值。"""
        data = data or {}
        hints = get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for dfield in dataclasses.fields(cls):
            key = _camel_case(dfield.name)
            if key in data:
                kwargs[dfield.name] = _convert(data[key], hints[dfield.name])
        return cls(**kwargs)


@dataclass
class Equip(_Model):
    """设备（App DTO ``Equip``）。"""

    id: str = ""  # equipId（字符串），调用 sweeper 等模块端点时作为参数
    dev_type: int = 0
    bind_type: int = 0
    product_id: int = 0
    status: int = 0
    vender: int = 0
    weight: int = 0
    account: int = 0
    create_time: int = 0
    family_id: int = 0
    last_end_time: int = 0
    last_start_time: int = 0
    rid: int = 0
    room_id: int = 0
    update_time: int = 0
    alias: str = ""
    bluetooth_mac_addr: str = ""
    continued: str = ""
    dialog_oks: str = ""
    manufactor_id: str = ""
    model: str = ""
    name: str = ""
    room_name: str = ""
    sn: str = ""
    type: str = ""
    wap_url: str = ""
    wifi_mac_addr: str = ""
    is_deleted: bool = False

    @property
    def is_sweeper(self) -> bool:
        """是否为扫地机器人（``product_id`` 属于 RV02/RV03）。"""
        return self.product_id in SWEEPER_PRODUCT_IDS

    @property
    def unique_identifier(self) -> str:
        """设备唯一标识：优先序列号 ``sn``，回退 ``id``（equipId）；均缺失为空串。"""
        return self.sn or self.id


@dataclass
class FamilyEquip(_Model):
    """家庭-房间与设备的关联项（App DTO ``FamilyEquip``）。"""

    equip_info: Equip | None = None
    family_id: int = 0
    id: int = 0
    room_id: int = 0
    equip_id: str = ""

    @property
    def equip(self) -> Equip | None:
        """关联的设备对象（``equipInfo``）。"""
        return self.equip_info


@dataclass
class Room(_Model):
    """家庭内的房间（App DTO ``Room``），含房间内设备列表。"""

    icon: int = 0
    family_equip_list: list[FamilyEquip] = field(default_factory=list)
    create_time: int = 0
    family_id: int = 0
    id: int = 0
    name: str = ""


@dataclass
class Member(_Model):
    """家庭成员（App DTO ``Member``）。"""

    type: int = 0
    family_id: int = 0
    invite_time: int = 0
    pid: int = 0
    head_pic: str = ""
    name: str = ""
    uid: str = ""


@dataclass
class Family(_Model):
    """家庭（App DTO ``Family``）：房间、成员与分享设备的集合。"""

    id: int = 0
    name: str = ""
    owner_pid: int = 0
    type: int = 0
    theme: int = 0
    room_list: list[Room] = field(default_factory=list)
    member_list: list[Member] = field(default_factory=list)
    share_equip_list: list[Equip] = field(default_factory=list)

    @property
    def equips(self) -> list[Equip]:
        """家庭内全部设备：各房间内的设备 + 分享设备。"""
        result: list[Equip] = [
            family_equip.equip_info
            for room in self.room_list
            for family_equip in room.family_equip_list
            if family_equip.equip_info is not None
        ]
        result.extend(self.share_equip_list)
        return result


@dataclass
class EnvInfo(_Model):
    """家庭环境信息条目（App DTO ``EnvInfo``）。"""

    room_id: int = 0
    room_name: str = ""
    status_text: str = ""
    family_id: int = 0


@dataclass
class FamilyEnv(_Model):
    """家庭环境信息（App DTO ``FamilyEnv``）。"""

    list: list[EnvInfo] = field(default_factory=list)
    family_id: int = 0


@dataclass
class FamilyInfo(_Model):
    """家庭列表信息（App DTO ``FamilyInfo``，``GET /ai-app/family/info``）。"""

    family_list: list[Family] = field(default_factory=list)
    sort_info: str = ""
    unread: int = 0


@dataclass
class SweeperDeviceData(_Model):
    """扫地机实时数据（App DTO ``SweeperDeviceData``，``GET /ai-app/sweeper/rv02/getDeviceData``）。"""

    area_clean_flag: int = 0
    is_online: bool = False
    is_ota_updating: bool = False
    is_room_cleaning_status: bool = False
    charge_status: int = 0
    battery: int = 0
    clean_size: int = 0
    clean_time: int = 0
    # fault_type == 1 才是设备故障（错误）；fault_code 非 0 不代表错误（2101/2103/2105
    # 为在充电座/充电中等状态），见 const.SWEEPER_FAULT_TYPE_ERROR 与 sweeper_activity。
    fault_code: int = 0
    fault_type: int = 0
    today_clean_size: int = 0
    today_clean_time: int = 0
    clean_scheme_id: int = 0
    map_id: int = 0
    map_type: int = 0
    repeat_clean: int = 0
    map_url: str = ""
    protocol_version: str = ""
    water_control: int = 0
    wind_power: int = 0
    work_mode: str = ""
