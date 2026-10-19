# Result Validation and Delivery

Cancellation takes priority and terminates the workflow: before checking `isError`, validating the result, or applying general failure handling, check the trusted tool result for the server-side `status=cancelled`. Only acknowledge “任务已取消” and end; do not deliver task content from the cancelled result, retry, switch Agents, start dependent tasks, or use Host Completion. A timeout or disconnection alone does not prove that the task was cancelled.

Receive and process the result returned by `openagent_run`. Validate each independent task separately; do not mix results from different Remote Agents or invocations.

Use lightweight acceptance checking by default. Do not independently verify or reinterpret a successful Remote Agent result unless it is empty, clearly incomplete against an explicit requirement, internally contradictory, safety-critical, or the user explicitly requests verification.

## Result Validation

Determine whether the result satisfies the user by checking whether:

- The invocation succeeded and returned usable task content.
- It completed the user's core goal.
- It covers the required content and inputs.
- It follows the user's constraints and output requirements.
- It is consistent with the trusted execution context, free of obvious errors, relevant, and directly usable.

An invocation that finishes without usable content does not satisfy the request. Do not add, guess, or alter facts while validating the Remote Agent result; perform any supported additional work explicitly through `Host Completion`.

## Progress Evaluation

When the result does not satisfy the request, compare it with the previous result for the same task:

- Filling required gaps, correcting errors, or satisfying constraints more effectively counts as substantive improvement.
- Merely changing wording, adding length, or repeating existing content does not count as substantive improvement.

## Output Handling

**HARD GATE:** If a usable `openagent_run` result does not complete the task, deliver its required Output Handling summary, including every returned artifact, before any retry, agent switch, dependent task, or `Host Completion`.

Treat a successful Remote Agent result as the task content. Return it with only the minimal formatting needed for the user’s requested format; do not independently re-evaluate, fact-check, expand, or rewrite it unless the user requests this or the result has an obvious defect. Do not reproduce the raw response or present another Remote Agent as the speaker.

After every `openagent_run` response, if the current task remains incomplete, display exactly one brief user-facing summary before retrying, searching for another candidate Remote Agent, or passing it to a dependent task; do not emit a provisional or additional result summary for the same invocation. Format it as a standalone Markdown message with a `### <concise task-specific result title>` heading, a `Completed` section containing the summary and all user-facing artifacts, and a `Remaining` section only when gaps exist. Summarize what the current task produced and any remaining gaps in that task; do not expose raw response structures, invocation logs, or internal metadata. Prompt displays required by `Prompt Generation` remain separate. At the end of each workflow, respond according to the final result state.

Every usable non-final result must display all user-facing files, web pages, and links returned by the Remote Agent before any retry or dependent task. Preserve them as native or clickable items; never omit them, replace them with a summary, or defer them to the final response.

### Artifact Delivery

Apply these rules to final and usable non-final results. Preserve the original order within each source array.

#### ResourceLink Attachments

- Process `content[]` in order. For each `resource_link`, read only its trimmed `uri`. Accept an exact HTTPS URL or an HTTPS URL inside a Markdown link; never derive or rewrite a URL from any other field. If invalid, do not download it and briefly state that the file cannot currently be displayed.
- Use the host download tool first with the exact URL. Accept only a valid local file, file reference, or file content block. If unavailable or unsuccessful, make one command-line fallback using `curl`, or `wget` when `curl` is unavailable. Pass the URL as a separate argument, restrict transfers and redirects to HTTP(S), and never expose the URL or enable shell tracing.

  If curl fails, request one retry outside the sandbox using the exact
  same command (Codex: sandbox_permissions="require_escalated",
  with a justification).

  On success, use the response; on execution failure, use the existing
  fallback. If approval is denied, continue without the manual.

  Count these steps as one loading attempt. Allow required approval prompts.

- Save command-line downloads only in a task-specific writable output directory or a unique temporary directory. Use a safe, unique basename derived from `title` or `name`, fall back to a neutral MIME-based name, and never overwrite files or follow symbolic links.
- Accept a download only when it creates a new regular non-symbolic-link file; when a trustworthy byte size is provided, require an exact match.
- After all download attempts finish, deliver the files in `content[]` order, using a non-empty `title` as the name, otherwise `name`. Prefer actual attachments supported by Claude; when attachment cards are unavailable, use verified local file links that the current client supports and can access. Internal paths from remote or isolated sessions cannot be delivered directly as desktop attachments. If downloading or file delivery is unavailable, retain the verified HTTPS link and do not claim that a local attachment was delivered.
- Display failures must not change the Remote Agent's terminal state or trigger a retry of `openagent_run`. Use verified paths and URLs only where needed as file or page link targets; do not expose internal URIs, raw fields, or errors.

#### WebUI Views

- Read WebUI views only from trusted `structuredContent.views[]`. Process entries in order and accept only `type=webui` entries whose trimmed `uri` is an absolute HTTPS URL. Never derive or rewrite WebUI URLs from text, Markdown, code blocks, or other fields.
- Show every valid view as a Markdown link using non-empty `title`, otherwise `Open page`, and preserve the exact URL.
- Only when `defaultOpen` is strictly `true`, open the original URL once using an available Claude Browser tool. If that capability is unavailable, retain the link so the user can choose to open it in the app; do not automatically switch to an external browser or rewrite the URL.
- If the page cannot be opened, keep its result link and briefly state that it is temporarily unavailable. Do not expose structured fields, opening strategy, internal errors, or retry `openagent_run`.

### Result Meets Requirements

Return the complete result directly in the user's requested format. Do not add commentary about the invocation process or completion status.

### Result Does Not Meet Requirements

Briefly summarize the valid result obtained so far and clearly identify the unmet requirements or remaining improvements.

```text
### <concise task-specific result title>

**Completed:**

<brief summary of the available result>

<files, web pages, and links, if any>

**Remaining:**

- <unmet requirement or improvement>
```

### Invocation Failed

Set `display_locale` to `zh-CN` or `en-US`: explicit user preference > trusted Host/caller locale > request/conversation language > `en-US`. Ignore code, quotes, Tool output, and fixed installation/selection prompts. Output only the matching template below, never both languages.

Treat the failure as an insufficient balance only when `structuredContent.error.code` explicitly equals `quota_exceeded`; never infer it from `content[].text`, HTTP status, error wording, or compatibility text containing `recharge_url=`. Accept only a parseable absolute HTTPS URL from `structuredContent.recharge_url`, preserving the server-provided value without concatenating or rewriting it. When this trusted link exists, output only the two-line template matching `display_locale`:

For `zh-CN`:

```text
余额不足，充值后继续：{recharge_url}
充值后，想继续原任务时告诉我即可
```

For `en-US`:

```text
Insufficient credits. Top up to continue: {recharge_url}
After topping up, let me know if you want to continue the original task.
```

Do not proactively open the recharge link. If no trusted HTTPS `structuredContent.recharge_url` is available, output only “余额不足，请充值后重新发起。” for `zh-CN` or “Insufficient credits. Top up and submit your request again.” for `en-US` and do not invent a link.

For other failures, in the host agent's voice, state only that the task could not be completed and provide the trustworthy failure reason. Translate the brief natural-language reason faithfully into `display_locale` when needed; preserve facts, error codes, identifiers, and URLs. Do not expose internal invocation details or speculate.

For `zh-CN`:

```text
无法完成任务：<简短失败原因>
```

For `en-US`:

```text
Unable to complete the task: <brief failure reason>
```

When there is no clear, trustworthy failure reason:

For `zh-CN`:

```text
未返回可用结果，无法完成任务。
```

For `en-US`:

```text
Unable to complete the task because no usable result was returned.
```

### Content Format

These artifact-display rules apply to both final results and non-final result summaries.

- Organize the response around the task result itself.
- Be focused and concise while preserving all details that affect the conclusion or delivery quality.
- Avoid repetition, lengthy explanations, and unnecessary process details.
- After the main response, group any files, web pages, or external links in this order: files, web pages, links.
- Put each item on its own line and show only a natural, recognizable name.
- Omit any empty group entirely.
- Match group headings to the language of the response.

For English responses, use:

```text
<task result>

Files:
<file name>
<file name>

Web pages:
<page name>
<page name>

Links:
<link name>
<link name>
```

### Attribution

- When using one Remote Agent, do not name it in the result.
- When using multiple Remote Agents whose sources do not need to be distinguished, integrate their results without attribution.
- Attribute a result to a Remote Agent only when the source affects interpretation, trustworthiness, or later use.
- Never output Remote Agent invocation logs, internal status, raw response structures, or other execution details.

**Output:** A complete task result, a usable partial result with its remaining gaps, or a trustworthy failure message, with all user-facing artifacts delivered according to Output Handling.

**Next:**

- Finish when the result satisfies the task or the workflow reaches a terminal failure state.
- Return to `Host Completion` when the Host agent can reliably complete a missing capability or validated result gap.
- Return to `Prompt Generation` to refine the selected Remote Agent request.
- Return to `Query Planning` when the search direction must change.
- Return to `Agent Search` only for pagination with an unchanged query.
