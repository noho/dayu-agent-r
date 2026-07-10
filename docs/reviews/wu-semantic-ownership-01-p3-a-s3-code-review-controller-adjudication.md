# WU-SEMANTIC-OWNERSHIP-01 P3-A S3 code review controller adjudication

## Gate

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A / S3`。
- Gate：code review controller adjudication。
- Review artifacts：
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s3-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-s3-code-review-ds.md`
- Decision：进入 fix gate；4 项 accepted finding 必须全部修复并 re-review。

## Finding adjudication

### S3-CR-F01 — accepted

- 来源：AgentDS F1。
- 问题：`_execute_reactive_compaction` 仍用 `AttemptRow.terminal_event_id` 代理 Attempt terminal status。
- 裁决：accepted。P3-A 的 owner boundary 已明确 lifecycle truth 是 durable status，terminal refs 只负责 row consistency。即使正常 row shape 下行为等价，该分支仍在重建状态语义。
- 修复要求：改用 `is_terminal_attempt_status(latest.attempt.status)`；测试必须直接证明 reactive compaction 分支消费 status truth，并保持 public reactive path 回归通过。

### S3-CR-F02 — accepted

- 来源：AgentDS F2。
- 问题：`_TerminalPlan` 同时包含 Engine-origin 与 Host-lifecycle-origin 互斥 optional 字段。
- 裁决：accepted，不接受 reviewer 的 deferred 建议。Approved S3 plan 明确禁止一个 dataclass 混装互斥 Engine / Host optional payload；当前 `_HostLifecycleCloseoutCandidate.plan: _TerminalPlan` 仍让 type system 无法阻止跨来源字段污染。
- 修复要求：拆成明确的 Engine terminal plan 与 Host lifecycle terminal plan，或等价 discriminated union；两条 candidate / closeout path 的类型必须在编译期分离。不得引入 compatibility wrapper、optional probing 或更大的 god-bag。

### S3-CR-F03 — accepted

- 来源：AgentDS F3。
- 问题：`_validate_host_lifecycle_context` 未显式校验 `run.run_id == envelope.run_id`，与 Engine-origin ingress guard 不一致。
- 裁决：accepted，严重性 LOW。`read_run_by_id` 正常实现已隐含该不变量，但 ingress identity guard 应自足表达完整 identity contract，避免测试 double、未来 repository 实现或代码阅读产生不一致语义。
- 修复要求：补齐显式检查，并复用/补充 identity validation 测试；不要为此抽取无实际复杂度收益的兼容 seam。

### S3-CR-F04 — accepted

- 来源：AgentDS adversarial check 2 residual note，controller 升格为 finding。
- 问题：Engine 与 Host lifecycle closeout 都在调用 `terminal_closeout_in_transaction` 前写 payload descriptor；若 terminal CAS 以非 `UPDATED` 状态返回而不抛异常，当前 write transaction 可提交孤儿 payload descriptor。
- 裁决：accepted。低概率不改变 durable storage ownership；payload descriptor 的产生与 canonical terminal fact 必须原子同成败，不能把 cleanup 交给后续 maintenance。
- 修复要求：基于 transaction runner / payload repository 的直接语义选择最小方案，确保 non-UPDATED closeout 不提交 payload descriptor，同时保留 accepted/duplicate/rejected result contract。不得用下游清理、展示过滤或兼容读取掩盖。必须增加 adversarial CAS-lost/invalid-state 测试，证明无 orphan payload/event/status mutation。

### MiMo Observation 1 — rejected-with-reason

- Host lifecycle 在 `WAITING/SUSPENDED` 下允许 worker EOF/crash closeout 是正确设计；waiting confirmation exception 只属于真实 Engine waiting event。可选 docstring 不构成 finding。

### MiMo Observation 2 — rejected-with-reason

- `CANCELLED` dispatch record 返回不可 direct-cancel 是正确且已覆盖的状态机行为，不是缺陷。

### MiMo Observation 3 — rejected-with-reason

- 测试硬编码 `host_lifecycle_ref` 完整格式是对稳定治理来源 contract 的防御性断言，不是脆弱测试异味。

## Additional controller notes

- AgentDS 关于 partial worker-accepted fields 的文字说明存在反向表述：当前 helper 要求三个字段全部为 `None` 才返回 direct-cancelable，因此任一 partial fact 都会 fail closed；durable row validation 另负责拒绝非法组合。该文字不形成 finding。
- 两路均确认 synthetic EngineEvent 已移除、active-cancel decision table 正确、Host/Engine identity namespace disjoint、pyright 与 required tests 通过。

## Required validation after fix

```text
source .venv/bin/activate && pytest \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_active_cancel_dispatch.py \
  tests/host/test_recovery_dispatch.py \
  tests/host/test_public_cancel_session_runs.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_state_schema.py -q
source .venv/bin/activate && pyright
git diff --check
```

- 重跑 synthetic EngineEvent、terminal-ref routing、direct-cancel duplicate predicate、terminal event constant scans。
- README 决策重新检查；若只做内部类型/原子性修复且稳定边界文本不变，不机械修改 README。
- fix artifact 必须更新 propagation audit 与 residual risk 分类。

## Completion

- Accepted：4。
- Rejected-with-reason：3。
- Deferred：0。
- Needs-more-evidence：0。
- Blocking open question：none。
- Next gate：P3-A S3 fix by AgentCodex。
