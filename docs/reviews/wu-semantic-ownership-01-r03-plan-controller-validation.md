# WU-SEMANTIC-OWNERSHIP-01 / R03 Plan Controller Validation

## 1. Gate 与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- internal remediation sub-WU：`R03` / accepted call 与 evidence LLM projection。
- validated artifact：`docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`。
- plan evidence base：`444bb33eaebba5f56d3cd211ced90e3b9d67a4fc`。
- verdict：**READY_FOR_DUAL_PLAN_REVIEW**。这是同一 umbrella WU 的内部 remediation gate，不是新 WU，也不授权 implementation。

Controller 已完整读取计划的 1177 行并对照 controller discussion、Host/Engine/Tool/Fins/UI design truth、umbrella accepted plan、R01 completion §11 handoff 与当前代码证据。Topic 3/4 owner 决策没有被重解释，当前代码也没有提供与权威裁决直接矛盾的证据。

## 2. 独立验证

- 计划固定为三个 slices：S1 shared request atom，S2 blacklist repair 删除与 LLM source owner audit，S3 opaque refs internal-only propagation；没有第四片或替代 work unit。
- ordinary/awaiting 的 old-to-new durable flow、`TOOL_AWAITING` 删除字段、request link/digest corruption matrix、四个 LLM-facing consumer 与 explicit citation/source-unavailable contract均有符号级计划。
- 37 个 `dayu/config/prompts/**` asset 全部逐文件列出；constructor scan 当前返回 114 个 executable Python paths，逐路径与计划 inventory 集合比较无遗漏。
- R01 completion §11 的 30 个 data rows 在计划 §9 逐行消费；Doc navigation/output semantics 保留，Issue 177 没有被偷带。
- 当前 `json_redaction` 仅由 awaiting payload 和 Tool Trace 两个 R03 下游 repair 路径使用；计划分别在 S1/S2 删除调用和模块，同时明确不删除 Web egress、path containment、DNS/peer、resource budget、atomic write 等既有安全 owner。
- Engine message/schema serialization、prompt assets和多数 tool schema 均有 no-diff evidence；只计划修正 `fetch_more`、Web `url` 与 Fins common ids 的 source-owner self-description。
- `git diff --check` 与新 artifact whitespace check 无输出；工作区只有计划与本 validation/control artifacts，没有 production、tests、README 或 design truth 改动。

## 3. Review 必须重点挑战

双路 reviewer 应独立验证，而不是沿用本 verdict：

1. shared writer 是否能在现有 transaction append API 中取得真实 event sequence 并安全写入 `TOOL_AWAITING` link；是否遗漏 cold descriptor、idempotent replay 或 same-transaction failure atomicity。
2. Host 机械读取 `result.value.citation` 是否确为当前 accepted outcome public contract，且不会变成 speculative `BusinessSource` 或 Fins reverse dependency。
3. 删除 `json_redaction` 是否只消除本 WU 已裁决的下游 repair，不会误删其它 owner 的安全防御。
4. Memory/Compact/Tool Trace 的 strict material/fail-closed 计划是否覆盖所有真实 producer/consumer，且不以 fallback 或 display-only 修补掩盖 durable corruption。
5. real Doc/Web/Fins public-run smoke 是否在当前真实入口可执行、不会要求 deferred Issue 177/178、不会使用 fake provider或手工 wait result。
6. 1177 行计划是否存在 allowlist 过宽、测试成本失衡、无必要新抽象、遗漏 current source owner 或 LLM-facing 文本不自足。

## 4. Handoff

下一 gate 是 AgentMiMo 与 AgentDS 对同一 immutable plan target 的并发 adversarial plan review。两路 review 均须使用 `/planreview`，输出独立 artifact；Controller 随后逐项裁决。任何 accepted finding 必须交回 AgentCodex 修改计划并完成双路 re-review，计划接受前不得 implementation、commit 或 push。
