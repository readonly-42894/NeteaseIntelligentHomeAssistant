"""网易 URS 登录 SDK 客户端。

逆向自网易智造 App（com.netease.intelligent 5.3.5）中的网易 URS 登录 SDK
（com.netease.loginapi，SDK 版本 2.1.9），用于在 Home Assistant 集成中实现真实的
短信验证码 / 邮箱登录，产出 ONE_TOKEN / ONE_TOKEN_ID。

协议要点：
- 所有请求为 POST application/x-www-form-urlencoded，附加请求头 ``yd-version: 2.1.9``。
- 业务参数先拼成 ``k1=v1&k2=v2...``，再用 AES-128/ECB/PKCS5 加密（输出小写 hex），
  作为表单字段 ``params``；登录态凭据 ``id``（ONE_TOKEN_ID）以明文字段 ``id`` 传输。
- 首次使用前先调用 ``/services/initSdk`` 初始化，得到 ``id`` 与会话 AES 密钥 ``key``。
- RSA（1024 位，PKCS1 v1.5）用于初始化时的密钥协商与 SHA256withRSA 签名验签。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import string
import time
import uuid
from typing import Any
from urllib.parse import parse_qsl, quote

import aiohttp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# --- 常量（com/netease/intelligent/kernel/config/Config.java）---
PRODUCT: str = "ai"
SDK_VERSION: str = "2.1.9"
BASE_URL: str = "https://sdk.reg.163.com"

# URS 服务端 RSA 公钥（DER，1024 位）
SERVER_PUBKEY_HEX: str = (
    "30819f300d06092a864886f70d010101050003818d0030818902818100"
    "b139bf8ea8e37c8e22f6c8c10ab5a4b89478ef3f4d5725b165d1ea51fba8593e"
    "a3c365494ae445d32ae06f222db474298cbbb671fad2a97c1dfd79c20cb8240"
    "dfe99e798061d0af9f6a2d8ee6af277db2b854f12bccd012e7b19042c5978c5c"
    "69ba03d73af73d8a96afd6f1e5fbdb6c3c695fd30fa5489ec196e13c1697ffc4f"
    "0203010001"
)

# URS 客户端 RSA 私钥（DER，PKCS#8，1024 位）
CLIENT_PRIKEY_HEX: str = (
    "30820277020100300d06092a864886f70d0101010500048202613082025d020100"
    "02818100bd93181b7727f408496cc44509fe259c0489592aab5ae0b3dd30710c59"
    "11d70ecc234d0081201816d976b0fbde745380d12d955b821529ecf451d90248f8"
    "214d79c9bafe80a6330726f91ecb29962227d3ac516c30ecd2a8191eb15d58fb33"
    "351e93333c296ea927cf5d0d566c0e0452249691ead663e5badd213f46b4aadc27"
    "0203010001028180478e1afe5af690ad0411f2ef603b36b4f21d69b3aa642e0696"
    "09afd20a58aa8522567cbd21001d379ab3ab5016826ff6627e432efc25c2e276c1"
    "e21873b47cd4db90d1ac2a1b0627c899b286b3c66d566516e17aafd788defc0b2b"
    "a1ffb2611ab342a3454912ffd22f36da273e1a9cebc2ffb2a134a80cb8c294ae05"
    "e52ee8e1024100f1576ff4d3504efa27c82a98505a07c06f24ef9d6e45ad883b3d"
    "63b5de6402ab4442e3172585c108da44d02a3ee80a0116f92df4fac5daa7da8043"
    "ab4a4f8851024100c916be9a92ec59b038c471d712594e75e5bb4be4aa6492de6e"
    "83a8e600da587162608e27e381290ee545588b5a2d82f2e90c28847902bbddb094"
    "14f75a4976f7024100d00e22f41adfd6d60d49a07ee2765acc68849d154925446e"
    "77337b2c24666f6e9a50575972fd95e63dd4a8e86286c3692116fba9802ee54b63"
    "30c4257cd087a102400c777383a3be3165426fb35b111126531ad5fcc38568ccce"
    "2b6dd027ca3fbf21f0666a09c109fde0a5882210299c0eb53e8b796b9510fd52a6"
    "22d815e9ac0a4b0241008d482b78acf49e53da7ab68bd7b337e0b0cbbbf7716c875"
    "9729b133276590aa76fa8141fad38504db578d491fd75d95d7f15a3795d1f7f5a3"
    "afb9bbab079bd13"
)

# 端点（com/netease/loginapi/f.java）
PATH_INIT_SDK: str = "/services/initSdk"
PATH_EMAIL_LOGIN: str = "/services/safeUserLoginForMob"
PATH_SMS_ACQUIRE: str = "/interfaces/yd/login1.do"
PATH_SMS_VERIFY: str = "/interfaces/yd/login2.do"
PATH_MOBILE_PWD_LOGIN: str = "/interfaces/yd/pwdlogin.do"

# 请求头（URSHttp 静态块中配置）
REQUEST_HEADERS: dict[str, str] = {"yd-version": SDK_VERSION}

# 邮箱登录密码不截断的域名（LoginOptions.NONE_LIMIT_PWD_DOMAINS）
NO_PWD_TRUNCATE_DOMAINS: tuple[str, ...] = ("126.com", "188.com", "vip.163.com")


class UrsError(Exception):
    """URS 登录业务错误。"""

    def __init__(self, code: int | str, message: str = "") -> None:
        self.code = code
        self.message = message
        super().__init__(f"URS error {code}: {message}")


def _result_code(obj: dict[str, Any]) -> int:
    """读取响应 JSON 的 result 字段并转为 int。

    服务端返回的是字符串 ``"201"``（Java 侧 Gson 会自动强转为 int），
    而 Python 的 json.loads 保留字符串，需手动转换。
    """
    try:
        return int(obj.get("result"))
    except (TypeError, ValueError):
        return -1


# ---------------------------------------------------------------------------
# 密码学（复刻 com/netease/loginapi/util/{a,i,j}.java）
# ---------------------------------------------------------------------------

def aes_encrypt(plaintext: str, key_hex: str) -> str:
    """AES/ECB/PKCS5Padding 加密，密钥为 hex 字符串，输出小写 hex。"""
    key = bytes.fromhex(key_hex)
    data = plaintext.encode("utf-8")
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len]) * pad_len
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return (encryptor.update(padded) + encryptor.finalize()).hex()


def aes_decrypt(cipher_hex: str, key_hex: str) -> str:
    """AES/ECB/PKCS5Padding 解密，返回 UTF-8 字符串。"""
    key = bytes.fromhex(key_hex)
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    padded = decryptor.update(bytes.fromhex(cipher_hex)) + decryptor.finalize()
    return padded[: -padded[-1]].decode("utf-8")


def md5(text: str) -> str:
    """MD5，小写 hex。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _server_pubkey():
    return serialization.load_der_public_key(bytes.fromhex(SERVER_PUBKEY_HEX))


def _client_prikey():
    return serialization.load_der_private_key(bytes.fromhex(CLIENT_PRIKEY_HEX), password=None)


def rsa_encrypt(data: bytes) -> str:
    """用服务端公钥加密（RSA/None/PKCS1Padding），返回 base64。"""
    ct = _server_pubkey().encrypt(data, asym_padding.PKCS1v15())
    return base64.b64encode(ct).decode("ascii")


def rsa_decrypt(cipher_b64: str) -> str:
    """用客户端私钥解密（RSA/None/PKCS1Padding），返回 UTF-8 字符串。"""
    pt = _client_prikey().decrypt(base64.b64decode(cipher_b64), asym_padding.PKCS1v15())
    return pt.decode("utf-8")


def rsa_sign(data: str) -> str:
    """SHA256withRSA 私钥签名，返回 base64。"""
    sig = _client_prikey().sign(data.encode("utf-8"), asym_padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


def rsa_verify(sign_b64: str, data: str) -> bool:
    """SHA256withRSA 公钥验签。"""
    try:
        _server_pubkey().verify(
            base64.b64decode(sign_b64),
            data.encode("utf-8"),
            asym_padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


def fix_email_password(email: str, password: str) -> str:
    """复刻 LoginOptions.fixLenOfPasswordBefore09 的密码截断逻辑。"""
    if not password or len(password) <= 16:
        return password
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if domain in NO_PWD_TRUNCATE_DOMAINS:
        return password
    return password[:16]


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------

class UrsClient:
    """URS 登录客户端，持有会话密钥（id/key），供多个请求复用。"""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._unique_id = uuid.uuid4().hex  # 32 位，初始化签名会用到，须稳定
        self._id: str | None = None
        self._key: str | None = None

    @property
    def token_id(self) -> str | None:
        return self._id

    @property
    def is_inited(self) -> bool:
        return bool(self._id and self._key)

    def _common_params(self) -> dict[str, Any]:
        """复刻 f.addCommonParams() 的公共设备参数（按插入顺序）。"""
        return {
            "rtid": uuid.uuid4().hex,
            "androidID": uuid.uuid4().hex[:16],
            "carrier": "",
            "network": "UNKNOWN",
            "pdtVersion": "5.3.5",
            "mac": "",
            "resolution": "1080*1920",
            "uniqueID": self._unique_id,
            "uniqueID_cf": self._unique_id,
            "imei": "",
            "product": PRODUCT,
            "deviceType": "Pixel5",
            "systemName": "android",
            "systemVersion": "33",
            "isEmulator": 0,
        }

    @staticmethod
    def _serialize_params(params: dict[str, Any]) -> str:
        """复刻 h.a("&", map)：key=value 用 & 连接，空值转空串。"""
        return "&".join(
            f"{k}={'' if v is None else v}" for k, v in params.items()
        )

    async def _post(self, path: str, data: dict[str, str]) -> str:
        url = BASE_URL + path
        async with self._session.post(
            url, data=data, headers=REQUEST_HEADERS
        ) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise UrsError(resp.status, f"HTTP {resp.status}")
            return text

    async def _post_login(self, path: str, extra: dict[str, Any]) -> str:
        """构造带 id + AES 加密 params 的登录请求体并发起请求。"""
        assert self.is_inited, "must call init() first"
        params = self._common_params()
        params.update(extra)
        encrypted = aes_encrypt(self._serialize_params(params), self._key)
        return await self._post(path, {"id": self._id, "params": encrypted})

    async def init(self) -> tuple[str, str]:
        """初始化 SDK（/services/initSdk），返回 (id, key)。"""
        aes_key = os.urandom(16).hex()  # 随机 AES 密钥（32 位小写 hex）
        prefix = "".join(random.choices(string.ascii_letters + string.digits, k=4))
        timestamp = str(int(time.time() * 1000))

        # sign = URLEncode(base64(SHA256withRSA_sign(clientPriKey, product+"2.1.9"+uniqueID+ts)))
        sign = rsa_sign(PRODUCT + SDK_VERSION + self._unique_id + timestamp)
        sign_encoded = quote(sign, safe="")

        # pinfo = base64(RSA_encrypt(serverPubKey, 4随机字符 + aesKeyHex))
        pinfo = rsa_encrypt((prefix + aes_key).encode("utf-8"))

        params = self._common_params()
        params["ctt"] = timestamp
        params["sign"] = sign_encoded
        encrypted = aes_encrypt(self._serialize_params(params), aes_key)

        text = await self._post(
            PATH_INIT_SDK,
            {"product": PRODUCT, "pinfo": pinfo, "params": encrypted},
        )
        obj = json.loads(text)
        code = _result_code(obj)
        if code != 201:
            raise UrsError(code, obj.get("msg", ""))

        # rk 用客户端私钥解密得到临时 AES 密钥，再解密 msg 得到 {"id","key","sign"}
        rk = obj.get("rk", "")
        if not rk:
            raise UrsError(code, "missing rk in init response")
        inner = json.loads(aes_decrypt(obj.get("msg", ""), rsa_decrypt(rk)))
        self._id = inner["id"]
        self._key = inner["key"]
        if not rsa_verify(inner.get("sign", ""), self._id + self._key):
            raise UrsError(code, "init sign verification failed")
        return self._id, self._key

    async def acquire_sms_code(self, phone: str) -> None:
        """获取短信验证码（/interfaces/yd/login1.do）。"""
        text = await self._post_login(
            PATH_SMS_ACQUIRE,
            {"mobile": phone, "referer": ""},
        )
        obj = json.loads(text)
        code = _result_code(obj)
        if code != 201:
            raise UrsError(code, obj.get("msg", ""))

    async def verify_sms_code(self, phone: str, code: str) -> tuple[str, str]:
        """校验短信验证码并登录（/interfaces/yd/login2.do），返回 (token, ssn)。"""
        text = await self._post_login(
            PATH_SMS_VERIFY,
            {
                "smscode": code,
                "mobile": phone,
                "loginException": 0,
                "needLeakInfo": 0,
            },
        )
        obj = json.loads(text)
        code_result = _result_code(obj)
        if code_result != 201:
            raise UrsError(code_result, obj.get("msg", ""))

        # msg 解密后为 "token=...&ssn=...&ydAccount=..." 形式的 URL query
        fields = dict(parse_qsl(aes_decrypt(obj.get("msg", ""), self._key)))
        token = fields.get("token", "")
        if not token:
            raise UrsError(code_result, "no token in verify response")
        return token, fields.get("ssn", "")

    async def email_login(self, email: str, password: str) -> tuple[str, str, str]:
        """邮箱密码登录（/services/safeUserLoginForMob），返回 (token, ssn, username)。"""
        text = await self._post_login(
            PATH_EMAIL_LOGIN,
            {
                "username": email,
                "password": md5(fix_email_password(email, password)),
                "isMd5": 1,
                "needmainaccount": 1,
            },
        )

        # 文本响应：首段为 code（数字），末段为 "result=<AES>" 形式的 message
        lines = [line for line in text.split("\n") if line.strip()]
        if not lines:
            raise UrsError(-1, "empty response")
        code = int(lines[0].strip()) if lines[0].strip().isdigit() else -1
        if code != 201:
            raise UrsError(code, lines[-1] if len(lines) > 1 else "")

        result_enc = dict(parse_qsl(lines[-1])).get("result", "")
        if not result_enc:
            raise UrsError(code, "no result in login response")
        fields = dict(parse_qsl(aes_decrypt(result_enc, self._key)))
        token = fields.get("token", "")
        username = fields.get("aliasuser", "")
        ssn = fields.get("username", "")
        if not token or not username:
            raise UrsError(code, "parse login result failed")
        return token, ssn, username
