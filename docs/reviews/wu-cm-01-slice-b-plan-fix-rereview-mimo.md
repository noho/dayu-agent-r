# WU-CM-01 Slice B Plan Fix Re-Review (MiMo)

日期：2026-06-04

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice B plan fix re-review |
| design source | `docs/host/design.md` 第 24 / 25 章 |
| control doc | `docs/host/issues-implementation-control.md` |
| accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-b-implementation-codex.md` |
| controller blocker adjudication | `docs/reviews/wu-cm-01-slice-b-blocker-controller-adjudication.md` |
| plan fix artifact | `docs/reviews/wu-cm-01-slice-b-plan-fix-codex.md` |
| reviewer | AgentMiMo |
| review scope | plan fix / control / artifact 修正，不审当前未接受的 partial implementation code diff |

## Review Focus Areas

用户指定 5 个重点检查区域：

1. 将 `engine_ingest.py` 加入 Slice B 是否必要且 scope 足够窄。
2. proactive subsequent run input / memory projection / RunInputBuilder consumption 是否正确归还 Slice C/D。
3. 测试边界是否还能验证 operation/event/proactive/reactive closeout。
4. 是否仍禁止旧 payload compatibility fields、projection shim、old candidate adapter、lazy import、extra payload、untyped event payload。
5. 是否有新的 pyright-clean slice 风险。

## Assumptions Tested

1. Plan fix 对 `engine_ingest.py` scope 限制是否足够具体，不会让 implementation agent 越界扩大修改。
2. Plan fix 是否明确处理了 proactive subsequent run input 测试的归属问题。
3. Plan fix 是否保持了旧路径删除边界的一致性。
4. Plan fix 是否在 control doc 中正确追踪了修正。

## Findings

### 01-未修复-低-engine_ingest.py 非 closeout 函数的旧类型残留边界未显式约束

- **位置**: Plan fix artifact "修改内容" 第 2 条、Slice B 实现边界 `engine_ingest.py` 条目
- **问题类型**: 契约缺失
- **当前写法**: Plan fix 声明 `engine_ingest.py` 不得修改"其它状态机、projection catch-up、RunInputBuilder 调用或旧 payload 兼容路径"，但未明确说明 `engine_ingest.py` 中非 closeout 函数仍保留旧 `CompactionCandidate` / `CompactQualityCheckResult` 类型引用时，是否允许更新这些 import / type annotation 为 vNext 类型。
- **反例/失败场景**: Implementation agent 修改 `_append_reactive_compacted_event` 签名和 `build_context_compacted_payload` 调用后，同一模块其它函数仍持有旧类型 import。Pyright 可能报告旧 import unused 或类型不一致；agent 可能被迫扩大修改范围来消除这些错误，从而越界。
- **为什么有问题**: `engine_ingest.py` 是一个大型模块，旧 `CompactionCandidate` 等类型在非 reactive closeout 路径也有使用。若 plan 不明确"旧 import 可保留到后续 slice 清理"或"只允许替换 reactive closeout 路径的类型引用"，implementation agent 面对 pyright 报错时无法安全决策。
- **直接证据**: Blocker artifact 列出 `engine_ingest.py:66-75` 导入 `CompactQualityCheckResult`、`CompactionCandidate`、`ContextCompactor`，且 `engine_ingest.py:1696-1705` `_append_reactive_compacted_event` 签名要求旧类型。
- **影响**: Implementation agent 可能在 pyright 压力下扩大 `engine_ingest.py` 修改范围，或被迫添加 lazy import / type: ignore 来绕过。
- **建议改法和验证点**: 在 Slice B 实现边界中补充："`engine_ingest.py` 内非 reactive closeout 路径的旧类型 import / annotation 在本 slice 可原样保留；pyright 若报 unused import 或类型不一致，允许在本 slice 内仅删除 reactive closeout 路径已不再使用的旧 import，但不得修改非 closeout 函数的类型签名或实现。"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低 — 该风险可通过 implementation agent 保守处理，但显式约束能减少歧义。

### 02-未修复-中-proactive subsequent run input 测试归属未在 plan fix 中显式处理

- **位置**: Plan fix artifact "修改内容"、Slice B 退出信号
- **问题类型**: 测试缺口
- **当前写法**: Plan fix 声明"proactive closeout 只验证 operation 编排、accepted / failed event payload、artifact descriptor 与 fallback 行为；不得要求 accepted compacted event 已被 subsequent RunInputBuilder 消费"和"subsequent run input、memory projection、durable snapshot materialization、post-compact delta 和 RunInputBuilder 对 vNext payload 的消费断言属于 Slice C / D"。但未明确 `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 测试在 Slice B 应如何处理。
- **反例/失败场景**: Implementation agent 完成 Slice B 所有其它退出信号后，该测试仍失败。agent 可能被迫在 Slice B 中添加旧 payload compatibility fields 来让测试通过，或者跳过该测试但无法证明 proactive closeout 正确。两种路径都违反 plan 约束。
- **为什么有问题**: Blocker artifact 已明确指出该测试失败的 root cause 是"memory projection / RunInputBuilder 仍按旧 compacted payload 字段读取"，属于 Slice C/D 范围。Plan fix 接受了这一判断，但未在修正后的 Slice B 中显式说明该测试应跳过、移动到 Slice C/D 测试集、或在 Slice B 中调整断言范围。
- **直接证据**: Blocker artifact 列出 `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 的失败原因为 `ValueError: evidence_backed_fact_candidates is required`，来自 compacted 后的后续 run input/projection 消费路径仍按旧 payload 字段读取。
- **影响**: Implementation agent 在 Slice B 验收时面对该失败测试无法安全决策，可能绕过约束。
- **建议改法和验证点**: 在 Slice B 实现边界或退出信号中显式补充："`test_multi_turn_proactive_compact_feeds_subsequent_run_input` 测试的断言要求 memory projection / RunInputBuilder 消费 vNext compacted payload，不属于 Slice B；Slice B implementation gate 应将该测试标记为 Slice C/D 待迁移，或在 Slice B 中将该测试的断言范围缩减为仅验证 proactive operation / event closeout，不验证 subsequent run input 消费。"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中 — 若不显式处理，implementation agent 面对明确的测试失败时无法安全完成 Slice B 验收。

## Focus Area Verdicts

### Focus 1: engine_ingest.py 加入 Slice B 是否必要且 scope 足够窄

**结论：必要且 scope 基本足够窄。**

直接证据支持将 `engine_ingest.py` 加入 Slice B：reactive accepted compaction closeout 的生产代码在 `engine_ingest.py:1666-1766`，包括 `_append_reactive_compacted_event` 调用、`CompactArtifactStore.write_compact_artifact` 写入和 `build_context_compacted_payload` 调用。Blocker artifact 的 `TypeError: CompactArtifactWriteRequest.accepted_candidate must be CompactionCandidate` 是直接 failure evidence。

Plan fix 对 scope 的限制基本足够：不得修改"其它状态机、projection catch-up、RunInputBuilder 调用或旧 payload 兼容路径"。Finding 01 指出的非 closeout 函数旧类型残留边界是一个低严重度的契约缺口，可通过补充说明消除。

### Focus 2: proactive subsequent run input / memory projection / RunInputBuilder consumption 是否正确归还 Slice C/D

**结论：正确归还。**

Plan fix 显式声明："subsequent run input、memory projection、durable snapshot materialization、post-compact delta 和 RunInputBuilder 对 vNext payload 的消费断言属于 Slice C / D"和"Slice B 不得通过旧 payload compatibility fields、projection shim、old candidate adapter、额外 payload 字段或旧 compacted payload 字段让 Slice C / D 断言提前通过"。这与设计真源第 24.4 章的 projection 规则和第 25.1 章的 compact event 响应路径一致。

Finding 02 指出该归还未在测试层面显式落地，是一个中等严重度的测试缺口。

### Focus 3: 测试边界是否还能验证 operation/event/proactive/reactive closeout

**结论：基本可以，但有一个测试归属缺口。**

Plan fix 更新了 Slice B 退出信号："proactive accepted / failed closeout 与 reactive accepted / failed / fallback closeout 都能形成 vNext event / artifact / state transition 闭环；测试断言停在 operation/event closeout，不断言 subsequent run input 已消费 compacted view"。这正确界定了验证边界。

但 `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 测试当前断言范围超出 Slice B 边界，plan fix 未显式处理该测试的归属（Finding 02）。其余 reactive 测试（`test_reactive_overflow_recovers_and_dispatches_new_attempt` 等）的 failure root cause 在 `engine_ingest.py`，plan fix 已通过允许修改该文件解决。

### Focus 4: 是否仍禁止旧 payload compatibility fields、projection shim、old candidate adapter、lazy import、extra payload、untyped event payload

**结论：全部保持禁止。**

Plan fix 显式重申："不得通过旧 payload compatibility fields、projection shim、old candidate adapter、额外 payload 字段或旧 compacted payload 字段让 Slice C / D 断言提前通过"和"禁止兼容 wrapper / re-export / lazy import / extra payload / untyped event payload 的约束未放松"。这与原 Slice B plan 和 controller blocker adjudication 一致。

### Focus 5: 是否有新的 pyright-clean slice 风险

**结论：存在可控风险。**

`engine_ingest.py` 加入 Slice B 后，implementation agent 需要修改该模块的 reactive closeout 路径的类型签名和 import。该模块同时持有旧类型引用（Finding 01）。若 pyright 报告旧 import unused 或类型不一致，agent 需要在"保守保留旧 import"和"清理但扩大修改范围"之间决策。Plan fix 未显式约束这一边界，但风险可控——通过补充说明即可消除。

## Open Questions

无。所有用户指定的 focus area 均有直接证据支撑的裁决。

## Residual Risks

| ID | 来源 | 类型 | 状态 | Owner / Destination | 下一步 |
|---|---|---|---|---|---|
| RR-1 | Plan fix re-review Finding 01 | engine_ingest.py 非 closeout 旧类型残留边界 | open | Slice B implementation gate | implementation agent 在 Slice B 实现时保守处理旧 import；若 pyright 压力过大，停止并回 plan gate |
| RR-2 | Plan fix re-review Finding 02 | proactive subsequent run input 测试归属 | open | Slice B implementation gate | 在 Slice B 中将该测试标记为 Slice C/D 待迁移或缩减断言范围 |
| RR-3 | Plan fix artifact | Slice C 仍负责 vNext compact event 到 memory durable/projection 的 materialization | deferred-with-owner | Slice C | 无需当前处理 |
| RR-4 | Plan fix artifact | Slice D 仍负责 RunInputBuilder / subsequent run input / fallback prompt assembly 的 vNext 消费闭环 | deferred-with-owner | Slice D | 无需当前处理 |
| RR-5 | Plan fix artifact | 若 engine_ingest.py reactive closeout 需要修改超出 event / artifact closeout 的状态机或 public contract | open | Slice B implementation gate | 停止实现并回到 design / plan gate |

## Conclusion

**Verdict: pass-with-risks**

Plan fix 正确解决了 controller blocker adjudication 指出的两个核心问题：

1. `engine_ingest.py` 加入 Slice B allowed files，scope 限制为 reactive accepted compaction event / artifact closeout。
2. Proactive subsequent run input / memory projection / RunInputBuilder consumption 正确归还 Slice C/D。

Plan fix 保持了所有旧路径禁止约束不变。两个 non-blocking findings（engine_ingest.py 非 closeout 旧类型残留边界、proactive subsequent run input 测试归属）属于 implementation gate 可处理的低/中风险，不阻塞 plan 接受。

建议 controller 接受 plan fix，并在 implementation gate 中显式处理 Finding 01 和 Finding 02 的具体落地。
