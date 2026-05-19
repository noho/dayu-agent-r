# Phase 11 Slice 4 Re-Review — AgentDS — 2026-05-19

## Review Scope

- 角色：AgentDS，strict re-review specialist
- 工作区：`/Users/leo/workspace/dayu-agent-r`，分支 `feat/host-phase-11-recovery`
- 审查对象：Fix artifact `docs/reviews/phase11-slice4-fix-codex-20260519.md` 声明的 S4-F1 / S4-F2 / S4-F3 fix diff
- Controller adjudication：`docs/reviews/phase11-slice4-code-review-controller-adjudication-20260519.md`
- 原始 DS review：`docs/reviews/phase11-slice4-code-review-ds-20260519.md`
- Fix 文件：`dayu/host/admission.py`、`tests/host/test_public_cancel_session_runs.py`

## 验证结果

```bash
source .venv/bin/activate && pytest tests/host/test_public_cancel_session_runs.py \
  tests/host/test_public_cancel_smoke.py tests/host/test_public_lifecycle_smoke.py \
  tests/host/test_watch_session_events.py -q
# → 20 passed in 0.66s (fix 前 19 passed，新增 1 个 idempotency test)

source .venv/bin/activate && python -m pyright dayu/host tests/host
# → 0 errors, 0 warnings, 0 informations

git diff --check
# → clean, no output
```

## S4-F1 收口确认：cancel_session_runs unsupported error message

**原始 finding**：AgentDS M1 — `_read_supported_targets_or_raise` 错误信息未列出 RECOVERING。

**Controller 裁决**：accepted current fix，只更新错误信息，不改变状态机。

**Fix diff**（`admission.py:2059`）：
```diff
- "STARTING, active worker, and WAITING Runs in the "
+ "STARTING, active worker, WAITING, and RECOVERING Runs in the "
```

**判定**：收口。错误信息已更新，与当前 supported target 集合一致。未改变 `_session_cancel_target_for_run` 的 supported target 判定逻辑，该错误路径只在 `return None` 时触发（RECOVERING 不再返回 None）。无新增风险。

## S4-F2 收口确认：released_active_slot=True 局部注释

**原始 finding**：AgentMiMo L1 / AgentDS L1 — `_cancel_recovering` 中 `released_active_slot=True` 字段名容易被误读为释放 active worker slot。

**Controller 裁决**：accepted current fix as narrow comment/doc clarification。

**Fix diff**（`admission.py:1755`）：
```diff
+            # 这里释放的是 session active slot / queue promotion 资格，不是 active worker cancel。
             released_active_slot=True,
```

**判定**：收口。注释精确说明释放的是 session active slot / queue promotion 资格，澄清了字段名可能的歧义。注释极窄，不引入行为变更，不扩散改动范围。

## S4-F3 收口确认：cancel_run RECOVERING 幂等性测试

**原始 finding**：AgentDS L3 — 缺少 `cancel_run` RECOVERING 专用幂等性测试。

**Controller 裁决**：accepted current fix，新增 RECOVERING-specific `cancel_run` idempotency replay 测试。

**Fix diff**（`test_public_cancel_session_runs.py` 新增 `test_cancel_run_recovering_replay_is_idempotent_per_run_id`）：

测试覆盖三个断言层：
1. **同 Run 同 client_request_id 重放**：`first == replay`，`after_replay_events == after_first_events`，`CANCEL_REQUESTED` 和 `RUN_CANCELLED` 各仅 1 条。
2. **幂等 scope 不跨 run_id 漂移**：同一 `client_request_id` 用于另一个 RECOVERING Run（`peer_recovering`）时，`peer.run_id == peer_recovering.run_id`，peer 的 CANCEL_REQUESTED / RUN_CANCELLED 各 1 条。
3. **run_id 隔离**：`first.run_id == recovering.run_id`，`replay.run_id == recovering.run_id`。

**判定**：收口。测试精确验证了 RECOVERING cancel_run 的 `(run_id, client_request_id)` 幂等 scope 未漂移，且不同 run_id 之间的幂等隔离正确。测试结构与既有 fixture 一致，不引入新 helper 膨胀。

## Fix 引入新 Blocker 检查

逐项检查 fix diff 是否引入新问题：

| 检查项 | 结果 |
|--------|------|
| 错误信息更新是否改变 supported target 判定 | 否——仅改文案，不改 `_session_cancel_target_for_run` 逻辑 |
| 注释是否引入误导 | 否——"session active slot / queue promotion 资格"精确描述 promotion 语义 |
| 新测试是否使用正确 fixture | 是——复用 `_mark_run_status`、`_cancel_run_request`、`_event_types_for_run`，与既有测试一致 |
| 新测试是否创建孤立状态 | 否——与 `test_cancel_run_recovering_appends_no_attempt_terminal` 共享相同的 RECOVERING 构造路径 |
| 新测试断言是否完备 | 是——覆盖同 Run 重放、跨 Run 隔离、event count 逐条验证 |
| pyright 新增错误 | 0 |
| focused tests 回归 | 0（20 passed，含原有 19 + 新增 1） |
| git diff --check | clean |
| 是否触及禁改模块（dispatch.py / open_host.py / engine） | 否 |

## Fix 超出 scope 检查

Fix artifact 声明的改动范围为 admission.py（错误信息 + 注释）与 test_public_cancel_session_runs.py（新测试）。实际 diff 与声明一致，无 scope creep。

## 结论

**PASS** — S4-F1 / S4-F2 / S4-F3 全部收口，fix 未引入新 blocker。

- S4-F1：错误信息已更新，与当前 supported target 一致。
- S4-F2：局部注释已添加，澄清 `released_active_slot` 语义。
- S4-F3：RECOVERING cancel_run 幂等性测试已添加，覆盖同 Run 重放与跨 Run 隔离。
- 验证：20 tests passed，pyright 0 errors，git diff --check clean。
- 无 scope creep，无禁改模块触碰，无回归。
