# WU-CM-01 Slice C Plan Fix Re-review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C plan fix/reslice re-review adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| plan fix artifact | `docs/reviews/wu-cm-01-slice-c-plan-fix-codex.md` |
| review artifacts | `docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-mimo.md`; `docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-ds.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`pass-with-accepted-followup`。

AgentMiMo 与 AgentDS 均裁决 `pass-with-findings`，且均无 blocking finding。Controller 接受两路复审对核心动机的判断：Slice C blocker 的根因是旧 `ConversationMemorySnapshot` / `MemoryProjectionPolicy` direct consumer graph 已跨 Host prompt / dispatch、Service assembly、Runtime config 与多份测试；若不把这些 consumer 纳入同一个 pyright-clean closure，只能依赖旧字段 alias、compat wrapper 或旧 snapshot bridge，违反项目 no-compat 与 pyright 硬约束。

扩大 Slice C 为 memory contract / durable projection / compact material / RunInputBuilder / dispatch / service assembly / runtime config 的 vertical slice 是当前设计真源和代码事实下的最小可维护闭环。范围变大是已知风险，但不是过度设计；review gate 后仍会按 implementation、code review、fix、re-review 执行。

## Finding Adjudication

| finding | 来源 | 裁决 | 理由 | 后续动作 |
|---|---|---|---|---|
| `CompactMaterialPack` 字段迁移映射未显式指定，`CompactMaterialBlockKind` 旧枚举到 vNext section 的映射不完整 | MiMo 01 | accepted | `dayu/host/compaction.py` 仍有 `stable_input`、`history_input`、`evidence_input`，Slice C 会修改 compact material contract；计划必须避免 implementation agent 自行推断字段重命名。 | 派发 AgentCodex 做 plan follow-up，补充字段重命名和旧 block kind 全量迁移表。 |
| config JSON 文件迁移未显式覆盖 | MiMo 02 | accepted | 设计真源第 3 章明确 `execution_profiles.json.memory_projection_policy` 的 vNext 字段集；当前仓库实际配置真源是 `dayu/config/execution_profiles.json`，测试 fixtures 也含旧字段。计划必须说明 packaged config 与测试 fixture 同步迁移，旧字段 fail fast。 | 派发 AgentCodex 做 plan follow-up，补充 `dayu/config/execution_profiles.json` 与 fixture 更新边界。 |
| vNext config JSON 字段名未给出完整 inventory | DS NF-1 | accepted | 设计真源第 3 章已列出字段名；计划应直接引用完整字段清单，避免从语义描述反推。 | 派发 AgentCodex 做 plan follow-up，写入完整字段清单。 |
| `test_memory_repair.py` 存在性待确认 | DS NF-2 | accepted | 该文件当前存在，但计划中的条件描述会误导 implementation gate。 | 派发 AgentCodex 做 plan follow-up，改为直接纳入测试命令。 |
| durable schema 旧库 fail-fast 行为未显式说明 | DS NF-3 | accepted | schema 变更按全新 schema 起库处理，但旧 item kind / old snapshot key 的 fail-closed 行为需要成为可断言边界，避免静默读取或兼容迁移。 | 派发 AgentCodex 做 plan follow-up，补充 durable schema fail-fast / fail-closed 断言。 |
| control doc implementation commits 行未含 plan fix commit | DS NF-4 | rejected-with-reason | plan fix re-review 通过前尚未创建 accepted plan-fix commit；该行应在 Controller 提交 accepted follow-up commit 后更新，不是计划缺陷。 | Controller 在 accepted follow-up commit 后更新总控记录。 |

## Next Gate

进入 `WU-CM-01 Slice C plan fix follow-up gate`，由 AgentCodex 只修改计划 / 总控 / follow-up artifact，不修改 production code、tests、schema、config 或 README。

Follow-up 完成后，Controller 需要复核是否只做 accepted clarification；若未扩大 scope 且未引入新设计取舍，可直接接受并创建 accepted plan-fix commit。若 AgentCodex 改变 Slice C 范围、字段语义或分层边界，必须重新进入 plan re-review。

## Residual Risks

| 风险 | owner | destination |
|---|---|---|
| Slice C implementation / review 复杂度上升 | WU-CM-01 Slice C | implementation + code review gates |
| vNext public contract 或 durable schema 若在实现中发现设计真源不足 | Controller | 回到 Host design gate |
| 完整 Conversation Memory eval benchmark | WU-CM-10 / GitHub Issue #80 | 后续 work unit |
