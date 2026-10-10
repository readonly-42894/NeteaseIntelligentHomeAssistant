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

坐标约定：``MapData.physics_to_grid`` 得到栅格坐标；渲染时 **Y 轴翻转**，
使栅格第 0 行绘制在图片底部，与 App 视角一致。

本模块不含 Home Assistant 依赖，仅需 Pillow。
"""

from __future__ import annotations

import glob
import io
import math
import os
from collections.abc import Callable
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

# 标记物理尺寸（米）：MapRobotSpirit.ROBOT_SIZE / MapChargerSpirit.CHARGE_SIZE。
_ROBOT_SIZE_METERS: float = 0.35
_CHARGER_SIZE_METERS: float = 0.28

#: App drawable 资源目录（``res/drawable*`` 中地图相关图标/纹理，透明 PNG）。
_ASSETS_DIR: str = os.path.join(os.path.dirname(__file__), "map_assets")

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


def _room_palette_index(room_id: int) -> int:
    """房间调色板索引（``MapUtil.roomId2Index(roomId) % 6``）。"""
    return (room_id - ROOM_ID_BASE) % len(_ROOM_COLOR_NOT_ARRIVED)


def _cell_color(
    value: int, grid_x: int, grid_y: int, history: bool = False
) -> tuple[int, int, int] | None:
    """栅格像素值 → 颜色；``None`` 表示背景（不绘制）。

    ``history`` 为 ``True`` 时按清扫结果显示：已清扫地面 ``MAP_COLOR_ARRIVED``、
    已清扫房间实色 ``ROOM_COLOR_ARRIVED``；为 ``False`` 时与 App 实时视图一致
    （已清扫地面白色、房间一律棋盘格）。
    """
    if value == MAP_VALUE_BACKGROUND:
        return None
    if value == MAP_VALUE_OBSTACLE:
        return _COLOR_UNREACHABLE
    if MAP_VALUE_NOT_ARRIVED_ROOM_LOW <= value <= MAP_VALUE_ARRIVED_ROOM_HIGH:
        index = _room_palette_index(map_value_2_room_id(value))
        if history and value >= MAP_VALUE_ARRIVED_ROOM_LOW:
            return _ROOM_COLOR_ARRIVED[index]
        palette = _ROOM_COLOR_NOT_ARRIVED[index]
        return palette[((grid_x // 2) + (grid_y // 2)) % 2]
    if history and value == MAP_VALUE_ARRIVED:
        return _COLOR_ARRIVED
    # NotArrived / 实时模式下的 Arrived：统一白色。
    return _COLOR_NOT_ARRIVED


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
) -> None:
    """绘制白描边标签（锚点为几何中心）。"""
    draw.text(
        xy,
        text,
        font=font,
        fill=fill,
        stroke_width=2,
        stroke_fill=_COLOR_TEXT_STROKE,
        anchor="mm",
    )


def render_map(
    package: MapPackage,
    *,
    target_size: int = MAP_DEFAULT_TARGET_SIZE,
    history: bool = True,
) -> bytes:
    """把地图包渲染为 PNG 字节。

    ``package`` 需包含 ``map_data``（否则抛 ``ValueError``）；``target_size``
    为输出图片的最大边长（像素）。``history`` 为 ``True``（默认）时按清扫结果
    着色并绘制 ``MapHistory`` 轨迹；为 ``False`` 时保持 App 实时视图外观。
    """
    map_data = package.map_data
    if map_data is None or map_data.size_x <= 0 or map_data.size_y <= 0:
        raise ValueError("map package has no usable map data")

    min_x, max_x, min_y, max_y = _render_bounds(map_data, package)
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    cell = max(1, target_size // max(width, height))
    image = Image.new("RGB", (width * cell, height * cell), _COLOR_BACKGROUND)
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
            color = _cell_color(map_data.grid[row + grid_x], grid_x, grid_y, history)
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
                overlay_draw.polygon(pixels, fill=_COLOR_AREA_FILL)
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
            draw.line(points, fill=_COLOR_PATH, width=max(2, cell), joint="curve")

    # 虚拟墙：轮廓线 + 尺寸标签。
    if package.wall is not None and package.wall.items:
        wall_font = _load_font(max(12, cell * 2))
        for item in package.wall.items:
            pixels = _polygon_pixels(item, to_pixel)
            if len(pixels) < 3:
                continue
            draw.line(
                pixels + [pixels[0]],
                fill=_COLOR_WALL,
                width=max(2, int(round(cell * 0.6))),
            )
            center = _polygon_center(pixels)
            label = _area_size_label(item)
            if center is not None and label:
                _draw_label(draw, center, label, wall_font, _COLOR_WALL_TEXT)

    # 清扫区域：轮廓线 + 序号标签。
    if package.area is not None and package.area.items:
        area_font = _load_font(max(12, cell * 2))
        for index, item in enumerate(package.area.items, start=1):
            pixels = _polygon_pixels(item, to_pixel)
            if len(pixels) < 3:
                continue
            draw.line(pixels + [pixels[0]], fill=_COLOR_AREA_TEXT, width=max(1, cell // 2))
            center = _polygon_center(pixels)
            if center is not None:
                _draw_label(draw, center, f"{index:02d}", area_font, _COLOR_AREA_TEXT)

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

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
