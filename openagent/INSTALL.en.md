# Install OpenAgent in Claude

This document is for the Claude model performing the installation. Before running any installation command, confirm the client hosting the current session, the session mode, and the MCP source. For another client, return to the [OpenAgent installation hub](https://openagent.org/plugin) and find its installation link. If these cannot be confirmed, stop and ask the user.

Attachment uploads require Node.js 20+. The plugin includes the fixed COS Node.js SDK and its dependencies in the run Skill’s `scripts/cos_sdk.cjs.gz` bundle, installed alongside `scripts/cos_upload.cjs` and `scripts/cos_sdk.lock.json`. On first use, the script verifies and extracts the bundle offline into `scripts/.cos-sdk/node_modules/<bundle SHA-256>/cos_sdk.cjs`. Later uses verify SHA-256 before reusing the cache; a missing or damaged cache, or an updated bundle, triggers extraction automatically. The cache remains after exit. The current user must be able to write to `scripts/`. Upload checkpoint cleanup does not load the SDK. The plugin does not search for a host SDK, run `npm`, or download dependencies. Stop and repair the plugin installation if installation files are missing or bundle verification fails.

## Before installation: check the session mode

**If the current session is Cowork:** Do not run the installation commands below, register an OAuth client, modify configuration, or restart the app. Show the following notice and the complete copyable message below, then end this installation branch:

> This session cannot perform this local installation. Switch to Code in Claude, select Local and a local folder, then send the installation request below in a new session.

```text
Read https://openagent.org/claude, first confirm that this is a local macOS Claude Code session with Local selected, then follow the guide to actually install and verify OpenAgent.
```

If the user explicitly provided an `agent_id`, Agent name, or business request, append those details verbatim as a separate paragraph in the same copyable message; otherwise, do not invent them. Do not replace the installation request with the already-installed startup message from section 4, or claim that installation or automatic switching has occurred. Ordinary 3P Cowork currently has no available tool for automatic Code handoff. Do not guess tools, change hidden flags, call private IPC, or use scheduled tasks to simulate switching before installation.

**If the current session is Code → Local:** Reconfirm that command tools run on the user's local Mac and that Claude 3P has completed **Configure Third-Party Inference**. Installation requires Python 3, Git, and a Claude CLI that supports plugin management. If the tools can only access an isolated Linux or remote environment, stop the local installation and use the local Code handoff notice and installation request above. Do not treat successful commands in an isolated environment as a successful local installation.

Proceed to section 1 only after confirming the local Code conditions above; stop installation for other modes or an unknown environment. After entering section 1, use only these fixed messages for user-visible progress updates; do not add a summary of installation steps. The host tools record commands and their results:

- At the start: "Installing OpenAgent..."
- When the plugin MCP or Connector helper login page opens and authorization is pending: "Please log in to OpenAgent on the page that opened..."
- When the current login command explicitly succeeds: "Logged in to OpenAgent."
- If the current login command times out: "Login is not complete yet. Reply 'continue login' and I will reopen the login page." Start one new attempt for the corresponding login only after the user explicitly replies "continue login".
- Before submitting the restart task: "The installation steps are complete. After this turn ends, Claude will restart and fill the startup message into a new Code session for you to send."
- If any required step fails or its result is unknown, use the incomplete-installation template at the end to report the actual state. Do not use a success message.

## 1. Install the 3P MCP, plugin, and Skills

The `openagent:*` Skills or `mcp__openagent__*` tools already present in this conversation are only a loaded session snapshot, not proof that this installation is complete. CLI plugin registration, the Desktop 3P Connector, and managed plugins are separate. Existing tools in one of them do not justify skipping installation, login, or this installation's restart.

First display the installation progress message above. Then check dependencies and existing installation state one command at a time using the local command tool. Except for eligible read or download failures handled below, if any command fails, record that step's result and stop; do not continue with subsequent installation commands:

```bash
python3 --version
git --version
claude plugin --help
claude plugin marketplace list
claude plugin list
```

Downloads prefer `https://github.com/openagent-org/claude-plugin.git` (`github`), with `https://gitee.com/openagent-org/claude-plugin.git` (`gitee`) as the fallback. The assistant selects the fallback once without asking the user to classify their network. Keep an existing valid official source instead of forcing it back to the preferred source; when starting from a previously installed Gitee source, the other official source is the fallback. Never switch back after this loading attempt has already used its one fallback. Only DNS, connection, timeout, interrupted-transfer, or HTTP 5xx failures permit one fallback attempt. Stop on permission or approval denial, certificate errors, HTTP 401/403/404/429/451, or digest, syntax, execution, or OAuth errors. Stop if the fallback also fails. The installer does not retry another source internally.

Before selecting a source, read only `source`, `url`, `ref`, and `installationPreference` for the OpenAgent Marketplace in the active 3P configuration; do not display the full configuration or inference credentials. Retain a valid, usable official source already registered there instead of resetting it because the example says `github`. Set `install_source` to the selected source and retain it for later commands; do not depend on shell variables surviving separate command calls. Download installation files directly from `rel`; Gitee Raw uses `https://gitee.com/openagent-org/claude-plugin/raw/rel/<path>`. Download both complete files into the temporary directory and validate syntax before executing the installer once. Only after the original command has ended and the installer is confirmed not to have run may an eligible download failure use the fallback to complete the downloads. Discard partial files without joining output. Never pipe a download into execution, use a command-failure pipeline to execute from another source, or rerun an execution whose result is unknown. Apply the same download-only rule to the restart below.

Next, download the [3P configuration script](https://github.com/openagent-org/claude-plugin/blob/rel/install-desktop-connector.py) and `openagent-connector-auth.py` from the selected official repository at `rel`. Pass `--ref rel` and the selected source to the installer and remove the temporary files when the command finishes:

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

The script persistently installs the helper from its own directory to `~/Library/Application Support/OpenAgent/Claude/openagent-connector-auth.py`, with an absolute shebang for the Python interpreter running the installer. An interpreter path containing whitespace causes an explicit failure; spaces in the helper path are supported. It then incrementally updates `managedMcpServers` and `allowedPluginMarketplaces` in the active 3P configuration. With `--ref rel`, the installer internally resolves the selected official source's current release and stores the full commit required by the host with `installationPreference: auto_install`; it never stores the branch name `rel` as an auto-install pin. New installations, old branch configurations, and older pinned versions update to the current release. Repeating the same version and source leaves the configuration unchanged. `--source` accepts only `github` or `gitee`; omitting it defaults to GitHub for a new installation and retains an existing valid source. Running the installer without `--ref` still preserves an existing valid pin. Only the exact GitHub and Gitee sources above are accepted; other same-name sources stop without being overwritten. For the OpenAgent Connector, it replaces native `oauth` with the absolute `headersHelper` path, `headersHelperTtlSec=300`, and `headersHelperRefreshBufferSec=60`, retaining `X-OASN-MCP-OAuth: required`, `X-OASN-MCP-Widget-Transport: claude-direct`, and `X-OASN-Client-Source: claude`. Omit `oauth`; do not set `oauth:false`. The installer neither registers an OAuth client nor obtains tokens; helper `login` does that in section 2. Configuration is backed up in the same directory before writing. Backups may contain inference credentials; do not upload them. Installer success proves that files and configuration were written, not that the running Claude has loaded the Connector or plugin.

Use the earlier `claude plugin marketplace list` result to check `openagent-claude`. If absent, use the selected source: `claude plugin marketplace add 'https://github.com/openagent-org/claude-plugin.git#rel'` or `claude plugin marketplace add 'https://gitee.com/openagent-org/claude-plugin.git#rel'`. An existing exact official GitHub or Gitee source on `rel` may continue without forcing a switch to GitHub. Migrate an older branch of either official source as described below; stop on other sources. Native CLI registration retains `#rel` for updates. Read back the actual official source, branch, and plugin installation and enabled state.

Use `claude plugin list` to check `openagent@openagent-claude`: run `claude plugin install openagent@openagent-claude --scope user` only if it is not installed; skip it if installed and enabled; if installed but disabled, stop and report that state rather than counting installation as complete. After each operation, read the corresponding list again to verify its result. Wait for the original Marketplace download command to finish; do not start duplicate installations concurrently. Only after the command has ended with an eligible download failure, reread Marketplace and plugin state before switching an exact official user-scope registration once using the steps below. Continue directly only when the registration matches the source selected for this attempt; if a switch has been selected and the source differs, follow the migration steps below. Stop if partial state or side effects are uncertain. Do not rerun completed configuration, sign-in, or restart steps. The plugin contains five Skills, with no separate copying required: `openagent-first-task-router`, `openagent-guide-agent`, `openagent-search-agent`, `openagent-run-agent`, and `openagent-query-account`.

Migration from an official source's older branch or this installation's download fallback changes only an exact official user-scope registration named `openagent-claude`. Legacy `master` must belong to the official GitHub or Gitee source above; a confirmed eligible download failure on `rel` may belong to the official GitHub or Gitee source above. Run `claude plugin marketplace remove openagent-claude --scope user`, then reread `claude plugin marketplace list`. Only after confirming removal, add the selected source using the command above, reread its source and `rel`. Stop if another scope still has that name; do not expand removal. Reread `claude plugin list`: install if missing, run `claude plugin update openagent@openagent-claude --scope user` if still installed and enabled, or stop if disabled. Stop and record each failure before applying the download-only recovery rule above. Continue from actual registration state without removing an already matching source again. Do not run the uninstaller, `mcp logout`, or clear OAuth configuration. Other same-name sources remain conflicts.

The target MCP must be `https://openagent.org/mcp/v1/open-agent`. The step 1 script accepts only this URL. A same-name Connector using another URL stops without configuration changes or authorization reuse. See the optional section at the end for terminal CLI plugin updates; they are not a prerequisite for Desktop 3P installation.

The plugin MCP and Desktop 3P Connector use independent clients and grants; never copy tokens between them. Desktop 3P installation completes only helper login in section 2 by default. Run the optional CLI login at the end only when the user needs OpenAgent in the terminal CLI. Plugin and Skills installation does not require CLI OAuth. The uninstaller recognizes only the current MCP URL and the official GitHub and Gitee sources above. It safely removes the dedicated helper, `.auth.lock`, and entire dedicated Keychain item while retaining unknown files. Neither uninstall nor helper logout revokes authorization remotely.

## 2. Log in to the Desktop Connector

First confirm that the command tool can retain and wait for the same process. The default installation runs only helper `login` and `status`, without CLI MCP login:

```bash
(
  set -e
  "$HOME/Library/Application Support/OpenAgent/Claude/openagent-connector-auth.py" login
  "$HOME/Library/Application Support/OpenAgent/Claude/openagent-connector-auth.py" status
)
```

Helper `login` first reuses existing credentials with sufficient permissions and validity, or refreshes them with the refresh token when renewal is needed. Browser authorization starts only when credentials have not been saved (first authorization or after `logout`), or refresh explicitly returns HTTP 400 `invalid_grant`. Corrupted existing credentials, resource or permission mismatches, network errors, and service failures preserve the existing state and report failure without registering again or automatically opening authorization. When authorization is needed, reuse a matching independent registration or register a public client for `agent.discover agent.invoke artifact.read`. The initial sign-in and consent still require the user. To switch accounts or force reauthorization, explicitly run helper `logout` followed by `login`.

Keep only one login process and wait for it to finish. Display the waiting message above only when a page actually opens; the user signs in to OpenAgent in the browser and confirms the permissions. Display the logged-in message only after the command explicitly succeeds. On cancellation, timeout, or failure, stop and use the corresponding template above. Do not retry concurrently, click Desktop's Connect, or collect authorization codes, callback URLs, or tokens. After installation, the same entry point can also be invoked as `python3 "$HOME/Library/Application Support/OpenAgent/Claude/openagent-connector-auth.py" login`. During routine no-argument invocations by Claude, the helper noninteractively reuses or refreshes existing credentials. If reauthorization is required, it returns an error without opening the browser.

All registration records, tokens, and expiry information are stored only in macOS Keychain (service `com.oasn.openagent.claude.headers-helper`, account `credentials`), with no token file on disk. The adjacent `.auth.lock` is only for mutual exclusion. `status` emits redacted state and does not prove that Desktop is connected. **The installation assistant must never invoke the helper without a subcommand**: that entry point is exclusively for Claude to read JSON Authorization headers and emits credentials. Do not use it for checks or read the Keychain item directly. `logout` clears only this helper's local tokens and retains its registration; it neither revokes authorization remotely nor affects plugin CLI login. See [Claude's official headersHelper documentation](https://claude.com/docs/third-party/claude-desktop/extensions#short-lived-credentials-with-a-headers-helper).

A zero exit code from `status` only confirms that the read completed. Before restarting, also require `registered`, `credentials_present`, and `access_token_usable` to all be `true`; otherwise stop and report the actual state. `verification=local_only` explicitly limits this to a local credential check.

## 3. Check and verify the 3P Connector

### Restart Claude outside the sandbox

After sections 1 and 2 have both succeeded, first generate the complete startup message using section 4. Use a file-writing tool to save it in a private local directory as a UTF-8 JSON file with mode 0600 and the structure `{"message":"complete startup message"}`. Use JSON serialization to preserve quotes, internal line breaks, and the user's original requirements. Do not interpolate the message into shell commands or write it to the repository or diagnostic output. The message must be nonempty and at most 14,336 UTF-16 code units. Longer messages are rejected before restart, never truncated. The script only URL-encodes the content; Claude may normalize characters and whitespace in its native composer, so the user must check it before sending. Replace `message_file` below with the file's actual absolute path; do not retain the example path or placeholders. Preserve installation progress, redacted helper login/status results, and the user's original requirements in the current conversation, then display the restart message above.

Run the command from the current Claude Code Bash tool, retaining the host-provided `CLAUDE_CODE_SESSION_ID`. The script uses it to uniquely associate this session and the unfinished Bash call. Stop if this context is missing; do not copy another session's ID or fabricate the variable in a regular terminal. Request **unsandboxed Bash execution** for this command only. If the actual Bash tool exposes `dangerouslyDisableSandbox`, set it to `true` in the tool-call arguments and follow the host's permission flow. It is neither a shell environment variable nor a Python argument. Use the host's execution status to confirm that the command runs outside the sandbox. If `sandbox.allowUnsandboxedCommands=false` or a managed policy blocks it, stop automatic restart and report that the user must quit and reopen the app normally; then apply section 5 before deciding on a manual message. Do not automatically change security settings, exempt all Python commands, or substitute `--dangerously-skip-permissions` for unsandboxed execution. See the [official Claude sandbox documentation](https://code.claude.com/docs/en/sandboxing).

Before execution, set `install_source` below to the actual source selected in section 1 and download the restart script from its `rel` branch. Apply section 1 only to download failures; never switch sources and rerun a restart that was submitted or has an unknown result.

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

The script supports only `/Applications/Claude.app`. The foreground process uniquely maps the current session metadata, then follows transcript `parentUuid` links from this unfinished Bash call to the main `user` message starting this input turn, excluding `tool_result` messages. The on-disk `lastAssistantUuid` may match any assistant already present on that same turn and branch; `lastActivityAt` in the same metadata snapshot must be no earlier than that assistant timestamp before its `completedTurns` becomes the baseline. If the current Bash call has not been persisted (zero unfinished calls), or the current turn metadata is not ready, the script rereads both within the same 15-second deadline. Multiple unfinished Bash calls, broken chains, cycles, duplicate UUIDs, subagent records, and corrupt records are rejected immediately. Timeout stops before worker creation, without falling back to an earlier turn, a summary, an old count, or a fixed delay. The assistant must not add `sleep` and retry. A one-time worker handed to the current user's macOS `launchd` enters `waiting_for_turn` and checks the count every second. Only a strict increase permits a normal Claude quit request; there is no fixed 5-second delay. A changed target PID or a new error stops the worker without force-killing or retrying. Existing normal quit protections still apply. If the host prohibits unsandboxed execution, do not use `launchd` to bypass it. If macOS requests permission to control Claude, follow the system permission flow.

Record the absolute `receipt` path printed by the command. The script copy and receipt are stored in a separate `/private/tmp/openagent-claude-restart-*` directory so that deleting the temporary download does not prevent restart. `scheduled` means only worker handoff, and `waiting_for_turn` means that the current turn has not finished; neither proves a restart. **After successful submission, end this installation turn normally. Do not poll the worker, wait for its terminal state, or continue installation tool calls in this same turn: that would prevent the turn from completing.** Save progress, tasks, and memories before submission; after successful submission, do not read the receipt or update tasks or memories. `重启提交未确认` means the foreground command did not confirm handoff, not that an executed restart failed. Check this call and any returned receipt without editing the script or adding a delay and retrying. The old three-minute terminal-state rule does not apply to `waiting_for_turn`. If submission fails or a later receipt shows `failed`, read `stage` and stop retrying. A submission timeout leaves the result unknown: retain any worker and receipt that may still be active, and do not resubmit. If Claude closed but did not reopen, the user must open it manually and return to this conversation.

After the old PID has completely disappeared, the worker opens Claude normally and confirms a new PID, then uses the native `claude://code/new?q=<message>` deep link to prefill a new Code composer. The link contains only `q`, without `folder`, and does not guarantee reuse of the installation session's directory. Before sending, the user must check or select Local and the target folder. Claude still asks for trust when an untrusted folder is selected. The user must click Send. The handoff uses macOS `NSWorkspace.openURL`, passing the content through standard input rather than process arguments and checking that the system handler is `/Applications/Claude.app` before opening. It requires no plugin hook and uses no macOS accessibility automation, System Events, clipboard, CDP, or private send interface. The script creates no Claude scheduled task and neither reads nor writes existing tasks or scheduling preferences. Managed `disableDeepLinkRegistration=true` or `disableDesktopLocalSessions=true` stops the flow without changing policy or bypassing directory trust. Standalone calls may omit `--message-file` to restart only; this installation flow passes the message from section 4.

After restart, first read this installation's `receipt`. Confirm a process restart only when `state=restarted` and distinct old and new PIDs are recorded. This does not prove that the composer displays the message, the Connector loaded, or OAuth succeeded. With a message, the receipt records `prompt_prefill=not_requested/pending_verification/requested` and `prompt_delivery=not_sent`. `prompt_prefill=requested` means only that the system accepted the deep link. On handoff failure or timeout, inspect the actual composer; do not retry, overwrite the user's draft, or send for them. `prompt_delivery=not_sent` records only that the script did not send; the user's later click does not update this receipt. Resume from the receipt check; do not rerun sections 1 and 2. Use section 5 to report or offer a message for manual entry. After confirming the terminal state, retaining redacted results, and checking that the worker has ended, remove only its remaining `status.json` and empty directory. Do not use wildcard cleanup across other tasks.

Accept only the `receipt` returned and recorded by this installation's restart command after sections 1 and 2 succeed. Reinstalling after an uninstall starts a new installation and requires one new restart submission after those sections succeed. Do not skip it based on a historical receipt, a restart earlier today, or the `custom3p-mcp-schemas.json` cache. The no-repeat rule above applies only when resuming an interrupted installation whose restart was already submitted. If the receipt cannot be tied to this installation, report the restart as unconfirmed and check this installation's submission record and active task before taking further action; do not blindly restart. If the user declines restart or permissions block it, report installation as incomplete.

### Verify the connection read-only after restart

Claude should obtain authorization headers automatically through the configured helper, without clicking **Connect**. After resuming, inspect the `openagent` Connector and tool connection state actually loaded by the current Desktop instance. Use authorized read-only interface tools or redacted state/logs from that client. Do not operate Connect or Disconnect, call private IPC, open remote-debugging ports, or fabricate authorization records. Without current Desktop connection evidence, use the incomplete-installation template and preserve the separate facts that configuration was written, helper login succeeded, and Desktop verification is pending. An old session's tool snapshot, CLI `Connected`, or helper `status` is not a substitute.

If the actual connection fails, first check whether the active configuration points to the fixed helper, native `oauth` has been removed, and the explicit `status` subcommand and client errors explain the state. Do not invoke the helper without a subcommand, copy tokens, repeat login, or reinstall. The receipt's `oauth=pending_verification` always means only "not yet verified" and cannot serve as authorization evidence. Any required browser authorization was completed before restart, or the helper reused or refreshed existing credentials. Subsequent credential reads and refreshes are noninteractive.

If `OAuth probe timeout after 10000ms` actually occurs, record the error and check the network path from the local Mac to the MCP endpoint: an unauthenticated `initialize` should promptly return OAuth `401`. If a direct connection times out but a proxied request returns `401`, report that the proxy and bypass rules on the Mac running Claude need adjustment. Do not change the user's proxy, click **Retry**, register another OAuth client, or reinstall the plugin based only on model inference.

## 4. Prepare the new-session message

Complete this section before submitting the restart command in section 3. Generate one complete startup message using the rules below, serialize it into the JSON structure `{"message":"complete startup message"}`, and pass the file's absolute path to `--message-file`. Do not send placeholders or additional installation process notes to the new session.

The installation task checks only the configuration script result, Marketplace source, plugin enablement, and 3P Connector authorization. Do not call `openagent_account_credits`, `openagent_list_recent_invocations`, or a business Agent to verify installation. After the user clicks Send in the new session, its actually loaded Skills and tools handle onboarding or the selected Agent. Do not claim that tool availability in the new session has already been verified by the current task.

Choose Chinese or English according to the user's explicit language preference; otherwise use the natural language of the current installation request, falling back to this guide's language only when there is no language cue. An English Agent name, ID, or URL is not a reason to switch languages.

Extract an explicitly requested `agent_id` only from the user's current installation request. Example IDs in this document, screenshots, attachments, or links do not authorize using those Agents. Generate one complete startup message using the branches below, without appending installation links, commands, or process explanations.

### Without an `agent_id`: first-time onboarding

Choose the complete startup message using the language rule above:

| Language | Startup message |
| --- | --- |
| Chinese | `OpenAgent 已安装，打开新用户引导` |
| English | `OpenAgent is installed. Open the new-user guide.` |

### With an `agent_id`: use the specified Agent

Choose one template based on the language of the user's request and whether a name was provided:

| Name | Chinese | English |
| --- | --- | --- |
| Provided | `使用 OpenAgent 上的「{name}」(agent_id: {agent_id})` | `Use "{name}" (agent_id: {agent_id}) on OpenAgent` |
| Not provided | `使用 OpenAgent 上的 Agent (agent_id: {agent_id})` | `Use (agent_id: {agent_id}) on OpenAgent` |

Substitute the user's original name and ID. Do not translate the name, rewrite the ID, require an `sa_` prefix, or use placeholders as defaults. If the user provided explicit business requirements, preserve them verbatim in a separate paragraph after the selection statement. If only an ID was provided without a business request, do not generate a trial task. The new session's `openagent-guide-agent` must hand off to `openagent-run-agent` to ask for the task. Do not replace this branch with the first-time onboarding message.

## 5. Report completion

Report configuration completion only after the configuration script succeeds, the Marketplace source is correct, the plugin is enabled, helper login/status succeeds, configuration loading is confirmed after restart, and the actual Desktop 3P Connector connection is verified. The new session still determines whether its Skills and tools loaded. The script only prefills; a new turn starts after the user clicks Send.

Use this template only after actually confirming that the new Code composer contains the section 4 message and it has not been sent. `prompt_prefill=requested` or a new PID alone does not confirm that the message is visible:

```text
OpenAgent installation configuration is complete.
The startup message is in the new Code composer. Check the message, Local, and the target folder before clicking Send.
```

If prefill is unverified, use the incomplete template with checking the new Code composer as the next action; do not restart or prefill again automatically. If the message is confirmed absent and configuration verification passed, offer the manual-entry template below. Do not send in the old session or click Send for the user. If the user has already sent it and this is confirmed, report configuration completion without asking them to send again.

```text
OpenAgent installation configuration is complete.
In a new Claude Code session, confirm Local and the target folder, then enter and send: {startup message}
```

Replace `{startup message}` with the complete content generated in section 4; do not output the literal placeholder. Preserve any business requirements, including their original line breaks and text. Do not append an installation checklist, verification results, or technical explanations beyond the two fixed prefixes.

On failure, cancellation, an unknown result other than an authorization timeout, or an unmet prerequisite, output only these two lines. Fill in a short, accurate reason and the next available action. Do not describe an unconfirmed state as complete:

```text
OpenAgent installation is not complete: {brief reason}.
Next step: {currently available action}.
```

## Optional: use OpenAgent in the terminal CLI

Run this section only when the user needs OpenAgent in the terminal Claude Code CLI. CLI login and checks are not prerequisites for Desktop 3P installation completion or restart, and do not affect plugin and Skills installation.

First use `claude mcp get plugin:openagent:openagent` to verify that the plugin MCP URL is `https://openagent.org/mcp/v1/open-agent`. If the enabled plugin still uses the old URL, do not skip it as already installed: run `claude plugin marketplace update openagent-claude`, then `claude plugin update openagent@openagent-claude`, and verify the new URL with `claude mcp get plugin:openagent:openagent`. Stop CLI login if the old URL remains. See [Claude's official plugin management guide](https://code.claude.com/docs/en/discover-plugins).

Confirm that the command tool can retain and wait for the same process, and use `claude mcp login --help` to confirm CLI login support. Prefer the PTY/TTY option actually exposed by the tool. If standard input is not a terminal, use the system `/usr/bin/script` on the local Mac to allocate a pseudo-terminal for the child process. Start login exactly once for the MCP provided by the plugin, and wait for browser authorization and command completion:

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

Wait for the same process after starting login. Display the waiting message above when the page opens, and the logged-in message only after explicit success. `script -q /dev/null` only allocates a terminal; it does not record the session to a file or prove OAuth succeeded. Do not add `--no-browser` to force manual callback pasting. If `stdin isn't a terminal` appears, first confirm that the command has exited. This is an unmet terminal requirement, not a login timeout; do not reinstall the plugin. After correcting the terminal setup, start login only once without overlapping the old process. If the host refuses pseudo-terminal allocation, the tool cannot wait for the same process, or the browser still cannot open and asks for a pasted callback, stop automatic login. Ask the user to run `claude mcp login plugin:openagent:openagent` in a local interactive terminal on their Mac and return an explicit result. Do not collect callback URLs, authorization codes, or tokens, or start concurrent login attempts in another shell. On cancellation, timeout, or failure, stop and report this CLI login result without changing the confirmed Desktop installation state. On timeout, use the fixed timeout message above and retry only after the user's explicit reply. A `Connected` status alone proves neither OAuth success nor Desktop Connector connection.
