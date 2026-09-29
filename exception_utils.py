import sys
import traceback
from datetime import datetime


def format_exception_detail(e):
    """格式化异常详情。

    :param e: 异常对象或异常字符串
    :return: 格式化后的异常信息
    """
    tb_obj = None

    if hasattr(e, "__traceback__") and e.__traceback__:
        tb_obj = e.__traceback__
    else:
        _, _, tb_obj = sys.exc_info()

    if tb_obj:
        tb = traceback.extract_tb(tb_obj)
        last = tb[-1]
    else:
        stack = traceback.extract_stack()
        last = stack[-2]

    return f"""错误信息：`{str(e).strip()}`\n
        错误位置：`{last.filename}:{last.lineno}`\n
        当前时间：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n
        函数：`{last.name}`\n
        代码：`{last.line or "未获取到代码行"}`"""
