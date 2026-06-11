# WU-PROJ-01 PR Review — AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review gate
- 日期: 2026-06-11
- Reviewer: AgentMiMo
- PR: [#136](https://github.com/noho/dayu-agent-r/pull/136) (draft)
- Branch: `wu-proj-01` → `main`
- Local HEAD: `228c5e44`
- Reviewed range: `main..HEAD` (51 files, +8724 / -250)

## Preflight 检查

| 检查项 | 结果 |
|---|---|
| 当前分支 | `wu-proj-01` ✅ |
| 工作区干净 | ✅ |
| PR 状态 | OPEN, isDraft=true ✅ |
| PR diff 文件列表与本地一致 | ✅ (51 files match exactly) |

## 审查范围

- 生产代码: `dayu/host/compact_material.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/memory_repair.py`、`dayu/host/open_host.py`
- 测试: `tests/host/test_compact_material.py`、`tests/host/test_dispatch_scheduler.py`、`tests/host/test_memory_projection.py`、`tests/host/test_memory_repair.py`、`tests/host/test_open_host_runtime.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_logging.py`
- 设计文档: `docs/host/design.md`
- 控制文档: `docs/host/issues-implementation-control.md`
- Review artifacts: `docs/reviews/wu-proj-01-*` (完整 slice 1-4 review chain)

## 核对清单

### 1. PR diff 与本地 branch 一致

✅ 通过。`gh pr diff 136 --name-only` 输出与 `git diff main..HEAD --name-only` 完全一致，无差异。

### 2. PR body 准确性

✅ 通过。PR body 准确描述了：
- Summary: EventLog-backed compact material view、proactive Context Governance 通过冻结 material view、bounded memory projection catch-up/rebuild、regression coverage。
- Validation: pyright 0 errors、143 passed (AgentDS)、68 passed / 1 skipped / 123 deselected (MiMo validation)、25 passed / 103 deselected (Slice 4 controller validation)。与 aggregate deepreview controller adjudication 记录一致。
- Review Artifacts: plan、aggregate review、control doc 均正确引用。
- Residual Risk: `WU-PROJ-01-S3-R1` 和 `WU-PROJ-01-S4-R1` 正确声明为 deferred。

### 3. 设计真源符合性

✅ 通过。代码实现与 `docs/host/design.md` 以下关键设计要求一致：

- **Line 3139**: Proactive compact material view 由 EventLog-backed builder 生成，而非 Context Governance 临时拼接 → `build_pre_dispatch_compact_material_view` 实现了从 latest accepted `CONTEXT_COMPACTED` 构造 `previous_compacted_view`、从 post-compact delta 构造 material blocks、当前输入作为 anchor。
- **Line 3202**: Compact material build 启动前校验 EventLog / payload / artifact source refs 与 digest → `CompactMaterialSourceBoundary` 与 `PreDispatchCompactMaterialView.__post_init__` 执行完整边界校验。
- **Line 3204**: Ordinary dispatch 前 snapshot cursor 不能覆盖 required cursor 时执行 bounded catch-up/rebuild → `_build_engine_run_request` 中 `MemoryProjectionRepairRequired` 捕获后调用 `rebuild_conversation_memory_projection`，带 `_memory_projection_catchup_budget` 总预算。
- **Line 3186-3192**: compact material selection 确定性输出、已代表内容不重复展开 → `select_compact_segment` 实现确定性排序与 exclusion reason codes。
- **Line 3194-3200**: material data block section 映射一对一，无跨 section 重复 → `_raise_on_duplicate_section_owner` 校验。
- **Line 2834**: compact material LLM-facing 语义自解释，不暴露内部治理标识 → evidence query text 使用 `_readable_query_text_from_envelope` 从 request atom 恢复可读文本，缺失时产生 limited-signal 而非暴露 digest/cursor。

### 4. 控制文档完整性

✅ 通过。`docs/host/issues-implementation-control.md` 记录：
- WU-PROJ-01 状态: `review`
- Draft PR: `https://github.com/noho/dayu-agent-r/pull/136`
- Accepted deepreview commit: `84e40096`
- Residual risks: `WU-PROJ-01-S3-R1` (deferred-with-owner → Host dispatch test hardening)、`WU-PROJ-01-S4-R1` (deferred-with-owner → Host dispatch scheduler test hardening)
- Next gate: WU-PROJ-01 PR review gate via AgentMiMo / AgentDS

### 5. PR 级 Blocking Issue 扫描

#### 5a. 漏提交

✅ 无漏提交。PR diff 包含完整 4-slice 实现链：compact_material.py (+1291 lines)、dispatch.py (+497/-)、engine_ingest.py (+30)、memory_repair.py (+263/-)、open_host.py (+28/-)，以及对应的 7 个测试文件和 review/plan/control 文档。

#### 5b. PR body 误导

✅ 无误导。PR body 的 validation 数据与 aggregate deepreview controller adjudication 记录完全一致。

#### 5c. Diff 泄漏无关文件

✅ 无泄漏。51 个变更文件全部属于 WU-PROJ-01 scope：
- 6 个生产代码文件 (compact_material, dispatch, engine_ingest, memory_repair, open_host, host/README.md)
- 7 个测试文件
- 38 个文档/review artifact 文件
- 无 UI/Service/Engine/Fins 层文件泄漏

#### 5d. 残余风险无 owner

✅ 残余风险均有 owner：
- `WU-PROJ-01-S3-R1`: deferred-with-owner → Host dispatch test hardening
- `WU-PROJ-01-S4-R1`: deferred-with-owner → Host dispatch scheduler test hardening
- 两项均为测试覆盖/稳定性增强，不阻塞 PR gate

#### 5e. 测试/pyright 证据

⚠️ 发现非阻塞问题（见 Findings）。

## 验证

### pyright

```
0 errors, 0 warnings, 0 informations
```
✅ 通过。

### 测试

**PR 引入的新/修改测试** (118 passed):
```
tests/host/test_compact_material.py    — passed
tests/host/test_memory_repair.py       — passed
tests/host/test_memory_projection.py   — passed
tests/host/test_open_host_runtime.py   — passed
tests/host/test_run_input_builder.py   — passed
tests/host/test_logging.py             — passed
```
✅ 通过。

**dispatch scheduler 测试** (121 passed, 3 failed):
```
FAILED tests/host/test_dispatch_scheduler.py::test_dispatch_lag_repair_rebuild_retry_does_not_fail_run
FAILED tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering
FAILED tests/host/test_dispatch_scheduler.py::test_persistent_memory_lag_repair_failure_closes_starting_run
```

⚠️ 3 个测试失败。经核实，**这 3 个测试在 main 分支上同样失败**，是预存问题，非本 PR 引入。

根因分析：这 3 个测试的 `_LagRepairRunInputBuilder` / `_PersistentLagRepairRunInputBuilder` 固定设置 `required_event_sequence=20`，但测试 fixture `_seed_current_run` 只在 EventLog 中写入约 5 个事件。`rebuild_conversation_memory_projection` 在扫描完所有可用事件后因 `events_scanned < limit` 停止（stop_reason=idle），finished_cursor=5，未达到 required=20。`_raise_if_memory_projection_target_not_reached` 抛出 `_MemoryProjectionDispatchDiagnosticError`，导致 Run 进入 FAILED 而非预期的 RUNNING。

这表明测试 fixture 缺少足够的 EventLog 事件来满足 rebuild 目标，与 `WU-PROJ-01-S3-R1`（dispatch test hardening）的 residual risk 描述一致。

## Findings

| # | 严重度 | 描述 | 裁决 |
|---|---|---|---|
| F1 | Low | 3 个 dispatch scheduler 测试在 main 上预存失败（`required_event_sequence=20` 但 fixture 只有 ~5 events） | non-blocking；预存问题，与 `WU-PROJ-01-S3-R1` / `WU-PROJ-01-S4-R1` residual risk 描述一致，不阻塞本 PR |
| F2 | Info | `_memory_projection_catchup_budget` 的 unsupported purpose defensive branch 无直接测试 | non-blocking；aggregate deepreview 已裁决为 rejected-as-nonblocking (AgentMiMo NF1) |

## 结论

**PASS-WITH-FINDINGS**

WU-PROJ-01 PR 136 通过 PR review gate。核心判断：

1. PR diff 与本地 branch 完全一致，无漏提交、无泄漏。
2. PR body 准确描述 scope、validation 和 residual risk。
3. 实现符合 `docs/host/design.md` 的 EventLog-backed compact material truth、bounded memory projection catch-up/rebuild、Context Governance 单向关系等关键设计约束。
4. 控制文档完整记录 PR 136、accepted deepreview commit、residual risk owner 和下一 gate。
5. pyright 0 errors；PR 引入的新测试 118 passed。
6. 3 个 dispatch scheduler 测试失败为 main 预存问题，非本 PR 引入，已有 residual risk owner。

无 blocking finding。建议进入下一 gate。
