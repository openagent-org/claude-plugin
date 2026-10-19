---
name: openagent-search-agent
description: Use when the user asks to find, recommend, or select Agents with an explicit query, browse available Agents without a query, or an upstream business Skill requests headless capability discovery. Perform one discovery and selection protocol only; do not plan tasks, search again, or call execution tools.
---

# OpenAgent Agent Discovery

## Purpose

Complete a single OpenAgent discovery request. Direct user searches always open the Claude Browser and wait for a trusted user selection, with or without an explicit query. Background searches return complete candidates to the caller. This Skill does not plan business tasks, automatically search again, or call Agent execution tools.

## Terminology

- **OpenAgent**: The platform and tools for discovering, invoking, and managing Remote Agents.
- **Remote Agent**: A remote service callable through OpenAgent; it does not automatically inherit the Host conversation or local environment.

## Status Update Format

When entering a workflow stage, send a standalone assistant commentary update in this format:

```text
OpenAgent: <stage name> — <brief action phrase>
```

- Use the exact English workflow-stage heading for `<stage name>` and a short, verb-led action phrase in the user's language. Describe only the current action, without reasoning, results, next steps, candidate counts, internal identifiers, or handoff URLs; never claim success before authoritative confirmation.
- Emit one update on stage entry. Do not repeat it for tool polling, candidate-by-candidate checks, or resuming a pending call; re-entry may emit a new update.
- Deliver actual results separately. `Output` and `Next` describe internal data handoff and workflow transitions; do not display these labels to the user.
- For an upstream `presentation_mode=headless` request, suppress all user-facing stage updates, candidate-check notices, and UI; return data only to the caller, which owns progress reporting. On cancellation, go directly to Failure Handling and output only its fixed terminal reply, without another stage update.

## Workflow

On an explicit OpenAgent authentication failure, follow [runtime sign-in](../openagent-login/runtime-sign-in.md) before other error, fallback, or completion rules. Otherwise keep this workflow unchanged. A user-requested retry of an unfinished sign-in goes there too.

1. Run `Agent Search` once. Every direct user search uses browser presentation, with or without an explicit query; an upstream headless request uses headless presentation.
2. Pass a browser handoff result to `Browser Handoff` for validation and opening. Pass headless results to `Result Validation and Delivery`.
3. After `Browser Handoff` opens, recovers, or links the page, immediately enter `Agent Selection` in the same Turn. Use the shared Wait and Close Orchestration for every wait. On `more_requested`, return to `Browser Handoff` with the new URL, then resume selection on the same session.
4. Pass a successful selection to `Result Validation and Delivery` in the same Turn for authorization validation and handoff to `openagent-run-agent`. Handle cancellation, timeout, invalid results, or other failures in `Failure Handling` and end locally.

### Loop Control

Call the search tool only once per discovery request. For `more_requested`, use only the new handoff URL returned by the wait result and continue waiting on the same selection session; do not start a new search. The caller decides whether to search again. Keep only one active wait per selection session at a time.

## Workflow Stages

Follow the orchestration in Workflow and transition only through each stage's `Next` contract.

### Agent Search

Input is an explicit query with constraints, a general browsing intent, or a headless request from an upstream business Skill. Emit the stage update before searching, except in headless mode.

1. For every direct user search, with or without an explicit query, call `openagent_search(presentation_mode=browser)` once with `locale=zh-CN|en-US` matching the current user's language and a new stable `idempotency_key`. Pass explicit search terms as `q` (1–200 Unicode characters) to prefill and search the page, preserving names and constraints. Otherwise omit `q`; never invent terms. Do not pass other search filters. Retain the original request for post-selection handoff. Do not call `openagent_user_guide`.
2. For an upstream headless request, call `openagent_search` once with the supplied query, `presentation_mode=headless`, and the same locale rule; preserve the caller's query and constraints. In this mode, pass category, tags, sort, and pagination only when explicitly requested. Pass `category` only when the caller explicitly supplies a server-recognized category ID; never put natural-language search terms directly in that field.
3. Preserve the returned candidates and metadata without selecting, reordering, or inventing Agents. Do not open a browser or call `openagent_wait_for_selection` in this stage.

| Request source | `presentation_mode` | Result handling |
| --- | --- | --- |
| An upstream business Skill requests background capability discovery | `headless` | Do not display a Widget or the Claude Browser; return structured candidates only to the current caller |
| The user searches or browses available Agents, with or without an explicit query | `browser` | Do not show the Search Agents Widget; pass the returned handoff result to Browser Handoff, open the Claude Browser, and wait for selection |

“Find a PPT Agent”, “Find a stock analysis Agent”, “What is available in OpenAgent?”, and “Browse available Agents” all use `presentation_mode=browser` and open the Claude discovery page.

**Output:** One unchanged search Tool Result, including candidates and any presentation or selection metadata.

**Next:** Browser results enter `Browser Handoff`; headless results enter `Result Validation and Delivery`; errors or inconsistent presentation metadata enter `Failure Handling`.

### Browser Handoff

Input is the browser result from Agent Search or a trusted `more_requested` result from Agent Selection. This stage opens the page; it does not search or wait for selection.

1. For an initial browser result, require `presentation_mode=browser`, `browser_handoff=true`, `status=pending`, non-empty `selection_id` and `handoff_url`, and no Search Agents Widget binding. For `more_requested`, require the same trusted selection session and a new non-empty `handoff_url` from its wait result. Reject invalid handoffs before opening a page.
2. Use only the original absolute HTTPS `handoff_url` and `selection_id` from that result. Do not construct, rewrite, or reuse URLs from another selection session. Use the full URL only as this session's navigation argument or the target of an "Open the OpenAgent selection page" link localized into the user's language; do not additionally expose temporary tokens, bare URLs, or diagnostic logs.
3. Emit the Browser Handoff update and follow the six-step opening procedure below. Use only the `mcp__Claude_Browser__tabs_context`, `navigate`, and `tabs_close` tools actually exposed by the current Host, following their schemas. If a required tool is unavailable or the fixed file cannot be created, read, or opened, provide the original URL as an "Open the OpenAgent selection page" link localized into the user's language, mention the Open in app option, and wait on the same selection session. Do not claim the page opened automatically.
4. For `more_requested`, repeat the six-step procedure with the new URL for the same selection session; do not search again. If automatic opening fails or times out, do not retry navigation. Inspect once with `tabs_context` when available, clean up only temporary tabs confirmed to belong to this attempt, preserve the same link, and begin waiting.

#### Six-Step Opening Procedure

Use the fixed local bootstrap file `~/.claude/.openagent/browser/blank.md` on the user's machine. Resolve the current user's home directory at runtime; do not hardcode a username, plugin installation directory, or temporary directory. Reuse an existing file without rewriting or clearing it. If absent, use local file tools to create its parent directories and an empty file with exclusive creation to prevent concurrent overwrites; reuse it if another session creates it first. If the path is not a regular file or creation or reading fails, use the link fallback above. Convert the absolute path to a `file://` URL with a standard file URI conversion, correctly encoding spaces and Chinese characters; do not pass a literal `~` in the URL. Keep the file for future sessions; tab cleanup must not delete it.

1. **`tabs_context`**: Record every existing `tabId`, `origin`, and `isActive`, plus the pane's display state. Preserve all existing tabs: subsequent navigation must not target their `tabId`, and no cleanup, including terminal selection cleanup, may close them.
2. **`navigate(file_url)`**: Confirm the fixed file exists, creating it first if absent, then navigate to its `file://` URL without a `tabId`. This step opens and displays the right-side pane; do not skip it or run it in parallel with the next step. Record the local file tab handle created by this attempt. Proceed to step 3 only when the tool explicitly confirms the local file opened successfully. On failure, timeout, or an ambiguous result, stop further automatic navigation, preserve the selection-page link, and wait on the same selection session.
3. **`navigate(handoff_url)`**: Local file tabs cannot be navigated, so omit `tabId` to open the original `handoff_url` in a new active tab. Record the returned target `tabId`. Do not rewrite the URL, navigate an existing tab, or use `force` to discard unsaved content.
4. **`tabs_context`**: Identify the target using the step 3 navigation result. Confirm it is newly created, its `origin` matches the `handoff_url` origin, `isActive=true`, and the pane is explicitly `displayed`. An existing same-origin tab cannot substitute for the target; `browserOpen=true` or `navOk=true` cannot substitute for `displayed`. If these facts cannot be confirmed, preserve the link and report that opening is unconfirmed; do not create another page.
5. **`tabs_close`**: Close the local file tab created in step 2 by its exact `tabId`. Also close any seed tab newly created by this attempt that tool results confirm is still blank. IDs to close must be absent from the step 1 original set and must not identify the target tab. `origin=null`, a matching domain, or a tab name alone does not establish ownership. Preserve tabs with missing handles or uncertain ownership. Do not retry a failed close or let it affect the selection session.
6. **`tabs_context`**: Read back and report all remaining tabs' `tabId / origin / isActive` and the pane's `displayed` or `hidden` state. If the tool provides no display state, report it as unconfirmed rather than guessing. Claim the page is displayed only after confirming all original tabs remain, the target is active, and the pane is `displayed`. This is the sole display exception for browser-state checks; do not expose full URLs, paths, query parameters, or tokens. Immediately wait on the same selection session without waiting for the page to finish loading.

**Output:** The same trusted selection session and the opened, recovered, or linked handoff page, or a handoff failure.

**Next:** Immediately enter `Agent Selection` in the same Turn after opening, recovery, or link delivery. Page load state must not be a prerequisite for listening or handling a terminal selection state. Invalid or failed handoffs enter `Failure Handling`.

### Agent Selection

Input is an opened, recovered, or linked Browser Handoff with a non-empty `selection_id` for the same session. Headless results and results without a selection handle must not enter this stage.

1. The discovery page has been opened, recovered, or provided as a link. Regardless of whether the original request was to search, recommend, view, select, or find and run, emit the Agent Selection update and immediately use `selection_id` to call `openagent_wait_for_selection` through Wait and Close Orchestration in the same Turn. Do not deliver candidates first, end the Turn to await a new user message, or open the Claude Browser again.
2. Allow only one active wait call per `selection_id` at a time. The selection-wait update replaces the opening status; do not append another guidance message or repeat the update when resuming a pending orchestration call.
3. On `more_requested`, retain the same selection session and pass only the newly returned `handoff_url` to Browser Handoff. Do not search again or start a second simultaneous wait.
4. On `selected`, `cancelled`, or `timed_out`, perform terminal cleanup through Wait and Close Orchestration. `openagent_wait_for_selection` returns selection data only; it does not close the browser. Complete the cleanup gate before any next-stage update, before reading or invoking `openagent-run-agent`, and before any final reply, including No Explicit Intent guidance. This stage does not validate execution authorization or invoke a business Agent.

**Output:** The unchanged trusted wait result from the same selection session. Keep actual terminal cleanup tool results or concrete reasons a step could not be performed in Host context only; do not add fields to the server result.

**Next:** `more_requested` returns to `Browser Handoff`; `selected` enters `Result Validation and Delivery` in the current Turn; cancellation, timeout, or wait failure enters `Failure Handling`. Do not end the Turn between the successful wait and authorization handoff.

### Result Validation and Delivery

Input is a complete headless search result or a trusted terminal selection state. For browser `selected` results, first check the cleanup evidence required by Wait and Close Orchestration and complete any missing, unattempted steps. Only then emit the Result Validation and Delivery update, validate, and hand off. Headless results require no cleanup gate or stage update.

- If `recommended_agent_id` is non-empty, `results` must contain exactly one matching candidate with a non-empty name. On mismatch, do not recommend or execute an Agent; enter Failure Handling. For headless requests, return the current query and trusted public error; for direct requests, explain that search results are temporarily unavailable and end.
- Determine whether candidates are empty only from `results` and trusted counts, not from a missing selection handle. Headless results may contain multiple candidates without a handle. Do not show an empty card or invent Agents.
- For a direct `search_only` request, complete the browser handoff and `openagent_wait_for_selection` in the same Turn first. After successful selection, enter the No Explicit Intent branch of `openagent-run-agent`; do not end the Turn early because the original request was only to search or select.
- `find_and_run` still returns only structured discovery results. The current caller decides whether to search again or execute. For direct user requests, hand off to `openagent-run-agent` only when an explicit executable prompt and trusted authorization already exist.
- Headless search returns complete model-readable candidates only. It creates no selection session, returns no Widget binding metadata, and does not enter the human-assisted discovery chain. The current caller selects a trusted Agent.
- Return headless search results completely unchanged to the current caller. Do not rewrite candidates, reorder results, or replace the upstream decision.
- For `status=selected`, pass the cleanup gate above first; do not repeat a close already attempted. Read only trusted `selected_agent`, `execution_authorization`, and `action`, preserving `selected_agent.name` and the Agent Card's `selected_agent.description`. A selection action provides server authorization only; it does not replace the user's business requirement. A general discovery request has no executable task. If the original request only searches, recommends, views, or selects an Agent, pass the trusted Agent to the No Explicit Intent branch of `openagent-run-agent` for its fixed two-line guidance. Do not use the selection action or an Agent default task to start a run; do not execute a default task.
- Normal public discovery returns `execution_authorization=null` and `action.type=none`. Validate the trusted `selected_agent` identity, then pass it with the user's original business requirement to `openagent-run-agent` using ordinary `agent_id` and `data`. If no business task was supplied, use its No Explicit Intent branch. A selected Agent is not authorization to invent a task.
- Only a legacy persisted trial selection may contain `execution_authorization.source=user_selection`, `immediate=true`, and `action.type=call_tool`. Validate its matching selection handle and bound idempotency key before handing it to the execution Skill; never reinterpret an invalid legacy authorization as an ordinary task. After validation, read the `openagent-run-agent` Skill if needed, or reuse it if already read in the current context. Immediately pass the selection result and authorization unchanged to `openagent-run-agent` in the same Turn. Do not end the Turn between `openagent_wait_for_selection` and `openagent-run-agent`.

**Output:** Complete candidate results, or validated and unchanged user selection authorization with the Selected Remote Agent.

**Next:** For headless requests, deliver results to the caller and end. With valid authorization, hand off to `openagent-run-agent` in the same Turn so it can determine whether an executable business requirement exists.

### Failure Handling

Input is a trusted failure result from search, selection waiting, handoff, or result validation. Emit the Failure Handling update except for headless requests and cancellation.

For cancellation replies, set `display_locale` to `zh-CN` or `en-US`: explicit user preference > trusted Host/caller locale > request/conversation language > `en-US`. Ignore code, quotes, Tool output, and fixed installation/selection prompts. Output only the matching single-language reply.

- For `status=cancelled`, first check the cleanup gate and complete any missing, unattempted steps. Do not repeat a close or emit a stage update. Use only existing trusted evidence of page closure; `status=cancelled` alone does not prove that the page is closed. If closure is confirmed, output only “你已关闭 OpenAgent 发现页。” for `zh-CN` or “You have closed the OpenAgent discovery page.” for `en-US`. Otherwise, output only “OpenAgent 选择已取消。” for `zh-CN` or "OpenAgent selection cancelled." for `en-US`. End selection; do not automatically reopen the page or continue Agent execution.
- For `status=timed_out`, first check the cleanup gate and complete any missing, unattempted steps without repeating a close. Explain that selection timed out and end discovery. Do not automatically reopen the page.
- This Skill handles search, wait, and browser handoff failures locally; do not silently switch Agents. Use only trusted Tool Results, authoritative states, or stable public Host error codes. Without a stable public code, treat the error as unknown and do not retry automatically. Do not infer error category, authentication state, or retryability from message text.
- Headless failures must return the original search goal, constraints, trusted public reason, and all candidates already obtained to the current caller, without overwriting or fabricating results. For direct requests, show only a natural-language reason; hide raw results and internal fields.

**Output:** A caller-facing failure result preserving full context, or a trusted user-visible termination explanation.

**Next:** End the current discovery without silently searching again, reopening the page, or executing another Agent.

## Shared OpenAgent Rules

### Shared Protocol References

- Reuse [the shared rules of openagent-run-agent](../openagent-run-agent/SKILL.md#shared-openagent-rules) for post-selection execution authorization, Invocations, Sessions, attachments, and execution result delivery. Referencing a protocol does not authorize execution; hand off only after Result Validation and Delivery passes.
- This Skill owns search, candidate delivery, and UI Handoff. Callers must not independently rewrite the browser opening, waiting, or cleanup protocol.

### Result and User Boundaries

- Trust only candidates, metadata, and authorization returned by the search Tool. Return headless results completely to the current caller without fabrication, reordering, or rewriting.
- Raw tool results, selection handles, and Widget credentials are internal only. Expose `handoff_url` only as the target of this selection session's link in Browser Handoff; do not output bare URLs, extracted tokens, or logs.

### Browser Display Boundary

Open, inspect, or close pages only through tools exposed by the current Claude Host. When tools are unavailable, provide a link and wait on the same selection session; do not guess tool names or use another client's browser runtime.

### Wait and Close Orchestration

1. Call `openagent_wait_for_selection` directly once with the current trusted `selection_id`. Do not wrap it in a local JavaScript executor or implement the MCP call yourself over HTTP. Allow only one active wait per session.
2. On `more_requested`, retain the same session, pass the new URL back to Browser Handoff, and then wait sequentially. Do not search again.
3. On `selected`, `cancelled`, or `timed_out`, preserve the original result and actually call the current Host's `mcp__Claude_Browser__tabs_close` once with the selection tab's `tabId` recorded during opening, following the tool's schema. Close only selection tabs confirmed to have been created by this flow; do not close tabs in bulk by domain, original tabs, or result pages. If the handle or close tool is unavailable, record the concrete reason; skipping is not successful closure.
4. After handling step 3, including when closing is impossible, actually call `mcp__Claude_Browser__tabs_context` once. Separately check that the target tab is gone, original tabs remain, and the pane is `displayed` or `hidden`. Record the state as unconfirmed if the tool is unavailable or reading fails; a `tabs_close` success message cannot replace this readback. Preserve the pane when other tabs remain. If no tabs remain but the pane is still `displayed`, record that it is not hidden; if no display state is provided, record it as unconfirmed. Do not invent a hide API or close other tabs to force the pane to hide.
5. The cleanup gate accepts only actual close and readback results in the current tool history, or concrete reasons the corresponding steps could not be performed. A terminal selection result, an opening result, a plan to close, or this Skill's text is not cleanup evidence. Complete only missing, unattempted steps; do not retry attempted steps. Enter the next stage or give a final reply only after passing this gate, without exposing internal diagnostic fields.
6. Pass the original wait result unchanged to the next stage. Cleanup failures must not overwrite it or trigger new business requests. Preserve authorization validation and the requirement to ask for a task when no business intent exists.
