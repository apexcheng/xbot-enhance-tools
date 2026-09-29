import ctypes
import os
from ctypes import wintypes


def get_wps_lock_user(workbook):
    """
    获取 WPS / Excel 共享文件当前占用者用户名。

    :param workbook: 影刀 Excel 工作簿对象
    :return: 占用者用户名；锁文件存在但无法解析时返回“未知用户”；未占用时返回 None
    """
    if workbook.workbook.ReadOnly == False:
        return None

    file_path = workbook.get_full_name()

    folder = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    lock_path = os.path.join(folder, "~$" + filename)

    if not os.path.exists(lock_path):
        return None

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    CreateFileW.restype = wintypes.HANDLE

    ReadFile = kernel32.ReadFile
    ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    ReadFile.restype = wintypes.BOOL

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    GENERIC_READ = 0x80000000

    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    FILE_SHARE_DELETE = 0x00000004

    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80

    handle = CreateFileW(
        lock_path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )

    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    if handle == INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        raise OSError(error, ctypes.FormatError(error), lock_path)

    try:
        buffer = ctypes.create_string_buffer(4096)
        bytes_read = wintypes.DWORD()

        if not ReadFile(
            handle,
            buffer,
            len(buffer),
            ctypes.byref(bytes_read),
            None,
        ):
            error = ctypes.get_last_error()
            raise OSError(error, ctypes.FormatError(error), lock_path)

        data = buffer.raw[:bytes_read.value]

        if not data:
            return "未知用户"

        # 优先读取 Unicode 用户名。
        # 当前实测 WPS 锁文件：
        # 0~54   为 ANSI/GBK 区域
        # 55~56  为 Unicode 用户名字符数
        # 57开始 为 UTF-16LE 用户名
        if len(data) >= 57:
            name_length = int.from_bytes(data[55:57], "little")

            if 0 < name_length <= 54:
                end = 57 + name_length * 2

                if end <= len(data):
                    user_name = data[57:end].decode("utf-16le").strip()

                    if user_name:
                        return user_name

        # 兼容只有 ANSI / GBK 用户名的情况
        name_length = data[0]

        if 0 < name_length <= 54 and 1 + name_length <= len(data):
            try:
                user_name = data[1:1 + name_length].decode("gbk").strip()

                if user_name:
                    return user_name
            except UnicodeDecodeError:
                pass

        return "未知用户"

    finally:
        CloseHandle(handle)
