# WU-RUNTIME-01 Slice 2 Implementation Artifact

## Changed Files

- `tests/host/test_audit_sink.py`
- `tests/host/test_tool_trace_projection.py`
- `docs/reviews/wu-runtime-01-implementation-slice2-codex-20260601.md`

未修改 `dayu/host/audit.py`、`dayu/host/tool_trace.py` 或其它 Host production source。

## Worktree Note

- Slice 2 implementation 的实际 changed files 只有 `tests/host/test_audit_sink.py`、`tests/host/test_tool_trace_projection.py` 和本 artifact。
- 当前工作区另有 pre-existing user changes：`AGENTS.md`、`CLAUDE.md`。
- Slice 2 implementation agent 未修改、未 stage、未 revert `AGENTS.md` 或 `CLAUDE.md`；它们不属于 Slice 2 changed files。

## Implemented Items

- `LogAuditSink` 现有 JSONL 字段回归用例改为使用 explicit `lock_path`，并继续断言 JSONL line 成功追加、sink marker 写入、projection checkpoint 推进到已扫描事件、lock marker 文件存在。
- `ToolTraceProjectionConsumer` 现有 hot / cold 投影回归用例改为使用 explicit `lock_path`，并继续断言 hot row 写入、cold JSONL line 追加、projection checkpoint 推进到结果事件、lock marker 文件存在。
- 测试没有导入第三方 `filelock`，没有读取 token 状态，没有 mock runtime internals。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q`
  - Result: pass, `13 passed in 0.33s`
- `source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q`
  - Result: pass, `36 passed in 0.74s`
- `source .venv/bin/activate && pyright`
  - Result: pass, `0 errors, 0 warnings, 0 informations`

## README Decision

- `tests/README.md`: checked and not updated.
- Reason: existing filelock testing description only covers current stable test facts such as parent directory policy、context manager release、release idempotency、non-blocking timeout wrapping and import boundary. It does not mention removed `released` / `_active_token` semantics, and Slice 2 only strengthens existing Host regression coverage without adding a new test layer or changing test commands.

## Residual Risks

- No new residual risk introduced in Slice 2.
- Existing accepted residual risk remains: lock marker file is not Host durable truth; this slice only verifies runtime marker restoration on the production call path.

## Stop Conditions

- Stop conditions hit: none.
- Host tests did not require production changes to `dayu/host/audit.py` or `dayu/host/tool_trace.py`.
