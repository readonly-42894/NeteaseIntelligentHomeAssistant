#!/usr/bin/env python3
"""网易智造「长连接」推送通道探针（只监听，不向设备下发控制指令）。

按官方 App 的实抓协议复刻一个最小 ``Socket.IO`` 客户端，用于验证/观察
``wss://3c.163.com`` 上的设备推送。协议来源：

- 反编译：``com.yy.httpproxy.socketio.SocketIOProxyClient``
  （Engine.IO v3、仅 WebSocket、客户端主动心跳）
- 反编译：``com.netease.intelligent.kernel.util.EventUtil`` +
  ``kernel.config.Action`` + ``sweeper.modules.home.HomeActivity``
  （进入/离开设备页的 ``event/view`` 开始/关闭推送）
- 实抓 HAR：``wss://3c.163.com/socket.io/?EIO=3&transport=websocket``
  （注册序列与推送帧结构；服务端推送事件名为 ``"p"``）

协议要点：

1. 连接：``GET wss://3c.163.com/socket.io/?EIO=3&transport=websocket``，
   **不携带任何 Cookie / Header**；服务端证书需放宽校验（官方客户端亦信任所有证书）。
2. 握手：收 Engine.IO open ``0{...}`` → 发 ``40``（Socket.IO connect）→ 收 ``40``。
3. 注册：发 ``42["pushId",{id,platform,topics,lastPacketIds}]``（服务端回显确认），
   再发 ``42["setTags",[...]]``、``42["unbindUid"]``、
   ``42["bindUid",{"uid":"r_intelligent_<pid>"}]`` 绑定登录用户。
4. 开始/关闭推送：登录后调用 HTTP
   ``GET /ai-app/app/event/view?pushId=&productId=&eventType=&equipId=``
   （需 Cookie 鉴权，普通 REST、与其它 ``/ai-app/*`` 一致）。
   官方在**进入设备页**发 ``eventType=1``（开始推送该设备事件）、
   **离开设备页**发 ``eventType=2``（关闭推送）；本探针在开始监听前发 ``1``、
   结束后发 ``2``。``productId`` 为扫地机品类 id（RV02=9、RV03=26）。
5. 心跳：客户端每 ``--ping`` 秒发 Engine.IO ping ``2``、服务端回 ``3``
   （不发心跳时连接约 60s 后被服务端断开）。
6. 推送：``42["p",{"android":{"payload":{"msgType":..,"data":{"opType":10,
   "json":{"eventType":1,"subtype":..,"type":..,"payload":{..}}}}}}]``，
   ``subtype`` 1=设备状态 / 2=地图 / 3=轨迹；``type`` 为 productId。

``uid`` 构造 = ``ENV + "_" + APP_NAME + "_" + pid``。release 下
``ENV = "r"``（``AlcsConstant.MODE_VALUE_READ``）、
``APP_NAME = "intelligent"``（``R.string.host_push_product_name``）。
``pid`` 取自账号信息：``GET /ai-app/account/info?from=1`` 的 ``UserInfo.pid``
（即 OpenAPI 的 ``opId=getAccountInfo``），或从 HAR 中已登录请求的业务参数读取。

用法：

    # 仅监听（无 event/view）
    .venv/bin/python scripts/push_probe.py <pid> --watch 120 --ping 20

    # 完整复刻官方「开始/关闭推送」：从 HAR 提取 Cookie 鉴权
    .venv/bin/python scripts/push_probe.py <pid> --har <har 文件路径> \
        --equip-id <equipId> --product-id 26

返回码：``0`` = 已连接并注册，``2`` = WebSocket 连接失败，``3`` = 握手/注册失败。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import ssl
import sys

import aiohttp

# 生产推送域名（release）。alpha/beta 为 t2.3c.163.com，develop 为 t.3c.163.com。
HOST = "wss://3c.163.com/socket.io/"
HTTP_HOST = "https://3c.163.com"
EVENT_VIEW_PATH = "/ai-app/app/event/view"
USER_AGENT = "Intelligent/ntes3c/5.3.5/release/Release"

ENV = "r"
APP_NAME = "intelligent"
APP_VERSION = "5.3.5"
APP_SOURCE = "Release"
PLATFORM = "android"
TOPICS = ["noti", "event"]

# event/view 的 eventType（EventUtil.EVENT_TYPE_*）。
EVENT_TYPE_ENTRY_PAGE = 1  # 进入设备页：开始推送
EVENT_TYPE_EXIT_PAGE = 2  # 离开设备页：关闭推送

SUBTYPES = {
    1: "设备状态(Sweeper_Push_Info)",
    2: "地图(Sweeper_Push_Map)",
    3: "轨迹(Sweeper_Push_History)",
}


def make_push_id() -> str:
    """模拟 ``RandomPushIdGenerator``：``BigInteger(130bit).toString(32)``。"""
    return "".join(random.choices("0123456789abcdefghijklmnopqrstuv", k=26))


def make_tags() -> list[str]:
    """与官方 ``PushManager`` 一致的四元 tag 列表。"""
    return [APP_VERSION, f"{ENV}_{APP_NAME}", f"{ENV}_{APP_NAME}_android", APP_SOURCE]


def load_cookie_from_har(path: str) -> str:
    """从 HAR 中首个带 Cookie 的请求提取 ``name=value; ...`` 串。"""
    with open(path, encoding="utf-8") as fp:
        har = json.load(fp)
    for entry in har["log"]["entries"]:
        cookies = entry.get("request", {}).get("cookies") or []
        if cookies:
            return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    return ""


async def send_event_view(
    session: aiohttp.ClientSession,
    ctx: ssl.SSLContext,
    cookie: str,
    push_id: str,
    product_id: int,
    equip_id: str,
    event_type: int,
) -> None:
    """调用 ``event/view`` 开始（1）/关闭（2）该设备的推送。"""
    url = f"{HTTP_HOST}{EVENT_VIEW_PATH}"
    params = {
        "pushId": push_id,
        "productId": product_id,
        "eventType": event_type,
        "equipId": equip_id,
    }
    headers = {"Cookie": cookie, "User-Agent": USER_AGENT}
    action = "开始推送" if event_type == EVENT_TYPE_ENTRY_PAGE else "关闭推送"
    try:
        async with session.get(url, params=params, headers=headers, ssl=ctx) as resp:
            text = await resp.text()
            print(
                f"* event/view({action} eventType={event_type}) -> "
                f"{resp.status} {text[:200]}",
                flush=True,
            )
    except Exception as err:  # noqa: BLE001
        print(f"!! event/view({action}) 失败: {err!r}", flush=True)


def handle_push(frame: str) -> None:
    """解析 ``42["p", {...}]`` 并打印关键字段。"""
    try:
        parsed = json.loads(frame[2:])
    except ValueError:
        return
    if not (isinstance(parsed, list) and parsed and parsed[0] in ("p", "push")):
        return
    env = parsed[1] if len(parsed) > 1 and isinstance(parsed[1], dict) else {}
    # 正文可能在 android.payload 下，也可能直接是 payload。
    body = (env.get("android") or {}).get("payload") or env
    data = body.get("data") or {}
    inner = data.get("json") or {}
    subtype = inner.get("subtype")
    equipment = inner.get("payload") or {}
    print(
        "★ PUSH 事件名=%r msgType=%r opType=%r eventType=%r subtype=%r type=%r"
        % (
            parsed[0],
            body.get("msgType"),
            data.get("opType"),
            inner.get("eventType"),
            subtype,
            inner.get("type"),
        ),
        flush=True,
    )
    print("   subtype 说明:", SUBTYPES.get(subtype, "?"), flush=True)
    print("   payload:", json.dumps(equipment, ensure_ascii=False)[:1000], flush=True)


async def run(args: argparse.Namespace) -> int:
    pid = args.pid
    watch = args.watch
    ping = args.ping
    push_id = make_push_id()
    uid = f"{ENV}_{APP_NAME}_{pid}"
    url = f"{HOST}?EIO=3&transport=websocket"

    event_view = bool(args.equip_id) and not args.no_event_view
    cookie = args.cookie or (load_cookie_from_har(args.har) if args.har else "")
    if event_view and not cookie:
        print("!! 需要 --har 或 --cookie 才能调用 event/view（已跳过）", flush=True)
        event_view = False

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    print(f"* pushId={push_id}\n* uid={uid}\n* {url}", flush=True)
    if event_view:
        print(
            f"* event/view: equipId={args.equip_id} productId={args.product_id}",
            flush=True,
        )

    async with aiohttp.ClientSession() as session:
        try:
            ws = await session.ws_connect(
                url,
                ssl=ctx,
                heartbeat=None,
                timeout=aiohttp.ClientWSTimeout(ws_close=25),
            )
        except Exception as err:  # noqa: BLE001
            print(f"!! WebSocket 连接失败: {err!r}", flush=True)
            return 2

        connected = False
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        deadline = t0 + watch

        async def send(frame: str) -> None:
            print(f"[+{loop.time() - t0:7.2f}s] >> {frame[:200]}", flush=True)
            await ws.send_str(frame)

        async def ping_loop() -> None:
            while not ws.closed:
                await asyncio.sleep(ping)
                if ws.closed:
                    return
                await send("2")

        ping_task = asyncio.create_task(ping_loop())
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    print(f"* 监听 {watch}s 结束", flush=True)
                    break
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
                except asyncio.TimeoutError:
                    print(f"* 监听 {watch}s 结束", flush=True)
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    print(f"* 帧类型 {msg.type!r} data={msg.data!r}", flush=True)
                    if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                        print(f"* 关闭 code={ws.close_code}", flush=True)
                        break
                    continue

                frame = msg.data
                if frame.startswith("0{"):
                    await send("40")
                elif frame.startswith("40") and not connected:
                    connected = True
                    await send(
                        "42"
                        + json.dumps(
                            [
                                "pushId",
                                {
                                    "id": push_id,
                                    "platform": PLATFORM,
                                    "topics": TOPICS,
                                    "lastPacketIds": {"noti": "0"},
                                },
                            ]
                        )
                    )
                    await send("42" + json.dumps(["setTags", make_tags()]))
                    await send('42["unbindUid"]')
                    await send("42" + json.dumps(["bindUid", {"uid": uid}]))
                    print(f"* 已注册并 bindUid，监听 {watch}s（被动）", flush=True)
                    if event_view:
                        await send_event_view(
                            session,
                            ctx,
                            cookie,
                            push_id,
                            args.product_id,
                            args.equip_id,
                            EVENT_TYPE_ENTRY_PAGE,
                        )
                elif frame.startswith('42["p"') or frame.startswith('42["push"'):
                    print(f"[+{loop.time() - t0:7.2f}s] << {frame[:220]}", flush=True)
                    handle_push(frame)
                elif frame.startswith("2"):
                    await send("3")
                elif frame.startswith("1"):
                    print("* Socket.IO disconnect", flush=True)
                    break
                else:
                    print(f"[+{loop.time() - t0:7.2f}s] << {frame[:200]}", flush=True)

            if event_view and not ws.closed:
                await send_event_view(
                    session,
                    ctx,
                    cookie,
                    push_id,
                    args.product_id,
                    args.equip_id,
                    EVENT_TYPE_EXIT_PAGE,
                )
        finally:
            ping_task.cancel()
            await ws.close()

        print(f"* 结束: connected={connected}", flush=True)
        return 0 if connected else 3


def main() -> int:
    parser = argparse.ArgumentParser(
        description="网易智造长连接推送通道探针（被动监听）",
    )
    parser.add_argument("pid", type=int, help="账号 pid（见 getAccountInfo）")
    parser.add_argument("--watch", type=int, default=120, help="总监听秒数（默认 120）")
    parser.add_argument("--ping", type=int, default=20, help="心跳间隔秒数（默认 20）")
    parser.add_argument(
        "--equip-id",
        default="",
        help="设备 equipId；给出后调用 event/view 复刻官方开始/关闭推送",
    )
    parser.add_argument(
        "--product-id",
        type=int,
        default=26,
        help="event/view 的 productId（RV02=9、RV03=26，默认 26）",
    )
    parser.add_argument("--har", default="", help="从该 HAR 提取 Cookie（event/view 鉴权）")
    parser.add_argument("--cookie", default="", help="直接指定 Cookie 串（event/view 鉴权）")
    parser.add_argument(
        "--no-event-view",
        action="store_true",
        help="即使给了 --equip-id 也不调用 event/view",
    )
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
