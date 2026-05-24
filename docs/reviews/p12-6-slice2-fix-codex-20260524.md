# P12.6 Slice 2 Targeted Fix Artifact - AgentCodex

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 2 deterministic Segment Selection / Material Pack Builder
- Gate: code review targeted fix
- Role: AgentCodex targeted fix specialist
- Source adjudication: `docs/reviews/p12-6-slice2-code-review-controller-adjudication-20260524.md`
- Non-goals: 不处理 DS M3、snapshot text escaping、stable kind ordering；不改 Engine / Service / Fins / public Host API；不提交、不 push、不修改 `docs/host/implementation-control.md`。

## 动机判断

A1 / A2 / A3 的修复动机成立，且范围应保持最小。A1 是 renderer 与 classifier 之间的同模块脆弱字符串重复；A2 是实现相对 plan §6.6 多引入未裁决 inline delta 硬门槛；A3 是类型注解表达的 key 语义与实际 block id 不一致。三项均可通过局部修复完成，不需要重新设计 public contract。

## Accepted Findings 修复状态

### A1 - 已修复 - `_memory_material_kind` uses fragile string prefix matching

- 改动文件：`dayu/host/run_input.py`
- 修复方式：抽出 memory section header 私有模块常量，message renderer 与 `_memory_material_kind(...)` 共享同一 typed source，不再各自硬编码重复 header 文案。
- API 影响：无 public API 变更。

### A2 - 已修复 - snapshot cursor inline repair uses an extra undocumented hard threshold

- 改动文件：`dayu/host/compact_material.py`、`tests/host/test_compact_material.py`
- 修复方式：`check_compact_memory_snapshot_cursor(...)` 的 inline delta gate 只使用 `policy.max_lag_events_for_inline_delta`；删除 `lag_events > policy.max_delta_repair_events` 附加硬门槛。
- 测试同步：新增 `test_snapshot_cursor_inline_delta_uses_inline_lag_threshold_only`，覆盖 lag 在 inline 阈值内但超过 delta repair budget 时仍接受 inline delta view。

### A3 - 已修复 - `excluded_reason_codes` key annotation implies prompt-local label

- 改动文件：`dayu/host/compaction.py`
- 修复方式：将 `CompactSegmentSelection.excluded_reason_codes` 注解改为 `Mapping[str, str]`，与 docstring 中的 block id key 语义一致，避免误导为 prompt-local material label。
- API 影响：运行时 shape 未变，仍为字符串到字符串的只读 mapping。

## 验证结果

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
# 93 passed in 1.82s
```

```bash
source .venv/bin/activate && python -m pyright dayu/host/compact_material.py dayu/host/run_input.py dayu/host/memory.py dayu/host/memory_repair.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py
# 0 errors, 0 warnings, 0 informations
```

```bash
git diff --check
# passed
```

## README 决策

无需更新 README。本次修复只收敛 Slice 2 内部实现质量与类型注解语义，不改变 Host 对外稳定行为、开发手册中的 compact material 语义、测试运行方式或用户命令。

## 剩余风险

- DS M3 `event_sequence=None` 已按 controller 裁决 deferred 到 Slice 5，本次未处理。
- Snapshot text escaping / stable kind ordering 为 non-blocking residual，本次未处理。
- 当前工作区已有 Slice 2 implementation diff 与 `docs/host/implementation-control.md` 变更；本次 fix 未提交、未 push，也未修改 control doc。

## Completion

Targeted fix complete. Accepted findings A1 / A2 / A3 均已修复并通过指定验证。
