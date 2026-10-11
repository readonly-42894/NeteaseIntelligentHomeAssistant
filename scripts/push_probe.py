#!/usr/bin/env python3
"""网易智造「长连接」推送通道探针（只监听，不向设备下发控制指令）。

按官方 App 的实抓协议复刻一个最小 ``Socket.IO`` 客户端，用于验证/观察
``wss://3c.163.com`` 上的设备推送。协议来源：

- 反编译：``com.yy.httpproxy.socketio.SocketIOProxyClient``
  （Engine.IO v3、仅 WebSocket、客户端主动心跳）
- 实抓 HAR：``wss://3c.163.com/socket.io/?EIO=3&transport=websocket``
  （注册序列与推送帧结构；服务端推送事件名为 ``"p"``）

协议要点：

1. 连接：``GET wss://3c.163.com/socket.io/?EIO=3&transport=websocket``，
   **不携带任何 Cookie / Header**；服务端证书需放宽校验（官方客户端亦信任所有证书）。
2. 握手：收 Engine.IO open ``0{...}`` → 发 ``40``（Socket.IO connect）→ 收 ``40``。
3. 注册：发 ``42["pushId",{id,platform,topics,lastPacketIds}]``（服务端回显确认），
   再发 ``42["setTags",[...]]``、``42["unbindUid"]``、
   ``42["bindUid",{"uid":"r_intelligent_<pid>"}]`` 绑定登录用户。
4. 心跳：客户端每 ``--ping`` 秒发 Engine.IO ping ``2``、服务端回 ``3``
   （不发心跳时连接约 60s 后被服务端断开）。
5. 推送：``42["p",{"android":{"payload":{"msgType":..,"data":{"opType":10,
   "json":{"eventType":1,"subtype":..,"type":..,"payload":{..}}}}}}]``，
   ``subtype`` 1=设备状态 / 2=地图 / 3=轨迹；``type`` 为 productId。

``uid`` 构造 = ``ENV + "_" + APP_NAME + "_" + pid``。release 下
``ENV = "r"``（``AlcsConstant.MODE_VALUE_READ``）、
``APP_NAME = "intelligent"``（``R.string.host_push_product_name``）。
``pid`` 取自账号信息：``GET /ai-app/account/info?from=1`` 的 ``UserInfo.pid``
（即 OpenAPI 的 ``opId=getAccountInfo``），或从 HAR 中已登录请求的业务参数读取。

用法：:

    .venv/bin/python scripts/push_probe.py <pid> [--watch 120] [--ping 20]

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
ENV = "r"
APP_NAME = "intelligent"
APP_VERSION = "5.3.5"
APP_SOURCE = "Release"
PLATFORM = "android"
TOPICS = ["noti", "event"]

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


async def run(pid: int, watch: int, ping: int) -> int:
    push_id = make_push_id()
    uid = f"{ENV}_{APP_NAME}_{pid}"
    url = f"{HOST}?EIO=3&transport=websocket"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    print(f"* pushId={push_id}\n* uid={uid}\n* {url}", flush=True)

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
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=watch)
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
                elif frame.startswith('42["p"'):
                    print(f"[+{loop.time() - t0:7.2f}s] << {frame[:220]}", flush=True)
                    handle_push(frame)
                elif frame.startswith("2"):
                    await send("3")
                elif frame.startswith("1"):
                    print("* Socket.IO disconnect", flush=True)
                    break
                else:
                    print(f"[+{loop.time() - t0:7.2f}s] << {frame[:200]}", flush=True)
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
    parser.add_argument("--watch", type=int, default=120, help="监听秒数（默认 120）")
    parser.add_argument("--ping", type=int, default=20, help="心跳间隔秒数（默认 20）")
    args = parser.parse_args()
    return asyncio.run(run(args.pid, args.watch, args.ping))


if __name__ == "__main__":
    sys.exit(main())
