# WU-TOOLS-01-F01 Slice S2 Code Review

## Gate Metadata

- Gate: code review only.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S2 - Preprocess / Process Runtime Pipeline`.
- Branch: `host-wu-tools-01-f01`.
- Artifact path: `docs/reviews/wu-tools-01-f01-s2-code-review-ds.md`.
- Scope guard: 本轮只 review Slice S2 实现；禁止修改 production/test/README/control doc，禁止 fix，禁止 commit/push/PR。

## Scope

- Mode: current changes.
- Branch: `host-wu-tools-01-f01`.
- Base: `main`.
- Output file: `docs/reviews/wu-tools-01-f01-s2-code-review-ds.md`.
- Included scope:
  - `dayu/fins/ingestion_runtime.py`
  - `dayu/fins/service_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `dayu/fins/README.md`
  - `tests/README.md`
- Excluded scope:
  - `docs/host/issues-implementation-control.md` — 仅作为 controller bookkeeping 背景，不当实现 bug 审。
  - `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md` — 作为 acceptance criteria 参照源，不审其内容。
  - S1/S3/S4/S5/S6 slices — 不在当前 review scope。
  - 未修改的 `dayu/fins/storage/`、`dayu/documents/processors/` — 仅验证边界合规，不深入内部实现。
- Parallel review coverage: 无（单 reviewer 全覆盖）。

## Validation Commands Executed

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q`
  - 结果: 29 passed, 3 warnings (edgartools deprecation, 非本 slice 引入), 耗时 1.29s。
- `source .venv/bin/activate && python -m pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - 结果: 0 errors, 0 warnings, 0 informations。

## Findings

### F01-S2-001-Medium: `_MAX_PREPROCESS_DOCUMENTS` 限制在文档形态/表单过滤前执行，导致合法有界请求被拒绝

- **入口/函数**: `FinsIngestionRuntime._select_preprocess_documents` → `start_preprocess` → `_run_preprocess_job` → `_execute_preprocess_request`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1025-1027`
- **输入场景**: 对持仓较多（>50 份任意类型 filing）的 ticker 发起 whole-ticker 预处理，但通过 `form_types=("10-K",)` 过滤后实际只需处理 ≤50 份文档。
- **实际分支**: 代码在 `selected_ids = requested_ids or available_ids` 后立即检查 `len(selected_ids) > _MAX_PREPROCESS_DOCUMENTS`（第 1026 行），然后才进入 `is_deleted`/`ingest_complete`/`form_type` 过滤循环（第 1034-1044 行）。限制检查的对象是 **未过滤的全量候选 ID**，而非过滤后的实际待处理 ID。
- **预期行为**: 上限应约束实际会被处理的文档数（即过滤后的 `filtered_ids`），或至少先执行不依赖 `get_source_meta` 的成本低廉过滤，再检查上限。当用户通过 `form_types` 明确缩小范围后，合法请求不应因未过滤集合超限被拒绝。
- **实际行为**: 若 ticker 有 60 份任意 filing，用户请求 `form_types=("10-K",)` 且实际只有 5 份 10-K 时，代码在第 1026-1027 行抛出 `ValueError("预处理文档数量超过上限: 50")`，job 进入 `failed` 终态。
- **直接证据**: 第 1025 行 `selected_ids = requested_ids or available_ids` 使用未过滤全集，第 1026 行 `if len(selected_ids) > _MAX_PREPROCESS_DOCUMENTS: raise ValueError(...)`，第 1034-1044 行的 form_type/is_deleted/ingest_complete 过滤循环在限制检查**之后**执行。
- **影响**: 合法用户请求被错误拒绝，需绕过方案（显式传入 `document_ids`）才能工作。不影响显式 `document_ids` 路径（显式 ID 数量通常远小于 50）。
- **建议改法和验证点**: 将 `len(selected_ids) > _MAX_PREPROCESS_DOCUMENTS` 限制检查移到过滤循环之后、`filtered_ids` 之上。注意 `get_source_meta` 调用次数增加带来的 I/O 成本——对真实大 ticker 可能需考虑分批或 early bail-out。验证点：构造 >50 份 filing 但仅少量匹配 `form_types` filter 的 fixture，确认请求成功且只处理匹配文档。
- **修复风险（低）**: 仅移动一行检查的位置，不改变过滤逻辑和状态写入。需确认 `get_source_meta` 的 N+1 调用在 50+ 文档时不会引入不可接受的延迟。
- **严重程度（中）**: 阻止满足 bounded selection 语义的合法请求，但可通过显式 `document_ids` 绕过，不导致数据丢失或安全漏洞。

### F01-S2-002-Low: `_run_preprocess_job` 中的后台异常处理在 job store 不可用时静默丢失终态

- **入口/函数**: `FinsIngestionRuntime._run_preprocess_job` → `_save_failed_from_exception`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1240-1246`
- **输入场景**: 后台 pipeline 正常执行（已写入 processed 文档），但在 `_run_preprocess_job` 的 post-pipeline 阶段（第 879 行 `self.job_store.read_job(job_id)`）遇到 job store 不可用（磁盘满、权限变更等），或 pipeline 本身抛异常后在 `_save_failed_from_exception` 内部再次 job store 不可用。
- **实际分支**: 外层 `except Exception` 捕获异常后调用 `_save_failed_from_exception`（第 898-899 行）。`_save_failed_from_exception` 在 1240-1246 行读取 job record 并尝试写入 failed 终态，但所有 job store 操作被内层 `except Exception: return` 静默吞掉。
- **预期行为**: 在 job store 暂时不可用时，应有至少一次重试或在 observable 层面暴露"job 终态未持久化"。当前单次 try-except-return 让调用方（daemon 线程）无任何反馈。
- **实际行为**: pipeline 已写入的 processed 产物存在于仓储中，但 job record 停留在 `RUNNING` 状态（若 job store 在 `_mark_job_running_or_cancelled` 之后才变为不可用），或连 `RUNNING` 都没写入（若更早失败）。外部 poll adapter 最终应将 stale `RUNNING` 映射为 `WaitPollLost`，但这依赖于 adapter 的 stale 判定实现（尚在 S5）。
- **直接证据**: 第 1240 行 `try:` 开始，第 1241-1244 行尝试 read + save_failed，第 1245-1246 行 `except Exception: return` 静默吞噬所有异常。
- **影响**: 在极端磁盘故障下，job 终态丢失——processed 数据已写入但 job record 未反映终态。poll adapter 的 stale 检测（future S5）可作为兜底，但这是一个 observable gap。
- **建议改法和验证点**: 考虑在 `_save_failed_from_exception` 中至少做一次 logging/trace 输出，或在 `_run_preprocess_job` 的顶层 `except` 中记录异常证据（即使是 best-effort）。当前项目尚无 ingestion 专用日志通道，可作为 S5/S6 的 observability 补充项。验证点：mock job store 在 save 时抛异常，确认不会导致 daemon 线程崩溃且至少有一条 diagnostic 可见。
- **修复风险（低）**: 仅添加 best-effort 日志，不改变状态机逻辑。
- **严重程度（低）**: 仅在存储层极端故障时触发，且 poll adapter lost 兜底存在（future S5），不造成数据丢失（processed 数据已落地）。

## AGENTS.md / CLAUDE.md 合规检查

| 检查项 | 结果 |
|--------|------|
| 弱类型签名（`Any`/`object`/无类型参数/无类型返回值） | 通过。所有公开函数、dataclass 字段、Protocol 方法均使用具体类型注解（`str`/`int`/`bool`/`JsonValue`/tuple/list/dict 等带参数泛型）。 |
| `hasattr`/`getattr` 滥用 | 通过。diff 中无 `hasattr`/`getattr` 调用。 |
| 魔法字符串/数字 | 通过。所有字面量均定义为模块级 `Final` 常量（如 `_MAX_PREPROCESS_DOCUMENTS`、`_JOB_ID_PREFIX`、`_KEY_JOB_ID` 等）。 |
| 中文 docstring | 通过。所有函数、类、方法均有完整中文 docstring，含参数、返回值、异常。 |
| 分层反向依赖 | 通过。`ingestion_runtime.py` 仅依赖 `dayu.fins.storage`（Protocol）、`dayu.fins.ticker_normalization`（public API）、`dayu.fins.domain`（dataclass）、`dayu.documents.processors`（Protocol）、`dayu.contracts.json_value`（公共契约），均为下层或同层。无 Host/Engine/Service/UI 导入。 |
| 兼容 facade/re-export | 通过。`__all__` 只导出新增类型，无旧名重导出。 |
| Source/processed 读写是否全部走 `dayu.fins.storage` repository protocols | 通过。`_select_preprocess_documents` 通过 `source_repository.list_source_document_ids/get_source_meta`；`_preprocess_one_document` 通过 `source_repository.get_source_meta/get_primary_source` 读取源文档，通过 `processed_repository.create_processed/update_processed` 写入 processed 产物。无直接 `Path("processed/...")` 文件树写入。 |
| `start_preprocess` job lifecycle: queued→running→succeeded/failed/cancelled | 通过。`_create_queued_job` 先持久化 `QUEUED`；`_mark_job_running_or_cancelled` 转 `RUNNING` 或收口 `CANCELLED`；`_save_succeeded`/`_save_failed`/`_save_cancelled` 写终态。后台异常经 `_save_failed_from_exception` 收口为 FAILED。 |
| 取消可靠性 | 通过。`request_cancel` 标记 `CANCELLING`；`_mark_job_running_or_cancelled` 在入 running 前检查取消；per-document 循环在每次迭代前读 job 检查 `cancellation_requested`；post-pipeline 再次检查。终态 job 的 `request_cancel` 原样返回不可回退。 |
| Explicit document_ids 与 whole-ticker bounded selection | 通过（除 F01-S2-001）。`document_ids` 非空时精确匹配；为空时从 `list_source_document_ids` 全量获取并施加 `_MAX_PREPROCESS_DOCUMENTS` 上限。不涉及 ticker parsing/market inference。 |
| Overwrite/rebuild semantics 属于 runtime，不依赖 provider | 通过。`rebuild_processed` 由 `FinsPreprocessRequest` 携带，在 `_preprocess_one_document` 中判断——跳过或 update。provider 层（S4）只透传此 flag。 |
| Processor registry 使用正确性 | 通过。通过 `processor_registry.create_with_fallback(source, form_type, media_type)` 获取 processor；`ValueError`（无可用处理器）转为 `_PreprocessNotSupportedError` 并记录 `not_supported_document_ids`。`unsupported`/`skipped`/`failed` 计数和文档 ID 在 job summary 中业务可读（不含 Host refs）。 |
| README 只同步稳定事实 | 通过。`dayu/fins/README.md` 正确反映了 `ingestion_runtime` 的存在、preprocess pipeline 路径、job store 位置和 download 当前状态（只持久化 queued record）。无未来计划或越界说明。`tests/README.md` 正确反映了 test coverage。 |

## Test Coverage Assessment

| 场景 | 覆盖 | 测试函数 |
|------|------|---------|
| 同 workspace 多 runtime 实例共享 job store | ✓ | `test_default_runtime_instances_share_workspace_job_store_without_singleton` |
| download 持久化 queued + ticker normalization | ✓ | `test_start_download_persists_queued_record_and_uses_public_ticker_normalization` |
| download form_type 允许业务斜杠（10-K/A） | ✓ | `test_start_download_allows_sec_amended_form_type` |
| download source 拒绝路径分隔符 | ✓ | `test_start_download_still_rejects_path_separator_in_source` |
| preprocess 持久化 queued + ticker normalization | ✓ | `test_start_preprocess_persists_queued_record_and_uses_public_ticker_normalization` |
| preprocess document_ids/form_types 允许业务斜杠 | ✓ | `test_start_preprocess_allows_slash_in_document_ids` |
| result summary 允许业务斜杠 | ✓ | `test_result_summaries_allow_slash_in_document_ids` |
| 取消标记 active job + 终态不可回退 | ✓ | `test_request_cancel_marks_active_job_and_keeps_terminal_job_terminal` |
| job record 不泄漏正文/payload/路径 | ✓ | `test_job_records_do_not_expose_payload_bodies_raw_provider_payloads_or_paths` |
| preprocess source → processed pipeline 成功 | ✓ | `test_start_preprocess_processes_source_document_to_processed_repository` |
| rebuild=false 跳过已有 processed | ✓ | `test_start_preprocess_skips_existing_processed_document_without_rebuild` |
| rebuild=true 更新已有 processed | ✓ | `test_start_preprocess_rebuild_updates_existing_processed_document` |
| cancel before execution → cancelled | ✓ | `test_start_preprocess_cancel_before_execution_writes_cancelled_terminal` |
| 缺失文档 → failed terminal | ✓ | `test_start_preprocess_missing_document_fails_terminal_record` |
| 无可用的 processor → not_supported + failed | ✓ | `test_start_preprocess_unsupported_document_records_not_supported_summary` |
| job store atomic replace 失败清理临时文件 | ✓ | `test_job_store_removes_temp_file_when_atomic_replace_fails` |
| 文件锁 flock 失败关闭 stream | ✓ | `test_store_file_lock_closes_stream_when_flock_fails` |
| read tool service 不受 ingestion 影响 | ✓ | `test_default_runtime_keeps_read_tool_service_lazy_singleton` |
| cancel mid-execution（per-document loop 检测） | ✗ | 无。cancel-before-execution 测试使用 `_HoldingExecutor` + `run_all()`，只证明入 running 前的取消路径。per-document 循环内的 `cancellation_requested` 检查与入 running 前检查使用相同机制，但无测试证明 mid-execution break 后 partial result 的正确性。 |
| form_type 过滤选择 | ✗ | 无。fixture 构造时 meta 中包含 `filing_date`/`report_date` 但不包含明确的 `form_type` 字段——`_fixture_markdown` 也不包含。实际的 `form_type` 在 `SourceDocumentUpsertRequest` 中直接传入 `"10-K"`，但 meta 中未写入 `form_type` 键。需要确认 `get_source_meta` 返回的 meta 是否包含 `form_type`。 |
| `is_deleted`/`ingest_complete` 过滤 | ✗ | 无。fixture 不构造 is_deleted/ingest_complete 为 False 的边界场景。 |
| whole-ticker 选择 + 过滤（非显式 document_ids） | ✗ | 所有 preprocess 测试均传入显式 `document_ids`。无 whole-ticker 选择 + form filter 组合测试。 |
| `_MAX_PREPROCESS_DOCUMENTS` 超限 | ✗ | 无。 |

**测试绕过 production boundary 检查**: `test_start_preprocess_unsupported_document_records_not_supported_summary` 通过 `FinsIngestionRuntime.create(...)` 直接构造带空 `ProcessorRegistry` 的 runtime 实例，绕过了 `DefaultFinsRuntime.create` 的装配路径。这是合理的测试做法（直接测试 ingestion runtime 层，不依赖上层装配），且 plan S2 未要求测试必须走 `DefaultFinsRuntime`。

## Open Questions

- 无。

## Residual Risk

- **未覆盖场景**: cancel mid-execution partial result、form_type 过滤选择、`is_deleted`/`ingest_complete` 过滤、whole-ticker selection、`_MAX_PREPROCESS_DOCUMENTS` 超限。这些场景的缺失不会使 S2 不可交付，但 F01-S2-001 修复后必须补齐 `_MAX_PREPROCESS_DOCUMENTS` + form filter 的组合测试。
- **daemon thread 风险**: `FinsIngestionThreadExecutor` 使用 daemon thread。daemon thread 在进程退出时会被强制终止，不保证 job 终态持久化完成。当前设计假设 Host 进程常驻（不频繁退出），且在进程退出前应通过 S5 的 wait adapter 等待活跃 job 终态。若进程异常退出，残留 `RUNNING` job 会在 S5 poll adapter 中映射为 `WaitPollLost`。该风险在 plan 中已识别，不构成 S2 blocking finding。
- **financials 字段**: `ProcessedCreateRequest` 和 `ProcessedUpdateRequest` 的 `financials` 参数当前传入 `None`。plan 和 implementation report 均已记录为 "assigned to later work unit"——现有 processor protocol 没有统一结构化 financials 生产方法。该 residual risk 不影响 S2 preprocess pipeline 的基本正确性（sections/tables/meta 均已正确写入）。

## Verdict

**pass-with-findings**

F01-S2-001（Medium）是真实 correctness issue，影响特定合法请求场景。F01-S2-002（Low）是 edge case observability gap。两项均不构成 merge blocker——F01-S2-001 可通过显式 `document_ids` 绕过，F01-S2-002 有 S5 poll adapter lost 兜底。

所有 plan S2 expected assertions（source→processed pipeline、skip/rebuild、cancel、missing document failed、unsupported processor summary、storage boundary、ticker normalization）均被实现和测试覆盖。AGENTS.md 合规检查全部通过。pyright 零错误。29 tests passed。
