# WU-TOOLS-01-F01-02 Aggregate Deep Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 Migrated Tools Cancellation Propagation And Response |
| gate | aggregate deepreview |
| reviewer | AgentMiMo |
| date | 2026-06-08 |
| design source | `docs/host/design.md`；`docs/engine/design.md` |
| plan | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| review range | accepted plan commit `af3ac6b8` → Slice 5 accepted commit `68f5fd40` |
| uncommitted changes | `docs/host/issues-implementation-control.md` bookkeeping only |

## Scope

本 review 覆盖 WU-TOOLS-01-F01-02 全部 5 个 implementation slices 的生产代码变更与测试变更。Review 范围包含 10 个生产模块和 6 个测试模块，共约 5900 行新增 / 修改。

## Validation

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
```

结果：PASS，113 passed。

```bash
source .venv/bin/activate && pyright
```

结果：PASS，0 errors。

## Core Issue Validation

### 1. CancellationToken 传递审计完整性

| 工具族 | 工具数 | 注入声明 | token 到达业务入口 | 覆盖证据 |
|---|---|---|---|---|
| Fins awaiting | 2 (download, preprocess) | direct callable 消费 context | YES: `context.cancellation_token` → `runtime.start_*(..., cancellation_token=)` | `test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime` (AST guard) |
| Web search | 1 (`search_web`) | `execution_context_param_name="execution_context"` | YES: `_resolve_execution_cancellation_token` → `search_public_web(cancellation_token=)` | `test_search_web_receives_execution_context_and_passes_cancellation_token` |
| Web fetch | 1 (`fetch_web_page`) | pre-existing | YES: pre-existing token path confirmed | existing `test_fetch_playwright_cancel_projects_to_cancelled_failure` |
| Doc tools | 5 (list_files, get_file_sections, search_files, read_file, read_file_section) | `execution_context_param_name="execution_context"` | YES: `_resolve_doc_cancellation_token` → checkpoints | `test_doc_declarations_request_execution_context_injection`；`test_doc_tools_cancelled_before_work_return_tool_cancelled` |
| Fins read | 9 (list_documents, get_document_sections, read_section, search_document, list_tables, get_table, get_page_content, get_financial_statement, query_xbrl_facts) | `execution_context_param_name="execution_context"` | YES: `_resolve_fins_cancellation_token` → `FinsReadRuntime(..., cancellation_token=)` | `test_fins_read_declarations_request_execution_context_injection`；per-tool pre-cancel tests |

结论：**PASS**。全部 18 个已迁移工具均完成 CancellationToken 传递审计，无遗漏。

### 2. 长事务工具取消响应

#### Fins download / preprocess awaiting tools

- **start 前取消**：callable 读取 `context.cancellation_token.is_cancelled()`，若已取消则返回 `ToolCancelledOutcome`，不创建 durable job。
  - 证据：`test_download_tool_cancelled_before_start_returns_cancelled_without_job`；`test_preprocess_tool_cancelled_before_start_returns_cancelled_without_job`
- **job 创建后 submit 前取消**：`start_download` / `start_preprocess` 在 `_start_lock` 内完成 create → checkpoint → submit 三步原子序列。checkpoint 命中取消时调用 `_save_cancelled(start.record)` 标记 job 为 CANCELLED 终态，不提交后台 executor。
  - 证据：`test_download_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit`；`test_preprocess_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit`
- **后台 pipeline 取消**：runtime 已有 `_mark_job_running_or_cancelled`、循环中 cancel check、终态前 `cancellation_requested` check。本 WU 不新增后台 pipeline 逻辑，复用已有 durable cancel 状态机。
- **awaiting accept 前 orphan 窗口**：按 plan 裁决 deferred，R1 residual risk 已记录。

结论：**PASS**。Fins awaiting 工具在 start 前、create 后 submit 前两个关键边界实现取消响应；后台 pipeline 复用已有 durable cancel 状态机。

#### Web search / fetch

- `search_web` 在 adapter 注入后立即 checkpoint；`search_public_web` 在 query/domain normalize 后、每个 provider fallback loop 迭代前、provider result 返回后均做 checkpoint。取消后停止 provider fallback，不尝试后续 provider。
  - 证据：`test_search_web_cancelled_before_provider_returns_tool_cancelled`；`test_search_web_cancelled_between_provider_attempts_stops_fallback`
- `fetch_web_page` 已有 token 传递和 Playwright / HTTP checkpoint，本 WU 确认覆盖。
- 同步 `requests` 调用无法被 token 抢占式中断（R2 accepted residual limitation）。

结论：**PASS**。

#### Doc / Fins read 风险路径 checkpoint

- Doc tools：`list_files` 在 glob 前、文件迭代内、返回前 checkpoint；`search_files` 在 rglob 前、每文件迭代内、processor search / line scan 前、返回前 checkpoint；`read_file` 在每个编码尝试前、readlines 后、range 提取前 checkpoint；`read_file_section` 在 processor 创建前、read_section 前、子章节遍历前 checkpoint。
  - 证据：`test_search_files_cancelled_during_iteration_stops_before_later_scan`；`test_read_file_cancelled_after_first_failed_encoding_stops_fallback`
- Fins read runtime：所有 9 个 read 方法在入口、`_normalize_document_identity`、`_get_or_create_processor`、processor 调用前后、循环内均做 checkpoint。search engine `_execute_query_search` 在策略入口、精确匹配、扩展查询循环内均做 checkpoint。
  - 证据：`test_search_document_cancellation_during_search_stops_before_all_candidates`；`test_read_section_cancelled_before_processor_read_returns_tool_cancelled`；`test_query_xbrl_facts_cancellation_during_filtering_stops_promptly`

结论：**PASS**。checkpoint 密度按风险分级合理覆盖。

### 3. 其它工具 token 传入业务入口

全部 18 个工具均通过 `execution_context_param_name` 声明或 direct context 消费将 token 传入业务入口。参见 Issue 1 审计表。

结论：**PASS**。

### 4. Host cancel 真源保持

- 工具只观察 `CancellationToken`，不维护私有 cancel 状态。
- Fins awaiting job cancel 仍通过 `job_store.request_cancel` / `save_cancelled` / `save_succeeded_or_cancelled` 表达，不新增第二套状态机。
- `_save_cancelled` 设置 `status=CANCELLED, cancellation_requested=True`，与已有 Fins job cancel 状态机一致。
- 后台 pipeline 通过 `_mark_job_running_or_cancelled` 和 `job_store.read_job` 观察 durable cancel 事实。
- `FinsIngestionStartCancelledError` 仅用于 runtime start 方法到 tool callable 的异常传播，不替代 Host cancel 真源。

结论：**PASS**。Host cancel 真源未被替代。

### 5. Awaiting accept 前 orphan job 两阶段启动

按 plan 裁决，本 WU 不实现两阶段启动。当前实现只做 start 前/后 token checkpoint 与 durable cancel bridge。两阶段启动需要先设计 Host awaiting accepted activation contract，已记录为 R1 residual risk，owner/destination 为 WU-WAIT-03 或独立 follow-up。

结论：**PASS（按 plan deferred）**。未擅自扩大 Host wait adapter / Fins runtime contract。

### 6. LLM-facing schema 隔离

- `test_ingestion_tool_schemas_hide_host_internal_fields`：断言 `execution_context` 和 `cancellation_token` 不在 `properties` 和 `required` 中。
- `test_doc_tool_schemas_do_not_expose_execution_context`：断言五个 Doc tools schema 不含 `execution_context` / `cancellation_token`。
- `test_fins_read_tool_schemas_do_not_expose_execution_context`：断言九个 Fins read tools schema 不含治理字段。
- `test_web_audit_matrix_context_injection_and_schema_no_leak`：断言两个 Web tools schema 不含治理字段。
- `test_combined_discovery_returns_single_bundle_without_reserved_names`：断言 combined bundle 全部 definitions 不含治理字段。
- `execution_context_param_name` 是 adapter 注入 metadata，不进入 LLM-facing JSON schema。

结论：**PASS**。`execution_context` / `cancellation_token` / Host 内部治理字段未泄漏到 LLM-facing schema。

### 7. README 触发、测试覆盖、pyright、residual risk

- **README**：`dayu/fins/README.md` 已更新 ingestion runtime cancellation token 签名、`FinsIngestionStartCancelledError` 契约说明、awaiting 流程中 token checkpoint 描述。`tests/README.md` 已更新 Fins awaiting callable 启动前 cancellation 和 runtime create 后 submit 前 cancellation 覆盖描述。其它 README 按触发规则检查后无需更新。
- **测试覆盖**：全部 5 个 slices 均有行为测试覆盖关键取消路径。source-level AST guard 仅用于 `del context` 和 runtime keyword bridge 等行为测试难以直接定位的边界。测试覆盖 >= 80%。
- **pyright**：PASS，0 errors。
- **residual risk owner/destination**：R1 (orphan job / two-stage startup) → WU-WAIT-03 或 follow-up；R2 (non-preemptible I/O) → accepted limitation；R3 (legacy adapter outcome) → adapter contract WU。均有明确 owner/destination。

结论：**PASS**。

## Findings

无 blocking finding。

### Informational Findings

| ID | Severity | 位置 | 描述 | 影响 |
|---|---|---|---|---|
| I-1 | informational | `dayu/fins/ingestion_runtime.py:1049-1068` | `start_download` / `start_preprocess` 在 `_start_lock` 内调用 `_save_cancelled`，而 `_save_cancelled` 内部调用 `job_store.save_job` 可能获取 job store 内部锁。当前实现中 `_start_lock` 与 job store 锁无嵌套持有风险（`_start_lock` 范围内不持有 job store 锁后再获取 `_start_lock`），但后续扩展需注意锁顺序。 | 无当前风险；记录供后续维护参考。 |
| I-2 | informational | `dayu/fins/tools/read_runtime.py` | `_raise_if_fins_cancelled` 在 `_enrich_sections_with_semantic` 的两个 `for sec in sections` 循环中均做 checkpoint，每个 section 一次 `is_cancelled()` 调用。对于超大文档（数千 sections），这会增加常数开销。 | 性能影响可忽略；`is_cancelled()` 是 O(1) 原子读。 |
| I-3 | informational | `dayu/tools/doc_tools.py:868` / `search_engine.py:73` | Doc tools 和 Fins search engine 各自实现了几乎相同的 `_raise_if_*_cancelled` helper 模式（check `is_cancelled()` → 构造 `ToolBusinessError(code="tool_cancelled")` → raise）。按 AGENTS.md "数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取" 约束，理论上可抽取为公共 helper。 | 当前各 helper 的 message 和 hint 有工具族特化差异，且 `dayu.runtime` 不得 import `dayu.tools` / `dayu.fins`，抽取需要先确定公共层位置。不阻塞本次 WU；记录供后续工具取消契约 WU 参考。 |

## Residual Risk Review

| ID | 风险 | plan 裁决 | 当前状态 | Owner / Destination |
|---|---|---|---|---|
| R1 | Awaiting accept 前 orphan job 窗口：job 已 submit 但 Host 尚未 accept awaiting fact。 | Deferred | 本 WU 实现 start 前/后 checkpoint 与 durable cancel bridge，不实现两阶段启动。 | WU-WAIT-03 或独立 follow-up；需先设计 Host awaiting accepted activation contract。 |
| R2 | 同步 requests / filesystem / processor 调用无法被 token 抢占式中断。 | Accepted residual limitation | checkpoint + timeout budget。 | provider-specific runtime owner。 |
| R3 | Legacy adapter 把 `ToolBusinessError(code="tool_cancelled")` 投影为 `ToolFailedOutcome` 而非 `ToolCancelledOutcome`。 | Deferred | 本 WU 保持 stable error code 和 prompt hint，不改 adapter-wide contract。 | 后续独立 tool adapter cancellation contract WU。 |
| R4 | Fins read runtime 内部 search / XBRL helper 深层 checkpoint。 | Plan 要求按风险补 checkpoint | 已在 `_execute_query_search`、XBRL fact loop、section semantic enrichment loop 中补 checkpoint。 | 当前 WU 已覆盖；未覆盖的深层 processor 内部属于 R2 范畴。 |

## Conclusion

**PASS**。

WU-TOOLS-01-F01-02 全部 5 个 slices 的实现满足 plan 定义的全部 success signal：

1. 18 个已迁移工具均有明确 CancellationToken 传递审计结论。
2. Fins awaiting 工具在 start 前、create 后 submit 前实现取消响应，后台 pipeline 复用已有 durable cancel 状态机。
3. Fins job cancel 真源仍为 job store，不新增第二套状态机。
4. Web search 补齐了 execution context 注入与 provider 路径 checkpoint。
5. Doc / Fins read tools 均把 token 传入业务入口，并按风险分级补 checkpoint。
6. Host cancel 真源未被替代。
7. 两阶段启动按 plan deferred，未擅自扩大 Host wait adapter / Fins runtime contract。
8. LLM-facing schema 未泄漏 `execution_context` / `cancellation_token` / Host 内部治理字段。
9. README 已按触发规则更新，测试覆盖充分，pyright clean，residual risks 均有明确 owner/destination。

无 blocking finding。三个 informational findings 不阻塞后续 gate。三个 residual risks 均按 plan 裁决 deferred 或 accepted，有明确 owner/destination。
