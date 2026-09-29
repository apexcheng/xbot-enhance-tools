"""
ntfy 消息发送与接收
"""

import json

import requests


def send_ntfy_message(message, topic, server="https://ntfy.sh"):
    """
    发送消息到 ntfy topic
    * @param message, 消息内容
    * @param topic, ntfy topic 名称
    * @param server, ntfy 服务器地址，默认 https://ntfy.sh
    * @return 发送成功返回 True，失败抛出异常
    """
    url = f"{server}/{topic}"
    try:
        resp = requests.post(url, data=message.encode("utf-8"),
                             headers={"Content-Type": "text/plain"}, timeout=15)
        if resp.status_code == 200:
            return True
        else:
            raise Exception(f"发送失败，HTTP 状态码: {resp.status_code}")
    except requests.RequestException as e:
        raise Exception(f"发送消息失败: {e}") from e


def receive_ntfy_message(topic, server="https://ntfy.sh", since="10m", timeout=15):
    """
    从 ntfy topic 拉取消息（轮询方式）
    * @param topic, ntfy topic 名称
    * @param server, ntfy 服务器地址，默认 https://ntfy.sh
    * @param since, 拉取时间范围，默认 10m（10分钟）
    * @param timeout, 请求超时时间（秒），默认 15
    * @return 返回消息列表，无消息返回空列表，失败抛出异常
    """
    url = f"{server}/{topic}/json"
    params = {"since": since, "poll": 1}
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            raise Exception(f"请求失败，HTTP 状态码: {resp.status_code}")

        messages = []
        for line in resp.text.splitlines():
            if not line:
                continue
            raw = line.strip()
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and msg.get("event") == "message":
                messages.append({
                    "id": msg.get("id"),
                    "time": msg.get("time"),
                    "message": msg.get("message", "")
                })

        return sorted(messages, key=lambda item: item.get("time") or 0, reverse=True)

    except requests.RequestException as e:
        raise Exception(f"拉取消息失败: {e}") from e
