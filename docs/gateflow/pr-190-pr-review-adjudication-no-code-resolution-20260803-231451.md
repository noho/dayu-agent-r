# PR 190 PR-review 控制器裁决与 no-code resolution

## Gate metadata

- Gate：PR review adjudication / no-code resolution
- Work unit：PR 190 `fix(cli): close interactive conformance gaps`
- Branch：`codex/interactive-oracle`
- Base：`main` / `113ea34d47b95812d79aa31705949bbb46bc6061`
- Reviewed head：`b819309c654b9db8e3f02280687bdb3291442a89`
- 裁决时间：2026-08-03 23:14:51 +08:00
- Controller scope：完整裁决两路 PR review 的每个独立 finding；只允许新增本 artifact，不允许修改 review、production code、tests、prompt、manifest、README、design、oracle/scenario；本 artifact 创建阶段不执行 stage、commit 或 push。
- Completion status：`pass / no-code-resolution`

## Reviewed targets

两份初始 review artifact 均完整读取，并保持原文件不变：

1. `docs/reviews/pr-190-review-20260803-225333.md`
   - SHA-256：`0517f0e2c496a2990313cd2782ce572deb589a31e9348c61190352b364fe0506`
2. `docs/reviews/pr-190-review-20260803-225520.md`
   - SHA-256：`70f30f0a5878ba196c9942754cc274a38462977ea10dbebb6a966478fbec4c97`

本裁决不因两路 review 对某项 finding 一致就自动接受，也不因只有一路提出就自动拒绝；每项 disposition 都回到设计契约、直接实现、全部相关消费者与 owner-level tests 独立判定。

## First-principles judgment

PR review code fix 只有在当前实现违反业务/架构 contract、存在可触发的 correctness 或 stability failure、或在当前 work unit 内能完整修复唯一语义 owner 时才成立。

本轮证据显示：

- 九个 `Readable*VNext`/`TraceReadable*VNext` 名称及剩余 `vNext` docstring 是真实命名债，但该债务在 PR 190 的 merge base 已存在，不改变运行时语义；只改其中一部分不能完成命名 contract 清理。
- 空 snapshot Protocol、interactive wait-result union、composer phase 交互均是有意的 typed boundary/lifecycle 设计，没有发现错误数据流或分裂真源。
- `intent_type`/`reference_continuity.reason` 的开放字符串是已冻结的 LLM-facing 业务语义；所有生产消费者均机械校验、持久化、投影或渲染，没有按旧 enum token 分支。
- `source_boundary_refs` 的位置 contract 已由 design 与 strict parser owner 明确定义；消费者读取 parser 投影的 typed fields，没有从 raw index 反推语义。

因此没有 accepted PR-review code fix。唯一保留项是一个明确归属后续专门 work unit 的非阻塞命名债。

## Independent finding adjudication

### F-01：九个 readable-view 类型仍使用 `VNext` 后缀

- 来源：第一路 finding 01；第二路 finding 03。
- Disposition：`deferred-with-owner`。
- Severity reclassification：非阻塞 naming debt；不是当前 PR correctness defect。
- Owner / destination：后续单独的 **Host compaction/readable-view naming-cleanup work unit**；语义 owner 为 `dayu/host/compaction.py` 的 readable-view public contract，并需一次性覆盖其直接消费者、exports 与 owner tests。

直接证据：

1. `git merge-base main HEAD` 与当前 `main` 都是 `113ea34d47b95812d79aa31705949bbb46bc6061`。在该 PR merge base 的 `dayu/host/compaction.py` 中，以下九个类型已全部存在：
   - `TraceReadableKindVNext`
   - `ReadableFactItemVNext`
   - `ReadableAnswerAnchorItemVNext`
   - `ReadableAnswerAnchorVNext`
   - `ReadableForwardIntentVNext`
   - `ReadableReferenceContinuityItemVNext`
   - `TraceReadableItemVNext`
   - `EvidenceReadableItemVNext`
   - `AnswerReadableItemVNext`
2. `git log -S` 将这些名称追溯到 `473dd5eb302a612c4ac60ed9cf7dde880f0f2eaa`（2026-06-05，`WU-CM-01 Conversation Memory vNext (#116)`），早于 PR 190。
3. 当前九个类型仍由 `dayu/host/compaction.py` 的 `__all__` 导出，并被 `dayu/host/compact_material.py` 与多份 Host tests 共同引用；重命名需要一次性更新整个 readable-view contract surface，而不是只改九个 class declaration。
4. 类型名称不参与 schema literal、候选验收、持久化或运行时分支；当前 schema 真源仍是 `COMPACT_INPUT_SCHEMA_V2` / `COMPACT_OUTPUT_SCHEMA_V2`。

裁决理由：命名不一致真实存在，但它是历史 public naming debt。把它塞入当前交互一致性/compactor 语义 PR 的 review fix，只会形成范围不完整的部分重命名，也不会修复 correctness。必须由专门 work unit 一次性清理 owner、imports、exports、tests 与文档术语。

### F-02：`compaction.py` 剩余 `vNext` docstring

- 来源：第一路 finding 02；第二路 finding 04。
- Disposition：`deferred-with-owner`。
- Severity reclassification：非阻塞 documentation/naming debt；与 F-01 同一 destination，不创建第二 owner。
- Owner / destination：同一 **Host compaction/readable-view naming-cleanup work unit**。

直接证据：

1. merge base 的 `dayu/host/compaction.py` 有 95 行包含 `vNext`；当前文件有 61 行，说明 PR 已随 v2 contract 改造移除一部分旧术语，但未完成整个模块的命名清理。
2. 当前 diff 仅新增一行含 `vNext` 的 docstring 文案，该行是把 base 中原有“返回 vNext candidate”改成“返回与实际成功 Runner call 身份配对的 vNext proposal”；它没有引入新的命名体系，仍是既有术语债在变更行上的延续。
3. 剩余文案分布在 readable view、candidate、validator、port 与 JSON projection helpers。机械局部替换不能同时解决 F-01 的 public type names、field-name diagnostics、helper wording 与消费者命名。
4. docstring 不进入 LLM-facing prompt，也不改变 schema、durable state、Memory 或 RunInput 行为。

裁决理由：债务成立，但不是当前 PR 的行为缺陷。与 F-01 分拆修复会制造同一 owner 的两次不完整迁移；应由同一后续命名清理 work unit 完整处理。

### F-03：`CompactPipelineAttemptDispatchSnapshot` 是空 Protocol

- 来源：第一路 finding 03；第二路 finding 05。
- Disposition：`rejected-with-reason`。

直接证据：

1. `dayu/host/compact_pipeline.py:1-6` 明确把该模块限定为薄 helper contract：不读取 EventLog、不创建 Attempt、不推进 lifecycle。
2. `dayu/host/compact_pipeline.py:169-170` 的 snapshot Protocol 没有成员；同文件 `CompactPipelineProtectedRawTailProvider.load_ordinary_raw_tail` 的 docstring 明确写明“具体类型由 RunInput adapter 拥有”。
3. 生产 concrete value 是 `dayu/host/api.py:715-740` 的 `AttemptDispatchSnapshot`；`dayu/host/run_input.py` 同时知道 concrete type 与 lower seam，并在 `RunInputBuilder.build` 调用 provider 时传入该值。
4. 两个生产 provider implementation（`_NoopProtectedRecentRawTailProvider` 与 `_DurableProtectedRecentRawTailProvider`）均不读取 snapshot 成员；前者与后者都显式 `del snapshot`。全仓没有 lower seam 对该 Protocol 成员的消费。
5. raw-tail 所需真实数据由另外三个窄协议参数 `current_facts`、`memory`、`compact` 提供；这些协议各自声明实际被消费的成员。
6. owner-level raw-tail / RunInput tests通过，证明该 opaque handoff 没有导致实际 raw-tail 选择或去重缺口。

裁决理由：该参数是由 RunInput adapter 绑定的 opaque lower-layer seam，不是 compact pipeline 可解释的数据 contract。给空 Protocol 添加 `AttemptDispatchSnapshot` 字段会把上层 concrete shape 泄漏进不消费它的下层 helper，并发明未使用的 contract；以 `object`/`Any` 替代又违反项目严格类型约束。review 所称“任何对象均满足”是结构类型事实，但在这里正是“不允许下层依赖其 shape”的边界表达，不构成缺陷。

### F-04：`InteractiveComposerCompletionResult` union 过宽

- 来源：第一路 finding 04。
- Disposition：`rejected-with-reason`。

直接证据：

1. `dayu/cli/session_execution.py:2144` 的 union 精确覆盖同一 `asyncio.wait` 集合内四类真实 task result：
   - composer task：`_InteractiveComposerCompletion`；
   - submit/cancel task：`EntrypointRunTerminalResult`；
   - current/queued acceptance task：`str`；
   - SIGINT monitor task：`int`。
2. `_InteractiveActiveTurn.submit_task`、`_InteractiveQueuedFollowup.submit_task` 与 `_ActiveTurnCloseout.cancel_task` 都显式声明为 `asyncio.Task[EntrypointRunTerminalResult]`；acceptance 与 SIGINT task 也分别有 `Task[str]` / `Task[int]` 注解，不存在未约束返回值。
3. `asyncio.wait` 返回后，driver 先用 task identity 判断 `composer_task in done`、`current_acceptance_task in done`、`queued_acceptance_task in done`、`sigint_task in done` 或 `active.submit_task in done`，再 await 已识别的窄变量；代码不从一个 union result 值猜测其语义类型。
4. 两处集合确实是异构 task 集合。建议改成 `set[asyncio.Task[object]]` 会直接引入项目禁止的 `object`，而为每个 task 创建独立 wait 集合会破坏 `FIRST_COMPLETED` 的单一竞争集合。
5. 相关 interactive lifecycle tests 与目标模块 pyright 均通过。

裁决理由：union 不是对业务结果做模糊分支，而是精确描述 `asyncio.wait` 容器的异构 task result 上界；任务身份在 await 前已知，运行逻辑继续使用窄类型变量。无外部消费者不是删除内部类型别名的依据。

### F-05：composer 与 driver 分裂 phase ownership

- 来源：第一路 finding 05；第二路 finding 06。
- Disposition：`rejected-with-reason`。

直接证据：

1. phase state 的唯一 storage owner 是 `PromptToolkitInteractiveComposer._phase`：字段在 `dayu/cli/composer.py:323` 声明、在 constructor 中初始化，所有读取都通过 composer 自身的 `_current_phase` / key-binding condition。
2. composer 对同步输入语义拥有必须早于 event-loop 调度的内部 transition：`_record_submit_intent` 在 Enter chord 解码时立即进入 `SUBMITTING`；`accept_submit` 原子清理 pending document/history 后进入 `RUNNING`；`reject_submit_delivery` 恢复文档后进入 `IDLE`。
3. driver 没有读取或写入 `_phase`，只通过 `InteractiveComposer` public Protocol 的 `set_phase` 通知 Host acceptance、cancel、terminal、queued promotion 等 lifecycle transition。driver 负责何时发生生命周期转换，composer 负责保存 phase 并把它投影为按键语义；这不是两个 storage/source-of-truth owner。
4. `accept_submit(record_history=True)` 后 driver 再公开确认 `RUNNING` 是同值幂等 transition；它让 scripted composer 与真实 composer 遵循同一 public lifecycle contract，不产生第二份 phase state。
5. composer tests 覆盖 submit intent、accept/reject、active typeahead 与 phase matrix；driver tests 覆盖 queued promotion、cancel、terminal race 与 SIGINT chord，目标用例全部通过。

裁决理由：finding 把“transition 的调用者”误判成“状态 owner”。私有状态和按键解释仍唯一属于 composer；driver 只是协调 Host lifecycle 并调用公开 transition。收回任一侧职责反而会丢失 Enter chord 的同步语义或把 prompt-toolkit 私有状态泄漏给 driver。

### F-06：`intent_type` / `reference_continuity.reason` 从 enum 变为 free-text

- 来源：第二路 finding 01。
- Disposition：`rejected-with-reason`。

直接证据：

1. LLM-facing owner `dayu/config/prompts/scenes/conversation_compaction_user.md:47-55` 自足声明：
   - `intent_type` 是非空、业务可读的后续动作类别；
   - `reason` 是说明为何仍需保留指代、术语或对象关系的非空业务文本。
   两者都没有闭集允许值；与同一 schema 中明确列出闭集的 `status` 和 drop `reason` 形成清晰对照。
2. `dayu/host/llm_compaction.py` 对两字段使用 `_required_string`；`CompactForwardIntentV2` / `CompactReferenceContinuityV2` 使用 `str` 并校验非空。parser、typed contract 与 prompt owner 同源一致。
3. 全部生产消费者审计结果：
   - Context Governance 只将规范化 `intent_type+text` 用作重复/矛盾 identity，将 `reason` 用于相同 reference text 的矛盾检测；
   - compact material、Memory 与 durable Memory 只复制、序列化/反序列化这些文本；
   - RunInput 只把它们渲染成业务可读上下文；
   - 没有任何生产代码按旧 enum token（`open_question`、`pending_clarification`、`pending_user_visible_task`、`next_step_note`、`local_reference`、`ordinal_reference`、`ellipsis_recovery`、`recent_state`）执行分支。
4. `tests/host/test_context_compact_events.py` 明确用 `custom_follow_up` 与 `retain_for_next_comparison` 证明 persisted parser 接受任意非空业务文本；同文件另测 `status` 非法值必须拒绝，锁定开放/闭集边界。
5. `tests/host/test_llm_compaction.py` 锁定 prompt 中“业务可读的后续动作类别”和“为什么仍需保留该指代、术语或对象关系”两项开放语义。
6. prompt asset 由 `docs/cli_init_workspace_manifest_v1.json` 的 content SHA-256 固定发布，当前 owner digest 为 `a2f5711c84f6fdd51f921e5d266d05cdb3f6a34a6c8321ffc42f0c5dc75a0dce`。

裁决理由：这不是“下游缺少防护”，而是业务语义从旧技术分类 token 改为自解释开放文本。新增 allowlist 会改变已冻结的 prompt/schema 语义，并把旧 enum 重新引入 accept owner；这需要新的业务语义 work unit 重新裁决，不能作为本 PR review fix 偷渡。

### F-07：`source_boundary_refs[0]` 是未文档化隐式契约

- 来源：第二路 finding 02。
- Disposition：`rejected-with-reason`。

直接证据：

1. `docs/host/design.md:3429-3431` 明确规定持久化顺序：第一项必须是 `current_input_ref`，其余去重 refs 是 `compacted_source_refs`；只含当前输入时后者可为空。
2. 同一设计段明确指定 compact payload source boundary 是 typed read owner，并禁止 Conversation Memory 等消费者索引 raw list、按 ref 前缀或 event 顺序/时间戳反推角色。
3. `dayu/host/compact_payload.py:177-211` 的 strict parser 一次性校验 raw list 非空、每项非空且全局唯一，将首项投影为 `ContextCompactedSemanticPayload.current_input_ref`，再校验完整 tuple 必须等于 `(current_input_ref, *compacted_source_refs)`。
4. 两个 writer 同源遵守 contract：`dayu/host/compact_payload.py:780-784` 与 `dayu/host/compact_pipeline.py:288-299` 都写出 current input 在前、covered refs 在后。
5. `dayu/host/memory.py:1229-1240` 只消费 parser 已投影的 `compacted_semantics.current_input_ref` 与 `.compacted_source_refs`；生产 Memory consumer 没有索引 raw `source_boundary_refs`。
6. `tests/host/test_context_compact_events.py` 覆盖空、重复、空文本、错误类型、缺字段与“缺少 covered refs”反例；`tests/host/test_memory_projection.py` 覆盖 current input 保留、covered raw 删除、uncovered protected raw 保留、current-only boundary，以及 incremental/rebuild/serialized snapshot 等价。

裁决理由：review 的事实前提“未文档化”不成立。raw index 只在指定 parser owner 内用于解码已明示的位置 contract，随后立即投影成 typed fields；这正是 design 要求的边界，而不是消费者隐式推断。拆字段会成为新的 durable schema 设计，不是修复现有缺陷。

## Aggregate decision

| Finding | Final disposition | Blocking | Fix in PR 190 |
|---|---|---:|---:|
| F-01 readable-view `VNext` names | `deferred-with-owner` | 否 | 否 |
| F-02 remaining `vNext` docstrings | `deferred-with-owner` | 否 | 否 |
| F-03 empty snapshot Protocol | `rejected-with-reason` | 否 | 否 |
| F-04 interactive completion union | `rejected-with-reason` | 否 | 否 |
| F-05 composer/driver phase ownership | `rejected-with-reason` | 否 | 否 |
| F-06 open `intent_type` / `reason` | `rejected-with-reason` | 否 | 否 |
| F-07 `source_boundary_refs[0]` contract | `rejected-with-reason` | 否 | 否 |

**Accepted PR-review code fix remaining：无。**

本 gate 是 no-code resolution：没有 production/test/prompt/manifest/README/design/oracle/scenario change，也没有 fix artifact 或 accepted-finding implementation。

## Validation

### Read-only evidence commands

- `git branch --show-current`
- `git status --short`
- `git merge-base main HEAD`
- `git grep` / `rg`：核对九个名称、所有 `vNext` 文案、Protocol/union/phase 的定义与消费者、free-text 的全部生产消费者、source-boundary writers/parser/typed consumers/tests。
- `git log -S` / `git show main:...`：确认命名债在 merge base 与 2026-06-05 历史 commit 已存在。
- `shasum -a 256`：固定两份初始 review artifact 未修改基线。

### Executed tests and type checks

1. Host owner-level targeted suite：`83 passed in 0.44s`
   - 完整 `tests/host/test_context_compact_events.py`；
   - compact pipeline ordinary raw-tail 两项；
   - Memory source-boundary projection两项；
   - RunInput protected raw-tail 三项。
2. CLI composer/driver targeted suite：`6 passed in 1.41s`
   - submit acceptance、active typeahead phase、queued lifecycle、lost closeout 与 terminal/Enter race；
   - 仅出现依赖包 `edgar` 的 3 条 deprecation warning，与本裁决无关。
3. 受影响模块 pyright：`0 errors, 0 warnings, 0 informations`
   - 覆盖 compact pipeline、RunInput、compact payload、compaction、LLM parser、Context Governance、Memory、composer 与 session execution。

## Changed files and docs decision

- 新增且仅新增：`docs/gateflow/pr-190-pr-review-adjudication-no-code-resolution-20260803-231451.md`
- 两份初始 `docs/reviews/` artifact 保持未修改。
- README decision：无 production/test/public workflow 变更，不触发 README 更新。
- Stage/commit/push：本 artifact 创建阶段均未执行；两路 re-review accepted 后按 Gateflow 进入 accepted PR-review checkpoint 并 push。

## Residual risks and uncovered areas

1. **Readable-view/vNext 命名债**
   - Classification：`assigned to later work unit`
   - Owner/destination：专门的 **Host compaction/readable-view naming-cleanup work unit**。
   - Boundary：一次性处理 `dayu/host/compaction.py` 的 readable-view public names、剩余 docstrings、exports、直接消费者与 owner tests；不得在其它入口加兼容 re-export/wrapper。
2. **PR 无 reported CI checks**
   - Classification：`requiring explicit PR-gate verification`
   - 本轮只运行本地 targeted tests/type checks；没有把“无 reported checks”误分类成代码 finding，也未获授权修改外部 CI 状态。
3. **PR 体量导致的遗漏风险**
   - Classification：`covered by subsequent two-route PR rereview`
   - 本裁决不宣称 targeted suites 等价于两路完整 PR rereview。
4. 两份 review 的其它 Open Questions/Residual Risk 条目没有以独立、证据完整 finding 形式提交，本 artifact 不把它们自动提升为 accepted code fix；后续 rereview 如要升级，必须给出直接 owner/code/test failure evidence。

不存在 unclassified residual risk 或 blocking open question。

## Preservation set for subsequent two-route PR rereview

后续两路 PR rereview 必须原样保留并共同读取以下三个精确路径：

1. `docs/reviews/pr-190-review-20260803-225333.md`
2. `docs/reviews/pr-190-review-20260803-225520.md`
3. `docs/gateflow/pr-190-pr-review-adjudication-no-code-resolution-20260803-231451.md`

初始两份 review artifact 不得被回写；后续 reviewer 应新建各自带时间戳的 rereview artifact，并逐项核对本控制器 disposition 是否仍被当前 head 的直接证据支持。

## Next entry point

- Current gate decision：PR-review adjudication `pass / no-code-resolution`。
- Next entry point：**PR re-review（两条独立路线）**。
- 后续 rereview 的 entry criteria：以当前 PR head、上述三份 preservation artifacts、直接代码/tests 与最新本地/CI validation 为准；不得仅复制本裁决结论。
- 本 artifact 创建阶段未执行 stage、commit 或 push；两路 re-review accepted 后按 Gateflow 进入 accepted PR-review checkpoint 并 push。
