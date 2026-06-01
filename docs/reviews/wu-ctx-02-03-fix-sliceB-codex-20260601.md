# WU-CTX-02 + WU-CTX-03 Slice B Fix Artifact

## Gate / Scope

- **Current gate**: WU-CTX-02 + WU-CTX-03 Slice B fix
- **Fix agent**: Codex
- **日期**: 2026-06-01
- **Fix 范围**: 只修 controller accepted findings DS-F1、DS-F2。
- **明确非目标**: 不修 DS-F3、DS-F9；不改 production behavior；不进入 review、commit、push 或 PR。

## Source Review Artifacts

- `docs/reviews/wu-ctx-02-03-code-review-sliceB-mimo-20260601.md`
- `docs/reviews/wu-ctx-02-03-code-review-sliceB-ds-20260601.md`
- `docs/reviews/wu-ctx-02-03-code-controller-adjudication-sliceB-20260601.md`

## Accepted Finding IDs

- DS-F1: `_assert_failed_payload_no_fallback` 在两个测试模块中逐字重复。
- DS-F2: `_validate_failed_fallback_fields` 拒绝路径缺少显式单元测试。

## Per-Finding Fix Status

| Finding | 状态 | 修复说明 | 验证点 |
|---|---|---|---|
| DS-F1 | 已修复 | 新增 `tests/host/_context_compaction_assertions.py`，集中提供 `assert_failed_payload_no_fallback`；`test_dispatch_scheduler.py` 与 `test_engine_ingest_mapping.py` 改为复用该 helper，并删除各自重复 helper。helper 使用 `Mapping[str, JsonValue]`、`str | None`、`int`、`bool` 的严格签名，未使用 `Any` / `object`，并提供中文 docstring。 | `rg _assert_failed_payload_no_fallback tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/_context_compaction_assertions.py` 无旧重复 helper；pytest 与 pyright 均通过。 |
| DS-F2 | 已修复 | `test_context_compact_events.py` 新增三类拒绝路径测试：`not_applicable` 携带任一 fallback 诊断字段非 `None` 必须拒绝；`dispatch` 缺失或置空必需 fallback 字段必须拒绝；`fail_closed` 缺失或置空必需 fallback 字段必须拒绝。 | 新增测试随指定 pytest 命令通过；pyright 通过。 |

## Changed Files

- `tests/host/_context_compaction_assertions.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `docs/reviews/wu-ctx-02-03-fix-sliceB-codex-20260601.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q`
  - Result: PASS
  - Output summary: `129 passed in 1.38s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: PASS
  - Output summary: `0 errors, 0 warnings, 0 informations`

## Docs Decision

- 已检查 `tests/README.md`。本次只新增同层级测试 helper 与现有 context compact validator 拒绝路径测试；未新增测试层级、运行方式或维护规则，README 当前职责说明仍匹配代码事实。
- Allowed write files 不包含 README；无必要更新。

## Finding Title Status Update

- Source review artifacts 不在本 handoff 的 allowed write files 内，未回写原 review 标题。
- 本 artifact 记录最终 fix 自报状态：
  - DS-F1: 已修复
  - DS-F2: 已修复
  - DS-F3: deferred-with-owner，未处理，owner 仍为 WU-CTX Slice D / aggregate review
  - DS-F9: rejected-with-reason，未处理

## New Risks / Open Questions

- 新增 blocking open questions: 无。
- 新增风险: 无。

## Residual Risk Classification

- DS-F3: deferred-with-owner，继续归属 WU-CTX Slice D / aggregate review；本 fix 未扩大范围。
- DS-F9: rejected-with-reason，不处理。
- 本 fix 引入的 residual risk: 无已知未分类风险。

## Artifact Path

- `docs/reviews/wu-ctx-02-03-fix-sliceB-codex-20260601.md`
