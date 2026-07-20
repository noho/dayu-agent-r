# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Plan Correction Artifact

## 1. Gate 与结论

- Work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`。
- Slice：既有 `R03-S1 — ordinary/awaiting shared request atom + durable replay identity`。
- Gate：plan correction；不是新 WU、新 slice、第四个 slice 或 implementation continuation。
- Controller 输入：`docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-controller-adjudication.md`。
- follow-up 输入：Controller plan validation 指出 public corrupt path 无法到达 lower transition invariant。
- 结论：**PLAN_CORRECTION FOLLOW-UP READY FOR MIMO/DS DUAL REVIEW**。
- 本 gate 只修改 accepted plan 并新增本 artifact；没有修改 control、production、tests、README、design truth 或 prior artifacts。
- 当前未提交 R03-S1 implementation diff 作为受保护输入完整保留；本 gate 没有删除、回滚、覆盖或继续实现。
- commit/push：未执行，也不授权执行。

## 2. 第一性原理、root cause 与 owner

修订动机成立，且严重性没有被高估。Controller 在 strict accepted-result execution equality 落地后执行真实 `resolve_wait` producer path，9 文件矩阵出现 3 个同源失败；直接源码证据是 `dayu/host/durable/run_transition.py::_waiting_tool_result_event_request` 把 fresh `TOOL_RESULT_ACCEPTED.execution_id` 硬编码为 `None`，而其 envelope 链接的 canonical request row 持有 suspended source Attempt 的真实 durable execution id。

这不是 consumer 过严、fixture 过旧或 `waiting.py` 需要 seam。result fact 属于发起 await 的 source Attempt；因而其 execution identity 的唯一 owner 是已读取 suspended `AttemptRow` 并直接写 EventLog fact 的 durable transition。同一 transition 已读取 `WaitRecordRow`，所以必须在任何 append/state mutation 前证明 `wait_record.execution_id == source_attempt.execution_id`。正确修复边界是 writer 及其写前不变量，不是下游 `None` 放行、fallback、loose fixture 或 resume identity 替代。

Controller follow-up 的测试路径 finding 同样成立。`DefaultHostResolveWaitService` 在调用 resume/terminal durable transition 前，先为 typed input 求值 `_tool_result_resolution_payload`；该 helper 通过 `_wait_tool_call_requested_event` 校验 `TOOL_AWAITING` 和 `TOOL_CALL_REQUESTED` 的 execution 都与 `WaitRecord.execution_id` 一致。因此腐化 WaitRecord 后调用 public `resolve_wait` 会先抛 `HostDurableError`，既不会调用 `_invalid_waiting_resolution_precondition`，也不会获得 transition `INVALID_STATE`。上游 request-atom guard 是正确且必须保留的第一层证据，但它不能代替 direct lower-transition owner test。

## 3. 计划纠正清单

| 纠正项 | accepted plan 的最终约束 |
| --- | --- |
| production owner allowlist | 在 R03-S1 加入 `dayu/host/durable/run_transition.py`；这是唯一新增 production owner |
| result execution identity | resume 与 terminal 两个 union 分支的 `TOOL_RESULT_ACCEPTED.attempt_id/execution_id` 精确取 suspended source `AttemptRow`；不取 resume Attempt、`None`、payload 或下游推断值 |
| transition precondition | `_invalid_waiting_resolution_precondition` 校验 `WaitRecord.execution_id == source Attempt.execution_id`；mismatch 在任何 result/resume/terminal append 或 state mutation 前返回 `INVALID_STATE` |
| writer symbol | `_waiting_tool_result_event_request` 以 typed 直接参数消费已校验 source Attempt，resume/terminal 共用该 writer，不新建 facade/seam |
| 最小 owner test | 只选现有 `tests/host/test_resolve_wait_command.py`；不新增测试文件，不修改其他 transition test |
| resume union proof | 在现有 completed 测试断言 result 使用 seeded source attempt/execution，并与新 resume Attempt execution 分离 |
| terminal union proof | 在现有 failed/lost 测试分别断言 result 使用各自 suspended source attempt/execution，且无 resume Attempt/dispatch |
| mismatch no-partial-facts | 同文件以 completed/failed 参数化覆盖 resume/terminal；正常 seed waiting 后把 WaitRecord 指向另一个 FK-valid Attempt execution，直接调用 `resume_run_from_waiting_in_transaction` / `fail_run_from_waiting_in_transaction`，断言 `INVALID_STATE` 且 EventLog/Run/Attempt/Wait/dispatch 全表 snapshot 不变 |
| public corrupt path | 现有 request-atom corruption tests 保留上游 `HostDurableError` + no mutation，但不计作 lower transition invariant coverage；public resolve tests 只证正常 resume/failed/lost producer identity |
| 保留 contract | 保留 request/result execution strict equality、descriptor arguments/query 冷热互斥 guards、governance-only `TOOL_AWAITING` exact-key fixture 及 no-publication 反例 |
| validation/coverage | S1 9 文件矩阵、full Host、pyright、ruff；`run_transition.py >=80%`，由 `test_resolve_wait_command.py` 加现有 no-diff transition regression 执行逐文件 coverage |
| stop | 任何需要 `None`、resume identity、payload 推断、consumer equality 放宽、计划外 path 或无法写前 fail closed 的方案都停止回 Controller |

## 4. 完整修订计划的位置

| plan section | 修订内容 |
| --- | --- |
| §0 | 改为既有 R03-S1 plan correction gate，记录 accepted plan commit、受保护 dirty worktree、本 gate 两个 writable artifact 与 dual-review 路由 |
| §1–§4 | 补齐 durable transition owner、source Attempt execution identity、WaitRecord/source Attempt 同源不变量和 no-partial-facts corruption contract |
| §6.1–§6.3 | 同步 S1 目标、production/test allowlist 和符号级改动；保留 Controller 已接受的四个 strict-consumer test path |
| §6.4 | 固定最小 owner-level test file：public tests 证正常 resume/failed/lost identity，direct typed transition tests 证 resume/terminal mismatch `INVALID_STATE` 与全表 no-partial-facts；明确上游 request-atom guard 不代替 lower proof |
| §6.5–§6.6 | 同步 9 文件/full Host/pyright/ruff/coverage 验证，增加 `run_transition.py` 逐文件覆盖目标与 implementation continuation stop |
| §13.3–§13.4 | 增加 aggregate coverage row，明确纠正后 S1 implementation allowlist 与本 artifact-only gate 的更窄 writable scope |
| §16–§17 | 增加 source execution/mismatch stop 与 plan gate self-check；明确不扩展 S2/S3、Issue #177/#178 或 authorization |

## 5. 本 gate 验证

本 gate 只修文档，没有运行 implementation tests、coverage 或 pyright；这些命令已在计划中同步为 Controller 接受后的同一 R03-S1 implementation continuation gate。本 gate 执行的 artifact-only 检查结果如下：

- `git diff --check` 与 plan-specific `git diff --check -- docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`：均 exit `0`，通过。
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-codex.md`：exit `1` 是 no-index 对新文件检出 diff 的预期状态；命令无 whitespace-error 输出，通过。
- writable-path scan 精确为 `M docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` 与 `?? docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-codex.md`；`dayu/host/durable/run_transition.py` 仍为 clean/no-diff。
- correction 前已存在的 22 个受保护 dirty/untracked path（production、tests、README、control 和 3 个 prior Controller/implementation artifacts）SHA-256 全部与本 gate 取证值一致，无删除、回滚、覆盖或继续实现。
- plan scope scan 确认必需项均有显式命中：`run_transition.py`、两个 transition symbols、`WaitRecord.execution_id == source_attempt.execution_id`、public 正常 resume/failed/lost identity、direct resume/terminal typed inputs、`INVALID_STATE`、全表 mismatch no-partial-facts、public upstream guard 不代替 lower proof、唯一 owner test file、strict equality、descriptor 互斥 guard 与 governance-only fixture。
- follow-up stale-expectation scan 确认已删除“腐化 WaitRecord 后由 public API 获得 transition `INVALID_STATE`/`HostApiError`”的正向测试要求；相关文本只保留“该 public path 会先以 `HostDurableError` 失败，不能代替 lower proof”的 boundary 说明。
- diff-hunk scope scan 只命中 plan §0–§6、§13、§16–§17；没有改写 S2/S3 实施段、Issue #177/#178 或 authorization contract，只在 boundary/stop 文本中明确禁止越界。
- `git rev-parse --short HEAD` 仍为 gate 前的 `244bfdae`；本 gate 未创建 commit。

## 6. 后续 gate 与 residual risk

下一 gate 只是 AgentMiMo / AgentDS 对完整修订计划的双路 review，再由 Controller 裁决。Controller 接受前，当前 implementation diff 必须继续原样保留，不得进入 code review、implementation continuation、S2、S3 或 aggregate。

当前没有未裁决的产品语义；唯一 residual 是修订计划尚未经双路 review/Controller 接受，因此本 artifact 不构成实现授权。
