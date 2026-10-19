#!/usr/bin/env bash
set -euo pipefail

PLUGIN_NAME="openagent"
PLUGIN_ID="openagent@openagent-claude"
MARKETPLACE_NAME="openagent-claude"
MCP_NAME="plugin:openagent:openagent"
ASSUME_YES=false

usage() {
  cat <<'EOF'
卸载 OpenAgent Claude 插件、Marketplace、缓存、本地 MCP OAuth、headersHelper 和当前 3P 配置中的 MCP。

用法：
  bash uninstall-openagent.sh [--yes]

选项：
  --yes   跳过人工确认，适用于 curl 管道执行
  --help  显示帮助

运行前请完全退出 Claude Desktop、Claude Code 和仍在使用本插件的 CLI 会话。
本脚本不会删除整个 ~/.claude、其他插件、用户产物或其他 MCP 配置。
EOF
}

while (($#)); do
  case "$1" in
    --yes)
      ASSUME_YES=true
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "错误：不支持的参数：$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

find_claude() {
  if [[ -n "${CLAUDE_CLI:-}" ]]; then
    if [[ ! -x "$CLAUDE_CLI" ]]; then
      echo "错误：CLAUDE_CLI 不是可执行文件：$CLAUDE_CLI" >&2
      return 1
    fi
    printf '%s\n' "$CLAUDE_CLI"
    return
  fi
  if command -v claude >/dev/null 2>&1; then
    command -v claude
    return
  fi
  if [[ -n "${HOME:-}" && -x "$HOME/.local/bin/claude" ]]; then
    printf '%s\n' "$HOME/.local/bin/claude"
    return
  fi
  echo "错误：未找到 Claude Code CLI；请先确认 claude 已安装并可执行。" >&2
  return 1
}

resolve_plugin_root() {
  local configured
  if [[ -n "${CLAUDE_CODE_PLUGIN_CACHE_DIR:-}" ]]; then
    configured="$CLAUDE_CODE_PLUGIN_CACHE_DIR"
  elif [[ -n "${CLAUDE_CONFIG_DIR:-}" ]]; then
    configured="${CLAUDE_CONFIG_DIR%/}/plugins"
  elif [[ -n "${HOME:-}" ]]; then
    configured="${HOME%/}/.claude/plugins"
  else
    echo "错误：无法确定 Claude 插件目录。" >&2
    return 1
  fi
  configured="${configured%/}"
  case "$configured" in
    ""|"/"|*[[:cntrl:]]*)
      echo "错误：Claude 插件目录不安全：$configured" >&2
      return 1
      ;;
    /*) ;;
    *)
      echo "错误：Claude 插件目录必须是绝对路径：$configured" >&2
      return 1
      ;;
  esac
  if [[ -d "$configured" ]]; then
    (cd "$configured" && pwd -P)
  else
    printf '%s\n' "$configured"
  fi
}

path_exists() {
  [[ -e "$1" || -L "$1" ]]
}

assert_owned_paths() {
  local path
  [[ "$MARKETPLACE_DIR" == "$PLUGIN_ROOT/marketplaces/$MARKETPLACE_NAME" ]] || return 1
  [[ "$CACHE_PLUGIN_DIR" == "$PLUGIN_ROOT/cache/$MARKETPLACE_NAME/$PLUGIN_NAME" ]] || return 1
  for path in \
    "$PLUGIN_ROOT/marketplaces" \
    "$MARKETPLACE_DIR" \
    "$PLUGIN_ROOT/cache" \
    "$PLUGIN_ROOT/cache/$MARKETPLACE_NAME" \
    "$CACHE_PLUGIN_DIR"; do
    if [[ -L "$path" ]]; then
      echo "错误：拒绝清理符号链接路径：$path" >&2
      return 1
    fi
  done
}

assert_no_live_cache_users() {
  local marker marker_name marker_json filename_pid pid
  path_exists "$CACHE_PLUGIN_DIR" || return 0
  while IFS= read -r -d '' marker; do
    marker_name="${marker##*/}"
    if [[ "$marker_name" =~ ^([0-9]+)$ ]]; then
      filename_pid="${BASH_REMATCH[1]}"
    elif [[ "$marker_name" =~ ^([0-9]+)\.tmp\.[[:alnum:]]+$ ]]; then
      filename_pid="${BASH_REMATCH[1]}"
    else
      echo "错误：发现无法识别的插件占用标记：$marker" >&2
      return 1
    fi

    if ! marker_json="$(<"$marker")" || [[ ! "$marker_json" =~ \"pid\"[[:space:]]*:[[:space:]]*([0-9]+) ]]; then
      echo "错误：插件占用标记内容无效：$marker" >&2
      return 1
    fi
    pid="${BASH_REMATCH[1]}"
    if [[ "$pid" != "$filename_pid" ]]; then
      echo "错误：插件占用标记的进程号不一致：$marker" >&2
      return 1
    fi
    if kill -0 "$pid" 2>/dev/null; then
      echo "错误：进程 $pid 仍在使用 OpenAgent 插件；请完全退出 Claude 后重试。" >&2
      return 1
    fi
  done < <(find "$CACHE_PLUGIN_DIR" -type f -path '*/.in_use/*' -print0)
}

find_logout_plugin_dir() {
  local candidate
  candidate="$MARKETPLACE_DIR/$PLUGIN_NAME"
  if [[ -d "$candidate" && ! -L "$candidate" && -f "$candidate/.claude-plugin/plugin.json" && -f "$candidate/.mcp.json" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi
  path_exists "$CACHE_PLUGIN_DIR" || return 1
  while IFS= read -r -d '' candidate; do
    if [[ ! -L "$candidate" && -f "$candidate/.claude-plugin/plugin.json" && -f "$candidate/.mcp.json" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(find "$CACHE_PLUGIN_DIR" -mindepth 1 -maxdepth 1 -type d -print0)
  return 1
}

remove_owned_directory() {
  local path="$1"
  path_exists "$path" || return 0
  rm -rf -- "$path"
  if path_exists "$path"; then
    echo "错误：未能删除 OpenAgent 专属目录：$path" >&2
    return 1
  fi
}

manage_3p_config() {
  python3 - "$1" <<'PY'
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone

mode = sys.argv[1]
directory = Path.home() / "Library/Application Support/Claude-3p/configLibrary"
server_urls = {"https://oasn-ow.haimawan.com/mcp/v1/open-agent",
               "https://oasn-pre.haimawan.com/mcp/v1/open-agent"}
server_names = {"openagent", "OpenAgent"}
marketplace_urls = {
    "https://github.com/openagent-org/claude-plugin.git",
    "https://oasn-ow.haimawan.com/git/openagent/claude-plugin.git",
}

def load(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"不是普通配置文件：{path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"配置不是 JSON 对象：{path.name}")
    return value

try:
    if not directory.exists():
        print("absent")
        sys.exit(0)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("3P 配置目录不是普通目录")
    applied_id = load(directory / "_meta.json").get("appliedId")
    if not isinstance(applied_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", applied_id):
        raise ValueError("无法确认当前生效的 3P 配置 ID")
    profile_path = directory / f"{applied_id}.json"
    profile = load(profile_path)
    servers = profile.get("managedMcpServers", [])
    marketplaces = profile.get("allowedPluginMarketplaces", [])
    if not isinstance(servers, list) or not all(isinstance(item, dict) for item in servers):
        raise ValueError("managedMcpServers 格式异常")
    if not isinstance(marketplaces, list) or not all(isinstance(item, dict) for item in marketplaces):
        raise ValueError("allowedPluginMarketplaces 格式异常")
    server_matches = [item for item in servers if item.get("name") in server_names or item.get("url") in server_urls]
    marketplace_matches = [item for item in marketplaces if item.get("expectedName") == "openagent-claude" or item.get("url") in marketplace_urls]
    if (len(server_matches) > 1 or any(item.get("name") not in server_names or item.get("url") not in server_urls
                                       or item.get("transport") != "http" for item in server_matches)):
        raise ValueError("OpenAgent MCP 配置与安装器不匹配，停止删除")
    if (len(marketplace_matches) > 1 or any(item.get("source") != "git" or item.get("url") not in marketplace_urls
                                            or item.get("expectedName", "openagent-claude") != "openagent-claude"
                                            or not ((item.get("ref") in ("master", "rel") and item.get("installationPreference", "available") == "available")
                                                    or (isinstance(item.get("ref"), str) and re.fullmatch(r"[0-9a-fA-F]{40}", item["ref"])
                                                        and item.get("installationPreference") == "auto_install"))
                                            for item in marketplace_matches)):
        raise ValueError("OpenAgent 插件源与安装器不匹配，停止删除")
    if not server_matches and not marketplace_matches:
        print("absent")
        sys.exit(0)
    if mode == "check":
        print("present")
        sys.exit(0)
    if server_matches:
        profile["managedMcpServers"] = [item for item in servers if item not in server_matches]
    if marketplace_matches:
        profile["allowedPluginMarketplaces"] = [item for item in marketplaces if item not in marketplace_matches]
    backup = profile_path.with_name(f"{profile_path.name}.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}")
    with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as saved:
        with profile_path.open("rb") as original:
            shutil.copyfileobj(original, saved)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, prefix=".openagent-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump(profile, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, profile_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print("removed")
except (OSError, ValueError, json.JSONDecodeError) as error:
    sys.exit(f"错误：无法安全清理当前 3P 配置：{error}")
PY
}

manage_desktop_files() {
  # 先验证并规划所有专属目录及共享 JSON 的定点更新，再备份、原子写入和清理。
  python3 - "$1" <<'PY'
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone

mode = sys.argv[1]
home = Path.home().resolve()
base = home / "Library/Application Support/Claude-3p"
plugin_id = "openagent@openagent-claude"
marketplace = "openagent-claude"
updates, directories, links, files = [], [], [], []

def safe(path):
    if path.resolve() != path or path.lstat().st_uid != os.getuid():
        raise ValueError("路径为符号链接或不属于当前用户")

def load(path):
    safe(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("元数据不是普通文件")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("元数据不是对象")
    return value

def remove_entry(path, keys, name):
    if not path.exists() and not path.is_symlink():
        return
    value = load(path)
    entries = value
    for key in keys:
        entries = entries.get(key, {})
        if not isinstance(entries, dict):
            raise ValueError("元数据条目格式异常")
    if name in entries:
        del entries[name]
        updates.append((path, value))

try:
    runtime_roots = list((base / "local-agent-mode-sessions").glob("*/*/cowork_plugins"))
    for root in runtime_roots:
        safe(root)
        market_dir = root / "marketplaces" / marketplace
        cache_dir = root / "cache" / marketplace / "openagent"
        known_path = root / "known_marketplaces.json"
        if known_path.exists() or known_path.is_symlink():
            known = load(known_path).get(marketplace)
            if known is not None:
                source = known.get("source", {})
                if (source.get("source") != "git"
                        or source.get("url", "").removesuffix(".git") not in {
                            "https://github.com/openagent-org/claude-plugin",
                            "https://oasn-ow.haimawan.com/git/openagent/claude-plugin",
                        }
                        or known.get("installLocation") != str(market_dir)):
                    raise ValueError("托管 Marketplace 来源或位置冲突")
                remove_entry(known_path, [], marketplace)
        installed_path = root / "installed_plugins.json"
        if installed_path.exists() or installed_path.is_symlink():
            installed = load(installed_path).get("plugins", {})
            if not isinstance(installed, dict):
                raise ValueError("托管插件登记格式异常")
            if plugin_id in installed:
                entries = installed[plugin_id]
                if not isinstance(entries, list) or not entries:
                    raise ValueError("托管插件记录格式异常")
                for entry in entries:
                    location = Path(entry["installPath"])
                    if (location != market_dir / "openagent"
                            and not (location.parent == cache_dir and location.name not in (".", ".."))):
                        raise ValueError("托管插件路径越界")
                remove_entry(installed_path, ["plugins"], plugin_id)
        for directory in (market_dir, cache_dir):
            if not directory.exists() and not directory.is_symlink():
                continue
            safe(directory)
            if not directory.is_dir():
                raise ValueError("托管插件路径不是目录")
            # 不跟随任何内部链接，不删除其他安装或未知 Marketplace。
            for child in directory.rglob("*"):
                safe(child)
                if child.is_file() and child.parent.name == ".in_use":
                    marker = load(child)
                    pid = marker.get("pid")
                    if type(pid) is not int or pid <= 0 or child.name.split(".")[0] != str(pid):
                        raise ValueError("托管插件占用标记异常")
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        pass
                    else:
                        raise ValueError("托管插件仍被使用")
            manifest = (directory / ".claude-plugin/marketplace.json" if directory == market_dir else None)
            if manifest is not None:
                definition = load(manifest)
                plugins = definition.get("plugins", [])
                if (definition.get("name") != marketplace or len(plugins) != 1
                        or plugins[0].get("name") != "openagent" or plugins[0].get("source") != "./openagent"):
                    raise ValueError("托管 Marketplace 标识或插件范围不匹配")
            directories.append(directory)
        # 只解除指向本轮已验证托管位置的宿主入口，不删除链接目标以外的内容。
        hostloop = Path(tempfile.gettempdir()).resolve() / "claude-hostloop-plugins"
        for link in hostloop.glob("*/openagent"):
            if (link.is_symlink() and link.lstat().st_uid == os.getuid()
                    and link.resolve() == market_dir / "openagent"):
                safe(link.parent)
                links.append(link)

    for path, keys in ((base / "custom3p-mcp-schemas.json", ["directMcpToolSchemas"]),
                       (base / "config.json", ["custom3pMcpOAuth"])):
        if path.exists() or path.is_symlink():
            value = load(path)
            entries = value.get(keys[0], {})
            if not isinstance(entries, dict):
                raise ValueError("Desktop MCP 缓存格式异常")
            changed = False
            for name in ("openagent", "OpenAgent"):
                if name in entries:
                    del entries[name]
                    changed = True
            if changed:
                updates.append((path, value))

    blank = home / ".claude/.openagent/browser/blank.md"
    if blank.exists() or blank.is_symlink():
        safe(blank)
        if blank.is_file() and blank.stat().st_size == 0:
            files.append(blank)
        elif mode != "check":
            print("保留非空或未知的浏览器引导文件。", file=sys.stderr)
    if mode == "check":
        print("present" if updates or directories or links or files else "absent")
        sys.exit(0)

    for path, value in updates:
        backup = path.with_name(f"{path.name}.bak-openagent-uninstall-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}")
        with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as saved:
            saved.write(path.read_bytes())
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                os.fchmod(handle.fileno(), 0o600)
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    for link in links:
        link.unlink()
    for directory in directories:
        shutil.rmtree(directory)
    for file in files:
        file.unlink()
    print("Desktop OpenAgent 专属登记、缓存、OAuth 和空白引导文件已清理；共享 JSON 的权限 0600 备份保留在原目录。")
except (OSError, ValueError, KeyError, TypeError, AttributeError):
    sys.exit("错误：Desktop OpenAgent 文件格式、归属或清理校验失败，停止卸载；不输出配置或凭据正文。")
PY
}

manage_restart_receipts() {
  # 仅处理本用户的已结束回执；不递归删除，不移除 launchd 任务或 worker。
  python3 - "$1" <<'PY'
import json
import os
from pathlib import Path
import re
import stat
import sys

mode = sys.argv[1]
directories = []
for directory in Path("/private/tmp").glob("openagent-claude-restart-*"):
    if re.fullmatch(r"openagent-claude-restart-[a-z0-9_]{8}", directory.name):
        try:
            if directory.lstat().st_uid == os.getuid():
                directories.append(directory)
        except FileNotFoundError:
            continue
if mode == "check":
    print("present" if directories else "absent")
    sys.exit(0)

for directory in directories:
    try:
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("目录类型或权限不符")
        # worker/request 尚在、临时写入或未知文件存在时，不视作已结束。
        if {item.name for item in directory.iterdir()} != {"status.json"}:
            raise ValueError("任务尚未收尾或包含未知文件")
        receipt = directory / "status.json"
        info = receipt.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError("回执类型、归属或权限不符")
        value = json.loads(receipt.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or value.get("state") not in ("restarted", "failed")
                or value.get("oauth") != "pending_verification"):
            raise ValueError("非终态或无法识别的回执")
        receipt.unlink()
        directory.rmdir()
        print(f"已清理重启回执：{directory.name}")
    except (OSError, ValueError) as error:
        print(f"保留重启目录：{directory.name}（{type(error).__name__}，未确认可安全清理）", file=sys.stderr)
PY
}

manage_headers_helper() {
  # 不执行已安装脚本、不读取凭据正文；与 helper 共用锁，只清理本工具固定归属。
  python3 - "$1" <<'PY'
import errno
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import sys

mode = sys.argv[1]
directory = Path.home().resolve() / "Library/Application Support/OpenAgent/Claude"
helper = directory / "openagent-connector-auth.py"
lock_path = directory / ".auth.lock"
security = "/usr/bin/security"
keychain_args = ["-s", "com.oasn.openagent.claude.headers-helper", "-a", "credentials"]
descriptor = None

def safe(path, permissions, is_directory=False):
    info = path.lstat()
    expected = stat.S_ISDIR if is_directory else stat.S_ISREG
    if (path.resolve() != path or not expected(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != permissions or (not is_directory and info.st_nlink != 1)):
        raise ValueError("helper 路径类型、归属或权限不符")

def keychain(operation):
    result = subprocess.run([security, operation, *keychain_args],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    if result.returncode not in (0, 44):
        raise ValueError("无法安全检查或清理 helper 的 Keychain 项")
    return result.returncode == 0

try:
    if directory.resolve() != directory:
        raise ValueError("helper 路径含符号链接")
    if not Path(security).exists() and not directory.exists():
        print("absent")
        sys.exit(0)
    if directory.exists() or directory.is_symlink():
        safe(directory, 0o700, is_directory=True)
    has_helper = helper.exists() or helper.is_symlink()
    has_lock = lock_path.exists() or lock_path.is_symlink()
    if has_helper:
        safe(helper, 0o700)
        with helper.open(encoding="utf-8") as source:
            source.readline()
            if source.readline().rstrip("\n") != "# OpenAgent Claude headersHelper v1":
                raise ValueError("helper 标识与安装器不匹配")
    if has_lock:
        safe(lock_path, 0o600)
    has_credentials = keychain("find-generic-password")
    if not (has_helper or has_lock or has_credentials):
        print("absent")
        sys.exit(0)
    if mode != "check" and not directory.exists():
        directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.mkdir(mode=0o700)
        safe(directory, 0o700, is_directory=True)
    if has_lock or mode != "check":
        descriptor = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_CREAT, 0o600)
        safe(lock_path, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        opened, current = os.fstat(descriptor), lock_path.stat()
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise ValueError("helper 锁已变更，停止清理")
    if mode == "check":
        print("present")
        sys.exit(0)
    keychain("delete-generic-password")
    if has_helper:
        helper.unlink()
    lock_path.unlink()
    try:
        directory.rmdir()
    except OSError as error:
        if error.errno != errno.ENOTEMPTY:
            raise
        print("helper 目录含其他文件，已保留这些内容。", file=sys.stderr)
    print("helper 专属脚本、锁和本地 Keychain 凭据已清理；未撤销服务端授权。")
except BlockingIOError:
    sys.exit("错误：headersHelper 正在登录或刷新，未清理其凭据；请结束操作后重试。")
except (OSError, ValueError, subprocess.SubprocessError):
    sys.exit("错误：headersHelper 的归属、锁或 Keychain 检查失败，未确认清理完成；不输出凭据正文。")
finally:
    if descriptor is not None:
        os.close(descriptor)
PY
}

confirm_uninstall() {
  if [[ "$ASSUME_YES" == true ]]; then
    return 0
  fi
  if ! ( : </dev/tty ) 2>/dev/null; then
    echo "错误：当前没有可用的控制终端；确认无误后请使用 --yes。" >&2
    return 1
  fi
  printf '输入 uninstall 确认上述清理：' >/dev/tty
  local confirmation
  IFS= read -r confirmation </dev/tty || {
    echo "错误：无法读取确认输入，未执行卸载。" >&2
    return 1
  }
  if [[ "$confirmation" != "uninstall" ]]; then
    echo "已取消，未执行卸载。"
    return 1
  fi
}

PLUGIN_ROOT="$(resolve_plugin_root)" || exit 1
MARKETPLACE_DIR="$PLUGIN_ROOT/marketplaces/$MARKETPLACE_NAME"
CACHE_PLUGIN_DIR="$PLUGIN_ROOT/cache/$MARKETPLACE_NAME/$PLUGIN_NAME"
assert_owned_paths || {
  echo "错误：OpenAgent 清理路径未通过安全校验。" >&2
  exit 1
}
THREE_P_STATUS="$(manage_3p_config check)" || exit 1
RESTART_STATUS="$(manage_restart_receipts check)" || exit 1
DESKTOP_STATUS="$(manage_desktop_files check)" || exit 1
HELPER_STATUS="$(manage_headers_helper check)" || exit 1
if [[ "$THREE_P_STATUS" == "present" || "$DESKTOP_STATUS" == "present" || "$HELPER_STATUS" == "present" ]]; then
  if pgrep -x Claude >/dev/null; then
    echo "错误：Claude Desktop 仍在运行；请完全退出后再清理 3P MCP 和托管插件。" >&2
    exit 1
  else
    process_status=$?
    if [[ "$process_status" != 1 ]]; then
      echo "错误：无法核对 Claude 进程，未执行卸载。" >&2
      exit 1
    fi
  fi
fi
if ! CLAUDE="$(find_claude)"; then
  if [[ "$THREE_P_STATUS" == "present" || "$HELPER_STATUS" == "present" ]]; then
    assert_no_live_cache_users || exit 1
    echo "只能清理 Desktop 的 OpenAgent MCP、插件源及 headersHelper；Claude CLI 不可用，插件部分无法核验。"
    confirm_uninstall || exit 1
    if [[ "$THREE_P_STATUS" == "present" ]]; then
      [[ "$(manage_3p_config remove)" == "removed" ]] || exit 1
    fi
    [[ "$(manage_3p_config check)" == "absent" ]] || exit 1
    manage_desktop_files remove
    manage_headers_helper remove
    manage_restart_receipts remove
    echo "当前 3P 配置中的 OpenAgent MCP、插件源和 headersHelper 本地状态已清理；插件、插件 MCP OAuth 和缓存尚未核验，请安装 Claude CLI 后重运行此脚本。" >&2
  fi
  exit 1
fi

if ! PLUGINS_JSON="$("$CLAUDE" plugin list --json)"; then
  echo "错误：无法读取 Claude 插件状态，未执行卸载。" >&2
  exit 1
fi
if ! MARKETPLACES_JSON="$("$CLAUDE" plugin marketplace list --json)"; then
  echo "错误：无法读取 Claude Marketplace 状态，未执行卸载。" >&2
  exit 1
fi

PLUGIN_INSTALLED=false
MARKETPLACE_CONFIGURED=false
DIRECTORIES_PRESENT=false
MCP_LOGOUT_MODE="none"
MCP_LOGOUT_PLUGIN_DIR=""
if grep -Fq "$PLUGIN_ID" <<<"$PLUGINS_JSON"; then
  PLUGIN_INSTALLED=true
fi
if grep -Fq "$MARKETPLACE_NAME" <<<"$MARKETPLACES_JSON"; then
  MARKETPLACE_CONFIGURED=true
fi
if path_exists "$MARKETPLACE_DIR" || path_exists "$CACHE_PLUGIN_DIR"; then
  DIRECTORIES_PRESENT=true
fi
if [[ "$PLUGIN_INSTALLED" == true ]]; then
  MCP_LOGOUT_MODE="installed"
elif [[ "$DIRECTORIES_PRESENT" == true ]] && MCP_LOGOUT_PLUGIN_DIR="$(find_logout_plugin_dir)"; then
  MCP_LOGOUT_MODE="residual"
fi

if [[ "$PLUGIN_INSTALLED" == false && "$MARKETPLACE_CONFIGURED" == false && "$DIRECTORIES_PRESENT" == false && "$THREE_P_STATUS" == "absent" && "$RESTART_STATUS" == "absent" && "$DESKTOP_STATUS" == "absent" && "$HELPER_STATUS" == "absent" ]]; then
  echo "OpenAgent Claude 插件、Marketplace、专属缓存和当前 3P MCP 均不存在，无需处理。"
  exit 0
fi
if [[ "$PLUGIN_INSTALLED" == false && "$DIRECTORIES_PRESENT" == true && "$MCP_LOGOUT_MODE" == "none" ]]; then
  echo "错误：发现 OpenAgent 残留目录，但无法定位可信插件定义来清除 MCP OAuth；未执行删除。" >&2
  exit 1
fi

assert_no_live_cache_users || exit 1

echo "将完整清理用户范围的 OpenAgent Claude 安装："
if [[ "$MCP_LOGOUT_MODE" != "none" ]]; then
  echo "  - 清除 $MCP_NAME 的本地 OAuth 凭据"
fi
if [[ "$PLUGIN_INSTALLED" == true ]]; then
  echo "  - 卸载插件 $PLUGIN_ID"
fi
if [[ "$MARKETPLACE_CONFIGURED" == true ]]; then
  echo "  - 移除 Marketplace $MARKETPLACE_NAME"
fi
echo "  - 删除 $MARKETPLACE_DIR"
echo "  - 删除 $CACHE_PLUGIN_DIR"
echo "  - 安全清理本用户已结束的重启回执；保留运行中或状态未知的目录"
echo "  - 清理 Desktop 中 OpenAgent 托管插件、登记、schema 缓存和 OAuth；共享 JSON 先备份，保留其他条目"
if [[ "$HELPER_STATUS" == "present" ]]; then
  echo "  - 清理 headersHelper 专属脚本、锁及本地 Keychain 凭据；不撤销远端授权"
fi
if [[ "$THREE_P_STATUS" == "present" ]]; then
  echo "  - 从当前 3P 配置移除 OpenAgent MCP 和插件源，并备份原配置"
fi

confirm_uninstall || exit 1

if [[ "$MCP_LOGOUT_MODE" != "none" ]]; then
  echo ">>> 清除 MCP OAuth..."
  if [[ "$MCP_LOGOUT_MODE" == "installed" ]]; then
    MCP_LOGOUT_COMMAND=("$CLAUDE" mcp logout "$MCP_NAME")
  else
    MCP_LOGOUT_COMMAND=("$CLAUDE" --plugin-dir "$MCP_LOGOUT_PLUGIN_DIR" mcp logout "$MCP_NAME")
  fi
  if ! "${MCP_LOGOUT_COMMAND[@]}"; then
    echo "错误：MCP OAuth 清除失败；插件、Marketplace 和缓存保持不变。" >&2
    exit 1
  fi
fi

if [[ "$PLUGIN_INSTALLED" == true ]]; then
  echo ">>> 卸载插件..."
  if ! "$CLAUDE" plugin uninstall "$PLUGIN_ID" --scope user; then
    echo "错误：插件卸载失败；Marketplace 和缓存保持不变。" >&2
    exit 1
  fi
  if ! PLUGINS_JSON="$("$CLAUDE" plugin list --json)"; then
    echo "错误：插件命令已执行，但无法复核卸载结果；Marketplace 和缓存保持不变。" >&2
    exit 1
  fi
  if grep -Fq "$PLUGIN_ID" <<<"$PLUGINS_JSON"; then
    echo "错误：复核时仍发现 ${PLUGIN_ID}；Marketplace 和缓存保持不变。" >&2
    exit 1
  fi
fi

if [[ "$MARKETPLACE_CONFIGURED" == true ]]; then
  echo ">>> 移除 Marketplace..."
  MARKETPLACE_REMOVE_OUTPUT=""
  if MARKETPLACE_REMOVE_OUTPUT="$("$CLAUDE" plugin marketplace remove "$MARKETPLACE_NAME" --scope user 2>&1)"; then
    if [[ -n "$MARKETPLACE_REMOVE_OUTPUT" ]]; then
      printf '%s\n' "$MARKETPLACE_REMOVE_OUTPUT"
    fi
  elif grep -Fq "is not declared in user settings" <<<"$MARKETPLACE_REMOVE_OUTPUT"; then
    echo "用户范围已无 $MARKETPLACE_NAME 声明，继续清理同名 Marketplace 的残留作用域..."
    if ! "$CLAUDE" plugin marketplace remove "$MARKETPLACE_NAME"; then
      echo "错误：Marketplace 残留作用域移除失败；缓存保持不变。" >&2
      exit 1
    fi
  else
    if [[ -n "$MARKETPLACE_REMOVE_OUTPUT" ]]; then
      printf '%s\n' "$MARKETPLACE_REMOVE_OUTPUT" >&2
    fi
    echo "错误：Marketplace 移除失败；缓存保持不变。" >&2
    exit 1
  fi
  if ! MARKETPLACES_JSON="$("$CLAUDE" plugin marketplace list --json)"; then
    echo "错误：Marketplace 命令已执行，但无法复核移除结果；缓存保持不变。" >&2
    exit 1
  fi
  if grep -Fq "$MARKETPLACE_NAME" <<<"$MARKETPLACES_JSON"; then
    echo "错误：复核时仍发现 ${MARKETPLACE_NAME}；缓存保持不变。" >&2
    exit 1
  fi
fi

echo ">>> 删除 OpenAgent 专属文件..."
remove_owned_directory "$MARKETPLACE_DIR"
remove_owned_directory "$CACHE_PLUGIN_DIR"

if [[ "$THREE_P_STATUS" == "present" ]]; then
  echo ">>> 清理当前 3P 配置..."
  [[ "$(manage_3p_config remove)" == "removed" ]] || {
    echo "错误：当前 3P 配置未完成清理。" >&2
    exit 1
  }
fi

if "$CLAUDE" mcp get "$MCP_NAME" >/dev/null 2>&1; then
  echo "错误：复核时仍能读取 ${MCP_NAME}。" >&2
  exit 1
fi
if path_exists "$MARKETPLACE_DIR" || path_exists "$CACHE_PLUGIN_DIR"; then
  echo "错误：OpenAgent 专属目录仍然存在。" >&2
  exit 1
fi
if [[ "$(manage_3p_config check)" != "absent" ]]; then
  echo "错误：复核时当前 3P 配置仍有 OpenAgent MCP 或插件源。" >&2
  exit 1
fi

manage_desktop_files remove
[[ "$(manage_desktop_files check)" == "absent" ]] || {
  echo "错误：Desktop OpenAgent 专属状态仍存在。" >&2
  exit 1
}
manage_restart_receipts remove
manage_headers_helper remove
[[ "$(manage_headers_helper check)" == "absent" ]] || {
  echo "错误：headersHelper 本地状态仍存在。" >&2
  exit 1
}

echo "OpenAgent Claude 插件已卸载：插件、Marketplace、专属缓存、headersHelper 本地状态和当前 3P 配置中的 MCP 均已清理；已安装插件的本地 MCP OAuth 也已退出。未确认可安全清理的重启目录按提示保留。"
echo "请新建 Claude Code 会话，确认 mcp__plugin_openagent_openagent__* 工具不再出现。"
echo "服务端账号授权是否需要另行撤销，以 OpenAgent 实际提供的授权管理入口为准。"
