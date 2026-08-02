# WU CLI Conformance F01-F07 — Integration Corrective Code Review (DS)

## Scope

- Mode: current changes (corrective slice review, not full branch review)
- Branch: `codex/interactive-oracle`
- Base: `df99f858` (entry HEAD)
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-review-ds.md`
- Review timestamp: 2026-08-03T04:55:18Z
- Reviewer: AgentDS (independent from MiMo)

### Included scope (corrective slice, 本 slice 修改对象)

| 文件 | 角色 |
|---|---|
| `docs/cli_init_workspace_manifest_v1.json` | 更新三个 package 文件 SHA-256 |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | 更新 frozen manifest SHA-256 常量 |
| `tests/host/test_phase5_local_execution_integration.py` | 五个单 worker 场景 + 一个双 worker 场景的 exact-once 证据重构 |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | fake compact input → v2 format, candidate 断言 → v2 schema |
| `tests/service/test_host_assembly.py` | compactor prompt 断言重新分配 system/user prompt 语义 |
| `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md` | 实现 artifact（准确性与一致性审查） |

### Excluded scope (S8 保留基线，不是本 slice 修改对象)

- `README.md`
- `dayu/config/README.md`
- `dayu/host/README.md`
- `tests/README.md`
- S8 implementation artifact
- 所有 `dayu/` 下的 production 代码（经 `git diff HEAD --name-only -- dayu/` 确认无 production 修改）

### Parallel review coverage

无。单路独立深度审查。

## Findings

### 01-已确认-低-`_assert_exactly_once_dispatch_outcome` 列索引裸数字脆弱

- **入口/函数**: `_assert_exactly_once_dispatch_outcome`
- **文件(行号)**: `tests/host/test_phase5_local_execution_integration.py:1570-1638`
- **输入场景**: 任意调用此 helper 的测试场景。
- **实际分支**: 总是走到 SQL 结果行的 `[0]`、`[1]`、`[2]`、`[3]` 位置索引。
- **预期行为**: 语义正确的列访问。
- **实际行为**: 代码使用 `run_rows[0][0]`、`run_rows[0][1]`、`run_rows[0][2]`、`run_rows[0][3]` 访问 `status`、`current_attempt_id`、`terminal_event_id`、`terminal_event_sequence`。如果 SELECT 列顺序被无意修改（如后续维护中加列或调整顺序），这些索引会静默指向错误列。
- **直接证据**: 行 1571-1598 的 SQL SELECT 列顺序与行 1623-1638 的 `[0]`-`[3]` 索引之间没有编译期绑定。例如 `run_rows[0][2]` 是第 3 列，SELECT 中第 3 列是 `terminal_event_id`，但没有任何机制保证这点不变。
- **影响**: 维护风险。若后续修改 SELECT 列顺序，断言可能比较错误列而 pass（最坏情况）或 fail（最好情况）。
- **建议改法和验证点**: 使用 `sqlite3.Row` row factory + 命名访问（`row["terminal_event_id"]`），或使用 `connection.execute(...).fetchone()` 后在 helper 内用 `row[0]` 时加上 `# status` 等行内注释。当前函数已有上层语义参数 `expected_run_status`、`expected_attempt_status`、`terminal_event_type` 做交叉校验，实际漂移检出风险较低。
- **修复风险（低）**: 仅影响测试 helper，改列访问方式不改变行为。
- **严重程度（低）**: 当前所有调用处 SELECT 列顺序稳定，且有交叉校验作为后备检测。

### 02-已确认-低-`host_attempt_dispatch_records` COUNT 用 `run_id` 而非 `attempt_id` 过滤

- **入口/函数**: `_assert_exactly_once_dispatch_outcome`
- **文件(行号)**: `tests/host/test_phase5_local_execution_integration.py:1581-1587`
- **输入场景**: 单 Attempt 的 Run。
- **实际分支**: `SELECT COUNT(*) FROM host_attempt_dispatch_records WHERE run_id = ?` — 不限制 `attempt_id`。
- **预期行为**: 单 Attempt Run 中 dispatch record COUNT = 1 等价于 exact-once dispatch。
- **实际行为**: 同 Run 内有多个 Attempt（如 continuation）时，此查询会统计全部 Attempt 的 dispatch records。但当前所有 6 个测试场景的 Run 均为 `max_iterations=1`、`continuation_max_attempts=0`，确为单 Attempt，COUNT(*) 语义正确。
- **直接证据**: 行 1582-1586 的 SQL 与行 1350-1351 的 `AgentPolicy(continuation_max_attempts=0)` 约束。
- **影响**: 仅当后续已有多 Attempt Run 的测试复用此 helper 且未调整查询时产生误判。当前无影响。
- **建议改法和验证点**: 加 `AND attempt_id = ?` 使 exact-once 语义显式化，或在 docstring 中标注此 helper 仅适用于单 Attempt Run。
- **修复风险（低）**: 加 `AND attempt_id = ?` 后对所有现有调用处仍 pass。
- **严重程度（低）**: 当前无实际错误，仅语义精度。

### 03-已确认-中-`test_queue_promotion_after_terminal_and_cancel_wakes_dispatch` 的两个子场景耦合在同一函数中

- **入口/函数**: `test_queue_promotion_after_terminal_and_cancel_wakes_dispatch`
- **文件(行号)**: `tests/host/test_phase5_local_execution_integration.py:733-876`
- **输入场景**: terminal promotion 与 cancel promotion 两个独立场景。
- **实际分支**: 两个场景连续写在同一测试函数中，terminal 子场景的 scheduler/host 在 `try/finally` 内正确 close，cancel 子场景独立打开新资源。
- **预期行为**: 两个子场景应能独立运行、独立失败。
- **实际行为**: terminal 子场景在第 802 行 `terminal_host.close()` 后，cancel 子场景在第 804 行开始。如果 terminal 子场景的 assertion 失败，cancel 子场景不会运行，导致一个独立场景的失败掩盖另一个。此外当前函数单个场景状态约 140 行，超过本文件其他测试的典型长度（~30-50 行）。
- **直接证据**: 行 733-876 整个函数体，terminal 子场景结束于行 802，cancel 子场景开始于行 804。
- **影响**: 故障隔离不足。如果 terminal promotion 逻辑回归，cancel promotion 覆盖也会丢失，延长排障周期。
- **建议改法和验证点**: 拆为两个独立测试函数，共享 setup helper。保持 `expected_factory_creations=2` 在两个函数中各自独立断言。
- **修复风险（低）**: 纯重构，不改变断言语义。
- **严重程度（中）**: 不是 correctness bug，但 two-in-one pattern 在 pytest 中降低故障诊断效率。考虑到本文件其他测试均为单场景，此设计不一致。

### 04-已确认-中-worker factory `created` 计数在双 worker 场景中为累计值，语义不够精确

- **入口/函数**: `_assert_exactly_once_dispatch_outcome` 中的 `worker_factory.created == expected_factory_creations`
- **文件(行号)**: `tests/host/test_phase5_local_execution_integration.py:1639`
- **输入场景**: `test_queue_promotion_after_terminal_and_cancel_wakes_dispatch` 中连续两个 `_assert_exactly_once_dispatch_outcome` 调用共享同一个 `worker_factory`，两次调用的 `expected_factory_creations` 均为 2。
- **实际分支**: 两个 worker 依次创建后 `factory.created == 2`，第一个 assertion（行 779-788）和第二个 assertion（行 789-798）都断言 `created == 2`。
- **预期行为**: 每个 assertion 应验证每个 worker 恰好被创建一次。
- **实际行为**: 第一个 assertion 验证 `created == 2`（全局累计），第二个也验证 `created == 2`（相同全局累计）。如果 factory 异常创建 3 个 worker（例如 promoted dispatch 触发两次），两个 assertion 会同时失败（`2 != 3`），能检测到问题。但无法区分是哪个 worker 被多创建了。
- **直接证据**: 行 779 对 `first_terminal_refs` 调用 `_assert_exactly_once_dispatch_outcome(worker_factory=terminal_worker_factory, expected_factory_creations=2)` 与行 789 对 `promoted_terminal_refs` 的同样调用。
- **影响**: 当前 `expected_factory_creations` 是一个 lazy 全局断言 — 它在每次 assertion 时检查相同的全局累计值，不能证明每个 Run 各自对应的 worker 创建次数。但由于 `_SequencedLocalWorkerFactory` 的 `created` 是 monotonic counter 且两个 worker 共享同一个 factory，这是唯一可行的验证方式。不影响正确性，但语义微妙，容易误导读者。
- **建议改法和验证点**: 在 helper docstring 中明确说明 `expected_factory_creations` 是 factory 累计创建次数（跨 Run），或在双 worker 场景中分两个 factory 各自断言 `expected_factory_creations=1`。后者语义更精确但需要两个 `_SequencedLocalWorkerFactory` 实例分别在 dispatch 的不同阶段注入（对于 promotion 场景不可行，因为两个 dispatch 共享同一个 scheduler）。
- **修复风险（低）**: docstring 修改无风险。
- **严重程度（中）**: 语义精度问题，不影响正确性检测能力。

### 05-已确认-低-`test_cancel_active_fake_worker_closes_cancelled` 中 `wait_until_events_started` 后直接断言 `RUNNING`

- **入口/函数**: `test_cancel_active_fake_worker_closes_cancelled`
- **文件(行号)**: `tests/host/test_phase5_local_execution_integration.py:700-704`
- **输入场景**: cancel 测试中的 RUNNING 状态检查。
- **实际分支**: `await handle.wait_until_events_started()` 返回后，`assert get_run(host, refs.run_id).status is RunStatus.RUNNING`。
- **预期行为**: ATTEMPT_RUNNING 已提交 → RUNNING 状态在 public API 可见。
- **实际行为**: 经 `dispatch.py:4727` 与 `dispatch.py:5287-5289` 逐行走读确认：`_accept_worker_running()` 已在 `consumer_started` barrier 之前同步提交 ATTEMPT_RUNNING。`anext(events)`（触发 `_events_started.set()`）发生在 consumer task 中，此时 durable RUNNING 事实已提交。`wait_until_events_started()` 的正确性有直接代码证据支撑。
- **直接证据**: `dayu/host/dispatch.py:4727`（`_accept_worker_running` 同步提交）→ `dispatch.py:4744-4751`（register）→ `dispatch.py:4756`（create consumer task）→ `dispatch.py:4773`（`consumer_started.wait()`）→ `dispatch.py:5287`（`consumer_ready.set()`）→ `dispatch.py:5289`（`anext(events)`—触发 `_events_started`）。
- **影响**: 无实际风险，`wait_until_events_started` 满足 RUNNING 断言的前提。此 finding 记录为验证 trace，确认时序安全。
- **建议改法和验证点**: 无需修改。
- **修复风险（低）**: 无需修改。
- **严重程度（低）**: 无实际缺陷，仅为时序验证记录。

### 06-已确认-低-单独打开 SQLite 连接绕过 Host public read path

- **入口/函数**: `_assert_exactly_once_dispatch_outcome`
- **文件(行号)**: `tests/host/test_phase5_local_execution_integration.py:1561`
- **输入场景**: exact-once durable 证据的持久化读取。
- **实际分支**: `with sqlite3.connect(db_path) as connection:` 打开独立连接，不经过 `HostCommandHandle` 的 public read path 或 `HostDurableStore` 的 transaction runner。
- **预期行为**: 直接读取 durable 状态是真源验证。
- **实际行为**: 绕过了 Host public API 可能存在的 read projection/cache/view 层。同时使用 `get_run(host, refs.run_id)`（public API）和 `sqlite3.connect`（raw durable），形成双源验证。这是设计意图，不是缺陷。
- **直接证据**: 行 1560 的 `get_run(host, refs.run_id)`（public owner）与行 1561-1621 的 `sqlite3.connect`（durable owner）构成双 owner 证据。helper docstring（行 1547-1557）明确说明"public 与 durable owner 证据"。
- **影响**: 如果未来 Host 对 durable state 添加了应用层 write-ahead 缓存或 delayed materialization，raw SQLite reads 可能看到与 public API 不同的视图。但在当前 WAL 模式下，已提交事务对独立连接可见，这是安全做法。双源验证设计合理。
- **建议改法和验证点**: 当前设计合理，无需修改。
- **修复风险（低）**: 无需修改。
- **严重程度（低）**: 设计意图验证记录，非缺陷。

### 07-已确认-严重-`utils/smoke_host_public_conversation_memory_scenarios.py` 与 `tests/host/fake_compaction.py` 中 `session_summary.source_labels` 语义不一致

- **入口/函数**: 两个独立实现的 `fake_compaction_proposal_from_material_json`（或语义等价函数）
- **文件(行号)**:
  - `utils/smoke_host_public_conversation_memory_scenarios.py:1990-1998`（仅 `PREVIOUS_SESSION_SUMMARY` + `TRACE_MATERIAL`）
  - `tests/host/fake_compaction.py:564`（全部 boundary labels）
- **输入场景**: 相同的 v2 source_boundary 输入。
- **实际分支**:
  - `utils/` 版本：`session_summary.source_labels` 只包含 `source_kind in (PREVIOUS_SESSION_SUMMARY, TRACE_MATERIAL)` 的 label
  - `tests/host/` 版本：`session_summary.source_labels` 包含所有 boundary item 的 label（含 EVIDENCE_MATERIAL、ANSWER_MATERIAL）
- **预期行为**: 两个 fake compactor 对相同 v2 input 应产出语义一致的 v2 output。
- **实际行为**: 两个实现有不同的 `session_summary.source_labels` 过滤规则。用 `utils/` 的 runtime smoke test 断言 `["T1"]`（符合 utils/ 过滤），而 `tests/host/` 版本的消费者（如 `test_public_compact_smoke.py`）会得到 `["T1", "E1", "A1"]`。这会导致跨 test suite 的 compact v2 output contract 语义漂移：一个 consumer 认为 session_summary 只含 trace-level label，另一个 consumer 认为含全部 label。
- **直接证据**:
  - utils 版本行 1990-1998: `if item[1] in (CompactSourceKindV2.PREVIOUS_SESSION_SUMMARY.value, CompactSourceKindV2.TRACE_MATERIAL.value)` 过滤
  - tests/host 版本行 563-564: `summary_labels = tuple(item.source_label for item in boundary)` 无过滤
  - debug 确认：对相同 3-item input，utils 产量 `["T1"]`，tests/host 产量 `["T1", "E1", "A1"]`
- **影响**: 两个 fake compactor 互不一致。当一个 product consumer（Context Governance accept barrier）期望某种 source_labels 语义时，使用不同 fake 的测试会验证不同的 contract。这可能导致 compact acceptance test 通过但 production acceptance 拒绝（或反过来）。
- **建议改法和验证点**: 两个 fake compactor 必须收敛到同一 `session_summary.source_labels` 规则。推荐以 `utils/` 版本为准（只包含 trace-level label + previous session summary），因为：
  1. `utils/` 版本由 S8 基线确定，与 production v2 contract 对齐（`dayu/host/README.md:739` 的 represented/dropped coverage 约束）
  2. `utils/` 版本的语义更合理：session_summary 是对"会话全貌"的概括，不应重复已在 `evidence_facts`、`answer_anchors` 各自 section 中表达的 label
  3. runtime smoke test 已在用 utils 版本并通过

  注意：此不一致是在 S8 baseline（entry HEAD `df99f858`）中引入的，不是本 corrective slice 的 regression。但它是本 slice 关注的"v2 compact prompt consumer"与"artifact accuracy"的直接风险面。建议在 `tests/host/fake_compaction.py:564` 处增加与 utils 版本一致的 `source_kind` 过滤。
- **修复风险（中）**: 需要检查所有 `tests/host/fake_compaction.py:fake_compaction_proposal_from_material_json` 的调用方是否依赖当前"全部 label"行为。涉及 `test_public_compact_smoke.py` 与 `test_compaction_cancellation_scope.py` 中的调用。
- **严重程度（严重）**: 两个独立 fake compactor 的语义不一致是 silent contract drift —— 不同 test suite 验证不同 compact output schema，可能让 production bug 穿过去。但当前 corrective slice 的 runtime smoke test（使用 utils 版本）的断言是正确的，且本次没有修改 tests/host 版本。

### 08-已确认-中-实现 artifact 中 full-suite flake 诊断缺少可复现 root cause

- **入口/函数**: 实现 artifact §6.1（Cancel-watchdog）、§6.2（Recovery multiprocess）
- **文件(行号)**: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md:111-122`
- **输入场景**: full-suite run（6571 tests）中偶发的 watchdog duplicate 与 SIGKILL delayed recovery timeout。
- **实际分支**: artifact 记录逐线程专项诊断：串行 10+5=15 轮、三进程并发、成对串行 5 轮，所有诊断 pass；full-suite 复跑也 pass。artifact 结论"没有稳定 reproduction 或直接 root cause"。
- **预期行为**: CI-level flake 应有稳定 root cause 或明确排除归因于本 slice。
- **实际行为**: 诊断充分（多次独立 run 均 pass）但无法排除"全仓负载下偶发"的影响。artifact 正确地将此 assign 给 later S8 validation owner，且明确本 slice 不做生产修改、不放宽 timeout。但 flake disposition 的间接证据（诊断通过→不能归因于本 slice）不如直接证据（reproduction→root cause fix）强。
- **直接证据**: artifact 行 113 "该现象只能在一次全仓负载中观察"、行 120 "没有稳定 root cause，也没有证据把它归因于本轮 test consumer 变更"。
- **影响**: 如果这些 flake 实际与本 slice 的 worker lifecycle signal (`wait_until_closed` → 延迟) 有间接关系（本 slice 移除了 `drain_once()` 的同步 barrier，改为依赖 async event），则 flake 可能在 CI 压力下复发。但本 slice 的 exact-once helper 自身不引入新的 race —— 它只在 `wait_until_closed()` 后读取已提交状态。
- **建议改法和验证点**: artifact 的 residual risk 记录已到位。确认 flake 诊断时使用的测试文件版本与最终 corrective slice 完全一致（artifact 提到"修改前先执行目标 node"但不清楚"修改前"是相对于 entry HEAD 还是相对于最终 slice）。
- **修复风险（低）**: 无需修改代码，仅 artifact accuracy。
- **严重程度（中）**: 非 correctness bug，而是 flake disposition 的 evidence strength。建议 artifact 补充：flake 诊断使用的 exact commit hash。

### 09-已确认-低-实现 artifact §7 的 Ruff 97 纠正与 accepted plan 的对齐

- **入口/函数**: 实现 artifact §7
- **文件(行号)**: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md:139-142`
- **输入场景**: S8 artifact 的 full-repository Ruff 97 被记为 readiness blocker。
- **实际分支**: artifact 纠正 S8 artifact 的记录——accepted plan §10-12 没有 full-repository Ruff gate，97 项是既有跨仓 debt。
- **预期行为**: corrective artifact 准确报告 readiness 状态，不将已存在 debt 错归为 blocker。
- **实际行为**: 纠正正确。本 slice 的门禁是 changed Python Ruff（已全绿）。纠正不修改原 S8 artifact。
- **直接证据**:
  - artifact 行 141 "该纠正不声称 97 项 debt 已消失，也不修改原 S8 artifact"
  - 实现 artifact §6 validation table 行 "Changed Python Ruff: All checks passed!"
  - `git diff HEAD --name-only -- dayu/` 确认无 production 修改
- **影响**: 无实际风险。纠正表述准确。
- **严重程度（低）**: artifact accuracy 已验证。

### 10-已确认-低-publication manifest digest 更新仅涉及 3 个文件，其余 40 个文件 SHA-256 不变

- **入口/函数**: publication manifest diff
- **文件(行号)**: `docs/cli_init_workspace_manifest_v1.json:27,39-40`
- **输入场景**: `cli init` 的 workspace publication 校验。
- **实际分支**: 仅更新 `interactive.json`、`conversation_compaction.md`、`conversation_compaction_user.md` 的 SHA-256。其余 40 个文件、5 个目录、16 个 model owner pointer 全部不变。
- **预期行为**: manifest SHA-256 与真实 package 文件内容一致。
- **实际行为**: 三个 digest 更新来源于 S8 基线对 package 文件的修改（非本 slice 所为），本 slice 只是让 publication manifest 与 package 文件保持一致。`FROZEN_MANIFEST_SHA256` 常量同步更新正确。
- **直接证据**: diff 显示仅 3 个文件 + 1 个常量改动；其余 manifest 内容逐行比对一致（通过 JSON parse + fresh publication tree 测试通过，artifact §4 记录）。
- **影响**: publication identity 一致。无 risk。
- **严重程度（低）**: 已验证正确，记录为证据。

### 11-已确认-低-`test_host_assembly.py` 的 prompt assertion 语义分配正确

- **入口/函数**: `test_compose_open_host_options_uses_runtime_tuning_from_config`
- **文件(行号)**: `tests/service/test_host_assembly.py:304-318`
- **输入场景**: compactor baseline prompt 的 system/user 语义分离。
- **实际分支**: 新增断言确认 system prompt 不携带 `<<compaction_request>>`、`dayu.context_compaction.input.v2`、`dayu.context_compaction.output.v2`（行 304-306），但携带 `完整 replacement candidate` 和 `source label 只是本次请求内的引用标签`（行 307-310）；user prompt 携带 placeholder、v2 schema、覆盖规则（行 311-318）。
- **预期行为**: v2 自足 request/schema 的 owner 是 user prompt，system prompt 只拥有稳定任务规则。
- **实际行为**: 断言准确反映 Service 层的 production 装配行为。system prompt 不泄漏 request placeholder 或 schema identifier 是 LLM-facing contract 的正确归属。
- **直接证据**: 行 304-306 的 `not in` 断言与行 311-316 的 `in` 断言形成完整的 semantic ownership 边界验证。
- **影响**: 无 risk。断言增强了对 LLM-facing contract 的 regression 保护。
- **严重程度（低）**: 语义归属验证正确。

## Open Questions

1. **`test_queue_promotion_after_terminal_and_cancel_wakes_dispatch` 中两个 `_assert_exactly_once_dispatch_outcome` 的第一个 assertion（terminal 子场景的行 779-788）不直接验证 `first_terminal` worker 在被 `wait_until_closed()` 等待前是否已完成 dispatch** — 当前依赖 `wait_until_closed()` 事件在 consumer finally block（`dispatch.py:5440`）中设置，已保证 worker close 在 terminal closeout commit 之后。时序是正确的。但 assertion 没有显式检查 `first_terminal` 的 dispatch 发生在 `promoted_terminal` 之前（两个 `wait_until_closed()` 都 await 完后才做 assertion）。这在单 worker 场景中不是问题（closeout 有序），在 scheduler 内部 lane capacity=1 的保证下也成立（一次只有一个 active dispatch）。但如果 lane capacity 被修改，可能引入 ordering 竞争。当前不需要修改。

2. **实现 artifact 中的 validation 结果（"6571 passed"）是否在最终 corrective slice 的 exact commit 上取得？** — artifact §6 的 validation table 记录完整 suite 复跑 `6571 passed` 在 `218.42s`。但未记录复跑时的 HEAD SHA。如果 validation 之后对测试文件有任何调整，validation 结果可能过时。建议 artifact 补充 validation commit hash。

## Residual Risk

| Risk | Owner / Status |
|---|---|
| `tests/host/fake_compaction.py` 与 `utils/smoke_host_public_conversation_memory_scenarios.py` 的 `session_summary.source_labels` 语义不一致（Finding 07） | 本 slice 未修改 `tests/host/fake_compaction.py`；不一致在 S8 baseline 引入。建议后续 work unit 收敛。当前 runtime smoke test（使用 utils 版本）的 v2 assertion 正确。 |
| `_assert_exactly_once_dispatch_outcome` 的列索引脆弱性（Finding 01） | 维护风险，当前有交叉校验保护。 |
| cancel-watchdog flake 与 SIGKILL recovery flake 无稳定 root cause | artifact 已 assign 给 later S8 validation owner。本 slice 的 worker lifecycle signal (`wait_until_closed`) 不引入新的 race（见 artifact §6.1-6.2 诊断）。 |
| Full-repository Ruff 97 | 跨仓 debt，非本 slice 门禁或修改范围。 |
| Frozen real CLI/provider/PTY/evidence bundle 未在本 slice 重跑 | artifact 明确 assign 给 later approved slice（§8 行 151）。 |
| 双 worker factory 累计计数语义（Finding 04） | 不影响正确性检测，但语义不够精确。 |

没有 unclassified residual risk 会 block merge。核心 corrective 改动（publication manifest digest 对齐、v2 compact input/output 更新、Phase5 exact-once evidence、compactor prompt 语义分配）的 owner 边界正确，无 production 修改，无测试悬挂或误通过的直接证据。
