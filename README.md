# OpenAgent for Claude

Find and run OpenAgents, upload task attachments, and check your OpenAgent Credits in Claude.

## Install

Follow the complete installation guide for your language:

- [English](openagent/INSTALL.en.md)
- [Simplified Chinese](openagent/INSTALL.md)

The Desktop installation supports macOS Claude Desktop with an existing third-party inference configuration. Run installation in **Code → Local**, with a local folder selected. If you are in Cowork, follow the guide to continue in Code.

Installation requires Git and Python 3. Attachment uploads require Node.js 20 or later. The guide handles plugin registration, Desktop Connector sign-in, restart, and connection verification. Desktop and terminal CLI sign-in are separate; the CLI sign-in steps are optional.

This repository publishes installation files on the `rel` branch. The Marketplace is `openagent-claude`; the plugin is `openagent@openagent-claude`.

## Use

After installation, start a new Claude session and ask to open the OpenAgent new-user guide. You can then ask Claude to find an Agent, run a task, or check your Credits. The five included Skills load with the plugin.

## Update

Follow the installation guide again to verify your source and update the installation. The guide also covers migration from the previous official `master` sources to an official `rel` source.

## Uninstall

Quit Claude Desktop, then download and run the official uninstaller in a terminal. Downloads prefer GitHub, with Gitee as the fallback. Only DNS, connection, timeout, interrupted-transfer, or HTTP 5xx failures permit one fallback attempt. Stop on permission or approval denial, certificate errors, HTTP 401/403/404/429/451, or digest, syntax, execution, or OAuth errors. Stop if the fallback also fails.

The assistant retains the selected source and public full SHA in the conversation. Set `uninstall_source` to that source and keep `uninstall_sha` empty only before the first resolution. If resolution fails before a SHA is known, the fallback may determine it; after resolution, reuse the same SHA and path without resolving the fallback `rel` again. An existing valid official source may continue without being forced back to GitHub; when starting from a previously installed Gitee source, the other official source is the fallback. Never switch back after using the one fallback. Download completely, check syntax, then execute once. Never pipe downloads into execution or switch sources after execution has started or its result is unknown:

```bash
(
  set -e
  uninstall_source='github'
  uninstall_sha=''
  case "$uninstall_source" in
    github) uninstall_repo='https://github.com/openagent-org/claude-plugin.git'; uninstall_raw='https://raw.githubusercontent.com/openagent-org/claude-plugin' ;;
    gitee) uninstall_repo='https://gitee.com/openagent-org/claude-plugin.git'; uninstall_raw='https://gitee.com/openagent-org/claude-plugin/raw' ;;
    *) exit 1 ;;
  esac
  if [ -z "$uninstall_sha" ]; then
    uninstall_ref="$(git ls-remote "$uninstall_repo" refs/heads/rel)"
    uninstall_sha="${uninstall_ref%%[[:space:]]*}"
  fi
  case "$uninstall_sha" in ''|*[!0-9a-f]*) exit 1 ;; esac
  [ "${#uninstall_sha}" -eq 40 ]
  printf 'OPENAGENT_SOURCE=%s\nOPENAGENT_REF=%s\n' "$uninstall_source" "$uninstall_sha"
  uninstall_file="$(mktemp "${TMPDIR:-/tmp}/openagent-claude-uninstall.XXXXXX")"
  trap 'rm -f -- "$uninstall_file"' EXIT
  curl -fsSL --proto '=https' --proto-redir '=https' "$uninstall_raw/$uninstall_sha/uninstall-openagent.sh" -o "$uninstall_file"
  bash -n "$uninstall_file"
  bash "$uninstall_file"
)
```

The uninstaller asks for confirmation and removes the recognized OpenAgent installation and its local authorization state. It preserves other plugins and Connectors and stops on conflicting configuration.
