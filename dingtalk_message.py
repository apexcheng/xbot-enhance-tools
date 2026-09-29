from .dingtalk_core import DingTalkRobotV2


def send_dingtalk_group(
    message_type,
    content,
    *,
    app_key=None,
    app_secret=None,
    robot_code=None,
    open_conversation_id=None,
    webhook_url=None,
    webhook_secret=None,
    title=None,
    at_mobiles=None,
    at_all=None,
    timeout=10.0,
):
    """
    发送钉钉群聊消息。

    text / markdown 优先使用显式传入的 webhook_url，否则使用企业机器人；
    image 使用企业机器人。所有配置均由调用方传入。

    :param message_type: 消息类型，只支持 text、markdown、image
    :param content: 文本内容、Markdown 内容，或本地图片路径
    :param app_key: 企业内部应用 AppKey，使用企业机器人时必填
    :param app_secret: 企业内部应用 AppSecret，使用企业机器人时必填
    :param robot_code: 企业内部机器人编码，可不传
    :param open_conversation_id: 群聊会话 ID，使用企业机器人时必填
    :param webhook_url: 自定义机器人 webhook 地址，群聊文本和 Markdown 可使用
    :param webhook_secret: 自定义机器人加签密钥，可不传
    :param title: Markdown 消息标题，仅 markdown 时使用
    :param at_mobiles: 群聊 @ 的手机号列表，仅 webhook text / markdown 有效
    :param at_all: 是否 @ 所有人，仅 webhook text / markdown 有效
    :param timeout: 请求超时时间，单位秒
    :return: 钉钉接口返回结果
    """
    return DingTalkRobotV2(
        app_key=app_key,
        app_secret=app_secret,
        robot_code=robot_code,
        open_conversation_id=open_conversation_id,
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        timeout=timeout,
    ).send_group(
        message_type,
        content,
        title=title,
        at_mobiles=at_mobiles,
        at_all=at_all,
    )


def send_dingtalk_private(
    message_type,
    content,
    *,
    app_key=None,
    app_secret=None,
    robot_code=None,
    title=None,
    user_ids=None,
    user_mobiles=None,
    timeout=10.0,
):
    """
    发送钉钉私聊消息。

    自动补全规则：
    - 私聊只走企业内部机器人
    - app_key 和 app_secret 由调用方提供
    - 私聊不使用 webhook_url

    :param message_type: 消息类型，只支持 text、markdown、image
    :param content: 文本内容、Markdown 内容，或本地图片路径
    :param app_key: 企业内部应用 AppKey，必填
    :param app_secret: 企业内部应用 AppSecret，必填
    :param robot_code: 企业内部机器人编码，可不传
    :param title: Markdown 消息标题，仅 markdown 时使用
    :param user_ids: 接收人的钉钉 userId 列表
    :param user_mobiles: 接收人的手机号列表，会先自动换取 userId
    :param timeout: 请求超时时间，单位秒
    :return: 钉钉接口返回结果
    """
    return DingTalkRobotV2(
        app_key=app_key,
        app_secret=app_secret,
        robot_code=robot_code,
        timeout=timeout,
    ).send_private(
        message_type,
        content,
        title=title,
        user_ids=user_ids,
        user_mobiles=user_mobiles,
    )
