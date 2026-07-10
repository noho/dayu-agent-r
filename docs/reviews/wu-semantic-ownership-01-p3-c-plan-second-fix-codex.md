# WU-SEMANTIC-OWNERSHIP-01 P3-C second plan-fix（AgentCodex）

## Gate metadata

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-C`。
- Gate：second plan-fix only。
- Timestamp：`2026-07-10T16:56:10+08:00`。
- Target：`docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`。
- Design sources：`docs/host/design.md` 第 23-25 节、`docs/engine/design.md` 第 1、4、
  14、15 节。
- Re-review inputs：
  - `docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-controller-adjudication.md`
- Current-code evidence：`dayu/host/compact_pipeline.py`、`dayu/host/run_input.py`、
  `dayu/host/compaction.py`、`dayu/host/compact_material.py`、
  `dayu/host/llm_compaction.py`、`dayu/host/compaction_operation.py`、
  `dayu/host/context_budget.py`。
- Write scope：只修改 target plan，并新建本 artifact；未修改生产代码、测试、control
  doc、既有 review artifacts、README 或其它未跟踪文件，未 commit。

## 第一性原理与 owner boundary

五项修复动机均成立。它们不是文案润色，而是 implementation 是否能在正确 owner
boundary 一次完成的必要条件：compact artifact 的 message projection 应在 concrete view、
raw-tail protocol 和所有 material builder 同时消失；typed evidence 的 component value 必须
直接来自 typed material，不能从最终 renderer 反解析；已决定删除的 string-wire helpers 和
false-owner dead constants 必须有可执行的零匹配 acceptance criterion。

owner boundary 保持不变：accepted compact 业务语义由 typed compact payload 读取并分别
投影到 Conversation Memory 与 next-compactor typed pair；ordinary RunInput 只从 memory
得到 accepted compact LLM material。Compact artifact view 只保存 event/artifact/evidence
provenance，protected-raw-tail protocol 只读取其所需的 artifact ref/digest。Accepted evidence
由 `AcceptedToolResultProjection.llm_material` 产生 component truth，唯一四字段 renderer
只产生最终 `block.text`。Budget ordinary-dispatch owner 是 `context_budget`；无消费点常量
不是第二 owner。

## Finding status

| Finding | Status | Plan locations |
|---|---|---|
| `P3-C-RR-PF-01` | fixed | 3.7、4.2、6.4、S2、9、10.1 |
| `P3-C-RR-PF-02` | fixed | 3.7、4.2、6.4、S2、9、10.1 |
| `P3-C-RR-PF-03` | fixed | 3.7、4.2、6.6、S3、10.2 |
| `P3-C-RR-PF-04` | fixed | 3.7、4.2、S2、9 |
| `P3-C-RR-PF-05` | fixed | 3.7、4.2、6.5、S2、9、10.1 |

## P3-C-RR-PF-01 — fixed

直接证据：

- `compact_pipeline.py:147-184` 的 `CompactPipelineCompactArtifactView` 当前声明
  `messages`、artifact ref/digest 和 represented evidence refs。
- `_DurableProtectedRecentRawTailProvider.load_ordinary_raw_tail()` 通过该 protocol 接收
  compact view；其 selection/validation path 在 `run_input.py:1410,3318-3333` 实际只读取
  artifact ref/digest。
- concrete `CompactArtifactView` 当前在 `run_input.py:424-437` 定义 `messages`；如果只删
  concrete 字段而不改 protocol，`run_input.py:1920-1925` 的 structural subtype 传参会被
  pyright 拒绝。

Plan 改动：

- 6.4 与 S2 同步删除 concrete/protocol 的 `messages`。
- raw-tail protocol 进一步收窄为实际消费的 artifact ref/digest；represented evidence refs
  留在 concrete view 给 accepted evidence 去重等直接消费者，不进入该 protocol。
- concrete view 允许额外携带 compaction event ref、represented refs，继续满足 structural
  subtype；明确禁止 adapter/facade 和 generic bag。
- validation 增加 protocol scoped scans，并要求 pyright/focused tests 证明 structural
  subtype。

## P3-C-RR-PF-02 — fixed

直接证据：

- `RunInputBuilder.build()` 当前在 `run_input.py:1937` 拼接 `*compact.messages`。
- `build_run_input_material_blocks()` 当前在 `run_input.py:2518-2530` 另有完整 loop，把
  `compact.messages` 生成为 `block_id="compact:*"` 的 `SESSION_SUMMARY` material block。
- 删除该 loop 后 helper 内不再有其它 compact 消费点。

Plan 改动：

- 6.4 与 S2 明确删除从 `compact_source_ref` 到整个 loop body，不等待 source scan 补漏，
  不保留空迭代、占位 block 或 compatibility branch。
- 同步从 helper 签名与 call sites 删除失去 material 职责的 `compact` 参数。
- provenance 仍由 builder 持有的 concrete compact view 用于 event-ref equality、protected
  raw-tail selection、represented-evidence 去重、runner-call manifest 与 audit；不再产生
  material block。
- S2 tests 明确断言没有 `compact:*` block，但上述 provenance consumers 仍工作。

## P3-C-RR-PF-03 — fixed

直接证据：

- `CompactEvidenceBlock` 当前字段在 `compaction.py:443-460` 为
  `readable_tool_name/readable_query_text/raw_result_text/readable_source_text`。
- `EvidenceReadableItemVNext` 当前在 `compaction.py:956-995` 使用 `response_text`。
- 当前 `compact_material.py:2745-2758` 把 `RunInputMaterialBlock.text` 填入
  `raw_result_text`，而 planned `block.text` 将变为完整四字段 renderer；若继续沿用该取值
  会把 renderer 全文污染结果分量。

Plan 改动：

- 6.6 增加 exact no-rename table：
  - `CompactEvidenceBlock.readable_tool_name <- material.tool_name`
  - `CompactEvidenceBlock.readable_query_text <- material.query_text`
  - `CompactEvidenceBlock.raw_result_text <- material.result_text`
  - `CompactEvidenceBlock.readable_source_text <- material.source_text`
  - `EvidenceReadableItemVNext.response_text <- material.result_text`
- target fields 不重命名；`block.text` 只等于 shared 四字段 renderer，永不作为 component
  field 的 value source 或 parse source。
- S3 tests 与 propagation audit 分别验证 component equality 和 renderer/component 分离。

## P3-C-RR-PF-04 — fixed

直接证据：

- `compact_material.py:3229-3354` 当前存在主
  `_previous_compacted_view_vnext()` 以及 session summary、fact、answer anchors、forward
  intents、references 五个 `_previous_compacted_*_vnext()` helper。
- 原 plan 只在 exact changes 点名删除，source scans 未覆盖该函数族；遗漏 dead helper 时
  acceptance 不会失败。

Plan 改动：

- 9 节加入显式函数名集合 scan，覆盖主函数与五个子函数，预期零匹配。
- S2 completion/validation 将该 scan 作为 hard acceptance criterion；不依赖未使用代码
  检查的间接信号。

## P3-C-RR-PF-05 — fixed

直接证据：

- 精确 `rg` 只在 `llm_compaction.py:92-97` 找到
  `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`、`_POST_COMPACT_BASE_MESSAGE_COUNT`、
  `_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT` 的定义，没有任何消费点。
- `compaction_operation.py:69,1493` 的同名 base count 有真实 ordinary post-compact budget
  消费；这才是迁到 `context_budget` 的语义。

Plan 改动：

- 纠正 6.5、S2、validation、residual risk 中把 `llm_compaction` 私有常量描述为当前
  proposal-budget owner 的 false claim。
- 将 `llm_compaction.py` 加入 S2 allowed production files，仅原地删除上述三个定义；不
  移动、re-export、alias 或保留为第二 owner，也不扩展为 broad dead-code cleanup。
- 9 节增加三个名称的零匹配 scan；`context_budget.POST_COMPACT_BASE_MESSAGE_COUNT` 仍是
  唯一 ordinary post-compact owner。

## Controller follow-up — llm_compaction coverage closure fixed

Follow-up status：fixed。

直接证据：

- S2 已把 `dayu/host/llm_compaction.py` 列为实际修改 production file，但原 aggregate
  coverage command 没有 `--cov=dayu.host.llm_compaction`，逐文件验收也没有显式
  `python -m coverage report --include='dayu/host/llm_compaction.py' --fail-under=80`。这会让
  三个 dead constant 删除在没有该修改文件 coverage gate 的情况下通过，违反 AGENTS.md
  的逐文件 `>=80%` 约束。
- 仓库实际存在 `tests/host/test_llm_compaction.py`；该文件直接 import
  `dayu.host.llm_compaction`，覆盖 source guard、safe outcome、typed proposal parsing、
  prepared compactor input、runner outcome 等 owner path。
- 现有 aggregate matrix 中的 `tests/host/test_public_compact_smoke.py` 只通过 monkeypatch
  局部触达 `dayu.host.llm_compaction._run_agent_request`，没有直接证据证明单靠原 matrix
  能把整个模块推到 80%。因此不能把 smoke 当成该模块 owner coverage test。

Plan 改动：

- 将真实存在且最直接的 `tests/host/test_llm_compaction.py` 加入 S2 allowed tests、S2
  focused commands 与 S3 后 aggregate affected matrix；未凭空命名测试文件。
- aggregate coverage collection 增加 `--cov=dayu.host.llm_compaction`。
- 逐文件验收显式增加
  `python -m coverage report --include='dayu/host/llm_compaction.py' --fail-under=80`；aggregate
  数字不能替代该文件 gate。
- 三个 implementation slices、PF-01 至 PF-05、首轮 closure 与其它 scope 全部保持不变。

## Preserved closure and scope

- 首轮 `P3-C-PF-01` 至 `P3-C-PF-06` 与三个 residual observations 的 plan closure 全部
  保留。
- Implementation slices 仍为三个：S1 typed compact -> memory；S2 typed pair / ordinary
  RunInput / budget；S3 typed evidence / renderer / typed mismatch。
- 未新增 compatibility、adapter/facade、callback、factory、lazy import、schema migration、
  caller override、unknown fallback 或 Tool Trace refactor。
- 本 gate 未进入 implementation、第二轮 re-review、commit、push 或 control-doc 更新。

## Propagation audit

Compact semantic/provenance path：

```text
CONTEXT_COMPACTED accepted candidate
  -> typed compact payload
  -> Conversation Memory snapshot -> ordinary RunInput compact business material
  -> compact pair projector -> next compactor typed previous view

CONTEXT_COMPACTED event/artifact/evidence provenance
  -> concrete CompactArtifactView
     -> event-ref equality / protected raw-tail ref+digest validation
     -> represented-evidence dedupe / manifest / audit
  -X-> CompactArtifactView.messages
  -X-> build_run_input_material_blocks compact material block
```

Evidence path：

```text
AcceptedToolResultProjection.llm_material
  -> exact component mapping -> CompactEvidenceBlock / EvidenceReadableItemVNext
  -> shared four-field renderer -> RunInputMaterialBlock.text
```

component fields 和 renderer text 从同一 typed material 派生，但 renderer text 不反向成为
component truth。Durable provenance、audit 与 LLM-facing projection 因此不会出现“显示正确
但持久化/typed component 错误”的分叉。

## Validation

- controller follow-up 后重跑 `git diff --check`：pass（exit 0，无输出）。
- controller follow-up 后重跑 untracked plan no-index whitespace check：pass（无
  whitespace diagnostic；exit 1 仅表示与 `/dev/null` 存在内容差异）。
- controller follow-up 后重跑 untracked second-fix artifact no-index whitespace check：pass
  （无 whitespace diagnostic；exit 1 仅表示与 `/dev/null` 存在内容差异）。
- pytest / pyright：本 gate 只修改 Markdown plan/review artifact，未修改生产代码或测试，
  按用户限定不运行实现期验证。

## Residual risks and blocking questions

- fixed in plan：`P3-C-RR-PF-01` 至 `P3-C-RR-PF-05`。
- covered by S1：persisted candidate read-side corruption、enum/snapshot drift。
- covered by S2：typed pair propagation、compact protocol structural subtype、non-material
  provenance、ordinary compact去重、budget owner、三个 false-owner dead constants，以及
  `llm_compaction.py` 的直接 owner test / aggregate collection / 单文件 coverage gate。
- covered by S3：typed evidence exact component mapping、唯一 renderer、typed mismatch。
- assigned to P3-E：accepted tool status fallback/raw outcome reconstruction。
- assigned to P3-J：全局 EventLog taxonomy/DDL closed-set。
- Blocking questions：0。

## Gate result

- `P3-C-RR-PF-01`：fixed。
- `P3-C-RR-PF-02`：fixed。
- `P3-C-RR-PF-03`：fixed。
- `P3-C-RR-PF-04`：fixed。
- `P3-C-RR-PF-05`：fixed。
- Controller coverage follow-up：fixed。
- Implementation slices：3（保持 S1/S2/S3）。
- Blocking questions：0。
- Decision：`ready-for-second-plan-rereview`。
- Next gate：parallel AgentMiMo + AgentDS second plan re-review；本轮未进入。

Artifact path：
`docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-fix-codex.md`。
