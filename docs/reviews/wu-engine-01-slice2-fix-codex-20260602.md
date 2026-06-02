# WU-ENGINE-01 Slice 2 Fix Artifact

## Gate / Role

- Current gate: Slice 2 fix
- Role: WU-ENGINE-01 Slice 2 fix agent
- Work unit: WU-ENGINE-01 Runner diagnostic payload audit
- Implementation artifact: `docs/reviews/wu-engine-01-slice2-implementation-codex-20260602.md`
- Source review artifacts:
  - `docs/reviews/wu-engine-01-slice2-code-review-mimo-20260602.md`
  - `docs/reviews/wu-engine-01-slice2-code-review-ds-20260602.md`
- Controller adjudication: `docs/reviews/wu-engine-01-slice2-code-review-controller-adjudication-20260602.md`

## Scope

- 只修 controller accepted findings。
- 未修 controller rejected finding `MIMO-001`，测试继续保留对 `diagnostic_payload` 私有常量的导入。
- 未提交、未 push、未创建 PR、未进入其他 gate。
- 未修改 controller / reviewer artifacts 或总控文档。

## Changed Files

- `dayu/engine/runners/openai/runner.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `docs/reviews/wu-engine-01-slice2-fix-codex-20260602.md`

## Per-finding Fix Status

### DS-1-已修复-[中]-`_HTTPErrorBody.raw_payload` 私有文档仍承诺原始载荷

- **Controller decision**: accepted
- **Fix**: 更新 `_HTTPErrorBody.raw_payload` docstring，说明该字段是从有界 HTTP body 派生的有界诊断载荷；解析失败或非 JSON object 时为 `None`。
- **Changed file**: `dayu/engine/runners/openai/runner.py`

### MIMO-002-已修复-[低]-context overflow HTTP JSON path 缺少 raw_payload 诊断断言

- **Controller decision**: accepted
- **Fix**: 在 `test_http_context_overflow_maps_to_context_length_exceeded` 的测试 body 中加入 provider error `type`，并复用 `_assert_http_diagnostic_payload` 断言 `raw_payload` 包含 `context_length_exceeded` 和 `invalid_request_error`。
- **Changed file**: `tests/engine/runners/openai/test_http_error_event.py`

### MIMO-001-未修复-[低]-测试导入 diagnostic_payload 私有常量

- **Controller decision**: rejected
- **Fix**: 未修改，按 controller adjudication 保留现状。

## Validation

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_engine_ingest_mapping.py
```

Result:

```text
67 passed in 0.55s
```

```bash
source .venv/bin/activate && pyright
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Pyright also printed an upstream version notice: `v1.1.409 -> v1.1.410`; this is not a type-check failure.

## New Risks / Open Questions

- No new blocking risk identified.
- No blocking questions.
- This fix pass did not change public dataclass fields, event type, Host production, Host state machine, EventLog schema, provider state sealed union, HTTP message text behavior, or provider request id behavior.

## Suggested Next Gate

Return to controller for Slice 2 re-review.
