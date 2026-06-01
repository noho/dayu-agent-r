# Code Re-Review

## Gate

- **Gate**: Slice 5 DS focused-fix re-review
- **Work Unit**: WU-STRESS-01
- **Slice**: Slice 5 mixed Host stress with deterministic fault injection
- **Role**: AgentDS independent re-review
- **Output file**: docs/reviews/wu-stress-01-code-rereview-slice5-ds-20260601.md
- **Review date**: 2026-06-01

## Scope

- Mode: current changes (focused fix after controller adjudication)
- Branch: test/host-stress-suite
- Base: main
- Included scope: `tests/host/test_host_production_stress.py` (unstaged changes from Codex fix), `tests/host/stress_support.py` (unstaged, Slice 5 baseline)
- Excluded scope: committed slices 1-4, production code
- Sources:
  - `docs/reviews/wu-stress-01-code-controller-adjudication-slice5-20260601.md`
  - `docs/reviews/wu-stress-01-code-review-slice5-ds-20260601.md`
  - `docs/reviews/wu-stress-01-code-review-slice5-mimo-20260601.md`
  - `docs/reviews/wu-stress-01-fix-slice5-codex-20260601.md`

## Review Pass/Fail

**PASS**

Both DS low findings are properly closed. The fix introduces no new issues, no production code changes, and no contract/schema changes.

## Validation of DS Findings Closure

### DS-01: `_SLICE5_PRIMARY_TERMINAL_COUNTS` 注释已添加

- **Adjudication 要求**: 在 `_SLICE5_PRIMARY_TERMINAL_COUNTS` 附近添加中文注释，解释每项的含义和 `RUN_LOST` 排除原因。
- **实际状态**: `tests/host/test_host_production_stress.py:122-124` 已添加三行中文注释，说明 session0 crash/recovery 的 RUN_LOST 和 session2 stream exception 均不作为 HostEvent 发给 watcher，因此 primary 期望为 `(4, 5, 4)`。
- **判定**: ✅ 已关闭。

### DS-02: `_slice5_timeout_summary` dedupe 字段一致性已修复

- **Adjudication 要求**: 将 `terminal_dedupe_ok` 改为 `True` 与 `terminal_duplicate_count=0` 保持一致；保留 `failure_boundary="unknown"` 作为失败信号。
- **实际状态**: `tests/host/test_host_production_stress.py:2112` 已从 `terminal_dedupe_ok=False` 改为 `terminal_dedupe_ok=True`。现在 `terminal_duplicate_count=0, terminal_dedupe_ok=True` 一致表达"timeout 路径上没有重复证据"语义，`failure_boundary="unknown"` 保留为失败信号。
- **判定**: ✅ 已关闭。

## Additional Checks

### 无新增问题

- 注释新增仅影响可读性，不改变运行时行为。
- 布尔值从 `False` 改 `True` 仅影响 timeout 失败路径的 summary JSON 诊断字段，且语义从"矛盾"修正为"一致"。该字段不在任何断言中使用（timeout 路径本身已通过 `failure_boundary="unknown"` 标记为失败），不改变测试通过/失败结果。

### 无生产代码修改

- 全量 diff（unstaged + staged）仅涉及 `tests/host/stress_support.py` 和 `tests/host/test_host_production_stress.py`。
- `dayu/` 下无任何 `.py` 文件被修改。

### 无 contract/schema 变更

- `HostStressScenario` dataclass 是测试层内部类型，明确文档声明"不作为 Host public contract"。
- 无 durable schema 变更，无 public API 签名变更，无 HostEvent/HostEventKind/HostTerminalStatus 修改。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

与 DS 初版 review 一致，无新增风险：

- `pytest-timeout` 120s 全局超时可在 event loop 全局阻塞时 SIGTERM 整个进程，此时 `_slice5_timeout_summary` 不会执行。这是 pytest-timeout 固有局限。
- `max(summary_watch_lag_samples)` 在 `summary_watch_lag_samples` 为空 tuple 时会抛出 `ValueError`。当前调用顺序保证非空，但未来重构可能暴露。
- `HostEventKind` 无 `LOST` 成员是 Host public contract 设计约束，非 Slice 5 缺陷。
