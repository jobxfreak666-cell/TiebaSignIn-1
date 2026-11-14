"""飞书群机器人推送（自定义机器人 Webhook）

通过环境变量 FEISHU_WEBHOOK_URL 读取完整的 Webhook 地址
（https://open.feishu.cn/open-apis/bot/v2/hook/<token>）。
未配置时 send_markdown 直接返回 False，不影响主流程。
可选环境变量 FEISHU_WEBHOOK_SECRET：机器人开启签名校验时填写，
未开启签名校验则留空。消息标题固定含「贴吧」，满足机器人
「自定义关键词」安全设置（关键词设为 贴吧）。

飞书自定义机器人文档:
    https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
"""

import base64
import hashlib
import hmac
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)


def get_webhook_url() -> str:
    return os.environ.get("FEISHU_WEBHOOK_URL", "").strip()


def get_webhook_secret() -> str:
    return os.environ.get("FEISHU_WEBHOOK_SECRET", "").strip()


def _sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _to_plain(content: str) -> str:
    """把企业微信 markdown 简单清洗成飞书可读的纯文本/lark_md。"""
    lines = []
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("#"):
            s = s.lstrip("#").strip()
        if s.startswith(">"):
            s = s.lstrip(">").strip()
        if s.startswith("- "):
            s = "• " + s[2:]
        lines.append(s)
    return "\n".join(lines)


def _post(url: str, payload: dict) -> bool:
    secret = get_webhook_secret()
    if secret:
        ts = int(time.time())
        payload = {**payload, "timestamp": str(ts), "sign": _sign(secret, ts)}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) != 0 and data.get("StatusCode", 0) != 0:
            logger.error(
                f"飞书推送失败: code={data.get('code')} msg={data.get('msg')}"
            )
            return False
        logger.info("飞书推送成功")
        return True
    except Exception as e:
        logger.error(f"飞书推送异常: {e}")
        return False


def send_markdown(content: str, url: str | None = None) -> bool:
    """把签到结果推送到飞书群。先发卡片，失败回退纯文本。"""
    url = (url or "").strip() or get_webhook_url()
    if not url:
        logger.info("未配置 FEISHU_WEBHOOK_URL，跳过飞书推送")
        return False

    body = _to_plain(content)
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "贴吧签到结果"},
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": body}}
            ],
        },
    }
    if _post(url, card):
        return True
    logger.warning("飞书卡片推送失败，回退纯文本")
    return _post(url, {"msg_type": "text", "content": {"text": "贴吧签到结果\n" + body}})
