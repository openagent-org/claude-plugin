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

Quit Claude Desktop and any CLI sessions using OpenAgent, then run this in your terminal:

```bash
curl -fsSL --proto '=https' --proto-redir '=https' 'https://raw.githubusercontent.com/openagent-org/claude-plugin/rel/uninstall-openagent.sh' | bash
```

The uninstaller asks for confirmation and removes the recognized OpenAgent installation and its local authorization state. It preserves other plugins and Connectors and stops on conflicting configuration.

If you have already confirmed that you want to uninstall OpenAgent, use this command to skip the confirmation prompt:

```bash
curl -fsSL --proto '=https' --proto-redir '=https' 'https://raw.githubusercontent.com/openagent-org/claude-plugin/rel/uninstall-openagent.sh' | bash -s -- --yes
```
