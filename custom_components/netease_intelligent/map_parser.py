"""网易智造扫地机二进制地图包解析。

复刻 App ``sweeper/modules/map/parser/MapDataParser`` 的解码流程：

1. 地图包（``SweeperDeviceData.mapUrl`` 指向的 NOS 资源）为 **zlib** 压缩的字节流
   （``InflaterInputStream``），解压后得到原始字节；
2. 头部 2 字节为位标志（``MapHeader``），决定后续分区的存在与顺序；
3. 按固定顺序依次解析 ``MapStatus`` / ``MapData`` / ``MapHistory`` / ``MapCharge``
   / ``MapWall`` / ``MapArea`` / ``MapSpot`` / ``MapRobot``，以及协议 V2 的
   ``MapInfo``（地图名）与 ``MapRoom``（房间名 + 中点）。

本模块仅依赖标准库（``struct`` / ``zlib``），不含 Home Assistant 与渲染依赖，
便于独立单元测试。
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

__all__ = [
    "MapArea",
    "MapAreaItem",
    "MapCharge",
    "MapData",
    "MapHeader",
    "MapHistory",
    "MapHistoryItem",
    "MapPackage",
    "MapParseError",
    "MapPoint",
    "MapRoomItem",
    "MapRobot",
    "MapSpot",
    "MapStatus",
    "parse_map",
    # 网格像素值（MapData.MapValue）
    "MAP_VALUE_BACKGROUND",
    "MAP_VALUE_OBSTACLE",
    "MAP_VALUE_NOT_ARRIVED",
    "MAP_VALUE_ARRIVED",
    "MAP_VALUE_NOT_ARRIVED_ROOM_LOW",
    "MAP_VALUE_NOT_ARRIVED_ROOM_HIGH",
    "MAP_VALUE_ARRIVED_ROOM_LOW",
    "MAP_VALUE_ARRIVED_ROOM_HIGH",
    "ARRIVED_ROOM_OFFSET",
    "ROOM_ID_BASE",
]


class MapParseError(Exception):
    """地图包格式非法或截断。"""


# --------------------------------------------------------------------------- #
# 网格像素值（复刻 MapData.MapValue，反编译 sweeper/modules/map/model/MapData.java）
# --------------------------------------------------------------------------- #
MAP_VALUE_BACKGROUND: int = 0  # [0, 0] 未知/背景
MAP_VALUE_OBSTACLE: int = 255  # [-1, -1] 障碍（有符号 byte 的 255）
MAP_VALUE_NOT_ARRIVED: int = 1  # [1, 1] 未到达（已探明但未清扫）
MAP_VALUE_ARRIVED: int = 2  # [2, 2] 已到达
MAP_VALUE_NOT_ARRIVED_ROOM_LOW: int = 10  # NotArrivedRoom 区间 [10, 59]
MAP_VALUE_NOT_ARRIVED_ROOM_HIGH: int = 59
MAP_VALUE_ARRIVED_ROOM_LOW: int = 60  # ArrivedRoom 区间 [60, 119]
MAP_VALUE_ARRIVED_ROOM_HIGH: int = 119
ARRIVED_ROOM_OFFSET: int = 50  # ArrivedRoom 值 - 50 = roomId
ROOM_ID_BASE: int = 10  # roomId2Index(roomId) = roomId - 10


def map_value_2_room_id(value: int) -> int:
    """``MapUtil.mapValue2RoomId``：像素值 → 房间 ID（非房间返回 ``-1``）。"""
    if MAP_VALUE_NOT_ARRIVED_ROOM_LOW <= value <= MAP_VALUE_NOT_ARRIVED_ROOM_HIGH:
        return value
    if MAP_VALUE_ARRIVED_ROOM_LOW <= value <= MAP_VALUE_ARRIVED_ROOM_HIGH:
        return value - ARRIVED_ROOM_OFFSET
    return -1


# --------------------------------------------------------------------------- #
# little-endian 读取工具
# --------------------------------------------------------------------------- #
def _le_int(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def _le_short(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def _le_float(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MapHeader:
    """头部 2 字节位标志（复刻 ``MapHeader``）。

    参数顺序即 App 构造函数顺序：``(withStatus, withMapData, withHistory,
    withCharge, withWall, withArea, withSpot, withRobot, withAreaMemory,
    withPlan, withRoom, withSelectedRoom, withRoomChain)``。
    """

    with_status: bool
    with_map_data: bool
    with_history: bool
    with_charge: bool
    with_wall: bool
    with_area: bool
    with_spot: bool
    with_robot: bool
    with_area_memory: bool
    with_plan: bool
    with_room: bool
    with_selected_room: bool
    with_room_chain: bool

    @classmethod
    def from_bytes(cls, byte0: int, byte1: int) -> MapHeader:
        """按位解析头部（byte0 位 0-7、byte1 位 0/3/4/5/6）。"""
        return cls(
            with_status=bool(byte0 & 0x01),
            with_map_data=bool(byte0 & 0x02),
            with_history=bool(byte0 & 0x04),
            with_charge=bool(byte0 & 0x08),
            with_wall=bool(byte0 & 0x10),
            with_area=bool(byte0 & 0x20),
            with_spot=bool(byte0 & 0x40),
            with_robot=bool(byte0 & 0x80),
            with_area_memory=bool(byte1 & 0x01),
            with_plan=bool(byte1 & 0x08),
            with_room=bool(byte1 & 0x10),
            with_selected_room=bool(byte1 & 0x20),
            with_room_chain=bool(byte1 & 0x40),
        )


@dataclass
class MapStatus:
    """状态区（复刻 ``MapStatus``）：11 个 little-endian int32。"""

    map_head_id: int = 0
    has_history_map: int = 0
    working_mode: int = 0
    battery_percent: int = 0
    charge_state: int = 0
    fault_type: int = 0
    fault_code: int = 0
    clean_preference: int = 0
    repeat_clean: int = 0
    clean_time: int = 0
    clean_size: int = 0


@dataclass
class MapData:
    """栅格地图（复刻 ``MapData``）。

    ``grid`` 为一维字节数组，索引方式为 ``grid[y * size_x + x]``
    （``pack()``：``renderingMap[x][y] = map[y * sizeX + x]``）。
    """

    map_head_id: int = 0
    map_valid: int = 0
    map_type: int = 0
    size_x: int = 0
    size_y: int = 0
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 0.0
    max_y: float = 0.0
    resolution: float = 0.0
    grid: bytes = b""

    def cell(self, x: int, y: int) -> int:
        """取 ``(x, y)`` 处像素值（无符号字节）。"""
        return self.grid[y * self.size_x + x]

    def physics_to_grid(self, x: float, y: float) -> tuple[float, float]:
        """物理坐标 → 栅格坐标（``MapUtil.physicsToGrid``）。"""
        resolution = self.resolution or 1.0
        return (x - self.min_x) / resolution, (y - self.min_y) / resolution


@dataclass
class MapHistoryItem:
    """历史轨迹点（9 字节：byte update + 2×float）。"""

    update: int
    pose_x: float
    pose_y: float


@dataclass
class MapHistory:
    """历史轨迹区。"""

    map_head_id: int = 0
    pose_id: int = 0
    items: list[MapHistoryItem] = field(default_factory=list)


@dataclass
class MapCharge:
    """充电座位姿（复刻 ``MapCharge``）。"""

    map_head_id: int = 0
    pose_x: float = 0.0
    pose_y: float = 0.0
    pose_phi: float = 0.0


@dataclass
class MapPoint:
    """平面点。"""

    x: float
    y: float


@dataclass
class MapAreaItem:
    """墙/区域多边形项（固定 10 个点，按 ``count`` 截断）。"""

    id: int
    count: int
    points: list[MapPoint] = field(default_factory=list)


@dataclass
class MapArea:
    """墙（``withWall``）或清扫区域（``withArea``）。"""

    map_head_id: int = 0
    type: int = 0
    items: list[MapAreaItem] = field(default_factory=list)


@dataclass
class MapSpot:
    """定点（复刻 ``MapSpot``）。"""

    map_head_id: int = 0
    ctrl_value: int = 0
    pose_x: float = 0.0
    pose_y: float = 0.0
    phi: float = 0.0


@dataclass
class MapRobot:
    """机器人位姿（复刻 ``MapRobot``）。"""

    map_head_id: int = 0
    pose_id: int = 0
    update: int = 0
    pose_x: float = 0.0
    pose_y: float = 0.0
    pose_phi: float = 0.0


@dataclass
class MapRoomItem:
    """房间项（复刻 ``MapRoomItem``）：房间名与中点物理坐标。"""

    room_id: int = 0
    name: str = ""
    state: int = 0
    middle_x: float = 0.0
    middle_y: float = 0.0


@dataclass
class MapPackage:
    """一张地图的完整解析结果。"""

    header: MapHeader
    status: MapStatus | None = None
    map_data: MapData | None = None
    history: MapHistory | None = None
    charge: MapCharge | None = None
    wall: MapArea | None = None
    area: MapArea | None = None
    spot: MapSpot | None = None
    robot: MapRobot | None = None
    rooms: list[MapRoomItem] = field(default_factory=list)
    raw: bytes = b""


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
_MAP_AREA_ITEM_SIZE: int = 12 + 10 * 8  # 10 个 MapPoint（固定读满）
_HISTORY_ITEM_SIZE: int = 9


def _parse_area(data: bytes, offset: int) -> MapArea:
    """解析墙/区域区，返回 ``MapArea``（游标推进由调用方按 12 + count*92 处理）。"""
    count = _le_int(data, offset + 8)
    base = offset + 12
    items: list[MapAreaItem] = []
    for k in range(count):
        item_offset = base + k * _MAP_AREA_ITEM_SIZE
        point_count = _le_int(data, item_offset + 8)
        points = [
            MapPoint(
                _le_float(data, item_offset + 12 + j * 8),
                _le_float(data, item_offset + 12 + j * 8 + 4),
            )
            for j in range(10)
        ]
        items.append(
            MapAreaItem(
                id=_le_int(data, item_offset),
                count=point_count,
                points=points[:point_count],
            )
        )
    return MapArea(
        map_head_id=_le_int(data, offset),
        type=_le_int(data, offset + 4),
        items=items,
    )


def _parse_rooms(data: bytes, offset: int) -> list[MapRoomItem]:
    """解析协议 V2 的 ``MapInfo`` + ``MapRoom``，仅取房间名与中点。"""
    # MapInfo：int mapHeadId, short mask, byte firstCleanFlag, byte itemCount
    item_count = data[offset + 7]
    cursor = offset + 8
    for _ in range(item_count):
        name_length = data[cursor + 4]
        cursor += name_length + 5
    # MapRoom：int planId, int roomCount, items
    room_count = _le_int(data, cursor + 4)
    cursor += 8
    rooms: list[MapRoomItem] = []
    for _ in range(room_count):
        room_id = data[cursor]
        name_length = data[cursor + 1]
        name_end = cursor + 2 + name_length
        name = data[cursor + 2 : name_end].decode("utf-8", errors="replace")
        rooms.append(
            MapRoomItem(
                room_id=room_id,
                name=name,
                state=data[name_end],
                middle_x=_le_float(data, name_end + 1),
                middle_y=_le_float(data, name_end + 5),
            )
        )
        cursor += name_length + 11
    return rooms


def parse_map(raw: bytes) -> MapPackage:
    """解析原始地图包（zlib 压缩）为 :class:`MapPackage`。

    ``raw`` 为 ``mapUrl`` 下载到的字节；若并非 zlib 压缩则按原始字节解析
    （容错，便于测试与格式演进）。格式非法时抛 :class:`MapParseError`。
    """
    try:
        data = zlib.decompress(raw)
    except zlib.error:
        data = raw

    if len(data) < 2:
        raise MapParseError("map package too short")

    header = MapHeader.from_bytes(data[0], data[1])
    status: MapStatus | None = None
    cursor = 4

    try:
        if header.with_status:
            values = [_le_int(data, off) for off in range(4, 44, 4)]
            status = MapStatus(*values)
            cursor = 48

        map_data: MapData | None = None
        if header.with_map_data:
            size_x = _le_int(data, cursor + 12)
            size_y = _le_int(data, cursor + 16)
            grid = data[cursor + 40 : cursor + 40 + size_x * size_y]
            map_data = MapData(
                map_head_id=_le_int(data, cursor),
                map_valid=_le_int(data, cursor + 4),
                map_type=_le_int(data, cursor + 8),
                size_x=size_x,
                size_y=size_y,
                min_x=_le_float(data, cursor + 20),
                min_y=_le_float(data, cursor + 24),
                max_x=_le_float(data, cursor + 28),
                max_y=_le_float(data, cursor + 32),
                resolution=_le_float(data, cursor + 36),
                grid=grid,
            )
            cursor += size_x * size_y + 40

        history: MapHistory | None = None
        if header.with_history:
            point_number = _le_int(data, cursor + 8)
            base = cursor + 12
            history = MapHistory(
                map_head_id=_le_int(data, cursor),
                pose_id=_le_int(data, cursor + 4),
                items=[
                    MapHistoryItem(
                        update=data[base + k * _HISTORY_ITEM_SIZE],
                        pose_x=_le_float(data, base + k * _HISTORY_ITEM_SIZE + 1),
                        pose_y=_le_float(data, base + k * _HISTORY_ITEM_SIZE + 5),
                    )
                    for k in range(point_number)
                ],
            )
            cursor += point_number * _HISTORY_ITEM_SIZE + 12

        charge: MapCharge | None = None
        if header.with_charge:
            charge = MapCharge(
                map_head_id=_le_int(data, cursor),
                pose_x=_le_float(data, cursor + 4),
                pose_y=_le_float(data, cursor + 8),
                pose_phi=_le_float(data, cursor + 12),
            )
            cursor += 16

        wall: MapArea | None = None
        if header.with_wall:
            wall = _parse_area(data, cursor)
            cursor += 12 + _le_int(data, cursor + 8) * _MAP_AREA_ITEM_SIZE

        area: MapArea | None = None
        if header.with_area:
            area = _parse_area(data, cursor)
            cursor += 12 + _le_int(data, cursor + 8) * _MAP_AREA_ITEM_SIZE

        spot: MapSpot | None = None
        if header.with_spot:
            spot = MapSpot(
                map_head_id=_le_int(data, cursor),
                ctrl_value=_le_int(data, cursor + 4),
                pose_x=_le_float(data, cursor + 8),
                pose_y=_le_float(data, cursor + 12),
                phi=_le_float(data, cursor + 16),
            )
            cursor += 20

        robot: MapRobot | None = None
        if header.with_robot:
            robot = MapRobot(
                map_head_id=_le_int(data, cursor),
                pose_id=_le_int(data, cursor + 4),
                update=data[cursor + 8],
                pose_x=_le_float(data, cursor + 9),
                pose_y=_le_float(data, cursor + 13),
                pose_phi=_le_float(data, cursor + 17),
            )
            cursor += 21

        rooms: list[MapRoomItem] = []
        if header.with_plan:
            rooms = _parse_rooms(data, cursor)
    except (struct.error, IndexError) as err:
        raise MapParseError(f"malformed map package: {err}") from err

    return MapPackage(
        header=header,
        status=status,
        map_data=map_data,
        history=history,
        charge=charge,
        wall=wall,
        area=area,
        spot=spot,
        robot=robot,
        rooms=rooms,
        raw=raw,
    )
