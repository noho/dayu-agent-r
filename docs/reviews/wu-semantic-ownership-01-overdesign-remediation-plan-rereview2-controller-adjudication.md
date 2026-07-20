# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Plan Second Re-Review Controller Adjudication

## Gate 身份

- 本文是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` remediation 总计划的第二轮双路完整 re-review 最终裁决，不是新 WU、R01 plan 或 implementation。
- 唯一产品裁决真源仍是 `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`；finding disposition 只由初轮 controller adjudication、第一轮 re-review controller adjudication 与本文组成的顺序链决定。
- 本轮证据：
  - `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview2-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview2-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-fix-codex.md`
  - 最终全文 `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`

## Closure 裁决

Controller 接受两路共同证据：

1. DS-RR-F01 四点均已真实关闭；§7.3 是唯一规范位置。
2. Umbrella 的 12 个 sub-WU、30 个 slice、production allowlist、测试/coverage/scan/README/smoke、安全矩阵与 aggregate gates 均未被删除或弱化。
3. Accepted-plan commit 前由 umbrella 拥有 mandatory current-evidence baseline；commit 后由 accepted sub-WU plan 独占 exact slice/file/command/test-node/scan execution truth。Umbrella 继续拥有边界、顺序、全局 invariant、accepted contract 和验证下限。
4. Owner、依赖、production allowlist 或 accepted contract 的实质变化必须 stop 并回 controller。
5. DS-RR-F02/F03、MIMO-RR-F01/F02/F03 均未被误实现。
6. 初轮 CTL-PF-01—05、DS-PF-01—12、MIMO-PF-01—15 的 closure 全部保持。
7. Topic 8/9 与 Issue 142/151/175/177/178 边界零漂移。

因此，DS-RR-F01 最终状态为“已修复”；没有未关闭的旧 accepted finding。

## AgentDS 第二轮新 findings

### DS-RR2-F01 — rejected-with-reason — 低

**Finding**：`mandatory starting baseline` 在 §7.5 本地仍可能被误读为 exact 命令必须逐字使用。

**裁决理由**：§7.5 同一句已经写明“later accepted sub-WU plan 必须逐项映射并核实，只有其 accepted-plan commit 后的 exact 项才支配该 sub-WU implementation”，并显式引用 §7.3 唯一时序规则。Reviewer 所建议的本地澄清已存在；再次复制只会增加以后漂移的第二份措辞。

### DS-RR2-F02 — rejected-with-reason — 低

**Finding**：Baseline 映射的“逐项”粒度未固定为每个 pytest/coverage/scan/README 项。

**裁决理由**：Mapping 的业务目的是真实证明每个 baseline 语义义务未被静默遗漏，而不是规定 Markdown 行数或命令拆合格式。Sub-WU plan 可能基于真实 test collection 合并/拆分命令；把 umbrella 语法单元固定成持久 contract 会制造无业务价值的格式 owner。双 plan review 按 baseline 义务和直接证据验证完整性即可。

### DS-RR2-F03 — rejected-with-reason — 低

**Finding**：R01→R03 的 LLM-facing handoff 未固定 Markdown 表格和独立节名。

**裁决理由**：§8.5 已规定必须逐文件覆盖 tool name/description/参数/枚举/错误、prompt fixture 与其它 LLM-facing 文本，并记录 source owner、删除/保留/改写和 final disposition；§7.3/§24 已规定 completion/handoff artifact。该 finding 与已拒绝的 MIMO-RR-F01“固定 inventory 表格模板”语义重复。格式由 R01 accepted plan 在不减少字段的前提下决定，不由 umbrella 再建第二模板 owner。

## AgentMiMo 第二轮新 findings

### MIMO-RR2-F01 — rejected-with-reason — 低

**Finding**：§26 可进一步把“本 gate”改写成“本 re-review-fix gate”。

**裁决理由**：§0 已把当前 gate 标为 `remediation plan re-review fix complete`；§26 同一句又明确“本 gate 不进入第二轮 re-review；下一动作只能由 umbrella controller 另行派发第二轮双路 re-review”。时序没有歧义，且第二轮现已按该规则完成。Accepted plan 保留 review 时点的 stop 记录，当前 gate 由 control doc 独占；不为历史状态做无语义收益的再修改。

### MIMO-RR2-F02 — rejected-with-reason — 低

**Finding**：§7.4 可补充 CI workflow 文件不属于 production/config/package 闭集。

**裁决理由**：§7.4 首句已经把表限定为 production/config/package 闭集；§18.1 明确若需要 Windows workflow，R11 子计划必须把精确文件加入自己的 closed allowlist并经双 plan review/controller 接受，umbrella 不预设文件名。两处组合已给出唯一扩域路径，无缺口。

### MIMO-RR2-F03 — note / no fix

`{mimo,ds}` 已被 plan 明确解释为两份 artifact。Reviewer 也认定无需修改，保持 note。

## Final Gate Decision

- 第二轮两路 verdict 均为 `PASS`；Controller 对最终全文的复核一致。
- 本轮没有 controller-accepted 新 finding，无 fix gate、无第三轮 re-review。
- Umbrella remediation 总计划达到 accepted-plan criteria。Controller 可以创建 accepted-plan local commit。
- 该 accepted commit 不授权跳过任何 R01—R12 自己的独立 plan/review/fix/re-review/accepted-plan-commit 流程。
- Accepted-plan commit 后的下一 entry point 是 R01 internal remediation sub-WU plan gate；不是 implementation。

## Final Finding Status

| Finding group | Final status |
| --- | --- |
| 初轮 CTL/DS/MiMo accepted findings | 全部已修复 |
| 第一轮 DS-RR-F01 | 已修复并经两路完整 re-review 通过 |
| 第一轮 rejected/note findings | 关闭，未实施 |
| DS-RR2-F01/F02/F03 | rejected-with-reason，关闭 |
| MIMO-RR2-F01/F02 | rejected-with-reason，关闭 |
| MIMO-RR2-F03 | note / no fix，关闭 |

Blocking user question：无。
