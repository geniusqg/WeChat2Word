# WeChat2Word

> 将微信 PC 版聊天记录导出为纯文本文件（.txt）

---

## 功能特点

- 🔓 **自动密钥获取** — 从运行中的微信进程读取解密密钥，无需手动配置
- 📝 **纯文本导出** — 简洁的 txt 格式，任何设备都能打开，支持搜索/编辑
- 🖼️ **多消息类型支持** — 文本、图片、语音、视频、链接、表情、系统通知
- 💬 **群聊支持** — 自动解析群消息发送者
- 🔍 **灵活筛选** — 支持按时间范围、消息数量筛选导出
- 🔧 **双模式** — 支持自动解密模式 + 已解密 SQLite 文件模式
- 🪶 **零额外依赖** — 只需 pysqlcipher3，无需安装 Office/WPS

---

## 环境要求

| 项目 | 要求 |
|------|------|
| 系统 | Windows 10/11（自动密钥模式），macOS/Linux（需手动提供密钥） |
| Python | >= 3.8 |
| 微信 | PC 版微信 3.x / 4.x（需保持登录状态） |

---

## 安装

```bash
# 克隆项目
git clone https://github.com/yourname/WeChat2Word.git
cd WeChat2Word

# 创建虚拟环境（推荐）
python -m venv .venv
.\.venv\Scripts\activate    # Windows
source .venv/bin/activate   # macOS/Linux

# 安装依赖
pip install -r requirements.txt
```

### pysqlcipher3 安装注意事项

`pysqlcipher3` 需要 C 编译环境：

**Windows（推荐）：**
```bash
pip install pysqlcipher3
```

**Windows MSVC Build Tools：**
- 下载 [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio)
- 安装时勾选 "C++ 生成工具"
- 重启终端后再安装

**macOS：**
```bash
brew install sqlcipher
pip install pysqlcipher3
```

**Linux：**
```bash
sudo apt install libsqlcipher-dev   # Debian/Ubuntu
pip install pysqlcipher3
```

---

## 快速开始

### 方式一：交互式导出（推荐）

```bash
python wechat2word.py
```

1. 程序自动从微信进程获取密钥
2. 显示所有会话列表
3. 输入序号选择要导出的聊天
4. 自动生成 txt 文件到桌面

### 方式二：命令行参数

```bash
# 列出所有会话
python wechat2word.py --list

# 导出指定会话（按用户名）
python wechat2word.py --session filehelper

# 导出最近 30 天的消息
python wechat2word.py --session 群聊名 --days 30

# 限制导出条数
python wechat2word.py --session 文件传输助手 --limit 1000

# 指定输出路径
python wechat2word.py --session xxx --output "D:/备份/聊天记录.txt"
```

### 方式三：使用已解密数据库

如果没有安装 pysqlcipher3，或想在非 Windows 平台使用，可手动解密数据库：

1. 使用 [DB Browser for SQLite](https://sqlitebrowser.org/) 或 [PyWxDump](https://github.com/xaoyaoo/PyWxDump) 解密数据库
2. 将 `MSG.db` 和 `MicroMsg.db` 导出为普通 SQLite 文件
3. 使用以下命令：

```bash
python wechat2word.py \
  --msg-db ./decrypted_MSG.db \
  --micro-db ./decrypted_MicroMsg.db \
  --session 文件传输助手 \
  --output ./聊天记录.txt
```

---

## 工作原理

```
┌─────────────────┐
│  微信 PC 版      │  数据库路径：
│  (运行中)        │  WeChat Files/<微信号>/Msg/
│                 │
│  ┌───────────┐  │  ┌────────────┐  ┌────────────┐
│  │ WeChatWin │  │  │  MSG.db   │  │MicroMsg.db │
│  │   .dll    │──┼─▶│ (加密)    │  │  (加密)    │
│  └───────────┘  │  └────────────┘  └────────────┘
└─────────────────┘           │
                               ▼
              ┌────────────────────────┐
              │    key_extractor.py    │  读取进程内存
              │  从 WeChatWin.dll      │  获取 32 字节
              │  固定偏移处提取密钥     │  SQLCipher 密钥
              └────────┬───────────────┘
                       │
                       ▼
              ┌────────────────────────┐
              │     db_parser.py        │
              │  pysqlcipher3 解密      │
              │  解析消息表、联系人表    │
              └────────┬───────────────┘
                       │
                       ▼
              ┌────────────────────────┐
              │     exporter.py         │
              │  纯文本格式生成          │
              │  日期分隔 + 消息时间轴    │
              └────────┬───────────────┘
                       │
                       ▼
              ┌────────────────────────┐
              │    输出文件              │
              │  聊天记录_张三_20260401.txt
              └────────────────────────┘
```

---

## 数据库表结构

### MSG 表（消息）

| 字段 | 类型 | 说明 |
|------|------|------|
| MsgSvrID | INTEGER | 消息服务器 ID |
| Type | INTEGER | 消息类型（见下表） |
| StrContent | TEXT | 文本内容 |
| StrTalker | TEXT | 对话者用户名 |
| CreateTime | INTEGER | Unix 时间戳（秒） |
| IsSender | INTEGER | 是否为自己发送（1=我，0=对方） |
| BytesExtra | BLOB | 附加信息（图片/语音路径等） |

### 消息类型（Type 字段）

| Type | 含义 | 导出血泡内容 |
|------|------|-------------|
| 1 | 文本消息 | 文本内容 |
| 3 | 图片 | `[图片]` |
| 34 | 语音 | `[语音消息]` |
| 43 | 视频 | `[视频]` |
| 47 | 表情 | `[表情]` |
| 49 | 链接/文件/小程序 | `[链接] 标题` |
| 10000 | 系统通知 | `[系统] 通知内容` |
| 10002 | 撤回消息 | `[消息已撤回]` |

---

## 项目结构

```
WeChat2Word/
├── wechat2word.py      # CLI 主入口
├── key_extractor.py    # 从微信进程获取密钥（仅 Windows）
├── db_parser.py        # 数据库解密与解析
├── exporter.py         # txt 文件生成
├── requirements.txt    # Python 依赖
└── README.md           # 本文件
```

---

## 构建 EXE（打包成可执行文件）

### 方式一：GitHub Actions 自动构建（推荐，无需本地配置）

本项目已配置 GitHub Actions，在云端 Windows 机器上自动构建 EXE。

1. 将项目上传到 GitHub 仓库
2. 在 GitHub 仓库页面点击 **Actions** → **Build Windows EXE** → **Run workflow**
3. 构建完成后在 **Artifacts** 中下载 `WeChat2Word-Windows` 或 `WeChat2Word-EXE`

> 无需本地安装任何工具，push 代码后自动出包。

### 方式二：本地 Windows 构建

1. 下载/克隆项目到 Windows 电脑
2. 安装 **Python 3.8+**（[python.org](https://python.org)）
3. 安装 **Visual Studio Build Tools**（勾选"C++ 生成工具"）——用于编译 pysqlcipher3
4. 双击运行 `build.bat`，自动完成构建

```batch
# 或手动命令：
pip install pysqlcipher3 pyinstaller
pyinstaller wechat2word.spec --clean --noconfirm
```

构建产物位于 `dist\WeChat2Word_Portable\`，包含：
- `WeChat2Word.exe` — 交互式主程序
- `WeChat2Word_Quick.exe` — 快速导出工具
- `README.md`、`start.bat` 等配套文件

> ⚠️ **杀毒软件误报**：EXE 会被部分杀毒软件识别为"风险程序"，这是因为 pysqlcipher3 调用了系统底层加密 API。将 EXE 添加到杀毒软件白名单即可正常使用。

---

## 注意事项 ⚠️

1. **仅用于个人备份** — 本工具仅供个人备份自己的微信聊天记录，请勿用于任何侵犯隐私的用途
2. **微信版本兼容性** — 密钥偏移表基于常见微信版本，新版微信可能需要重新探测偏移量
3. **密钥版本差异** — 不同微信版本的密钥偏移不同，程序会尝试自动匹配；如遇"不支持版本"提示，请手动获取密钥
4. **数据安全** — 解密后的数据库为明文，请妥善保管，不要上传到网络
5. **iOS/Android** — 本工具仅支持 PC 版微信；移动端数据请参考 WeChatMsg 项目

---

## 常见问题

**Q: 提示"未检测到微信进程"？**
> 确保微信 PC 版已登录并保持运行状态。

**Q: 提示"不支持当前微信版本"？**
> 尝试使用 `PyWxDump` 工具获取密钥，然后手动传入：
> ```bash
> python wechat2word.py --key <密钥hex> --wx-dir <微信数据目录> --session xxx
> ```

**Q: pysqlcipher3 安装失败？**
> Windows 上需要 Visual C++ Build Tools；Linux 需要 `libsqlcipher-dev`。也可使用已解密数据库模式绕过。

**Q: 导出的 txt 是乱码？**
> 确认微信昵称/备注中不含特殊符号，或用记事本/VS Code 重新打开（确保 UTF-8 编码）。

---

## 灵感来源

- [WeChatMsg](https://github.com/LC044/WeChatMsg) — 微信聊天记录导出 GUI 工具
- [PyWxDump](https://github.com/xaoyaoo/PyWxDump) — PC 微信数据库解密利器
- [sqlcipher](https://www.zetetic.net/sqlcipher/) — SQLite 数据库加密库

---

## License

MIT License — 仅供个人学习与备份使用
