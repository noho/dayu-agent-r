# P8.5 Tool Truncation Contract Cleanup Fix Report

- work gate name: `fix`
- work-unit name: P8.5 follow-up fix — remove public ToolTruncationInfo contract leakage
- source review artifact: `docs/host/phase8.5-tool-truncation-contract-cleanup-code-review.md`
- implementation artifact: `docs/host/phase8.5-tool-truncation-contract-cleanup-implementation-report.md`
- controller-accepted finding ids: `1`
- artifact path: `docs/host/phase8.5-tool-truncation-contract-cleanup-fix-report.md`

## Per-Finding Fix Status

### Finding 1 — serializer 仍接受旧 top-level ToolResultSuccess.truncation 行并静默丢弃

- status: fixed
- fix summary: `dayu/host/_run_event_serializer.py` 的 `_decode_result_success(...)` 现在显式拒绝 success result 顶层 `truncation` 字段，遇到旧 schema 行直接抛 `ValueError`，不再兼容读取或静默丢弃。
- verification: `tests/host/test_phase6_run_event_serializer.py` 新增旧 `outcome.result.truncation` payload 负测，断言反序列化失败；既有 ordinary `value["truncation"]` roundtrip 测试继续通过。
- stop condition status: 未触发。fail-fast 没有破坏当前 new schema ordinary value truncation roundtrip；未添加旧 schema compat path。

## Changed Files

- `dayu/host/_run_event_serializer.py`
- `tests/host/test_phase6_run_event_serializer.py`
- `docs/host/phase8.5-tool-truncation-contract-cleanup-fix-report.md`

## Documentation Sync Decision

- `tests/README.md`: not updated. 本次只新增 serializer schema 负测，没有改变测试分层、运行命令或维护规则。
- Host / Engine / migration design docs: not updated in this fix pass. 当前改动只收紧 serializer 对旧 schema 的读取边界，既有 P8.5 contract cleanup 文档事实未变化。

## Validation Commands And Results

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: passed, `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/host/test_phase6_run_event_serializer.py -q`
  - result: passed, `12 passed in 0.12s`
- `source .venv/bin/activate && pytest tests/contracts tests/engine -q`
  - result: passed, `327 passed in 1.10s`
- `source .venv/bin/activate && pytest tests/host -q`
  - result: passed, `377 passed in 2.70s`
- `source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q`
  - result: passed, `17 passed in 0.05s`
- `rg "ToolTruncationInfo|truncation=" dayu tests`
  - result: passed for expected boundary; only negative export tests mention `ToolTruncationInfo`, and no `truncation=` constructor usage remains.
- `rg "ToolTruncationInfo" dayu/contracts dayu/engine dayu/host dayu/host/README.md tests/README.md docs/host/design.md docs/host/migration-plan.md`
  - result: passed for expected boundary; only `docs/host/migration-plan.md` records the fixed residual.

## New Risks / Open Questions

- new risks: none identified.
- new open questions: none.
- plan deviation: none. Fix stayed within controller-accepted Finding 1 and allowed file scope.

## Residual Risk Classification

- current-slice fixed: Finding 1 is fixed and covered by serializer negative test plus existing ordinary value truncation roundtrip.
- accepted as covered by later slice: none.
- assigned to later phase/work unit: none introduced by this fix.
- tracked by existing issue: none introduced by this fix.
- requiring new issue or explicit user decision: none.
