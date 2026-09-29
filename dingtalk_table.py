"""将表格数据转换为钉钉可用的 Markdown。"""


def to_markdown_table(data, headers=None, max_cell_length=None):
    """将字典行或列表行转换为 Markdown 表格。

    :param data: list[dict] 或 list[list/tuple]；字典行默认用首行键名作表头
    :param headers: 可选表头；列表行不传时自动生成列名
    :param max_cell_length: 单元格最大显示长度，超过后截断
    :return: Markdown 表格字符串；空数据返回空字符串
    """
    if not data:
        return ""

    def format_cell(value):
        """将单元格值转为单行文本，并按需截断。"""
        value = str(value).replace("\n", " ")

        if max_cell_length and len(value) > max_cell_length:
            value = value[:max_cell_length - 3] + "..."

        return value

    # list[dict]
    if isinstance(data[0], dict):
        if headers is None:
            headers = list(data[0].keys())

        lines = []
        lines.append("| " + " | ".join(map(str, headers)) + " |")
        lines.append("|" + "|".join(["---"] * len(headers)) + "|")

        for row in data:
            values = [format_cell(row.get(h, "")) for h in headers]
            lines.append("| " + " | ".join(values) + " |")

        return "\n".join(lines)

    # list[list/tuple]
    elif isinstance(data[0], (list, tuple)):
        if headers is None:
            headers = [f"列{i+1}" for i in range(len(data[0]))]

        lines = []
        lines.append("| " + " | ".join(map(str, headers)) + " |")
        lines.append("|" + "|".join(["---"] * len(headers)) + "|")

        for row in data:
            values = [format_cell(v) for v in row]
            lines.append("| " + " | ".join(values) + " |")

        return "\n".join(lines)

    else:
        raise TypeError("data 必须是 list[dict] 或 list[list/tuple]")
