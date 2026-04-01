"""
quick_export.py — 快速导出脚本（无需交互）

使用方法：
    python quick_export.py 文件传输助手
    python quick_export.py 群聊名 --days 30 --output ./output.docx

适用于只想快速导出某个特定会话的场景。
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# 尝试自动获取密钥（Windows）
try:
    from key_extractor import get_wechat_key
    HAS_AUTO_KEY = True
except Exception:
    HAS_AUTO_KEY = False

from db_parser import WeChatDB
from exporter import export_chat_txt


def main():
    parser = argparse.ArgumentParser(description="快速导出微信聊天记录为 Word")
    parser.add_argument("session", help="会话名称或用户名（wxid_xxx）")
    parser.add_argument("--key",    help="数据库密钥（32位 hex）")
    parser.add_argument("--wx-dir", help="微信数据目录")
    parser.add_argument("--msg-db", help="已解密的消息数据库路径")
    parser.add_argument("--micro-db", help="已解密的联系人数据库路径")
    parser.add_argument("--days",   type=int, default=0, help="只导出最近 N 天")
    parser.add_argument("--limit",  type=int, default=0, help="最多导出条数")
    parser.add_argument("--output", help="输出文件路径")
    args = parser.parse_args()

    # ── 获取密钥 ──────────────────────────────
    wx_dir, key = "", ""
    if args.msg_db:
        pass  # 已解密模式
    elif args.key and args.wx_dir:
        wx_dir, key = args.wx_dir, args.key
    elif HAS_AUTO_KEY:
        print("[*] 正在获取微信密钥...")
        info = get_wechat_key()
        wx_dir, key = info["wx_dir"], info["key"]
        print(f"[+] 账号：{info['name']} ({info['account']})")
    else:
        print("[-] 需要提供 --key 和 --wx-dir，或在 Windows 上运行以自动获取密钥")
        sys.exit(1)

    # ── 打开数据库 ────────────────────────────
    try:
        db = WeChatDB(wx_dir=wx_dir, key=key,
                      msg_db_path=args.msg_db or "",
                      micro_db_path=args.micro_db or "")
        db.open()
    except Exception as e:
        print(f"[-] 数据库打开失败：{e}")
        sys.exit(1)

    contacts = db.get_contacts()

    # 查找匹配的会话
    sessions = db.list_sessions(contacts)
    matched = None
    for s in sessions:
        if (args.session.lower() in s["talker"].lower()
                or args.session.lower() in s["display_name"].lower()):
            matched = s
            break

    if not matched:
        print(f"[-] 未找到包含「{args.session}」的会话")
        db.close()
        sys.exit(1)

    talker = matched["talker"]
    display_name = matched["display_name"]
    print(f"[+] 已匹配：{display_name} ({matched['msg_count']} 条消息)")

    # ── 确定输出文件 ──────────────────────────
    if args.output:
        out_path = Path(args.output)
    else:
        desktop = Path.home() / "Desktop"
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in display_name)
        out_path = desktop / f"聊天记录_{safe}.txt"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ── 导出 ─────────────────────────────────
    start_time = None
    if args.days > 0:
        start_time = datetime.now() - timedelta(days=args.days)
        print(f"[*] 仅导出最近 {args.days} 天消息")

    print(f"[*] 开始导出到：{out_path}")
    messages = db.get_messages(talker, limit=args.limit or 0, start_time=start_time)
    export_chat_txt(
        chat_name=display_name,
        messages=messages,
        output_path=str(out_path),
    )
    db.close()
    print(f"\n[✓] 完成！文件已保存至：{out_path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[✗] 已取消")
