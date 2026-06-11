# WU-PROJ-01 PR Review Re-review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review re-review controller adjudication
- 日期: 2026-06-11
- PR: `https://github.com/noho/dayu-agent-r/pull/136`
- Controller: AgentController

## 输入

- Fix artifact: `docs/reviews/wu-proj-01-pr-review-fix-codex.md`
- AgentMiMo re-review: `docs/reviews/wu-proj-01-pr-review-rereview-mimo.md`
- AgentDS re-review: `docs/reviews/wu-proj-01-pr-review-rereview-ds.md`
- PR review controller adjudication: `docs/reviews/wu-proj-01-pr-review-controller-adjudication.md`

## 裁决结论

`PASS`。PR-F1 / PR-F2 均已关闭；不需要再次 fix；进入 accepted PR review commit。

## 关闭项

| Finding | 关闭证据 |
|---|---|
| PR-F1 | 3 个旧 dispatch scheduler 测试已按 WU-PROJ-01 fail-closed 新设计迁移；两路 re-review 均确认不再走旧 retry dispatch、不创建 worker、不进入 `RECOVERING`、Run / Attempt / dispatch record 正确 fail-closed。 |
| PR-F2 | PR body 已更新为完整受影响 Host 测试文件集合 `185 passed`、pyright `0 errors`、`git diff --check` passed；历史 `-k` 结果已标注为 focused review context。 |

## Controller 复验

- `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_logging.py tests/host/test_open_host_runtime.py`
  - `185 passed in 2.20s`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - pass

## Residual Risk

本 re-review 不改变以下 deferred risk：

- `WU-PROJ-01-S3-R1`: dispatch before-worker catch-up happy path 独立集成测试，deferred to Host dispatch test hardening。
- `WU-PROJ-01-S4-R1`: dispatch scheduler lane timeout flaky，deferred to Host dispatch scheduler test hardening。
