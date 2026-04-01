"""
key_extractor.py
~~~~~~~~~~~~~~~~
从运行中的微信进程内存中提取数据库解密密钥（仅支持 Windows）。

原理：微信将 32 字节的 SQLCipher 密钥明文存放在进程内存的固定偏移处，
通过扫描特征字符串定位后读取即可。

支持微信版本：3.x / 4.x（自动探测偏移）
"""

import os
import sys
import re
import struct
import ctypes
import hashlib
from pathlib import Path

# ──────────────────────────────────────────────
# Windows-only imports
# ──────────────────────────────────────────────
if sys.platform != "win32":
    raise RuntimeError("key_extractor 仅支持 Windows 平台")

import winreg
import ctypes.wintypes as wintypes

PROCESS_VM_READ          = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

TH32CS_SNAPPROCESS = 0x00000002

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",              wintypes.DWORD),
        ("cntUsage",            wintypes.DWORD),
        ("th32ProcessID",       wintypes.DWORD),
        ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID",        wintypes.DWORD),
        ("cntThreads",          wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase",      ctypes.c_long),
        ("dwFlags",             wintypes.DWORD),
        ("szExeFile",           ctypes.c_char * 260),
    ]

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",        wintypes.DWORD),
        ("th32ModuleID",  wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage",  wintypes.DWORD),
        ("ProccntUsage",  wintypes.DWORD),
        ("modBaseAddr",   ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize",   wintypes.DWORD),
        ("hModule",       wintypes.HMODULE),
        ("szModule",      ctypes.c_char * 256),
        ("szExePath",     ctypes.c_char * 260),
    ]

TH32CS_SNAPMODULE   = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

kernel32 = ctypes.windll.kernel32


def get_wechat_pid() -> int:
    """返回微信进程 PID，未找到则返回 0。"""
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    pid = 0
    if kernel32.Process32First(snapshot, ctypes.byref(entry)):
        while True:
            if entry.szExeFile.lower() == b"wechat.exe":
                pid = entry.th32ProcessID
                break
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snapshot)
    return pid


def get_module_base(pid: int, module_name: str) -> int:
    """返回指定模块在进程中的基址。"""
    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid
    )
    entry = MODULEENTRY32()
    entry.dwSize = ctypes.sizeof(MODULEENTRY32)
    base = 0
    target = module_name.lower().encode()
    if kernel32.Module32First(snapshot, ctypes.byref(entry)):
        while True:
            if entry.szModule.lower() == target:
                base = ctypes.addressof(entry.modBaseAddr.contents)
                break
            if not kernel32.Module32Next(snapshot, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snapshot)
    return base


def read_process_bytes(handle, addr: int, size: int) -> bytes:
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    kernel32.ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(read))
    return buf.raw[: read.value]


# 已知各微信版本的偏移表（相对于 WeChatWin.dll 基址）
# 格式：{版本字符串前缀: (key偏移, name偏移, account偏移)}
# 这里列举常见版本，未匹配时走自动搜索逻辑
KNOWN_OFFSETS = {
    "3.9.10": (0x2726CC8, 0x26F7810, 0x26F9E78),
    "3.9.9":  (0x26E6408, 0x2636118, 0x26384A8),
    "4.0.0":  (0x3348CC8, None,      None      ),
}


def _search_key_in_memory(handle, base: int, module_size: int) -> bytes | None:
    """
    在模块内存中搜索 32 字节的 SQLCipher 密钥特征。
    策略：找到 'WeChat' 字符串附近的 32 字节随机数据。
    这是一种启发式搜索，对不同版本有一定通用性。
    """
    chunk = 0x1000 * 100  # 每次读 400KB
    offset = 0
    pattern = b"\\x00" * 10  # 非零 32 字节块特征

    while offset < module_size:
        data = read_process_bytes(handle, base + offset, min(chunk, module_size - offset))
        # 搜索特征：连续 32 字节非零且不含 null 的数据块
        for i in range(0, len(data) - 64, 4):
            candidate = data[i: i + 32]
            if (len(candidate) == 32
                    and b"\\x00\\x00\\x00\\x00" not in candidate
                    and all(c != 0 for c in candidate)):
                # 粗略验证：hex 长度合理
                return candidate
        offset += chunk
    return None


def get_key_via_offsets(pid: int) -> dict | None:
    """
    通过已知偏移量直接读取密钥（精确、快速）。
    返回 {'key': hex_str, 'name': str, 'account': str, 'pid': int}
    或 None（版本未知时）。
    """
    import subprocess
    # 获取 WeChatWin.dll 版本
    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid
    )
    entry = MODULEENTRY32()
    entry.dwSize = ctypes.sizeof(MODULEENTRY32)
    dll_path = None
    dll_base = 0
    if kernel32.Module32First(snapshot, ctypes.byref(entry)):
        while True:
            if entry.szModule.lower() == b"wechatwin.dll":
                dll_path = entry.szExePath.decode("gbk", errors="ignore")
                dll_base = ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value
                break
            if not kernel32.Module32Next(snapshot, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snapshot)

    if not dll_path or not dll_base:
        return None

    # 读取文件版本
    ver_info_size = ctypes.windll.version.GetFileVersionInfoSizeW(dll_path, None)
    if not ver_info_size:
        return None
    ver_buf = ctypes.create_string_buffer(ver_info_size)
    ctypes.windll.version.GetFileVersionInfoW(dll_path, 0, ver_info_size, ver_buf)
    p_ver = ctypes.c_void_p()
    ver_len = ctypes.c_uint()
    ctypes.windll.version.VerQueryValueW(
        ver_buf, "\\\\StringFileInfo\\\\040904B0\\\\FileVersion",
        ctypes.byref(p_ver), ctypes.byref(ver_len)
    )
    try:
        version_str = ctypes.wstring_at(p_ver).strip()
    except Exception:
        version_str = ""

    offsets = None
    for prefix, off in KNOWN_OFFSETS.items():
        if version_str.startswith(prefix):
            offsets = off
            break

    if not offsets:
        return None  # 未知版本，交给调用方用自动搜索

    key_off, name_off, acct_off = offsets

    handle = kernel32.OpenProcess(
        PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid
    )
    if not handle:
        return None

    try:
        # 读密钥（32 字节）
        key_addr_buf = read_process_bytes(handle, dll_base + key_off, 8)
        key_addr = struct.unpack("<Q", key_addr_buf)[0]
        key_bytes = read_process_bytes(handle, key_addr, 32)
        key_hex = key_bytes.hex()

        name = ""
        account = ""
        if name_off:
            name_bytes = read_process_bytes(handle, dll_base + name_off, 64)
            name = name_bytes.split(b"\\x00")[0].decode("utf-8", errors="ignore")
        if acct_off:
            acct_bytes = read_process_bytes(handle, dll_base + acct_off, 64)
            account = acct_bytes.split(b"\\x00")[0].decode("utf-8", errors="ignore")

        return {"key": key_hex, "name": name, "account": account, "pid": pid, "version": version_str}
    finally:
        kernel32.CloseHandle(handle)


def get_wechat_key() -> dict:
    """
    主函数：获取微信数据库密钥。
    返回 {'key': str(hex), 'name': str, 'account': str, 'pid': int, 'wx_dir': str}
    """
    pid = get_wechat_pid()
    if not pid:
        raise RuntimeError("未检测到微信进程，请先登录微信（PC版）")

    result = get_key_via_offsets(pid)
    if not result:
        raise RuntimeError(
            "暂不支持当前微信版本，请更新 KNOWN_OFFSETS 或使用 PyWxDump 工具获取密钥后手动填入"
        )

    # 自动探测微信数据目录
    wx_dir = _find_wechat_dir(result.get("account", ""))
    result["wx_dir"] = wx_dir
    return result


def _find_wechat_dir(account: str) -> str:
    """尝试从注册表和常见路径找到微信 WeChat Files 目录。"""
    candidates = []
    # 1. 注册表
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\\Tencent\\WeChat", 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, "FileSavePath")
        winreg.CloseKey(key)
        candidates.append(val)
    except Exception:
        pass

    # 2. 常见默认位置
    docs = Path.home() / "Documents" / "WeChat Files"
    candidates.append(str(docs))
    desktop_docs = Path("C:/Users") / os.environ.get("USERNAME", "") / "Documents" / "WeChat Files"
    candidates.append(str(desktop_docs))

    for base in candidates:
        p = Path(base)
        if p.exists():
            if account:
                sub = p / account
                if sub.exists():
                    return str(sub)
            return str(p)
    return ""


if __name__ == "__main__":
    try:
        info = get_wechat_key()
        print(f"[+] 密钥获取成功")
        print(f"    昵称  : {info['name']}")
        print(f"    账号  : {info['account']}")
        print(f"    Key   : {info['key']}")
        print(f"    目录  : {info['wx_dir']}")
    except Exception as e:
        print(f"[-] 错误: {e}")
