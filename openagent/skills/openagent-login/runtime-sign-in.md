# OpenAgent runtime sign-in

## When to use

Use this only after an OpenAgent Tool or the Host explicitly reports missing or expired OpenAgent authentication, such as `MCP_AUTH_REQUIRED` or `MCP_TOKEN_INVALID`. A bare HTTP status, missing tool, insufficient scope, business error, or network failure is not enough. Do not check login before normal calls. Anonymous search, guide, and selection calls stay anonymous unless their supplied credentials are explicitly rejected.

This takes priority over the caller's failure, fallback, and completion rules. Headless or delegated calls return the trusted authentication failure to their caller; that caller owns the single login flow and user messages. This does not handle App-only tools.

## Flow and messages

Use `display_locale`; if unset, choose explicit preference > trusted Host locale > conversation language > `en-US`. Show only the matching column, without workflow labels.

| State | zh-CN | en-US |
| --- | --- | --- |
| Starting login | 需要登录 OpenAgent 才能继续。正在打开登录页面… | Please sign in to OpenAgent to continue. Opening the sign-in page… |
| Page opened, still waiting | 请在打开的页面中登录 OpenAgent… | Please sign in to OpenAgent in the page that opened… |
| Authorization confirmed | 已登录 OpenAgent | Signed in to OpenAgent |
| Timed out | 还未完成登录。回复“继续登录”，我会重新打开登录页面。 | Sign-in is not complete yet. Reply ‘continue sign-in’ and I will reopen the sign-in page. |

1. Use the login path below for the actual failing connection. If the Host or this conversation already has a login in progress, wait using the same process or session handle; do not start another or repeat its messages, even if the user says "continue sign-in" while it is pending. If the previous attempt's state cannot be confirmed, report that uncertainty and do not start another attempt.
2. Send the starting message immediately before launching login once. Keep and wait on the same process. Only the selected CLI, helper, or Host authentication action may open the OAuth page. Do not additionally use `open`, `start`, `Start-Process`, `xdg-open`, browser tools, or an in-app browser to open it. A printed OAuth URL alone does not prove opening and must never be used to open another page. Show the waiting message only after confirmed opening and while authorization is pending. These opening restrictions apply only to OAuth pages; normal discovery, selection, and result-page handoffs are unchanged.
3. Confirm this attempt's authorization callback and successful token exchange, then show the success message and perform the configuration check below. Report any verification failure separately. Configuration verification is not business success.
4. Cancellation, denial, trusted page-closure reports, opening failure, login failure, or authorization timeout ends the attempt without automatic retry. A short tool wait, a still-running result, or no new output is not an OAuth timeout; keep waiting on the same attempt. Use the fixed timeout message only when the login entry explicitly reports authorization timeout. If page closure is not observable, wait for the attempt's bounded outcome instead of claiming closure. Start one fresh attempt only after confirming the previous process or session has ended and the user explicitly asks to continue sign-in again. Never terminate or abandon the old attempt merely to enable a retry.

## Login

Choose the actual failing connection; a Code tab alone does not identify it. CLI plugin OAuth and Desktop Connector credentials are separate.

### CLI plugin MCP

For the terminal Claude Code plugin connection, confirm support with `claude mcp login --help` and check `claude mcp get plugin:openagent:openagent`. Keep the existing endpoint. Run `claude mcp login plugin:openagent:openagent` once with a PTY and wait for its callback and successful exit. Then use `mcp get` again to verify the same connection. `Connected` alone is not authorization confirmation.

### Desktop managed Connector

This path requires command access to the host Mac and the installed `~/Library/Application Support/OpenAgent/Claude/openagent-connector-auth.py`. If unavailable, use an explicitly exposed Host authentication action for this Connector or report that automatic sign-in is unavailable; do not switch to CLI OAuth.

Resolve `rel` of `https://github.com/openagent-org/claude-plugin.git` to a full 40-character commit SHA, or reuse the official source and SHA already retained for this loading attempt. Download `https://raw.githubusercontent.com/openagent-org/claude-plugin/<SHA>/openagent-connector-auth.py` into a private temporary directory with `curl --fail --location --silent --show-error --proto '=https' --proto-redir '=https'`. The fallback repository is `https://gitee.com/openagent-org/claude-plugin.git`; its corresponding file is `https://gitee.com/openagent-org/claude-plugin/raw/<SHA>/openagent-connector-auth.py`. An existing valid official source may continue without forcing a switch to GitHub; when starting from a previously installed Gitee source, the other official source is the fallback. Never switch back after this loading attempt has used its one fallback.

Only DNS, connection, timeout, interrupted-transfer, or HTTP 5xx failures allow the assistant to try the fallback once. If initial resolution failed before any SHA was obtained, resolve the initial SHA there. Once obtained, retain the same SHA and path; never resolve another `rel` after a download failure. Keep the selected source and public SHA in the conversation instead of relying on shell variables across command calls. Stop on fallback failure, permission or approval denial, certificate errors, HTTP 401/403/404/429/451, or digest, syntax, execution, or OAuth errors. Do not retry outside the sandbox to bypass a denied permission or add another download attempt.

After the complete download, validate Python syntax without execution (for example, `ast.parse`). Only then run `python3 "<downloaded-helper>" reauthorize` once. It uses the installed helper's lock, existing registration, and Keychain; it does not reinstall the Connector. Never pipe a download into execution or switch sources after execution failed or its outcome became unknown. Retain the temporary copy through the explicit `status` check below, then remove it.

- `SIGN_IN_OPENED`: the page was opened; show the waiting message only while authorization is pending.
- `SIGN_IN_AUTHORIZED`: this attempt's callback and token exchange succeeded; show the success message.
- `SIGN_IN_CANCELLED` / `SIGN_IN_TIMED_OUT`: stop and use the corresponding outcome above.

After success, run the downloaded helper's explicit `status` command. Check only the current Connector's endpoint, enabled state, and configured helper path through safe Host metadata; report unavailable or failed verification. `status` is a local credential check, not proof that Desktop has reloaded the connection. Never call the helper without a subcommand, read Keychain credentials, or use a business tool to verify login.
