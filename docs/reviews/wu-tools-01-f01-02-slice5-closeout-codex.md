# WU-TOOLS-01-F01-02 Slice 5 Closeout

执行者：AgentCodex

日期：2026-06-08

## 动机判断

Slice 5 的动机成立。Host 是 cancel 治理真源，前四个 slice 已经把 Host 注入的 `BatchToolExecutionContext.cancellation_token` 接入 Web / Doc / Fins read / Fins awaiting 工具边界。本 slice 不应改变 Host cancel 真源、不应实现两阶段启动，也不应修改公共 schema / contract；收口重点是证明迁移工具的 context/token bridge 没有遗漏，且 LLM-facing schema 不暴露治理字段。

## Audit Matrix

| 区域 | 工具 | 结论 | 覆盖证据 |
|---|---|---|---|
| Web | `search_web` | PASS：声明请求 `execution_context` 注入；schema 不含 `execution_context` / `cancellation_token`；行为测试证明 token identity 传入 `search_public_web`，pre-cancel 返回 `tool_cancelled`，provider fallback 间取消会停止后续 provider。 | `tests/tools/web/test_web_tools_provider.py::test_web_audit_matrix_context_injection_and_schema_no_leak`；`test_search_web_receives_execution_context_and_passes_cancellation_token`；`test_search_web_cancelled_before_provider_returns_tool_cancelled`；`test_search_web_cancelled_between_provider_attempts_stops_fallback` |
| Web | `fetch_web_page` | PASS：声明请求 `execution_context` 注入；schema 不含治理字段；行为测试证明 Playwright fallback 收到同一个 token，取消投影为稳定 `tool_cancelled` failure。 | `tests/tools/web/test_web_tools_provider.py::test_web_audit_matrix_context_injection_and_schema_no_leak`；`test_fetch_playwright_cancel_projects_to_cancelled_failure` |
| Doc | `list_files` / `get_file_sections` / `search_files` / `read_file` / `read_file_section` | PASS：五个 Doc tools 全部声明 `execution_context_param_name="execution_context"`；schema 不含 `execution_context` / `cancellation_token`；pre-cancel 行为全部返回 `tool_cancelled`，长循环/编码 fallback 取消由既有行为测试覆盖。 | `tests/tools/test_doc_tools_provider.py::test_doc_declarations_request_execution_context_injection`；`test_doc_tool_schemas_do_not_expose_execution_context`；`test_doc_tools_cancelled_before_work_return_tool_cancelled`；`test_search_files_cancelled_during_iteration_stops_before_later_files`；`test_read_file_cancelled_before_fallback_encoding_returns_tool_cancelled` |
| Fins read | `list_documents` / `get_document_sections` / `read_section` / `search_document` / `list_tables` / `get_table` / `get_page_content` / `get_financial_statement` / `query_xbrl_facts` | PASS：九个 read tools 全部声明 `execution_context` 注入；schema 不含 `execution_context` / `cancellation_token`；行为测试覆盖 pre-cancel、search loop、processor read 前取消、XBRL filtering 取消，以及 cancellation 不被降级块吞掉。 | `tests/fins/test_fins_storage_provider.py::test_fins_read_declarations_request_execution_context_injection`；`test_fins_read_tool_schemas_do_not_expose_execution_context`；`test_list_documents_pre_cancel_returns_tool_cancelled`；`test_search_document_cancellation_during_search_stops_before_all_candidates`；`test_read_section_cancelled_before_processor_read_returns_tool_cancelled`；`test_query_xbrl_facts_cancellation_during_filtering_stops_promptly` |
| Fins awaiting | `start_fins_download` / `start_fins_preprocess` | PASS：direct callable 消费 `BatchToolExecutionContext`，不再 `del context`；source-level guard 锁定 `runtime.start_download/start_preprocess(..., cancellation_token=cancellation_token)`；行为测试覆盖 start 前取消不创建 job、durable create 后 submit 前取消标记 job cancelled 且不提交后台操作、schema 不泄漏 Host 内部字段。 | `tests/fins/test_fins_ingestion_tools.py::test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime`；`test_download_tool_cancelled_before_start_returns_cancelled_without_job`；`test_preprocess_tool_cancelled_before_start_returns_cancelled_without_job`；`test_ingestion_tool_schemas_hide_host_internal_fields`；`tests/fins/test_fins_ingestion_runtime.py::test_download_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit`；`test_preprocess_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit` |

补充说明：source-level guard 只用于 `del context` 与 runtime keyword bridge 这种行为测试难以直接定位的边界；其余矩阵项优先使用 provider/runtime 行为测试。

## README Decision

- `dayu/fins/README.md`：已读取 `Agent更新约束【必须遵守】`。本 slice 只补测试矩阵与 closeout artifact，未修改 `dayu/fins/` 生产代码；前置 slice 已落地的 Fins ingestion runtime cancellation token 签名和 Fins/Host cancel 边界在当前 README 中已有稳定能力说明。本次不更新。
- `tests/README.md`：已读取测试手册职责。当前 README 已说明 `tests/tools/` 覆盖 Web/Doc provider、schema 隔离和 cancellation，`tests/fins/` 已说明 awaiting callable 启动前 cancellation、runtime create 后 submit 前 cancellation、read provider cancellation 响应。本 slice 新增的是同一测试层级下的矩阵式断言，不新增测试目录、测试层级或运行方式。本次不更新。
- `dayu/README.md` / 设计文档：未触及分层关系、装配方式、Host/Engine public contract 或公共 schema，不更新。
- control doc：按派发要求不修改；bookkeeping 由 controller 处理。

## Validation

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q
```

结果：PASS，69 passed。仅出现第三方 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
```

结果：PASS，44 passed。仅出现第三方 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pyright
```

结果：PASS，0 errors / 0 warnings / 0 informations。pyright 提示存在新版本 `1.1.410`，当前环境版本为 `1.1.409`，不影响本次验证。

```bash
git diff --check
```

结果：PASS，无输出。

补充定向验证：

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py::test_web_audit_matrix_context_injection_and_schema_no_leak tests/tools/test_doc_tools_provider.py::test_doc_tool_schemas_do_not_expose_execution_context tests/tools/test_doc_tools_provider.py::test_doc_declarations_request_execution_context_injection tests/fins/test_fins_storage_provider.py::test_fins_read_declarations_request_execution_context_injection tests/fins/test_fins_storage_provider.py::test_fins_read_tool_schemas_do_not_expose_execution_context tests/fins/test_fins_ingestion_tools.py::test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime -q
```

结果：PASS，6 passed。仅出现第三方 `edgar` deprecation warnings。

## Remaining Risks / Residual Owner

| ID | Residual risk | 当前裁决 | Owner / Destination |
|---|---|---|---|
| R1 | Awaiting outcome 被 Host durable accept 前仍存在 orphan job 窗口：job 可能已经 submit，但 Host 尚未接受 awaiting fact。 | Deferred。当前 WU 只做 start 前/后 token checkpoint 与 Fins durable cancel bridge；不实现两阶段启动。 | controller 转入 WU-WAIT-03 或独立 follow-up；需先在 `docs/host/design.md` / `docs/engine/design.md` 设计 Host awaiting accepted activation contract。 |
| R2 | 同步 `requests`、文件系统读、processor/XBRL 内部长阻塞无法被 token 抢占式中断，只能在调用前后或循环边界 checkpoint。 | Accepted residual limitation。当前实现依赖 timeout budget + checkpoint，不伪装物理 abort。 | 后续 provider-specific runtime owner；若需要物理取消，进入 WU-WAIT-03 或专项工具 runtime WU。 |
| R3 | legacy adapter 仍把 `ToolBusinessError(code="tool_cancelled")` 投影为 failed outcome，而不是统一 `ToolCancelledOutcome`。 | Deferred，避免扩大 adapter-wide contract blast radius。 | 后续独立 tool adapter cancellation contract WU。 |

## Closeout

本 slice 未改变 Host cancel 真源、Engine public input、Host wait schema、Fins job schema 或 LLM-facing tool schema。新增断言只锁定当前 cancellation propagation audit matrix，不添加旧 no-context 行为断言。
