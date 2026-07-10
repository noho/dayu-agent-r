# WU-SEMANTIC-OWNERSHIP-01 P3-A aggregate deepreview controller adjudication

## Gate

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A`。
- Gate：aggregate deepreview controller adjudication。
- Review base/head：`2400a04c..3649c9ea`。
- Review artifacts：
  - `docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-deepreview-ds.md`
- Decision：进入 aggregate fix gate；2 项 accepted finding 必须修复并 re-review。

## Review merge

- AgentDS：aggregate PASS，0 material finding；记录 SQL helper/read coverage residual note。
- AgentMiMo：2 项 current-scope finding，1 项 informational future-owner finding。
- Controller 不用 DS 的 PASS 抵消 MiMo 的直接代码证据；对同一 `START_BLOCKING_RUN_STATUSES` 语义的遗漏按 owner boundary 合并裁决。

## Finding adjudication

### P3-A-AGG-F01 — accepted

- Severity：Medium。
- 位置：`dayu/host/durable/state.py::_read_active_run_id`。
- 问题：`SessionSnapshot.active_run_id` 的私有读路径仍硬编码 `status IN (?, ?, ?, ?, ?)` 与五个 status params，没有消费 `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`。
- Root cause：S2 只迁移公开 active/non-terminal read helpers，遗漏了 snapshot projection 使用的私有查询。
- 影响：新增非终态状态时，公开 active run read 可自动纳入，用户可见 snapshot active run id 却可能遗漏，形成同一 durable fact 的 projection drift。
- 修复要求：私有查询直接消费 `START_BLOCKING_RUN_STATUSES` owner helper；测试证明 snapshot/private active id 与公开 active run read 对同一 session 同源，且 SQL params 由 owner set 派生。

### P3-A-AGG-F02 — accepted

- Severity：Low。
- 位置：`promote_queued_run_row`、`start_unstarted_run_row`、`resume_waiting_run_row`、`start_recovering_run_row` 的 active-run `NOT EXISTS` CAS guards。
- 问题：四条写路径各自硬编码相同五状态集合，未消费 `START_BLOCKING_RUN_STATUSES`。
- Root cause：S2 迁移了 read SQL，却把同一业务语义的 write guard 错分为另一个 owner。
- 影响：未来非终态状态扩展时，read/admission 与 write guard 会产生并发 Run 判定分歧。
- 修复要求：四条 guard 复用同一 owner-generated SQL clause/params；不得复制新的 tuple、模块常量或 compatibility wrapper。测试必须证明四条 guard 的 blocking status material 来自 owner set，并保持现有 transition/CAS 行为。

### P3-A-AGG-F03 — deferred-with-owner

- Severity：Informational。
- 问题：非 terminal EventLog 常量仍分散在 `run_transition.py` / `engine_ingest.py`。
- 裁决：deferred to P3-J / EventLog schema hardening。Approved P3-A 明确只统一 terminal lifecycle/status 语义；把非 terminal taxonomy 混入本次 aggregate fix 会扩大范围并增加无关 gate 风险。
- Owner/destination：`WU-SEMANTIC-OWNERSHIP-01 P3-J`。

## Validation baseline

- 两路 affected matrix：`323 passed`（MiMo artifact另记录扩展矩阵 332 passed）。
- pyright：0 errors。
- import cycle、terminal constant、synthetic EngineEvent、legacy mixed plan、nullable ref、command direct-cancel scans：通过。

## Required aggregate fix validation

```text
source .venv/bin/activate && pytest \
  tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_public_run_api.py \
  tests/host/test_recovery_dispatch.py \
  tests/host/test_active_cancel_dispatch.py -q
source .venv/bin/activate && pyright
git diff --check
```

- Source scan 必须确认 `_read_active_run_id` 与四个 active-run CAS guards 不再硬编码五状态 placeholders/params。
- README decision 重新检查；内部 owner helper propagation 若不改变稳定开发边界，不机械追加。
- Fix artifact 必须更新完整 Run status propagation audit 和 residual owner。

## Completion

- Accepted：2。
- Rejected-with-reason：0。
- Deferred-with-owner：1（P3-J）。
- Needs-more-evidence：0。
- Blocking open question：none。
- Next gate：P3-A aggregate fix by AgentCodex。
