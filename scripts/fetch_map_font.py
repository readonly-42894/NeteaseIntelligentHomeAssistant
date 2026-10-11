#!/usr/bin/env python3
"""下载并校验集成内置的地图字体（Noto Sans SC Regular）。

字号渲染依赖内置字体以摆脱宿主机系统字体（HA 官方容器常无 CJK 字体）。
字体来源固定到 notofonts/noto-cjk 的某个提交，并校验 SHA-256，保证可复现。

用法：:

    python3 scripts/fetch_map_font.py

升级字体时修改下方的 ``_COMMIT`` 与 ``_SHA256`` 后重新执行。
"""

from __future__ import annotations

import hashlib
import os
import sys
import urllib.request

_COMMIT = "f8d157532fbfaeda587e826d4cd5b21a49186f7c"
_BASE = f"https://raw.githubusercontent.com/notofonts/noto-cjk/{_COMMIT}"

#: (远程路径, 目标文件名, 期望 SHA-256)
_FILES: tuple[tuple[str, str, str], ...] = (
    (
        "Sans/SubsetOTF/SC/NotoSansSC-Regular.otf",
        "NotoSansSC-Regular.otf",
        "faa6c9df652116dde789d351359f3d7e5d2285a2b2a1f04a2d7244df706d5ea9",
    ),
    (
        "Sans/LICENSE",
        "LICENSE.txt",
        "6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2",
    ),
)

_FONT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "custom_components",
    "netease_intelligent",
    "fonts",
)


def _download(url: str) -> bytes:
    """下载 URL 内容（固定提交的 raw 文件）。"""
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def main() -> int:
    os.makedirs(_FONT_DIR, exist_ok=True)
    for remote, name, expected in _FILES:
        print(f"下载 {remote} ...")
        data = _download(f"{_BASE}/{remote}")
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected:
            print(f"SHA-256 不匹配：期望 {expected}，实际 {digest}", file=sys.stderr)
            return 1
        with open(os.path.join(_FONT_DIR, name), "wb") as handle:
            handle.write(data)
        print(f"已写入 fonts/{name}（{len(data)} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
