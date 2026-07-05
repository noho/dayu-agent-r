# WU-TOOLS-CANCEL-01 S2E Aggregate Validation - AgentCodex

## Scope

- Work unit: WU-TOOLS-CANCEL-01
- Gate: S2E aggregate validation
- Branch: `phase/wu-tools-cancel-01`
- Base slice commits observed: S2A1 `32030ca9`, S2A2 `0fea8da0`, S2B `03e546f5`, S2C `834b0df6`, S2D `94b3c196`

## First-principles Judgment

S2E 目标成立。S2A1-S2D 已分别解决 contract、Host wiring、Doc、Fins read 与 Web sync 的 process-backed 声明和执行边界，但单 slice 通过不等于 aggregate 可关闭；必须验证同一 typed execution contract 在 Host ToolRuntime、ToolsDiscovery digest、业务 provider、WAITING 工具和 late-result accept barrier 中没有语义漂移。

本轮没有发现需要当前修复的 root cause。现有风险主要是已知 residual risk 的覆盖边界和后续 owner，不是当前 production cancel closeout 的阻塞缺陷。

## Validation Commands

| Command | Result |
|---|---|
| `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/web/test_web_tools_provider.py -q` | PASS: `219 passed, 3 warnings in 15.51s`; warnings 均来自第三方 `edgar` deprecation |
| `source .venv/bin/activate && pytest tests/contracts tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q` | PASS: `92 passed in 0.09s`;补跑原因：S2E plan 要求覆盖 S2A1/S2A2 contract、discovery digest 与 declaration-backed wiring |
| `source .venv/bin/activate && pyright` | PASS: `0 errors, 0 warnings, 0 informations`;另有 pyright 新版本提示，非类型诊断 |
| `git diff --check` | PASS: no output |

## Production Execution Mode Matrix

| Tool family | Production tools | Mode | Validation evidence | Decision |
|---|---|---|---|---|
| Contract / discovery | `ToolDefinition.execution`、`@tool(...)`、ToolsDiscovery digest | Typed capability: default `async_direct`; explicit `thread_backed`; explicit `process_backed` | `tests/contracts/test_tool_declaration.py` 覆盖默认 async direct、thread-backed guard、process context / target / envelope pickle round-trip；`tests/runtime/test_tools_discovery_digest.py` 覆盖 async/thread/process digest shape，且 process target factory identity 不入 digest | Closed |
| Host ToolRuntime | declaration-backed factory and process capsule | Reads `ToolDefinition.execution`; process-backed maps JSON envelope to Host outcome | `tests/host/test_toolruntime_executor.py` 覆盖 production default factory 选择 process-backed、context 投影、completed/failed/malformed/Host-governed envelope、cancel 不等待自然完成、terminate ignored 时升级 kill、timeout governed failure | Closed |
| Doc | `list_files`、`read_file`、`search_files`、`get_document_sections`、`read_document_section` | `process_backed` | `tests/tools/test_doc_tools_provider.py` 覆盖 5 个 definition 声明 process-backed、factory/target pickle round-trip、不携带 provider lock / processor、真实 ToolRuntime cancel 后只 accept `tool_runtime_cancelled`，不接受子进程 late result | Closed |
| Fins read | `list_documents`、`get_document_sections`、`read_section`、`search_document`、`list_tables`、`get_table`、`get_page_content`、`get_financial_statement`、`query_xbrl_facts` | `process_backed` | `tests/fins/test_fins_storage_provider.py` 覆盖 9 个 definition 声明 process-backed、factory/target pickle round-trip、不携带 runtime / repository / provider lock / token、spawned child 重建 `DefaultFinsRuntime`、fast / processor / table path、`get_financial_statement` spawned child、真实 ToolRuntime cancel 后不接受 late result | Closed with low residual on independent real-XBRL spawned-child fixture |
| Fins download / preprocess / upload | `start_fins_download`、`start_fins_preprocess`、`start_fins_upload` | `async_direct` awaiting tool; returns `ToolAwaitingOutcome(EXTERNAL_JOB)` | `tests/fins/test_fins_ingestion_tools.py` 覆盖三类工具返回 `EXTERNAL_JOB`、resume token opaque、只 prepare observation 不提交 executor、启动前 cancel 返回 `ToolCancelledOutcome` 且不注册 job/observation、wait adapter abandon/cancel 分支 | Closed; WAITING 语义保持由 WU-WAIT-03 / activation hook 管理，不纳入 process-backed closeout |
| Web | `search_web`、`fetch_web_page` | `process_backed` | `tests/tools/web/test_web_tools_provider.py` 覆盖 2 个 definition 声明 process-backed、factory/target pickle round-trip、不携带 `requests.Session` / provider lock / token / Host / Browser / Playwright runtime、timeout 标量序列化、真实 spawned child 成功、真实 ToolRuntime cancel 后不接受 late result、Playwright unpicklable worker fail closed | Closed with accepted residuals below |

## Late-result Accept Barrier

- Host generic process capsule coverage remains passing: process-backed cancel returns governed `tool_runtime_cancelled`, does not wait for natural completion, timeout returns governed `tool_runtime_timeout`, illegal child envelopes fail closed, and terminate ignored is escalated to kill.
- Doc process-backed coverage remains passing: real ToolRuntime cancel accepts exactly one governed cancel candidate; the slow child result is not accepted later.
- Fins read process-backed coverage remains passing: real ToolRuntime cancel accepts governed cancel and does not accept late Fins child output.
- Web process-backed coverage remains passing: delayed HTTP server response after cancel does not become accepted tool result; accept port observes only governed cancel.
- Fins awaiting tools intentionally do not use the ordinary completed-result accept barrier. They enter awaiting accept / wait-resume lifecycle and retain `EXTERNAL_JOB` semantics.

No additional aggregate test was added in S2E. The existing focused tests exercise the shared Host accept barrier through the real production `DefaultToolRuntimeFactory` for each migrated tool family, and the generic Host tests cover the common timeout/cancel/kill/error-envelope state machine. A new test that only serializes Doc/Fins/Web calls in one file would duplicate those mechanisms without increasing failure sensitivity.

## Residual Risk Adjudication

| Risk | Current evidence | S2E decision | Owner / destination |
|---|---|---|---|
| Web process cold-start cost | Web uses per-call process-backed execution; tests verify correctness, not performance | Accepted, non-blocking. #87 closeout prioritizes interruptibility and late-result isolation over latency optimization | Later performance work if production telemetry shows material cost |
| Process failed envelope has no structured `hint` field; Doc/Fins/Web preserve hints by appending text into `message` | Tests cover recovery text remains in message; Host capsule contract currently consumes `error_type` and `message` only | Accepted for S2E, not a current fix. Changing the envelope is a Host process contract hardening task, not needed for cancel closeout | Later Host process envelope contract hardening |
| Playwright nested process cleanup under process-backed Web cancel | Web tests cover process-backed Web cancel on requests path, Playwright cancellation projection, pre-cancel no-start, and unpicklable worker fail closed. They do not launch a real browser tree under ToolRuntime cancel | Accepted with explicit residual. Current production no longer falls back to same-process execution, and parent process cancellation still prevents late accept. Full browser process-tree cleanup needs targeted smoke/stress coverage | Later Web/Playwright cleanup smoke or stress test |
| `query_xbrl_facts` is not independently exercised in spawned child with a real XBRL instance fixture | S2C covers all 9 definitions, fast path, processor path, table path, `get_financial_statement` spawned child, and `query_xbrl_facts` cooperative cancellation/filtering. Missing fixture is specific to real XBRL instance parsing inside spawned child | Accepted low residual, non-blocking. Current process-boundary mechanism is proven; the gap is fixture breadth | Later Fins XBRL fixture expansion |
| Doc FIFO fixture broadens `read_file` supported file kind for deterministic blocking test | S2B review accepted because allowed-root boundary remains and risk is bounded by process-backed cancel/timeout | Accepted residual, non-blocking | Later Doc test strategy/security review if product disallows FIFO reads |
| Thread-backed could be mistaken as production non-cooperative cancel evidence | Contract guard is `Literal[False]`; tests verify guard and digest shape | Closed | None |
| Fins WAITING tools are not process-backed | They are not blocking read tools; they return awaiting after registering lightweight observation and are governed by wait activation / poll / abandon lifecycle | Closed as intentional non-goal | WU-WAIT-03 / existing Fins wait lifecycle |

No residual risk remains unclassified.

## README / Design Sync

No README or design file was changed in S2E.

Decision:

- This S2E pass only writes an aggregate review artifact and does not change code behavior, public CLI/Web/WeChat workflow, durable schema, Host public API, Engine schema, tool schema, or user-visible output.
- `tests/README.md` already documents contract execution capability, Doc process-backed late-result tests, Fins read process-backed and Fins awaiting `EXTERNAL_JOB` coverage.
- `dayu/fins/README.md` already documents Fins read production `process_backed` execution and download/preprocess/upload awaiting activation/cancel semantics.
- `dayu/host/README.md` already documents Host-owned ToolRuntime, accept barrier, and Engine-visible schema boundary at the stable developer level.
- Root `README.md` is a final-user manual and is not triggered by this aggregate artifact.
- No separate Web package README exists in scope.

## Stop Condition Status

| Stop condition | Status |
|---|---|
| Typed execution cannot be expressed without raw dict / extra payload | Closed: strong typed `ToolDefinition.execution` exists |
| `dayu.runtime` must import Host / Engine / Service / UI / Fins | Closed: contract/digest/runtime tests pass |
| Host selects process-backed by tool-name branch | Closed: declaration-backed factory tests pass |
| Business tools import Host internals to declare process-backed | Closed: provider definitions declare public contract capability |
| `dayu.runtime.interruptible_process` must return `ToolExecutionOutcome` | Closed: Host capsule maps JSON envelope |
| Process context / target / envelope cannot be pickle round-tripped | Closed: contract, Doc, Fins and Web tests pass |
| Child target returns awaiting / cancelled / timeout / host_cancelled | Closed: unsupported envelopes fail closed; Fins failure envelope tests reject Host-governed values |
| Production critical path relies on `thread_backed` for non-cooperative blocking cancel | Closed: Doc/Fins/Web migrated to process-backed; thread guard covered |
| Process-backed requires parent provider lock / runtime / repository / session capture | Closed: pickle/repr tests and spawned-child tests pass |
| Doc / Fins read / Web sync cannot be process-backed or abort-capable async direct | Closed: all selected process-backed paths pass focused tests |
| Fins spawned-child runtime cannot reconstruct storage-backed read runtime | Closed: `DefaultFinsRuntime.create(...)` spawned-child tests pass |
| Web async_direct close proof missing | Not applicable: S2D chose process-backed |
| Process target cannot serialize and lacks fail-closed path | Closed: pickle tests and Playwright unpicklable worker fail-closed test pass |
| Engine requires capability field | Closed: Engine-facing schema excludes execution capability |
| New pyright errors, test failures, or README trigger unclassified | Closed: validations pass; README/design decision recorded |

## Verdict

S2E aggregate validation passes. S2 production execution mode is coherent across contract, Host ToolRuntime, Doc, Fins read, Web and Fins awaiting tools. Late-result accept barrier coverage is sufficient for Doc/Fins/Web process-backed cancel closeout, and remaining risks are classified as non-blocking follow-up work.

Stop condition: closed.

Next entry point: aggregate review.

READY_FOR_AGGREGATE_REVIEW
