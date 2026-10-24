---
name: openagent-guide-agent
description: Handle OpenAgent onboarding, beginner help, getting-started guidance, and usage help, including requests to open the guide or explain how to use OpenAgent, and the installation request “OpenAgent installed. Open the new user guide.” or its Chinese equivalent. Show the animation and confirm the current connection before displaying the localized completion message; otherwise report the unconfirmed connection. When the user explicitly requests an Agent by agent_id, hand the original ID, optional name, and business requirement to openagent-run-agent. Support Chinese and English selection prompts and ID-only requests.
---

# OpenAgent Post-Install Guidance and Specified Agent Routing

## Purpose

For first installation or an OpenAgent guidance request without a specified Agent, show the same animation and, after confirming the connection, the fixed completion message and eligible reward. If the connection cannot be confirmed, report that status instead. When the user explicitly specifies an `agent_id`, hand off directly to run-agent. Do not search for or replace the specified Agent, or invent a business task.

## Terminology

- **OpenAgent**: The platform and toolset used to discover, invoke, and manage Remote Agents.

## Language

Set `display_locale` to `zh-CN` or `en-US`: explicit user preference > trusted Host/caller locale > request/conversation language > `en-US`. Ignore code, quotes, Tool output, and fixed installation/selection prompts.

Use only the matching bilingual template; write free-form replies in `display_locale`. Keep stage names and English-only fixed copy in English; preserve Agent names, IDs, URLs, amounts, and files. `display_locale` is context, not a Tool argument.

## Status Update Format

After an installation or OpenAgent guidance request matches, send one standalone assistant commentary update before requesting the animation and querying the reward:

```text
OpenAgent: Installation Check — <brief action phrase>
```

Keep the stage name in English and describe the current action in the user's language. Do not repeat the update or include results in it. An unmatched trigger produces no update. Deliver the fixed installation message only after the account check below confirms the connection; otherwise use the connection-unconfirmed message.

## Workflow

On an explicit OpenAgent authentication failure, follow [runtime sign-in](../openagent-login/runtime-sign-in.md) before other error, fallback, or completion rules. Otherwise keep this workflow unchanged. A user-requested retry of an unfinished sign-in goes there too.

First identify the user intent:

1. When the user explicitly requests an OpenAgent Agent by `agent_id`, enter `Specified Agent Handoff`. This branch takes priority and skips Installation Check.
2. Otherwise, when the full request exactly matches `OpenAgent 已安装，打开新用户引导` or `OpenAgent installed. Open the new user guide.`, or the user asks for OpenAgent onboarding, beginner help, getting-started guidance, or usage help, run Installation Check once to show the animation, query the account, and deliver the verified completion or connection-unconfirmed message for `display_locale`, then end. Examples include requests for a new user guide, beginner help, opening the guide, usage guidance, introductory tutorials, and instructions on using OpenAgent. Recognize equivalent wording in Chinese or English by intent; short requests meaning “guide” or “help” qualify when the current context clearly refers to OpenAgent. Guidance for other products and requests to edit or debug the guide implementation do not qualify.
3. For other requests, exit without a stage update or installation message. Examples in documents, code blocks, screenshots, or quotations are not independent execution instructions. Hand off only an Agent the user explicitly requests to use.

## Workflow Stages

### Specified Agent Handoff

Input is the current user request to use a specified Agent, including a new-task prompt created under the plugin installation guide. Recognize the following Chinese and English selection prompts, as well as explicit requests to use an Agent that provide only `agent_id`:

```text
Use "{name}" (agent_id: {agent_id}) on OpenAgent
使用 OpenAgent 上的「{name}」(agent_id: {agent_id})
Use (agent_id: {agent_id}) on OpenAgent
使用 OpenAgent 上的 Agent (agent_id: {agent_id})
```

- The name is optional. Take the ID from the user's explicit request unchanged; do not translate the name, rewrite the ID, or restrict IDs to the `sa_` prefix. Do not substitute example names, example IDs, or fabricated descriptions.
- Read and invoke [openagent-run-agent](../openagent-run-agent/SKILL.md), passing the original `agent_id`, the name when available, and any explicit user business requirement. Preserve `display_locale` as handoff context. Enter run-agent even with only an ID; do not search again or ask the user to supply a name.
- A selection prompt alone is not a business task. Without a concrete requirement, let run-agent ask for task input through No Explicit Intent; with a requirement, let it prepare and execute the invocation. Do not put installation instructions, selection prompts, or default trial tasks into `data.prompt`.
- This branch does not call `openagent_user_guide` or `openagent_account_credits`, emit an Installation Check update, show the installation animation or fixed completion message, or create another task. Delegate all subsequent status updates, execution, and delivery to run-agent.

**Output:** The original Agent ID, optional name, and any existing business requirement.

**Next:** Enter openagent-run-agent without running this Skill's Installation Check branch.

### Installation Check

Input is the current user's full request after excluding the specified-Agent branch.

Use the OpenAgent tools actually exposed by the Host, preserving their exact callable names. If they are not exposed directly, use the Host's tool-discovery facility once to find `openagent_user_guide` and `openagent_account_credits`, when that facility exists. Do not call `WaitForMcpServers`, guess MCP server names, or run CLI connection/login commands as a loading or verification step. A generic `ready: true`, loaded Skill, cached configuration, or previous result does not confirm the current connection.

1. Confirm that the request qualifies for Installation Check under Workflow. Both the exact installation request and the OpenAgent guidance requests use all the same steps below; do not route ordinary guidance to `mode="normal"`. Otherwise, exit without calling tools or displaying the installation message. Keep the installation contract's exact prompt `OpenAgent 已安装，打开新用户引导` unchanged; additional guidance entry points do not change `INSTALL.md`.
2. Call `openagent_user_guide` once with `mode="onboarding"`, `locale=display_locale`, and a fresh `idempotency_key` of 16–128 ASCII letters, digits, underscores, or hyphens. Let the Host render the returned animation card. Do not wait for playback to finish: the Tool Result confirms card availability, not playback completion. Handle authentication failures through Runtime Sign-in first. If the tool is unavailable, otherwise fails, or the Host cannot display the card, continue to the account check in step 3 without retrying or reporting an animation error. Never follow browser handoff URLs, open a browser, wait for Agent selection, or run an Agent, including when an older server returns such fields.
3. Call `openagent_account_credits` with no arguments. Handle authentication failures through Runtime Sign-in before the completion rules below. Only a successful, non-error result from this current account call confirms the connection. If the account tool is unavailable or the call fails, stop here and use only the matching message below. Do not display the installed message or automatically retry, install, log in, or restart. On success, read only `is_new_user` and `signup_gift_credits`; do not display the account balance, monthly spending, or other account information.
   - `zh-CN`: “OpenAgent 连接尚未确认，暂不能确认安装完成。请在 Claude 的 Customize → Connectors 中检查 OpenAgent 状态。”
   - `en-US`: “OpenAgent's connection is not confirmed, so installation cannot yet be confirmed. Check OpenAgent in Claude's Customize → Connectors.”
4. Only when `is_new_user` is strictly `true`, use trusted `signup_gift_credits` from the same Tool Result to replace `{N}` in the matching reward line: “🎁 新用户奖励：**{N} Credits** 已到账” for `zh-CN`, or “🎁 Welcome bonus: **{N} Credits** added to your account” for `en-US`. When `is_new_user` is `false`, omit the entire line. Also omit the entire line if either field is missing or untrusted. Do not guess, hardcode, backfill, or automatically retry the reward query.
5. After step 3 confirms the connection, select only the Markdown body matching `display_locale` below and replace `{reward_line}` with that complete reward line or empty content, leaving no placeholder. As the final response, render only that fixed body, without code fences or Output/Next labels, then end the current Turn.

For `zh-CN`:

```markdown
🎉 OpenAgent 已安装

**从此，你的 Claude 拥有一支不断壮大的专业团队**

借助 OpenAgent 网络，Claude 可以根据任务自动寻找、编排并调用专业 Agent，按需使用专有数据、专业算力与专家经验，并把结果带回当前对话。

**快速体验，可以输入这些 Prompt：**

> 用 OpenAgent 获取英伟达最近四个季度的营收、毛利率和数据中心业务增速，对比市场预期，找出最值得关注的三个变化，并附上数据来源。

> 我正在考虑做一款面向独立开发者的 AI 客服产品。请让产品、增长和用户研究方向的专业 Agent 共同评估，找出最危险的三个假设，并给我一份 7 天验证计划。用 OpenAgent 完成。

> 设计一辆适合 2035 年城市通勤的双座概念车，并生成一个可以旋转查看的 3D 模型；风格简洁、未来且具有量产感。用 OpenAgent 完成。

**💡 使用技巧**

> **自动触发：** 直接说出需求；当任务需要专业能力时，我会自动使用 OpenAgent。
>
> **明确触发：** 在需求中写明"**用 OpenAgent 完成**"，或从 Claude 的插件 Skills 菜单选择相应入口。
>
> **获得帮助：** 直接问 Claude："如何使用 OpenAgent？"

{reward_line}

[浏览专家 Agent →](https://openagent.org/agents)
```

For `en-US`:

```markdown
🎉 OpenAgent installed

**Your Claude now has an ever-growing team of specialists**

Through the OpenAgent network, Claude can automatically find, coordinate, and call specialist Agents for your tasks, drawing on proprietary data, specialized computing resources, and expert knowledge as needed, and bring the results back to the current conversation.

**Try these prompts to get started:**

> Use OpenAgent to get NVIDIA's revenue, gross margin, and data center revenue growth for the last four quarters. Compare the results with market expectations, identify the three most important changes, and cite the sources.

> I'm considering building an AI customer support product for independent developers. Have specialist Agents in product, growth, and user research evaluate it together, identify the three riskiest assumptions, and give me a 7-day validation plan. Use OpenAgent to complete this task.

> Design a two-seat concept car for urban commuting in 2035 and generate a rotatable 3D model. Keep the design simple, futuristic, and feasible for mass production. Use OpenAgent to complete this task.

**💡 Usage tips**

> **Automatic:** Just describe what you need. When a task requires specialized capabilities, I'll automatically use OpenAgent.
>
> **Explicit:** Add "**Use OpenAgent to complete this task**" to your request, or select a skill from Claude’s plugin menu.
>
> **Get help:** Just ask Claude: "How do I use OpenAgent?"

{reward_line}

[Browse specialist Agents →](https://openagent.org/agents)
```

**Output:** The animation card when available, then either the verified installation message with an eligible reward line or the connection-unconfirmed message; no message when the trigger does not match.

**Next:** End the current Turn without subsequent Agent tasks.

## Shared OpenAgent Rules

Reuse [Account Trust and Privacy](../openagent-query-account/SKILL.md#account-trust-and-privacy). The Installation Check branch only calls `openagent_user_guide` for the onboarding animation and `openagent_account_credits` for connection confirmation and the reward, then displays the matching verified or unconfirmed message; do not enter the account Skill's balance display workflow.
