# WU-CTX-01 Slice 1 implementation review Controller adjudication

## 1. Scope

- Work Unit：`WU-CTX-01`
- Gate：Slice 1 implementation review
- Accepted plan base：`ed43bcf2`
- 实现交付：
  `docs/reviews/wu-ctx-01-slice-1-implementation-resume-codex.md`
- AgentMiMo review：
  `docs/reviews/code-review-20260724-035007.md`
- AgentDS review：
  `docs/reviews/code-review-20260724-034122.md`
- Controller 另外按 accepted plan、`docs/host/design.md` §25 与当前 workspace
  diff 做了独立 owner-boundary 复核。

`docs/host/issues-implementation-control.md` 是 Controller-owned diff，不作为
AgentCodex implementation finding。

## 2. Decision

**needs-fix**

Slice 1 的主骨架成立：实际 new Attempt producer 已做到
manifest-before-start，startup/wait/steer/reactive producer 已收口到 strict
candidate/source，direct queue promotion 已删除，5-stage production total function
完整，Slice 2 的 `CONTEXT_BUDGET_EVALUATED` 与 Slice 3 的 usage anchor 均未提前混入。

但 implementation review 不能通过。当前存在 6 个 correctness / durable contract
finding，以及 3 个同 gate 必须清理的低风险 invariant / dead-code finding。尤其是：

1. admission 已冻结实际生效工具事实，但 ordinary/queued dispatch 仍可按当前 opener
   工具集合重选；
2. no-policy 的 post-compact / dispatch-fallback manifest 会错误持久化
   `sizing_stage=ordinary`；
3. continuation 四类 closed unavailable reason 被一个宽泛异常分支压成
   `continuation_tool_schema_unavailable`。

这些不是展示层或测试夹具问题，必须在各自 semantic owner 边界修复，不能添加
consumer fallback、loose parsing、错误文本匹配或 current-config 补偿。

## 3. Accepted findings

### CTRL-IMPL-01（高）：durable effective tool facts 未被 ordinary/queued dispatch 精确消费

直接证据：

- `admission.py::_effective_tool_set_json` 持久化
  `effective_business_tool_names`、`business_bundle_digest`、
  `effective_schema_digest`、`tool_snapshot_ref` 与 `source_refs`；
- `dispatch.py::_selected_tool_names_from_effective_tool_set` 在
  `selector == "all"` 时直接返回 `None`，未读取或校验上述冻结事实；
- `EffectiveToolBundleBuildRequest.selected_business_tool_names=None` 的 contract 是
  “使用全部当前业务工具”，因此 queued Run 在 admission 后若 opener 新增工具，会把
  新工具加入 candidate；相同工具名下 schema 或 source 变化也没有对 admission
  digest 做严格校验。

这违反 accepted plan 的
“initial/queued candidate 使用 current `USER_INPUT_ACCEPTED` strict effective
execution/tool facts”，也违反 frozen candidate 与 actual request 同源要求。

修复要求：

- effective tool set 必须有一个共享 typed strict parser / contract owner，admission
  producer 与 dispatch/steer consumer不得各写一套 shape 解释；
- `selector=all` 只表示 caller 当时的选择意图，不得覆盖 admission 已冻结的
  `effective_business_tool_names`；candidate 必须按冻结后的 exact names 构造；
- 当前 runtime 只能在 business bundle、selected schema、source refs 与冻结 digest
  全部兼容时实现 candidate；任一 drift 必须在 start 前 fail closed，不能改用当前
  “all”、删工具、补工具或重算冻结事实；
- 不为 tests 中缺字段的手写旧 payload 保留兼容解析；fixture 必须迁移到 current
  exact schema。

最低反例测试：

- `selector=all` admission 后当前 runtime 新增工具；
- 相同工具名但 schema 改变；
- subset / none 的 exact names；
- bundle/schema/source ref digest 损坏；
- exact match 正常 dispatch；
- drift 失败后零新 Attempt、零 manifest、零 pending dispatch。

### CTRL-IMPL-02（中）：no-budget dispatch start 丢失真实 sizing stage

直接证据：

- `dispatch.py::_prepare_and_commit_start_in_transaction(..., stage)` 对
  post-compact / dispatch-fallback 已持有真实 `stage`；
- `context_budget_policy is None` 时构造的 `NoBudgetDispatchStart` 不携带 stage；
- `_commit_dispatch_candidate_in_transaction` 对所有 `NoBudgetDispatchStart`
  硬编码 `sizing_stage=ContextSizingStage.ORDINARY`。

因此 no-policy 的 `POST_COMPACT` 或 `DISPATCH_FALLBACK` candidate 会被 durable
manifest 错标为 ordinary。`status=unavailable` 并不允许丢弃 candidate 的真实 stage。

修复要求：

- `NoBudgetDispatchStart` 显式携带 `ContextSizingStage`；
- ordinary caller 传 `ORDINARY`，post-compact / fallback caller 传其真实 stage；
- commit owner 只消费 plan 中的 stage，不从 reason、Run status 或调用点反推。

测试必须覆盖 ordinary、post-compact、dispatch-fallback 三种 no-policy manifest。

### CTRL-IMPL-03（中）：continuation source failure reason 被错误归类

直接证据：

- accepted plan 固定四类 reason 与优先级：
  projection → tool schema → policy → request semantics；
- `engine_ingest.py::_continuation_frozen_sources` 把整个
  `load_prepared_runner_call_source_in_transaction(...)` 包在一个
  `except HostDurableError` 中，并一律返回
  `CONTINUATION_TOOL_SCHEMA_UNAVAILABLE`；
- strict source loader 先读取 Run input policy，随后还会因 manifest/hot identity、
  candidate policy/request semantics 与 tool snapshot 等不同边界失败。

当前实现会把 policy 缺失、request-semantics mismatch 或 source identity corruption
伪装成 tool-schema failure，破坏 closed diagnostic truth。

修复要求：

- failure category 必须由 `dayu.host.run_input` strict source owner 以 typed contract
  产生，或由明确分阶段的 typed loader 产生；
- 禁止在 Engine consumer 按异常 message、调用顺序或 raw payload 猜 reason；
- projection 优先级保持现状；其余三项按 tool → policy → request 的 accepted
  precedence 精确映射；
- 仍禁止从 current config 重建缺失 source。

测试必须逐项制造 projection、tool schema、policy、request semantics 缺失/损坏，
断言 manifest 的唯一 closed unavailable reason。

### CTRL-IMPL-04（中）：strict source loader 未校验 EventLog row 与 hot payload identity 同源

`run_input.py::_find_existing_runner_call_manifest_event` 只按 `run_id/event_type` 查询，
然后按 hot payload 内的 `attempt_id/execution_id` 选择 event；它没有校验
`EventLogRow.attempt_id/execution_id` 与 caller identity、hot identity 一致。

EventLog row 是 canonical fact identity owner，hot payload 是同一事实的 inline
projection。两者不一致时 strict loader 必须 fail closed，不能只相信 hot payload。

修复要求：

- 精确校验 event row 的 session/run/attempt/execution/type 与 caller、source Run 和
  hot payload 一致；
- corruption test 必须覆盖 row identity 与 hot identity 交叉错配，且不能误选另一
  Attempt 的 manifest。

### REVIEW-IMPL-05（中）：5-stage/15-cell owner test 缺少 CONTINUATION 三格

AgentMiMo finding 04 与 AgentDS finding 02 交叉成立。

`tests/host/test_context_budget.py` 只冻结 4×3=12 cells，缺
`CONTINUATION × normal/soft/hard`，docstring 也仍写 4×3。补齐三格并改为 5×3；
另加 unknown stage/pressure fail-closed 反例时不得用生产兼容分支放宽类型。

### REVIEW-IMPL-06（中）：compactor proposal 可解析 COMPLETE sizing snapshot

AgentDS finding 03 成立。

`_validate_sizing_snapshot` 的 UNAVAILABLE 与 NOT_APPLICABLE 分支校验
`runner_call_kind`，COMPLETE 分支却直接返回。因此损坏或错误 producer 可以让
`compactor_proposal` 携带 COMPLETE sizing。

manifest parser 必须拒绝该组合，并有正反 contract tests。compactor proposal 只能是
NOT_APPLICABLE；dispatch-relevant runner call 不能是 NOT_APPLICABLE。

### REVIEW-IMPL-07（低）：删除本轮新增但未使用的 source policy loader

AgentMiMo finding 02 成立。

`engine_ingest.py::_source_policy_snapshot_in_transaction` 是本轮新增的零 caller
第二加载路径，reactive recovery 已消费 strict source candidate 的 policy。删除该
helper 与仅为它保留的 imports/constants，避免形成第二 semantic owner。

### REVIEW-IMPL-08（低）：删除 admission 层无 caller 的 direct-running wrapper

AgentMiMo finding 01 的运行时严重度被高估，但维护性事实成立。

`admission.py::_create_running_admission_result` 当前零 caller，且若未来接入会绕过
scheduler governance 与 manifest-before-start。删除该 admission wrapper；不要为其
增加“未来预留”manifest 分支。底层
`create_running_run_with_starting_attempt_in_transaction` 是否在后续 work unit 删除
保持 residual risk，本 gate 不扩大到无关低层测试基础设施清理。

### REVIEW-IMPL-09（低）：同步 estimator digest docstring

AgentMiMo finding 06 成立。`BudgetEstimate.estimator_digest` 已不包含 policy
payload，docstring 必须改为真实的 estimator contract / input / constants 语义。

## 4. Rejected or deferred findings

| Finding | 裁决 | 理由 |
| --- | --- | --- |
| AgentMiMo 03：`source_boundary_refs` 首位缺位置校验 | rejected-as-not-actionable | parser 已通过 `_required_unique_text_list(..., allow_empty=False)` 保证非空、非空文本与唯一性；当前 schema 的业务语义本来就是首位编码 `current_input_ref`，payload 内没有第二个独立真源可供比较。增加 `assert len >= 1` 是重复校验，改 key-based schema 是超出本 Slice 的新 schema 设计。 |
| AgentMiMo 05：COMPLETE 内冗余 `None` 判断 | rejected-style-only | 前置完整性 guard 与后续范围 guard 的显式 narrowing 不改变语义，也未形成错误路径。 |
| AgentMiMo 07：hard closeout docstring 未解释另两 stage | rejected-style-only | docstring 已声明接受的 closed 三阶段；reactive/continuation hard=allow 由 15-cell owner contract 负责，不需要在不接收它们的 helper 重复承诺。 |
| AgentMiMo 08：`cast` 应改 assert | deferred-non-blocking | dependent optional atoms 已由 `_ContinuationFrozenSources` closed construction path 与 unavailable guard 约束；可在修 CTRL-IMPL-03 时自然改成 typed complete variant，但不能只用 assert 掩盖 reason 分类问题。 |
| AgentMiMo 09：recovery `CAS_LOST` 无显式分支 | rejected-as-unreachable | `start_recovery_run_with_starting_attempt_in_transaction` 对底层非 UPDATED mutation 调用 `_require_run_mutation_updated`，CAS_LOST 以 `HostDurableError` 抛出，不会作为 result status 返回。 |
| AgentDS 01：单 Run CAS miss 不应整 page rollback | rejected-conflicts-with-plan | accepted plan §5.3.1 与反例矩阵明确要求 startup valid CAS miss 使当前 recovery page transaction 整体 rollback、page 零 wake；在同 transaction 内普通返回会 commit 已写 manifest。 |
| AgentDS 04：wait helper 的 PayloadStore 可能为 `None` | rejected-as-false | `HostAdmissionService.payload_store` 与构造参数均为非 optional `PayloadStore`；admin handle 也持有该 primitive，真正 execution gate 是已存在的 optional memory policy 检查。 |
| AgentDS 05：局部 `PayloadStore()` 必须改注入 | rejected-style-only | `PayloadStore` 是无状态 durable primitive，局部构造没有第二配置或状态真源。若未来 primitive contract 改为有状态，应由该 primitive 的装配 work unit 统一迁移。 |
| AgentDS 06：startup rollback signal 不应继承 `HostDurableError` | rejected-conflicts-with-public-scan-contract | 该信号必须穿出 page `run_write` 以保证整页 rollback；scanner 的 declared failure contract 正是 `HostDurableError`。不能为了与另外两个局部 catch signal 外形一致而改变传播语义。 |
| AgentDS 07：两个 sizing factory 应立即自校验 | rejected-no-observable-gap | 两个 factory 固定构造 closed atoms，唯一 durable serializer 在写入前统一执行 strict validation；当前不存在构造与持久化之间消费未校验字段的路径。 |

## 5. Fix gate acceptance

AgentCodex 修复后必须：

1. 提供新的 fix artifact，逐项映射 CTRL/REVIEW-IMPL-01..09；
2. 运行受影响 focused tests；
3. 运行 full Host tests；
4. 运行 full pyright，保持 `0 errors, 0 warnings`；
5. 重新执行 changed production files 单文件覆盖率审计，保持每个 `>=80%`；
6. 运行 `git diff --check`、Slice 2/3 越界 symbol grep、direct-promotion stale
   symbol grep；
7. 按 README trigger 复核 Host/tests README；
8. 保留 optional real compactor smoke 与 Gemini quota 作为 residual risk，不得伪造
   已执行证据。

修复完成后进入双路 implementation re-review；通过前 workspace production/tests
仍为 **not accepted**，不得提交 protected implementation commit。
