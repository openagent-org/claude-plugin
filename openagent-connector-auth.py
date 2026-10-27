#!/usr/bin/env python3
# OpenAgent Claude headersHelper v1
"""Claude 3P 的独立 OAuth 客户端；凭据只保存在 macOS Keychain。"""

import base64
from contextlib import contextmanager
import ctypes
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import signal
import stat
import sys
import time
from urllib import error, parse, request


BASE_URL = "https://openagent.org"
RESOURCE = BASE_URL + "/mcp/v1/open-agent"
SCOPE = "agent.discover agent.invoke artifact.read"
DIRECTORY = Path.home() / "Library/Application Support/OpenAgent/Claude"
SERVICE = b"com.oasn.openagent.claude.headers-helper"
ACCOUNT = b"credentials"
MIN_LIFETIME = 360  # 宿主缓存 300 秒，另留 60 秒余量。
LOCK_TIMEOUT = 2
HTTP_TIMEOUT = 10
LOGIN_TIMEOUT = 300


class AuthError(Exception):
    """仅携带可安全展示的固定错误，不附加 URL、响应或凭据。"""


class InvalidRefreshGrant(AuthError):
    """仅代表服务端明确拒绝 refresh grant；只有显式 login 可恢复交互授权。"""


class KeychainStore:
    """单条 Generic Password 保存完整状态；禁止通过命令参数传递凭据。"""

    def __init__(self, interactive=False):
        if sys.platform != "darwin":
            raise AuthError("This authentication helper only supports macOS.")
        self.security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self.core = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        ptr = ctypes.c_void_p
        uint = ctypes.c_uint32
        signatures = {
            "SecKeychainSetUserInteractionAllowed": [ctypes.c_ubyte],
            "SecKeychainFindGenericPassword": [ptr, uint, ctypes.c_char_p, uint, ctypes.c_char_p,
                                               ctypes.POINTER(uint), ctypes.POINTER(ptr), ctypes.POINTER(ptr)],
            "SecKeychainItemFreeContent": [ptr, ptr],
            "SecKeychainItemModifyAttributesAndData": [ptr, ptr, uint, ctypes.c_char_p],
            "SecKeychainAddGenericPassword": [ptr, uint, ctypes.c_char_p, uint, ctypes.c_char_p,
                                              uint, ctypes.c_char_p, ctypes.POINTER(ptr)],
        }
        for name, arguments in signatures.items():
            function = getattr(self.security, name)
            function.argtypes = arguments
            function.restype = ctypes.c_int32
        self.core.CFRelease.argtypes = [ptr]
        self.core.CFRelease.restype = None
        self._check(self.security.SecKeychainSetUserInteractionAllowed(bool(interactive)))

    @staticmethod
    def _check(result):
        if result != 0:
            raise AuthError("Unable to access the helper's Keychain credentials. Run login in a terminal to check access permissions.")

    def _find(self):
        length, data, item = ctypes.c_uint32(), ctypes.c_void_p(), ctypes.c_void_p()
        result = self.security.SecKeychainFindGenericPassword(
            None, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT,
            ctypes.byref(length), ctypes.byref(data), ctypes.byref(item))
        if result == -25300:  # errSecItemNotFound
            return None, None
        self._check(result)
        try:
            value = ctypes.string_at(data, length.value)
        finally:
            self.security.SecKeychainItemFreeContent(None, data)
        return value, item

    def read(self):
        value, item = self._find()
        try:
            return {} if value is None else json.loads(value)
        except (ValueError, UnicodeError):
            raise AuthError("The helper's Keychain data has an invalid format. Reading stopped.") from None
        finally:
            if item:
                self.core.CFRelease(item)

    def write(self, value):
        encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
        _, item = self._find()
        try:
            if item:
                result = self.security.SecKeychainItemModifyAttributesAndData(item, None, len(encoded), encoded)
            else:
                result = self.security.SecKeychainAddGenericPassword(
                    None, len(SERVICE), SERVICE, len(ACCOUNT), ACCOUNT, len(encoded), encoded, None)
            self._check(result)
        finally:
            if item:
                self.core.CFRelease(item)


@contextmanager
def auth_lock(directory):
    """有限等待单写者；卸载期间目录消失或锁被替换时，不重新创建认证状态。"""
    directory = Path(directory).absolute()
    for component in (directory, *directory.parents):
        if stat.S_ISLNK(component.lstat().st_mode):
            raise AuthError("The helper installation path must not contain symbolic links.")
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise AuthError("The helper installation directory must be owned by the current user and have permissions set to 0700.")
    path = directory / ".auth.lock"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid() or opened.st_nlink != 1:
            raise AuthError("The authentication lock file is unsafe. Operation stopped.")
        os.fchmod(descriptor, 0o600)
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise AuthError("An authentication operation is already in progress. Try again later.") from None
                time.sleep(0.05)
        current = path.lstat()
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise AuthError("The authentication lock has been replaced. Reinstall the helper and try again.")
        # 卸载可能为保留用户文件而留下目录；已加载的旧进程不能因此重新建立授权。
        installed = (directory / "openagent-connector-auth.py").lstat()
        if (not stat.S_ISREG(installed.st_mode) or installed.st_uid != os.getuid()
                or installed.st_nlink != 1 or stat.S_IMODE(installed.st_mode) != 0o700):
            raise AuthError("The authentication helper has been uninstalled or its installation file is unsafe. Reinstall the helper.")
        yield
    finally:
        os.close(descriptor)


@contextmanager
def header_budget():
    """自动取头最多运行 25 秒，保留宿主 30 秒期限的退出余量。"""
    def expired(_signal, _frame):
        raise AuthError("Retrieving authentication headers timed out. Try again later.")

    previous_handler = signal.signal(signal.SIGALRM, expired)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 25)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def post_json(path, body, is_json=False):
    """固定 REL 端点，单次有界请求；拒绝重定向，不展示服务端正文。"""
    if path not in ("/owner-oauth/register", "/owner-oauth/token"):
        raise AuthError("Unsupported authentication endpoint.")
    content_type = "application/json" if is_json else "application/x-www-form-urlencoded"
    encoded = json.dumps(body).encode() if is_json else parse.urlencode(body).encode()
    message = request.Request(BASE_URL + path, data=encoded, method="POST",
                              headers={"Content-Type": content_type, "Accept": "application/json"})
    try:
        with request.build_opener(NoRedirect()).open(message, timeout=HTTP_TIMEOUT) as response:
            if response.status not in (200, 201):
                raise AuthError("The authentication service returned an unexpected status. Run login again.")
            content = response.read(131073)
            if len(content) > 131072:
                raise AuthError("The authentication service response exceeds the size limit.")
            result = json.loads(content)
    except error.HTTPError as exception:
        invalid_grant = False
        try:
            if (path == "/owner-oauth/token" and body.get("grant_type") == "refresh_token"
                    and exception.code == 400):
                content = exception.read(4097)
                result = json.loads(content) if len(content) <= 4096 else None
                invalid_grant = isinstance(result, dict) and result.get("error") == "invalid_grant"
        except (OSError, ValueError):
            pass  # 未知或过大的错误正文不能被当成凭据已失效。
        finally:
            exception.close()
        if invalid_grant:
            raise InvalidRefreshGrant("Saved authorization is no longer valid. Run login in a terminal to authorize again.") from None
        raise AuthError("The authentication request failed. Check your network connection and run login again if needed.") from None
    except (error.URLError, OSError, ValueError):
        raise AuthError("The authentication request failed. Check your network connection and run login again if needed.") from None
    if not isinstance(result, dict):
        raise AuthError("The authentication service response has an invalid format.")
    return result


def valid_scope(value):
    return isinstance(value, str) and set(value.split()) == set(SCOPE.split())


def registration(state):
    """校验注册元数据，不能因损坏而静默注册新的客户端身份。"""
    if not isinstance(state, dict):
        raise AuthError("The helper's authentication state has an invalid format.")
    if not state:
        return None
    if (state.get("version") != 1 or not isinstance(state.get("clientId"), str)
            or not state["clientId"].startswith("mcp_client_")
            or type(state.get("callbackPort")) is not int or not 1 <= state["callbackPort"] <= 65535):
        raise AuthError("The helper's OAuth registration data is invalid. Operation stopped.")
    return state


def validate_tokens(response, now):
    """完整校验换取结果后再写 Keychain；静态兼容响应从 JWT 取得实际到期时间。"""
    if (response.get("token_type", "").lower() != "bearer" or response.get("resource") != RESOURCE
            or not valid_scope(response.get("scope"))):
        raise AuthError("The OAuth token's resource or scope does not match.")
    for field in ("access_token", "refresh_token"):
        value = response.get(field)
        if not isinstance(value, str) or not value or any(character.isspace() for character in value):
            raise AuthError("The OAuth token has an invalid format.")
    try:
        parts = response["access_token"].split(".")
        if len(parts) != 3:
            raise ValueError()
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        expiry = claims["exp"]
        if type(expiry) not in (int, float) or not math.isfinite(expiry) or claims.get("aud") != RESOURCE:
            raise ValueError()
        lifetime = response.get("expires_in")
        if lifetime is not None:
            if type(lifetime) not in (int, float) or not math.isfinite(lifetime) or lifetime <= 0:
                raise ValueError()
            expiry = min(expiry, now + lifetime)
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise AuthError("The OAuth token's expiration data is invalid.") from None
    return {"access_token": response["access_token"], "refresh_token": response["refresh_token"],
            "expires_at": expiry, "scope": SCOPE, "resource": RESOURCE}


def usable_tokens(tokens, now):
    return (isinstance(tokens, dict) and tokens.get("resource") == RESOURCE and valid_scope(tokens.get("scope"))
            and isinstance(tokens.get("access_token"), str) and bool(tokens["access_token"])
            and not any(character.isspace() for character in tokens["access_token"])
            and type(tokens.get("expires_at")) in (int, float) and math.isfinite(tokens["expires_at"])
            and tokens["expires_at"] - now > MIN_LIFETIME)


def get_headers(store):
    state = registration(store.read())
    tokens = state.get("tokens") if state else None
    if not isinstance(tokens, dict) or not isinstance(tokens.get("refresh_token"), str) or not tokens["refresh_token"]:
        raise AuthError("Authorization is required. Run login in a terminal first.")
    if (tokens.get("resource") != RESOURCE or not valid_scope(tokens.get("scope"))
            or any(character.isspace() for character in tokens["refresh_token"])):
        raise AuthError("Saved credentials have an invalid resource or scope. Run login again.")
    if not usable_tokens(tokens, time.time()):
        # 请求开始时间更保守，避免把网络耗时错误计入 token 剩余寿命。
        started = time.time()
        response = post_json("/owner-oauth/token", {
            "grant_type": "refresh_token", "client_id": state["clientId"],
            "refresh_token": tokens["refresh_token"], "resource": RESOURCE, "scope": SCOPE})
        tokens = validate_tokens(response, started)
        state["tokens"] = tokens
        # 即使新 access token 太短，也必须先保留已轮换的 refresh token；失败时不返回头。
        store.write(state)
    if not usable_tokens(tokens, time.time()):
        raise AuthError("The OAuth token expires too soon. Run login again.")
    return {"Authorization": "Bearer " + tokens["access_token"]}


def open_browser(url):
    """直接调用 LaunchServices，授权 URL 不进入子进程参数或脚本文件。"""
    core = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    services = ctypes.CDLL("/System/Library/Frameworks/CoreServices.framework/CoreServices")
    pointer = ctypes.c_void_p
    core.CFStringCreateWithCString.argtypes = [pointer, ctypes.c_char_p, ctypes.c_uint32]
    core.CFStringCreateWithCString.restype = pointer
    core.CFURLCreateWithString.argtypes = [pointer, pointer, pointer]
    core.CFURLCreateWithString.restype = pointer
    core.CFRelease.argtypes = [pointer]
    core.CFRelease.restype = None
    services.LSOpenCFURLRef.argtypes = [pointer, ctypes.POINTER(pointer)]
    services.LSOpenCFURLRef.restype = ctypes.c_int32
    text = core.CFStringCreateWithCString(None, url.encode(), 0x08000100)
    address = core.CFURLCreateWithString(None, text, None) if text else None
    try:
        if not address or services.LSOpenCFURLRef(address, None) != 0:
            raise AuthError("Unable to open the system browser. Check your default browser and run login again.")
    finally:
        if address:
            core.CFRelease(address)
        if text:
            core.CFRelease(text)


def callback_handler(expected_state, result):
    """回调只接受匹配 state 的单次 code；HTTP 日志禁用，避免记录授权码。"""
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            parsed = parse.urlsplit(self.path)
            values = parse.parse_qs(parsed.query, keep_blank_values=True)
            matches = (parsed.path == "/callback" and not parsed.fragment
                       and len(values.get("state", [])) == 1
                       and secrets.compare_digest(values["state"][0].encode(), expected_state.encode())
                       and all(len(items) == 1 for items in values.values())
                       and ("resource" not in values or values["resource"][0] == RESOURCE))
            valid = matches and bool(values.get("code", [""])[0]) and "error" not in values
            if valid:
                result["code"] = values["code"][0]
            elif matches and "error" in values:
                result["error"] = True
                result["cancelled"] = values["error"][0] == "access_denied"
            body = ("Authorization callback received. You can close this page." if valid else "Authorization callback is invalid or was canceled.").encode()
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Callback


class CallbackServer(HTTPServer):
    """限制本机连接读超时，并避免异常日志带入回调内容。"""

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address

    def handle_error(self, *_args):
        pass


def login(store, reauthorize=False):
    """调用方持锁；正常登录先复用凭据，明确重新授权时始终等待本次回调。"""
    saved = registration(store.read())
    if not reauthorize and saved and "tokens" in saved:
        try:
            get_headers(store)
            return
        except InvalidRefreshGrant:
            pass
    state = dict(saved) if saved else {}
    nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    result = {}
    # 先监听再注册/打开浏览器，保证注册回调端口在本轮授权期间属于当前进程。
    with CallbackServer(("127.0.0.1", state.get("callbackPort", 0)), callback_handler(nonce, result)) as server:
        port = server.server_address[1]
        callback = f"http://127.0.0.1:{port}/callback"
        if not state:
            metadata = {"client_name": "OpenAgent Claude headersHelper", "client_source": "claude", "redirect_uris": [callback],
                        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
                        "token_endpoint_auth_method": "none", "scope": SCOPE}
            registered = post_json("/owner-oauth/register", metadata, is_json=True)
            candidate = {"version": 1, "clientId": registered.get("client_id"), "callbackPort": port}
            registration(candidate)
            if (registered.get("redirect_uris") != [callback] or not valid_scope(registered.get("scope"))
                    or registered.get("token_endpoint_auth_method") != "none"):
                raise AuthError("The OAuth client registration response does not match the request.")
            state = candidate
            store.write(state)  # 后续授权取消仍保留同一客户端，避免重复创建身份。
        parameters = {"response_type": "code", "client_id": state["clientId"], "redirect_uri": callback,
                      "resource": RESOURCE, "scope": SCOPE, "state": nonce,
                      "code_challenge": challenge, "code_challenge_method": "S256"}
        open_browser(BASE_URL + "/owner-oauth/authorize?" + parse.urlencode(parameters))
        if reauthorize:
            print("SIGN_IN_OPENED", flush=True)
        server.timeout = 1
        deadline = time.monotonic() + LOGIN_TIMEOUT
        while not result and time.monotonic() < deadline:
            server.handle_request()
        if "code" not in result:
            if reauthorize:
                if result.get("cancelled"):
                    print("SIGN_IN_CANCELLED", flush=True)
                elif not result:
                    print("SIGN_IN_TIMED_OUT", flush=True)
                raise AuthError("Authorization was not completed.")
            raise AuthError("Authorization was not completed. Registration data has been retained; run login again.")
        started = time.time()
        response = post_json("/owner-oauth/token", {
            "grant_type": "authorization_code", "client_id": state["clientId"], "redirect_uri": callback,
            "resource": RESOURCE, "code": result["code"], "code_verifier": verifier})
        state["tokens"] = validate_tokens(response, started)
        if not reauthorize:
            store.write(state)
        if not usable_tokens(state["tokens"], time.time()):
            raise AuthError("The OAuth token expires too soon to meet the Connector cache lifetime requirement.")
        if reauthorize:
            store.write(state)


def local_status(store):
    state = registration(store.read())
    tokens = state.get("tokens") if state else None
    return {"registered": bool(state), "credentials_present": isinstance(tokens, dict),
            "access_token_usable": usable_tokens(tokens, time.time()),
            "verification": "local_only"}


def run(command, store, directory):
    with auth_lock(directory):
        if command == "headers":
            print(json.dumps(get_headers(store), separators=(",", ":")))
        elif command == "login":
            login(store)
            print("OpenAgent helper authorization is ready. Start or restart Claude as described in the installation instructions.")
        elif command == "reauthorize":
            login(store, reauthorize=True)
            print("SIGN_IN_AUTHORIZED", flush=True)
        elif command == "status":
            print(json.dumps(local_status(store), separators=(",", ":")))
        elif command == "logout":
            state = registration(store.read())
            if state and "tokens" in state:
                state.pop("tokens")
                store.write(state)
            print("Local helper credentials cleared; client registration retained. Remote authorization has not been revoked.")


def main(argv=None, store=None, directory=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments in (["--help"], ["-h"]):
        print("Usage: openagent-connector-auth.py [login|reauthorize|status|logout]. Run without arguments for headersHelper.")
        return 0
    if len(arguments) > 1 or (arguments and arguments[0] not in ("login", "reauthorize", "status", "logout")):
        print("Error: Only login, reauthorize, status, logout, or no arguments are supported.", file=sys.stderr)
        return 2
    command = arguments[0] if arguments else "headers"
    try:
        if command == "headers":
            with header_budget():
                run(command, store or KeychainStore(), directory or DIRECTORY)
        else:
            run(command, store or KeychainStore(interactive=command in ("login", "reauthorize")), directory or DIRECTORY)
        return 0
    except AuthError as exception:
        print("Error: " + str(exception), file=sys.stderr)
    except KeyboardInterrupt:
        if command == "reauthorize":
            print("SIGN_IN_CANCELLED", flush=True)
        print("Authorization canceled.", file=sys.stderr)
        return 130
    except Exception:
        # ctypes、文件系统和回调解析的异常也不能把秘密带进 traceback。
        print("Error: Authentication failed. Check the helper installation, Keychain, and network connection, then try again.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
