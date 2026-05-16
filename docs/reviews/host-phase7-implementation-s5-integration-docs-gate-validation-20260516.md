# Host Phase 7 P7-S5 Implementation - Integration, Docs, Gate Validation

## 状态

P7-S5 implementation / docs / validation 准备已完成。未修改设计真源 `docs/host/design.md`，未修改总控文档 `docs/host/implementation-control.md`，未提交 commit、未 push、未开 PR。

## 改动

- 补齐 `tests/host/test_phase7_waiting_integration.py`：新增本地 awaiting tool 经真实 ToolRuntime accept path 进入 `WAITING` / `SUSPENDED`，再通过 public `resolve_wait(source=manual)` 恢复 Run，并验证 resume RunInputBuilder 重建 accepted wait/tool fact 的集成测试。
- 更新 `dayu/host/README.md`：同步当前已实现的 WAITING cancel、`resolve_wait` request shape、late diagnostic、poller 最小契约与 Engine awaiting / suspended diagnostic boundary。

## 测试覆盖判断

- manual resolve 集成：由本次新增 `test_local_awaiting_tool_manual_resolve_resumes_run` 覆盖本地 awaiting tool -> Host wait record -> `WAITING` -> manual `resolve_wait` -> resumed Run。
- poll resolve 集成：已有 `tests/host/test_wait_adapter_polling.py::test_poll_adapter_ready_result_resolves_wait` 覆盖 poll adapter ready -> `resolve_wait` -> wait resolved；`test_cancelled_poll_wait_is_abandoned_without_resolve` 覆盖 cancelled wait abandon。
- `tests/README.md` 未更新：本次没有新增测试层级或命令约定，现有 Host 测试说明已经包含 Phase 7 waiting / poll / late diagnostic 覆盖。

## 验证

- `source .venv/bin/activate && pytest tests/host -q`：389 passed。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：通过。

## 残余风险

- P7-S5 不实现 callback endpoint、callback auth / replay、防后台 poll loop、recovery scan、remote wait 恢复或外部 job physical cancel / revoke。
- Engine 公共事件当前不携带 Host accepted wait refs；P7 只能把 `TOOL_AWAITING` / `RUN_SUSPENDED` 作为 diagnostic confirmation，不能做强 matching-ref 校验。
