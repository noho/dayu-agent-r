# WU-SEMANTIC-OWNERSHIP-01 P3-H S3 implementation - AgentCodex

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S3 - SEC downloader diagnostics, README decision, and aggregate scans`
- Agent: AgentCodex
- Status: implementation complete; waiting for controller validation
- Commit: not created, per user instruction

## Scope judgment

The motivation is valid. `_resolve_user_agent(...)` is the first owner of the missing SEC User-Agent configuration fact and the producer of the downloader diagnostic. A CLI command name is not a downloader fact; command names belong to CLI help/docs. The fix therefore belongs in the downloader warning and its downloader test, not in CLI, Service, Host, Engine, or README text.

## Changed files

- `dayu/fins/downloaders/sec_downloader.py`
  - Removed the CLI command name from the missing SEC User-Agent warning.
  - The warning now references `SEC_USER_AGENT` and caller/deployment configuration only.
  - Fallback `_UNCONFIGURED_USER_AGENT`, rate limit logic, request headers, and download behavior were not changed.
- `tests/fins/test_sec_downloader.py`
  - Added `test_missing_sec_user_agent_warning_names_config_fact`.
  - The test asserts the warning contains `SEC_USER_AGENT` and does not contain the CLI command name, without keeping that command name as a contiguous Fins test source string.
- `docs/reviews/wu-semantic-ownership-01-p3-h-s3-implementation-codex.md`
  - This implementation artifact.

## Tests and validation

- `source .venv/bin/activate && pytest tests/fins/test_sec_downloader.py -q`
  - `47 passed in 5.01s`
- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_sec_downloader.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`
  - `306 passed, 1 skipped, 3 warnings in 15.52s`
  - Warnings are existing `edgar` dependency deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `0 errors, 0 warnings, 0 informations`
  - Pyright reported an available newer version, not a type failure.
- `git diff --check`
  - passed

## Required source scans

- `rg -n "_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_hint_with_diagnostic_refs|hint=policy_decision\\.reason_code" dayu tests`
  - No matches.
- `rg -n "_build_search_web_preferred_summary|_build_search_web_hint|_build_search_web_next_action|_build_search_web_next_action_args|当前没有可直接抓取|优先抓取首选结果正文|未找到可直接抓取正文|首选结果|标题：|日期：|摘要：" dayu/tools/web/web_search_providers.py tests/tools/web`
  - Allowed test-only matches:
    - `tests/tools/web/test_smoke_web_ci.py:248`
    - `tests/tools/web/test_web_tools_provider.py:924`
  - No provider-internal matches.
- `rg -n "preferred_result_summary|next_action|next_action_args|\\\"hint\\\"" dayu/tools/web/web_search_providers.py`
  - No matches.
- `rg -n "web_cancellation_text|WEB_CANCELLED_HINT" dayu/tools/web tests/tools/web`
  - Allowed matches in projection owner / consumer / tests:
    - `dayu/tools/web/web_tool_projection_text.py`
    - `dayu/tools/web/web_tools.py`
    - `tests/tools/web/test_web_tools_provider.py`
  - No obsolete `web_cancellation_text.py` module/import match.
- `rg -n "_WEB_SEARCH_CANCELLED_MESSAGE|_WEB_FETCH_CANCELLED_MESSAGE|当前工具调用已停止|搜索工具调用已取消|抓取工具调用已取消" dayu/tools/web/web_tools.py`
  - No matches.
- `rg -n "请检查 Fins ingestion|如仍需要该财报资料|Fins operation was cancelled before completion|_DIRECT_CANCELLED_MESSAGE|_DIRECT_FAILURE_TITLE|_DIRECT_SUCCESS_TITLE|_DIRECT_ERROR_TEXT_FALLBACK|下载准备中|下载已开始|下载已完成|下载已完成，存在失败候选|预处理准备中|预处理已选择源文档|预处理源文档已开始|预处理源文档不支持|预处理源文档失败|预处理源文档已完成|预处理源文档已跳过|预处理请求已完成|上传准备中|上传已开始|上传已完成|上传已完成，存在失败|操作已取消|操作完成|操作失败|执行失败|下载失败|预处理失败|上传失败|下载请求未写入任何源文档|没有任何请求文档完成预处理|上传运行时返回失败状态" dayu/fins/ingestion_runtime.py dayu/fins/ingestion/wait_adapter.py`
  - Allowed non-projection docstring matches:
    - `dayu/fins/ingestion_runtime.py:441` exception documentation for source-side download failure.
    - `dayu/fins/ingestion_runtime.py:4037` exception documentation for processor execution failure.
  - No direct-stream or wait-outcome hardcoded prose matches.
- `rg -n "_append_job_event_warn|已记录取消请求|job 已进入队列|job 已开始执行|job 已取消|job 已成功完成|job 已失败|job 状态未终结" dayu/fins/ingestion_runtime.py`
  - Expected legacy job sidecar matches retained; see sidecar section below.
- `rg -n "dayu-cli init|dayu-cli" dayu/fins/downloaders tests/fins`
  - No matches.

## README decision

- Read `dayu/fins/README.md` update constraints.
  - No update made. This slice changes an existing downloader diagnostic and does not add a stable Fins developer-facing boundary beyond the already documented direct stream / awaiting observation split.
- Read `tests/README.md` update constraints.
  - No update made. The new test is an ordinary assertion in an existing Fins downloader test file and does not add a new durable testing layer or responsibility.
- Root `README.md` and `dayu/README.md` were not read or changed because S3 does not change user commands, public workflow, package layering, or cross-package architecture, and the plan expected no update.

## Retained Fins job sidecar text

Retained matches in `dayu/fins/ingestion_runtime.py`:

- `_append_job_event_warn(...)`
- `已记录取消请求`
- `job 已进入队列`
- `job 已开始执行`
- `job 已取消`
- `job 已成功完成`
- `job 已失败`
- `job 状态未终结`

Reason retained: these messages are written as legacy job event sidecar/audit entries and are read through `read_job_events(...)`. Source inspection found no Service direct or wait adapter consumer of `read_job_events(...)`; `dayu/fins/ingestion/wait_adapter.py` does not consume these job event messages. They were not counted as direct-stream or wait-outcome copy and were left unchanged.

## Propagation audit

- Web search path:
  - Producer: search provider returns provider/result facts only.
  - Projection owner: Web search projection owns `preferred_result_summary`, `next_action`, `next_action_args`, and `hint`.
  - Tool outcome: `completed_outcome` contains projected JSON.
  - LLM-visible path: Engine tool message receives projected tool result; provider internals do not own LLM instructions.
- Web cancellation/declaration path:
  - Declaration owner: `@tool(...)` declarations in `web_tools.py` retain declaration-local display metadata.
  - Projection text owner: `web_tool_projection_text.py` owns cancellation/recovery copy.
  - Tool schema/outcome: `web_tools.py` consumes helper constants for cancellation outcomes.
  - LLM-visible path: cancelled tool outcome hint/message contains helper text only.
- Fins direct path:
  - Producer: runtime emits typed operation/status/count/payload facts.
  - Projection owner: Fins direct/wait text helper supplies direct progress/result text.
  - User-visible path: Service/CLI direct stream consumes `FinsEvent` text derived from helper.
- Fins job sidecar path:
  - Producer/owner for this WU: runtime job lifecycle/audit code retains legacy sidecar text.
  - Destination: durable job event/audit sidecar via `read_job_events(...)`.
  - Audit result: retained sidecar messages are not direct-stream or wait-outcome cleanup targets.
- Fins wait path:
  - Producer: observation snapshot carries status/result/error facts.
  - Adapter: wait adapter maps typed facts to Host wait outcome and consumes helper for LLM-facing hint/message.
  - LLM-visible path: resumed tool result gets helper text, not adapter-owned hardcoded recovery prose.
- SEC diagnostics path:
  - Producer: downloader reports missing `SEC_USER_AGENT` / caller configuration fact.
  - CLI/user docs: command names remain only in CLI/docs owner.
  - User-visible path: downloader warning no longer leaks CLI command names.

## Residual risk

- No unclassified residual risk remains for S3.
- Source scans are bounded evidence checks, not exhaustive proof for every possible prose owner. Current slice did not introduce new LLM-facing or UI-facing text outside the downloader diagnostic.
- Remaining `edgar` deprecation warnings are third-party dependency warnings and not caused by this slice.
