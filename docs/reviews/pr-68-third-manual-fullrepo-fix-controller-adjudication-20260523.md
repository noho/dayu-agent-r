# PR 68 第三轮手工全仓 Review 修复总控裁决

## 结论

Verdict：PASS。

本轮用户提供的两份全仓 review artifact 为：

- `docs/reviews/repo-review-20260523-215141.md`
- `docs/reviews/repo-review-20260523-215152.md`

总控裁决后接受 5 项当前 PR 必须修复的问题：

- `_DurableRunCancellationToken` 在 durable read retry exhausted 时不能 fail-open。
- `run_compaction_operation` 在 retry attempt 之间必须检查 Host lifecycle cancellation token。
- compaction proposal 异常 diagnostic refs 不能绕过脱敏路径。
- Engine exception diagnostic 不能因普通 `token` / `header` 词汇过度脱敏，但必须继续保护真实 secret 值。
- `dayu/contracts/cancellation.py` 与 `dayu/__init__.py` 的文档边界必须反映当前分层。

其它 findings 均裁决为后续 production hardening、cleanup 或非本轮阻断项，已映射到 `docs/host/implementation-control.md` 追踪区。

## 修复证据

Implementation artifact：

- `docs/reviews/pr-68-third-manual-fullrepo-fix-codex-20260523.md`

关键修复：

- `dayu/host/dispatch.py`：durable cancellation token 在 `HostTransactionRetryExhaustedError` 时返回 `durable_unavailable`，`is_cancelled()` 因而 fail-closed。
- `dayu/host/compaction_operation.py`：每次 compaction attempt 前检查 `cancellation_token.is_cancelled()`；已取消时返回 `failure_reason="cancellation_requested"`，并记录 rejected attempt。
- `dayu/host/compaction_operation.py`：`_exception_diagnostic_suffix()` 复用 `_safe_exception_message()`，避免 provider exception 明文 secret 进入 diagnostic refs。
- `dayu/engine/agent.py`：删除宽泛 marker 脱敏，改为 Bearer / API key / secret assignment value pattern；普通 `JWT token has expired` 与 `Content-Type header is invalid` 保持诊断可见。
- `dayu/contracts/cancellation.py`、`dayu/__init__.py`：修正分层和当前包概览文档。

## 复审证据

Re-review artifacts：

- `docs/reviews/pr-68-third-manual-fullrepo-fix-rereview-mimo-20260523.md`：PASS。
- `docs/reviews/pr-68-third-manual-fullrepo-fix-rereview-ds-20260523.md`：PASS。

两份复审均确认 5 项 accepted fix 覆盖真实 root cause，无 blocking findings。

## 验证

Controller validation：

- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py tests/engine/test_agent_phase2.py tests/host/test_dispatch_scheduler.py -q`：103 passed。
- `source .venv/bin/activate && pyright dayu tests`：0 errors。
- `git diff --check`：passed。

AgentDS re-review 也独立重复运行了同一组 affected tests 与 pyright，结果通过。

## 残余风险与 owner

以下不阻塞 PR 68 draft-PR-pass，均已转交后续 owner：

- SSE fatal tool call partial completion、context overflow error-body read failure、Engine import boundary 白名单：Engine runner / provider hardening。
- `ActiveWorkerRegistry` asyncio 同步语义、dispatch / recovery production hardening：Phase 15 或独立 hardening PR。
- SQLite stale read / durable transaction busy policy / CAS direct tests：durable production hardening。
- ConfigLoader inheritance depth、runtime lane indefinite wait、redaction helper taxonomy：Phase 15 Retention / Purge / Production Hardening。
- truncation cursor cap 与 duplicate governance attempt scope：ToolRuntime hardening。
- LLM compaction proposal parse cast、fact-candidate partial failure semantics：Conversation Memory / Compaction hardening。
