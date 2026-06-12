# WU-CM-01-F01-S7-R1 One-System-Message Rescope Plan

## Gate

- gate: plan
- work unit: `WU-CM-01-F01-S7-R1`
- parent work unit: `WU-CM-01-F01` public smoke correctness closeout
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- design source: `docs/host/design.md`
- control source: `docs/host/issues-implementation-control.md`
- accepted blocker adjudication: `docs/reviews/wu-dur-obs-cm-closeout-slice7-retry-blocker-controller-adjudication.md`
- DS blocker review: `docs/reviews/wu-dur-obs-cm-closeout-slice7-retry-blocker-review-ds.md`
- implementation retry artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice7-implementation-retry-codex.md`
- artifact path: `docs/host/wu-cm-01-f01-s7-r1-one-system-message-rescope-plan.md`

## First-Principles Judgment

目标成立，严重性没有被高估。

一次 runner call 是给无状态 LLM 的完整输入。Host 可以在内部保留多个来源、多个 provider view、多个 projection ref 和多个 manifest entry，但最终投影给 LLM 的 `AgentRunRequest.messages` 必须尽量降低 provider 差异和模型认知负担。多条 `system` message 会让不同 provider / adapter 如何合并系统指令变成隐式前提，也让 public smoke 无法稳定证明普通 public path 的 LLM-facing shape 已收敛。

因此，本轮不能通过削弱 Slice 7 新增红测来关闭 blocker。红测读取的是 public `open_host()` / `submit_followup()` 路径中实际传给 Engine / Runner 的 `AgentRunRequest.messages` 和 scripted runner `messages_seen`，不是测试私有重建。正确下一步是生产 RunInput / memory projection rescope。

## Direct Evidence

- `dayu/host/run_input.py:1499`：accepted compact artifact 当前以独立 `SystemMessage` 进入 RunInput。
- `dayu/host/run_input.py:1707`：Host execution context 当前以独立 `SystemMessage` 进入 RunInput，且内容包含 `policy_snapshot_ref`。
- `dayu/host/run_input.py:1830` 至 `dayu/host/run_input.py:1879`：`RunInputBuilder.build()` 把 `memory.messages`、`compact.messages`、`continuity.messages` 与 system prompt / scene messages 展开后直接组成最终 `messages`。
- `dayu/host/run_input.py:2243`、`dayu/host/run_input.py:2268`、`dayu/host/run_input.py:2297`、`dayu/host/run_input.py:2318`、`dayu/host/run_input.py:2335`：五类 high-level memory section 均可能产出独立 `SystemMessage`。
- `dayu/host/run_input.py:2365`：selected recent window 中的 evidence item 当前被渲染为 `SystemMessage`。
- `dayu/host/run_input.py:2495`：recent-window fallback 中除 user / assistant final answer 外的 material block 当前被渲染为 `SystemMessage`。
- `dayu/host/run_input.py:3182`：等待恢复 continuity 中的工具结果说明当前也以 `SystemMessage` 投影。
- `docs/host/design.md:2537` 至 `docs/host/design.md:2548`：设计真源定义了 message 构造顺序，但没有定义普通 runner input 的 system-role cardinality。
- `docs/host/design.md:2732` 至 `docs/host/design.md:2756` 与 `docs/host/design.md:2933`：设计真源已经禁止 compact / memory LLM-facing material 暴露内部 ref / digest / cursor，但普通 RunInput system envelope 的稳定 contract 仍缺失。

当前 public smoke 失败与上述代码同源：

- `tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity` 观测到 `roles=('system', 'user', 'system', 'assistant', 'user')`。
- `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` 观测到 `roles=('system', 'system', 'system', 'user', 'system', 'assistant', 'system', 'user')`。

## Goal

把 `one-system-message` 提升为生产 public RunInput message shape hard contract：

- 每次 ordinary public runner call 的 `AgentRunRequest.messages` 至多包含一条 `system` role message。
- 若存在任何 system-scoped material，唯一 `SystemMessage` 必须位于最终 message list 的第一条。
- Host / Service system prompt、Host execution context、high-level memory sections、accepted compacted view、fallback governance-neutral说明、等待恢复上下文等 system-scoped material 必须被合并为同一个 bounded system envelope。
- selected recent window 中的 user / assistant / tool 对话连续性保留原角色；不得为了满足数量断言把普通对话历史伪装成 system。
- LLM-facing system envelope 只包含业务可读、自足、当前任务必要的信息；不得暴露 EventLog id、event sequence、payload / artifact ref、digest、cursor、policy ref、projection checkpoint、projector metadata、attempt / execution ledger 或 Host 内部治理字段。

## Success Signals

- `tests/host/test_public_tool_wiring_smoke.py`、`tests/host/test_public_open_host_multiturn_smoke.py`、`tests/host/test_public_compact_smoke.py` 的当前红测变绿；此前的 4 failed 变为 pass，既有 9 passed / 1 skipped 不回退。
- 所有 public smoke helper 记录到的 `AgentRunRequest.messages` / runner `messages_seen` 满足 `assert_at_most_one_system_message()`。
- compact public smoke 仍证明 compactor prompt / material 不暴露内部实现术语，manifest `message_count`、`message_entries` 和 `role_sequence_digest` 同源。
- focused RunInputBuilder tests 覆盖以下路径的 system merge：普通 no-compact、多轮 continuity、post-compact memory、selected recent evidence、fallback recent-window、resolve-wait resume continuity。
- `RUNNER_CALL_INPUT_ASSEMBLED` manifest 的 `message_count`、`message_entries`、role sequence digest 与最终投给 Engine 的 messages 同源；message count 会随 merge 后的真实 messages 更新，不引入兼容旧数量。
- `source .venv/bin/activate && pyright` 通过。
- `git diff --check` 通过。

## Non-Goals

- 不修改 Engine / Runner 的 tool loop 或 provider adapter 语义。
- 不新增 Host public API 字段，不修改 `SubmitFollowupRequest`、`open_host(options)`、`HostEvent` 或 Service-facing command contract。
- 不把完整 messages、provider request、memory snapshot、compact material 或 analyzer bundle 内联为 EventLog canonical fact。
- 不修改 durable schema，除非 implementation 发现 manifest recorder 因 message shape contract 需要新的 payload descriptor 字段；若发生，必须停止并回到 design gate。
- 不保留旧 multi-system-message compatibility path、别名、wrapper、feature flag 或测试绕过。
- 不为旧库做兼容读取；测试和本地库一律按 fresh schema 起库。
- 不实现完整 Tool Trace analyzer，也不扩展 real provider matrix smoke 的 provider 可用性要求。
- 不把用户 / assistant 对话历史改写成 system role 来压低 system count。

## Design Source Updates Required Before Code

implementation 前必须先更新 `docs/host/design.md`，因为当前设计真源只定义了 RunInputBuilder 的输入来源和顺序，没有定义最终 message role shape。需要补入以下稳定约束：

1. **ordinary RunInput system cardinality**
   - 普通 public runner call 的 `AgentRunRequest.messages` 至多一条 `SystemMessage`。
   - 唯一 `SystemMessage` 是 RunInputBuilder 产出的 system envelope，位于 message list 首位。
   - Engine continuation / fallback / replay 若有独立 call shape 不满足该约束，必须在设计中显式分类；本轮 scope 只处理 Host ordinary public RunInputBuilder 入口。

2. **system envelope sections**
   - system envelope 以稳定 section 顺序承载：caller system prompt、Host-neutral execution instruction、memory summary / facts / anchors / forward intents / reference continuity、accepted compacted view、fallback / wait continuity guidance。
   - section header 是 LLM-facing 业务标题，不是 projector id、Python 类型名、policy ref 或内部模块名。
   - 空 section 不渲染；非空 section 之间使用稳定分隔，不依赖隐式位置让模型推断含义。

3. **role preservation**
   - selected recent window 中的用户输入继续是 `user`；助手最终回答继续是 `assistant`；工具结果和 evidence 若不能作为 `tool` role 合法进入当前 Engine contract，则进入 system envelope 的业务可读 evidence section，而不是散落为多条 `SystemMessage`。
   - 当前 user prompt 仍只来自 `USER_INPUT_ACCEPTED`，仍是最后的 current input `UserMessage`。

4. **LLM-facing internal-field ban for ordinary RunInput**
   - 普通 RunInput system envelope 与 selected recent window 都不得显示 EventLog id、event sequence、payload / artifact ref、digest、cursor、policy ref、projection checkpoint、projector metadata、attempt / execution ledger、tool_call_id 或 Host 内部账本字段。
   - 这些 refs / digests 只能进入 manifest、Tool Trace、audit、diagnostic 或 payload descriptor，不能作为模型阅读材料。

5. **manifest alignment**
   - `RUNNER_CALL_INPUT_ASSEMBLED.message_count`、`message_entries`、`role_sequence_digest` 必须记录 merge 后的最终 messages。
   - manifest 可以继续用 internal refs / projector metadata 解释每个 section 的来源；LLM-facing envelope 不得暴露这些 refs。

6. **boundedness**
   - 合并为单条 system message 不能绕过既有 memory / compact / fallback char caps。
   - system envelope 只拼接已由各 provider 预算治理后的 bounded content；不得因为合并而重新展开旧 compact artifact、完整 memory snapshot 或 raw history。

## Chosen Approach

选择在 `RunInputBuilder` 边界做生产级 system envelope normalization，而不是在测试里特殊处理，也不是要求 Engine / provider adapter 自行合并 system messages。

原因：

- RunInputBuilder 是设计真源指定的 `AgentRunRequest.messages` 唯一构造入口。
- Root cause 来自 RunInputBuilder 的多个 provider view 展开；在这里收敛能同源覆盖 memory、compact、continuity、fallback、manifest recorder。
- Engine 只执行单次 request，不应理解 Host memory / compact / governance sections，也不应承担 Host prompt shape 修复。
- Service / ScenePrepare 只提供 caller system prompt，不拥有 Host memory / compact / continuation material，不能从上层合并完整 envelope。

implementation 不应采用“只合并开头连续 system message”的局部止血。当前失败已经证明 system role 可能出现在 selected recent window、fallback material 或 wait continuity 之后；必须保证最终 message list 全局至多一条 system role message。

## Implementation Plan

### Slice S7-R1-S0: Design Contract Sync

Objective: 把 one-system-message 和 LLM-facing ordinary RunInput 边界写入 Host 设计真源。

Allowed files:

- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`

Expected changes:

- 在 `## 23. RunInputBuilder` 中补充 system envelope hard contract、section 顺序、role preservation、manifest alignment 与 boundedness。
- 在 `## 24. Conversation Memory` 相关 LLM-facing 边界中补充普通 RunInput memory projection 不暴露内部 refs / digests / cursors 的约束，避免只约束 compact input。
- control doc 进入 implementation gate 前记录 plan review 通过后的 accepted plan artifact。

Stop condition:

- 如果 design review 拒绝 one-system-message 作为 hard contract，停止 production implementation，并回到 Slice 7 success condition 重裁决；不得同时放宽红测和继续声称 one-system-message closeout。

### Slice S7-R1-S1: RunInput System Envelope

Objective: 在 `dayu/host/run_input.py` 中把所有 system-scoped material 合并为单条 system envelope，同时保持 user / assistant 对话历史角色。

Allowed production files:

- `dayu/host/run_input.py`

Expected changes:

- 新增模块级私有 typed helper，用于从最终候选 messages 中抽取所有 `SystemMessage` 内容，按原相对顺序合并为一个 `SystemMessage`，再把非 system messages 保持原序输出。
- helper 必须保留完整中文 docstring，参数和返回值必须有严格类型；不得使用 `Any`、`object` 或无类型签名。
- 合并逻辑必须 fail closed：若遇到未知 message type、空 section、无法读取文本 content 或 provider structured parts 无法按当前 contract 表达，抛出结构化 Host 错误，不静默丢内容。
- system envelope 使用模块级常量定义 section title / separator；不得散落魔法字符串。
- `_system_prompt_message()`、`DefaultSceneParameterProvider.build_scene_messages()`、memory high-level section、compact artifact view、fallback material 和 wait continuity 可以继续先产出内部候选 `SystemMessage`，但最终 `AgentRunRequest.messages` 必须经过统一 normalization 后再记录 manifest 和返回。
- 当前 `policy_snapshot_ref`、memory fact 的 `event_id` / `event_sequence` / `extraction_operation_ref` / internal evidence refs、wait continuity 的 `tool_call_id` 等内部字段不得继续进入 LLM-facing content；需要改为业务可读说明或 Host-neutral unavailable wording。
- manifest recorder 必须消费 normalization 后的 final messages，而不是 merge 前候选 messages。

Stop condition:

- 如果需要改变 Engine message dataclass、Runner contract 或 Host public request dataclass，停止并回到 design review。
- 如果某类 internal ref 无法在不丢业务语义的前提下改写为 LLM-readable wording，停止并列出该来源、字段和需要补的 durable atom；不得把 ref 原样留在 prompt。

### Slice S7-R1-S2: Focused Tests And Public Smoke Closeout

Objective: 用 focused tests 和既有 public smoke 红测证明 production path 收敛。

Allowed test files:

- `tests/host/test_run_input_builder.py`
- `tests/host/test_public_tool_wiring_smoke.py`
- `tests/host/test_public_open_host_multiturn_smoke.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/public_smoke_support.py` only if assertion helper needs stronger diagnostics without weakening cardinality

Expected changes:

- 更新 `test_run_input_builder.py` 中旧多 system shape 期望，断言 final messages 至多一条 system role message，并检查 envelope 包含必要业务 sections。
- 添加 focused cases 覆盖：
  - no-compact recent raw continuity；
  - post-compact facts / compact artifact；
  - selected recent evidence；
  - fallback recent-window；
  - wait resume continuity；
  - manifest `message_count` / `message_entries` / role digest 与 normalized messages 同源。
- 保留当前 Slice 7 public smoke assertions；不得删除或削弱 `assert_at_most_one_system_message()`。
- 若 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 的 `"policy"` / `"digest"` 未来误伤普通英文，应另行精确化 forbidden term，但本轮不得用该低风险项绕过 multi-system blocker。

Stop condition:

- 如果 public smoke 仍观测到多条 system message，停止并保留失败输出；不得通过跳过场景、改 label 或改 helper 让测试通过。
- 如果 focused tests 只能通过读取 private durable table 才能证明 message shape，停止；本 work unit 的核心验收必须来自 public path request / runner messages。

## Allowed Files Summary

Production:

- `dayu/host/run_input.py`

Design / control:

- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`

Tests:

- `tests/host/test_run_input_builder.py`
- `tests/host/test_public_tool_wiring_smoke.py`
- `tests/host/test_public_open_host_multiturn_smoke.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/public_smoke_support.py` only for non-weakening diagnostics

README inspection triggers:

- `dayu/host/run_input.py` change triggers `dayu/host/README.md` inspection. Update only if the README still describes RunInputBuilder as emitting separate memory / compact system messages or omits the new stable one-system envelope contract where it already documents RunInputBuilder message assembly.
- `tests/` changes trigger `tests/README.md` inspection. The current retry already documented public smoke one-system assertions; update only if focused RunInputBuilder coverage or public smoke responsibilities change further.
- `docs/host/design.md` update does not by itself require root README changes.
- No root `README.md` update is expected because CLI commands, install flow, trace/render entry points and user workflow do not change.
- No `dayu/README.md` update is expected unless implementation changes the `UI -> Service -> Host -> Engine` boundary or composition responsibility, which is a stop condition for this plan.

## Contract / Schema / Migration Strategy

- Contract change: ordinary public `AgentRunRequest.messages` is normalized to at most one `system` role message.
- Public API dataclasses do not change.
- Durable schema does not change in the intended implementation.
- Runner-call manifest schema does not change; its values update to reflect the normalized final messages.
- Fresh schema only. If implementation unexpectedly requires schema changes, create fresh-schema tests and do not add old DB compatibility readers, old manifest compatibility aliases, dual field names, fallback wrappers or migration bridges.
- Existing uncommitted red tests are acceptance assertions for the new contract and must remain active.

## Validation Matrix

Run from repository root:

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q
source .venv/bin/activate && pyright
git diff --check
```

Expected focused results:

| Area | Required proof |
|---|---|
| RunInputBuilder ordinary path | no-compact, multi-turn and post-compact inputs produce at most one `system` message |
| memory projection | summary / evidence facts / anchors / intents / reference continuity stay business-readable and bounded inside one envelope |
| selected recent window | user / assistant roles are preserved; evidence does not create extra system messages |
| fallback | recent-window fallback produces at most one system envelope and still includes selected bounded material |
| wait resume | wait continuity does not expose `tool_call_id` or ledger fields to LLM and does not add another system message |
| manifest | `message_count`, `message_entries` and `role_sequence_digest` match normalized final messages |
| compact public smoke | compactor prompt / material assertions from Slice 7 remain active |
| pyright | no new or expanded type errors |
| diff check | no whitespace errors |

Optional provider matrix remains environment-gated and is not required to close this deterministic production shape blocker:

```bash
source .venv/bin/activate && DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity -q
```

## Stop Conditions

- 设计真源未先接受 one-system-message hard contract。
- 需要改 Engine / Runner / Service public API 才能完成。
- 需要 schema 变更但没有新的 design review。
- 任何 implementation 试图删除、跳过、放宽当前 public smoke one-system assertions。
- LLM-facing content 仍包含 EventLog id、payload / artifact ref、digest、cursor、policy ref、projection checkpoint、projector metadata、attempt / execution ledger 或 `tool_call_id`。
- 合并 system messages 后丢失 compact artifact、memory section、tool evidence、wait continuity 或 selected recent window 中对当前任务必要的业务语义。
- `pyright` 出现新增或扩散错误。

## Residual Risks

- 不同 provider 对单条长 system envelope 的最佳格式可能仍有偏好差异。当前 mitigation 是 deterministic section ordering、bounded content 和 focused public smoke；real provider matrix 仍由后续 smoke / provider work 覆盖。
- 当前 plan 不重构 memory snapshot 存储或 compact artifact schema，因此只能保证本次 RunInput projection 不暴露内部 refs；历史 artifact / historical review 文本中出现的旧字段不是本轮 runtime LLM-facing 风险。
- 如果 design review 认为 `tool` role 应用于更多 historical evidence，而不是放入 system envelope，需要独立 Engine message contract review；本轮保守保持现有 Engine role vocabulary，不扩大 public API。

## Completion Report Format

implementation 完成后必须报告：

- 设计真源更新位置和 one-system-message contract 摘要。
- 生产变更：system envelope merge 点、移除或改写的 LLM-facing internal fields、manifest recorder 是否消费 normalized messages。
- 测试变更：focused RunInputBuilder cases 与 public smoke assertions 是否保留。
- 验证结果：pytest 命令与结果、pyright 结果、`git diff --check` 结果。
- README 决策：检查了哪些 README，是否更新以及原因。
- residual risk：仍未覆盖项、owner / destination。
