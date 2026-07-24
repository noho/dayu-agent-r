# WU-CTX-01 Goal Confirmation

## Gate

- Work Unit：`WU-CTX-01`
- 类型：GitHub Issue #20 对应的 architecture-sensitive issue / public-contract change
- gate：`goal confirmation`
- decision：`pass`
- 用户确认：2026-07-23
- next entry point：`plan`

## Preflight

- GitHub PR #182 已于 2026-07-23 合并，merge commit 为
  `5afe71fefa2486ff0e0d9b2026fee23685d48c2e`。
- 当前工作分支为 `feat/wu-ctx-01`，从上述 merge commit 起步。
- 工作树干净，不存在进行中的 merge、rebase 或 cherry-pick。
- `main` 与刷新后的 `github/main` 均为 `5afe71fe`，
  `main...github/main` ahead / behind 为 `0/0`。

## 第一性原理判断

目标成立。Host 必须在下一次完整 runner input dispatch 前做 context budget
判断；provider response 的 usage 只能在调用完成后成为历史 observation，不能替代
或回写已经完成的 dispatch decision。合法 usage 的价值是为后续完整输入提供同源
anchor；没有 usage 或 pairing 不可信时，当前 conservative estimator 仍是确定性
fallback。因此 provider 不返回 usage 不会使新算法比当前行为更差，也不得导致 Run
失败。

本 Work Unit 包含两个独立修改：

1. usage-anchored adaptive sizing：改变 Host-owned 预算预测算法，在直接同源证据成立时
   使用 `P_current = U_anchor + (E_current - E_anchor)`，否则使用当前完整输入的
   conservative estimate。
2. `CONTEXT_BUDGET_EVALUATED` canonical fact 与 Host -> Service typed context-usage
   projection：记录并公开 dispatch-relevant sizing result。该事实即使只使用
   conservative estimate 也能成立，不依赖 usage anchor。

两项修改可以复用同一个 Host-owned typed sizing result，但 plan、实现与测试必须分别
说明各自 owner、顺序、失败边界和验收信号，不能把 durable fact 当作新估算算法的附属
事件，也不能让 public projection 重算另一份结果。

## 直接代码证据

- `dayu/host/context_budget.py` 的 `estimate_context_budget(...)` 当前只实现
  conservative estimator，按文本、canonical JSON、message overhead 与 tool schema
  overhead 估算。
- `dayu/host/engine_ingest.py` 的 `_estimate_usage_observation_input(...)` 当前从
  `USER_INPUT_ACCEPTED.display_text` 重建估算；这不是完整 runner input 的同源证据，
  不能作为新 anchor contract。
- `RUNNER_CALL_INPUT_ASSEMBLED`、完整 input projection 与
  `RUNNER_CALL_INPUT_ITERATION_LINKED` 已提供 manifest / iteration lineage 基础，
  但现有 manifest contract 尚未冻结 estimator identity / version、`E_anchor` 与
  usage observation 的直接配对语义；该缺口属于 WU-CTX-01 的目标实现范围。
- `USAGE_REPORTED` 已 durable 保存 iteration-scoped `prompt_tokens` 等内部 signal；
  `supports_stream_usage` 只决定请求是否发送 `stream_options.include_usage=true`，
  不是 usage availability predicate。
- 当前 production code 不存在 `CONTEXT_BUDGET_EVALUATED`；Host activity allowlist、
  `HostActivityView` 与 Service `EntrypointActivity` 也没有 typed context-usage
  projection。

## Issue 与控制文档裁决

GitHub Issue #20 当前 title / body 已与 `docs/host/design.md` §25 对齐，并明确：
provider live evidence 不是 WU-CTX-01 的前置条件；usage 缺失时使用 conservative
fallback。控制文档中“七个 provider family 的真实流式调用缺一即阻塞”是过期条件，
与设计真源、Issue 当前 scope 和用户确认冲突，裁决为
`rejected-with-reason`。本 gate 不执行七家凭据依赖的阻塞式 probe；provider-neutral
正确性由 usage-present / usage-absent contract tests、实际合法 `USAGE_REPORTED`
presence 和 fallback 不变量验证。

## 目标与成功信号

- compatible ordinary anchor 使用 signed-delta 公式，覆盖正负 delta。
- usage 缺失、非法、歧义、manifest mismatch 或 lineage gap 时，当前候选完整输入的
  结果严格等于既有 conservative estimator，Run 不失败。
- provider / model / context window / estimator contract / serialization semantics
  不兼容以及 accepted compact 均使旧 anchor 失效。
- proactive compact、hard decision、post-compact / dispatch-fallback sizing 与
  diagnostics 消费同一个 Host-owned typed sizing result。
- `CONTEXT_BUDGET_EVALUATED` 先于其驱动的 compact 或 dispatch lifecycle fact，
  replay / recovery 不产生互相矛盾的重复 truth。
- Host 拥有 predicted tokens、ratio-derived thresholds、basis points 与 pressure
  level；Service 只做 typed 透传，UI 不读取 raw EventLog / usage payload 重算。

## 非目标

- provider tokenizer、provider/model sizing adapter、远程 token-count endpoint、
  tokenizer 下载或 provider-name branch。
- 跨 provider correction model、动态 ratio 学习或 billing-grade 精度。
- Engine 反向依赖 Host，或把 Host governance 搬入 Engine。
- 用 metadata / extra payload、时间戳、provider request id 或 display text 推断
  pairing。
- 具体 CLI / Web / WeChat 进度条、颜色、文案、小数位或历史图表。

## Blocking Open Questions

None。

## Completion

用户已确认目标、边界、成功信号与上述过期条件裁决。`goal confirmation` gate
通过；下一未完成 gate 为 `plan`，由 AgentCodex 产出 code-generation-ready plan。
