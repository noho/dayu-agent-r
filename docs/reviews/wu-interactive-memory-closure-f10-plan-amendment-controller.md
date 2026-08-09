# Interactive Conversation Memory closure F10：Implementation plan amendment

## 触发原因

F10 implementation 的 operation root guard 发现 accepted plan 中“selected block IDs 与 root compact boundary/provenance 同源”无法由现有字段诚实证明：`TurnGroupMembership` 只有 group id 与 block ids，`CompactMaterialPack` 只有 prompt-local label 到 canonical refs，二者之间缺少 block identity 到 packed boundary 的 canonical bridge。数量比较、解析 block id、依赖 label ordinal 或测试特例都不是 owner proof。

这不是 frozen oracle、Host design truth 与实现无法兼容；它是原 plan 对内部 typed contract 的字段规格不足。产品语义、v2 LLM input/output schema、五类 Memory、fallback policy 和 durable accept owner 均不改变。

## 总控裁决

### 1. 允许最小 Host-internal selected-block provenance binding

在 `dayu/host/compaction.py` 增加最小 frozen strict type `SelectedBlockProvenance`，只承载：

- `block_id`：selection 内部 block identity；
- `canonical_source_refs`：由对应 `RunInputMaterialBlock` 直接提供的非空 canonical refs；
- `packed_content_digest`：该 source block 投影为 `CompactMaterialPack` block 后，pack 中业务可读文本的 canonical digest。该值由 compact-material owner 的单一 helper机械派生：普通 trace/answer block 使用其 packed text digest；accepted tool evidence 使用 `CompactEvidenceBlock` 实际持有的 `result_text` digest，而不是 `RunInputMaterialBlock` 四行 evidence render 的 digest。同一 helper同时供 provenance producer与pack builder使用，禁止两处各自重算不同语义。

`CompactSegmentSelection` 增加按 stable material order 排列的 `selected_block_provenance`，并满足：

- provenance block ids 与 `selected_block_ids` 精确一一对应且顺序相同；
- refs 非空、每项唯一且不从 prompt label、ordinal、字符串化 block id 或下游 EventLog 反推；`packed_content_digest` 非空且与最终 pack block 的 existing `content_digest` 同源；
- root selector 从同一 `RunInputMaterialBlock` source snapshot 机械产生；transient pass 只取 root proof 的对应子集并继续绑定 `root_selection_digest`；
- canonical serialization 与 selection/request digest 包含该 proof；它只进入 Host-internal durable request/manifest，不进入 `CompactionRequest.llm_material_json()`、repair feedback LLM projection或 v2 output schema。

pipeline 在仍拥有 source snapshot 时验证 proof；operation 在 provider 前和 durable accept 前，将 proof 与 material pack 中实际 selected trace/evidence/answer blocks 的 canonical refs + packed content digest 做精确一一匹配。current input anchor与 previous compacted view 不冒充 selected history block。unknown id、等数量替换、完整 group swap、ref/digest 不一致均 fail closed，provider不调用或不得 durable accept。

`_single_block_segment_selection` 必须按 block id 从 root `selected_block_provenance` 精确取一个 entry，不允许重算或接受外部值。`_operation_pass_requests` 必须逐 pass 验证 transient provenance 是 root provenance 的精确子集：block id存在于root，refs与packed digest逐字段相等，所有pass合并后对root selected proof无重叠、无遗漏；每个pass还要在provider前验证其proof与自身material pack一致。

该类型不是 public schema、compatibility wrapper、root-proof facade 或 God helper；它是 accepted plan 已要求的同源不变量所缺少的最小 canonical fact。

### 2. 修复相同文本、不同 canonical ref 的错误去重

`dayu/host/compact_material.py` 的 packer 不再拥有 selected history/current-input dedup：`_selected_material_blocks` 对 selector 已选 block 必须一项不漏地投影，不得 `continue` 删除任何 group member。不得因 content digest 相同而删除 canonical refs 不同的历史 user input。若 source snapshot 意外让与 current input anchor 相同 canonical ref 的 history block进入 selected boundary，pipeline source/request validation 必须在pack/provider前 fail closed；不得把它当作pack阶段可静默删除的重复。新增 owner tests：

- 历史 user input 与 current input 文本相同但 event refs不同，完整 user/evidence/final group仍进入 pack与proof；
- selected history与current anchor canonical ref相同，pipeline fail closed且provider不调用；
- packer对任何合法selected ids保持数量和stable order一一对应。

### 3. 收紧 selection 的真实不可变性

`excluded_reason_codes` 是 selection digest 与 root proof 的组成部分，不得在 frozen dataclass 构造后继续变异。`CompactSegmentSelection.__post_init__` 必须先按 block id key稳定排序复制，再以真正只读的 mapping view保存；selection digest构造与 `to_json()` 都消费相同的sorted canonical mapping。保持现有 read-only `Mapping[str, str]` contract与 canonical JSON形状，不新增 alias/default/compat。测试断言不同input insertion order得到相同stored order/JSON/digest，外部原 mapping后续变更和对字段直接变更均不能改变 selection内容或digest。

### 4. Scope amendment

保持既有 F10 production owner files不变；新增/继续允许的测试仅为：

- `tests/host/test_compaction_contract.py`
- `tests/host/test_public_compact_smoke.py`

它们只迁移双 digest strict contract与验证LLM投影不泄漏治理 digest。新的 provenance/duplicate/immutability测试仍优先落在原计划的 compact material、pipeline、operation owner suites。

## 禁止事项

- 不修改 compactor v2 input/output LLM schema或 Memory/RunInput消费者。
- 不把完整 source snapshot塞入 request，不新增下游重算、字符串解析、数量代理或 compatibility fallback。
- 不让 governance digest/provenance bridge进入LLM-facing文本。
- 不改三份 frozen baseline，不运行五条正式 CLI scenarios。

## 成功信号

- unknown selected id、same-count swap、whole-group swap、canonical ref/packed-digest mismatch以及transient proof篡改在provider前fail closed；无accepted artifact/Memory/terminal分叉。
- same-text/different-ref completed Run不再被pack单独截断。
- root/transient proof、strict bounded selection、feedback双digest与single terminal既有测试继续通过。
- 全量Host/pytest最终不存在未分类deterministic failure；F09 fixture consumer若受已接受F09 contract影响，须在aggregate fix按其真实owner迁移，不能归类为existing而遗留。
