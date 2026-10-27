#!/usr/bin/env python3
"""为本机 Claude Desktop 3P 当前生效配置添加 OpenAgent Connector 和插件源。"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


SERVER = {
    "name": "openagent",
    "transport": "http",
    "url": "https://openagent.org/mcp/v1/open-agent",
    "headers": {"X-OASN-MCP-OAuth": "required", "X-OASN-MCP-Widget-Transport": "claude-direct", "X-OASN-Client-Source": "claude"},
}
OAUTH_SCOPE = "agent.discover agent.invoke artifact.read"
HELPER_NAME = "openagent-connector-auth.py"
HELPER_MARKER = b"# OpenAgent Claude headersHelper v1"
MARKETPLACE = {
    "source": "git",
    "url": "https://github.com/openagent-org/claude-plugin.git",
    "expectedName": "openagent-claude",
}
MARKETPLACE_URLS = {
    "github": MARKETPLACE["url"],
    "gitee": "https://gitee.com/openagent-org/claude-plugin.git",
}


def marketplace_ref(source: str = "github") -> str:
    """解析发布分支的完整提交，以满足 3P Marketplace 自动安装的固定版本要求。"""
    try:
        result = subprocess.run(
            ["git", "ls-remote", MARKETPLACE_URLS[source], "refs/heads/rel"],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("无法获取 OpenAgent 插件发布提交；3P 配置未修改") from error
    match = re.fullmatch(r"([0-9a-fA-F]{40})\s+refs/heads/rel\s*", result.stdout)
    if result.returncode != 0 or match is None:
        raise ValueError("无法确认 OpenAgent 插件发布提交；3P 配置未修改")
    return match.group(1).lower()


def installed_oauth(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == {"scope", "clientId", "callbackPort"}
            and value["scope"] == OAUTH_SCOPE
            and isinstance(value["clientId"], str) and value["clientId"].startswith("mcp_client_")
            and type(value["callbackPort"]) is int and 1 <= value["callbackPort"] <= 65535)


def read_regular_json(path: Path) -> dict:
    """拒绝符号链接和非对象 JSON，避免写错配置目标。"""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"不是普通文件：{path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"配置不是 JSON 对象：{path.name}")
    return value


def helper_payload(source: Path, destination: Path) -> bytes:
    """预检专属文件，绑定本次 Python 解释器，避免 GUI 的 PATH 影响执行。"""
    if not stat.S_ISREG(source.lstat().st_mode):
        raise ValueError("认证 helper 源文件不是普通文件")
    lines = source.read_bytes().split(b"\n", 1)
    if len(lines) != 2 or lines[1].split(b"\n", 1)[0] != HELPER_MARKER:
        raise ValueError("认证 helper 源文件标识不匹配")
    interpreter = str(Path(sys.executable).resolve())
    if not interpreter.startswith("/") or any(char.isspace() for char in interpreter) or len(interpreter.encode()) > 500:
        raise ValueError("Python 解释器须位于无空白的绝对路径，请更换解释器后安装")
    # 检查所有现存祖先，拒绝通过符号链接安装到其他位置。
    for parent in destination.parents:
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError("认证 helper 目录含符号链接或非目录")
    for parent in (destination.parent.parent, destination.parent):
        if parent.exists() and (parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077):
            raise ValueError("认证 helper 专属目录的归属或权限异常")
    if destination.exists() or destination.is_symlink():
        info = destination.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077
                or destination.read_bytes().split(b"\n")[1:2] != [HELPER_MARKER]):
            raise ValueError("已有认证 helper 文件归属或内容异常，停止覆盖")
    return b"#!" + interpreter.encode() + b"\n" + lines[1]


def write_helper(destination: Path, payload: bytes) -> bool:
    """只原子替换工具拥有的脚本，不访问或迁移任何 OAuth 凭据。"""
    if destination.exists() and destination.read_bytes() == payload and destination.stat().st_mode & 0o777 == 0o700:
        return False
    # Path.mkdir(parents=True) 的中间目录默认权限不满足专属目录要求。
    for parent in reversed(destination.parents):
        if not parent.exists():
            parent.mkdir(mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".helper-", delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o700)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def install(config_dir: Path, helper_dir: Path = None, helper_source: Path = None,
            resolve_ref=None, source: str = None, refresh_release: bool = False) -> str:
    """增量安装 Connector 和插件源；冲突不写，更新前备份且保留其他配置。"""
    explicit_ref = resolve_ref is not None or refresh_release
    if source is not None and source not in MARKETPLACE_URLS:
        raise ValueError("插件来源只能是 github 或 gitee")
    if helper_dir is None:
        helper_dir = Path.home() / "Library/Application Support/OpenAgent/Claude"
    helper = helper_dir / HELPER_NAME
    payload = helper_payload(helper_source or Path(__file__).with_name(HELPER_NAME), helper)
    helper_config = {"headersHelper": str(helper), "headersHelperTtlSec": 300,
                     "headersHelperRefreshBufferSec": 60}
    if not config_dir.is_dir():
        raise ValueError("未找到 Claude Desktop 3P 本机配置；请先完成第三方推理设置")
    meta = read_regular_json(config_dir / "_meta.json")
    applied_id = meta.get("appliedId")
    if not isinstance(applied_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", applied_id):
        raise ValueError("无法确认当前生效的 3P 配置 ID，停止修改")
    profile_path = config_dir / f"{applied_id}.json"
    profile = read_regular_json(profile_path)
    marketplaces = profile.get("allowedPluginMarketplaces", [])
    if not isinstance(marketplaces, list) or not all(isinstance(item, dict) for item in marketplaces):
        raise ValueError("allowedPluginMarketplaces 不是插件源列表，停止修改")
    official_urls = MARKETPLACE_URLS.values()
    matching = [item for item in marketplaces if item.get("url") in official_urls
                or item.get("expectedName") == MARKETPLACE["expectedName"]]
    if matching and (len(matching) != 1 or matching[0].get("source") != "git"
            or matching[0].get("url") not in official_urls
            or matching[0].get("expectedName", MARKETPLACE["expectedName"]) != MARKETPLACE["expectedName"]):
        raise ValueError("已有冲突的 OpenAgent 插件源，停止覆盖")
    existing_marketplace = matching[0] if matching else None
    if source is None:
        source = next((name for name, url in MARKETPLACE_URLS.items()
                       if existing_marketplace and existing_marketplace.get("url") == url), "github")
    selected_marketplace = {**MARKETPLACE, "url": MARKETPLACE_URLS[source]}
    if resolve_ref is None:
        resolve_ref = lambda: marketplace_ref(source)
    pinned = existing_marketplace and (existing_marketplace.get("installationPreference") == "auto_install"
                                      and re.fullmatch(r"[0-9a-fA-F]{40}", str(existing_marketplace.get("ref", ""))))
    switching_source = existing_marketplace and existing_marketplace.get("url") != selected_marketplace["url"]
    if pinned and not switching_source and not explicit_ref:
        marketplace_action = ""
    else:
        if existing_marketplace and not pinned and (existing_marketplace.get("ref") not in ("master", "rel") or
                existing_marketplace.get("installationPreference", "available") != "available"):
            raise ValueError("已有冲突的 OpenAgent 插件源，停止覆盖")
        ref = existing_marketplace["ref"] if pinned and not explicit_ref else resolve_ref()
        pinned_marketplace = {**(existing_marketplace or {}), **selected_marketplace,
                              "ref": ref, "installationPreference": "auto_install"}
        marketplace_action = ""
        if pinned_marketplace != existing_marketplace:
            profile["allowedPluginMarketplaces"] = [
                pinned_marketplace if item is existing_marketplace else item for item in marketplaces
            ] if existing_marketplace else [*marketplaces, pinned_marketplace]
            marketplace_action = (f"迁移 OpenAgent 插件源至 {'GitHub' if source == 'github' else 'Gitee'}"
                                  if switching_source else "更新 OpenAgent 插件自动安装提交")
    servers = profile.get("managedMcpServers", [])
    if not isinstance(servers, list) or not all(isinstance(item, dict) for item in servers):
        raise ValueError("managedMcpServers 不是服务器列表，停止修改")
    named = [item for item in servers if item.get("name") == SERVER["name"]]
    if any(item.get("url") == SERVER["url"] and item.get("name") != SERVER["name"] for item in servers):
        raise ValueError("目标地址已被其他 Connector 使用，停止重复添加")
    if named:
        if (len(named) != 1 or named[0].get("transport") != SERVER["transport"]
                or named[0].get("url") != SERVER["url"]):
            raise ValueError("已有同名但配置不同的 OpenAgent Connector，停止覆盖")
        current = named[0]
        if (("oauth" in current and current["oauth"] is not True
             and current["oauth"] != {"scope": OAUTH_SCOPE} and not installed_oauth(current["oauth"]))
                or ("headersHelper" in current and ("oauth" in current or any(
                    current.get(key) != value for key, value in helper_config.items())))
                or ("headersHelper" not in current and any(key in current for key in
                    ("headersHelperTtlSec", "headersHelperRefreshBufferSec")))):
            raise ValueError("已有自定义认证配置，停止覆盖；请人工核对 OAuth 与 headersHelper")
        headers = current.get("headers", {})
        if not isinstance(headers, dict) or not all(isinstance(value, str) for value in headers.values()):
            raise ValueError("已有 Connector headers 格式异常，停止修改")
        if any(key.lower() == "authorization" for key in headers):
            raise ValueError("已有 Authorization 配置，停止覆盖；请人工核对")
        markers = [key for key in headers if key.lower() == "x-oasn-mcp-oauth"]
        if len(markers) > 1 or (markers and headers[markers[0]] != "required"):
            raise ValueError("已有 OAuth 请求标记冲突，停止覆盖")
        transports = [key for key in headers if key.lower() == "x-oasn-mcp-widget-transport"]
        if len(transports) > 1 or (transports and headers[transports[0]] != "claude-direct"):
            raise ValueError("已有 Claude 直连请求标记冲突，停止覆盖")
        sources = [key for key in headers if key.lower() == "x-oasn-client-source"]
        if len(sources) > 1 or (sources and headers[sources[0]] != "claude"):
            raise ValueError("已有客户端来源标记冲突，停止覆盖")
        updated_headers = dict(headers)
        if not markers:
            updated_headers["X-OASN-MCP-OAuth"] = "required"
        if not transports:
            updated_headers["X-OASN-MCP-Widget-Transport"] = "claude-direct"
        if not sources:
            updated_headers["X-OASN-Client-Source"] = "claude"
        updated = {**current, "url": SERVER["url"], "headers": updated_headers, **helper_config}
        # oauth 存在时 Claude 不使用 helper 的 Authorization，迁移必须完全移除此字段。
        updated.pop("oauth", None)
        if updated == current:
            action = ""
        else:
            profile["managedMcpServers"] = [updated if item is current else item for item in servers]
            action = "升级 OpenAgent Connector 为 headersHelper"
    else:
        profile["managedMcpServers"] = [*servers, {**SERVER, **helper_config}]
        action = "添加 OpenAgent Connector"

    changes = [item for item in (action, marketplace_action) if item]
    if not changes:
        if write_helper(helper, payload):
            return "已更新 OpenAgent 认证 helper；3P 配置无需修改"
        return "已存在相同的 OpenAgent Connector 和插件源，无需修改"

    backup = profile_path.with_name(
        f"{profile_path.name}.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    if backup.exists():
        raise ValueError("备份文件已存在，停止修改")
    write_helper(helper, payload)
    # 配置含推理凭据，备份从创建时就仅当前用户可读，不先复制再收窄权限。
    with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as saved:
        with profile_path.open("rb") as original:
            shutil.copyfileobj(original, saved)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=config_dir, prefix=".openagent-", suffix=".tmp", delete=False
        ) as handle:
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
    return f"已{'、'.join(changes)}；原配置已在同目录备份"


def main() -> None:
    if sys.platform != "darwin":
        raise ValueError("本脚本仅适用于 macOS Claude Desktop 3P")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="rel 表示由安装器解析当前发布提交；也兼容完整提交 SHA")
    parser.add_argument("--source", choices=MARKETPLACE_URLS, help="官方插件来源；新装默认 github，已有合法来源默认保留")
    args = parser.parse_args()
    if args.ref and args.ref != "rel" and not re.fullmatch(r"[0-9a-fA-F]{40}", args.ref):
        raise ValueError("发布 ref 必须是 rel 或完整提交 SHA")
    config_dir = Path.home() / "Library/Application Support/Claude-3p/configLibrary"
    print(install(config_dir, resolve_ref=(lambda: args.ref.lower()) if args.ref and args.ref != "rel" else None,
                  source=args.source, refresh_release=args.ref == "rel"))
    print("请在 Claude 的 Customize → Connectors 核对 openagent；配置写入不等于运行中的 Claude 已加载。")
    print("请执行已安装的 openagent-connector-auth.py login，首次在浏览器确认三项权限；随后用 status 核对。")
    print("helper 独立授权，不复用 CLI 或 Desktop 原生 OAuth 凭据；不要无参数运行并展示其认证头。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        sys.exit(f"安装未完成：{error}")
