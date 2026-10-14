import time
from pathlib import Path
import fnmatch


def wait_appear_by_xpath(page, xpath, timeout=20):
    """等待 XPath 对应的元素出现（匹配到一个及以上即算出现）。

    用 find_all_by_xpath 而不是 find_by_xpath：后者在匹配到多个元素时会抛异常，
    导致"等待出现"被误判为失败。

    :param page: xbot.web 页面对象。
    :param str xpath: XPath 字符串。
    :param int|float timeout: 最多等待秒数。
    :return: 找到的第一个元素；超时返回 None。
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            elements = page.find_all_by_xpath(xpath, timeout=1)
        except Exception:
            elements = []
        if elements:
            return elements[0]

    return None


def wait_disappear_by_xpath(page, xpath, timeout=20):
    """等待 XPath 对应的元素全部消失。

    用 find_all_by_xpath 判断：返回空列表才算消失，避免匹配到多个元素时
    find_by_xpath 抛异常被误判为"已消失"。

    :param page: xbot.web 页面对象。
    :param str xpath: XPath 字符串。
    :param int|float timeout: 最多等待秒数。
    :return: 消失返回 True，超时返回 False。
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            elements = page.find_all_by_xpath(xpath, timeout=1)
        except Exception:
            elements = []
        if not elements:
            return True

    return False


def wait_download_file(download_dir=None, filename_pattern=None, timeout=300, start_time=None):
    """等待下载目录中的文件下载完成。

    :param download_dir: 下载目录，不传则默认使用当前用户下载目录
    :param filename_pattern: 可选，文件名关键词或 glob 表达式，例如 "支付宝"、"*.xlsx"、"*账单*.csv"
    :param timeout: 最大等待秒数
    :param start_time: 下载开始时间，建议点击下载前用 time.time() 记录
    :return: Path
    """
    interval = 1

    if download_dir is None:
        download_dir = Path.home() / "Downloads"
        if not download_dir.exists():
            download_dir = Path.home() / "下载"
    else:
        download_dir = Path(download_dir)

    deadline = time.time() + timeout

    if start_time is None:
        start_time = time.time()

    temp_suffixes = {".crdownload", ".part", ".tmp"}
    file_states = {}

    while time.time() < deadline:
        if not download_dir.exists():
            time.sleep(interval)
            continue

        files = [p for p in download_dir.iterdir() if p.is_file() and not p.name.startswith("~$")]
        candidates = []

        if filename_pattern:
            pattern = str(filename_pattern)

            # 没有 glob 符号时，按关键词包含匹配
            if not any(char in pattern for char in "*?[]"):
                pattern = f"*{pattern}*"

            for p in files:
                if p.suffix.lower() in temp_suffixes:
                    continue
                if fnmatch.fnmatch(p.name, pattern):
                    candidates.append(p)
        else:
            candidates = [
                p for p in files
                if p.suffix.lower() not in temp_suffixes
            ]

        try:
            # 优先检查最新文件，避免目录中多个匹配文件时误取旧文件
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        except FileNotFoundError:
            time.sleep(interval)
            continue

        for file_path in candidates:
            try:
                stat = file_path.stat()
                size = stat.st_size
                mtime = stat.st_mtime

                # 只接受点击下载之后新增或更新的文件，预留 2 秒容错
                if mtime < start_time - 2:
                    continue

                if size <= 0:
                    continue

                old_state = file_states.get(file_path)
                current_state = (size, mtime)

                # 当前轮和上一轮大小、修改时间都一致，认为下载完成
                if old_state == current_state:
                    return file_path

                file_states[file_path] = current_state

            except FileNotFoundError:
                continue

        time.sleep(interval)

    raise TimeoutError(f"等待下载文件超时：{download_dir}，filename_pattern={filename_pattern}")
