"""HTTP 会话与微信读书扫码登录。"""
from __future__ import annotations

import hashlib
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .paths import SESSION_FILE, beijing_now, load_json, save_json

WEREAD_MOBILE_BASE = "https://i.weread.qq.com"
WECHAT_QR_BASE = "https://open.weixin.qq.com"
WECHAT_QR_POLL = "https://long.open.weixin.qq.com/connect/l/qrconnect"
REQUEST_TIMEOUT = (10, 30)

MOBILE_HEADERS = {
    "baseapi": "30",
    "appver": "2.1.2.10245900",
    "basever": "2.1.2.10245900",
    "osver": "11",
    "channelId": "900",
    "User-Agent": (
        "WeRead/2.1.2 WRBrand/Onyx wr_eink "
        "Dalvik/2.1.0 (Linux; U; Android 11; BOOX Build/onyx)"
    ),
}

_SESSION: Optional[requests.Session] = None


def get_http_session() -> requests.Session:
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    _SESSION = session
    return session


def http_get(url: str, *, headers=None, params=None, timeout=60):
    return get_http_session().get(url, headers=headers, params=params, timeout=timeout)


def response_json(response, label: str, allow_http_error: bool = False) -> Dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{label}没有返回 JSON。") from exc
    if response.status_code >= 400 and not allow_http_error:
        raise RuntimeError(f"{label}失败：HTTP {response.status_code}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label}返回格式异常。")
    return payload


def _show_login_qr(confirm_url: str) -> Path:
    try:
        import qrcode
    except ImportError as exc:
        raise RuntimeError('缺少二维码依赖，请先：pip install "qrcode[pil]"') from exc

    qr_path = Path(tempfile.gettempdir()) / "weread_monitor_login_qr.png"
    qrcode.make(confirm_url).save(qr_path)
    print("微信读书登录二维码已打开，请用微信扫码并在手机上确认。")
    print(f"二维码文件: {qr_path}")
    try:
        if sys.platform == "darwin":
            os.system(f'open "{qr_path}"')
        elif os.name == "nt":
            os.startfile(str(qr_path))  # type: ignore[attr-defined]
        else:
            import webbrowser

            webbrowser.open(qr_path.as_uri())
    except Exception:
        print("请手动打开上述二维码图片扫码。")
    return qr_path


def _new_mobile_device_id() -> str:
    return f"eink334691225{str(secrets.randbits(63)).zfill(19)}"


def _new_mobile_install_id() -> str:
    digits = "".join(str(secrets.randbelow(10)) for _ in range(26))
    return f"eink31{digits}"


def login_weread_mobile(deadline_seconds: int = 300) -> Dict[str, str]:
    session = get_http_session()
    ticket = response_json(
        session.get(
            f"{WEREAD_MOBILE_BASE}/wxticket",
            params={"nonceStr": "weread"},
            headers=MOBILE_HEADERS,
            timeout=REQUEST_TIMEOUT,
        ),
        "获取微信读书二维码票据",
    )
    signature, timestamp = ticket.get("signature"), ticket.get("timeStamp")
    if not signature or timestamp is None:
        raise RuntimeError("微信读书二维码票据缺少 signature 或 timeStamp。")

    qr_data = response_json(
        session.get(
            f"{WECHAT_QR_BASE}/connect/sdk/qrconnect",
            params={
                "appid": "wxab9b71ad2b90ff34",
                "noncestr": "weread",
                "timestamp": str(timestamp),
                "scope": "snsapi_userinfo,snsapi_timeline,snsapi_friend",
                "signature": str(signature),
            },
            headers={"User-Agent": MOBILE_HEADERS["User-Agent"]},
            timeout=REQUEST_TIMEOUT,
        ),
        "获取微信登录二维码",
    )
    if qr_data.get("errcode") != 0 or not qr_data.get("uuid"):
        raise RuntimeError(f"获取微信登录二维码失败：{qr_data.get('errcode')}")

    uuid = str(qr_data["uuid"])
    qr_artifact = _show_login_qr(f"{WECHAT_QR_BASE}/connect/confirm?uuid={uuid}")
    deadline = time.monotonic() + deadline_seconds
    last_status = None
    wx_code = None

    try:
        while time.monotonic() < deadline:
            params = {"f": "json", "uuid": uuid}
            if last_status is not None:
                params["last"] = last_status
            remaining = max(1, int(deadline - time.monotonic()))
            poll_data = response_json(
                session.get(
                    WECHAT_QR_POLL,
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=(10, min(65, remaining)),
                ),
                "轮询微信扫码状态",
            )
            status = int(poll_data.get("wx_errcode", 0))
            if status == 405:
                wx_code = poll_data.get("wx_code")
                if not wx_code:
                    raise RuntimeError("手机已确认，但微信没有返回登录 code。")
                break
            if status == 404:
                print("二维码已扫描，请在手机上确认登录……")
            elif status == 408:
                time.sleep(1)
            elif status == 402:
                raise RuntimeError("二维码已过期，请重新运行并扫码。")
            elif status == 403:
                raise RuntimeError("手机端已拒绝登录。")
            else:
                raise RuntimeError(f"未知扫码状态：{status}")
            last_status = status
    finally:
        try:
            qr_artifact.unlink(missing_ok=True)
        except OSError:
            pass

    if not wx_code:
        raise RuntimeError("扫码登录超时，请重新运行。")

    device_id = _new_mobile_device_id()
    login_timestamp = int(time.time() * 1000)
    random_value = secrets.randbelow(1000)
    signature_text = f"{login_timestamp}{device_id}{random_value}"
    result = response_json(
        session.post(
            f"{WEREAD_MOBILE_BASE}/login",
            headers={**MOBILE_HEADERS, "Content-Type": "application/json; charset=UTF-8"},
            json={
                "appFirstInstall": 1,
                "code": wx_code,
                "deviceId": device_id,
                "deviceName": "BOOX",
                "installId": _new_mobile_install_id(),
                "isAutoLogout": 0,
                "isFromQrcode": 1,
                "random": random_value,
                "signature": hashlib.sha256(signature_text.encode("utf-8")).hexdigest(),
                "timestamp": login_timestamp,
                "trackId": "",
                "deviceType": 3,
            },
            timeout=REQUEST_TIMEOUT,
        ),
        "微信读书扫码登录",
    )
    if not result.get("accessToken") or not result.get("refreshToken"):
        raise RuntimeError(
            f"微信读书扫码登录失败：{result.get('errCode', '')} {result.get('errMsg', '')}".strip()
        )
    creds = {
        "vid": str(result.get("vid")),
        "accessToken": str(result["accessToken"]),
        "refreshToken": str(result["refreshToken"]),
        "deviceId": device_id,
        "saved_at": beijing_now().isoformat(),
    }
    print(f"扫码登录成功，vid={creds['vid']}")
    return creds


def save_session(creds: Dict[str, str]) -> None:
    save_json(SESSION_FILE, creds)
    print(f"已保存会话: {SESSION_FILE.name}")


def load_session() -> Optional[Dict[str, Any]]:
    data = load_json(SESSION_FILE)
    if not data.get("accessToken") or not data.get("vid"):
        return None
    return data


def obtain_credentials(force_fresh: bool = False) -> Dict[str, Any]:
    if not force_fresh:
        cached = load_session()
        if cached:
            print(f"复用已有会话 {SESSION_FILE.name}（可用 --fresh 强制重扫）")
            return cached
    print("正在启动微信读书扫码登录……")
    creds = login_weread_mobile()
    save_session(creds)
    return creds
