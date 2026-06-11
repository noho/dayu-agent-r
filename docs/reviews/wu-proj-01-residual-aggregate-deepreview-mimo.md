# WU-PROJ-01 Residual Aggregate Deepreview

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: aggregate deepreview
- Date: 2026-06-11
- Reviewer: AgentMiMo
- Mode: current changes
- Branch: `wu-proj-01`
- Base: `d0dfd7d9`
- Output file: `docs/reviews/wu-proj-01-residual-aggregate-deepreview-mimo.md`
- Included scope:
  - commit `448b70ba` (CAP-R1): 去掉 compact material / compaction evidence query 固定截断、delta/evidence caps、required/rebuild projection correctness batch budgets
  - commit `3baeef53` (S3/S4): dispatch checkpoint-covered happy path 测试；reactive fallback flaky lane timeout fixture hardening
  - 当前未提交 `docs/host/issues-implementation-control.md` gate 状态更新
- Excluded scope: 无
- Parallel review coverage: 无

## Scope

审查范围覆盖 CAP-R1 与 S3/S4 两个 accepted slice commit 的全部生产代码与测试变更，以及控制文档 gate 状态更新。设计真源为 `docs/host/design.md` 与 `docs/engine/design.md`。总控文档为 `docs/host/issues-implementation-control.md`。

必读 artifacts：
- `docs/reviews/wu-proj-01-cap-r1-rereview-controller-adjudication.md`
- `docs/reviews/wu-proj-01-s3-s4-code-review-controller-adjudication.md`
- `docs/reviews/wu-proj-01-s3-s4-residual-controller-adjudication.md`

## Findings

未发现实质性问题。

## Non-Blocking Findings

### NF-1-信息-控制文档 CAP-R1 测试计数微小偏差

- **入口/函数**: `docs/host/issues-implementation-control.md` WU-PROJ-01 状态行
- **文件(行号)**: `docs/host/issues-implementation-control.md:227`
- **输入场景**: 控制文档记录 CAP-R1 focused tests 计数
- **实际分支**: 文档写 "CAP-R1 focused tests -> 173 passed"
- **预期行为**: 当前运行同一组测试文件得到 174 passed（S3/S4 commit 在 `test_dispatch_scheduler.py` 新增了 1 个测试）
- **实际行为**: 173 vs 174 的 1 条偏差
- **直接证据**: `python -m pytest tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py` -> 174 passed
- **影响**: 仅文档精度，不影响正确性、测试稳定性或 gate 结论
- **建议改法和验证点**: 可选更新计数为 174 或注明 S3/S4 新增测试后合计为 174
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

无。active residual risk 表中无 WU-PROJ-01 条目。

## 正确性审查

### CAP-R1: 截断与 caps 移除

- `compact_material.py`: 移除 `_READABLE_QUERY_TEXT_MAX_CHARS`(1200)、`_READABLE_QUERY_TRUNCATED_MARKER`、`_DEFAULT_PRE_DISPATCH_MAX_DELTA_EVENTS`(256)、`_DEFAULT_PRE_DISPATCH_MAX_EVIDENCE_BLOCKS`(8)。`build_pre_dispatch_compact_material_view` 不再接受 `max_delta_events` / `max_evidence_blocks` 参数。`_bounded_query_text` 重命名为 `_normalized_query_text`，只做空白规范化，不截断。
- `compaction_evidence.py`: 同步移除 `_READABLE_QUERY_TEXT_MAX_CHARS`、`_READABLE_QUERY_TRUNCATED_MARKER`，`_bounded_query_text` 重命名为 `_normalized_query_text`。
- 正确性：post-compact delta 与 accepted evidence blocks 不再被固定条数裁剪，semantic query text 完整保留。这与 design.md 要求 compact material 从 EventLog durable truth 完整构造一致。

### CAP-R1: required/rebuild projection budget 移除

- `dispatch.py`: 移除 `_MEMORY_PROJECTION_BEST_EFFORT_MAX_BATCHES`(1)、`_MEMORY_PROJECTION_REQUIRED_BEFORE_DISPATCH_MAX_BATCHES`(16)、`_MEMORY_PROJECTION_REBUILD_BEFORE_DISPATCH_MAX_BATCHES`(32)。required catch-up 和 rebuild 路径传 `budget=None`。保留 `_OPPORTUNISTIC_AFTER_COMPACT_MEMORY_PROJECTION_BATCH_COUNT`(1) 用于 compact 后非 correctness 推进。
- `open_host.py`: 同步重命名为 `_OPPORTUNISTIC_AFTER_COMMIT_MEMORY_PROJECTION_BATCH_COUNT`，docstring 明确不参与 dispatch 前 required/rebuild correctness catch-up。
- 正确性：`catch_up_conversation_memory_projection` 和 `rebuild_conversation_memory_projection` 在 `budget=None` 时无批次数/扫描事件上限，追到 target cursor、idle 或 failure。opportunistic 路径仍保持 1 batch 行为。这与 design.md 要求 correctness 路径不受固定预算截断一致。

### S3/S4: dispatch checkpoint-covered happy path

- `test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input`: 预热 memory projection 到 required cursor 以下 1，确认 checkpoint 已覆盖。dispatch 时 monkeypatch `catch_up_conversation_memory_projection` 观察返回值。断言：dispatch 内部 catch-up 被调用 1 次、started_cursor == finished_cursor == required_event_sequence、events_scanned == 0、target_reached is True、worker accepted、Run 进入 RUNNING、无 RUN_FAILED/RUN_RECOVERING。
- 正确性：该测试覆盖 checkpoint 已覆盖 required cursor 时不阻断 ordinary RunInput 构造的 happy path，与 S3-R1 裁决一致。

### S3/S4: reactive fallback flaky 修复

- `test_reactive_compact_failure_fallback_dispatch_uses_failed_view`: 新增 `lane_default_timeout_seconds=1.0`，避免 10ms lane acquire 窗口导致的偶发失败。
- 正确性：不修改生产 lane acquire 语义，只消除无关 timing 风险。所有原有断言（fallback artifact、第二次 dispatch request、Attempt 数量、无 CONTEXT_COMPACTED、无 RUN_LOST）均保留。

### 控制文档 gate 状态

- WU-PROJ-01 状态从 `implementation` 更新为 `aggregate-deepreview`，与当前 gate 一致。
- 记录 CAP-R1 `448b70ba` 和 S3/S4 `3baeef53` 为 accepted commits。
- Residual risk 表无 WU-PROJ-01 条目：CAP-R1、S3-R1、S4-R1 均已在对应 controller adjudication 中关闭。

## Design Alignment

- 截断移除与 design.md 一致：compact material 从 EventLog durable truth 完整构造，不在 source builder 阶段用固定限制裁剪。
- budget 移除与 design.md 一致：correctness 路径（required catch-up、rebuild）不受固定批次预算约束。
- opportunistic one-batch 行为保留与 design.md 一致：compact accepted 后的轻量推进是非 correctness 行为。
- LLM-facing material semantics：query text 不再包含截断标记 `[truncated_query_text]`，完整 semantic query 或 arguments 对 compactor 可见。
- test robustness：S4 flaky 修复通过增加测试专用 lane timeout 消除无关 timing 风险。

## 验证

- `python -m pytest tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py` -> 174 passed
- `pyright` -> 0 errors
- `git diff --check` -> passed

## 结论

**PASS**
