"""
db_parser.py
~~~~~~~~~~~~
解密并解析微信 PC 版本地 SQLite 数据库，提取聊天消息与联系人信息。

依赖：
    pip install pysqlcipher3   # Windows 需要 Visual C++ Build Tools
    # 或直接使用预解密后的普通 SQLite（手动用 DB Browser for SQLite 解密导出）

如果安装 pysqlcipher3 有困难，也支持传入已经解密好的 .db 文件路径（普通 sqlite3）。
"""

import os
import re
import sqlite3
import struct
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Generator

# ── 消息类型映射 ─────────────────────────────────
MSG_TYPES = {
    1:      "文本",
    3:      "图片",
    34:     "语音",
    43:     "视频",
    47:     "表情",
    49:     "链接/文件/小程序",
    50:     "通话",
    10000:  "系统通知",
    10002:  "撤回消息",
}


def _decrypt_db(src: str, key_hex: str, dst: str):
    """
    用 SQLCipher 解密微信数据库，输出普通 SQLite 文件。
    优先使用 pysqlcipher3；若未安装则尝试 sqlcipher 命令行工具。
    """
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher  # type: ignore
        conn = sqlcipher.connect(src)
        c = conn.cursor()
        c.execute(f"PRAGMA key=\"x'{key_hex}'\"")
        c.execute("PRAGMA cipher_page_size = 4096")
        c.execute("PRAGMA kdf_iter = 64000")
        c.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA1")
        c.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA1")
        c.execute(f"ATTACH DATABASE '{dst}' AS plaintext KEY ''")
        c.execute("SELECT sqlcipher_export('plaintext')")
        c.execute("DETACH DATABASE plaintext")
        conn.close()
        return
    except ImportError:
        pass

    # 回退：sqlcipher 命令行（需用户自行安装）
    import subprocess
    cmd = (
        f"sqlcipher \"{src}\" "
        f"\"PRAGMA key=\\\"x'{key_hex}'\\\"; "
        f"PRAGMA cipher_page_size=4096; "
        f"ATTACH DATABASE '{dst}' AS plaintext KEY ''; "
        f"SELECT sqlcipher_export('plaintext'); "
        f"DETACH DATABASE plaintext;\""
    )
    result = subprocess.run(cmd, shell=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"数据库解密失败。\\n请安装 pysqlcipher3：pip install pysqlcipher3\\n"
            f"或手动使用 DB Browser for SQLite 解密后再使用本工具。\\n"
            f"错误：{result.stderr.decode()}"
        )


class WeChatDB:
    """
    微信数据库访问封装。

    用法 A（自动解密）：
        db = WeChatDB(wx_dir="C:/Users/xxx/Documents/WeChat Files/wxid_xxx", key="abcdef1234...")
        db.open()

    用法 B（已解密的普通 sqlite 文件）：
        db = WeChatDB(msg_db_path="decrypted_MSG.db", micro_db_path="decrypted_MicroMsg.db")
        db.open()
    """

    def __init__(
        self,
        wx_dir: str = "",
        key: str = "",
        msg_db_path: str = "",
        micro_db_path: str = "",
    ):
        self.wx_dir = wx_dir
        self.key = key
        self._msg_db_path = msg_db_path
        self._micro_db_path = micro_db_path
        self._tmp_dir = None
        self.msg_conn: sqlite3.Connection | None = None
        self.micro_conn: sqlite3.Connection | None = None

    # ── 生命周期 ───────────────────────────────────

    def open(self):
        if self._msg_db_path and self._micro_db_path:
            # 已解密模式
            self.msg_conn = sqlite3.connect(self._msg_db_path)
            self.msg_conn.row_factory = sqlite3.Row
            self.micro_conn = sqlite3.connect(self._micro_db_path)
            self.micro_conn.row_factory = sqlite3.Row
            return

        if not self.wx_dir or not self.key:
            raise ValueError("需要提供 wx_dir + key，或 msg_db_path + micro_db_path")

        # 自动找到数据库文件并解密
        self._tmp_dir = tempfile.mkdtemp(prefix="wechat2word_")
        msg_src, micro_src = self._find_db_files()

        msg_dst = os.path.join(self._tmp_dir, "MSG.db")
        micro_dst = os.path.join(self._tmp_dir, "MicroMsg.db")

        print(f"[*] 正在解密 MSG.db ...")
        _decrypt_db(msg_src, self.key, msg_dst)
        print(f"[*] 正在解密 MicroMsg.db ...")
        _decrypt_db(micro_src, self.key, micro_dst)

        self.msg_conn = sqlite3.connect(msg_dst)
        self.msg_conn.row_factory = sqlite3.Row
        self.micro_conn = sqlite3.connect(micro_dst)
        self.micro_conn.row_factory = sqlite3.Row

    def close(self):
        if self.msg_conn:
            self.msg_conn.close()
        if self.micro_conn:
            self.micro_conn.close()
        if self._tmp_dir:
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    # ── 数据库文件定位 ────────────────────────────

    def _find_db_files(self) -> tuple[str, str]:
        base = Path(self.wx_dir)
        msg_candidates = list(base.rglob("MSG.db")) + list(base.rglob("MSG0.db"))
        micro_candidates = list(base.rglob("MicroMsg.db"))

        if not msg_candidates:
            raise FileNotFoundError(f"在 {self.wx_dir} 下未找到 MSG.db")
        if not micro_candidates:
            raise FileNotFoundError(f"在 {self.wx_dir} 下未找到 MicroMsg.db")

        return str(msg_candidates[0]), str(micro_candidates[0])

    # ── 联系人 ───────────────────────────────────

    def get_contacts(self) -> dict[str, dict]:
        """
        返回 {username: {'nickname': str, 'alias': str, 'remark': str, 'is_group': bool}}
        """
        contacts = {}
        try:
            cur = self.micro_conn.execute(
                "SELECT UserName, NickName, Alias, Remark, Type FROM Contact"
            )
            for row in cur:
                uname = row["UserName"] or ""
                contacts[uname] = {
                    "nickname": row["NickName"] or uname,
                    "alias":    row["Alias"] or "",
                    "remark":   row["Remark"] or "",
                    "is_group": uname.endswith("@chatroom"),
                }
        except Exception as e:
            print(f"[!] 读取联系人表失败: {e}")
        return contacts

    def get_display_name(self, username: str, contacts: dict) -> str:
        info = contacts.get(username, {})
        return info.get("remark") or info.get("nickname") or username

    # ── 会话列表 ─────────────────────────────────

    def list_sessions(self, contacts: dict | None = None) -> list[dict]:
        """
        返回所有会话，按最后消息时间降序。
        每项：{'talker': str, 'display_name': str, 'msg_count': int, 'last_time': datetime}
        """
        if contacts is None:
            contacts = self.get_contacts()
        sessions = []
        try:
            cur = self.msg_conn.execute(
                """
                SELECT StrTalker,
                       COUNT(*)       AS cnt,
                       MAX(CreateTime) AS last_ts
                FROM MSG
                GROUP BY StrTalker
                ORDER BY last_ts DESC
                """
            )
            for row in cur:
                talker = row["StrTalker"]
                sessions.append({
                    "talker":       talker,
                    "display_name": self.get_display_name(talker, contacts),
                    "msg_count":    row["cnt"],
                    "last_time":    datetime.fromtimestamp(row["last_ts"]),
                })
        except Exception as e:
            print(f"[!] 读取会话列表失败: {e}")
        return sessions

    # ── 消息读取 ─────────────────────────────────

    def get_messages(
        self,
        talker: str,
        limit: int = 0,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> Generator[dict, None, None]:
        """
        逐条 yield 消息字典：
        {
            'id': int,
            'type': int,
            'type_name': str,
            'is_send': bool,
            'time': datetime,
            'sender': str,       # 群聊时为发送者 wxid
            'content': str,
            'raw_content': str,
        }
        """
        conditions = ["StrTalker = ?"]
        params: list = [talker]

        if start_time:
            conditions.append("CreateTime >= ?")
            params.append(int(start_time.timestamp()))
        if end_time:
            conditions.append("CreateTime <= ?")
            params.append(int(end_time.timestamp()))

        where = " AND ".join(conditions)
        sql = f"SELECT * FROM MSG WHERE {where} ORDER BY CreateTime ASC"
        if limit:
            sql += f" LIMIT {limit}"

        cur = self.msg_conn.execute(sql, params)
        for row in cur:
            yield self._parse_row(dict(row))

    def _parse_row(self, row: dict) -> dict:
        msg_type = row.get("Type", 1)
        raw_content = row.get("StrContent", "") or ""
        content = self._extract_content(msg_type, raw_content, row)

        # 群消息发送者在 StrContent 或 BytesExtra 里
        sender = ""
        talker = row.get("StrTalker", "")
        if talker.endswith("@chatroom"):
            # 群消息：content 前缀可能是 "wxid_xxx:\n实际内容"
            m = re.match(r"^([\w@.]+):\n(.+)$", raw_content, re.DOTALL)
            if m:
                sender = m.group(1)
                if msg_type == 1:
                    content = m.group(2)

        return {
            "id":          row.get("MsgSvrID", 0),
            "type":        msg_type,
            "type_name":   MSG_TYPES.get(msg_type, f"未知({msg_type})"),
            "is_send":     bool(row.get("IsSender", 0)),
            "time":        datetime.fromtimestamp(row.get("CreateTime", 0)),
            "sender":      sender,
            "content":     content,
            "raw_content": raw_content,
        }

    def _extract_content(self, msg_type: int, raw: str, row: dict) -> str:
        if msg_type == 1:
            return raw
        if msg_type == 3:
            return "[图片]"
        if msg_type == 34:
            return "[语音消息]"
        if msg_type == 43:
            return "[视频]"
        if msg_type == 47:
            return "[表情]"
        if msg_type == 49:
            # 解析 XML 获取描述
            return self._parse_type49(raw)
        if msg_type == 50:
            return "[语音/视频通话]"
        if msg_type == 10000:
            return f"[系统] {raw}"
        if msg_type == 10002:
            return "[消息已撤回]"
        return raw or f"[{MSG_TYPES.get(msg_type, '未知')}]"

    @staticmethod
    def _parse_type49(xml_str: str) -> str:
        """从 type=49 的 XML 内容中提取可读描述。"""
        if not xml_str:
            return "[链接/文件]"
        # 尝试提取 <title>
        m = re.search(r"<title>(.*?)</title>", xml_str, re.DOTALL)
        if m:
            title = m.group(1).strip()
            # 判断子类型
            sub = re.search(r"<type>(\d+)</type>", xml_str)
            sub_type = int(sub.group(1)) if sub else 0
            type_label = {
                1:  "链接",
                3:  "音乐",
                5:  "链接",
                6:  "文件",
                19: "聊天记录",
                33: "小程序",
                36: "小程序",
                57: "引用消息",
                63: "视频号",
            }.get(sub_type, "附件")
            return f"[{type_label}] {title}"
        return "[链接/文件]"
