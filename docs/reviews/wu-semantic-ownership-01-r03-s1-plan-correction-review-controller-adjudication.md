# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Plan Correction Review Controller Adjudication

## 1. Final verdict

- MiMo review：`docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-review-mimo.md`
  — **PASS**。
- DS review：`docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-review-ds.md`
  — **PASS**。
- Controller verdict：**ACCEPTED_PLAN_CORRECTION**。

两路 reviewer 均完整核对修订计划与 current code evidence，零 material finding、零 open product
question。R03-S1 仍是既有 umbrella WU 的同一 implementation slice；本裁决不创建新 WU、新
slice 或第四片。

## 2. Accepted contract

1. `dayu/host/durable/run_transition.py` 是 S1 唯一新增 production owner。
2. wait-resolution `TOOL_RESULT_ACCEPTED.attempt_id/execution_id` 精确取 suspended source
   `AttemptRow`，不得使用 resume identity、`None`、payload 或 consumer 推断。
3. `_invalid_waiting_resolution_precondition` 在 resume/terminal 任一 append/state mutation 前
   校验 `WaitRecord.execution_id == source_attempt.execution_id`；mismatch 返回
   `INVALID_STATE` 且无 partial facts/state。
4. public completed/failed/lost tests 证明正常 producer identity；direct typed transition tests
   独立证明 lower mismatch invariant。public request-atom guard 保留，但不冒充 lower proof。
5. strict request/result equality、descriptor 冷热互斥 guard、governance-only
   `TOOL_AWAITING` fixture 与 no-publication 反例全部保留。
6. exact allowlist、逐文件 coverage、full Host、pyright、ruff、diff/source scans 和 stop 条件按
   修订计划执行；不得越界到 S2/S3、Issue 177/178 或 authorization。

## 3. Reviewer note adjudication

两份 review 对核心结论一致，但其非 blocker 旁注中有一处 schema 描述不准确：

- `dayu/host/durable/schema.py` 的 `host_wait_records` 同时有
  `FOREIGN KEY(attempt_id) -> host_attempts(attempt_id)` 与
  `FOREIGN KEY(execution_id) -> host_attempts(execution_id)`；DS 所称 execution 无 FK、MiMo
  所称 FK 是否存在不确定，都不是 current schema truth。
- 修订计划本身已经正确要求先创建另一组 FK-valid auxiliary Attempt，再把目标 WaitRecord 的
  execution 指向该 auxiliary execution；因此 fixture 可执行，plan 无需修改。
- 不需要给 `ResumeRunFromWaitingInput` / `WaitingRunTerminalInput` 新增
  `suspended_execution_id`：两个 transition 已读取 source `AttemptRow`，writer 可用现有 typed
  direct parameter 消费它。若 implementation 发现必须新增输入字段，按 plan stop 返回
  Controller，不得由 `waiting.py` 复制第二份 authority。

上述纠正不产生 accepted finding，不触发 plan fix/re-review。

## 4. Next gate

只授权把 plan correction/review/controller artifacts 做 accepted local commit。取得真实 SHA 并
更新 control 后，下一 gate 才是同一 R03-S1 implementation continuation：AgentCodex 修复
durable transition producer，并完成已识别的 fixture/storage-shape/strict-execution follow-up、
全部测试与验证。不得直接进入 code review、S2、S3 或 aggregate。
