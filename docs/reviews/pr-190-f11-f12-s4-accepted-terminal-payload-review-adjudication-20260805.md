# PR 190 F11/F12 S4.2 accepted terminal payload review adjudication

## 范围与裁决原则

- 基线：`f7957b6343f4647ce0c6058a08e9ae84ab629f30`
- MiMo review：`docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-mimo-review-20260805.md`
- DeepSeek review：`docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-review-20260805.md`
- 实现说明：`docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-fix-20260805.md`
- 裁决 owner：Gateflow controller

两路 review 都作为 durable artifact 保留。本裁决逐项依据当前生产路径、持久化事务语义和已经冻结的 owner boundary 判断，不以 reviewer 是否一致代替证据。

## 裁决摘要

| Finding | 裁决 | 理由 |
|---|---|---|
| MiMo：无实质 finding | 接受 review 结论，但补充 DS-F01 | MiMo 对两路 writer、主要消费者、artifact/terminal 同源、background health 与类型/测试的判断成立；它遗漏了 `DurableCompactArtifactProvider` 的 raw inline consumer。 |
| DS-F01 | **accepted / must-fix** | `DurableCompactArtifactProvider._load_compact_artifact_tx` 在同一 read transaction 内仍调用 `_payload_object(row)`；descriptor-backed `CONTEXT_COMPACTED` 必然读成 `{}`，随后 strict semantic parser 失败。它是当前公开 production provider 的真实 consumer，必须复用统一 resolver 并补 oversized owner test。 |
| DS-F02 | rejected-with-reason | 当前 `HostTransactionRunner.run_write` 的 busy retry 每次都 rollback 整个 SQLite transaction 后重跑，没有 reviewer 假设的 savepoint/部分提交。外层重新执行时 terminal permit 会先读取 canonical terminal；不存在“第一次部分提交后以新 event id 写第二 terminal”的可达当前路径。随机 event id 是既有 proactive identity 选择，不是本 blocker 引入；为未来未存在的 savepoint 语义改造 idempotency 超出本 slice，且不能作为“严重”现存 bug。 |
| DS-F03 | rejected-with-reason | 这是既有 `PayloadStore.write_bounded_json_payload` 的通用 filesystem/SQLite rollback 属性，不是本 slice 新建的特殊路径；compact artifact 本来也先写 filesystem 后写 descriptor。当前 work unit 明确不扩张到通用 filesystem transaction/rollback 设计。content-addressed artifact 的 orphan/cleanup 若需改变，应由独立 durable-storage work unit 统一处理，不能只在 compaction owner 局部 catch/unlink；并发同 digest 下 reviewer 建议反而可能删除其它已引用内容。分类为 independent pre-existing storage lifecycle risk，非 S4.2 blocker。 |
| DS-F04 | rejected-with-reason | 当前 activity contract 对 `CONTEXT_COMPACTED` 只投影固定 completed 状态/title，并仅从 payload 读取本事件不存在的 `failure_reason`；inline `{}` 与完整 payload 的可观察结果相同。不存在当前语义丢失。若未来 activity 需要 attempt/operation 字段，应届时在 read-api owner 明确扩展 typed projection；现在增加解析和失败语义属于 speculative scope。 |
| DS-F05 | rejected-with-reason | `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 当前只有 inline canonical writer，且 EventLog canonical inline guard 会拒绝超限；本 slice 没有也不应为它虚构 descriptor-backed contract。F11 rejected response identity 已由其 canonical inline terminal owner解析。为不存在的 writer path预先加 reader 分支属于兼容/过度设计。 |
| DS-F06 | rejected-with-reason | 同 DS-F05。`ATTEMPT_REJECTED`、`FAILED` 与 `RUNNER_CALL_INPUT_ASSEMBLED` 当前没有 descriptor-backed storage contract；`_project_state` 的 accepted `CONTEXT_COMPACTED` 分支才是本次需要迁移的真实消费者。未来改变其它 event storage 时必须由各自 writer/reader owner 同步设计，不能在当前 consumer 预留 loose capability。 |
| DS-F07 | rejected-with-reason | `PayloadStore` 当前无实例状态；proactive 内原本已经多处按值实例化该 durable primitive。改为 scheduler 注入不会改变任何当前语义，只会扩大构造/public wiring。不是 bug，也不是本 slice 必需重构。 |
| DS-F08 | rejected-with-reason | `build_context_compacted_payload` 拥有 canonical semantic shape，不拥有 storage threshold；尺寸与 inline/descriptor 选择应由新 durable mapping owner完成，EventLog仍保留最终 fail-closed guard。把 storage policy塞进 semantic builder会造成 owner drift；非-canonical event 使用该 canonical terminal builder也不存在当前路径。 |

## 必须修复的精确边界

只接受 DS-F01：

1. `DurableCompactArtifactProvider._load_compact_artifact_tx` 必须用当前 transaction 调用 `resolve_context_compacted_payload(transaction, row)`。
2. 保持 `parse_context_compacted_semantic_payload` 与 compact artifact digest 的现有 strict validation；不得增加 fallback、默认值或 inline 特例。
3. 新增 owner test，以低 inline threshold 写入真实 descriptor-backed `CONTEXT_COMPACTED`，再通过 `DurableCompactArtifactProvider` 读取并断言 artifact ref/digest、event ref 与 represented evidence refs。
4. 加入 corruption 反例，证明 provider 与其它 consumer 一样对 ref/digest/blob 漂移 fail closed；若已有同层严格 resolver test 足以直接覆盖，可在 re-review 中以直接测试证据说明而不重复所有 corruption matrix。

## Gate 状态

- 当前 S4.2：`FIX_REQUIRED`。
- implementation owner：AgentCodex。
- 修复后必须由 MiMo、DeepSeek 对完整 S4.2 diff 各自重新 `/deepreview` 并产出独立 re-review artifact。
- 两路 re-review accepted 前不得 commit/push，也不得重启 real-provider observation。
