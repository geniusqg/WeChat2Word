"""
exporter.py
~~~~~~~~~~~
将微信聊天记录导出为纯文本文件（.txt）。

用法：
    from exporter import export_chat_txt
    export_chat_txt(
        chat_name="张三",
        messages=msg_generator,
        output_path="聊天记录_张三.txt",
    )
"""

import os
from datetime import datetime
from typing import Generator


# 消息类型的中文标签
MSG_TYPE_LABELS = {
    1:      "",
    3:      "[图片] ",
    34:     "[语音消息] ",
    43:     "[视频] ",
    47:     "[表情] ",
    49:     "[链接] ",
    50:     "[通话] ",
    10000:  "",
    10002:  "[撤回消息] ",
}


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def export_chat_txt(
    chat_name: str,
    messages: Generator[dict, None, None],
    output_path: str,
    show_type: bool = True,
) -> str:
    """
    将聊天记录导出为 txt 文件。

    参数：
        chat_name   : 聊天对象名称（显示在标题和文件名中）
        messages    : 消息生成器，每条消息格式：
                      {
                          'type': int,
                          'is_send': bool,
                          'time': datetime,
                          'sender': str,     # 群聊时为发送者 wxid
                          'content': str,
                          'raw_content': str,
                      }
        output_path : 输出文件路径
        show_type   : 是否显示消息类型前缀（如 [图片]）
    返回：
        输出文件路径
    """
    lines: list[str] = []

    # ── 封面 ──────────────────────────────────
    width = 60
    sep   = "─" * width
    pad   = lambda s: f"  {s}"

    lines.append(sep)
    lines.append(f"  微信聊天记录")
    lines.append(f"  聊天对象：{chat_name}")
    lines.append(f"  导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  {'─' * width}")
    lines.append("")  # 空行

    last_date  = None
    last_sender = None

    for msg in messages:
        msg_time   = msg["time"] if isinstance(msg["time"], datetime) else datetime.fromtimestamp(msg["time"])
        msg_type   = msg["type"]
        is_send    = bool(msg["is_send"])
        sender     = msg.get("sender", "")
        content    = msg.get("content", "") or ""

        # ── 日期分隔线 ──────────────────────
        date_str = msg_time.strftime("%Y-%m-%d")
        if date_str != last_date:
            lines.append("")
            lines.append(f"  ┌{'─' * (width - 4)}┐")
            lines.append(f"  │  {date_str}  {' ' * (width - 20)}│")
            lines.append(f"  └{'─' * (width - 4)}┘")
            lines.append("")
            last_date   = date_str
            last_sender = None

        # ── 系统消息 ────────────────────────
        if msg_type in (10000, 10002):
            sys_text = content or msg.get("raw_content", "")
            lines.append(f"      {sys_text}")
            lines.append("")
            continue

        # ── 普通消息 ───────────────────────
        prefix = MSG_TYPE_LABELS.get(msg_type, f"[类型{msg_type}] ")
        if show_type and msg_type not in (1, 10000, 10002):
            content = prefix + content

        me_label   = "我"
        other_label = sender if sender else "对方"

        if is_send:
            # 自己发的
            label = me_label
            bullet = "●"
        else:
            label   = other_label
            bullet  = "○"

        time_str = msg_time.strftime("%H:%M:%S")

        # 发送者变化时换行
        if sender != last_sender and sender:
            lines.append("")  # 换行区分不同说话人

        line = f"  {bullet} [{time_str}] {label}：{content}"
        lines.append(line)

        last_sender = sender

    # ── 结尾 ──────────────────────────────────
    lines.append("")
    lines.append(sep)
    lines.append("  本文档由 WeChat2Word 自动生成 · 仅供个人备份使用")
    lines.append(sep)

    # ── 写入文件 ───────────────────────────────
    text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    print(f"[+] 已保存到：{os.path.abspath(output_path)}")
    return output_path
