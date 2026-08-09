# Interactive Conversation Memory closure F08–F10：aggregate deepreview fix/audit

## Gate identity

- Gate：Gateflow aggregate deepreview fix。
- Work unit：Interactive Conversation Memory closure F08–F10。
- Review range：accepted plan checkpoint `68ba403811fe98835ea93f8c715ca8ed7ba26164` 至 accepted F10 commit
  `fd15b6601a985c538cdbe6a529af99d07c281a05`。
- Review inputs：
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-deepreview-ds.md`
- 执行者：AgentCodex；本 artifact 是对两路 durable review 的独立逐项裁决，不以 reviewer 的 PASS 代替代码证据。
- 总结论：MiMo PASS 成立；DS 的 cross-slice PASS 结论成立；DS 三项 nonblocking finding/observation 均
  `rejected-with-reason`，没有 accepted contract gap，不修改 production/tests，不扩大 schema/public surface。
- 当前状态：aggregate deepreview fix 完成，停在 aggregate re-review handoff。
- 本 gate 未 commit、未运行五条正式 CLI scenarios。

## 第一性原理与 owner 边界

本 gate 的判断标准是：是否存在当前正式 producer/call path 中能够改变 durable semantic set、越过 provider 前
guard，或造成 F08/F09/F10 truth 分叉的可复现反例。仅证明 operation 没有重复 pipeline 的 raw snapshot 知识、
policy helper 当前为闭集，或无状态 primitive 没有注入 seam，不构成 correctness finding。

当前 owner 分层是：

1. compact-material 从 accepted compact event 机械生成并原子校验 previous blocks/readable view pair；previous 是稳定
   compacted memory，不是本轮 raw delta selection。
2. pipeline 持有 frozen source snapshot，负责 selected `block_id -> refs/final-pack digest` exact identity、root partition
   与 transient source-snapshot identity；tier 2/3 只能通过 typed keep/drop transform 改变 previous pair。
3. operation 不持有 raw snapshot，负责 root/transient exact partition、每 pass selected pack multiset、完整
   `CompactInputV2.source_boundary` 与 candidate binding，以及 single durable terminal。
4. Host context policy 拥有 compact 后 hard-threshold acceptance；PayloadStore 是 transaction-less durable primitive，
   manifest recorder 拥有同一 transaction 内 descriptor/EventLog identity 装配。

## DS-A：previous_compacted_view 不属于 selected_block_provenance

**裁决：`rejected-with-reason`。** Review 的机械观察成立——`_validate_operation_selected_pack` 只比较
trace/evidence/answer selected pack；但其前提“selected proof 可能包含 previous”与当前 contract 和所有 production producer
直接矛盾。

直接证据：

- `initial_segment_selection` 的 selected ids 固定只来自 trace/evidence/answer；每个 previous label 被固定写入
  `excluded_reason_codes`，reason 为 `previous_compacted_view`。因此 previous 从未进入 selected proof。
- normal/tier selection 只消费 `source_snapshot.material_blocks`（raw delta）；previous 在
  `CompactPipelineSourceSnapshot.previous_compacted_view` 中是独立字段。pipeline 从 raw snapshot 重建并逐字段比较
  `SelectedBlockProvenance`，root 还要求 selected/excluded 对 raw snapshot 无重叠、无遗漏。
- previous blocks/readable view 在 `validate_previous_compacted_view_pair` 中校验 presence、kind、label、数量与文本 exact
  pairing；正式来源是 latest accepted `CONTEXT_COMPACTED` candidate 的机械映射。tier recovery 只调用
  `transform_previous_compacted_view_pair_for_recovery` 做完整 item keep/drop，不改写 semantic text。
- `CompactionRequest.compact_input` 按 previous、trace、evidence、answer 的最终 pack 机械生成完整 source boundary；
  `_validate_operation_root_request` 要求全部 pack labels 与该 boundary 顺序精确一致。accepted truth 随后对同一完整
  `CompactInputV2` 做 source-boundary exact binding。
- `_validate_operation_selected_pack` 的 proof domain 刻意只覆盖本轮 raw selected delta；把 previous 加进去会让每个合法
  带 previous 的请求出现 `len(proof) < len(pack)` 假阳性，并把 stable memory 冒充 raw selected block。

反例审计：

1. 交换/篡改 raw selected block 的 refs 或 digest：pipeline snapshot exact proof 或 operation selected-pack multiset 在
   provider 前失败，已有 whole-group swap、unknown id、refs/digest mismatch owner tests。
2. 在 transient pass 中把 previous 或 selected source 重复/遗漏：operation 的 pass boundaries 必须对 root boundary
   无重叠、无遗漏精确二分；selected proof 还必须是 root per-block-id exact subset。
3. 只伪造一个自洽的 previous pack、readable view、provenance map 与由该 pack 派生的 boundary：手工绕过 private pipeline
   producer 可以构造另一份完整 request，但 operation 没有 durable source snapshot，无法区分“合法 request”与“整体伪造的
   合法 request”。这不是 provider 前漏掉的内部 mismatch，而是把未授权 caller 当成 source owner。若让 operation 重新读取
   accepted EventLog 或接收完整 snapshot，恰好会复制 pipeline/material owner并扩大 request contract。

因此没有找到“由当前正式 producer 产生、改变 durable semantic set、同时通过 provider 前校验”的反例；不扩展
`SelectedBlockProvenance`，不把 previous 加入 selected multiset，也不新增固化错误 domain 的测试。

## DS-B：_requires_budget_acceptance 当前恒真

**裁决：`rejected-with-reason`。** 这是既有 accepted Host hard-threshold contract，不是 F08–F10 引入的死分支或待实现
conditional。

`git blame` 与 line history 的直接证据：

- helper 本身早于 F08–F10 存在；commit `bd1d3e94c571e0b98096e9cfa4d169cefd8003c9`
  （2026-07-20，`WU-SEMANTIC-OWNERSHIP-01: align implementation with design truth (#179)`）把旧的
  `return request.trigger_source is PROACTIVE` 明确改为 `del request; return True`。
- 同一变更的 docstring 明确：compaction owner 必须在接受 candidate 前统一执行 hard threshold 验收，proactive 与
  reactive 都不能把仍明显越界的输出交给 dispatch/Engine loop。
- 该 truth 早于 accepted F08–F10 plan checkpoint `68ba4038`，本 work unit 没有授权削弱或重新条件化它；当前 operation
  对 hard-threshold rejection/repair 的 owner tests 保持通过。

删除 helper、改成 trigger conditional，或标注“future optional extension”都会暗示存在绕过硬闸门的合法路径。当前函数名
表达的是 Host policy requirement，参数保留 request-level policy seam；无 correctness 或维护性收益足以支持本 slice 改动。

## DS-C：manifest recorder 内建 PayloadStore

**裁决：`rejected-with-reason`。** 当前实现符合 Host recorder owner 装配和同类模式，不存在 F09 identity 分叉。

直接证据：

- `PayloadStore` 文档与实现明确其不持有连接、不创建 transaction；方法只把调用方传入的 `HostTransaction` 与 typed
  request 委托给 durable payload primitive。实例没有 constructor state、缓存或 identity counter。
- 同类 `DurableRunnerCallManifestRecorder` 同样在 recorder 内创建 `EventLogStore()` 与 `PayloadStore()`；需要共享外部
  state 的 Host providers 才使用注入。这里的 transaction、artifact policy、payload ref/digest 都由调用参数/descriptor
  决定，不由 `PayloadStore` 实例身份决定。
- F09 diff `47b6a2af..d04f7531` 没有引入该内建实例；它只把同一 `manifest_descriptor.payload_ref` 与同一
  `manifest_digest` 填入 canonical EventLog row，并从同一 projection descriptor 填充 manifest/hot projection triple。
- recorder 在一个 `run_write` transaction 内先写 projection descriptor、再写 manifest descriptor、再 append EventLog；
  hot payload、row descriptor 与返回的 `CompactorProposalManifestReference` 全部复用这两个 descriptor 的同源值，没有
  第二个 store-derived identity。

增加 optional `payload_store` 参数会扩大 constructor/public seam、产生默认/注入双装配路径，却不能修复任何当前 identity
问题；“未来可能有状态”不能替代当前直接证据。故不做接口扩张、不新增 mock-oriented test。

## MiMo PASS 与 DS cross-slice 结论复核

| 审计项 | 独立结论 | 直接证据摘要 |
|---|---|---|
| F08 summary null/meaningful | PASS | prompt 明确 meaningful/null；governance 接受合法 null；memory projection 已有 prior-non-null → null 清除 owner test |
| F09 manifest identity | PASS | projection/manifest descriptor、hot atoms、EventLog row与 formal resolver 使用同源 ref/digest/size；mismatch fail closed |
| F10 atomic selection/budget | PASS | collective exclusion 后按 turn-group atomic unit strict prefix；首个 oversized 不越 cap、不拆组、不跳过；raw snapshot保留 |
| root/transient proof | PASS | pipeline snapshot exact proof；root raw partition；operation pass per-id exact subset、无重叠遗漏、完整 boundary partition |
| repair binding | PASS | request digest + source-boundary digest 双绑定；root→root保留，root/tier/boundary变化清空；governance digest不投影给 LLM |
| durable terminal/race | PASS | operation 仅 aggregate root产出 accepted truth；dispatch terminal CAS拒绝 multiple；stale/late结果 fail closed |
| Memory/RunInput/artifact fork | PASS | accepted compact EventLog 是 memory 单向真源；post-compact re-freeze 使用最新 snapshot；sizing/manifest digest校验 |
| compat/schema/public drift | PASS | 无 alias、optional shim、旧 digest fallback或下游补偿；proof字段保持最小 Host-internal surface |
| LLM governance leakage | PASS | material/repair projection剥离 canonical refs、digest、cursor与 provenance map |
| ownership/maintainability | PASS | 单一 `_packed_content_digest`；无新增 God helper、反向依赖或重复 semantic owner |

MiMo 的全部 PASS 项与当前代码/owner tests一致。DS 对 F08 null flow、F09 所有真实 prepared runner-call paths、
stale/late/double terminal、identity mismatch、LLM leak、Memory/RunInput/artifact fork、compat/schema drift 与 God helper 的
cross-slice PASS 结论也成立；其三项观察不改变 aggregate PASS。

## Changed files 与 README/design trigger

本 fix gate 不修改 production、tests、Host stable design 或 README；只新增本 durable fix artifact。F08–F10 accepted diff 已在
`docs/host/design.md`、`dayu/host/README.md` 与 `tests/README.md` 记录稳定事实。本 gate 没有新增 contract、测试分层或用户
工作流变化，因此 README/design trigger 未再次命中。

## Validation

- F08–F10 focused suite（11 files）：`489 passed, 1 skipped in 8.30s`；skip 为 opt-in real provider smoke。
- focused coverage suite（10 Host files）：`418 passed, 1 skipped in 5.68s`。
  - `dayu/host/compact_material.py`：86%
  - `dayu/host/compact_pipeline.py`：92%
  - `dayu/host/compaction.py`：84%
  - `dayu/host/compaction_operation.py`：86%
  - `dayu/host/context_governance.py`：89%
  - `dayu/host/dispatch.py`：83%
  - 六文件合计：85%；所有单文件均 ≥80%。
- 全仓 pytest：
  - 首轮：`6638 passed, 10 skipped, 6 deselected, 1 failed in 222.22s`；唯一失败为
    `test_open_host_active_cancel_watchdog_public_watch_observes_cancelled`，观测同一 opener thread 上 token cancel 两次而
    断言只允许一次。
  - 隔离：该 node 首次单跑通过，随后循环 5 次全部通过（合计 6/6 green）。仓库未安装 `pytest-repeat`，一次
    `--count=5` 调用因参数不可识别退出 4；未执行测试，不计产品验证失败。
  - 第二轮全仓：`6639 passed, 10 skipped, 6 deselected in 226.89s`，完整绿色。该现象分类为不在 F08–F10 diff 的
    active-cancel watchdog 非确定性时序观测，不是本 work unit regression，也没有用“existing failure”掩盖。
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- 精确 Ruff：对 `68ba4038..fd15b660` 的 17 个 changed Python files 执行 `ruff check`，通过。
- compileall：`python -m compileall -q dayu tests utils`，通过。
- JSON：`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、
  `docs/cli_init_workspace_manifest_v1.json` 均通过 `python -m json.tool`。
- `git diff --check 68ba4038..fd15b660`：通过。
- frozen digest：
  - `docs/cli_ci_oracles.json`：`da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
  - `docs/cli_ci_scenarios.json`：`7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
  - `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：
    `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`
- 五条正式 CLI scenarios：按 gate 约束未运行。
- Git：未 commit、未 push。

## Residual risk disposition

- DS-A/B/C：均为 `rejected-with-reason`；不是 deferred correctness risk，不需要 future compatibility owner。
- active-cancel watchdog 首轮时序观测：已由 6 次隔离通过与第二轮完整全仓通过覆盖；若未来重复出现，应由
  `open_host` active-cancel runtime/test owner 单独立项，不在 F08–F10 semantic closure 内修改。
- 五条正式 CLI scenarios 与真实 provider evidence：`covered by later approved evidence/readiness gate`。
- aggregate re-review：`covered by current Gateflow next gate`。

没有 unclassified residual risk，没有 blocking open question。

## Completion status

Aggregate deepreview fix/audit 完成；无需生产或测试修复。当前停在 aggregate re-review handoff，等待独立复审；不提交。
