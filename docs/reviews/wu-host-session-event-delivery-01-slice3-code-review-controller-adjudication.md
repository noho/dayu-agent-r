# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Code Review Controller Adjudication

## Gate 与输入

- Gate：`code-review-slice-3`
- Accepted base：`b33bb80b`
- AgentMiMo：`docs/reviews/wu-host-session-event-delivery-01-slice3-implementation-mimo.md`
- AgentDS：`docs/reviews/wu-host-session-event-delivery-01-slice3-code-review-codex.md`
- Implementation evidence：`docs/reviews/wu-host-session-event-delivery-01-slice3-implementation-codex.md`
- Controller-owned `docs/host/issues-implementation-control.md` 已从实现 review scope 排除。

两路 review 独立并行完成。AgentMiMo verdict=`PASS`；AgentDS 报告 1 个 material correctness finding 与 1 个 maintainability finding。finding 按代码证据逐项裁决，不按多数票处理。

## 逐项裁决

### S3-CR-F01 `_fail_recovering_run` 丢失 exact terminal notice

- 来源：AgentDS Finding 1
- 严重度：material / correctness
- 裁决：`accepted-current-fix`
- 直接证据：`dayu/host/engine_ingest.py::_fail_recovering_run` 的 `StateMutationStatus.UPDATED` 分支返回 `terminal_closeout=True`，但硬编码 `terminal_notice=None`。同一函数刚完成 `fail_recovering_run_in_transaction(...)`，其结果包含 same-transaction exact `run_event`；两个上游 caller 都直接传播该缺失值。
- Plan 对照：accepted manifest 明确包含 `EngineEventIngestor._fail_recovering_run -> fail_recovering_run_in_transaction`；该 `RECOVERING -> FAILED` 首次 terminal 释放 active slot，flag 必须为 `wake_queue_promotion=True`。
- 反例：recovery start/compaction 后收口失败时 durable terminal 已提交，但 `_finish_ingest` 因 notice 为 `None` 不通知 opener-local coordinator；本地 watcher 只能等待 periodic durable reconciliation，且 queued B 的低延迟 promotion barrier没有被该 producer履行。
- 修复要求：只从该 transaction result 构造 exact notice，flag=`True`；补 owner-level producer test与完整 `_finish_ingest -> port` runtime propagation evidence，禁止 post-commit latest/max/readback。

AgentMiMo 的 PASS 不覆盖此直接代码缺口；该 finding 阻塞 accepted Slice 3 commit。

### S3-CR-F02 四份 transition-result-to-notice helper 重复

- 来源：AgentDS Finding 2
- 严重度：maintainability / hard project constraint
- 裁决：`accepted-current-fix`
- 直接证据：`admission.py`、`engine_ingest.py`、`recovery.py`、`dispatch.py` 各自定义 `_terminal_notice_from_transition`，重复执行 `run_event is not None` 与 stable Run/Event identity校验，且参数名、错误消息和校验分支已经漂移。
- Owner 裁决：same-transaction `RunTransitionResult.run_event` 到 immutable local notice 的投影应由单一 shared projection helper拥有；当前正确 owner 放在 `dayu.host.durable.run_transition`，由各 producer直接复用。该 helper 可依赖 Host-private `TerminalPostCommitNotice`，不得 public package export或反向进入 Engine。
- 约束对照：根 `AGENTS.md` 明确要求重复逻辑必须抽取；这不是可推迟 residual。
- 修复要求：抽取单一 typed helper并统一参数名/校验/docstring；删除四份本地实现，更新必要 owner/static tests，保持 static producer manifest、flag与 post-commit调用时点不变。

## 非 findings 与保持项

- coordinator watermark/dedupe、closing barrier、低基数日志、scheduler construction failure、Host close order、三条真实 A→B barrier、dual opener isolation、同页 multi-terminal、local-only边界、coverage、pyright与README audit均有充分证据；当前不要求其它实现变化。
- README 实际更新仍属于 accepted Slice 4，不在本 fix 中扩大范围。
- 不接受兼容 wrapper、optional/default port、runtime rebind或新的 session-id-only handoff。

## Decision

`fix-required`

下一 gate：`code-review-fix-slice-3`。只由 AgentCodex 修复 `S3-CR-F01` 与 `S3-CR-F02`；修复完成后必须由 AgentMiMo、AgentDS 原 reviewers 并行执行 `$deepreview` re-review，分别确认两项关闭且无新 material finding。
