# Deep Review — `dayu-cli download` Aggregate (WU-CLI-DOWNLOAD-01)

## Gate 状态

- **Reviewer**: AgentDS（独立 review，不采信任何其它 reviewer 结论）。
- **基线**: `bad90963abad48d29b5571d44a1cd9a80e0e2d77`（github/main）。
- **HEAD**: `9e30896accb28c44a647b57612b24ac5e50e3ce0`（codex/download-oracle）。
- **HEAD 构成**: 四 slice 实现提交（到 `5f5b1994`）+ 文档 closeout 提交 `9e30896a`（`README.md`、`dayu/fins/README.md`、`tests/README.md` 及三份 closeout artifact）。
- **日期**: 2026-08-10。
- **类型**: 四 slice 实现 + 文档 closeout 后的 aggregate deep review。
- **验证方法**: 独立全 diff 阅读（基线到 HEAD 115 文件）、完整 production/test/doc 文件读取、关键路径 grep/AST 枚举、pyright 全仓校验、595 个 affected union tests 运行通过。
- **结论**: **PASS** — 5 个 findings，其中 0 个 correctness/stability blocking、4 个 LOW severity、1 个 MEDIUM severity（未拦截 pass）。

---

## 1. Adversarial Failure Pass — DL-F01～DL-F11 逐项闭合

### DL-F01：静态输入校验发生在 workspace 副作用前

**证据**：`dayu/cli/commands/fins.py:224` `_prevalidate_download_request(args)` 先于 `:225` `_resolve_workspace_root(args.workspace_root)` 和 `:226` `FINS_DIRECT_SERVICE_FACTORY(workspace_root)` 执行。`build_direct_download_request` 在 `dayu/service/fins_direct.py:466` 调用 `build_fins_download_request`（真源在 `dayu/fins/download_contract.py:596`），其中 `_parse_single_ticker`（`:641`）校验 ticker 非空、长度、CSV 拒绝；`_parse_form_types`（`:667`）校验数量和业务取值；`_parse_date_bound`（`:708`）校验日期格式和展开。任何校验失败抛 `FinsDownloadUsageError`，在 `run_fins_direct_command:195` 捕获并返回 `EXIT_USAGE_ERROR`（exit 2）。此时 workspace 尚未 resolve、Fins storage 未初始化。

**静态证据**：`rg -n "rebuild_processed" dayu/fins/storage/_fs_storage_infra.py` 返回 0 hits — storage 构造不涉及下载 schema。

**结论**: PASS。

### DL-F02：单 ticker，CSV 拒绝

**证据**：`_parse_single_ticker` 在 `download_contract.py:659` 拒绝包含逗号（半角/全角）的输入。`build_direct_download_request` —> `build_fins_download_request` 路径不调用 `_parse_ticker_csv`。`_parse_ticker_csv`（`fins.py:1044`）保留原 CSV/alias 语义，仅被 `upload_filings_from:289`、`upload_filing:626`、`upload_material:658`、`process:695`、`process_filing:720`、`process_material:745` 使用 — 全部是 upload/preprocess 路径。argparse 的 last-wins 行为保持不变，由 argparse 自身机制保证。

**静态证据**：
- `rg -n "_parse_ticker_csv" dayu/cli/commands/fins.py` 返回 6 处，无一处是 download 路径。
- `_prevalidate_download_request` 不调用 `_parse_ticker_csv`。

**结论**: PASS。

### DL-F03：显式日期窗口不被 SC13 补拉扩大

**证据**：`FinsDownloadDateRange`（`download_contract.py:512`）携带 `start_is_explicit: bool`、`end_is_explicit: bool`。`build_fins_download_request:630-633` 把 `start is not None` / `end is not None` 机械映射为 explicit 标记。`FinsDownloadDateRange.__post_init__:528` 校验 explicit 要求对应 bound 非空、start <= end。该 typed fact 从 `FinsDownloadRequest.date_range` 经 adapter 传入 SEC pipeline/workflow 下层，不从中游日期值反推。

**静态证据**：`rg -n "start_is_explicit" dayu/fins/download_contract.py dayu/fins/pipelines/sec_pipeline.py` — 该字段从 contract 穿透到 SEC download stream 参数签名。

**结论**: PASS。

### DL-F04：普通 download 不删除历史 filing

**证据**：
- `rg -n "cleanup_stale|_cleanup_stale_filing_dirs" dayu/fins/pipelines/sec_download_workflow.py` 返回 0 hits — 旧的 stale cleanup 调用已被删除。
- `FilingMaintenanceRepositoryProtocol.cleanup_stale_filing_documents` 仍在协议中（`repository_protocols.py:1280`），但 download workflow 不再调用。若未来有显式 prune 操作可用，不在本 WU 范围。
- diff head 中 `sec_download_workflow.py` 删除了 `_cleanup_stale_filing_dirs` 调用，新增了 whole-tree repair preflight + post-repair mutation 调用。

**结论**: PASS。

### DL-F05：`--rebuild` 不修改 processed

**证据**：
- `FinsDownloadRequest.rebuild_local_artifacts:593` 替换了旧的 `rebuild_processed`。
- `rg -n "rebuild_processed" dayu/fins/download_contract.py dayu/fins/pipelines/sec_rebuild_workflow.py dayu/fins/pipelines/cn_download_rebuild.py dayu/fins/pipelines/sec_download_workflow.py dayu/fins/pipelines/cn_download_workflow.py dayu/fins/pipelines/sec_pipeline.py dayu/fins/pipelines/cn_pipeline.py | grep -v "preprocess"` — download 路径 0 hits。
- `ingestion_runtime.py` 中的 `rebuild_processed` 仅在 `FinsPreprocessRequest:484`、preprocess builder `:3194`、preprocess adapter call `:3678` 和 preprocess helper `:4251` — 全部属于 preprocess/upload owner，不是 download。
- `sec_rebuild_workflow.py` 和 `cn_download_rebuild.py` 是 `rebuild_local_artifacts=True` 时调用的 local rebuild 路径 — 不访问远端、不改 source bytes、不改 processed。

**结论**: PASS。

### DL-F06：CN/HK missing period 不计入 discovered/skipped

**证据**：`cn_download_workflow.py:564` `_resolve_missing_periods(requested, selected)` 计算 `requested - {candidate.fiscal_period}` 集合差。`:237` `missing_periods = _resolve_missing_periods(periods.target_periods, selected)` 把 missing periods 作为独立 tuple，不构造 synthetic filing result。`:371` 传递给 `FinsDownloadResultSummary` 的 `missing_periods`。`FinsDownloadResultSummary.__post_init__:297` 校验 `discovered == sum(downloaded, skipped, rejected, failed)`，missing periods 不参与计数。`rg -n "missing_period" dayu/fins/pipelines/cn_download_workflow.py` 显示 `missing_periods` 只在 summary 和 `_SUM_FIELDS` 中使用，不出现在四类 disposition count 中。

**结论**: PASS。

### DL-F07：SEC UA 配置与日志隐私

**证据**：
- `sec_downloader.py:2294` `_resolve_user_agent` 只解析一次（在 constructor `:1098`）。未配置时返回 `SecUserAgentState.UNCONFIGURED, None` 并发出 warning（`:2317`），warning 只含 `configured=false` 和环境变量名 `SEC_USER_AGENT`，不含 contact 原文。
- `_:2335` `_build_headers` → `if self._user_agent_state is SecUserAgentState.UNCONFIGURED: raise SecUserAgentConfigurationError()` — 首次 HTTP 前 fail closed。
- `_:1104` 和 `_:1181` 的日志只记录 `configured=true/false`，不记录 `self._user_agent` 值。`self._user_agent` 仅在 `_:2340` 用于构造 HTTP header。
- `SecUserAgentConfigurationError`（`download_contract.py:137`）继承 `FinsDownloadProviderError`，使用 `UNCONFIGURED` transport category 和中文 safe message。
- `sec_downloader.py:1176-1178` `configure()` 方法检查 `configured_value` 是否与构造时不同，若不同则抛 `ValueError`，防止二次装配产生重复 warning。

**结论**: PASS。

### DL-F08：同 ticker 并发使用 blocking writer lock

**证据**：
- `_fs_storage_infra.py:1510-1512` `_acquire_ticker_lock` 使用 `blocking=True` — 不再 `blocking=False` fail-fast。
- `_:217` `_acquire_storage_lock_token(lock_path, blocking=True)` 调用 `file_lock(lock_path).acquire()` 无超时 — 阻塞直到锁可用。
- 旧的 `_:200` 非阻塞路径仅在 recovery `_:1877` 使用（`blocking=False`）— `_try_acquire_recovery_ticker_lock` 仍保持非阻塞 skip，不改变全局语义。
- `_:1280` commit/rollback 后 `self._batch_condition.notify_all()` 释放等待者。
- `_:1463` `_acquire_lock_token` 统一入口。

**结论**: PASS。

### DL-F09：CLI 不抢占 Fins terminal，Docling 在独立进程边界

**证据**：
- `fins.py:755` `_wait_for_terminal_handling_sigint` — SIGINT 时只 `cancellation_token.request_cancel("keyboard_interrupt")` (`:795`)，不调用 `event_task.cancel()`，不本地合成 exit 130。
- `_:784` `return await event_task` — terminal 来自 Fins owner。
- `_CliDirectLocalExit` dataclass 已从 `fins.py` 删除。旧 `render_fins_direct_local_exit_after_cancel` 虽仍在 `output.py` 定义但不再被 import。
- `ingestion_runtime.py:2707` `_run_direct_stream` 创建 `operation_task`，保存 thread/queue pump ownership。`:2765` `_run_direct_stream_operation` 是唯一拥有 producer thread 的 owner。
- `_:1298-1302` `_DirectStreamCancellationState.claim_terminal` — 若已请求取消，原子优先返回 `CANCELLED`；若 terminal 已决则返回 `None`。
- `cn_docling_process.py:124-173` `ProcessCnDoclingConversionRunner.convert_pdf_to_docling_json` — 使用 `InterruptibleProcessHandle.start()`（不是 `.spawn()`），在 `system-temp` 唯一目录下运行，terminate→kill 升级（2.0s grace → 1.0s kill），close 后 `finally` 清理 temp tree。child 成功后才发 `CONVERSION_COMPLETED`（`:150` cancel checkpoint 之后）。

**静态证据**：
- `rg -n "asyncio.to_thread" dayu/fins/pipelines/` — 0 hits，旧的 `asyncio.to_thread(convert_pdf_to_docling_json, ...)` 已删除。
- `rg -n "\.spawn\(" dayu/fins/pipelines/cn_docling_process.py` — 0 hits，只使用 `handle.start()`。
- `rg -n "InterruptibleProcessHandle(" dayu/fins/pipelines/cn_docling_process.py` — 1 hit，`:130`，使用公开构造函数和 `.start()`。

**结论**: PASS。

### DL-F10：source integrity mismatch 自动修复

**证据**：
- `source_integrity.py:46-76` `SourceIntegrityClassification` — 三种封闭状态 `MISSING/COMPLETE/REPAIR_REQUIRED` 和三种修复原因 `PHYSICAL_FILE_MISSING/SIZE_MISMATCH/DIGEST_MISMATCH`。
- `_:167` `has_same_source_publication_identity` — 比较 revision 是否相同。
- `_:193` `classify_source_integrity_preflight` — 基于完整 inventory 计算 repair disposition：single selected repair、clean 或 error（multiple/unselected/rejected repair）。
- `sec_download_filing_workflow.py:230` Phase A `classify_source_integrity`（published）→ `:242` `COMPLETE && !overwrite` → fast skip 不发网络请求 → `:270` `REPAIR_REQUIRED` 强制进入 repair → `:494` Phase B `classify_staged_source_integrity`（staged）→ `:501` identity comparison。
- `cn_download_filing_workflow.py:164` CN 同样实现两阶段。
- 两个 workflow 均使用 `_MAX_SOURCE_IDENTITY_ROUNDS = 3` 限制 revision churn。
- `sec_download_workflow.py:583` whole-tree preflight 排定 repair target 优先执行 → `:685` post-repair 重新 preflight 验证 → 若仍有 `SelectedSourceRepairRequired` 抛 `SourceIntegrityRevisionConflictError`。

**结论**: PASS。

### DL-F11：typed final summary 自足展示

**证据**：
- `download_contract.py:276` `FinsDownloadResultSummary` — owner 保留完整 operation-local rows。`from_document_rows:367` 从 rows 派生 counts（同源）。
- `direct_events.py:344` `FinsDownloadPublicSummary` — bounded public projection，含 `source`、`canonical_ticker`、`effective_filters`、counts、`document_rows`（最多 10）、`missing_periods`、`omitted_count`、`terminal_disposition`。`__post_init__:388` 校验 counts 与 rows 一致性和 disposition 映射。
- `output.py:427` `_print_download_summary` 从 `FinsDownloadPublicSummary` 机械投影 — 不 import `dayu.fins.storage`，不扫描私有文件系统。
- `_:457-463` 逐行输出 document rows 和 missing periods。
- `_:491` `_print_download_failure` 投影 closed `FinsPublicFailure`。
- `rg -n "from dayu\.fins\.storage" dayu/cli/output.py` — 0 hits。

**结论**: PASS。

---

## 2. 分层、反向依赖与 semantic ownership

- `dayu/fins/download_contract.py` — 只依赖 `dayu.contracts.json_value`、`dayu.fins.domain.filing_semantics`、`dayu.fins.ticker_normalization`；不依赖 `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`。
- `dayu/fins/storage/source_integrity.py` — 只依赖 `dayu.fins.domain.document_models` 和 `dayu.fins.domain.enums`；不依赖 CLI、Service、Engine、Host。
- `dayu/fins/pipelines/cn_docling_process.py` — 依赖 `dayu.runtime.interruptible_process`（层中立 runtime）、`dayu.documents.docling_runtime`（文档转换）；不把 Fins 业务语义下沉到 runtime。
- `dayu/runtime/interruptible_process.py` — 0 import from `dayu.fins`/`dayu.host`/`dayu.engine`/`dayu.service`/`dayu.ui`。
- `dayu/cli/commands/fins.py` — 不 import `dayu.fins.storage`。
- `dayu/cli/output.py` — 不 import `dayu.fins.storage`。

所有 module owner boundary 清晰，无反向依赖，无 semantic ownership drift。

**结论**: PASS。

---

## 3. 取消/terminal race 检查

- `_DirectStreamCancellationState.claim_terminal`（`ingestion_runtime.py:1298`）：原子锁保护下，若 `_cancellation_requested` 则返回 `CANCELLED` 而非 requested_status；若 terminal 已决返回 `None`。单一 owner、单一写者。
- CLI `_wait_for_terminal_handling_sigint:795` 只幂等 `cancellation_token.request_cancel`，不调用 `event_task.cancel()` 或本地合成 exit 130。
- `_run_direct_stream:2761` finally 中若 `operation_task` 未完成，先 `cancellation_state.request_consumer_abort()` 再由 `await asyncio.shield(operation_task)` 等待 producer cleanup。
- `_cancel_and_drain_fins_event_task:812` 处理 consumer exception 时的 event_task cancel 和 drain，保持 primary error 身份。
- `ProcessCnDoclingConversionRunner:176` `_wait_for_conversion`：取消时先 `terminate(grace=2.0s)` → 仍未退出 `kill(grace=1.0s)` → 仍未退出抛 `RuntimeError`。cleanup 异常记录为 bounded warning 不覆盖 primary outcome。
- 测试覆盖：`test_direct_download_very_early_cancel_skips_adapter_and_joins_thread`、`test_direct_cancel_wins_late_provider_failure_and_exhausts_after_join`、`test_direct_terminal_state_is_atomic_and_ignores_late_cancel_or_result`、`test_cli_stream_owner_sigint_waits_for_canonical_cancelled_terminal`、`test_cancel_race_does_not_override_terminal_result` 等。

**结论**: PASS。取消前终态/终态前取消两种路径均有唯一 owner 裁决，无 race。

---

## 4. Storage atomicity/concurrency 检查

- `_acquire_ticker_lock(blocking=True)` — 阻塞等待同一个 ticker 的 writer。
- `begin_batch` → staging → commit/rollback → writer/release + notify_all — 所有路径释放。
- recovery path `_try_acquire_recovery_ticker_lock(blocking=False)` — 保持非阻塞 skip。
- lock 顺序：local reservation → cross-process ticker writer → staging → publication guard。
- 所有外部 I/O（HTTP、PDF、Docling）发生在 `begin_batch` 之前或 commit 之后，不在 writer lock 区间（由 AST/call-graph 验证）。
- commit/rollback 均终态消费 token，finally 确保 release。
- `_MAX_SOURCE_IDENTITY_ROUNDS = 3` 限制 integrity repair 的 revision churn。

**Residual risk（已知且记录在 plan §11）**: 底层文件系统永久 I/O 卡死可导致 blocking writer 无限等待；不引入业务 timeout 解决。该 risk 在 plan 中明确为 residual。

**结论**: PASS。

---

## 5. Secret/contact 泄露检查

- `sec_downloader.py:1104` 日志 `configured=true/false`，不记录 `self._user_agent` 值。
- `_:1181` 同样只记录 boolean state。
- `_:2317` warning 只含 `configured=false` 和环境变量名 `SEC_USER_AGENT`。
- `_:2340` `self._user_agent` 仅用于 HTTP header 构造。
- `cn_docling_process.py:297` cleanup warning 只记录 `stage`、`error_type`（`type(error).__name__`），不含 temp 路径、PDF 内容或绝对路径。
- `download_contract.py:801` `_validate_public_text` 拒绝 `://`、绝对路径、`raw payload`、`provider payload`。
- `direct_events.py` 所有 public text 均经过 `_validate_safe_text` 校验。
- `output.py:466` `_download_document_line` — `artifact_locator` 显示为 workspace-relative POSIX 路径，不含绝对前缀。
- `rg -n "@sec\.gov|@cninfo|@hkex|User-Agent:|mailto:|phone|邮箱|联系电话" dayu/cli/output.py dayu/fins/direct_events.py dayu/fins/download_contract.py dayu/fins/pipelines/cn_docling_process.py` — 0 hits。

**结论**: PASS。

---

## 6. 过度设计检查

- 三个新增 production 模块各有唯一缺失 owner：`download_contract.py`（typed 下载请求/结果）、`source_integrity.py`（完整性分类）、`cn_docling_process.py`（Docling 进程边界）。无 generic framework。
- 复用 `InterruptibleProcessHandle.start/wait/terminate/kill/close` — 不新增 `spawn()` wrapper。
- 复用 `SecDownloader` 既有 `_SecThrottleState` + shared state file + file lock — 不新增 source-wide 限流。
- `FinsDownloadPublicSummary` 覆盖用户已要求事实，最多 10 行文档、240 字符文本 — 不建 observability 平台。
- Host/Engine 零 diff — 无 contract 变化。

**结论**: PASS。

---

## 7. 测试 owner contract 检查

- 测试均通过 typed contract 入口而非 mock internal state：
  - `test_fins_ingestion_runtime.py` — 通过 `FinsDownloadRequest` / `FinsResultSummary` / `ValidatedFinsEventStream` 验证。
  - `test_sec_pipeline_download.py` — 通过 `SecPipeline.download_stream` 验证，断言 typed document rows、counts 不变量。
  - `test_cn_docling_process.py` — 通过 `ProcessCnDoclingConversionRunner.convert_pdf_to_docling_json` 验证 process boundary。
  - `test_fins_storage_atomicity.py` — 通过 `SourceDocumentRepositoryProtocol` 验证 integrity classification、writer concurrency。
- 595 passed、0 failed、pyright 0 errors/0 warnings。
- 测试不使用 `asyncio.sleep` 猜测时序 — concurrent tests 使用 `threading.Event`/`asyncio.Event` barrier。
- 测试 factory 继承 production wrapper（`FsSourceDocumentRepository`），无 standalone Protocol 山寨实现。

**结论**: PASS。

---

## 8. Findings

### F-DS-01: `render_fins_direct_local_exit_after_cancel` 死代码（LOW）

- **文件/行号**: `dayu/cli/output.py:279-293`、`:589`（`__all__`）。
- **严重级别**: LOW。
- **根因**: 移除 CLI 本地合成 exit 130 行为后（DL-F09），该函数不再被任何模块 import（`rg "render_fins_direct_local_exit_after_cancel" dayu/ --include="*.py" | grep -v "output.py"` 返回 0 hits），但函数定义和 `__all__` 导出仍保留。
- **触发路径**: 当前无触发路径（死代码）；若未来有人重新 import 则恢复旧的 local exit 行为（越过 Fins terminal owner）。
- **修复建议**: 删除 `render_fins_direct_local_exit_after_cancel` 函数、其使用的 `_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE` 常量（`:59`），并从 `__all__` 中移除。这是 DL-F09 修复的完成性清理。

### F-DS-02: `__all__` 导出未使用的 `render_fins_direct_local_exit_after_cancel`（LOW）

- **文件/行号**: `dayu/cli/output.py:589`。
- **严重级别**: LOW。
- **根因**: 同上。`__all__` 包含已去除但未清理的符号，违反"禁止兼容性导出"规则。
- **触发路径**: 对外部 import 者仍然可见，可能被误用。
- **修复建议**: 同 F-DS-01。

### F-DS-03: `SecDownloader.configure()` 允许二次无操作调用（LOW）

- **文件/行号**: `dayu/fins/downloaders/sec_downloader.py:1177-1178`。
- **严重级别**: LOW。
- **根因**: `configure()` 在 `configured_value` 与 `self._user_agent` 相同时允许无操作调用（`if configured_value and configured_value != self._user_agent` — 当 `configured_value` 为 `None` 或相等时通过）。虽然当前 production 调用路径只调用一次，但 protocol 未禁止二次调用。这不产生重复 warning（warning 只在 constructor 发一次），但 `configure()` 的设计意图是"一次性配置"（异常文案如此声称），实际实现却允许相同值的二次调用。
- **触发路径**: 无人为路径触发实际危害；语义不一致。
- **修复建议**: 要么将异常文案改为"配置不可更改"并拒绝任何二次调用（包括相同值），要么更新 docstring 允许相同值的幂等调用。当前实现与 docstring 语义一致（只拒绝不同值），但异常消息误导。

### F-DS-04: `cn_pipeline.py:1421` `_required_cn_text_list` 的 loose parsing risk（LOW）

- **文件/行号**: `dayu/fins/pipelines/cn_pipeline.py:1421`。
- **严重级别**: LOW。
- **根因**: `_required_cn_text_list(result, "missing_periods")` 把 JSON list 元素转为字符串，未对每个 period 做 `_validate_public_text`。period 值来自 `cn_download_workflow.py:_resolve_missing_periods` 的集合差计算，其输入 `item.fiscal_period` 为 provider 返回值。虽然 `FinsDownloadResultSummary.__post_init__` 对 each period 调用了 `_validate_public_text`，但如果 cn_pipeline.py 的 strict projection helper 直接读取原始 result dict 并构造 summary 时使用了 `_required_cn_text_list` 的返回值，该值未在 pipeline 层校验。
- **触发路径**: provider 返回意外长文本或非法字符时，pipeline strict projection 可能在到达 summary constructor 之前就接受了脏数据（取决于具体的调用链）。但 `FinsDownloadResultSummary.from_document_rows` 最终仍会调用 `_validate_public_text` 作为最后防线 — 只是失败时机从 pipeline projection 延迟到了 summary constructor。
- **修复建议**: 在 `_required_cn_text_list` 调用后对每个 period 增加 `_validate_public_text`（需 import），或直接在 `cn_pipeline.py:1422-1428` 的 summary constructor 调用前显式校验。实际风险低因为 `FinsDownloadResultSummary` constructor 是最终 fail-closed 防线。

### F-DS-05: 并发同 ticker blocking writer 无上界等待（MEDIUM — residual，非实现缺陷）

- **文件/行号**: `dayu/fins/storage/_fs_storage_infra.py:1512`。
- **严重级别**: MEDIUM — 但这是 plan §11 明确记录的 residual risk，非实现遗漏。
- **根因**: `_acquire_ticker_lock(blocking=True)` → `file_lock(lock_path).acquire()` 无超时，底层文件系统 I/O 永久卡死会导致 writer 无限阻塞。当前设计有意不引入任意业务 timeout（否则违反 DL-F08 "不能把普通并发请求作为业务错误拒绝"）。
- **触发路径**: OS/文件系统级故障（NFS hang、kernel bug 等），非正常使用路径。
- **缓解**: commit/rollback 后的 `notify_all` 确保正常路径释放；OS lock 在进程 crash 时由 kernel 释放。`begin_batch` 前所有远端 I/O 已完成，transaction 只含本地 staging/publication，因此正常 commit 时间极短。
- **修复建议**: 不修。已在 plan §11 列为 residual risk。若未来需要可考虑增加一个极大的 safety timeout（如 30 分钟）并产生 typed diagnostic 而非业务失败，但超出本 WU 范围。

---

## 9. 审查覆盖清单

| 维度 | 状态 | 证据 |
|---|---|---|
| DL-F01..DL-F11 闭合 | PASS | §1 逐项 direct code/grep/diff evidence |
| 分层与反向依赖 | PASS | §2 — 4 个关键模块、runtime 隔离、CLI 隔离 |
| Semantic ownership drift | PASS | typed contract 单真源，无下游反推 |
| 取消/terminal race | PASS | §3 — claim_terminal atomic、CLI 只 request、Docling terminate→kill |
| Storage atomicity/concurrency | PASS | §4 — blocking writer、统一 release/notify、锁顺序固定 |
| Secret/contact 泄露 | PASS | §5 — UA log boolean only、cleanup 不含路径、validate_public_text gate |
| 过度设计 | PASS | §6 — 3 个新模块各有唯一缺失 owner |
| 观察基础设施扩张 | PASS | 无新增 observation/generic framework |
| 测试 owner contract | PASS | §7 — typed contract 入口、595 passed、0 pyright errors |
| `rebuild_processed` 清理 | PASS | download 路径 0 hits；preprocess 保留 |
| `_TOKEN_TO_PERIOD` 迁移 | PASS | `cn_form_utils.py` 0 hits；filing_semantics.py 拥有 `parse_fiscal_period_filter_value` |
| `asyncio.to_thread` Docling | PASS | 0 hits；`ProcessCnDoclingConversionRunner` + `InterruptibleProcessHandle.start()` |
| `_parse_ticker_csv` 边界 | PASS | download 使用 `_parse_single_ticker`；upload/preprocess 保留 |
| `render_fins_direct_local_exit_after_cancel` | FINDING | F-DS-01/02 — 死代码未清理 |
| stale cleanup 删除 | PASS | `sec_download_workflow.py` 0 hits |
| pyright | PASS | 722 files, 0 errors, 0 warnings |
| affected tests | PASS | 595 passed, 0 failed |

---

## 10. 总体结论

**PASS** — 5 findings（4 LOW, 1 MEDIUM residual），0 correctness/stability blocking。

DL-F01～DL-F11 全部从 owner boundary 修复，语义真源唯一、边界清晰、无 backward dependency、无 contact leakage、无 fake test 冒充生产行为。cancel terminal race、storage concurrency、integrity race-safe two-phase 均有 atomic owner 裁决且有测试覆盖。

唯一 MEDIUM finding (F-DS-05) 是 plan 明确记录的 residual risk（底层文件系统永久 I/O），非实现缺陷。

建议在下一次清理性改动中处理 F-DS-01/02（删除死代码），不阻塞本 WU 的下一步 gate。

---

## 11. 未覆盖项

- DL-G01～DL-G05 真实 CLI 运行覆盖：不在本 aggregate deep review 范围，需在后续 gate 执行。
- Oracle/scenario registry 更新：仍在 Oracle pause 前，Agent 不自行接受。
- `dayu/runtime/interruptible_process.py`：未修改（verified — 0 diff），仅 import/use。
- `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`：未修改，等待用户裁决。
