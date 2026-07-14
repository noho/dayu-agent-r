# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input — 第二路 Aggregate Deepreview (AgentDS)

## Scope

- **Mode**: aggregate deepreview (不是新 WU，不是 per-slice review)
- **Umbrella WU**: `WU-SEMANTIC-OWNERSHIP-01`
- **Internal remediation sub-WU**: `R01 Doc complete input`, slug `r01-doc-complete-input`
- **Accepted R01 plan**: `54e35231` (`gateflow: accept R01 doc complete input plan`)
- **Accepted S1 commit**: `1a94d798` (`gateflow: accept R01-S1 complete source snapshot`)
- **Accepted S2 commit**: `aa875ea5` (`gateflow: accept R01-S2 directory completeness`)
- **Aggregate validation HEAD**: `26a65b0e`
- **Review base**: accepted R01 plan `54e35231`
- **Artifact**: 第二路 aggregate deepreview；只审查，不修改 production/tests/README/control/design 或现有 artifact
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-aggregate-deepreview-ds.md`

### 必读真源与裁决优先级

本 review 按脚本指定的真源层级裁决所有冲突：

1. `AGENTS.md` 语义所有权、LLM-facing、分层、编码、测试、README 约束
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 1 与 Topic 9 的最终 controller/user 裁决
3. 五份永久设计真源：`docs/host/design.md`、`docs/tool/design.md`、`docs/engine/design.md`、`docs/fins/design.md`、`docs/ui/design.md`
4. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §0、§6、§7、§8、§21、§22
5. `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`（accepted R01 plan）
6. `docs/host/issues-implementation-control.md` 的 R01 gate 状态
7. `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-aggregate-validation.md`（第一路 aggregate validation）
8. R01 全量 S1/S2 implementation、双路 code review/fix/re-review/controller 裁决 artifacts
9. 当前 production code、tests、README 的直接证据

### 审查范围

1. `54e35231..26a65b0e` 的完整 production/test/README 组合行为：
   - `dayu/documents/processors/bounded_source.py` → `source_snapshot.py`（owner rename/rewrite）
   - `dayu/tools/doc_tools.py`（S1 + S2 修改）
   - `tests/documents/test_processors.py`（owner/consumer 测试迁移）
   - `tests/documents/test_import_boundary.py`（import 边界验证）
   - `tests/tools/test_doc_tools_provider.py`（provider/integration/smoke 测试）
   - `tests/README.md`（owner contract 段落迁移）
2. 必须挑战的六个维度（按脚本要求）：
   - SourceSnapshot 状态机与 Doc consumer 真实大输入/错误/取消/cleanup 同源性
   - source/directory cap 全链清零
   - complete-input 与 output truncation/fetch_more 的 owner 分离
   - symlink/containment/allowed_paths/cancellation/process fencing 保持
   - S1/S2 findings 最终状态、coverage、真实 smoke、README/R03 handoff、allowlist 组合闭合
   - cross-slice ownership drift、下游补偿、兼容 seam、deferred Issue creep、unrelated change
3. 明确非目标：
   - 不恢复 producer cap
   - 不扩大 Issue 177
   - 不创建统一 authorization framework
   - 不修改 production、tests、README、control 或现有 artifact

### 验证环境

- Python 3.11 venv
- 84 tests passed（Documents + Doc provider 完整 suite）
- pyright: 0 errors, 0 warnings, 0 informations
- `git diff --check 54e35231..HEAD`: pass

---

## Findings

### DS-R01-AF-01 — 无 material finding: SourceSnapshot 状态机与 Doc consumers 全路径同源

- **入口/函数**: `SourceSnapshot.__enter__` / `SourceSnapshot.__exit__` / `SourceSnapshot.close` / `SourceSnapshot.open` / `SourceSnapshot.materialize`（`dayu/documents/processors/source_snapshot.py`） → `_source_snapshot` helper → `_execute_doc_business_value` → `_route_doc_business` → 五工具 business helper（`dayu/tools/doc_tools.py`）
- **文件(行号)**: `source_snapshot.py:260-458`；`doc_tools.py:1866-1887`, `1049-1138`, `1141-1209`, `1472-1555`, `1558-1611`, `1613-1708`, `1738-1796`, `1799-1863`, `2223-2254`, `2257-2339`
- **输入场景**: 正常复制到 EOF、空来源、`Source.open` 失败（`OSError`）、复制中途 I/O 异常、取消检查触发 `BaseException`、consumer Python 异常、物化写入失败、多游标并发读取+close 串行化
- **实际分支**: 逐一沿真实代码路径走读，覆盖全部状态转换与异常路径
- **预期行为**: 状态机 `new → active → closed`；单次进入（复用抛 `RuntimeError`）；`close` 幂等；活跃期间每次 `open()` 提供独立 seekable cursor；同一 snapshot 最多一个 materialized path 且复用；物化时观察取消检查；正常退出、Python 异常、I/O 异常、取消均关闭 spool 并清理 materialized path
- **实际行为**: 实现与预期行为完全一致
- **直接证据**:
  - 单次进入：`source_snapshot.py:275-277` — `if self._entered: raise RuntimeError(...)`；`self._entered = True`
  - 复制到真实 EOF：`source_snapshot.py:284-297` — 循环 `source_stream.read(_COPY_CHUNK_BYTES)` 直到 `not chunk`；写入 spool；seek(0)；记录精确 `_snapshot_size = copied`
  - 取消检查：`source_snapshot.py:285,288,294` — 进入时、每次 chunk 前、完成后各一次 `_check_cancellation()`
  - 异常清理：`source_snapshot.py:298-300` — `except BaseException: self.close(); raise`
  - 关闭幂等：`source_snapshot.py:390-420` — 先删 materialized file（`missing_ok=True`、抑制 `OSError`），再锁内 close spool 并置 None，抑制 close `OSError`
  - 读/关闭串行化：`source_snapshot.py:412-420` — 同一把 `_lock` 内执行 spool 状态 detach 与 close；reader 通过 `_read_at:438-457` 持锁读取；测试 `test_source_snapshot_close_serializes_inflight_read_and_actual_close:404-446` 用 `ThreadPoolExecutor` + `_ConcurrentSpoolProbe` 确定性证明 close 等待临界区读取、close 持锁执行、关闭后 reader 读取抛 `ValueError`
  - 取消透出：`source_snapshot.py:422-436` — `_check_cancellation` 直接调用 `self._cancellation_check()` 并原样透出异常
  - Source.open 失败：`test_source_snapshot_open_oserror_is_preserved_and_closes_spool:643-671` — 断言 `open_error` 的 `is` 身份透出、spool 已关闭
  - 物化写入失败：`test_source_snapshot_materialize_write_oserror_removes_partial_path:674-706` — 断言异常透出、partial 文件已删除
  - 物化取消：`test_source_snapshot_materialize_observes_cancellation_and_cleans_resources:561-641` — 断言取消透出、partial 文件删除、spool 关闭
  - I/O/取消关闭：`test_source_snapshot_closes_spool_on_io_failure_or_cancellation:716-752` — 参数化 `(FailingSource→OSError, MemorySource+cancel→_SyntheticCancellation)` 两条路径
  - Consumer 使用：`_get_file_sections_business:1583`、`_search_files_business:1670`、`_read_file_business:1776`、`_read_file_section_business:1824` — 全部通过 `with _source_snapshot(...) as snapshot:` 进入上下文后使用
  - 五个 consumer 都不读取 `content_length` 作为 budget（docstring 明确标注 cancel/timeout/error 路径）
- **影响**: 无。状态机在正常、失败、取消、并发路径上均与 accepted contract 同源。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无。
- **严重程度**: 无（无 material finding）。

---

### DS-R01-AF-02 — 无 material finding: source/directory cap 在 producer/result/schema/prompt/tests/README/LLM-readable surface 全链清零

- **入口/函数**: 全部 Doc producer（`_list_files_business`、`_search_files_business`、`_read_file_business`、`_read_file_section_business`、`_get_file_sections_business`）、五个工具 schema builders（`_build_*_definitions`）、LLM description/parameter 文本、prompt assets（`dayu/config/prompts/base/tools.md`）、tests、`tests/README.md`
- **文件(行号)**: `doc_tools.py` 全文件（3215 行）；`test_doc_tools_provider.py` 全文件；`test_processors.py` 全文件；`tests/README.md`
- **输入场景**: 对 `dayu/ tests/ README.md` 做全域 semantic/LLM/数值扫描
- **实际分支**: 所有扫描均为零命中
- **预期行为**: 被删除符号 (`DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files`) 在生产/测试/README 全域零残留；被删除 LLM 引导语 (`较小文件|拆分文件|缩小文件范围|缩小目录`) 在 Doc tool/prompt/测试 零残留；旧模块/类 (`bounded_source|BoundedSourceSnapshot|dayu-doc-bounded`) 零残留；旧常量 (`_DOC_SOURCE_MAX_BYTES|_DOC_DIRECTORY_MAX_ENTRIES`) 零残留；`resource_budget` 参数全链删除
- **实际行为**: 所有扫描预期命中数为零，实际命中数确为零
- **直接证据**:
  - `rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files' dayu tests README.md` → 零命中
  - `rg -n 'bounded_source|BoundedSourceSnapshot|dayu-doc-bounded' dayu tests` → 零命中
  - `rg -n 'directory_entry_limit|source_limit|skipped_oversized_files|source_budget_exceeded|较小文件|拆分文件|缩小文件范围|缩小目录' dayu/tools/doc_tools.py dayu/config/prompts tests/tools/test_doc_tools_provider.py` → 零命中
  - `rg -n 'resource_budget|_DOC_DIRECTORY_MAX|_DOC_SOURCE_MAX|max_source_bytes|max_directory_entries|DocResourceBudget' dayu/tools/doc_tools.py tests/tools/test_doc_tools_provider.py` → 零命中
  - Doc-scoped legacy numeric scan (`32 MiB`, `10_000`)唯一命中在 `dayu/documents/processors/html_extraction.py:323,333` 的两个 `-10_000` HTML 评分哨兵——已分类为 `unrelated unchanged literal`（仅用于 HTML candidate 评分，不参与 source bytes、directory entries、遍历停止、result partial 或 LLM-facing contract）
  - `scan_complete/truncated_reason` 生产全范围分类扫描：list producer 零命中、list schema 零命中、生产 consumer 零命中；仅 search(read) 的 result_limit/char output 有合法命中（逐项 owner 分类参见 aggregate validation §4.2）
  - `tests/README.md` 不再描述 directory partial
- **影响**: 无。被删除 cap 的语义在全链零残留。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无。
- **严重程度**: 无（无 material finding）。

---

### DS-R01-AF-03 — 无 material finding: complete-input 与 output truncation/fetch_more 由正确 owner 分离，未误接 Issue 177

- **入口/函数**: `_read_file_business` / `_read_file_section_business` → `_read_bounded_text` → `_read_source_with_encoding`；`_build_read_file_definition` / `_build_read_file_section_definition` → `ToolTruncateSpec` 声明
- **文件(行号)**: `doc_tools.py:1738-1796`, `1799-1863`, `2223-2339`, tool definition builders `doc_tools.py:791-950`
- **输入场景**: 大文件读取 → output char truncation → Host `ToolTruncateSpec` / `fetch_more` 治理
- **实际分支**: read/read-section 保留 `ToolTruncateSpec(TEXT_CHARS, target_field="content")` 声明；完整 source 读入后应用 `max_chars` 截断
- **预期行为**: Doc producer 不接入 `TruncationManager`、不注册 business `fetch_more`、不自行实现 pagination/continuation；完整 input 进入 producer，output 截断由 Host ToolRuntime 治理；Issue 177 仍然是五工具完整 `TruncationManager`/`fetch_more` 的唯一 destination
- **实际行为**: 与预期完全一致
- **直接证据**:
  - `rg -n 'TruncationManager|FetchMoreToolCallable|fetch_more' dayu/tools/doc_tools.py dayu/tools/doc_provider.py` → 零命中
  - `git diff --name-only 54e35231..HEAD -- dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json` → 零 diff（Host/runtime/contracts/tool_discovery 无变更）
  - `rg -n 'ToolTruncateSpec|truncate=_text_content_truncate' dayu/tools/doc_tools.py tests/tools/test_doc_tools_provider.py` → 仅命中 read/read-section 定义与 owner tests
  - `test_read_tools_expose_current_truncate_spec_and_no_old_imports:1810` — 断言 `ToolTruncateSpec` target_field 为 `"content"`，旧 truncation 字段（`result_size`、`estimated_total`）不存在
  - `test_no_old_fetch_more_business_tool:1801` — 断言 Doc 未注册 business `fetch_more`
  - `test_combined_truncate_specs_and_fetch_more_owner`（consumer test）— Doc `ToolTruncateSpec` 仍在 combined bundle 中保留
  - `_read_file_business:1764-1796` — `max_chars` 传到 `_read_bounded_text`，char 截断由 `_read_source_with_encoding` 的 `max_chars + 1` probe 执行；producer 不自行 pre-truncate
- **影响**: 无。input completeness 与 output truncation 的 owner 边界正确分离。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无。
- **严重程度**: 无（无 material finding）。

---

### DS-R01-AF-04 — 无 material finding: symlink/containment/allowed_paths/cancellation/process fencing 保持且未被统一权限设计替代

- **入口/函数**: `_project_doc_paths` (direct read containment)、`_resolve_search_files_candidate` (search candidate containment)、`_iter_directory_entries` (directory/file symlink traversal)、`_raise_if_doc_cancelled` (cancellation)、`_DocProcessTarget` (process fencing)
- **文件(行号)**: `doc_tools.py:1268-1317` (resolve roots)、`doc_tools.py:1711-1735` (search candidate)、`doc_tools.py:1432-1469` (iterator)、`doc_tools.py:384-445` (process target)
- **输入场景**: allowed-root 内 file symlink 指向外部、directory symlink entry、指向外部目录的 file symlink、取消信号、process capsule 治理
- **实际分支**: 三条 owner boundary 保持独立：list 按 entry metadata（不读内容、不做 containment）、search 在 candidate resolve 边界做 containment、direct read 在 path projection 边界做 containment
- **预期行为**: list 不新增 per-entry containment；search 不读取外部 symlink target；direct read 拒绝外部 symlink target；directory symlink 不递归（Python 3.11 现状保持）；process capsule 保留；allowed_paths 必须为非空
- **实际行为**: 与预期完全一致，三条行为独立且均正确
- **直接证据**:
  - **list file symlink**: `_list_files_business:1508-1542` — 对 `_iter_directory_entries` 产出的每个 entry 做 `is_file()` 判断；list 的 record 使用 `file_path.relative_to(dir_path)`（symlink entry 的相对路径）和 `file_stat.st_size`（不在 list 层做 resolve/containment）
  - **search symlink containment**: `_search_files_business:1660-1663` — 每个 file entry 先调用 `_resolve_search_files_candidate` 做 `resolve(strict=True)` + containment check；`resolved_file is None` 时 continue（不读取）
  - **direct read containment**: `_project_doc_paths`（在 `_execute_doc_business_value:1084-1089` 调用）— 输入路径 canonical resolve + containment；resolve 后 outside 的 file symlink 直接返回 `permission_denied`
  - **directory symlink no-recursion**: `_iter_directory_entries:1464` — 递归条件 `not entry.is_symlink() and entry.is_dir()` 明确排除 directory symlink
  - **smoke 验证**: `test_doc_complete_input_real_smoke_above_legacy_thresholds:1511-1518` — outside file symlink 的 `read_file` 返回 `permission_denied`；`test_search_files_does_not_read_symlink_escape:1521` — search 不读取外部 symlink 目标
  - **三个 owner 的独立 test 合约**: `test_directory_symlink_entry_is_yielded_without_recursing_target:974`（directory symlink 不递归）; `test_list_files_keeps_allowed_file_symlink_as_directory_entry:1009`（list file symlink 仅按 entry metadata）; `test_search_files_does_not_read_symlink_escape:1521`（search 拒绝外部 target）; `test_disallowed_path_returns_failed_outcome:577`（direct read 拒绝外部 target）
  - **cancellation**: `_iter_directory_entries` 每层枚举前、每个 entry 产出前、递归前检查取消（`doc_tools.py:1455,1457,1462`）；`_search_files_business` 每文件处理前、编码尝试间、结果返回前检查取消；`_read_source_with_encoding` 每 chunk 解码后检查取消；`_source_snapshot` 构造带 `_DocSourceCancellationCheck` 的 snapshot；测试覆盖 `list_files` iteration cancel (`test_list_files_directory_iteration_observes_cancellation:844`)、search cancel 两种路径 (`test_search_files_cancelled_during_iteration_stops_before_later_scan:1555`、`test_search_files_line_scan_cancellation_returns_host_cancelled:1638`)、read cancel (`test_read_file_cancelled_after_first_failed_encoding_stops_fallback:1677`)、markdown section cancel (`test_markdown_section_extraction_observes_cooperative_cancellation:1699`)
  - **process fencing**: `_DocProcessTarget.__call__:408-445` — 子进程内使用 `_DocProcessCancellationToken`（不响应 Host cancel）；父进程 `ProcessBackedToolExecutionCapability` 独占总治理权；`test_all_doc_tool_definitions_declare_process_backed_execution:340` — 全部五工具 declare process-backed
  - **allowed_paths**: `test_provider_enabled_without_allowed_paths_fails_fast:555` — `allowed_paths` 为空时 provider 构造直接 fail-fast
  - **无统一授权**: `rg -n 'authorization|Authorization|permission_framework|role_model' dayu/tools/doc_tools.py dayu/documents/processors/source_snapshot.py` → 零命中
- **影响**: 无。所有 retained security/cancellation/process fencing 行为保持且未被统一权限设计替代。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无。
- **严重程度**: 无（无 material finding）。

---

### DS-R01-AF-05 — 无 material finding: S1/S2 全部 findings 最终状态闭合，coverage/smoke/README/R03 handoff/allowlist 组合闭合

- **入口/函数**: S1 code review DS-F01—DS-F08 + S2 code review（零 finding）；controller adjudication；re-review closure；aggregate validation
- **文件(行号)**: 全量 evidence chain（implementation/review/fix/re-review/controller artifacts）
- **输入场景**: 逐 finding 按 controller 最终裁决追踪闭合状态
- **实际分支**: 全部 accepted 已闭合；全部 rejected/deferred 未误实现
- **预期行为**: 所有 accepted finding 已修复并经双路 re-review 确认；所有 rejected/deferred/note 未被实现；无遗漏 finding
- **实际行为**: 完全一致
- **直接证据**:
  - **S1 accepted findings**: DS-F01 (lock/close serialization) — `source_snapshot.py:412-420` lock-scoped close + `test_source_snapshot_close_serializes_inflight_read_and_actual_close:404`；DS-F02 (materialize cancellation) — `source_snapshot.py:364,374-375,382-388` materialize 内 `_check_cancellation` + partial cleanup + `test_source_snapshot_materialize_observes_cancellation_and_cleans_resources:561`；DS-F03 (empty source) — `test_source_snapshot_empty_source_has_exact_eof_and_materialization:449`；DS-F04 (Source.open OSError) — `test_source_snapshot_open_oserror_is_preserved_and_closes_spool:643`；DS-F05 (materialize write OSError) — `test_source_snapshot_materialize_write_oserror_removes_partial_path:674`；全部 5 个 accepted finding 在双路 re-review 中确认闭环（controller adjudication R01-S1 code re-review 裁定 PASS）
  - **S1 rejected/deferred**: DS-F06 (rejected — 由 S2 real >33 MiB smoke 覆盖而非 S1 伪 declared-length 测试)、DS-F07 (rejected — unchanged defensive 行为，不属 R01)、DS-F08 (rejected — 冲突 accepted exact LLM-facing contract assertion)；controller 已裁决 rejected-with-reason；代码中无对应实现
  - **S2**: 两路 reviewer 均返回 PASS、零 material finding — controller adjudication 接受；无 accepted finding 需修复
  - **Coverage**: `source_snapshot.py` 93.506% (144/154 statements) — ≥80% ✓；`doc_tools.py` 80.519% (620/770 statements) — ≥80% ✓
  - **Real smoke**: `test_doc_complete_input_real_smoke_above_legacy_thresholds:1408` — 10,001 个小文件 + 一个 35,651,621-byte 大文件 + 一个 outside file symlink；真实 `discover_tools → ToolDefinition.callable` 路径；list 完整观察 `scanned_entries=10,003` 且 `total=1`；read 成功（仅合法 char output truncation）；search 大文件尾部命中且 `scan_complete=True`；direct read symlink escape 返回 `permission_denied`
  - **README**: `tests/README.md` 已迁移 Documents/Tools owner 段落到 complete snapshot/full traversal/real threshold smoke（S2 实现 artifact 记录）
  - **R03 handoff**: accepted R01 plan §13.2 逐文件 inventory 在 R01 completion 时必须交付（当前 R01 未到 completion gate）；R01 completion artifact 规格在 plan §14.3 明确
  - **Allowlist**: `54e35231..HEAD` 的 semantic diff 只包含 `source_snapshot.py`(new)、`doc_tools.py`、`test_processors.py`、`test_import_boundary.py`、`test_doc_tools_provider.py`、`tests/README.md`（+ R01 implementation/review/controller artifacts）——全在 accepted plan §6 闭集内
- **影响**: 无。S1/S2 findings 组合闭合。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无。
- **严重程度**: 无（无 material finding）。

---

### DS-R01-AF-06 — 无 material finding: 无 cross-slice ownership drift、下游补偿、兼容 seam、deferred Issue creep 或 unrelated change

- **入口/函数**: 全量 diff `54e35231..26a65b0e` 的 cross-slice 审计
- **文件(行号)**: 全量变更文件
- **输入场景**: 检查是否存在：跨 slice 所有权漂移、下游消费者自行补偿上游语义、兼容 wrapper/re-export/alias、deferred Issue 越界实现、无关变更
- **实际分支**: 逐文件、逐 diff hunk 走读
- **预期行为**: 无上述问题
- **实际行为**: 无上述问题
- **直接证据**:
  - **无兼容 seam**: `bounded_source.py` 完全删除（非 rename-to-alias），`source_snapshot.py` 为全新文件；doc_tools.py 中 `from dayu.documents.processors.source_snapshot import SourceSnapshot` 是唯一 import 点；无旧 import 路径保留；`__init__.py` 无 re-export
  - **无下游补偿**: `_execute_doc_business_value:1049-1138` 中 `SourceBudgetExceeded` mapping 已删除（仅保留 `_DocToolArgumentError`、`_DocFileAccessError`、`FileNotFoundError`、`PermissionError`、`Exception` 五条 error mapping）；下游无自行重算 `total` / `scanned_entries` / `scan_complete` 的逻辑
  - **无临时间接层**: S1→S2 过渡签名已封闭——`_DOC_DIRECTORY_MAX_ENTRIES` 常量、`max_directory_entries` 参数 均已删除；`_route_doc_business` 的 `list/search` 分支不传 budget 参数
  - **S2 closure**: `_list_files_business` signature 只保留 `limit` + `max_files` (output side)，`_search_files_business` signature 只保留 `limit` + `max_results` (output side)；无 directory/entry input cap
  - **无 Issue 177 creep**: `TruncationManager|FetchMoreToolCallable|fetch_more` 在 doc_tools/doc_provider 零命中；Host/runtime/contracts 无 diff
  - **无 Issue 175/178 creep**: `rg -n 'Issue.?175|Issue.?178|process.isolation|storage.state.lifecycle' dayu/documents/processors/ dayu/tools/doc_tools.py tests/documents/ tests/tools/test_doc_tools_provider.py` → 零命中（仅 artifacts 中有引用）
  - **无无关变更**: 全部 semantic diff 在 accepted plan §6 allowlist 内；`dayu/config/prompts/base/tools.md` 零 diff（"大文件先看章节"保留为 output/导航效率建议，不属于被删除的 input cap 引导）；`dayu/config/tool_discovery.json` 零 diff；`dayu/tools/doc_provider.py` 零 diff
- **影响**: 无。无 cross-slice drift、downstream compensation、compatibility seam、deferred Issue creep 或 unrelated change。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无。
- **严重程度**: 无（无 material finding）。

---

## R01 完整覆盖、验证与 residual classification

### 覆盖矩阵

| 维度 | 覆盖状态 | 证据 |
|---|---|---|
| SourceSnapshot 正常路径 | covered | `test_processors.py` 6 个 owner test + provider search/read/get-sections tests |
| SourceSnapshot 失败路径（I/O 失败、取消、consumer 异常、物化写入失败） | covered | `test_processors.py` 5 个 failure path tests (`_ConcurrentSpoolProbe`, `_FailingSource`, `_FailingOpenSource`, `_FailingMaterializedOutput`, `_CancelAfterChecks`) |
| SourceSnapshot 并发安全（读/关闭串行化） | covered | `test_source_snapshot_close_serializes_inflight_read_and_actual_close:404` |
| 目录完整遍历（>10,000 entry） | covered | real smoke `test_doc_complete_input_real_smoke_above_legacy_thresholds:1408` |
| source 完整输入（>33 MiB） | covered | 同一 real smoke — read 成功、search 尾部命中 |
| deterministic traversal | covered | `test_list_and_search_order_is_stable_across_reversed_creation_order:891` |
| directory symlink no-recursion | covered | `test_directory_symlink_entry_is_yielded_without_recursing_target:974` |
| list file symlink entry metadata | covered | `test_list_files_keeps_allowed_file_symlink_as_directory_entry:1009` |
| search symlink containment | covered | `test_search_files_does_not_read_symlink_escape:1521` + smoke |
| direct read symlink containment | covered | smoke `direct_read_escape → permission_denied` + `test_disallowed_path_returns_failed_outcome:577` |
| output limit (result_limit) | covered | `test_search_files_cumulative_match_limit_returns_result_partial:1258` |
| output char truncation | covered | `test_read_file_long_single_line_stops_at_character_limit:1047` + smoke `read → content_truncated=True` |
| cancellation (list iteration) | covered | `test_list_files_directory_iteration_observes_cancellation:844` |
| cancellation (search iteration + line scan) | covered | `test_search_files_cancelled_during_iteration_stops_before_later_scan:1555` + `test_search_via_line_scan_observes_loop_cancellation:1622` + `test_search_files_line_scan_cancellation_returns_host_cancelled:1638` |
| cancellation (read encoding fallback) | covered | `test_read_file_cancelled_after_first_failed_encoding_stops_fallback:1677` |
| process fencing | covered | `test_all_doc_tool_definitions_declare_process_backed_execution:340` + `test_doc_toolruntime_cancel_returns_governed_failure_without_late_accept:1950` |
| provider allowed_paths | covered | `test_provider_enabled_without_allowed_paths_fails_fast:555` |
| ToolTruncateSpec/fetch_more owner | covered | 4 consumer tests (combined truncation/bundle/fetch_more) |
| removed symbol 全域扫描 | covered | 13 条语义/LLM/旧模块/源 propagation scan — 全部零命中（除已分类的 `-10_000` HTML scoring sentinels） |
| `scan_complete/truncated_reason` 逐 owner 分类 | covered | 生产全范围逐行分类——list 零命中；search/read 合法命中已归类 |
| pyright | covered | 0 errors, 0 warnings, 0 informations |
| 逐文件 coverage (source_snapshot.py) | covered | 93.506% ≥ 80% |
| 逐文件 coverage (doc_tools.py) | covered | 80.519% ≥ 80% |

### 未覆盖区域与 residual classification

| 维度 | 状态 | residual owner |
|---|---|---|
| search `total_matches` 为实际返回数而非真实匹配总数（`result_limit` 到达后停止搜索） | 已知局限——accepted R01 plan §16.1 明确为 output limit scope 内的已知行为；`scan_complete=false`+`truncated_reason=result_limit` 会告知 consumer | Issue 177：完整 `TruncationManager` + `fetch_more` 接入时一并收敛 |
| Doc 五工具未完整接入 `TruncationManager`/`fetch_more` | 明确非目标——R01 不接入 | GitHub Issue #177 |
| 极大本地 source/目录的资源消耗（磁盘、时间、inode） | known residual——当前通过 process boundary、cooperative/parent cancellation 与 output limit 治理；不恢复未经裁决的 hard-fail | Issue #177 / 后续输入治理设计 |
| symlink/TOCTOU 是既有局部防御边界，三条 owner 行为尚未统一 | known residual——R01 保持现状，不统一权限或重设计 symlink policy | 后续独立 tool authorization/filesystem hardening WU |
| R03 handoff inventory | 尚未交付——R01 completion artifact 必须包含 plan §13.2 的逐文件 LLM-facing inventory | R01 completion gate |

### 关键不变量的端到端验证

1. **任何 source 长度均不产生 size/budget terminal**: real smoke 使用 35,651,621-byte (>33 MiB) 文件通过 read + search ✓
2. **任何目录 entry 数均不产生 entry partial**: real smoke 使用 10,003 entries（超过旧 10,000 阈值）完整观察 ✓
3. **只有 output limit/字符截断产生 output partial**: search `result_limit` 和 read `content_truncated` 是唯一 partial 来源 ✓
4. **取消不伪造 complete**: cancellation 路径快速收口且不写 complete result（process `host_cancelled` + direct callable `_DocCancelledError` → `host_cancelled_outcome`）✓
5. **deferred Issue 零越界**: Issue 177/175/178 均无 product diff ✓

---

## Open Questions

无。R01 实现在所有审查维度均闭合，无 blocking question、无需要更多证据的项、无待澄清的 owner boundary。

---

## Residual Risk

以 umbrella plan §23 的 R01-relevant residual 为基准，逐项核实当前状态：

| residual risk | 当前状态 | owner/destination |
|---|---|---|
| Doc 极大输入可能耗尽资源 | 本 WU 已删除未经裁决的 hard-fail；spool/cancel/output limit 保留 | Issue 177：完整 TruncationManager/输入治理设计 |
| search `total_matches` 在 result_limit 下并非真实匹配总数 | `scan_complete=false` + `truncated_reason=result_limit` 告知 consumer | Issue 177 若以 complete result + fetch_more 重构 |
| symlink/TOCTOU 是既有局部防御 | 三条 owner 保持独立；R01 不统一 | 后续独立 tool authorization / filesystem hardening WU |
| R03 handoff inventory 尚未完成 | 按 plan §13.2，R01 completion 时交付 | R01 completion gate |

无新增 residual risk。上诉四项均为 accepted plan 已登记的 known residual，R01 实现没有扩大其 blast radius 或在代码中提前承诺未授权的修复。

---

## Reviewer Verdict

**PASS — 零 material finding。**

R01 组合实现（`54e35231..26a65b0e`）在以下六个强制审查维度上全部闭合：

1. **SourceSnapshot 状态机与 Doc consumers 同源**：正常、失败、取消、并发路径均沿真实代码路径走读，无一背离 accepted contract。
2. **source/directory cap 全链清零**：13 条语义/LLM/数值扫描全域零命中（除一条已分类的无关 literal）；list 的 `scan_complete/truncated_reason` 已删除且生产/消费面零残留。
3. **complete-input 与 output truncation 正确分离**：Doc 五工具未接入 `TruncationManager`，未注册 business `fetch_more`；Host/runtime/contracts 无 diff；Issue 177 仍是唯一 destination。
4. **symlink/containment/allowed_paths/cancellation/process fencing 保持**：三条 owner boundary 独立且正确（list entry metadata、search candidate resolve、direct read path projection）；取消覆盖 iterator/copy/read/line-scan/section-extraction；process capsule 保留；无统一授权框架或新 symlink policy。
5. **S1/S2 findings 组合闭合**：全部 5 个 accepted S1 finding 已修复并经双路 re-review 确认；6 个 S1 rejected/deferred 未误实现；S2 零 accepted finding；coverage ≥80%；real >33 MiB + >10,000-entry smoke 通过；README 已迁移；R03 handoff 规格已冻结；allowlist 闭集无越界。
6. **无 cross-slice ownership drift、下游补偿、兼容 seam、deferred Issue creep 或 unrelated change**：S1→S2 过渡签名已完全封闭；无 re-export/wrapper/alias；无下游 fallback 或重算；无 Issue 175/177/178 越界 diff；无无关改动。

本 verdict 不授权 R01 completion/accepted aggregate commit。若 controller 接受本 review，下一 gate 为 R01 completion gate（需交付 §13.2 R03 handoff inventory 等 completion artifact）。

---

**审查人**: AgentDS（第二路独立 aggregate deepreview）  
**审查时间**: 2026-07-14T20:14:45+08:00  
**审查 base**: accepted R01 plan `54e35231`  
**目标 artifact**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-aggregate-deepreview-ds.md`
