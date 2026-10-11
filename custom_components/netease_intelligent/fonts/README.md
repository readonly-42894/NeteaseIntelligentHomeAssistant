# 内置地图字体

`NotoSansSC-Regular.otf` 是本集成的内置 CJK 字体，供 `map_render.py` 渲染房间名、
尺寸标签等文字使用。宿主机（尤其 Home Assistant 官方容器）通常不带 CJK 字体，
仅依赖系统字体会把中文渲染成豆腐块，因此字体随集成一起分发。

## 来源与许可

| 项 | 值 |
|----|----|
| 字体族 | Noto Sans SC（Regular） |
| 上游仓库 | <https://github.com/notofonts/noto-cjk> |
| 文件路径 | `Sans/SubsetOTF/SC/NotoSansSC-Regular.otf` |
| 固定提交 | `f8d157532fbfaeda587e826d4cd5b21a49186f7c` |
| SHA-256 | `faa6c9df652116dde789d351359f3d7e5d2285a2b2a1f04a2d7244df706d5ea9` |
| 许可 | SIL Open Font License 1.1（见 `LICENSE.txt`，随字体一并分发） |

## 更新

字体已固定到上述提交并校验 SHA-256。需要升级时修改 `scripts/fetch_map_font.py`
中的 `_COMMIT` / `_SHA256` 后重新执行：

```bash
python3 scripts/fetch_map_font.py
```
