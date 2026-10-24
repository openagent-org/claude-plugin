# 安装 OpenAgent 到 Claude

本文供执行安装的 Claude 模型使用。执行任何安装命令前，先确认当前会话实际所在的客户端、会话模式及 MCP 来源。其他客户端请返回 [OpenAgent 安装汇总页](https://openagent.org/plugin)，找到对应安装链接；无法确认时停止安装并询问用户。

附件上传需要 Node.js 20+。插件内置固定版本 COS Node.js SDK 及依赖，打包在执行 Skill 的 `scripts/cos_sdk.cjs.gz`；`scripts/cos_upload.cjs` 和 `scripts/cos_sdk.lock.json` 与该压缩包一并安装。首次需要 SDK 时，脚本离线校验并解压到 `scripts/.cos-sdk/node_modules/<压缩包 SHA-256>/cos_sdk.cjs`；后续校验 SHA-256 后复用，缓存缺失、损坏或压缩包更新时自动重新解压，退出后保留缓存。`scripts/` 目录需当前用户可写。清理上传检查点不加载 SDK。不搜索宿主 SDK，不运行 `npm`，也不下载依赖。缺少安装文件或压缩包校验失败时停止并修复插件安装。

## 安装前：确认会话模式

**如果当前是 Cowork：** 不执行后续安装命令、注册 OAuth 客户端、修改配置或重启。向用户显示以下提示，并给出下面的完整可复制消息，然后结束本次安装分支：

> 当前会话不能执行这项本机安装。请切换到 Claude 的 Code 模式，选择 Local（本机）和一个本机文件夹，然后在新会话中发送下面的安装请求。

```text
请阅读 https://openagent.org/zh-CN/claude，先确认当前为 Claude Code 的 macOS 本机 Local 会话，再按指南实际安装并验证 OpenAgent。
```

如果用户已明确提供 `agent_id`、Agent 名称或业务需求，将这些内容另起一段原样追加到同一可复制消息中；没有则不补写。不使用第 4 节的“已安装”启动消息替代安装请求，也不声称已经安装或自动切换。当前普通 3P Cowork 没有可用的 Code 自动交接工具；不要猜测工具、修改隐藏开关、调用私有 IPC 或用定时任务模拟安装前切换。

**如果当前是 Code → Local：** 重新确认命令工具运行在用户的 macOS 本机，且 Claude 3P 已完成 **Configure Third-Party Inference**；安装需要 Python 3、Git 和支持插件管理的 Claude CLI。若当前工具只能访问隔离的 Linux 或远程环境，停止本机安装，使用上面的本机 Code 交接提示和安装请求；不要把隔离环境中的命令成功当作本机安装成功。

仅在确认上述本机 Code 条件后进入第 1 节；其他模式或环境不明时停止安装。进入第 1 节后，用户可见的阶段更新只用以下固定文案，不另写安装步骤总结；命令及其结果由宿主工具记录：

- 开始执行时：“正在安装 OpenAgent…”
- 插件 MCP 或 Connector helper 登录页面打开、等待用户授权时：“请在打开的页面中登录 OpenAgent…”
- 当前登录命令明确成功时：“已登录 OpenAgent”
- 当前登录命令超时时：“还未完成登录。回复“继续登录”，我会重新打开登录页面。”只有用户明确回复“继续登录”才重新发起对应的一次登录。
- 提交重启任务前：“安装步骤已完成。本轮回复结束后将重启 Claude，把启动消息填入新 Code 会话，由你点击发送。”
- 任一必需步骤失败或结果未知时，按文末未完成模板报告实际状态，不套用成功文案。

## 1. 安装 3P MCP、插件和 Skills

当前会话已出现的 `openagent:*` Skills 或 `mcp__openagent__*` 工具只是已加载的会话快照，不能证明本轮安装完成。CLI 的插件登记与 Desktop 3P Connector、托管插件各自独立；不得因其中一处已有工具而跳过本文的安装、登录或本轮重启。

先输出上述安装中间文案，再在本机命令工具逐条检查依赖和已有安装状态；除下述允许备用的读取或下载失败外，任何命令失败时记录该步结果并停止，不继续执行后面的安装命令：

```bash
python3 --version
git --version
claude plugin --help
claude plugin marketplace list
claude plugin list
```

下载首选 `https://github.com/openagent-org/claude-plugin.git`（`github`），备用为 `https://gitee.com/openagent-org/claude-plugin.git`（`gitee`）。由安装助手执行一次备用选择，不让用户选择网络地区；已有合法官方来源可继续使用，不为恢复主源而强制迁移；从此前已装 Gitee 开始时，另一官方来源是备用。本次加载已使用一次备用后不得回切。仅 DNS、连接、超时、传输中断或 HTTP 5xx 失败可尝试备用一次；权限或审批拒绝、证书错误、HTTP 401/403/404/429/451，以及摘要、语法、执行或 OAuth 错误均停止，不换源。备用也失败即停止。安装器本身不自动重试另一来源。

选择来源时先只读当前生效 3P 配置中 OpenAgent Marketplace 的 `source`、`url`、`ref`、`installationPreference` 字段；不要输出整个配置或推理凭据。已有合法且仍可用的官方来源优先沿用，不能因命令示例为 `github` 就把它迁回。执行前将 `install_source` 填为本次选定来源，后续命令沿用该来源，不依赖不同命令调用共享 shell 变量。安装文件直接从 `rel` 下载；Gitee Raw 地址为 `https://gitee.com/openagent-org/claude-plugin/raw/rel/<path>`。两份文件完整下载到临时目录并通过语法校验后才执行安装器一次。仅在原命令已结束且确认安装器尚未执行的下载失败后，才可改来源补全下载，丢弃残片，不拼接输出；禁止管道执行、`命令 || 换源执行` 或执行结果未知后重跑。后续重启同样只对下载阶段适用此规则。

然后从选定官方仓库的 `rel` 下载 [3P 配置脚本](https://github.com/openagent-org/claude-plugin/blob/rel/install-desktop-connector.py)和 `openagent-connector-auth.py`。向安装器传入 `--ref rel` 和选定来源，命令结束后清理临时文件：

```bash
(
  set -e
  install_source='github'
  case "$install_source" in
    github) install_raw='https://raw.githubusercontent.com/openagent-org/claude-plugin/rel' ;;
    gitee) install_raw='https://gitee.com/openagent-org/claude-plugin/raw/rel' ;;
    *) exit 1 ;;
  esac
  printf 'OPENAGENT_SOURCE=%s\n' "$install_source"
  install_dir="$(mktemp -d "${TMPDIR:-/tmp}/openagent-claude-install.XXXXXX")"
  trap 'rm -f -- "$install_dir/install-desktop-connector.py" "$install_dir/openagent-connector-auth.py"; rmdir -- "$install_dir"' EXIT
  curl -fsSL --proto '=https' --proto-redir '=https' "$install_raw/install-desktop-connector.py" -o "$install_dir/install-desktop-connector.py"
  curl -fsSL --proto '=https' --proto-redir '=https' "$install_raw/openagent-connector-auth.py" -o "$install_dir/openagent-connector-auth.py"
  python3 -c 'import ast, pathlib, sys; [ast.parse(pathlib.Path(path).read_bytes(), filename=path) for path in sys.argv[1:]]' "$install_dir/install-desktop-connector.py" "$install_dir/openagent-connector-auth.py"
  python3 "$install_dir/install-desktop-connector.py" --ref rel --source "$install_source"
)
```

脚本将同目录 helper 持久安装到 `~/Library/Application Support/OpenAgent/Claude/openagent-connector-auth.py`，使用本次 Python 解释器的绝对 shebang；解释器路径含空白时明确失败，helper 路径含空格不受影响。随后增量写入当前 3P 配置的 `managedMcpServers` 和 `allowedPluginMarketplaces`：`--ref rel` 由安装器内部解析所选官方来源的当前发布提交，并以宿主要求的完整提交设置 `installationPreference: auto_install`；不将分支名 `rel` 直接写成自动安装版本。新装、旧分支配置及旧固定版本都会更新到当前发布版本，同一版本和同一来源重复执行不改配置。`--source` 只接受 `github` 或 `gitee`；新装省略时默认 GitHub，已有合法来源未显式指定时保留。直接运行安装器且未传入 `--ref` 时仍保留已有合法固定版本。插件源仅接受上述 GitHub 或 Gitee 精确地址；其他同名来源停止，不覆盖。OpenAgent Connector 的旧原生 `oauth` 被替换为绝对路径 `headersHelper`，`headersHelperTtlSec=300`、`headersHelperRefreshBufferSec=60`，保留 `X-OASN-MCP-OAuth: required` 和 `X-OASN-MCP-Widget-Transport: claude-direct`；省略 `oauth`，不写 `oauth:false`。安装器不注册 OAuth 客户端，也不获取 Token；注册与授权在第 2 节的 helper `login` 中完成。配置写入前在同目录备份，备份可能含推理凭据，不要上传。脚本成功只证明文件与配置已写入，不证明运行中的 Claude 已加载 Connector 或插件。

根据刚才的 `claude plugin marketplace list` 核对 `openagent-claude`：不存在时，按本次选定来源执行 `claude plugin marketplace add 'https://github.com/openagent-org/claude-plugin.git#rel'` 或 `claude plugin marketplace add 'https://gitee.com/openagent-org/claude-plugin.git#rel'`；已存在且为这两个精确官方来源之一、分支为 `rel` 时可继续使用，不强制切回 GitHub；上述官方来源的旧分支按下方迁移，其他来源停止，不覆盖。原生 CLI 保留 `#rel` 更新机制，回读实际登记的官方来源、分支及插件安装和启用状态。

根据 `claude plugin list` 核对 `openagent@openagent-claude`：未安装时才执行 `claude plugin install openagent@openagent-claude --scope user`；已安装且启用时跳过；已安装但停用时停止并报告状态，不把它算作安装完成。每次执行后重新读取对应列表确认结果；Marketplace 下载未结束时等待原命令，不并发重复安装。仅当确认原命令已结束且失败限于上述可备用的下载错误时，先回读 Marketplace 和插件状态，再对精确官方、用户范围登记按下方步骤切换一次来源；登记已与本次选定来源一致才直接继续；已决定换源且来源不同则执行下方迁移步骤。部分状态或副作用不明时停止。不得重跑已成功的配置、登录或重启步骤。插件包含五个 Skills，无须另行复制：`openagent-first-task-router`、`openagent-guide-agent`、`openagent-search-agent`、`openagent-run-agent`、`openagent-query-account`。

官方源旧分支迁移或本次下载备用切换：仅对 `openagent-claude` 的精确官方用户范围登记操作。旧 `master` 仅允许上述 GitHub 或 Gitee；本次明确下载失败的 `rel` 允许上述 GitHub 或 Gitee。执行 `claude plugin marketplace remove openagent-claude --scope user`，回读 `claude plugin marketplace list`；确认该登记已移除后，按所选来源执行上方 `marketplace add`，回读确认来源及 `rel`。若仍有其他作用域同名登记，停止，不扩大删除范围。随后重新读取 `claude plugin list`：缺失时安装，仍已安装且启用时执行 `claude plugin update openagent@openagent-claude --scope user`，停用时停止并报告。每步失败先停止并记录；只能按上述下载规则恢复，且从实际登记状态继续，不重复移除已匹配的新源。不执行卸载脚本、`mcp logout` 或清理 OAuth 配置。其他同名来源仍按冲突处理。

目标 MCP 必须为 `https://openagent.org/mcp/v1/open-agent`。第 1 步脚本只接受这一地址；同名 Connector 使用其他地址时停止，不覆盖配置或复用其授权。终端 CLI 插件更新见文末可选步骤，不作为 Desktop 3P 安装前置。

插件 MCP 和桌面 3P Connector 使用独立 client 与 grant，不复制彼此 Token。Desktop 3P 默认只完成第 2 节的 helper 登录；只有用户需要在终端 CLI 中使用 OpenAgent 时，才执行文末可选的 CLI 登录。插件和 Skills 安装不要求先完成 CLI OAuth。卸载器仅识别当前 MCP 地址和上述 GitHub、Gitee 官方来源；另安全清理专属 helper、`.auth.lock` 和 Keychain 整项，未知文件保留，两者均不远端撤销授权。

## 2. 登录 Desktop Connector

先确认命令工具能够保留并等待同一进程。默认安装只运行 helper `login` 和 `status`，不运行 CLI MCP 登录：

```bash
(
  set -e
  "$HOME/Library/Application Support/OpenAgent/Claude/openagent-connector-auth.py" login
  "$HOME/Library/Application Support/OpenAgent/Claude/openagent-connector-auth.py" status
)
```

helper `login` 先复用权限和有效期符合要求的既有凭据；需要续期时先使用 Refresh Token 刷新。只有尚未保存凭据（首次或 `logout` 后），或刷新明确返回 HTTP 400 `invalid_grant` 时，才打开浏览器授权；已有凭据损坏、资源或权限异常、网络错误或服务故障则保留原有状态并报告失败，不重新注册或自动弹出授权页。需要授权时复用匹配的独立注册，必要时注册 `agent.discover agent.invoke artifact.read` 的公开客户端。首次仍由用户登录并同意权限；需要切换账号或强制重新授权时，显式运行 helper `logout` 后再运行 `login`。

仅允许一个登录进程，发起后保留并等待其结束。页面实际打开时才输出上述等待文案，由用户在浏览器中登录 OpenAgent 并确认权限；命令明确成功后输出上述已登录文案。取消、超时或失败时停止，使用上述对应模板，不并发重试，不点击 Desktop 的 Connect，不代收授权码、回调 URL 或 Token。也可在安装后用 `python3 "$HOME/Library/Application Support/OpenAgent/Claude/openagent-connector-auth.py" login` 发起同一入口。日常由 Claude 无参调用时，helper 非交互复用或刷新既有凭据，需要重新授权时只返回错误，不打开浏览器。

所有注册记录、Token 和过期信息只存 macOS Keychain（service `com.oasn.openagent.claude.headers-helper`，account `credentials`），不写磁盘 Token；同目录 `.auth.lock` 只用于互斥。`status` 只输出脱敏状态，不证明 Desktop 已连接。**安装助手严禁直接运行无参数 helper**：该入口仅供 Claude 自动读取 JSON Authorization header，会输出凭据；不要用它做检查，也不要直接读取 Keychain 条目。`logout` 仅清除该 helper 的本地 Token 并保留注册，不远端撤销、不影响插件 CLI 登录。参见 [Claude 官方 headersHelper 说明](https://claude.com/docs/third-party/claude-desktop/extensions#short-lived-credentials-with-a-headers-helper)。

`status` 退出码为 0 只表示读取完成；继续重启前还须确认 `registered`、`credentials_present`、`access_token_usable` 均为 `true`，否则停止并报告实际状态。`verification=local_only` 明确表示它只是本地凭据检查。

## 3. 核对 3P Connector 并验证

### 沙箱外重启 Claude

第 1、2 节全部成功后，先按第 4 节生成完整启动消息，并用文件写入工具保存为本用户私有目录中的 UTF-8 JSON 文件，结构为 `{"message":"完整启动消息"}`，文件权限为 0600。使用 JSON 序列化保留引号、段内换行及用户原始需求，不把消息正文插入 shell 命令、不写入仓库或诊断输出。消息必须非空且不超过 14,336 个 UTF-16 code units，超长在重启前拒绝，不截断。脚本只做 URL 编码；Claude 原生输入框会规范化部分字符和空白，用户发送前需核对。将下方 `message_file` 替换为这个文件的真实绝对路径，不能保留示例路径或占位符。保存本次安装进度、helper login/status 的脱敏结果和用户原始需求到当前会话，再输出上述重启文案。

命令必须来自当前 Claude Code Bash，保留宿主提供的 `CLAUDE_CODE_SESSION_ID`；脚本用它唯一关联本次会话和仍未完成的 Bash 调用。缺少该上下文时停止，不从其他会话复制 ID，也不在普通终端伪造环境变量。只对下面这一条命令请求 **Bash 沙箱外执行**：若实际 Bash 工具提供 `dangerouslyDisableSandbox`，在工具调用参数中设为 `true`，遵循宿主权限流程。它不是 shell 环境变量，也不是 Python 参数。以宿主显示的沙箱外执行状态为准；`sandbox.allowUnsandboxedCommands=false` 或管理策略阻止时，停止自动重启，报告需要用户正常退出并重新打开应用，后续按第 5 节核对后决定人工发送。不要自动修改安全配置、放行所有 Python 命令或用 `--dangerously-skip-permissions` 替代沙箱外执行。参见 [Claude 官方沙箱说明](https://code.claude.com/docs/en/sandboxing)。

执行前将下方 `install_source` 填为第 1 节选定的实际来源，从该来源的 `rel` 下载重启脚本。下载失败仅按第 1 节规则处理，重启已提交或结果未知时不得换源重跑。

```bash
(
  set -e
  message_file='/absolute/path/to/openagent-startup.json'
  [ -n "${CLAUDE_CODE_SESSION_ID:-}" ]
  restart_file="$(mktemp "${TMPDIR:-/tmp}/openagent-claude-restart.XXXXXX")"
  trap 'rm -f -- "$restart_file"' EXIT
  install_source='github'
  case "$install_source" in
    github) install_raw='https://raw.githubusercontent.com/openagent-org/claude-plugin/rel' ;;
    gitee) install_raw='https://gitee.com/openagent-org/claude-plugin/raw/rel' ;;
    *) exit 1 ;;
  esac
  curl -fsSL --proto '=https' --proto-redir '=https' "$install_raw/restart-desktop.py" -o "$restart_file"
  python3 -c 'import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_bytes(), filename=sys.argv[1])' "$restart_file"
  python3 "$restart_file" --message-file "$message_file"
)
```

脚本只支持 `/Applications/Claude.app`。前台唯一映射当前会话 metadata，从本次未完成 Bash 沿 transcript 的 `parentUuid` 回溯到本轮首条非 `tool_result` 的主 `user` 消息；磁盘 `lastAssistantUuid` 可匹配本轮同分支任一已出现的 assistant UUID，并要求同份 metadata 的 `lastActivityAt` 不早于该 assistant 时间，才读取 `completedTurns` 基线。当前 Bash 尚未落盘（未返回数量为 0）或本轮 metadata 尚未就绪时，在同一 15 秒期限内等待并重读；多个未返回 Bash、断链、循环、重复 UUID、子代理或损坏记录立即拒绝。超时在创建 worker 前停止，不退回旧轮摘要、旧计数或固定等待，也不由助手追加 `sleep` 后重试。一次性 worker 交给当前用户的 macOS `launchd` 后进入 `waiting_for_turn`，每秒检查计数，只有严格增长才请求正常退出 Claude；不再固定等待 5 秒。目标 PID 变化或出现新错误时停止，不强杀、不自动重试，仍尊重客户端正常退出保护。宿主禁止沙箱外执行时，不得通过 `launchd` 绕过限制。若 macOS 请求控制 Claude 的权限，按系统权限流程处理。

记录命令输出中的 `receipt` 绝对路径。脚本副本和回执放在独立的 `/private/tmp/openagent-claude-restart-*` 目录，避免临时下载文件删除后无法重启。`scheduled` 仅为 worker 交接状态，`waiting_for_turn` 表示正在等待当前 turn；两者都不代表重启成功。**提交成功后正常结束当前安装 turn，不在本轮轮询 worker、等待终态或继续调用安装工具，否则会阻止本轮完成。** 进度、任务和记忆应在提交前保存；提交成功后不再读回执、更新任务或记忆。`重启提交未确认` 表示前台未确认任务交接，不能当作执行重启后的失败；先核对本次调用和已返回回执，不自行改脚本或追加延迟重试。`waiting_for_turn` 不适用旧“超过三分钟无终态”判断。提交失败或后续回执为 `failed` 时读取 `stage` 定位并停止重试；提交超时属于结果未知，保留可能仍在运行的 worker 与回执，不重复提交。Claude 已关闭且未重新打开时，由用户手动打开应用并恢复本会话。

旧 PID 完全消失后，worker 先正常打开 Claude 并确认新 PID，再通过原生 `claude://code/new?q=<提示语>` 深链预填新 Code 会话输入框，等待用户主动点击发送。链接仅包含 `q`，不传 `folder`，不保证沿用安装会话的目录；发送前由用户核对或选择 Local 和目标目录，未信任目录仍由 Claude 正常确认。使用 macOS `NSWorkspace.openURL`，正文只经标准输入交接，不进入进程命令参数；核对系统处理应用为 `/Applications/Claude.app` 后才打开。此入口不需要插件 hook，不使用 macOS 辅助功能自动化、System Events、剪贴板、CDP 或私有发送接口。脚本不创建 Claude 定时任务，不读写旧任务或调度开关。管理配置 `disableDeepLinkRegistration=true` 或 `disableDesktopLocalSessions=true` 时停止，不改政策、不绕过工作目录信任。独立调用可省略 `--message-file`，此时只重启；本安装流程传入第 4 节消息。

重启后先读取本轮 `receipt`。只有 `state=restarted` 且记录了不同的旧、新 PID 才确认进程重启；这不证明输入框已显示、Connector 已加载或 OAuth 已成功。有消息时回执记录 `prompt_prefill=not_requested/pending_verification/requested` 和 `prompt_delivery=not_sent`。`prompt_prefill=requested` 只表示系统接受了深链；交接失败或超时须核对实际输入框，不能据此重试、覆盖用户草稿或代替用户发送。`prompt_delivery=not_sent` 只记录脚本没有发送，用户之后点击发送不会更新此回执。需要恢复时从回执检查继续，不重跑第 1、2 节；按第 5 节报告或提供手动填入的消息。确认终态、保存脱敏结果并确保 worker 已结束后，只清理该次目录剩下的 `status.json` 和空目录，不按通配符清理其他任务。

本轮安装仅接受第 1、2 节完成后由本轮重启命令返回并记录的 `receipt`。卸载后重新安装属于新一轮安装，必须在前两节成功后按本节重新提交一次重启，不能用历史回执、“今天已经重启过”或 `custom3p-mcp-schemas.json` 缓存跳过。上述“不重复提交”仅适用于同一轮安装中已提交重启后的中断恢复；不能确认回执属于本轮时，报告重启未确认，先核对本轮提交记录及活动任务，不盲目重启。用户拒绝重启或权限不允许时，报告安装尚未完成。

### 重启后只读核对连接

Claude 应通过配置的 helper 自动取得授权 header，无须点击 **Connect**。恢复后只读核对当前 Desktop 实际加载的 `openagent` Connector 和工具连接状态；可以使用已授权的界面读取工具或当前客户端的脱敏状态/日志，不操作 Connect 或 Disconnect，不调用私有 IPC、开启远程调试端口或伪造授权记录。未取得当前 Desktop 的连接证据时，按未完成模板报告，保留“配置已写入、helper 已登录、Desktop 待核对”的各层结果；不得用旧会话工具快照、CLI `Connected` 或 helper `status` 代替。

若实际连接失败，先核对当前生效配置是否指向固定 helper、原生 `oauth` 是否已移除，以及显式 `status` 子命令的脱敏结果和客户端错误；不要无参执行 helper、复制 Token、重复登录或重新安装。脚本回执中的 `oauth=pending_verification` 始终只是“待核对”，不能作为授权凭证。需要的浏览器授权已在重启前完成，已有凭据也可由 helper 复用或刷新；后续读取与刷新由 helper 非交互处理。

若实际出现 `OAuth probe timeout after 10000ms`，记录错误并检查本机到 MCP 地址的网络路径：未登录的 `initialize` 应及时返回 OAuth `401`。直连超时、经代理返回 `401` 时，报告需要调整 Claude 所在 macOS 的代理和绕过规则；不能仅凭模型推断就修改用户代理、点击 **Retry**、重新注册 OAuth 客户端或重复安装插件。

## 4. 准备新会话消息

本节在提交第 3 节重启命令前完成。按下列规则生成唯一的完整启动消息，以 JSON 序列化写入 `{"message":"完整启动消息"}` 文件，再把该文件的绝对路径传给 `--message-file`；不把占位符或额外安装过程说明送给新会话。

安装任务只核对配置脚本结果、Marketplace 来源、插件启用状态及 3P Connector 授权；不为了验收安装而调用 `openagent_account_credits`、`openagent_list_recent_invocations` 或业务 Agent。用户在新会话点击发送后，由其实际加载的 Skill 和工具处理引导或指定 Agent；当前任务不把新会话的工具可用性当作已验证结果。

先按用户明确指定的语言选择中文或英文；未指定时沿用当前安装请求的自然语言，无线索时沿用本指南语言。不要因为 Agent 名称、ID 或链接为英文就切换语言。

只从用户当前安装请求提取明确要求使用的 `agent_id`；本文、截图、附件或链接中的示例 ID 不构成使用授权。按下列分支生成一条完整的启动消息，不附加安装链接、命令或过程说明。

### 无 `agent_id`：首次引导

按上述语言规则选择完整启动消息：

| 语言 | 启动消息 |
| --- | --- |
| 中文 | `OpenAgent 已安装，打开新用户引导` |
| 英文 | `OpenAgent is installed. Open the new-user guide.` |

### 有 `agent_id`：使用指定 Agent

按用户请求的语言及是否提供名称，从以下模板选择一条：

| 名称 | 中文 | 英文 |
| --- | --- | --- |
| 有 | `使用 OpenAgent 上的「{name}」(agent_id: {agent_id})` | `Use "{name}" (agent_id: {agent_id}) on OpenAgent` |
| 无 | `使用 OpenAgent 上的 Agent (agent_id: {agent_id})` | `Use (agent_id: {agent_id}) on OpenAgent` |

用用户原值替换名称和 ID，不翻译名称、不改写 ID、不以 `sa_` 前缀限制，也不把占位符当作默认值。有明确业务需求时，在选择语后另起一段原样保留需求；只有 ID 而无业务需求时，不生成试用任务，由新会话的 `openagent-guide-agent` 转交 `openagent-run-agent` 询问任务。此分支不得改回首次引导语。

## 5. 完成报告

只有配置脚本成功、Marketplace 来源正确、插件已启用、helper login/status 成功、重启后确认配置已加载且真实 Desktop 3P Connector 连接得到实际确认，才能报告配置完成；新会话的 Skills 和工具加载仍由新会话判断。脚本只预填、不发送，用户点击发送后才启动新 turn。

实际核对新 Code 输入框已有第 4 节提示语且尚未发送时，使用以下模板；仅有 `prompt_prefill=requested` 或新 PID 时不能声称已经填入：

```text
OpenAgent 安装配置已完成。
启动消息已填入新 Code 会话，请核对提示语、Local 和目标目录后点击发送。
```

预填状态未知时，使用未完成模板，下一步为核对新 Code 输入框，不重复重启或自动预填。已确认未填入且配置验收通过时，提供以下手动输入模板；不在旧会话发送，也不替用户点击发送。若用户已主动发送并得到实际确认，只报告配置完成，不要求再次发送。

```text
OpenAgent 安装配置已完成。
请在 Claude 新 Code 会话确认 Local 和目标目录后，填入并发送：{启动消息}
```

`{启动消息}` 必须替换为第 4 节生成的完整内容，不得输出字面占位符。有业务需求时保留原有换行与正文；两行固定前缀之外不追加安装清单、验证结果或技术说明。

失败、取消、授权超时以外的结果未知或前置条件不满足时，只输出以下两行；填入简短、准确的原因和下一步操作，不得把未确认状态写成已完成：

```text
OpenAgent 安装尚未完成：{简短原因}。
下一步：{当前可执行的操作}。
```

## 可选：在终端 CLI 中使用 OpenAgent

仅当用户需要在终端 Claude Code CLI 中使用 OpenAgent 时执行本节；CLI 登录及检查结果不作为上述 Desktop 3P 安装完成或重启的门禁，不影响插件和 Skills 安装。

先用 `claude mcp get plugin:openagent:openagent` 核对插件 MCP 地址为 `https://openagent.org/mcp/v1/open-agent`。插件已安装且启用但仍使用旧地址时，不得按“已安装”跳过：依次执行 `claude plugin marketplace update openagent-claude`、`claude plugin update openagent@openagent-claude`，再用 `claude mcp get plugin:openagent:openagent` 核对新地址；仍为旧地址时停止 CLI 登录。更新方式参见 [Claude 官方插件管理说明](https://code.claude.com/docs/en/discover-plugins)。

先确认命令工具能够保留并等待同一进程，并用 `claude mcp login --help` 确认 CLI 支持登录。优先使用工具实际提供的 PTY/TTY 选项；若标准输入不是终端，在本机 macOS 使用系统 `/usr/bin/script` 为子进程分配伪终端。只对插件提供的 MCP 发起一次登录，并等待浏览器授权和命令结束：

```bash
(
  set -e
  if [ -t 0 ]; then
    claude mcp login plugin:openagent:openagent
  else
    /usr/bin/script -q /dev/null claude mcp login plugin:openagent:openagent
  fi
  claude mcp get plugin:openagent:openagent
)
```

发起后等待同一进程，页面打开时输出上述等待文案，明确成功后输出上述已登录文案。`script -q /dev/null` 只分配终端，不把会话录制到文件，也不代表 OAuth 成功；不要添加 `--no-browser` 强制进入手动粘贴回调模式。若出现 `stdin isn't a terminal`，先确认命令已退出；这是终端条件不满足，不是登录超时，不要重新安装插件。修正终端方式后只发起一次登录，不与旧进程并发。若宿主拒绝伪终端、工具不能等待同一进程，或浏览器仍无法打开并要求粘贴回调，则停止自动登录，请用户在 Mac 本机交互终端运行 `claude mcp login plugin:openagent:openagent` 并返回明确结果；不要代收回调 URL、授权码或 Token，不在另一个 shell 并发登录。取消、超时或失败时停止并报告本次 CLI 登录结果，不改变已确认的 Desktop 安装状态；超时时沿用上述固定超时文案，只在用户明确回复后重试。单独显示 `Connected` 不证明 OAuth 成功，也不能证明 Desktop Connector 已连接。
