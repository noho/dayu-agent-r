# P8.5 Slice 6 Code Review

## Review Gate

- review gate name: `code review`
- work-unit name: P8.5 — P8 Stabilization / ToolRuntime Event Model
- assigned slice id: Slice 6 — Documentation / Migration Registry Closeout
- reviewed target: workspace diff from baseline `8e5ca33` plus `docs/host/phase8.5-s6-implementation-report.md`
- approved plan path: `docs/host/phase8.5-plan.md`
- implementation artifact: `docs/host/phase8.5-s6-implementation-report.md`
- artifact path: `docs/host/phase8.5-s6-code-review.md`

## Reviewer Conclusion

当前 Slice 6 文档总体按 accepted plan 收口：Host README 没有把旧 `ToolFetchMore*` / `TOOL_CURSOR_*` /
`TOOL_RESULT_TRUNCATED` 作为当前接口保留，`docs/host/design.md` 修正了 P7-era inline raw payload 与 trace
checkpoint transaction 旧事实，implementation report 也完整记录了已知验证失败。

本 review 发现 2 个需要 controller 裁决的 blocker / residual-tracking finding。尤其是
`pytest tests/contracts tests/engine -q` 的失败不是当前证据下的生产代码契约漂移：代码、Engine README 与
Slice 4 artifact 均显示 `partial_tool_calls` / `PartialToolCallSummary` 是已接受的 SSE partial diagnostic
契约，失败来自 Engine 显式字段 / 包根导出白名单测试仍锁定旧集合。它阻断当前 work unit closeout / PR gate，
应作为跨 slice validation fix 更新测试断言，而不是回滚代码契约。

## Findings

### S6-CR-01-未修复-[高]-Engine partial_tool_calls 新契约已落地但白名单测试仍锁旧字段集合
- **入口/函数**: `pytest tests/contracts tests/engine -q`；`test_provider_protocol_error_engine_data_has_explicit_fields` / `test_provider_protocol_error_runner_data_has_explicit_fields` / `test_engine_all_matches_expected_set`
- **文件(行号)**: `tests/engine/test_metadata_boundary.py:48`、`tests/engine/test_metadata_boundary.py:61`、`tests/engine/test_package_exports.py:124`
- **输入场景**: 运行 Slice 6 plan 要求的 contracts + engine validation。
- **实际分支**: 字段集合断言仍只允许旧的 protocol error 字段；包根导出白名单仍不包含 `PartialToolCallSummary`。
- **预期行为**: 按 P8.5 Slice 4 当前设计，provider / runner protocol error data 应显式携带 bounded `partial_tool_calls` 诊断，`dayu.engine.__all__` 可导出对应公共 summary type。
- **实际行为**: 测试失败报告 `partial_tool_calls` 是额外字段，`PartialToolCallSummary` 是额外导出，导致 `pytest tests/contracts tests/engine -q` 为 `3 failed, 323 passed`。
- **直接证据**: `ProviderProtocolErrorData` 当前在 `dayu/engine/contracts/engine_events.py:198` 文档化 `partial_tool_calls`，字段定义在 `dayu/engine/contracts/engine_events.py:207`；`RunnerProtocolErrorData` 当前在 `dayu/engine/contracts/runner_events.py:157` 文档化该字段，字段定义在 `dayu/engine/contracts/runner_events.py:165`；`dayu.engine.__all__` 在 `dayu/engine/__init__.py:145` 导出 `PartialToolCallSummary`；Engine README 已在 `dayu/engine/README.md:70` 说明 provider protocol error 携带 bounded `partial_tool_calls` 摘要；本地复跑 `source .venv/bin/activate && pytest tests/contracts tests/engine -q` 复现同样 3 个失败。
- **影响**: work unit 级必跑 validation 不能通过，PR gate 不能 clean closeout；若把它当作代码漂移去回滚字段，会破坏 Slice 4 已接受的 SSE partial diagnostic 设计。
- **建议改法和验证点**: 做一个跨 slice validation fix：更新 `tests/engine/test_metadata_boundary.py` 的 expected field set，纳入 `partial_tool_calls`；更新 `tests/engine/test_package_exports.py` 的 `EXPECTED_EXPORTS`，纳入 `PartialToolCallSummary`；必要时补一条断言确保 summary 不含 raw arguments。验证 `pytest tests/contracts tests/engine -q`、`pytest tests/host -q`、`python -m pyright dayu/ tests/ utils/`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高
- **controller decision status**: `pending-controller-decision`

### S6-CR-02-未修复-[中]-transport-layer partial diagnostic residual 没有明确 phase/issue owner
- **入口/函数**: P8.5 residual registry closeout
- **文件(行号)**: `docs/host/migration-plan.md:178`
- **输入场景**: controller 按 Slice 6 目标检查每项 P8.5 residual 是否已 fixed / deferred / issue-tracked。
- **实际分支**: registry 把 “SSE 中途失败导致 partial tool call 缺少完整 trace 语义” 的 owner 写成 `P8.5 Slice 4`，status 又写 “transport-layer read failures remain later provider adapter coverage”。
- **预期行为**: 若 provider protocol error 部分已 fixed，而 transport-layer read failure 仍是 residual，registry 必须给这个 residual 一个明确 destination，例如具体 later phase / work unit / GitHub issue / user decision。
- **实际行为**: “later provider adapter coverage” 不是可执行 owner，也不是 issue 编号或 phase；同一行 owner 仍指向已完成的 `P8.5 Slice 4`，无法区分已修复部分和仍 deferred 的 transport-layer 覆盖面。
- **直接证据**: accepted plan 的 residual owner table要求 residual 有 owner；Slice 4 implementation report 已把 “provider stream transport-layer read failure 目前仍走 HTTP error 语义” 标为 later coverage；当前 migration registry 只保留模糊的 “later provider adapter coverage”，没有 phase / issue / work-unit id。
- **影响**: residual registry 不能支撑 Gateflow closeout / PR gate；后续 controller 无法判断该剩余风险是否已被 P9/P15/P16、现有 issue 或新 issue 承接。
- **建议改法和验证点**: 将 line 178 拆成两行：provider protocol error partial diagnostic 标 `P8.5 Slice 4 | fixed, validated`；transport-layer read failure coverage 单独标 `deferred-with-owner`，并写明具体 phase / work unit / issue number。同步 implementation report 的 residual risk wording，避免继续使用无主的 “later provider adapter coverage”。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中
- **controller decision status**: `pending-controller-decision`

## Open Questions And Residual Risk

- `docs/host/migration-plan.md` 的 P9 / P15 / P16 / issue #41 owner 基本明确；issue #36 / #38 也有追踪目的地。
- `dayu/host/README.md` 与 `tests/README.md` 未发现旧 ToolRuntime 专属事件 / public fetch_more handle 被写成当前接口。
- `docs/host/migration-plan.md` 中旧 `TOOL_FETCH_MORE*` / `TOOL_CURSOR_*` / `TOOL_RESULT_TRUNCATED` 命中属于历史、审计或 residual context，符合 plan 的 historical-doc guard。
- 未发现 `docs/host/design.md` 本次 diff 把未实现的 P9/P15/P16 行为写成已完成；P9/P15/P16 在 migration plan 与 README 中仍被标为未实现 / planned / deferred。

## Validation Performed During Review

```bash
source .venv/bin/activate && pytest tests/contracts tests/engine -q
```

Result: failed, `3 failed, 323 passed in 1.09s`，失败项与 implementation report 记录一致。

```bash
git diff --check
```

Result: passed.
