# Interactive Conversation Memory closure F08–F10：Plan fix

## Gate identity

- **Gate**: Gateflow plan-fix。
- **Work unit**: Interactive Conversation Memory closure F08–F10。
- **Timestamp**: `20260804-155026`（本机系统时钟）。
- **Fixed target**: `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`。
- **Input reviews**:
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-review-mimo.md`
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-review-ds.md`
- **Controller decision**: 用户本轮十一个裁决点为最终 scope/contract 决定。
- **Artifact path**: `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-fix-codex.md`。
- **Write scope**: 只修订 target plan 并新增本 artifact；未修改实现、frozen baseline 或 frozen evidence。

## First-principles judgment

Plan fix 动机成立。两路 review 发现的主要问题不是生产根因判断错误，而是原 plan 在 checkpoint 边界、F08 LLM-facing 判断规则、F10 oversized/raw retention、digest 生命周期与 defensive failure closure 上欠规格；这些空白会迫使 implementation agent 重新设计，或把修复落到错误 owner。

直接代码证据支持本次收敛方向：

- `dayu/host/compaction_operation.py` 的 manifest recorder 已生成 canonical descriptor，hot JSON 已 inline manifest body并携带 ref/digest，但 EventLog row descriptor 仍写 `None`。
- `dayu/host/compact_material.py::select_compact_segment` 当前逐 block 做 budget，且首项在特定条件下可越过 size cap；`_sorted_material_blocks` 与 `_block_exclusion_reason` 已提供稳定顺序和既有 reason precedence。
- `dayu/host/compact_pipeline.py::build_tier_recovery_request_plans` 的 tier 1–3 selection 只消费 frozen snapshot；`build_fallback_decision_input` 之后仍从完整 `source_snapshot.material_blocks` 构造 recent-window fallback 输入。
- `dayu/host/dispatch.py::_execute_proactive_compaction` 当前无条件传递 `next_repair_feedback`；operation 异常若逃逸会绕开该函数内既有单一 failed terminal/fallback 收口。
- `docs/cli_init_workspace_manifest_v1.json` 冻结 package prompt bytes；`tests/cli/test_smoke_cli_init_provider_matrix.py::FROZEN_MANIFEST_SHA256` 是该 manifest raw bytes 的 authoritative assertion consumer。

因此最小正确路径是：在语义 owner 增加自足规则/严格 typed contract，在现有 selector、operation 与 fallback 边界闭环；不增加自然语言 heuristic、oversized 专用 signal、新 public schema、下游补偿或兼容层。

## Review findings adjudication and fixes

| 来源 | Finding / 决定 | 裁决 | Plan fix |
|---|---|---|---|
| DS F1 / MiMo F1 | frozen baseline checkpoint 缺失且原 plan 明确排除 | accepted | §1、§10 改为单一独立 accepted-plan checkpoint：精确包含三份 frozen baseline、plan、MiMo/DS reviews、plan fix、后续 re-review/controller adjudication；implementation 后三个 baseline digest 永不改变。删除相反提交表述。 |
| DS F2 | F08 prompt 自足性不足 | accepted with controller refinement | §5.4、F08 slice 与测试矩阵改成无阈值业务判断维度：完整、可独立理解的业务陈述覆盖实际相关的当前目标、结论/进展、后续关键约束/下一步；cap 内无法形成至少一条完整陈述时必须 `null`；禁止占位符、孤立字符/标点和截断片段。 |
| MiMo F4 | 用 Host negative test 固化句点可接受 | rejected | 明确禁止 Host 自然语言 heuristic，也禁止新增“句点/占位符可接受”的 negative acceptance test；real-provider 遵从性保留给后续 Agent-in-the-loop scenario。 |
| DS F6 / controller F08 consumer | config README 证据与 prompt publication digest | accepted | F08 allowed files 新增 publication manifest 与其 raw-digest owner test；明确只更新目标 prompt asset SHA 和 `FROZEN_MANIFEST_SHA256`。已读取 `dayu/config/README.md` 开篇职责，判定其不拥有 prompt 内容且无需更新。focused validation 新增 init manifest test、JSON tool 与 SHA-256 核对。 |
| MiMo F2 | F09 hot payload 描述歧义 | accepted | §4.2/F09 明确 hot JSON inline manifest body并携带 ref/digest，EventLog row descriptor 改为同一 ref/digest；resolver/projector 不变。 |
| MiMo F5 | F09/F10 共享文件 sequencing | accepted in part | 固定先 F09、后 F10，F10 从已接受 F09 checkpoint 继续；拒绝 rebase 建议，不执行 rebase。 |
| DS F3 | oversized group fallback 未闭环 | finding accepted, proposed signal rejected | §5.2、F10 B/C、tests 明确不增加 special signal。完整 group 放不下时全组 `budget_limit`，selection 为空或保留已选 prefix，随后 eligible units 同样 budget-limited；完整 raw group 留在 frozen canonical snapshot并进入既有 tier 4/5 raw-window/fail-closed owner。新增 selector、pipeline raw-retention、fallback terminal owner tests。 |
| DS F5 | selector two-pass 欠规格 | accepted | 明确阶段一稳定归并 units并计算 collective exclusion，阶段二仅对 eligible units做 prefix budget；reason precedence 固定为 current-input → protected recent floor → already-represented → previous-compacted-view → not-in-segment；item count按真实 blocks。 |
| DS F7 | group typed surface 不明确 | accepted | 选择 `TurnGroupMembership` + root/transient selection scope 两个最小严格类型，作为 `CompactSegmentSelection` 的直接不可分割字段；不建 public schema、root-proof facade、builder hierarchy或 God helper。 |
| DS F4 / MiMo F3 | digest 变化与历史 durable fact | accepted | 明确全新当前 schema、无旧库兼容；新 typed fields自然改变新 request digest；fixture从 production owner helper生成。历史 EventLog digest保持产生时 immutable，不由新代码重算；运行时只绑定当前 frozen schedule/request。 |
| DS F8 | mismatch 只在 operation 抛错会使 Run 崩溃 | accepted | dispatcher 正常按双 digest 清空；operation mismatch在 provider 前返回 existing non-repairable failed result，无 next feedback、无异常逃逸；dispatcher 停止 schedule并走既有单一 failed terminal/fallback。补 operation 与 scheduler defensive tests。 |
| Controller validation | 验证命令与明确不跑场景不足 | accepted | 补全 full `pytest -q`、Ruff、compileall、JSON tool、全仓 pyright、逐 production 文件 coverage ≥80%、diff/status/baseline digest；列出五条明确不运行的正式 CLI scenarios。 |

## Assumptions tested

| Assumption | Result |
|---|---|
| F08 必须由 Host 判定自然语言意义 | 证伪。Host 只拥有 shape/cap/coverage；prompt 是选择规则 owner。 |
| 修改 prompt 只需改 prompt 文件 | 证伪。publication manifest 与其 raw digest assertion 是 authoritative downstream consumers。 |
| oversized group 需要新增专用 signal 才能进入 fallback | 证伪。frozen source snapshot 已完整保留 raw blocks，既有 fallback owner直接消费该 snapshot。 |
| group 可以算一个 item以保持原子性 | 证伪。这会静默扩大 item cap；必须按真实 block 数计数。 |
| feedback mismatch 抛 contract exception即可 fail closed | 证伪。异常可逃逸 scheduler并绕过既有 terminal收口；operation必须返回 failed result。 |
| 新代码需要重算历史 EventLog digest保证一致 | 证伪。历史 digest 是当时产生的 immutable fact；只对当前 request做 binding。 |
| F09/F10 共享文件需要 rebase | 证伪。固定顺序 checkpoint 足以隔离语义 owner，且 controller 明确禁止 rebase。 |

## Planreview lenses self-check

- **Architecture boundary**: F08 规则在 prompt owner，publication digest在 manifest owner；F09 在 recorder append boundary；F10 在 selector/dispatcher/operation owner。无 Memory/renderer/CLI/Engine 下游补偿或反向依赖。
- **Best practice**: strict typed membership、two-phase deterministic selection、immutable request binding、single-terminal fail-closed 与 owner-level tests均有明确 contract。
- **Optimal solution**: 复用既有 source snapshot、fallback decision与terminal permit；未引入新 oversized protocol或自然语言 validator。
- **Overengineering**: 拒绝 special signal、public schema、兼容 shim、God helper、额外 terminal branch与 Host semantic heuristic。
- **Overcoupling**: F08/F09/F10 仍为独立 slices；F09/F10 的共享文件通过固定顺序处理，不把两个语义合为 mixed implementation commit。

自检未发现新的 material finding。该结论只表示 plan-fix 内容已覆盖裁决，不替代下一 Gateflow plan re-review/controller adjudication。

## Validation

- 读取并交叉核对 target plan、MiMo/DS 两份 review、frozen finding、`dayu/config/README.md`、`tests/README.md`、`dayu/host/README.md` 与直接生产代码。
- 本机时钟 timestamp：`20260804-155026`。
- plan-fix 前三份 baseline SHA-256：
  - `docs/cli_ci_oracles.json`: `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
  - `docs/cli_ci_scenarios.json`: `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
  - `docs/reviews/wu-interactive-memory-closure-f08-f10.md`: `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`
- 未运行 Python tests/pyright/coverage：本 gate 只修改 Markdown plan artifacts，不修改实现；实施验证命令已完整写入 plan。

## Docs decision

- 本 gate 仅允许并实际修改 plan/review artifacts。
- `dayu/config/README.md` 不更新：它不拥有单个 prompt 的业务文案。
- implementation 后 `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md` 是否/如何更新，已按各自职责写入 plan；不得在代码落地前写成现状。

## Residual risks and classification

| Risk | Classification | Owner / destination |
|---|---|---|
| F08 prompt 仍可能被真实 provider违反 | covered by later approved evidence stage | 五条正式 CLI scenarios 中的 `interactive.g06.summary-null`；本 work unit 明确不运行。 |
| oversized group 可能使 compactor更早耗尽并进入 fallback | fixed contract, validation pending implementation | F10 raw-retention/terminal owner tests及后续 `interactive.g06.turn-group-atomicity`。 |
| typed fields改变新 request/selection digest | fixed in plan; implementation verification pending | owner helper fixtures、全 pytest、历史 EventLog immutable-fact tests。 |
| F09 real provider/model/response identity尚未由正式场景证明 | covered by later approved evidence stage | `interactive.g06.tool-trace-formal`。 |

没有未分类 residual risk，没有 blocking open question。

## Open questions

无。两路 review 的 open questions 已由 controller 裁决或在修订 plan 中以 owner contract 收敛；下一 gate 不需要 implementation agent 自行决定 schema、ownership、fallback 或测试接受边界。

## Final planreview conclusion

`pass`。修订 plan 已覆盖全部 accepted findings 和 controller decisions；未发现新的 material plan finding。该结论是 plan-fix 内部 adversarial self-check，Gateflow 的独立 plan re-review/controller adjudication 仍是进入 implementation 前的必经 gate。

## Completion status

- **Plan-fix status**: complete。
- **Planreview self-check conclusion**: `pass`，但不替代独立 re-review。
- **Next Gateflow entry point**: plan re-review；随后 controller adjudication，通过后创建单一 accepted-plan checkpoint。
