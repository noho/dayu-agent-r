# WU-CM-01 Slice C Plan Fix Follow-up Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C plan fix follow-up adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| follow-up artifact | `docs/reviews/wu-cm-01-slice-c-plan-fix-followup-codex.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`accepted`。

AgentCodex 只处理了 Controller 在 `docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-controller-adjudication.md` 中接受的 clarification findings，未修改 production code、tests、schema、config JSON 或 README，未创建 commit、push 或 PR。

## Accepted Clarifications

- `CompactMaterialPack` 旧 `stable_input` / `history_input` / `evidence_input` / `current_input_anchor` 到 vNext material section 的迁移规则已写入 Slice C。
- 旧 `CompactMaterialBlockKind` 全量枚举到 vNext section 或删除语义的映射已写入 Slice C，并明确禁止旧 enum alias。
- vNext `memory_projection_policy` JSON 字段完整清单已对齐 `docs/host/design.md` 第 3 章。
- `dayu/config/execution_profiles.json` packaged config 与 `tests/runtime` / `tests/service` config fixtures 的 Slice C implementation 迁移边界已写入计划；旧 config 字段必须 fail fast，不做 alias、默认补齐或 wrapper。
- `tests/host/test_memory_repair.py` 已作为现存必跑测试纳入命令，不再保留条件式替代描述。
- durable/schema 的旧 snapshot key / 旧 durable item kind row fail-fast / fail-closed 断言已写入 Slice C。

## Re-review Decision

不需要重新 re-review。follow-up 没有扩大 Slice C allowed files 之外的新业务范围，也没有改变 design source 中的 vNext memory contract、policy 字段语义或分层边界；它只是把已接受 finding 变成 implementation gate 可执行的计划文字。

## Next Gate

进入 `WU-CM-01 Slice C implementation gate`。

AgentCodex implementation 必须按更新后的 plan 执行，并在 implementation artifact 中明确验证：

- 旧 snapshot / policy direct consumers 已迁移；
- old config fields fail fast；
- old snapshot key / old durable item kind fail-fast / fail-closed；
- focused tests 与 pyright 通过；
- 若触发 README 更新规则，按职责同步更新。
