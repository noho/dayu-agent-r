# WU-TOOLS-01-F01-02 Plan Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | plan review controller adjudication |
| plan artifact | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| review artifacts | `docs/reviews/wu-tools-01-f01-02-plan-review-mimo.md`; `docs/reviews/wu-tools-01-f01-02-plan-review-ds.md` |
| date | 2026-06-08 |

## Controller Decision

Plan review gate 未通过，进入 fix gate。

理由：两路 review 都确认 plan 的 root cause 判断基于直接代码证据，scope 与设计真源基本对齐；但 AgentDS 提出的两个文本级 blocking finding 会影响 implementation agent 对 Slice 1 的执行边界理解，必须先修 plan artifact，再进入 re-review。

## Findings Adjudication

| Finding | 来源 | 裁决 | 原因 | Fix / Owner |
|---|---|---|---|---|
| F-DS-1 direct Fins callable 返回 `ToolCancelledOutcome` 的类型合法性需显式写入 plan | AgentDS Finding 1 | accepted | `ToolExecutionOutcome` 已包含 cancelled outcome，但 plan 的 Slice 1 需要自足说明，避免 implementation agent 误判为 contract change。 | 当前 fix gate；AgentCodex 修改 plan artifact。 |
| F-DS-2 `_start_lock` 与 create/checkpoint/submit 时序需显式约束 | AgentDS Finding 2 | accepted | 当前 plan 的 invariant 要求 create 与 submit 间取消不得 submit 后台 job；若 plan 不写二次 checkpoint 或锁内 submit 决策，implementation agent 可能留下 race。 | 当前 fix gate；AgentCodex 修改 plan artifact。 |
| F-DS-3 Doc `list_files` 非递归 checkpoint 粒度 | AgentDS Finding 3 | deferred-with-owner | 这是实现粒度和性能说明，不阻塞 plan；可在 implementation report 记录递归/非递归 checkpoint 裁决。 | implementation agent。 |
| F-DS-4 Fins read 瞬时方法与循环方法 checkpoint 密度标准 | AgentDS Finding 4 | accepted | 该标准应补入 plan，能降低 implementation 歧义，但不需要重新设计。 | 当前 fix gate；AgentCodex 可一并补充。 |
| F-DS-5 `search_public_web` provider fallback 循环 checkpoint 位置 | AgentDS Finding 5 | accepted | Plan 已有 invariant，但 fix 可明确写在 provider fallback loop 每次迭代开头、provider attempt 前检查 token。 | 当前 fix gate；AgentCodex 可一并补充。 |
| F-DS-6 legacy adapter cancelled-as-failed LLM 可见性 | AgentDS Finding 6 | accepted | 不改变 adapter contract；implementation 应确保 message / hint 自解释。 | implementation agent。 |
| F-DS-7 audit matrix 声明级与行为级覆盖不平衡 | AgentDS Finding 7 | accepted | 作为测试策略说明即可，不阻塞 plan。 | implementation report 记录。 |
| F-MIMO-01 `read_section` 的 `**_kwargs` 是否可移除需证据 | AgentMiMo F-01 | needs-more-evidence | 不阻塞 plan；implementation 先 grep 调用方再裁决，不为旧测试保留兼容 wrapper。 | implementation agent。 |
| F-MIMO-02 `search_public_web` 调用方范围审计 | AgentMiMo F-02 | deferred-with-owner | 新增 keyword-only 默认参数应兼容，但 implementation 必须审计调用方范围。 | implementation agent。 |
| F-MIMO-03 Doc/Fins read cancelled 异常类名 | AgentMiMo F-03 | needs-more-evidence | 不阻塞 plan；implementation 先复用 Web `tool_cancelled` 业务错误模式的直接证据。 | implementation agent。 |
| F-MIMO-04 Fins start 后 cancel 应直接返回 cancelled outcome | AgentMiMo F-04 | accepted | 与 F-DS-1 同源，纳入当前 fix。 | 当前 fix gate；AgentCodex 修改 plan artifact。 |
| F-MIMO-05 start 后 checkpoint 使用同步 `is_cancelled()` | AgentMiMo F-05 | accepted | 与 F-DS-2 相关；plan fix 应明确同步 checkpoint，不引入 async cancel helper。 | 当前 fix gate；AgentCodex 修改 plan artifact。 |
| F-MIMO-06 R1 mitigation 覆盖范围需在 implementation report 记录 | AgentMiMo F-06 | accepted | 不阻塞 plan；implementation closeout 记录。 | implementation agent。 |
| F-MIMO-07 Fins read 9 个工具的声明级覆盖 | AgentMiMo F-07 | accepted | 测试策略有效；行为测试按风险类覆盖，声明级覆盖所有工具。 | implementation agent。 |
| F-MIMO-08 source-level guard test 原则 | AgentMiMo F-08 | accepted | Plan 已有原则，不阻塞。 | implementation agent。 |

## Required Plan Fix

AgentCodex 必须只修改 `docs/host/wu-tools-01-f01-02-cancellation-plan.md`，至少补齐：

- Slice 1 明确：direct Fins awaiting callable 的返回类型 `ToolExecutionOutcome` 已合法包含 `ToolCancelledOutcome`，不需要修改 callable 协议或 Host / Engine contract。
- Slice 1 明确 create/checkpoint/submit 时序：在 durable job create 后、后台 submit 前必须做同步 token checkpoint；若 checkpoint 命中 cancel，调用 `runtime.request_cancel(job_id)` 并不得 submit 后台 job。实现可以扩展 `_start_lock` 范围覆盖 create/checkpoint/submit 决策，或在锁释放后、submit 前做二次同步 checkpoint；无论方案如何，都必须满足 invariant。
- Slice 4 明确 checkpoint 密度裁决：瞬时读方法入口 checkpoint 足够；含搜索、XBRL、processor、目录/文件循环或大结果组装的方法需要循环内或高风险边界 checkpoint。
- Slice 2 明确 `search_public_web` provider fallback loop 在每次 provider attempt 前检查 token，取消后不得尝试后续 fallback provider。

## Residual Risks

| ID | 状态 | Owner / Destination | 下一步 |
|---|---|---|---|
| R1 | deferred-with-owner | WU-WAIT-03 或独立 Host awaiting activation design WU | 两阶段启动需先设计 Host awaiting accepted activation contract，不在当前 WU 实现。 |
| R2 | accepted limitation | 当前 WU implementation report | 同步 requests / filesystem / processor 调用只能 checkpoint，不能物理抢占。 |
| R3 | deferred-with-owner | 后续 tool adapter contract WU | legacy adapter 若要统一 cancelled outcome，需要独立 contract 设计。 |

## Gate Result

进入 fix gate。Plan fix 完成后必须派发两路 re-review，重点确认上述 required plan fix 是否完整落入 plan artifact。
