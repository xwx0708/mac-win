# mac-win 互联服务

Windows（xwx）和 Mac（wenxuanmacbook-pro）各运行一份 `macwin_link.py serve`。两边经 Tailscale 保持**一条长连接**，里面分出两个通道：

| 通道 | 做什么 |
|---|---|
| 文件通道 | 在对方电脑的开放范围内（见下）列目录、读写文件（1 MiB 分块，大文件不会堵住通知）、建目录、复制、移动、删除。删除不真删：共享目录里的移进共享目录下的 `.trash`，其他位置的移进系统回收站（Windows 回收站 / Mac 废纸篓） |
| 通知通道 | 每秒扫描本机共享目录（递归），以及对方订阅了的目录（只看一层，`watch` 操作），有新增、修改、删除就推给对方。对方收到后要回执，没回执的变化留在待发队列里，重连后补发 |
| 智能体通道 | 让对方电脑上的终端版 Claude Code 或 Codex 在指定目录（默认对方共享目录，须在对方可写范围内）执行一个任务，返回输出。Claude Code 用 `acceptEdits`，Codex 用 `workspace-write` 沙箱。单个任务最长 600 秒，可在 `config.json` 里用 `agent_timeout_seconds` 改；设 `"agents_enabled": false` 可关掉本机的智能体通道 |

## 开放范围（`scope.py`）

人工（命令行、App）和智能体（MCP）用同一套规则，按顺序判断：

| | Windows | Mac |
|---|---|---|
| **禁区**：看不到、读不了、写不了，列目录时连名字都不显示 | `E:/隐私数据`、`~/.ssh`、`~/.claude/.credentials.json`、`~/.codex/auth.json`、Windows 凭据目录（`Microsoft/Credentials`、`Microsoft/Protect`）、`C:/Windows/System32/config` | `~/Library/Keychains`、`/Library/Keychains`、`~/.ssh`、`~/.codex/auth.json`、`~/.claude/.credentials.json`、`/private/var/db`、`/System/Volumes` |
| **可见**（能读） | C、D、E 盘 | 整个磁盘 `/` |
| **可写** | E 盘、D 盘、用户主目录 `C:/Users/29412` | 用户主目录、`/Volumes`、`/tmp` |

其余可见位置只读（如 `C:/Windows`、`C:/Program Files`、`/System`、`/Applications`）。另外不能删除或移动整个盘、用户主目录、共享目录本身。

判断前会先解析符号链接和联接点，并忽略大小写，所以换大小写、走 `..`、经联接点都绕不进禁区。规则可以在 `config.json` 里按设备 ID 覆盖：`"scope": {"<设备ID>": {"roots": [...], "writable": [...], "deny": [...]}}`。

路径写法：绝对路径（`E:/工作区/x.txt`、`/Users/wx/x.txt`），或相对本机共享目录的路径（老写法，照旧可用）。共享目录里的文件返回相对路径，其他位置返回绝对路径。

`list` 的每一项多了 `hidden`（Windows 的隐藏/系统属性、Mac 的点开头或隐藏标记），由界面决定显不显示；目录本身带 `writable`。新增两个操作：

- `roots`：本机开放的盘（含容量、剩余、是否可写）、常用位置（桌面、文档、下载等的实际路径）、禁区和可写范围。
- `watch`：`{"paths": [...], "ttl": 秒}`，订阅这些目录的变化（不递归，最多 32 个，默认 120 秒内不续就失效）。每次调用传完整列表，替换上一次的。订阅时立刻建立基准，之后的新增、修改、删除都会经通知通道推给对方。

断线后会自动重连：每 10 秒互发心跳，35 秒收不到任何数据就断开重连；重连间隔从 1 秒开始翻倍，最长 30 秒。只用 Python 标准库。

| 机器 | 共享目录 | 程序位置 | 自启方式 |
|---|---|---|---|
| Windows | `E:\收件箱\Mac互传` | 本目录 | 计划任务 `mac-win-link`（登录时启动，用 pythonw 后台运行） |
| Mac | `~/Windows互传` | `~/macwin-link/` | LaunchAgent `com.macwin.link` |

## 认证

不自己造密钥，全部交给 Tailscale：

1. 长连接只监听本机的 Tailscale IPv4 地址。所有流量都走 WireGuard，发送方由各设备的密钥保证，伪造不了。
2. 有连接进来时，先用 `tailscale whois` 查出对方的设备 ID（StableID）。必须在 `config.json` 的 `allowed_devices` 白名单里，并且和本机属于同一个 Tailscale 账号，否则直接断开。
3. 双方再互发 hello，对方自报的设备 ID 必须和 Tailscale 查到的一致，协议版本也要一致。
4. 主动连接的一方在连之前也会用 whois 确认对方的 IP 此刻确实属于目标设备。

由设备 ID 较小的一方（目前是 Mac）主动连接。两边都在监听，所以先启动哪边都行。

## 常用命令

所有命令都在本机运行，由本机后台服务转发给对方。路径都是相对**对方**共享目录的路径。

```
python macwin_link.py status                  连接状态、延迟、累计连接次数
python macwin_link.py ls [对方路径]            列对方共享目录
python macwin_link.py put <本地文件> [对方路径]  上传；对方路径以 / 结尾表示放进该目录
python macwin_link.py get <对方路径> [本地路径]  下载
python macwin_link.py mkdir <对方路径>
python macwin_link.py mv <对方路径> <对方新路径>
python macwin_link.py rm <对方路径>            移进对方 .trash
python macwin_link.py watch                   持续显示对方共享目录的变化
python macwin_link.py ask claude "<任务>" [对方子目录]   让对方的 Claude Code 执行任务
python macwin_link.py ask codex "<任务>" [对方子目录]    让对方的 Codex 执行任务
python macwin_link.py whoami                  本机的 Tailscale 设备 ID
```

Mac 上先运行 `cd ~/macwin-link`，并把 `python` 换成 `python3`。

## 给其他程序用的本机接口

后台服务在 `127.0.0.1:47111` 上开了 HTTP 控制接口，只有本机能访问。命令行用的就是它：

| 请求 | 作用 |
|---|---|
| `GET /status` | 连接状态（JSON） |
| `GET /events?since=<序号>&wait=<秒>&epoch=<上次返回的 epoch>` | 长轮询对方推来的变化。`since=-1` 表示从现在开始 |
| `POST /file`，头 `X-Op: <操作>`、`X-Args: <JSON>`，请求体是要写入的数据 | 在对方共享目录上执行 `list` / `stat` / `read` / `write` / `mkdir` / `move` / `delete`。结果放在响应头 `X-Result`（JSON，中文用 \u 转义），读到的数据放在响应体 |
| `POST /agent`，请求体 JSON `{"agent": "claude"或"codex", "prompt": "...", "cwd": "对方子目录", "timeout": 秒}` | 让对方的智能体执行任务，返回 `{ok, exit_code, seconds, output, error}` |

本机接口还支持（MCP 服务用的就是这些）：

| 请求 | 作用 |
|---|---|
| 请求头 `X-Source: {"kind":"agent","agent":"claude","session":"..."}` | 标明是哪个智能体、哪个会话发起的。写操作和任务委托会记进 `state/activity.jsonl`，不带此头视为人工操作 |
| `POST /file` 加头 `X-Target: self` | 在**本机**共享目录上执行文件操作（默认 `peer` 是对方）。另有 `copy` 操作；`write` 支持 `if_version` 冲突检测；`stat`/`list`/`read` 返回 `version` |
| `POST /task/start`，体 `{"agent","prompt","cwd","timeout","wait"}` | 把任务派给对方智能体，后台执行。带 `X-Delegated: 1` 的请求会被拒绝 |
| `GET /task?id=<task_id>` / `POST /task/cancel`（体 `{"task_id"}`） | 查询 / 取消任务 |
| `GET /activity?n=100` | 最近的操作记录 |

## MCP 服务（给 Claude Code 和 Codex 用）

`mcp_server.py` 是一层包装：把 MCP 工具调用转发给上面的本机接口。stdio 方式运行，只用标准库，两台电脑同一份。

| 类别 | 工具 |
|---|---|
| 文件（都带 `device: mac|windows`，路径可以是绝对路径） | `list_dir`、`stat`、`read_file`、`write_file`（`if_version` 冲突检测）、`move`、`copy`（`dest_device` 不同即跨设备，只支持单个文件）、`mkdir`、`delete`（只进回收区 / 系统回收站） |
| 状态 | `list_roots`（某台电脑开放的盘和常用位置）、`peer_status` |
| 智能体 | `delegate_task`（`wait` 等结果或立即返回 `task_id`）、`get_task`、`cancel_task` |

任务状态：运行中、完成、失败、超时、已取消、**未送达**（对方离线，没送出去）、**不确定**（送出后失去联系）。

防循环委托：被委托执行任务的智能体启动时带环境变量 `MACWIN_DELEGATED=1`，它加载的 MCP 服务就不提供 `delegate_task`；核心服务也会拒绝带 `X-Delegated: 1` 的委托请求，对方核心服务再查一次。

注册方法（两台电脑都已注册，名字都是 `macwin`，用户级，所有项目可用）：

```
# Windows
claude mcp add -s user macwin -- "C:\Users\29412\AppData\Local\Programs\Python\Python312\python.exe" "E:\工作区\claude工作区\mac-win\link\mcp_server.py" --agent claude
codex mcp add macwin -- "C:\Users\29412\AppData\Local\Programs\Python\Python312\python.exe" "E:\工作区\claude工作区\mac-win\link\mcp_server.py" --agent codex

# Mac
claude mcp add -s user macwin -- /opt/homebrew/bin/python3 ~/macwin-link/mcp_server.py --agent claude
codex mcp add macwin -- /opt/homebrew/bin/python3 ~/macwin-link/mcp_server.py --agent codex
```

`--agent` 决定操作记录里的"智能体"。会话 ID 取 `CLAUDE_CODE_SESSION_ID`；拿不到时（例如 Codex）用 MCP 进程自己生成的 ID，一个会话对应一个 MCP 进程。

配套技能 `macwin-peer`（正文在 `E:\工具\ai-skills\macwin-peer\SKILL.md`，Mac 上直接复制在 `~/.claude/skills` 和 `~/.codex/skills`）：规定操作共享文件优先用这些工具、改文件带版本号、把对方智能体当子 agent 用的方法。

## 文件

| 文件 | 内容 |
|---|---|
| `macwin_link.py` | 入口：后台服务、本机控制接口、命令行 |
| `conn.py` | 长连接：分帧、通道复用、心跳、握手、自动重连、通知的待发队列 |
| `files.py` | 文件操作、系统回收站、目录订阅、轮询检测变化 |
| `scope.py` | 开放范围：禁区、可见、可写，以及盘和常用位置列表 |
| `tsauth.py` | Tailscale 身份：本机身份、whois、白名单校验 |
| `agents.py` | 智能体通道：调用本机终端版 Claude Code / Codex |
| `tasks.py` | 后台任务：执行方（启动、查询、取消）和委托方（记录派出的任务，`state/tasks.json`） |
| `activity.py` | 操作记录（`state/activity.jsonl`），标明人工还是哪个智能体的哪个会话 |
| `mcp_server.py` | MCP 服务 |
| `config.json` | 端口、白名单、两边的共享目录。两台电脑用同一份 |
| `install_windows.ps1` / `install_mac.sh` | 注册开机自启 |
| `logs/link.log` | 运行日志（1MB 轮换） |
| `state/status.json` | 最近一次的连接状态 |

帧格式：4 字节大端头长度 + JSON 头 + 可选二进制负载（长度写在头的 `size` 里）。头里的 `ch` 字段区分 `ctl`（握手、心跳）、`file`、`notify` 三个通道；请求带 `id`，回复带 `re`。

## 部署与更新

- 改完代码后同步到 Mac（走互联服务，不用 SSH）：对每个改过的文件运行 `python macwin_link.py put <文件> /Users/wx/macwin-link/<文件>`
- 重启 Windows 服务：先结束 `pythonw.exe` 里命令行含 `macwin_link.py serve` 的进程，等计划任务 `mac-win-link` 不再是 Running，再 `Start-ScheduledTask mac-win-link`。注意按命令行筛进程时要限定 `pythonw.exe`，否则会连发命令的 PowerShell 自己一起结束
- 重启 Mac 服务：让 Mac 的智能体运行 `nohup sh ~/macwin-link/restart-later.sh >/dev/null 2>&1 &`（8 秒后 `launchctl kickstart -k`；智能体自己就跑在这个服务下，所以要延后放到后台，先把回复送出去）
- 用 `ask` 给对方智能体发任务时，任务文字里不要带英文双引号：Windows 传命令行参数会把它吃掉，命令就变了。需要复杂命令时先 `put` 一个脚本过去，让对方运行脚本
- 卸载：Windows 运行 `Unregister-ScheduledTask -TaskName mac-win-link -Confirm:$false`；Mac 运行 `launchctl bootout gui/$(id -u)/com.macwin.link` 并删掉 `~/Library/LaunchAgents/com.macwin.link.plist`

## 已验证（2026-11-16）

- 25MB 随机文件上传约 1.8 秒，下载约 1.7 秒，SHA-256 一致；中文文件名和目录名正常。
- 移动、删除到 `.trash`、建目录正常；`..`、盘符、绝对路径都会被拒绝。
- 变化通知两个方向都能送达。
- 把 Mac 服务冻结 45 秒来模拟静默断线：Windows 在 40 秒左右判定心跳超时；Mac 恢复后 1 秒内重连成功，断线期间 Windows 上新建的文件随后补发给了 Mac。
- 任意一边重启服务，另一边都会自动重连。
- 从 Windows 让 Mac 的 Claude Code（2.1.325）和 Codex（0.169.0）各在共享目录里建一个文件，分别用了 5.5 秒和 9.0 秒，再用文件通道取回，内容正确。
- MCP：Mac 上的 Codex 通过 MCP 工具列出了 Windows 的共享目录、把 hello.txt 从 Mac 跨设备移到 Windows（Mac 源文件进了回收区）、委托 Windows 上的 Claude Code 回答操作系统并拿回结果"完成"。两边的操作记录都标着 codex 和同一个会话 ID。
- 用户在 Mac 上用 Claude Code 交互式调用 MCP，委托 Windows 上的 Claude Code 完成测试任务，结果正常（17:39）。操作记录里带着 Mac Claude Code 的真实会话 ID，说明 Claude Code 会把会话 ID 传给 MCP 进程。
- MCP 的版本冲突、只新建、复制、删除、取消任务、对方离线（"对方离线""未送达"）、被委托者不能再委托，都从 Windows 测过。

- 开放范围（2026-11-16 17:50 后）：
  - Mac 的 `list_roots` 列出 Macintosh HD 和桌面、文稿、下载等实际路径；Windows 的列出 C、D、E 三个盘（C 只读）和重定向后的桌面 `E:/工作区/桌面` 等。
  - 后台服务（LaunchAgent 下的 Python）能读 Mac 的桌面、文稿、下载，没有被系统拦。
  - 把 `E:/收件箱/待删除/...` 下的文件跨设备复制到 Mac 的 `/tmp`，内容一致。在 Mac 盘外重命名、删除，进了废纸篓；Windows 盘外删除进了回收站。
  - 禁区（`E:/隐私数据`，含小写 `e:/` 写法、`~/.ssh`、钥匙串）全部拒绝，`E:/` 的列表里看不到隐私数据；只读区（`C:/Windows`、`/System`、`/Applications`）写入被拒。从 Mac 发起访问 Windows 的这些位置，结果相同。
  - 订阅 Mac 的 `/tmp/macwin测试` 后，在 Mac 本地新建、删除文件，Windows 都收到了通知；不能订阅禁区。
  - 委托 Mac 的 Codex 在 `/tmp/macwin测试` 里工作：它执行了 `pwd`，并通过 MCP 列出了 Windows 的 `E:/工作区/桌面/111`。把工作目录设成只读区 `/System` 时，对方拒绝执行。

- "不确定"（2026-11-16 23:11–23:23）：从 Windows 给 Mac 的 Claude 派一个要跑 40–50 秒的任务，运行中把 Windows 的互联服务停 25 秒再启动。Mac 还没重连（重拨按退避间隔）时查询，任务显示"不确定：对方离线，无法确认最新进度（最后已知：运行中）"；约 5 秒后重连，再查变回"运行中"，随后"完成"并拿到输出。共测 3 次，结果一致（第一次时"最后已知"显示成"未知"，已修正）。

Codex 默认每次调用 MCP 工具都要人工批准，非交互（`codex exec`，包括被委托执行任务时）会直接被拒。两台电脑的 `~/.codex/config.toml` 都已在 `[mcp_servers.macwin]` 下加了 `default_tools_approval_mode = "approve"`（2026-11-16 用户同意），只对 macwin 这一个服务免批准。

## 为什么智能体要走互联服务，而不直接 SSH

在 Mac 上，Claude Code 的登录凭据存在钥匙串里，只有图形登录会话里的进程才能读到。从 SSH 直接运行 `claude` 会报"Not logged in"。互联服务是 LaunchAgent，本来就跑在图形会话里，所以能正常调用。Codex 的凭据是文件，SSH 也能用。

## 注意

- **Mac 睡眠就会断**。这是 Tailscale 层面的离线，重连要等 Mac 醒来。需要一直连着的话，在「系统设置 → 电池」里关掉自动睡眠。
- 变化检测靠每秒轮询，共享目录里文件特别多（几万个以上）时会占 CPU。到时再换成系统的文件监听。
- 通知至少送达一次：回执丢失时会重发，所以对方偶尔会收到重复通知。
- 命令行 `put` 不带版本号，一边在 `put`、另一边同时在本地改同一个文件时，后写的覆盖先写的；MCP 的 `write_file` 带 `if_version` 可以避免。
- 订阅目录只看一层、靠每秒轮询；一个目录超过 5000 项只比较前 5000 项。
- Mac 上如果哪天读桌面、文稿等报"系统不允许读取"，是 macOS 隐私保护拦了后台的 Python，需要在「系统设置 → 隐私与安全性 → 完全磁盘访问权限」里加上 Homebrew 的 Python。
- launchd 下没有 `TERM` 环境变量，Tailscale.app 自带的命令行没有它时会去启动图形界面。`tsauth.py` 调用时已补上 `TERM`，不要删。
- 两边 Python 版本不同（Windows 3.12，Mac 3.15），代码不要用 3.12 以后才有的语法。
