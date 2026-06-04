# WU-CM-01 Slice C Plan Fix Follow-up

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C plan fix follow-up |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-controller-adjudication.md` |
| rereview artifacts | `docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-mimo.md`; `docs/reviews/wu-cm-01-slice-c-plan-fix-rereview-ds.md` |
| author | AgentCodex |
| date | 2026-06-04 |

## Motivation

动机成立。Controller 已接受的 findings 都是 code-generation-ready clarification 缺口，不是新的架构取舍：Slice C implementation 会修改 compact material contract、memory projection policy config、durable schema boundary 与测试矩阵；如果计划不固定字段清单和旧 shape 删除语义，implementation agent 仍需自行推断，容易引入旧字段 alias、compat wrapper 或旧库兼容读取。

严重性为低到中。复审未发现 blocking finding，核心 Slice C reslice 方案仍成立；但这些 clarification 会直接影响 implementation 的字段命名、配置迁移和 fail-fast 测试断言，适合在进入 implementation gate 前补齐。

## Plan Updates

已更新 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- 补充 `CompactMaterialPack` 字段迁移表：`stable_input` 删除旧顶层字段并按 vNext snapshot / accepted compact output 重建为 `previous_compacted_view` 等材料；`history_input` 迁移为 `trace_material` / `answer_material`；`evidence_input` 迁移为 `evidence_material`；`current_input_anchor` 保留为 vNext typed field 但不得作为旧字段 alias。
- 补充旧 `CompactMaterialBlockKind` 全量枚举到 vNext section 或删除语义的映射，并明确不得保留旧 enum alias。
- 补充 vNext `memory_projection_policy` JSON 完整字段清单，直接对齐 `docs/host/design.md` 第 3 章。
- 明确 `dayu/config/execution_profiles.json` packaged config 真源，以及 `tests/runtime`、`tests/service` 中 config fixtures，必须在 Slice C implementation 中同步迁移为 vNext 字段；旧字段必须 fail fast，不做 alias、默认补齐或 wrapper。
- 将 `tests/host/test_memory_repair.py` 作为当前存在的必跑测试纳入 Slice C 命令，删除“不存在则替代覆盖”的条件描述。
- 在 durable/schema 边界补充旧 snapshot key / 旧 durable item kind row 的 fail-fast / fail-closed 断言：全新 schema 起库，不兼容读取旧库 row，不静默跳过或物化旧 item kind，失败时 checkpoint 不前进、snapshot 不部分提交。

## Control Doc Updates

已更新 `docs/host/issues-implementation-control.md`：

- `implementation status` 改为 `slice-c-plan-fix-followup-complete`。
- `next entry point` 改为 `WU-CM-01 Slice C implementation gate`。
- 记录 Slice C plan fix rereview artifacts、Controller adjudication artifact 与本 follow-up artifact。
- 保持 implementation commits 行不变，未声称存在 Slice C implementation commit 或 follow-up accepted commit。

## Untouched Scope

本 gate 未修改 production code、tests、schema、config JSON、README，未运行实现测试或 pyright，未 commit / push / PR，也未进入 Slice C implementation。

## Re-review Need

不需要重新 re-review。本次只把 Controller 已接受 findings 写成计划澄清，没有改变 Slice C 范围、字段语义、分层边界或 durable schema 设计取舍。建议 Controller 复核本 follow-up 是否严格限于 accepted clarification；若通过，可进入 `WU-CM-01 Slice C implementation gate`。
