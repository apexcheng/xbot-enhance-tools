"""影刀自定义对话框配置的加密持久化工具。

对外只提供 3 个方法：

1. ``dialog_result_to_dict(dialog_result)``
   将 ``xbot.app.dialog.show_custom_dialog`` 的返回对象转换为普通 ``dict``。
2. ``save_secret_config(json_path, config_obj, ...)``
   使用 Windows DPAPI 加密配置并持久化到磁盘。
3. ``load_secret_config(json_path, ...)``
   从磁盘读取并解密配置，返回普通 ``dict``。

典型调用流程：

    dialog_result = xbot.app.dialog.show_custom_dialog(...)
    config = dialog_result_to_dict(dialog_result)
    save_secret_config(config_path, config)
    config = load_secret_config(config_path)

加密使用 Windows DPAPI，密文默认只能由执行加密的 Windows 用户在同一
Windows 安全上下文中解密。磁盘文件只保存 Base64 编码后的加密 token，
不保存明文配置。
"""

import ast
import base64
import ctypes
import json
from ctypes import wintypes
from pathlib import Path


__all__ = ["dialog_result_to_dict", "save_secret_config", "load_secret_config"]


_IGNORE_ATTR = {
    "__doc__", "__slots__", "_fields", "_field_defaults", "__new__", "_make", "_replace", "__repr__",
    "_asdict", "__getnewargs__", "__match_args__", "pressed_button", "__module__", "__hash__",
    "__getattribute__", "__lt__", "__le__", "__eq__", "__ne__", "__gt__", "__ge__", "__iter__",
    "__len__", "__getitem__", "__add__", "__mul__", "__rmul__", "__contains__", "index", "count",
    "__class_getitem__", "__str__", "__setattr__", "__delattr__", "__init__", "__reduce_ex__", "__reduce__",
    "__subclasshook__", "__init_subclass__", "__format__", "__sizeof__", "__dir__", "__class__",
}


class _DATA_BLOB(ctypes.Structure):
    """Windows CryptoAPI 使用的二进制数据结构。"""

    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


_crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_CryptProtectData = _crypt32.CryptProtectData
_CryptProtectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
    wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
]
_CryptProtectData.restype = wintypes.BOOL

_CryptUnprotectData = _crypt32.CryptUnprotectData
_CryptUnprotectData.argtypes = [
    ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p,
    ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DATA_BLOB),
]
_CryptUnprotectData.restype = wintypes.BOOL

_LocalFree = _kernel32.LocalFree
_LocalFree.argtypes = [ctypes.c_void_p]
_LocalFree.restype = ctypes.c_void_p


def _to_blob(data):
    """把 ``bytes`` 转换为 CryptoAPI 可读取的 ``DATA_BLOB``。

    同时返回底层 buffer，保证 Windows API 调用结束前内存不会被 Python 回收。
    """
    buffer = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    blob = _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _blob_to_bytes(blob):
    """把 CryptoAPI 返回的 ``DATA_BLOB`` 转换回 ``bytes``。"""
    return ctypes.string_at(blob.pbData, blob.cbData)


def _auto_convert(value):
    """把对话框字符串尽量还原为 Python 基础对象。

    ``show_custom_dialog`` 的部分字段会以字符串形式返回。例如 ``"True"``、
    ``"123"``、``"[1, 2]"`` 或 JSON 字符串。这里先尝试
    ``ast.literal_eval``，失败后再尝试 ``json.loads``；两种方式都失败时
    保留原字符串。

    对 dict、list、tuple、set 会递归转换其内部值。
    """
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text:
        return value

    try:
        value = ast.literal_eval(text)
    except Exception:
        try:
            value = json.loads(text)
        except Exception:
            return value

    if isinstance(value, dict):
        return {key: _auto_convert(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_auto_convert(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_auto_convert(item) for item in value)
    if isinstance(value, set):
        return {_auto_convert(item) for item in value}

    return value


def dialog_result_to_dict(dialog_result, ignore_attr=None):
    """将影刀 ``show_custom_dialog`` 返回值转换为普通字典。

    :param dialog_result: ``xbot.app.dialog.show_custom_dialog`` 的返回对象；如果
        已经是 dict，则直接清洗其中的值。
    :param ignore_attr: 可选的属性忽略集合。通常无需传入；默认使用本模块针对
        影刀对话框返回对象维护的忽略列表。
    :return: 可直接用于业务逻辑或传给 ``save_secret_config`` 的普通 dict。

    字符串字段会经过 ``_auto_convert`` 自动转换。例如 ``"True"`` 转为
    ``True``，``"[1, 2]"`` 转为 list。对影刀返回对象中读取失败的内部属性
    会跳过，不影响其他配置字段。
    """
    if isinstance(dialog_result, dict):
        return {key: _auto_convert(value) for key, value in dialog_result.items()}

    ignore_attr = ignore_attr or _IGNORE_ATTR
    config = {}

    for attr in object.__dir__(dialog_result):
        if attr in ignore_attr:
            continue

        try:
            config[attr] = _auto_convert(getattr(dialog_result, attr))
        except Exception:
            continue

    return config


def _encrypt_json_dpapi(obj, entropy="", description="my_app"):
    """使用当前 Windows 用户的 DPAPI 加密配置并返回 Base64 token。

    :param obj: 必须能被 ``json.dumps`` 序列化的 Python 对象。
    :param entropy: 可选附加熵。保存和读取必须传入完全相同的值。
    :param description: 写入 DPAPI 密文的描述文本，不参与业务数据。
    :return: 可安全写入 JSON 文件的 Base64 字符串。
    :raises OSError: Windows ``CryptProtectData`` 调用失败时抛出。
    """
    plaintext = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    in_blob, in_buffer = _to_blob(plaintext)
    entropy_blob, entropy_buffer = _to_blob(entropy.encode("utf-8")) if entropy else (_DATA_BLOB(0, None), None)
    out_blob = _DATA_BLOB()

    ok = _CryptProtectData(
        ctypes.byref(in_blob), description, ctypes.byref(entropy_blob), None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        raise OSError(ctypes.get_last_error())

    try:
        return base64.urlsafe_b64encode(_blob_to_bytes(out_blob)).decode("ascii")
    finally:
        _LocalFree(out_blob.pbData)


def _decrypt_json_dpapi(token, entropy=""):
    """解密 ``_encrypt_json_dpapi`` 生成的 token。

    :param token: ``_encrypt_json_dpapi`` 返回的 Base64 token。
    :param entropy: 加密时使用的附加熵；必须与保存时完全一致。
    :return: 解密并 JSON 反序列化后的 Python 对象。
    :raises OSError: Windows ``CryptUnprotectData`` 调用失败时抛出。
    """
    ciphertext = base64.urlsafe_b64decode(token.encode("ascii"))
    in_blob, in_buffer = _to_blob(ciphertext)
    entropy_blob, entropy_buffer = _to_blob(entropy.encode("utf-8")) if entropy else (_DATA_BLOB(0, None), None)
    out_blob = _DATA_BLOB()
    desc_ptr = wintypes.LPWSTR()

    ok = _CryptUnprotectData(
        ctypes.byref(in_blob), ctypes.byref(desc_ptr), ctypes.byref(entropy_blob), None, None, 0, ctypes.byref(out_blob)
    )
    if not ok:
        raise OSError(ctypes.get_last_error())

    try:
        return json.loads(_blob_to_bytes(out_blob).decode("utf-8"))
    finally:
        _LocalFree(out_blob.pbData)
        if desc_ptr:
            _LocalFree(desc_ptr)


def load_secret_config(json_path, entropy=""):
    """读取磁盘上的加密配置并返回普通字典。

    :param json_path: 加密配置文件路径。文件格式为 ``{"token": "..."}``。
    :param entropy: 保存时使用的附加熵；如果保存时未传，则读取时也保持默认空串。
    :return: 解密成功时返回 dict；文件不存在、JSON 无效、token 缺失、解密失败
        或解密结果不是 dict 时返回 ``None``。

    该方法用于机器人启动阶段读取初始化配置。读取失败统一返回 ``None``，方便
    调用方判断是否需要重新弹出配置对话框。
    """
    path = Path(json_path)
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        token = data.get("token")
        if not isinstance(token, str) or not token.strip():
            return None
        config = _decrypt_json_dpapi(token.strip(), entropy=entropy)
    except Exception:
        return None

    return config if isinstance(config, dict) else None


def save_secret_config(json_path, config_obj, entropy="", description="my_app"):
    """使用 Windows DPAPI 加密配置并持久化到磁盘。

    :param json_path: 配置文件保存路径；父目录不存在时自动创建。
    :param config_obj: 要保存的普通 dict。通常来自 ``dialog_result_to_dict``。
    :param entropy: 可选附加熵。若传入，后续读取必须使用相同的值。
    :param description: DPAPI 描述文本，默认 ``"my_app"``。
    :return: ``None``。
    :raises TypeError: ``config_obj`` 中包含无法 JSON 序列化的数据时抛出。
    :raises OSError: DPAPI 加密或文件写入失败时抛出。

    磁盘文件只保存 ``{"token": "<加密后的 Base64>"}``，不会写入明文配置。
    """
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = _encrypt_json_dpapi(config_obj, entropy=entropy, description=description)
    path.write_text(json.dumps({"token": token}, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_dialog_config(json_path, dialog_result, entropy="", description="my_app"):
    """内部快捷方法：转换影刀对话框结果后直接加密保存。

    对外不推荐使用此方法。显式调用 ``dialog_result_to_dict`` 后再调用
    ``save_secret_config``，数据流更清晰，也更方便调用方在保存前检查或修改配置。
    """
    config = dialog_result_to_dict(dialog_result)
    save_secret_config(json_path, config, entropy=entropy, description=description)
    return config
