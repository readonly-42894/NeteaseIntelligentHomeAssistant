"""把解析出的地图包渲染为 PNG（Pillow 实现）。

复刻 App ``MapBaseSpirit`` 的上色规则与 ``MapView`` 的坐标变换，输出一张可直接
在 Home Assistant ``image`` 实体中展示的静态地图：

- 栅格底色：障碍 ``#717AE4``、未清扫地面白色；房间按 ``ROOM_COLOR_NOT_ARRIVED``
  6 组双色棋盘交替着色（实时地图不区分已到/未到房间）；
- 叠加层：房间名（白描边）、机器人位置、充电座位置。

坐标约定：``MapData.physics_to_grid`` 得到栅格坐标；渲染时 **Y 轴翻转**，
使栅格第 0 行绘制在图片底部，与 App 视角一致。

本模块不含 Home Assistant 依赖，仅需 Pillow。
"""

from __future__ import annotations

import glob
import io
import os

from PIL import Image, ImageDraw, ImageFont

from .map_parser import (
    MAP_VALUE_ARRIVED_ROOM_HIGH,
    MAP_VALUE_ARRIVED_ROOM_LOW,
    MAP_VALUE_BACKGROUND,
    MAP_VALUE_NOT_ARRIVED_ROOM_HIGH,
    MAP_VALUE_NOT_ARRIVED_ROOM_LOW,
    MAP_VALUE_OBSTACLE,
    ROOM_ID_BASE,
    MapData,
    MapPackage,
    map_value_2_room_id,
)

__all__ = ["render_map", "MAP_DEFAULT_TARGET_SIZE"]

#: 输出图片的最大目标边长（像素），实际尺寸按栅格长宽比缩放。
MAP_DEFAULT_TARGET_SIZE: int = 800

# 颜色（RGB）——对应反编译 MapBaseSpirit 的整型颜色常量。
_COLOR_BACKGROUND: tuple[int, int, int] = (0xF2, 0xF2, 0xF2)  # 未探明区域（留白）
_COLOR_UNREACHABLE: tuple[int, int, int] = (0x71, 0x7A, 0xE4)  # MAP_COLOR_UNREACHABLE
_COLOR_NOT_ARRIVED: tuple[int, int, int] = (0xFF, 0xFF, 0xFF)  # MAP_COLOR_NOT_ARRIVED
# ROOM_COLOR_NOT_ARRIVED：6 组双色，按 ((x // 2) + (y // 2)) % 2 交替。
_ROOM_COLOR_NOT_ARRIVED: tuple[tuple[tuple[int, int, int], ...], ...] = (
    ((0xA9, 0x9B, 0xDB), (0xCB, 0xC3, 0xE9)),
    ((0x73, 0xB3, 0xC5), (0xA1, 0xD1, 0xDC)),
    ((0xEB, 0x9D, 0x73), (0xF1, 0xBA, 0x95)),
    ((0xE2, 0x77, 0x9C), (0xEA, 0x9A, 0xB9)),
    ((0xD2, 0xA9, 0xCD), (0xE4, 0xCB, 0xE1)),
    ((0x77, 0x7C, 0xB2), (0x9A, 0xA1, 0xC9)),
)

_COLOR_ROBOT: tuple[int, int, int] = (0x33, 0x33, 0x33)  # 机器人标记
_COLOR_CHARGE: tuple[int, int, int] = (0xFF, 0xB3, 0x00)  # 充电座标记
_COLOR_SPOT: tuple[int, int, int] = (0xE5, 0x39, 0x35)  # 定点标记
_COLOR_OUTLINE: tuple[int, int, int] = (0xFF, 0xFF, 0xFF)  # 标记描边
_COLOR_TEXT: tuple[int, int, int] = (0x22, 0x22, 0x22)  # 房间名文字色（R.color.txt_1）
_COLOR_TEXT_STROKE: tuple[int, int, int] = (0xFF, 0xFF, 0xFF)

#: 优先使用的 CJK 字体路径（跨平台常见位置），均不存在时回退 Pillow 默认字体。
_FONT_CANDIDATES: tuple[str, ...] = (
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

#: 兜底：在上述固定路径之外，按通配符搜索常见 CJK 字体（不同发行版布局不一）。
_FONT_GLOBS: tuple[str, ...] = (
    "/usr/share/fonts/noto-cjk/*CJK*Regular*.ttc",
    "/usr/share/fonts/**/NotoSansCJKsc-Regular.*",
    "/usr/share/fonts/**/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/**/wqy*.ttc",
)

#: 全背景时回退的居中窗口宽度（米），对应 App 的 MAP_DEFAULE_WIDTH。
_FALLBACK_WINDOW_METERS: float = 3.0


def _font_paths() -> list[str]:
    """候选字体路径：固定路径 + 通配符搜索（去重、保序）。"""
    paths: list[str] = []
    for path in _FONT_CANDIDATES:
        if path not in paths:
            paths.append(path)
    for pattern in _FONT_GLOBS:
        for path in sorted(glob.glob(pattern, recursive=True)):
            if path not in paths:
                paths.append(path)
    return paths


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """加载一个尽量支持中文的字体；失败时回退 Pillow 默认字体。"""
    for path in _font_paths():
        if not os.path.exists(path):
            continue
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # 旧版 Pillow 的 load_default 不接受 size
        return ImageFont.load_default()


def _cell_color(value: int, grid_x: int, grid_y: int) -> tuple[int, int, int] | None:
    """栅格像素值 → 颜色；``None`` 表示背景（不绘制）。"""
    if value == MAP_VALUE_BACKGROUND:
        return None
    if value == MAP_VALUE_OBSTACLE:
        return _COLOR_UNREACHABLE
    is_room = (
        MAP_VALUE_NOT_ARRIVED_ROOM_LOW <= value <= MAP_VALUE_NOT_ARRIVED_ROOM_HIGH
        or MAP_VALUE_ARRIVED_ROOM_LOW <= value <= MAP_VALUE_ARRIVED_ROOM_HIGH
    )
    if not is_room:
        # NotArrived / Arrived 等：实时地图（非 history）统一白色。
        return _COLOR_NOT_ARRIVED
    room_id = map_value_2_room_id(value)
    palette = _ROOM_COLOR_NOT_ARRIVED[(room_id - ROOM_ID_BASE) % len(_ROOM_COLOR_NOT_ARRIVED)]
    return palette[((grid_x // 2) + (grid_y // 2)) % 2]


def _render_bounds(
    map_data: MapData, package: MapPackage
) -> tuple[int, int, int, int]:
    """计算渲染所用的栅格包围盒 ``(min_x, max_x, min_y, max_y)``（含端点）。

    先取非背景像素的紧包围盒，再用墙/区域顶点、定点、机器人、充电座的物理坐标
    经 ``physics_to_grid`` 外扩；全背景时回退到居中的 3.0m 窗口。
    """
    size_x = map_data.size_x
    size_y = map_data.size_y
    if size_x <= 0 or size_y <= 0:
        return 0, 0, 0, 0

    min_x = max_x = min_y = max_y = None
    grid = map_data.grid
    for y in range(size_y):
        row = y * size_x
        for x in range(size_x):
            if grid[row + x] == MAP_VALUE_BACKGROUND:
                continue
            if min_x is None:
                min_x = max_x = x
                min_y = max_y = y
                continue
            if x < min_x:
                min_x = x
            elif x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            elif y > max_y:
                max_y = y

    def include(physics_x: float, physics_y: float) -> None:
        """把物理坐标点纳入包围盒；越出栅格范围的无效点（如空定点哨兵值）忽略。"""
        nonlocal min_x, max_x, min_y, max_y
        grid_x, grid_y = map_data.physics_to_grid(physics_x, physics_y)
        gx = int(round(grid_x))
        gy = int(round(grid_y))
        if not (0 <= gx < size_x and 0 <= gy < size_y):
            return
        if min_x is None:
            min_x = max_x = gx
            min_y = max_y = gy
            return
        min_x = min(min_x, gx)
        max_x = max(max_x, gx)
        min_y = min(min_y, gy)
        max_y = max(max_y, gy)

    for area in (package.wall, package.area):
        if area is None:
            continue
        for item in area.items:
            for point in item.points:
                include(point.x, point.y)
    if package.spot is not None:
        include(package.spot.pose_x, package.spot.pose_y)
    if package.robot is not None:
        include(package.robot.pose_x, package.robot.pose_y)
    if package.charge is not None:
        include(package.charge.pose_x, package.charge.pose_y)

    if min_x is None:
        # 全背景：回退到地图中心、边长 3.0m 的窗口。
        span = (
            int(round(_FALLBACK_WINDOW_METERS / map_data.resolution))
            if map_data.resolution
            else size_x
        )
        span = max(1, min(span, min(size_x, size_y)))
        center_x = size_x // 2
        center_y = size_y // 2
        min_x = max(0, center_x - span // 2)
        max_x = min(size_x - 1, min_x + span - 1)
        min_y = max(0, center_y - span // 2)
        max_y = min(size_y - 1, min_y + span - 1)

    return int(min_x), int(max_x), int(min_y), int(max_y)


def _draw_marker(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    radius: int,
    fill: tuple[int, int, int],
) -> None:
    """绘制带白色描边的圆形标记。"""
    draw.ellipse(
        [x - radius, y - radius, x + radius, y + radius],
        fill=fill,
        outline=_COLOR_OUTLINE,
        width=max(1, radius // 3),
    )


def render_map(
    package: MapPackage,
    *,
    target_size: int = MAP_DEFAULT_TARGET_SIZE,
) -> bytes:
    """把地图包渲染为 PNG 字节。

    ``package`` 需包含 ``map_data``（否则抛 ``ValueError``）；``target_size``
    为输出图片的最大边长（像素）。
    """
    map_data = package.map_data
    if map_data is None or map_data.size_x <= 0 or map_data.size_y <= 0:
        raise ValueError("map package has no usable map data")

    min_x, max_x, min_y, max_y = _render_bounds(map_data, package)
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    cell = max(1, target_size // max(width, height))
    image = Image.new("RGB", (width * cell, height * cell), _COLOR_BACKGROUND)
    draw = ImageDraw.Draw(image)

    # 栅格底色：Y 轴翻转，使栅格第 0 行位于图片底部。
    for grid_y in range(min_y, max_y + 1):
        row = grid_y * map_data.size_x
        pixel_y = (max_y - grid_y) * cell
        for grid_x in range(min_x, max_x + 1):
            color = _cell_color(map_data.grid[row + grid_x], grid_x, grid_y)
            if color is None:
                continue
            pixel_x = (grid_x - min_x) * cell
            draw.rectangle(
                [pixel_x, pixel_y, pixel_x + cell - 1, pixel_y + cell - 1],
                fill=color,
            )

    # 房间名。
    if package.rooms:
        font = _load_font(max(12, cell * 3))
        for room in package.rooms:
            if not room.name:
                continue
            grid_x, grid_y = map_data.physics_to_grid(room.middle_x, room.middle_y)
            pixel_x = (int(round(grid_x)) - min_x) * cell
            pixel_y = (max_y - int(round(grid_y))) * cell
            if not (0 <= pixel_x <= width * cell and 0 <= pixel_y <= height * cell):
                continue
            draw.text(
                (pixel_x, pixel_y),
                room.name,
                font=font,
                fill=_COLOR_TEXT,
                stroke_width=max(1, cell // 2),
                stroke_fill=_COLOR_TEXT_STROKE,
                anchor="mm",
            )

    # 标记：充电座、机器人、定点（物理坐标 → 栅格 → 像素）。
    def to_pixel(physics_x: float, physics_y: float) -> tuple[float, float] | None:
        grid_x, grid_y = map_data.physics_to_grid(physics_x, physics_y)
        if not (0 <= grid_x < map_data.size_x and 0 <= grid_y < map_data.size_y):
            return None
        return (
            (grid_x - min_x + 0.5) * cell,
            (max_y - grid_y + 0.5) * cell,
        )

    marker_radius = max(3, cell * 3)
    if package.charge is not None:
        pixel = to_pixel(package.charge.pose_x, package.charge.pose_y)
        if pixel is not None:
            _draw_marker(draw, pixel[0], pixel[1], marker_radius, _COLOR_CHARGE)
    if package.spot is not None:
        pixel = to_pixel(package.spot.pose_x, package.spot.pose_y)
        if pixel is not None:
            _draw_marker(draw, pixel[0], pixel[1], max(2, marker_radius // 2), _COLOR_SPOT)
    if package.robot is not None:
        pixel = to_pixel(package.robot.pose_x, package.robot.pose_y)
        if pixel is not None:
            _draw_marker(draw, pixel[0], pixel[1], marker_radius, _COLOR_ROBOT)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
