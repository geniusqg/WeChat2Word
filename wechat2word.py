"""
wechat2word.py
~~~~~~~~~~~~~~~
微信聊天记录导出工具 — 主入口（CLI）

功能：
  1. 自动从运行中的微信 PC 版获取数据库密钥
  2. 解密并解析聊天记录
  3. 导出为纯文本文件（.txt）

用法：
  python wechat2word.py                          # 交互式选择会话导出
  python wechat2word.py --account <账号>         # 导出所有会话
  python wechat2word.py --session <会话ID>       # 导出指定会话
  python wechat2word.py --key <密钥> --wx-dir <路径>  # 手动指定密钥和路径

依赖：
  pip install pysqlcipher3
  （无需 python-docx，txt 格式纯 Python 无依赖）
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# ── 检查可选依赖（pysqlcipher3，用于自动解密）────────
try:
    import pysqlcipher3  # noqa: F401
    HAS_PYSQLCIPHER = True
except ImportError:
    HAS_PYSQLCIPHER = False


# ── 内部模块 ───────────────────────────────────────
from db_parser import WeChatDB
from exporter import export_chat_txt

try:
    from key_extractor import get_wechat_key
    HAS_KEY_EXTRACTOR = True
except Exception:
    HAS_KEY_EXTRACTOR = False


# ── CLI 参数解析 ───────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="微信聊天记录 → Word 文档导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python wechat2word.py                        # 交互式选择
  python wechat2word.py --list                 # 仅列出所有会话
  python wechat2word.py --session filehelper   # 导出"文件传输助手"
  python wechat2word.py --account wxid_xxx     # 导出该账号所有会话
  python wechat2word.py --key <hex> --wx-dir "C:/WeChat Files/wxid_xxx" --session xxx
  python wechat2word.py --msg-db ./MSG.db --micro-db ./MicroMsg.db --session xxx
""",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--msg-db",  help="已解密的消息数据库路径（普通 SQLite）")
    group.add_argument("--account", help="微信账号（wxid_xxx），自动定位数据目录")

    parser.add_argument("--micro-db", help="已解密的联系人数据库路径（需配合 --msg-db 使用）")
    parser.add_argument("--key",      help="手动指定数据库密钥（32位 hex）")
    parser.add_argument("--wx-dir",   help="手动指定微信数据目录")
    parser.add_argument("--session",  help="指定要导出的会话用户名（如 filehelper）")
    parser.add_argument("--limit",    type=int, default=0,
                        help="最多导出消息条数（0=不限制）")
    parser.add_argument("--days",     type=int, default=0,
                        help="只导出最近 N 天的消息（0=不限制）")
    parser.add_argument("--output",   help="输出文件路径（默认桌面）")
    parser.add_argument("--list",      action="store_true",
                        help="列出所有会话后退出")
    parser.add_argument("--no-auto-key", action="store_true",
                        help="禁用自动密钥获取，强制使用手动参数")
    return parser.parse_args()


# ── 核心流程 ───────────────────────────────────────

def get_db_info(args) -> tuple[str, str]:
    """
    根据命令行参数确定 wx_dir 和 key。
    返回 (wx_dir, key_hex)
    """
    if args.msg_db:
        # 已解密模式，不需要 key
        return "", ""

    if args.key and args.wx_dir:
        return args.wx_dir, args.key

    if not HAS_KEY_EXTRACTOR or args.no_auto_key:
        raise RuntimeError(
            "请提供 --key 和 --wx-dir，或先安装 key_extractor 所需依赖后重试"
        )

    print("[*] 正在从微信进程获取密钥（请确保微信已登录运行中）...")
    info = get_wechat_key()
    print(f"[+] 获取成功：{info['name']} ({info['account']})")
    return info["wx_dir"], info["key"]


def list_sessions(wx_dir: str, key: str, msg_db: str, micro_db: str):
    """列出所有会话。"""
    try:
        db = WeChatDB(wx_dir=wx_dir, key=key,
                      msg_db_path=msg_db, micro_db_path=micro_db)
        db.open()
        contacts = db.get_contacts()
        sessions = db.list_sessions(contacts)
        db.close()
    except Exception as e:
        print(f"[-] 无法连接数据库：{e}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"{'会话名':<30} {'消息数':>8}  {'最后消息时间':>18}")
    print("-" * 60)
    for s in sessions:
        name = s["display_name"][:28]
        cnt  = s["msg_count"]
        ts   = s["last_time"].strftime("%Y-%m-%d %H:%M")
        print(f"{name:<30} {cnt:>8}  {ts:>18}")
    print(f"{'='*60}")
    print(f"共 {len(sessions)} 个会话")


def export_one_session(
    db: WeChatDB,
    talker: str,
    display_name: str,
    output_path: str,
    limit: int,
    days: int,
):
    """导出单个会话为 txt 文件。"""
    contacts = db.get_contacts()
    # 确保显示名有值
    if not display_name:
        display_name = db.get_display_name(talker, contacts)

    start_time = None
    if days > 0:
        start_time = datetime.now() - timedelta(days=days)

    messages = db.get_messages(talker, limit=limit, start_time=start_time)

    print(f"[*] 开始导出：{display_name}")
    export_chat_txt(
        chat_name  = display_name,
        messages   = messages,
        output_path= output_path,
    )
    print(f"[✓] 完成：{output_path}")


def interactive_choose_session(
    db: WeChatDB,
) -> tuple[str, str]:
    """交互式选择要导出的会话。"""
    contacts = db.get_contacts()
    sessions = db.list_sessions(contacts)

    print("\n可用会话（输入序号）：")
    for i, s in enumerate(sessions[:50], 1):
        print(f"  {i:>2}. {s['display_name']}  ({s['msg_count']} 条消息)")

    if len(sessions) > 50:
        print(f"  ... 还有 {len(sessions)-50} 个会话（用 --session 指定）")

    while True:
        choice = input("\n请输入序号（q退出）: ").strip()
        if choice.lower() == "q":
            sys.exit(0)
        try:
            idx = int(choice) - 1
            s = sessions[idx]
            return s["talker"], s["display_name"]
        except (ValueError, IndexError):
            print("无效输入，请重试")


def main():
    args = parse_args()

    # ── 处理已解密数据库模式 ───────────────────
    msg_db_path  = args.msg_db or ""
    micro_db_path = args.micro_db or ""
    if msg_db_path and not micro_db_path:
        print("[!] 提供了 --msg-db 但缺少 --micro-db，使用单文件模式（部分功能受限）")
        micro_db_path = ""

    # ── 确定数据库路径 ─────────────────────────
    wx_dir, key = get_db_info(args)

    # ── 打开数据库 ─────────────────────────────
    try:
        db = WeChatDB(
            wx_dir        = wx_dir,
            key           = key,
            msg_db_path   = msg_db_path,
            micro_db_path = micro_db_path,
        )
        db.open()
    except Exception as e:
        print(f"[-] 无法打开数据库：{e}")
        sys.exit(1)

    # ── 仅列出会话 ─────────────────────────────
    if args.list:
        list_sessions(wx_dir, key, msg_db_path, micro_db_path)
        db.close()
        return

    # ── 确定输出路径 ───────────────────────────
    output_dir = Path(args.output).parent if args.output else Path.home() / "Desktop"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 确定要导出的会话 ───────────────────────
    contacts = db.get_contacts()

    if args.session:
        talker = args.session
        display_name = db.get_display_name(talker, contacts)
    else:
        talker, display_name = interactive_choose_session(db)

    # 文件名：聊天记录_张三_20260101.txt
    safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in display_name)
    ts_str = datetime.now().strftime("%Y%m%d")
    out_file = output_dir / f"聊天记录_{safe_name}_{ts_str}.txt"
    if args.output:
        out_file = Path(args.output)

    export_one_session(
        db, talker, display_name,
        output_path=str(out_file),
        limit=args.limit,
        days=args.days,
    )
    db.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[✗] 已取消")
        sys.exit(1)
