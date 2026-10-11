"""把解析出的地图包渲染为 PNG（Pillow 实现）。

复刻 App spirit（``MapBaseSpirit`` / ``MapWallSpirit`` / ``MapAreaSpirit`` /
``MapChargerSpirit`` / ``MapRobotSpirit`` / ``MapSpotSpirit``）的上色与变换规则，
并直接复用 App 的 ``res/drawable`` 图标/纹理（见 ``map_assets/``），输出一张可直接
在 Home Assistant ``image`` 实体中展示的静态地图：

- 背景：底色 ``fill_4``（``#F9FAFC``）＋平铺 ``sweeper_bg_cell`` 纹理；
- 栅格底色：障碍 ``#717AE4``、未清扫地面白色；房间按 ``ROOM_COLOR_NOT_ARRIVED``
  6 组双色棋盘交替着色；
- 清扫结果（``history=True``，默认）：已清扫地面 ``MAP_COLOR_ARRIVED``、已清扫
  房间实色 ``ROOM_COLOR_ARRIVED``，并绘制 ``MapHistory`` 轨迹；
- 虚拟墙：平铺 ``sweeper_map_wall_cell`` 斜纹 ＋ ``#364866`` 边框 ＋ 尺寸标签；
- 清扫区域：``#66FFCA65`` 填充 ＋ ``#FF8F00`` 边框 ＋ 序号标签；
- 标记：机器人 ``sweeper_map_robot``（物理 0.35m、按朝向旋转）、充电座
  ``sweeper_map_charge``（0.28m、按朝向旋转）、定点 ``sweeper_map_spot``（底端锚定）；
- 房间名：白描边文字。
- ``dark=True``（可选）：整幅地图改用深色调色板（深色界面下不刺眼），墙斜纹
  纹理同步重着色；其余渲染流程完全一致。
- ``rotation``（可选，默认 ``0``）：把整幅地图（含轨迹、墙、区域、房间名、标记）
  逆时针旋转给定角度，用于把地图转到与真实户型/App 视角一致的朝向。

坐标约定：``MapData.physics_to_grid`` 得到栅格坐标；渲染时 **Y 轴翻转**，
使栅格第 0 行绘制在图片底部，与 App 视角一致。

本模块不含 Home Assistant 依赖，仅需 Pillow。
"""

from __future__ import annotations

import io
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFont

from .map_parser import (
    MAP_VALUE_ARRIVED,
    MAP_VALUE_ARRIVED_ROOM_HIGH,
    MAP_VALUE_ARRIVED_ROOM_LOW,
    MAP_VALUE_BACKGROUND,
    MAP_VALUE_NOT_ARRIVED_ROOM_LOW,
    MAP_VALUE_OBSTACLE,
    ROOM_ID_BASE,
    MapAreaItem,
    MapData,
    MapPackage,
    map_value_2_room_id,
)

__all__ = ["render_map", "MAP_DEFAULT_TARGET_SIZE"]

#: 输出图片的最大目标边长（像素），实际尺寸按栅格长宽比缩放。
MAP_DEFAULT_TARGET_SIZE: int = 800

# 颜色（RGB/A）——对应反编译 spirit 的颜色常量与 drawable 定义。
_COLOR_BACKGROUND: tuple[int, int, int] = (0xF9, 0xFA, 0xFC)  # fill_4 = gray_200（地图底色）
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

_COLOR_TEXT: tuple[int, int, int] = (0x22, 0x22, 0x22)  # 房间名文字色（R.color.txt_1）
_COLOR_TEXT_STROKE: tuple[int, int, int] = (0xFF, 0xFF, 0xFF)
# 已清扫区域（history 模式）：MAP_COLOR_ARRIVED 与 ROOM_COLOR_ARRIVED（6 实色）。
_COLOR_ARRIVED: tuple[int, int, int] = (0xD2, 0xD5, 0xFF)
_ROOM_COLOR_ARRIVED: tuple[tuple[int, int, int], ...] = (
    (0xA9, 0x9B, 0xDB),
    (0x73, 0xB3, 0xC5),
    (0xEB, 0x9D, 0x73),
    (0xE2, 0x77, 0x9C),
    (0xD2, 0xA9, 0xCD),
    (0x77, 0x7C, 0xB2),
)
# 叠加层：清扫轨迹、虚拟墙、清扫区域（取 App drawable 的精确颜色）。
_COLOR_PATH: tuple[int, int, int] = (0x93, 0xC2, 0xEE)
_COLOR_WALL: tuple[int, int, int] = (0x36, 0x48, 0x66)  # 虚拟墙边框（sweeper_map_wall_*）
_COLOR_WALL_TEXT: tuple[int, int, int] = (0x36, 0x48, 0x66)  # MapWallSpirit.WALL_TEXT_COLOR
_COLOR_AREA_TEXT: tuple[int, int, int] = (0xFF, 0x8F, 0x00)  # 区域边框/标签 AREA_TEXT_COLOR
_COLOR_AREA_FILL: tuple[int, int, int, int] = (0xFF, 0xCA, 0x65, 0x66)  # 区域填充 #66FFCA65

# 深色调色板（``dark=True``）：在保持色相的前提下整体降低明度，避免在深色界面
# 中出现刺眼的大面积白色地面；墙斜纹改为浅色（原图深藏青在深色底上不可见）。
_COLOR_DARK_BACKGROUND: tuple[int, int, int] = (0x1C, 0x1C, 0x1E)
_COLOR_DARK_UNREACHABLE: tuple[int, int, int] = (0x5B, 0x63, 0xCC)
_COLOR_DARK_NOT_ARRIVED: tuple[int, int, int] = (0x2A, 0x2A, 0x2E)
_ROOM_COLOR_DARK_NOT_ARRIVED: tuple[tuple[tuple[int, int, int], ...], ...] = (
    ((0x4A, 0x43, 0x6B), (0x5E, 0x56, 0x82)),
    ((0x33, 0x53, 0x5E), (0x42, 0x68, 0x74)),
    ((0x6E, 0x48, 0x33), (0x88, 0x5A, 0x42)),
    ((0x6B, 0x37, 0x49), (0x84, 0x47, 0x5B)),
    ((0x5E, 0x4B, 0x5C), (0x74, 0x5E, 0x72)),
    ((0x39, 0x3C, 0x58), (0x49, 0x4D, 0x6E)),
)
_COLOR_DARK_TEXT: tuple[int, int, int] = (0xE5, 0xE5, 0xE5)
_COLOR_DARK_TEXT_STROKE: tuple[int, int, int] = (0x1C, 0x1C, 0x1E)
_COLOR_DARK_ARRIVED: tuple[int, int, int] = (0x36, 0x40, 0x6B)
_ROOM_COLOR_DARK_ARRIVED: tuple[tuple[int, int, int], ...] = (
    (0x4A, 0x43, 0x6B),
    (0x33, 0x53, 0x5E),
    (0x6E, 0x48, 0x33),
    (0x6B, 0x37, 0x49),
    (0x5E, 0x4B, 0x5C),
    (0x39, 0x3C, 0x58),
)
_COLOR_DARK_PATH: tuple[int, int, int] = (0x8A, 0xB6, 0xE8)
_COLOR_DARK_WALL: tuple[int, int, int] = (0x8F, 0xA6, 0xCC)
_COLOR_DARK_WALL_TEXT: tuple[int, int, int] = (0xC8, 0xD6, 0xEE)
_COLOR_DARK_AREA_TEXT: tuple[int, int, int] = (0xFF, 0x8F, 0x00)
_COLOR_DARK_AREA_FILL: tuple[int, int, int, int] = (0xFF, 0xCA, 0x65, 0x66)


@dataclass(frozen=True)
class _Palette:
    """一套地图配色；浅/深两套在渲染流程中同构替换。"""

    background: tuple[int, int, int]
    unreachable: tuple[int, int, int]
    not_arrived: tuple[int, int, int]
    room_not_arrived: tuple[tuple[tuple[int, int, int], ...], ...]
    text: tuple[int, int, int]
    text_stroke: tuple[int, int, int]
    arrived: tuple[int, int, int]
    room_arrived: tuple[tuple[int, int, int], ...]
    path: tuple[int, int, int]
    wall: tuple[int, int, int]
    wall_text: tuple[int, int, int]
    area_text: tuple[int, int, int]
    area_fill: tuple[int, int, int, int]
    #: 墙斜纹纹理的重着色；``None`` 表示沿用 ``wall_cell.png`` 原始颜色。
    wall_stripe: tuple[int, int, int] | None


#: 浅色（默认）调色板：即 App 原生配色。
_LIGHT_PALETTE = _Palette(
    background=_COLOR_BACKGROUND,
    unreachable=_COLOR_UNREACHABLE,
    not_arrived=_COLOR_NOT_ARRIVED,
    room_not_arrived=_ROOM_COLOR_NOT_ARRIVED,
    text=_COLOR_TEXT,
    text_stroke=_COLOR_TEXT_STROKE,
    arrived=_COLOR_ARRIVED,
    room_arrived=_ROOM_COLOR_ARRIVED,
    path=_COLOR_PATH,
    wall=_COLOR_WALL,
    wall_text=_COLOR_WALL_TEXT,
    area_text=_COLOR_AREA_TEXT,
    area_fill=_COLOR_AREA_FILL,
    wall_stripe=None,
)

#: 深色调色板。
_DARK_PALETTE = _Palette(
    background=_COLOR_DARK_BACKGROUND,
    unreachable=_COLOR_DARK_UNREACHABLE,
    not_arrived=_COLOR_DARK_NOT_ARRIVED,
    room_not_arrived=_ROOM_COLOR_DARK_NOT_ARRIVED,
    text=_COLOR_DARK_TEXT,
    text_stroke=_COLOR_DARK_TEXT_STROKE,
    arrived=_COLOR_DARK_ARRIVED,
    room_arrived=_ROOM_COLOR_DARK_ARRIVED,
    path=_COLOR_DARK_PATH,
    wall=_COLOR_DARK_WALL,
    wall_text=_COLOR_DARK_WALL_TEXT,
    area_text=_COLOR_DARK_AREA_TEXT,
    area_fill=_COLOR_DARK_AREA_FILL,
    wall_stripe=_COLOR_DARK_WALL,
)

# 标记物理尺寸（米）：MapRobotSpirit.ROBOT_SIZE / MapChargerSpirit.CHARGE_SIZE。
_ROBOT_SIZE_METERS: float = 0.35
_CHARGER_SIZE_METERS: float = 0.28

#: App drawable 资源目录（``res/drawable*`` 中地图相关图标/纹理，透明 PNG）。
_ASSETS_DIR: str = os.path.join(os.path.dirname(__file__), "map_assets")

#: 随集成分发的内置字体：Noto Sans SC（SIL OFL 1.1，见 ``fonts/LICENSE.txt``）。
#: HA 官方容器基于 Alpine，不装任何字体包，也无字体发现机制；因此 CJK 文字必须依赖
#: 集成自带的字体，不能指望宿主系统字体（否则房间名会渲染成豆腐块）。
_FONT_DIR: str = os.path.join(os.path.dirname(__file__), "fonts")
_BUNDLED_FONT: str = os.path.join(_FONT_DIR, "NotoSansSC-Regular.otf")

#: 全背景时回退的居中窗口宽度（米），对应 App 的 MAP_DEFAULE_WIDTH。
_FALLBACK_WINDOW_METERS: float = 3.0


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """加载支持中文的字体：内置 Noto Sans SC；缺失或损坏时回退 Pillow 默认字体。"""
    try:
        return ImageFont.truetype(_BUNDLED_FONT, size)
    except OSError:
        try:
            return ImageFont.load_default(size)
        except TypeError:  # 旧版 Pillow 的 load_default 不接受 size
            return ImageFont.load_default()


def _room_palette_index(room_id: int) -> int:
    """房间调色板索引（``MapUtil.roomId2Index(roomId) % 6``）。"""
    return (room_id - ROOM_ID_BASE) % len(_ROOM_COLOR_NOT_ARRIVED)


def _cell_color(
    value: int,
    grid_x: int,
    grid_y: int,
    history: bool = False,
    palette: _Palette = _LIGHT_PALETTE,
) -> tuple[int, int, int] | None:
    """栅格像素值 → 颜色；``None`` 表示背景（不绘制）。

    ``history`` 为 ``True`` 时按清扫结果显示：已清扫地面 ``MAP_COLOR_ARRIVED``、
    已清扫房间实色 ``ROOM_COLOR_ARRIVED``；为 ``False`` 时与 App 实时视图一致
    （已清扫地面白色、房间一律棋盘格）。``palette`` 指定配色（浅/深）。
    """
    if value == MAP_VALUE_BACKGROUND:
        return None
    if value == MAP_VALUE_OBSTACLE:
        return palette.unreachable
    if MAP_VALUE_NOT_ARRIVED_ROOM_LOW <= value <= MAP_VALUE_ARRIVED_ROOM_HIGH:
        index = _room_palette_index(map_value_2_room_id(value))
        if history and value >= MAP_VALUE_ARRIVED_ROOM_LOW:
            return palette.room_arrived[index]
        pair = palette.room_not_arrived[index]
        return pair[((grid_x // 2) + (grid_y // 2)) % 2]
    if history and value == MAP_VALUE_ARRIVED:
        return palette.arrived
    # NotArrived / 实时模式下的 Arrived：统一地面色。
    return palette.not_arrived


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


@lru_cache(maxsize=None)
def _load_asset(name: str) -> Image.Image:
    """加载 App 地图 drawable 资源（统一转为 RGBA；调用方不得修改返回对象）。"""
    return Image.open(os.path.join(_ASSETS_DIR, name)).convert("RGBA")


def _recolor_tile(tile: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """把纹理的 RGB 统一替换为 ``color``（保留 alpha），用于深色模式重着色。"""
    tinted = Image.new("RGBA", tile.size, (*color, 0xFF))
    tinted.putalpha(tile.getchannel("A"))
    return tinted


def _composite(image: Image.Image, layer: Image.Image, xy: tuple[int, int]) -> Image.Image:
    """把 RGBA ``layer`` 以自身 alpha 叠加到 ``image``（返回新的 RGB 图像）。"""
    base = image.convert("RGBA")
    base.paste(layer, xy, layer.getchannel("A"))
    return base.convert("RGB")


def _tile_image(tile: Image.Image, size: tuple[int, int], tile_px: int) -> Image.Image:
    """把 ``tile`` 缩放为 ``tile_px`` 见方后平铺铺满 ``size``（RGBA，未覆盖处透明）。"""
    tile_px = max(1, tile_px)
    scaled = tile.resize((tile_px, tile_px), Image.LANCZOS)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    for y in range(0, size[1], tile_px):
        for x in range(0, size[0], tile_px):
            out.paste(scaled, (x, y))
    return out


def _tile_background(image: Image.Image, cell: int) -> Image.Image:
    """铺 App 地图背景（``sweeper_bg_map``：底色 ``fill_4`` + 平铺 ``sweeper_bg_cell``）。"""
    bg = _tile_image(
        _load_asset("bg_cell.png"), image.size, max(4, int(round(cell * 6)))
    )
    return _composite(image, bg, (0, 0))


def _fill_polygon_tiled(
    image: Image.Image,
    pixels: list[tuple[float, float]],
    tile: Image.Image,
    tile_px: int,
) -> Image.Image:
    """用平铺纹理填充多边形（App 虚拟墙 ``sweeper_map_wall_unselected``）。"""
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    x0, y0 = int(math.floor(min(xs))), int(math.floor(min(ys)))
    x1, y1 = int(math.ceil(max(xs))) + 1, int(math.ceil(max(ys))) + 1
    width, height = x1 - x0, y1 - y0
    if width <= 0 or height <= 0:
        return image
    patch = _tile_image(tile, (width, height), tile_px)
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).polygon([(p[0] - x0, p[1] - y0) for p in pixels], fill=255)
    patch.putalpha(ImageChops.multiply(patch.getchannel("A"), mask))
    return _composite(image, patch, (x0, y0))


def _paste_glyph(
    image: Image.Image,
    xy: tuple[float, float],
    glyph: Image.Image,
    size_px: int,
    angle_deg: float = 0.0,
    *,
    anchor_bottom: bool = False,
) -> Image.Image:
    """在 ``xy`` 处贴一张方形 App 图标（返回新的 RGB 图像）。

    ``angle_deg`` 为逆时针角度（Pillow 约定，对应 App ``canvas.rotate(-deg(phi))``）；
    ``anchor_bottom=True`` 时图标底边对齐 ``xy``（定点图钉），否则几何中心对齐。
    """
    side = max(1, int(round(size_px)))
    tile = glyph.resize((side, side), Image.LANCZOS)
    if angle_deg:
        tile = tile.rotate(angle_deg, expand=True, resample=Image.BICUBIC)
    x, y = xy
    if anchor_bottom:
        pos = (x - tile.width / 2, y - tile.height)
    else:
        pos = (x - tile.width / 2, y - tile.height / 2)
    return _composite(image, tile, (int(round(pos[0])), int(round(pos[1]))))


def _marker_radius(map_data: MapData, cell: int, size_meters: float) -> int:
    """按标记物理尺寸（米）换算像素半径（``size/2/resolution*cell``）。"""
    resolution = map_data.resolution or 1.0
    return max(3, int(round(size_meters / 2 / resolution * cell)))


def _polygon_pixels(
    item: MapAreaItem, to_pixel: Callable[[float, float], tuple[float, float] | None]
) -> list[tuple[float, float]]:
    """墙/区域项的物理顶点 → 像素坐标（丢弃越界点）。"""
    pixels: list[tuple[float, float]] = []
    for point in item.points:
        pixel = to_pixel(point.x, point.y)
        if pixel is not None:
            pixels.append(pixel)
    return pixels


def _polygon_center(pixels: list[tuple[float, float]]) -> tuple[float, float] | None:
    """多边形顶点像素坐标的均值（近似质心）。"""
    if not pixels:
        return None
    return (
        sum(p[0] for p in pixels) / len(pixels),
        sum(p[1] for p in pixels) / len(pixels),
    )


def _area_size_label(item: MapAreaItem) -> str | None:
    """按物理包围盒生成尺寸标签（App ``WALL_TEXT_FORMAT_LENGTH`` 格式）。"""
    xs = [point.x for point in item.points]
    ys = [point.y for point in item.points]
    if not xs or not ys:
        return None
    width_m = max(xs) - min(xs)
    height_m = max(ys) - min(ys)
    if width_m <= 0.0 or height_m <= 0.0:
        return None
    return f"{width_m:.1f}m×{height_m:.1f}m"


def _draw_label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    *,
    stroke: tuple[int, int, int] = _COLOR_TEXT_STROKE,
) -> None:
    """绘制描边标签（锚点为几何中心）；默认白描边（浅色模式）。"""
    draw.text(
        xy,
        text,
        font=font,
        fill=fill,
        stroke_width=2,
        stroke_fill=stroke,
        anchor="mm",
    )


def render_map(
    package: MapPackage,
    *,
    target_size: int = MAP_DEFAULT_TARGET_SIZE,
    history: bool = True,
    dark: bool = False,
    rotation: int = 0,
) -> bytes:
    """把地图包渲染为 PNG 字节。

    ``package`` 需包含 ``map_data``（否则抛 ``ValueError``）；``target_size``
    为输出图片的最大边长（像素）。``history`` 为 ``True``（默认）时按清扫结果
    着色并绘制 ``MapHistory`` 轨迹；为 ``False`` 时保持 App 实时视图外观。
    ``dark`` 为 ``True`` 时使用深色调色板（深色界面下更柔和）。``rotation``
    为整幅地图逆时针旋转的角度（90° 步长，``0`` 表示不旋转）。
    """
    map_data = package.map_data
    if map_data is None or map_data.size_x <= 0 or map_data.size_y <= 0:
        raise ValueError("map package has no usable map data")

    palette = _DARK_PALETTE if dark else _LIGHT_PALETTE
    min_x, max_x, min_y, max_y = _render_bounds(map_data, package)
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    cell = max(1, target_size // max(width, height))
    image = Image.new("RGB", (width * cell, height * cell), palette.background)
    # 背景：App ``sweeper_bg_map``（底色 ``fill_4`` + 平铺 ``sweeper_bg_cell``）。
    image = _tile_background(image, cell)
    draw = ImageDraw.Draw(image)

    def to_pixel(physics_x: float, physics_y: float) -> tuple[float, float] | None:
        grid_x, grid_y = map_data.physics_to_grid(physics_x, physics_y)
        if not (0 <= grid_x < map_data.size_x and 0 <= grid_y < map_data.size_y):
            return None
        return (
            (grid_x - min_x + 0.5) * cell,
            (max_y - grid_y + 0.5) * cell,
        )

    # 栅格底色：Y 轴翻转，使栅格第 0 行位于图片底部。
    for grid_y in range(min_y, max_y + 1):
        row = grid_y * map_data.size_x
        pixel_y = (max_y - grid_y) * cell
        for grid_x in range(min_x, max_x + 1):
            color = _cell_color(
                map_data.grid[row + grid_x], grid_x, grid_y, history, palette
            )
            if color is None:
                continue
            pixel_x = (grid_x - min_x) * cell
            draw.rectangle(
                [pixel_x, pixel_y, pixel_x + cell - 1, pixel_y + cell - 1],
                fill=color,
            )

    # 虚拟墙：App ``sweeper_map_wall_unselected``——平铺斜纹纹理填充。
    if package.wall is not None and package.wall.items:
        wall_tile = _load_asset("wall_cell.png")
        if palette.wall_stripe is not None:
            wall_tile = _recolor_tile(wall_tile, palette.wall_stripe)
        wall_tile_px = max(4, int(round(cell * 6)))
        for item in package.wall.items:
            pixels = _polygon_pixels(item, to_pixel)
            if len(pixels) >= 3:
                image = _fill_polygon_tiled(image, pixels, wall_tile, wall_tile_px)
        draw = ImageDraw.Draw(image)

    # 清扫区域：App ``sweeper_map_area_unselected``——半透明实色填充（RGBA 叠加层）。
    if package.area is not None and package.area.items:
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for item in package.area.items:
            pixels = _polygon_pixels(item, to_pixel)
            if len(pixels) >= 3:
                overlay_draw.polygon(pixels, fill=palette.area_fill)
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(image)

    # 清扫轨迹（``MapHistory``）：仅在 history 模式且点数足够时绘制。
    if history and package.history is not None and len(package.history.items) >= 2:
        points = [
            pixel
            for pixel in (
                to_pixel(item.pose_x, item.pose_y)
                for item in package.history.items
            )
            if pixel is not None
        ]
        if len(points) >= 2:
            draw.line(points, fill=palette.path, width=max(2, cell), joint="curve")

    # 虚拟墙：轮廓线 + 尺寸标签。
    if package.wall is not None and package.wall.items:
        wall_font = _load_font(max(12, cell * 2))
        for item in package.wall.items:
            pixels = _polygon_pixels(item, to_pixel)
            if len(pixels) < 3:
                continue
            draw.line(
                pixels + [pixels[0]],
                fill=palette.wall,
                width=max(2, int(round(cell * 0.6))),
            )
            center = _polygon_center(pixels)
            label = _area_size_label(item)
            if center is not None and label:
                _draw_label(
                    draw,
                    center,
                    label,
                    wall_font,
                    palette.wall_text,
                    stroke=palette.text_stroke,
                )

    # 清扫区域：轮廓线 + 序号标签。
    if package.area is not None and package.area.items:
        area_font = _load_font(max(12, cell * 2))
        for index, item in enumerate(package.area.items, start=1):
            pixels = _polygon_pixels(item, to_pixel)
            if len(pixels) < 3:
                continue
            draw.line(
                pixels + [pixels[0]],
                fill=palette.area_text,
                width=max(1, cell // 2),
            )
            center = _polygon_center(pixels)
            if center is not None:
                _draw_label(
                    draw,
                    center,
                    f"{index:02d}",
                    area_font,
                    palette.area_text,
                    stroke=palette.text_stroke,
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
                fill=palette.text,
                stroke_width=max(1, cell // 2),
                stroke_fill=palette.text_stroke,
                anchor="mm",
            )

    # 标记：直接贴 App 图标（机器人/充电座按朝向旋转，定点底端锚定）。
    if package.charge is not None:
        pixel = to_pixel(package.charge.pose_x, package.charge.pose_y)
        if pixel is not None:
            image = _paste_glyph(
                image,
                pixel,
                _load_asset("charge.png"),
                2 * _marker_radius(map_data, cell, _CHARGER_SIZE_METERS),
                math.degrees(package.charge.pose_phi),
            )
    if package.spot is not None:
        pixel = to_pixel(package.spot.pose_x, package.spot.pose_y)
        if pixel is not None:
            image = _paste_glyph(
                image,
                pixel,
                _load_asset("spot.png"),
                max(8, int(round(cell * 4))),
                anchor_bottom=True,
            )
    if package.robot is not None:
        pixel = to_pixel(package.robot.pose_x, package.robot.pose_y)
        if pixel is not None:
            image = _paste_glyph(
                image,
                pixel,
                _load_asset("robot.png"),
                2 * _marker_radius(map_data, cell, _ROBOT_SIZE_METERS),
                math.degrees(package.robot.pose_phi),
            )

    # 地图朝向：整幅旋转（含轨迹/墙/区域/房间名/标记）。90° 倍数时 Pillow 走
    # 无损转置，无插值损失；其余角度用底色填充新出现的角。
    angle = rotation % 360
    if angle:
        image = image.rotate(
            angle, expand=True, resample=Image.BICUBIC, fillcolor=palette.background
        )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
