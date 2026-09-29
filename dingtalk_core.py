from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib import error, parse, request

ACCESS_TOKEN_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
GROUP_MESSAGE_URL = "https://api.dingtalk.com/v1.0/robot/groupMessages/send"
OTO_MESSAGE_URL = "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend"
MEDIA_UPLOAD_URL = "https://oapi.dingtalk.com/media/upload"
MOBILE_TO_USERID_URL = "https://oapi.dingtalk.com/topapi/v2/user/getbymobile"

MAX_IMAGE_BYTES = 20 * 1024 * 1024
SUPPORTED_IMAGE_SIGNATURES: Tuple[Tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"RIFF", "image/webp"),
)


class DingTalkRobotError(RuntimeError):
    """钉钉接口调用失败。"""


class DingTalkImageValidationError(ValueError):
    """图片发送前的本地校验失败。"""


def clean_dingtalk_markdown(markdown: str) -> str:
    """清理 Markdown 缩进，避免钉钉把整段内容识别成代码块。"""
    markdown = textwrap.dedent(str(markdown)).strip()
    return "\n".join(
        line.lstrip(" \t\u3000\xa0")
        for line in markdown.splitlines()
    ).strip()


class DingTalkWebhookRobot:
    """最小 webhook 发送器，用于群聊 text / markdown。"""

    def __init__(
        self,
        *,
        webhook_url: str,
        webhook_secret: Optional[str] = None,
        at_mobiles: Optional[list[str]] = None,
        at_all: Optional[bool] = None,
        timeout: float = 10.0,
    ) -> None:
        self.webhook_url = _require_text(webhook_url, "webhook_url")
        self.webhook_secret = webhook_secret
        self.at_mobiles = at_mobiles or []
        self.at_all = bool(at_all)
        self.timeout = timeout

    def send_text(self, content: str) -> Dict[str, Any]:
        content = self._append_at_hint(_require_text(content, "content"))
        return self._post(
            {
                "msgtype": "text",
                "text": {"content": content},
                "at": self._build_at_payload(),
            }
        )

    def send_markdown(self, title: str, markdown_text: str) -> Dict[str, Any]:
        markdown_text = self._append_at_hint(_require_text(markdown_text, "markdown_text"))
        return self._post(
            {
                "msgtype": "markdown",
                "markdown": {
                    "title": _require_text(title, "title"),
                    "text": markdown_text,
                },
                "at": self._build_at_payload(),
            }
        )

    def _build_at_payload(self) -> Dict[str, Any]:
        return {
            "atMobiles": [] if self.at_all else [_require_text(item, "at_mobile") for item in self.at_mobiles],
            "isAtAll": self.at_all,
        }

    def _append_at_hint(self, content: str) -> str:
        if self.at_all:
            return content
        if not self.at_mobiles:
            return content
        mentions = " ".join(f"@{mobile}" for mobile in self.at_mobiles)
        return f"{content}\n\n{mentions}"

    def _signed_url(self) -> str:
        if not self.webhook_secret:
            return self.webhook_url

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.webhook_secret}".encode("utf-8")
        digest = hmac.new(
            self.webhook_secret.encode("utf-8"),
            string_to_sign,
            digestmod=hashlib.sha256,
        ).digest()
        sign = parse.quote_plus(base64.b64encode(digest))
        separator = "&" if parse.urlparse(self.webhook_url).query else "?"
        return f"{self.webhook_url}{separator}timestamp={timestamp}&sign={sign}"

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = _http_json(
            self._signed_url(),
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=self.timeout,
        )
        _raise_on_oapi_error(result, "钉钉 webhook 发送失败")
        return result


class DingTalkEnterpriseRobot:
    """最小企业内部机器人发送器，用于私聊和群聊本地图片。"""

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        robot_code: Optional[str] = None,
        open_conversation_id: Optional[str] = None,
        user_ids: Optional[list[str]] = None,
        user_mobiles: Optional[list[str]] = None,
        at_mobiles: Optional[list[str]] = None,
        timeout: float = 10.0,
    ) -> None:
        self.app_key = _require_text(app_key, "app_key")
        self.app_secret = _require_text(app_secret, "app_secret")
        self.robot_code = robot_code or self.app_key
        self.open_conversation_id = open_conversation_id
        self.user_ids = user_ids or []
        self.user_mobiles = user_mobiles or []
        self.at_mobiles = at_mobiles or []
        self.timeout = timeout
        self._access_token: Optional[str] = None
        self._access_token_expire_at = 0.0

    def send_text(self, content: str) -> Dict[str, Any]:
        return self._send_message("sampleText", {"content": _require_text(content, "content")})

    def send_markdown(self, title: str, markdown_text: str) -> Dict[str, Any]:
        return self._send_message(
            "sampleMarkdown",
            {
                "title": _require_text(title, "title"),
                "text": _require_text(markdown_text, "markdown_text"),
            },
        )

    def send_image(self, file_path: Path) -> Dict[str, Any]:
        media_id = self._upload_image(file_path)
        return self._send_message("sampleImageMsg", {"photoURL": media_id})

    def _send_message(self, msg_key: str, msg_param: Dict[str, Any]) -> Dict[str, Any]:
        # if self.open_conversation_id:
        #     payload = {
        #         "robotCode": self.robot_code,
        #         "openConversationId": self.open_conversation_id,
        #         "msgKey": msg_key,
        #         "msgParam": json.dumps(msg_param, ensure_ascii=False),
        #     }

        # return self._post_openapi(GROUP_MESSAGE_URL, payload)

        if self.open_conversation_id:
            payload = {
                "robotCode": self.robot_code,
                "openConversationId": self.open_conversation_id,
                "msgKey": msg_key,
                "msgParam": json.dumps(msg_param, ensure_ascii=False),
            }

            # if self.at_mobiles:
            #     payload["atUsers"] = [
            #         {"dingtalkId": self.get_user_id_by_mobile(mobile)}
            #         for mobile in self.at_mobiles
            #     ]

            return self._post_openapi(GROUP_MESSAGE_URL, payload)

        user_ids = self._resolve_user_ids()
        if not user_ids:
            raise ValueError("私聊需要 user_ids 或 user_mobiles")
        payload = {
            "robotCode": self.robot_code,
            "userIds": user_ids,
            "msgKey": msg_key,
            "msgParam": json.dumps(msg_param, ensure_ascii=False),
        }
        return self._post_openapi(OTO_MESSAGE_URL, payload)

    def _upload_image(self, file_path: Path) -> str:
        image_path, content_type = validate_image_file(file_path)
        query = parse.urlencode({"access_token": self._get_access_token(), "type": "image"})
        body, boundary = _build_multipart_body(
            field_name="media",
            file_path=image_path,
            content_type=content_type,
        )
        result = _http_json(
            f"{MEDIA_UPLOAD_URL}?{query}",
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            timeout=self.timeout,
        )
        _raise_on_oapi_error(result, "钉钉图片上传失败")
        media_id = result.get("media_id")
        if not media_id:
            raise DingTalkRobotError(f"钉钉图片上传接口未返回 media_id: {result}")
        return str(media_id)

    def _resolve_user_ids(self) -> list[str]:
        user_ids = [_require_text(item, "user_id") for item in self.user_ids]
        for mobile in self.user_mobiles:
            user_ids.append(self.get_user_id_by_mobile(mobile))

        unique_user_ids: list[str] = []
        seen = set()
        for user_id in user_ids:
            if user_id not in seen:
                unique_user_ids.append(user_id)
                seen.add(user_id)
        return unique_user_ids

    def get_user_id_by_mobile(self, mobile: str) -> str:
        query = parse.urlencode({"access_token": self._get_access_token()})
        result = _http_json(
            f"{MOBILE_TO_USERID_URL}?{query}",
            body=json.dumps({"mobile": _require_text(mobile, "mobile")}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=self.timeout,
        )
        _raise_on_oapi_error(result, f"根据手机号获取 userId 失败: {mobile}")
        user_id = (result.get("result") or {}).get("userid")
        if not user_id:
            raise DingTalkRobotError(f"手机号未查询到 userId: {mobile}, 返回: {result}")
        return str(user_id)

    def _post_openapi(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = _http_json(
            url,
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "x-acs-dingtalk-access-token": self._get_access_token(),
            },
            timeout=self.timeout,
        )
        if "code" in result or "message" in result:
            raise DingTalkRobotError(f"钉钉机器人消息发送失败: {result}")
        return result

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expire_at:
            return self._access_token

        result = _http_json(
            ACCESS_TOKEN_URL,
            body=json.dumps(
                {"appKey": self.app_key, "appSecret": self.app_secret},
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=self.timeout,
        )
        token = result.get("accessToken")
        if not token:
            raise DingTalkRobotError(f"获取钉钉 accessToken 失败: {result}")

        expire_in = int(result.get("expireIn") or 7200)
        self._access_token = str(token)
        self._access_token_expire_at = now + max(expire_in - 300, 60)
        return self._access_token


def validate_image_file(file_path: Path) -> Tuple[Path, str]:
    path = file_path.expanduser().resolve()
    if not path.exists():
        raise DingTalkImageValidationError(f"图片文件不存在: {path}")
    if not path.is_file():
        raise DingTalkImageValidationError(f"图片路径不是文件: {path}")

    size = path.stat().st_size
    if size <= 0:
        raise DingTalkImageValidationError(f"图片文件为空: {path}")
    if size > MAX_IMAGE_BYTES:
        raise DingTalkImageValidationError(f"图片文件过大: {size} bytes")

    header = path.read_bytes()[:16]
    content_type = _match_image_content_type(header)
    if not content_type:
        raise DingTalkImageValidationError("不支持的图片格式。支持格式: png, jpg/jpeg, gif, bmp, webp")
    if content_type == "image/webp" and header[8:12] != b"WEBP":
        raise DingTalkImageValidationError("非法的 webp 图片文件头")

    return path, mimetypes.guess_type(str(path))[0] or content_type


def _match_image_content_type(header: bytes) -> Optional[str]:
    for marker, content_type in SUPPORTED_IMAGE_SIGNATURES:
        if header.startswith(marker):
            return content_type
    return None


def _build_multipart_body(
    *,
    field_name: str,
    file_path: Path,
    content_type: str,
) -> Tuple[bytes, str]:
    boundary = f"----DingTalkPython{uuid.uuid4().hex}"
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{file_path.name}"\r\n'
        ).encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        file_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts), boundary


def _http_json(
    url: str,
    *,
    body: bytes,
    headers: Dict[str, str],
    timeout: float,
) -> Dict[str, Any]:
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DingTalkRobotError(f"钉钉接口返回 HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise DingTalkRobotError(f"无法连接钉钉接口: {exc}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DingTalkRobotError(f"钉钉接口返回内容不是 JSON: {raw}") from exc


def _raise_on_oapi_error(result: Dict[str, Any], prefix: str) -> None:
    errcode = result.get("errcode")
    if errcode not in (None, 0):
        raise DingTalkRobotError(f"{prefix}: {result}")


def _require_text(value: str, name: str) -> str:
    normalized = str(value).strip() if value is not None else ""
    if not normalized:
        raise ValueError(f"{name} 不能为空")
    return normalized


class DingTalkRobotV2:
    """
    最小化的钉钉发送器。

    用法：
    1. 群聊 `text` / `markdown` 优先走 webhook，可用 `@`；没有 webhook 时走企业内部机器人。
    2. 群聊 `image` 走企业内部机器人，发送本地图片，不支持 `@`。
    3. 私聊 `text` / `markdown` / `image` 全走企业内部机器人。
    4. 图片统一只支持本地 `file_path`。
    """

    def __init__(
        self,
        *,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        robot_code: Optional[str] = None,
        open_conversation_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        """
        初始化 `DingTalkRobotV2` 实例。

        用法：
        - 当你要发群聊文本或 Markdown 时，优先传 `webhook_url`；没有 webhook 时传 `app_key`、`app_secret`、`open_conversation_id`
        - 当你要发群聊图片时，传 `app_key`、`app_secret`、`open_conversation_id`
        - 当你要发私聊消息时，传 `app_key`、`app_secret`

        :param app_key str: 企业内部应用的 AppKey
        :param app_secret str: 企业内部应用的 AppSecret
        :param robot_code str: 企业内部机器人编码，不传时默认使用 `app_key`
        :param open_conversation_id str: 群聊会话 ID，群聊走企业内部机器人时必填
        :param webhook_url str: 自定义机器人 webhook 地址，群聊文本和 Markdown 优先使用
        :param webhook_secret str: 自定义机器人加签密钥，可不传
        :param timeout float: 请求超时时间，单位秒
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self.robot_code = robot_code
        self.open_conversation_id = open_conversation_id
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.timeout = timeout

    def send_group(
        self,
        message_type: str,
        content: str,
        *,
        title: Optional[str] = None,
        at_mobiles: Optional[list[str]] = None,
        at_all: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        发送群聊消息。

        用法：
        - `message_type=\"text\"` 时，`content` 传文本内容，优先走 webhook，可 `@`；没有 webhook 时走企业内部机器人
        - `message_type=\"markdown\"` 时，`content` 传 Markdown 内容；优先走 webhook，没有 webhook 时走企业内部机器人
        - `message_type=\"image\"` 时，`content` 传本地图片路径，走企业内部机器人，不支持 `@`

        :param message_type str: 消息类型，只支持 `text`、`markdown`、`image`
        :param content str: 文本内容、Markdown 内容，或本地图片路径
        :param title str: Markdown 消息标题，仅 `markdown` 时使用
        :param at_mobiles list[str]: 群聊 @ 的手机号列表，仅 `text` / `markdown` 时使用
        :param at_all bool: 是否 @ 所有人；仅 webhook 路径支持
        :return dict: 钉钉接口返回结果
        """
        message_type = message_type.strip().lower()
        if not title and message_type in ['text', 'markdown']:
            title = content[:20]

        if message_type == "text":
            if self.webhook_url:
                robot = self._build_webhook_robot(at_mobiles=at_mobiles, at_all=at_all)
                return robot.send_text(content)
            if at_all or at_mobiles:
                raise ValueError("@ 功能必须使用 webhook_url")

            robot = self._build_enterprise_group_robot(at_mobiles=at_mobiles)
            return robot.send_text(content)

        if message_type == "markdown":
            if self.webhook_url:
                robot = self._build_webhook_robot(at_mobiles=at_mobiles, at_all=False)
                result = robot.send_markdown(title or "markdown message", clean_dingtalk_markdown(content))
                if at_all:
                    notify_robot = self._build_webhook_robot(at_mobiles=None, at_all=True)
                    notify_robot.send_text("请查看上方消息")
                return result

            if at_all or at_mobiles:
                raise ValueError("@ 功能必须使用 webhook_url")
            robot = self._build_enterprise_group_robot(at_mobiles=at_mobiles)
            return robot.send_markdown(title or "markdown message", clean_dingtalk_markdown(content))

        if message_type == "image":
            file_path = self._normalize_file_path(content)
            robot = self._build_enterprise_group_robot()
            return robot.send_image(file_path)

        raise ValueError("message_type 仅支持 text、markdown、image")

    def send_private(
        self,
        message_type: str,
        content: str,
        *,
        title: Optional[str] = None,
        user_ids: Optional[list[str]] = None,
        user_mobiles: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        发送私聊消息。

        用法：
        - `message_type=\"text\"` 时，`content` 传文本内容
        - `message_type=\"markdown\"` 时，`content` 传 Markdown 内容
        - `message_type=\"image\"` 时，`content` 传本地图片路径

        :param message_type str: 消息类型，只支持 `text`、`markdown`、`image`
        :param content str: 文本内容、Markdown 内容，或本地图片路径
        :param title str: Markdown 消息标题，仅 `markdown` 时使用
        :param user_ids list[str]: 接收人的钉钉 userId 列表
        :param user_mobiles list[str]: 接收人的手机号列表，会先自动换取 userId
        :return dict: 钉钉接口返回结果
        """
        message_type = message_type.strip().lower()

        if not title and message_type in ['text', 'markdown']:
            title = content[:20]

        robot = self._build_enterprise_private_robot(
            user_ids=user_ids,
            user_mobiles=user_mobiles,
        )

        if message_type == "text":
            return robot.send_text(content)

        if message_type == "markdown":
            return robot.send_markdown(title or "markdown message", clean_dingtalk_markdown(content))

        if message_type == "image":
            file_path = self._normalize_file_path(content)
            return robot.send_image(file_path)

        raise ValueError("message_type 仅支持 text、markdown、image")

    def _build_webhook_robot(
        self,
        *,
        at_mobiles: Optional[list[str]],
        at_all: Optional[bool],
    ) -> DingTalkWebhookRobot:
        """
        构造群聊文本 / Markdown 使用的 webhook 发送器。

        用法：
        - 给 `send_group` 的 `text` / `markdown` 分支内部调用

        :param at_mobiles list[str]: 群聊 @ 的手机号列表
        :param at_all bool: 是否 @ 所有人
        :return DingTalkWebhookRobot: webhook 发送器实例
        """
        if not self.webhook_url:
            raise ValueError("群聊 text/markdown 需要 webhook_url")
        return DingTalkWebhookRobot(
            webhook_url=self.webhook_url,
            webhook_secret=self.webhook_secret,
            at_mobiles=at_mobiles,
            at_all=at_all,
            timeout=self.timeout,
        )

    def _build_enterprise_group_robot(
        self,
        *,
        at_mobiles: Optional[list[str]] = None,
    ) -> DingTalkEnterpriseRobot:
        """
        构造群聊图片使用的企业内部机器人发送器。

        用法：
        - 给 `send_group` 的 `image` 分支内部调用

        :return DingTalkEnterpriseRobot: 企业内部机器人发送器实例
        """
        if not self.app_key or not self.app_secret:
            raise ValueError("群聊企业内部机器人发送需要 app_key 和 app_secret")
        if not self.open_conversation_id:
            raise ValueError("群聊企业内部机器人发送需要 open_conversation_id")
        return DingTalkEnterpriseRobot(
            app_key=self.app_key,
            app_secret=self.app_secret,
            robot_code=self.robot_code,
            open_conversation_id=self.open_conversation_id,
            timeout=self.timeout,
            at_mobiles=at_mobiles,
        )

    def _build_enterprise_private_robot(
        self,
        *,
        user_ids: Optional[list[str]],
        user_mobiles: Optional[list[str]],
    ) -> DingTalkEnterpriseRobot:
        """
        构造私聊发送器。

        用法：
        - 给 `send_private` 的三种消息类型内部调用

        :param user_ids list[str]: 接收人的钉钉 userId 列表
        :param user_mobiles list[str]: 接收人的手机号列表
        :return DingTalkEnterpriseRobot: 企业内部机器人发送器实例
        """
        if not self.app_key or not self.app_secret:
            raise ValueError("私聊需要 app_key 和 app_secret")
        return DingTalkEnterpriseRobot(
            app_key=self.app_key,
            app_secret=self.app_secret,
            robot_code=self.robot_code,
            user_ids=user_ids,
            user_mobiles=user_mobiles,
            timeout=self.timeout,
        )

    def _normalize_file_path(self, file_path: str) -> Path:
        """
        整理图片文件路径。

        用法：
        - 给群聊图片和私聊图片发送前做最小路径清洗

        :param file_path str: 本地图片路径
        :return Path: 处理后的 `Path` 对象
        """
        raw_path = str(file_path).strip()
        if not raw_path:
            raise DingTalkImageValidationError("image 不能为空")
        return Path(raw_path).expanduser()


def send_dingtalk_group(
    message_type: str,
    content: str,
    *,
    app_key: Optional[str] = None,
    app_secret: Optional[str] = None,
    robot_code: Optional[str] = None,
    open_conversation_id: Optional[str] = None,
    webhook_url: Optional[str] = None,
    webhook_secret: Optional[str] = None,
    title: Optional[str] = None,
    at_mobiles: Optional[list[str]] = None,
    at_all: Optional[bool] = None
) -> Dict[str, Any]:
    """
    群聊消息快捷入口。

    用法：
    - 文本：`send_dingtalk_group(\"text\", \"内容\", webhook_url=\"...\")`，没有 webhook 时传 app_key/app_secret/open_conversation_id
    - Markdown：`send_dingtalk_group(\"markdown\", \"### 标题\", webhook_url=\"...\", title=\"通知\")`，没有 webhook 时传 app_key/app_secret/open_conversation_id
    - 图片：`send_dingtalk_group(\"image\", \"/tmp/demo.png\", app_key=\"...\", app_secret=\"...\", open_conversation_id=\"...\")`

    :param message_type str: 消息类型，只支持 `text`、`markdown`、`image`
    :param content str: 文本内容、Markdown 内容，或本地图片路径
    :param app_key str: 企业内部应用的 AppKey，群聊走企业内部机器人时需要
    :param app_secret str: 企业内部应用的 AppSecret，群聊走企业内部机器人时需要
    :param robot_code str: 企业内部机器人编码，可不传
    :param open_conversation_id str: 群聊会话 ID，群聊走企业内部机器人时需要
    :param webhook_url str: 自定义机器人 webhook 地址，群聊文本和 Markdown 优先使用
    :param webhook_secret str: 自定义机器人加签密钥，可不传
    :param title str: Markdown 消息标题，仅 `markdown` 时使用
    :param at_mobiles list[str]: 群聊 @ 的手机号列表，仅 `text` / `markdown` 时使用
    :param at_all bool: 是否 @ 所有人，仅 `text` / `markdown` 时使用
    :return dict: 钉钉接口返回结果
    """
    return DingTalkRobotV2(
        app_key=app_key,
        app_secret=app_secret,
        robot_code=robot_code,
        open_conversation_id=open_conversation_id,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
    ).send_group(
        message_type,
        content,
        title=title,
        at_mobiles=at_mobiles,
        at_all=at_all,
    )


def send_dingtalk_private(
    message_type: str,
    content: str,
    *,
    app_key: str,
    app_secret: str,
    robot_code: Optional[str] = None,
    title: Optional[str] = None,
    user_ids: Optional[list[str]] = None,
    user_mobiles: Optional[list[str]] = None
) -> Dict[str, Any]:
    """
    私聊消息快捷入口。

    用法：
    - 文本：`send_dingtalk_private(\"text\", \"内容\", app_key=\"...\", app_secret=\"...\", user_mobiles=[\"138...\"])`
    - Markdown：`send_dingtalk_private(\"markdown\", \"### 标题\", app_key=\"...\", app_secret=\"...\", title=\"通知\", user_ids=[\"xxx\"])`
    - 图片：`send_dingtalk_private(\"image\", \"/tmp/demo.png\", app_key=\"...\", app_secret=\"...\", user_mobiles=[\"138...\"])`

    :param message_type str: 消息类型，只支持 `text`、`markdown`、`image`
    :param content str: 文本内容、Markdown 内容，或本地图片路径
    :param app_key str: 企业内部应用的 AppKey
    :param app_secret str: 企业内部应用的 AppSecret
    :param robot_code str: 企业内部机器人编码，可不传
    :param title str: Markdown 消息标题，仅 `markdown` 时使用
    :param user_ids list[str]: 接收人的钉钉 userId 列表
    :param user_mobiles list[str]: 接收人的手机号列表，会先自动换取 userId
    :return dict: 钉钉接口返回结果
    """
    return DingTalkRobotV2(
        app_key=app_key,
        app_secret=app_secret,
        robot_code=robot_code,
    ).send_private(
        message_type,
        content,
        title=title,
        user_ids=user_ids,
        user_mobiles=user_mobiles,
    )
