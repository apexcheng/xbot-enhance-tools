from xbot import win32


def is_win_element_clickable(element):
    """判断 Win 元素中心点是否在当前屏幕范围内。"""
    x, y, width, height = element.get_bounding()

    if width <= 0 or height <= 0:
        return False

    screen_width, screen_height = win32.get_screen_size()
    center_x = x + width / 2
    center_y = y + height / 2

    return 0 <= center_x <= screen_width and 0 <= center_y <= screen_height