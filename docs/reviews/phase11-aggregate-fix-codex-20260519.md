# Phase 11 Aggregate Fix - Codex - 2026-05-19

## 动机判断

P11-AGG-F1 动机成立。RECOVERING cancel 的行为本身正确，但 Run row CAS SQL 位于 `dayu.host.durable.run_transition`，与 `start_recovering_run_row(...)`、`terminal_recovering_run_row(...)` 等同类 Run row mutation owner 不一致。将其下沉到 `dayu.host.durable.state` 可以让 transition 层只负责编排 EventLog 与 durable state helper，降低后续 CAS 条件漂移风险。

P11-AGG-F2 动机成立。默认 stale threshold 与 heartbeat 周期的安全关系是 positive orphan proof 的局部前提；补充窄注释可以防止后续调参误把 heartbeat 周期调到接近或超过 stale threshold。

## 改动

- 在 `dayu/host/durable/state.py` 新增 `cancel_recovering_run_row(...)`，保留原 RECOVERING cancel 的 UPDATE 条件与 mutation 结果分类：命中时 `UPDATED`，row 不存在时 `NOT_FOUND`，row 存在但 CAS 未命中时 `CAS_LOST`。
- `dayu/host/durable/run_transition.py` 改为 import/use `cancel_recovering_run_row(...)`，删除本模块内的私有 SQL helper 和直接 `TABLE_HOST_RUNS` 依赖。
- 在 `dayu/host/recovery.py` 默认 stale threshold 常量旁增加中文注释，说明 heartbeat 周期必须显著小于 stale threshold，避免破坏 positive orphan proof。
- 未修改 Engine、public API、schema；未提交、未 push、未进入 re-review gate。

## 验证

```bash
source .venv/bin/activate && pytest tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py tests/host/test_public_cancel_session_runs.py -q
```

结果：50 passed。

```bash
source .venv/bin/activate && pytest tests/host -q
```

结果：793 passed, 1 skipped。

```bash
source .venv/bin/activate && pytest tests/runtime -q
```

结果：107 passed。

```bash
source .venv/bin/activate && python -m pyright dayu/host dayu/runtime tests/host tests/runtime
```

结果：0 errors, 0 warnings, 0 informations。

```bash
git diff --check
```

结果：通过，无输出。

## 风险与未覆盖项

- 本次仅移动 RECOVERING cancel Run-row CAS owner 并补注释，不改变 recovery policy、dispatch heartbeat、public cancel 语义或 durable schema。
- 未新增测试；既有 focused tests 已覆盖 RECOVERING cancel、startup recovery scan 与 public cancel session/run 行为。
- README 未修改：本次没有接口、命令、架构边界或稳定开发手册内容变化，且当前 fix scope 仅允许指定 host 文件与 review artifact。

FIX_COMPLETE
