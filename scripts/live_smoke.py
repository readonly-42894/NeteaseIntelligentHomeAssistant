"""在线冒烟测试：用 HAR 里抓到的 Cookie 凭证验证业务 API 客户端。

用法：:

    .venv/bin/python scripts/live_smoke.py [har 文件路径]

未传入路径时，默认取**当前工作目录**下最新的 ``*.har``。脚本从 HAR 中提取
``ONE_TOKEN`` / ``ONE_TOKEN_ID`` / ``UA-INFO`` 与 ``equipId``，
用仓库的 ``api.NeteaseIntelligentApiClient`` 打线上 ``3c.163.com``，
对比「抓包原始 UA-INFO」与「集成默认生成 UA-INFO」两种请求结果。

不写入任何文件，只打印结果。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import aiohttp

_REPO = Path(__file__).resolve().parents[1]
_PKG_DIR = _REPO / "custom_components" / "netease_intelligent"
_PKG = "netease_intelligent"

if _PKG not in sys.modules:
    _pkg = types.ModuleType(_PKG)
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules[_PKG] = _pkg


def _load(name: str):
    mod_name = f"{_PKG}.{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _PKG_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


const = _load("const")
models = _load("models")
api = _load("api")


def _find_har() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser()
    cwd = Path.cwd()
    hars = sorted(cwd.glob("*.har"), key=lambda p: p.stat().st_mtime)
    if not hars:
        raise SystemExit("未找到 HAR 文件，请显式传入路径")
    return hars[-1]


def _extract_creds(har_path: Path) -> dict[str, str]:
    with har_path.open() as f:
        har = json.load(f)
    creds: dict[str, str] = {}
    for entry in har["log"]["entries"]:
        req = entry["request"]
        for c in req.get("cookies", []):
            creds.setdefault(c["name"], c["value"])
        if "3c.163.com" in req["url"]:
            for q in req.get("queryString", []):
                if q["name"] == "equipId":
                    creds.setdefault("equipId", q["value"])
    for required in ("ONE_TOKEN", "ONE_TOKEN_ID", "UA-INFO", "equipId"):
        if required not in creds:
            raise SystemExit(f"HAR 缺少 {required}")
    return creds


async def main() -> None:
    har_path = _find_har()
    creds = _extract_creds(har_path)
    print(f"HAR: {har_path}")
    print(f"ONE_TOKEN_ID: {creds['ONE_TOKEN_ID'][:16]}...")
    print(f"ONE_TOKEN: {creds['ONE_TOKEN'][:24]}...")
    print(f"equipId: {creds['equipId']}")

    async with aiohttp.ClientSession() as session:
        captured = api.NeteaseIntelligentApiClient(
            session,
            token=creds["ONE_TOKEN"],
            token_id=creds["ONE_TOKEN_ID"],
            ua_info=creds["UA-INFO"],
        )
        generated = api.NeteaseIntelligentApiClient(
            session,
            token=creds["ONE_TOKEN"],
            token_id=creds["ONE_TOKEN_ID"],
        )
        eq = creds["equipId"]

        print("\n=== 抓包 UA-INFO (真机) getDeviceData ===")
        try:
            d = await captured.get_sweeper_data(eq)
            print(f"  battery={d.battery} work_mode={d.work_mode} "
                  f"charge_status={d.charge_status} fault_code={d.fault_code} "
                  f"water_control={d.water_control} wind_power={d.wind_power}")
            print(f"  电量百分比={const.sweeper_battery_percent(d.battery)}")
        except Exception as ex:
            print("  ERR:", ex)

        print("\n=== 集成默认 UA-INFO (Pixel5/Android13) getDeviceData ===")
        try:
            d = await generated.get_sweeper_data(eq)
            print(f"  battery={d.battery} work_mode={d.work_mode} "
                  f"charge_status={d.charge_status} fault_code={d.fault_code} "
                  f"water_control={d.water_control} wind_power={d.wind_power}")
            print(f"  电量百分比={const.sweeper_battery_percent(d.battery)}")
        except Exception as ex:
            print("  ERR:", ex)

        print("\n=== family/info ===")
        try:
            fi = await generated.get_family_info()
            print(f"  家庭数={len(fi.family_list)}")
            for fam in fi.family_list:
                print(f"    id={fam.id} name={fam.name!r} "
                      f"rooms={len(fam.room_list)} equips={len(fam.equips)}")
        except Exception as ex:
            print("  ERR:", ex)

        print("\n=== equip/list ===")
        try:
            el = await generated.get_equip_list()
            print(f"  设备数={len(el)}")
            for e in el:
                print(f"    id={e.id} name={e.name!r} model={e.model!r} "
                      f"productId={e.product_id} sn={e.sn!r} "
                      f"is_sweeper={e.is_sweeper}")
        except Exception as ex:
            print("  ERR:", ex)


if __name__ == "__main__":
    asyncio.run(main())
