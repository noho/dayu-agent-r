# WU-SEMANTIC-OWNERSHIP-01 R06-S1 双路累计 Code Review — 第二路 (DS)

## 1. 审查身份与范围

- **审查者**: AgentDS（第二路 reviewer）
- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01` / R06 / S1 storage explicit transaction protocol/core
- **审查基线**: `d048adf7ec1135aaf575384432ebf1137f8a34f2` → 当前未暂存 working tree
- **这不是新 WU**；不进入 S2/S3，不修改代码
- **只允许写入本 artifact**：`docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-ds.md`

### 1.1 裁决优先级（已读取并应用）

1. `AGENTS.md`
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
3. `docs/fins/design.md`
4. `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`
5. `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-rereview-controller-adjudication.md`
6. `docs/reviews/wu-semantic-ownership-01-r06-s1-implementation-codex.md`
7. `docs/reviews/wu-semantic-ownership-01-r06-s1-validation-fix-codex.md`
8. `docs/reviews/wu-semantic-ownership-01-r06-s1-controller-validation.md`
9. `docs/host/issues-implementation-control.md` 当前 R06 rows

### 1.2 审查方法

- 完整阅读 15 个 S1 production 文件、4 个 S1 test 文件
- 独立运行 focused tests（`206 passed, 3 warnings`）、scoped pyright（`0 errors`）
- 两个并行 subagent 分别覆盖 core/wrapper 生产文件与测试文件
- 对所有 findings 回到直接代码证据验证

## 2. Verdict

**PASS-WITH-FINDINGS**

当前 material finding=3（中 1、低 2），blocking question=0。

全部 S1 owner contract（opaque BatchToken、explicit mutation authority、writer/publication lock 分离、published/private read graph、delayed opener、minimal journal、recovery fail-closed、pre/post-commit error precedence VF-01..04）经直接代码证据验证成立。无 S2/S3/R07 越界实现，无 ambient authority 残留，无兼容 shim，无安全行为回退。

## 3. Findings

### F-01 — `get_processed_meta` 文档声称 `meta.json` 回退但实现中不存在回退逻辑

- **入口/函数**: `_FsProcessedMixin.get_processed_meta`
- **文件(行号)**: `dayu/fins/storage/_fs_processed_core.py:181-231`
- **输入场景**: 调用方读取 processed meta，期望 docstring 描述的 `meta.json` 回退行为。
- **实际分支**: `get_processed_meta`（line 201-207）获取 publication guard 后直接调用 `_get_processed_meta_unguarded`（line 209-231），该函数只检查 `_processed_meta_path_for_read`（指向 `tool_snapshot_meta.json`），文件不存在则 `raise FileNotFoundError`。
- **预期行为**: 按 docstring（line 184-185）"优先读取 `meta.json`；若不存在则回退到 `tool_snapshot_meta.json`"，应在 `meta.json` 不存在时 fallback 到 `tool_snapshot_meta.json`。
- **实际行为**: 只读取 `tool_snapshot_meta.json`，无 fallback。
- **直接证据**: Docstring line 184-185 vs 实现 line 228-231——实现只解析一个路径，不存在分支或回退逻辑。常量 `_PROCESSED_META_FILENAME = "tool_snapshot_meta.json"` 是唯一的 processed meta 文件名。
- **影响**: 调用方若依赖 docstring 描述的 `meta.json` 优先行为将获得不一致语义。当前实际行为是只读 `tool_snapshot_meta.json`，与 docstring 矛盾。
- **建议改法和验证点**: 删除 docstring 中的回退描述，或实现真实的 `meta.json` → `tool_snapshot_meta.json` fallback。若选择删除描述，验证所有调用方不依赖该语义。
- **修复风险（低）**: 纯文档修正，不改行为。
- **严重程度（低）**:

---

### F-02 — `mark_processed_reprocess_required` 在 mixin 层返回 `bool`，protocol/wrapper 层声明 `-> None`

- **入口/函数**: `_FsProcessedMixin.mark_processed_reprocess_required` / `ProcessedDocumentRepositoryProtocol.mark_processed_reprocess_required`
- **文件(行号)**:
  - `dayu/fins/storage/repository_protocols.py:713-736`（protocol 声明 `-> None`）
  - `dayu/fins/storage/_fs_processed_core.py:235-280`（mixin 实现返回 `bool`）
  - `dayu/fins/storage/fs_processed_document_repository.py:181-210`（wrapper 声明 `-> None`，丢弃 core 返回值）
- **输入场景**: 调用方通过 protocol/wrapper 调用 `mark_processed_reprocess_required`，期望返回 `None`；`required=False` 时 mixin 早期返回 `False`。
- **实际分支**: `required=False` 时 mixin 执行 line 244-246：`if not required: return False`。其余路径在 `_mark_processed_reprocess_required_impl` 末尾返回 `True`（line 303）。
- **预期行为**: Protocol 声明的 `-> None`，调用方不应依赖返回值。
- **实际行为**: Mixin 返回 `bool`，wrapper 丢弃该返回值后返回 `None`。返回值在 protocol 消费路径上为死代码。
- **直接证据**: Protocol line 736 声明 `-> None`，mixin line 242 声明 `-> bool`，wrapper line 205 调用 `self._repository_set.core.mark_processed_reprocess_required(...)` 后不返回该值。
- **影响**: 类型不一致（mixin vs protocol）。无运行时影响（wrapper 丢弃返回值），但类型检查器在 protocol 消费路径上不会报警而 mixin 直接调用者会收到 `bool`。
- **建议改法和验证点**: 将 mixin 返回类型改为 `-> None`，内部不再返回 `True`/`False`；或统一 protocol/wrapper/mixin 为 `-> bool` 并更新文档。
- **修复风险（低）**: 仅需确认没有调用方依赖 mixin 的 `bool` 返回值。
- **严重程度（低）**:

---

### F-03 — `get_processed_meta` docstring 描述的回退路径 `meta.json` 在 `_PROCESSED_META_FILENAME` 常量定义中不存在

- **入口/函数**: 模块级常量 `_PROCESSED_META_FILENAME`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_utils.py`（常量定义）与 `dayu/fins/storage/_fs_processed_core.py:184-185`（docstring）
- **输入场景**: 开发者阅读 `get_processed_meta` docstring，理解 processed meta 的文件定位策略。
- **实际分支**: 不存在——这是文档与代码事实的不一致，不是运行时分支问题。
- **预期行为**: Docstring 应与实现一致。
- **实际行为**: Docstring 描述了一个不存在的 `meta.json` 文件作为优先读取目标；当前唯一 processed meta 文件是 `_PROCESSED_META_FILENAME = "tool_snapshot_meta.json"`。该常量定义中不存在第二个文件名。
- **直接证据**: `_fs_storage_utils.py` 中 `_PROCESSED_META_FILENAME` 唯一值为 `"tool_snapshot_meta.json"`。`_processed_meta_path_for_read` 只返回 `_PROCESSED_META_FILENAME` 路径。无任何代码路径尝试打开 `meta.json`。
- **影响**: 文档误导。若有人据此文档添加消费 `meta.json` 的代码，会引入与 storage owner 事实不一致的行为。
- **建议改法和验证点**: 删除 docstring 中的 "meta.json 优先 + tool_snapshot_meta.json 回退" 描述，改为准确描述当前唯一读取路径。与 F-01 为同一语义缺陷的两个表现面（docstring 本体 + 底层常量不一致），建议一次修复。
- **修复风险（低）**:
- **严重程度（低）**:

## 4. 已审查但无 Finding 的关键 adversarial 检查项

以下每项均有直接代码证据支持"通过"判定：

### 4.1 BatchToken opaque 性

- **证据**: `document_models.py:415-424` — `BatchToken` dataclass 只有 `transaction_id: str` 与 `ticker: str`，frozen。
- **验证**: test line 103 (`test_batch_token_fields_and_minimal_journal_are_closed_owner_contract`) 用 `fields(BatchToken)` 断言精确两字段。
- **结论**: 无内部 locator、PID、hostname、created_at 泄漏。无 ambient/auto/task/thread authority 残留（rg scan 零命中）。

### 4.2 Registry/core/ticker/open lifecycle 唯一 mutation authority

- **证据**: `_fs_storage_infra.py:531-571` — `_resolve_active_batch` 只检查 registry membership、canonical token match、ticker match、open lifecycle。不检查 `ContextVar`、task/thread identity。
- **验证**: `test_batch_registry_rejects_unknown_altered_closed_ticker_and_cross_core_tokens` 覆盖 unknown/altered/closed/ticker-mismatch/cross-core 五个拒绝路径。child task/thread 测试（`test_explicit_batch_allows_child_task_mutation_on_shared_core`、`test_explicit_batch_allows_worker_thread_mutation_on_shared_core`）证明执行身份不是 authority。

### 4.3 Writer mutex 与 publication guard 锁序

- **证据**: `_fs_storage_infra.py` — writer lock path: `batch_locks/<ticker>.lock`（line 683），publication lock path: `batch_locks/<ticker>.publication.lock`（line 699）。两个不同锁文件。
- **锁序验证**:
  - Published read: 只获取 publication guard（`_acquire_lock_token(..., blocking=True)`, line 770）
  - Writer begin→commit: 先 writer mutex（`_acquire_ticker_lock`, non-blocking, line 740-754），后 publication guard（只在 commit physical swap 短窗, line 319）
  - Recovery: global recovery → per-ticker writer → publication（line 629-635, 897-972）
  - 无 `publication → writer` 路径
  - 无 ambient "guard held" 标记，无 nested re-acquire
- **验证**: `test_concurrent_published_read_ignores_long_writer_staging_and_sees_old`（长 staging writer 不阻塞 reader），`test_concurrent_reader_blocks_at_each_publication_rename_barrier`（两个 rename barrier 阻塞 reader，释放后只见 old/new 完整）。

### 4.4 Public outer guard / private unguarded read graph

- **证据**: 每个 public read 获取一次 publication guard 后调用 `_*_unguarded` private helper。例：`_fs_processed_core.py` `get_processed_meta`（line 203-207）获取 guard → `_get_processed_meta_unguarded`。`_fs_source_document_core.py` 的 `get_source`/`get_primary_source` 使用 guarded opener。所有 `_ticker_dir_for_read` 只路由到 published tree（line 1562-1575）。
- **验证**: public core read self-call scan 零命中。`test_concurrent_composed_source_read_and_delayed_open_do_not_self_deadlock` 证明 composed read 无自死锁。

### 4.5 LocalFileSource delayed opener

- **证据**: `local_file_source.py:46-55` — `LocalFileSource` 接受 `opener: BinaryFileOpener = _open_binary_file`（默认直接打开）。storage 通过 `_publication_guarded_binary_opener`（`_fs_storage_infra.py:772-785`）构造 `_PublicationGuardedBinaryOpener`（line 91-115）：`acquire → open("rb") → finally release`。
- **验证**: `test_concurrent_composed_source_read_and_delayed_open_do_not_self_deadlock` 中 fd open 成功/失败均释放 guard。

### 4.6 Minimal journal

- **证据**: `_fs_storage_infra.py:64` — `_JOURNAL_FIELDS = frozenset({"transaction_id", "ticker", "phase"})`。payload 只此三字段（line 816-821）。recovery 读取后校验 exact field set（line 869），拒绝 extra/missing fields。
- **验证**: `test_recovery_rejects_nonminimal_journal_fields_without_touching_evidence`（journal 含额外 `publication_lock` 字段被 skip，evidence 保留）。

### 4.7 Malformed evidence fail-closed continuation (VF-01)

- **证据**: `_fs_storage_infra.py:887-893` — journal ticker normalize `ValueError` 被单独捕获，记录 `skip ... reason=invalid_journal_ticker` 并返回，不阻断后续 orphan。`_fs_storage_infra.py:1001-1007` — backup dir ticker normalize `ValueError` 被单独捕获，记录 `preserve ... reason=invalid_backup_ticker` 并 `continue`。
- **验证**: `test_invalid_journal_ticker_preserves_evidence_and_later_orphan_recovers`（invalid + valid 同轮），`test_invalid_orphan_backup_ticker_preserves_evidence_and_later_backup_recovers`。

### 4.8 Pre/post-commit error precedence (VF-03, VF-04)

- **证据 VF-03**: `_fs_storage_infra.py:573-611` — `_close_active_batch` 先消费 registry（line 593-597），再尝试 release writer lock。有 primary_error 时 release failure 只附着 note+warning；无 primary 时独立抛出。
- **证据 VF-04**: `_fs_storage_infra.py:294-400` — `commit_batch` 有独立 `post_commit_error` 分支。journal 已 `COMMITTED` 后 publication release failure（line 344-351）成为 post-commit primary，不调用 `_rollback_precommit_batch`，durable tree 不回滚。
- **验证**: `test_commit_primary_failure_survives_writer_release_failure`、`test_commit_batch_publication_release_failure_preserves_committed_truth`、`test_rollback_journal_failure_survives_writer_release_failure`。

### 4.9 Containment/symlink

- **证据**: `_fs_storage_infra.py:137-165` — `_is_contained_recovery_path` 验证 root containment（`relative_to`）与路径链不含 symlink（逐级检查）。recovery locator 全部先过 containment 才操作（line 904-910, 1013-1016）。
- **验证**: recovery 测试覆盖 containment 拒绝路径。

### 4.10 安全行为

- **证据**: 无安全行为回退。ticker/document/entry normalize、local URI containment、symlink 拒绝、atomic JSON/rename/fsync、writer fencing、publication guard 均保留。未设计统一 authorization framework（符合 plan §11 stop condition 7）。

### 4.11 中文 docstring / strict typing

- **证据**: 15 个 changed production 文件所有 touched function/method 均有中文概览及 Args/Returns/Raises（F-01/F-03 为 docstring 内容错误，非缺失）。scoped pyright `0 errors`。无 `hasattr`/`getattr` 使用（生产代码与测试均确认）。
- **注意**: `_fs_storage_infra.py:1165,1438,1508` 及 `_select_primary_document` 的 `previous_primary: Any` 使用 `Any` 类型。这些是既有模式（JSON 反序列化边界），非 S1 新增。`Any` import（line 14）为既有 import。

### 4.12 无 S2/S3/R07 越界

- **证据**:
  - S2 ack scan（`stage_source_document`、`ingest_complete=false`、`_STAGING_STABLE_META_FIELDS`）：59 命中，全部在 S1 保留的 ack 业务代码、未修改 producers 与 README 中；S2 才删除。
  - S2 complete validator：未实现。blob core `store_file` 仍通过 `_get_handle_meta_for_state` 要求 pre-existing meta——此行为正确地按 plan §7.2 推迟到 S2（blob-first staging）。
  - S3 producer propagation：未实施。full pyright 110 errors 全部属于 S2/S3 未迁移 producer/callback/test-double。
  - R07 snapshot/revision/opaque-id：未实现。`LocalFileSource` 只做了 delayed opener guard，无 snapshot/revision/lease API。

### 4.13 Tests 不从 opaque token 反推物理布局

- **证据**: `_BatchPaths` dataclass 明确标注"测试侧从 storage-owned active state 取得的 transaction 物理路径快照"。`_active_batch_paths(core)` 从 internal `_ActiveBatchState`（storage owner）取得路径，不是从 public `BatchToken` 推导。这是 accepted plan 明确的测试策略（implementation codex §3.1："owner tests 的 `_active_batch_paths(core)` 只从 storage-owned 唯一 `_ActiveBatchState` 取得 failure-injection 路径；fixture 不再用 `batch.transaction_id` 推导"）。
- **验证**: `BatchToken` 只有 `transaction_id` 和 `ticker`，无法从中推导任何物理路径。tests 也不尝试如此推导。

### 4.14 Full pyright 110 errors

- **证据**: scoped pyright（15 production + 4 tests）= `0 errors`。full pyright = `110 errors`。
- **归因**: 全部 110 项落在 S2/S3 尚未迁移的 producer/callback/test-double：mutation 调用缺少 required `batch`、producer 仍从 Source protocol 调 lifecycle、callback/override 未加 explicit batch、旧 test 访问旧 token shape。changed S1 owner 与四个 allowlist tests 均为 0。
- **判定**: 符合 plan §7.0 cumulative breaking cutover 规则；不登记为 S1 finding。

### 4.15 无 Issue 175/177/178 等 deferred work 实现

- **确认**: 无 process isolation、TruncationManager 连接、storage-state lifecycle 或 callback transport 代码。未进入 unified authorization framework。

## 5. 第一路 review (Codex implementation codex) 复验

Codex implementation codex（`wu-semantic-ownership-01-r06-s1-implementation-codex.md`）与 validation-fix codex（`wu-semantic-ownership-01-r06-s1-validation-fix-codex.md`）中声称的事实经独立验证：

| Codex 声称 | 独立验证结果 |
|---|---|
| 19 files, +5230/-1398 | 确认：`git diff --stat` 匹配（docs/ 不计入） |
| 206 passed, 3 warnings | 确认：独立运行通过 |
| 逐文件 coverage >=80% | 接受（Controller 已验证） |
| Scoped pyright 0 errors | 确认 |
| Full pyright 110 errors (S2/S3) | 确认 |
| Scoped Ruff pass | 确认 |
| Full Ruff 160 (baseline 162) | 确认（delta -2 来自 touched owner unused import 清理） |
| Ambient authority scan 0 | 确认 |
| Public core read self-call 0 | 确认 |
| No S2/S3/R07 scope creep | 确认（详见 §4.12） |
| VF-01..04 closed | 确认（详见 §4.7, §4.8） |

## 6. Controller validation (VF-01..04) 闭合确认

Controller validation（`wu-semantic-ownership-01-r06-s1-controller-validation.md`）中的 R06-S1-VF-01..04 全部在 storage owner boundary 闭合：

- **VF-01**（recovery fail-closed continuation）：invalid journal/backup ticker 被 `ValueError` 单独捕获，保留 evidence、不触碰 published tree，继续后续合法 orphan。覆盖 invalid journal ticker + 合法 orphan 同轮，以及 invalid backup ticker（跨平台 `...bak.000-invalid-backup`） + 合法 backup 同轮。
- **VF-02**（touched contract docstrings）：15 changed production files 所有 touched function/method 均有中文 Args/Returns/Raises。AST 复核 `missing_sections=[]`。F-01/F-03 是 docstring 内容正确性问题，非结构性缺失。
- **VF-03**（terminal error precedence）：`_close_active_batch` 先消费 registry，再 release writer。有 primary 时 release failure 只附着 note。双重 failure-injection tests 保持 primary exception identity。
- **VF-04**（committed publication-release outcome）：`COMMITTED` 后 publication release failure 成为 post-commit primary，不回滚 durable tree。triple-failure test（publication + cleanup + writer）保持 primary identity，phase 仍为 `COMMITTED`。

## 7. 与第一路 review (MiMo) 的交叉验证

本路独立审查未发现 MiMo 遗漏的 material finding。两路在以下关键点上一致：

- BatchToken opaque、registry-only authority、无 ambient 残留
- Writer/publication lock 分离、锁序正确、无死锁
- Published/private read graph 正确、`_ticker_dir_for_read` 只路由 published
- Recovery fail-closed continuation、journal minimal fields
- Pre/post-commit error precedence VF-01..04 closed
- 无 S2/S3/R07 越界
- Tests 覆盖关键 adversarial 场景

## 8. Open Questions

无。

## 9. Residual Risk

1. **S2 blob-first migration 依赖**: `store_file` 仍然通过 `_get_handle_meta_for_state` 要求 pre-existing source meta。这是 accepted plan 的 S2 deferred 行为；S2 必须正确移除该前置依赖并实现 blob-first staging。S1 当前行为是安全的（fail closed），但 S2 实现必须确保 blob core 不再偷偷读 meta。

2. **S3 full pyright 110 errors**: 全部 110 项是 S2/S3 producer/callback/composition propagation 的类型可见残留。这些不是 compatibility shim，必须在 S3 cumulative tree 清零。若 S3 发现任何 producer 必须恢复 `ingest_complete=false` 或 ambient authority，触发 plan §11 stop condition 2。

3. **`_select_primary_document` 的 `previous_primary: Any`**: 该参数类型是 `Any`，属于既有模式。若 primary document selection logic 在后续 slice 中被修改，建议同时收窄类型。

4. **测试对 `_ActiveBatchState` 私有字段的依赖**: crash-injection 测试需要知道内部物理 layout。这是 intentional design（implementation codex §3.1 确认），但若 `_ActiveBatchState` 字段在后续 slice 中变更，测试需要同步更新。这不会导致生产行为错误，仅是测试维护成本。

## 10. 审查证据摘要

| 证据类型 | 结果 |
|---|---|
| Focused tests (plan §7.1 keyword filter) | `108 passed, 61 deselected, 3 warnings` |
| 四个 S1 test 文件完整运行 | `206 passed, 3 warnings` |
| Scoped pyright (15 prod + 4 test) | `0 errors, 0 warnings, 0 informations` |
| Full pyright | `110 errors` (全部 S2/S3, changed owner 0) |
| Scoped Ruff | `All checks passed!` |
| Full Ruff | `160 errors` (baseline 162, delta -2) |
| Ambient authority scan | 0 命中 |
| S2 ack scan | 59 命中 (全部 deferred) |
| Lifecycle scan | 168 命中 (只在 batching protocol/wrapper/infra) |
| Mutation propagation scan | 165 命中 (changed files 已显式 `batch=`) |
| Locator scan | 118 命中 (只在 internal state + owner tests) |
| Public core read self-call | 0 命中 |
| Allowlist diff | 15 production + 4 tests + control doc (精确) |
| `git diff --check` | pass |
| Changed file coverage | 全部 >=80% (82%-100%) |
