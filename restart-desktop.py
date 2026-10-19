#!/usr/bin/env python3
"""由已获准的 macOS 沙箱外命令提交一次重启；不修改权限或代替 OAuth。"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlencode


APP = Path("/Applications/Claude.app")
BUNDLE_ID = "com.anthropic.claudefordesktop"
LABEL = "com.openagent.claude-install-restart"


def read_text(path):
    """只读本用户普通文件，拒绝链接、特殊文件与过大的宿主状态。"""
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "r") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 10 * 1024 * 1024:
            raise ValueError("不是可安全读取的本机普通文件")
        return stream.read()


def read_json(path):
    value = json.loads(read_text(path))
    if not isinstance(value, dict):
        raise ValueError("本机状态不是 JSON 对象")
    return value


def plain_path(path):
    """只读宿主状态不能经过符号链接，避免读取别的配置或用户文件。"""
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("本机状态路径不能经过符号链接")
    return path


def completed_turns(session):
    # 首次成功之前原生 serializer 可以省略该可选字段。
    value = session.get("completedTurns", 0)
    if type(value) is not int or value < 0:
        raise ValueError("完成计数无效")
    return value


def current_bash(config_dir, session_id):
    """定位未返回的 Bash，并沿父链收集同一输入轮的 assistant；不输出正文。"""
    paths = list((config_dir / "projects").glob(f"*/{session_id}.jsonl"))
    if len(paths) != 1:
        raise ValueError("无法唯一定位当前 CLI 会话记录")
    pending = {}
    events = {}
    for line in read_text(plain_path(paths[0])).splitlines():
        event = json.loads(line)
        if event.get("sessionId") != session_id or event.get("isSidechain"):
            continue
        event_id = event.get("uuid")
        if event_id:
            if event_id in events:
                raise ValueError("会话记录包含重复 UUID")
            events[event_id] = event
        content = event.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if event.get("type") == "assistant" and block.get("type") == "tool_use" and block.get("name") == "Bash":
                pending[block["id"]] = event["uuid"]
            elif event.get("type") == "user" and block.get("type") == "tool_result":
                pending.pop(block.get("tool_use_id"), None)
    if not pending:
        return None  # 当前 Bash 可以先开始执行，再写入 transcript；由调用方有界等待。
    if len(pending) != 1:
        raise ValueError("无法唯一定位当前尚未返回的 Bash 调用")
    cursor = next(iter(pending.values()))
    anchors = {}
    visited = set()
    while cursor in events and cursor not in visited:
        visited.add(cursor)
        event = events[cursor]
        if event.get("parent_tool_use_id"):
            raise ValueError("不能从子代理安排桌面重启")
        content = event.get("message", {}).get("content", [])
        is_result = isinstance(content, list) and any(
            isinstance(block, dict) and block.get("type") == "tool_result" for block in content)
        if event.get("type") == "user" and not is_result:
            return anchors
        if event.get("type") == "assistant":
            anchors[cursor] = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).timestamp() * 1000
        cursor = event.get("parentUuid")
    raise ValueError("无法确认当前输入轮的完整消息分支")


def capture_turn(executable, old_pids):
    """在本次 Bash 返回前冻结新鲜计数，避免上一轮延迟落盘造成提前退出。"""
    cli_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", cli_id):
        raise ValueError("必须从当前 Claude Code 会话的 Bash 调用")
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).expanduser()
    if not config_dir.is_absolute():
        raise ValueError("Claude 配置目录必须为绝对路径")
    candidates = []
    for profile in ("Claude", "Claude-3p"):
        root = Path.home() / "Library/Application Support" / profile
        for path in (root / "claude-code-sessions").glob("*/*/local_*.json"):
            if read_json(plain_path(path)).get("cliSessionId") == cli_id:
                candidates.append((path, root))
    if len(candidates) != 1:
        raise ValueError("无法唯一映射当前 Desktop 会话")
    path, profile = candidates[0]
    started = time.time() * 1000

    def fresh_snapshot():
        if app_pids(executable) != old_pids:
            raise RuntimeError("取得完成基线前 Claude 进程已变化")
        anchors = current_bash(config_dir, cli_id)
        if anchors is None:
            return None
        data = read_json(path)
        if data.get("cliSessionId") != cli_id or data.get("sessionId") != path.stem:
            raise ValueError("会话映射已变化")
        activity = data.get("lastActivityAt")
        anchor_time = anchors.get(data.get("lastAssistantUuid"))
        if anchor_time is None or type(activity) not in (int, float):
            return None
        if activity < anchor_time:
            return None
        return data

    session = wait_for(fresh_snapshot, 15)
    return {"session_file": str(path), "cli_session_id": cli_id, "session_id": path.stem,
            "completed_turns": completed_turns(session), "requested_at": started,
            "profile_dir": str(profile)}


def wait_for_turn(request, executable):
    """后台只等本次基线增长；旧 PID 或映射变化、新错误、计数回退均不重启。"""
    while True:
        if app_pids(executable) != set(request["old_pids"]):
            raise RuntimeError("等待期间 Claude 进程已变化")
        session = read_json(plain_path(Path(request["session_file"])))
        if session.get("cliSessionId") != request["cli_session_id"] or session.get("sessionId") != request["session_id"]:
            raise ValueError("等待期间会话映射已变化")
        errors = (session.get("errorAt"), (session.get("priorErrorMark") or {}).get("at"),
                  session.get("interruptedByQuitAt"))
        if any(isinstance(value, (int, float)) and value >= request["requested_at"] for value in errors):
            raise RuntimeError("本轮出现错误或中断，停止重启")
        count = completed_turns(session)
        if count < request["completed_turns"]:
            raise ValueError("完成计数回退")
        if count > request["completed_turns"]:
            return
        time.sleep(1)


def prefill_url(request):
    """只读核对深链政策；仅编码提示语，避免触发外部指定目录的额外确认。"""
    profile = plain_path(Path(request["profile_dir"]))
    library = profile / "configLibrary"
    if library.exists():
        applied = read_json(plain_path(library / "_meta.json")).get("appliedId")
        if not isinstance(applied, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", applied):
            raise ValueError("不能确认当前 3P 策略")
        policy = read_json(plain_path(library / f"{applied}.json"))
        if policy.get("disableDeepLinkRegistration") is True or policy.get("disableDesktopLocalSessions") is True:
            raise ValueError("当前策略禁止 Code 深链预填")
    return "claude://code/new?" + urlencode({"q": request["message"]}, quote_via=quote)


def prefill_prompt(request):
    """新 PID 确认后仅交接一次原生草稿深链；正文走 stdin，系统接受不代表显示成功。"""
    url = prefill_url(request)
    script = f"""ObjC.import('AppKit');
const url = $.NSURL.URLWithString({json.dumps(url)});
const application = $.NSWorkspace.sharedWorkspace.URLForApplicationToOpenURL(url);
if (ObjC.unwrap(application.path) !== {json.dumps(str(APP))}) {{
    throw new Error('Unexpected Claude URL handler');
}}
if (!$.NSWorkspace.sharedWorkspace.openURL(url)) {{
    throw new Error('Claude URL handoff failed');
}}
"""
    run(["/usr/bin/osascript", "-l", "JavaScript", "-"], input=script, check=True)


def run(args, **kwargs):
    """只执行固定生命周期命令，捕获输出，不把宿主日志写入回执。"""
    return subprocess.run(args, text=True, capture_output=True, timeout=15, **kwargs)


def app_executable():
    """只接受标准安装位置的 Claude，拒绝未知应用。"""
    with (APP / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    if info.get("CFBundleIdentifier") != BUNDLE_ID:
        raise ValueError("目标不是 Claude Desktop")
    executable = APP / "Contents/MacOS" / info["CFBundleExecutable"]
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Claude 主程序不可执行")
    return str(executable)


def app_pids(executable):
    """按完整主程序路径识别进程，排除 CLI 和 Helper。"""
    result = run(["/bin/ps", "-axo", "pid=,comm="], check=True)
    pids = set()
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) == 2 and fields[1] == executable:
            pids.add(int(fields[0]))
    return pids


def save(state_dir, state, **fields):
    """原子写入阶段、进程号与预填状态；不记录指定内容或登录数据。"""
    receipt = {"state": state, "oauth": "pending_verification", **fields}
    temporary = state_dir / "status.tmp"
    temporary.write_text(json.dumps(receipt, ensure_ascii=False) + "\n")
    temporary.chmod(0o600)
    temporary.replace(state_dir / "status.json")
    return receipt


def wait_for(probe, timeout):
    """有界等待，超时保留失败阶段，不强制杀进程或自动重复重启。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(0.5)
    raise TimeoutError("等待 Claude 生命周期状态超时")


def restart(state_dir):
    """独立等待完成计数；正常重启且确认新 PID 后预填草稿，由用户主动发送。"""
    stage = "preflight"
    delivery = {}
    processes = {}
    try:
        request = read_json(state_dir / "request.json")
        executable = app_executable()
        old_pids = set(request["old_pids"])
        processes["old_pids"] = sorted(old_pids)
        if "message" in request:
            delivery = {"prompt_prefill": "not_requested", "prompt_delivery": "not_sent"}
            prefill_url(request)
        stage = "waiting_for_turn"
        save(state_dir, stage, **processes, **delivery)
        wait_for_turn(request, executable)
        if app_pids(executable) != old_pids:
            raise RuntimeError("提交后 Claude 进程已变化，停止重复重启")
        stage = "quitting"
        save(state_dir, stage, **processes, **delivery)
        run(["/usr/bin/osascript", "-e", f'tell application "{APP}" to quit'], check=True)
        wait_for(lambda: not app_pids(executable), 60)
        stage = "launching"
        save(state_dir, stage, **processes, **delivery)
        if app_pids(executable):
            raise RuntimeError("应用已被其他操作打开，停止重复启动")
        run(["/usr/bin/open", "-a", str(APP)], check=True)
        new_pids = wait_for(lambda: app_pids(executable) - old_pids, 45)
        processes["new_pids"] = sorted(new_pids)
        if "message" in request:
            stage = "prefilling"
            delivery["prompt_prefill"] = "pending_verification"
            save(state_dir, stage, **processes, **delivery)
            prefill_prompt(request)
            delivery["prompt_prefill"] = "requested"
        save(state_dir, "restarted", **processes, **delivery)
    except Exception as error:
        save(state_dir, "failed", stage=stage, error_type=type(error).__name__, **processes, **delivery)
    finally:
        # 仅清理本次 worker 和请求。保留 status.json 供恢复后的会话读取。
        (state_dir / "worker.py").unlink(missing_ok=True)
        (state_dir / "request.json").unlink(missing_ok=True)
        # remove 可能结束当前 worker，必须最后执行；不注册登录自启。
        run(["/bin/launchctl", "remove", LABEL])


def schedule(message_file=None):
    """提交一次性用户任务；由宿主批准沙箱外执行，本脚本不尝试逃逸。"""
    if sys.platform != "darwin":
        raise ValueError("仅支持用户本机 macOS")
    executable = app_executable()
    old_pids = app_pids(executable)
    if len(old_pids) != 1:
        raise ValueError("必须恰有一个正在运行的标准 Claude Desktop 主进程")
    if run(["/bin/launchctl", "list", LABEL]).returncode == 0:
        raise ValueError("已有重启任务；先读取其回执，不重复提交")
    request_data = {"old_pids": sorted(old_pids)}
    if message_file is not None:
        message_file = Path(message_file)
        if not message_file.is_absolute():
            raise ValueError("指定内容 JSON 必须为绝对路径")
        message = read_json(message_file).get("message")
        if not isinstance(message, str) or not message.strip() or len(message.encode("utf-16-le")) // 2 > 14336:
            raise ValueError("指定内容必须为非空且不超过 14,336 个 UTF-16 code units 的字符串")
        request_data["message"] = message
    request_data.update(capture_turn(executable, old_pids))
    if "message" in request_data:
        prefill_url(request_data)
    # 不使用可能随 Claude 会话退出而清理的 TMPDIR。
    state_dir = Path(tempfile.mkdtemp(prefix="openagent-claude-restart-", dir="/private/tmp"))
    worker = state_dir / "worker.py"
    shutil.copyfile(Path(__file__), worker)
    worker.chmod(0o600)
    request = state_dir / "request.json"
    request.write_text(json.dumps(request_data, ensure_ascii=False))
    request.chmod(0o600)
    receipt = save(state_dir, "scheduled", old_pids=sorted(old_pids))
    # 先输出路径，即便提交过程中当前会话中断，用户仍可查结果。
    print(json.dumps({**receipt, "receipt": str(state_dir / "status.json")}, ensure_ascii=False), flush=True)
    try:
        run(["/bin/launchctl", "submit", "-l", LABEL, "--",
             str(Path(sys.executable).resolve()), str(worker), "--worker", str(state_dir)], check=True)
    except subprocess.TimeoutExpired:
        # 提交结果未知时 worker 可能已运行；不得删除其文件或覆盖其阶段回执。
        raise
    except Exception as error:
        save(state_dir, "failed", stage="submit", error_type=type(error).__name__)
        worker.unlink(missing_ok=True)
        request.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--message-file", type=Path, help='UTF-8 JSON 绝对路径，格式为 {"message":"指定内容"}')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.worker:
            if args.message_file:
                raise ValueError("worker 不能重新指定消息")
            restart(args.worker)
        else:
            schedule(args.message_file)
    except Exception as error:
        # 不回显子命令输出或完整环境。
        phase = "重启执行未完成" if args.worker else "重启提交未确认"
        print(f"{phase}：{type(error).__name__}；请检查当前会话记录和本轮回执，勿自动重试。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
