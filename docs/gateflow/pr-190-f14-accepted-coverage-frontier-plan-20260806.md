# PR 190 F14 accepted coverage frontier 实施计划

## Gate metadata

- gate: `plan`
- work unit: F14，修复 accepted compact terminal 越过 protected/unselected raw turns
- branch / PR: `codex/interactive-oracle` / existing draft PR 190
- plan base: `ac68e77207c2809eabaf7ef51b6cdf65795889a7`
- Goal Confirmation: `docs/reviews/f14-goal-confirmation-20260806-221301.md`
- status: `accepted`
- current gate / next entry point: accepted plan commit 后进入 S1 implementation
- blocking open questions: 无
- artifact path: `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md`

## Outcome first

本 work unit 只修改 Host compact material owner：下一轮 pre-dispatch material view 不再以 latest `CONTEXT_COMPACTED.event_sequence + 1` 作为 delta 起点，而是从当前 Session 全部 strict accepted compact truth 的 `compacted_source_refs`、canonical raw material 与 Host Run group 原子性机械派生唯一 accepted consumption frontier。

accepted compact 只消费本次 immutable source boundary 中 represented / omitted exact partition 覆盖的 source refs；current input 与未进入 boundary 的 protected recent raw groups 保持未消费。失败、拒绝、取消、stale/late 与 tier 4/5 fallback 没有 `CONTEXT_COMPACTED`，自然不能推进 frontier。restart/reconnect 重新读取同一 EventLog accepted truth，结果必须相同。

不新增表、字段、cursor、schema、public contract、compatibility reader、LLM heuristic 或下游 fallback。

## 第一性原理与直接证据

### 失败链

1. Oracle report digest 已核验为 `788ba7d7979bc2a3eca33307a2a9fccd24da6263031765cc4096a3b21463b72b`。
2. production EventLog sequence 103–181 的四个 FY2025 correction Run groups 位于首次 accepted compact sequence 187 之前，但因 recent floor 保护没有进入该 accepted source boundary。
3. sequence 187 的 accepted truth 只覆盖 FY2024；后续 accepted boundaries 只看到 current input 与 previous compact，无法再为 FY2025 建立合法 provenance。
4. `select_compact_segment` 已把完整 `host_run_id` group 标为 `protected_recent_raw_floor` 并排除出 selected pack；错误发生在下一轮 builder 把 terminal ledger 位置误当 consumption frontier。
5. 当前 `_post_compact_delta_start_sequence` 在存在 latest accepted compact 时直接返回 terminal sequence + 1。这一分支既不读取 `source_boundary`，也不读取 represented / omitted coverage。

### 动机裁决

F14 成立且严重性正确。ledger terminal 只能证明 accepted fact 在何时提交，不能证明它之前的全部 raw facts 被 replacement 表达或明确消费。recent window 暂时保存 raw correction 只会延迟暴露 durable replacement 缺失，不会修复它。

## 语义 owner 与唯一真源

| 语义 | 唯一 owner | 本计划使用的不变量 |
| --- | --- | --- |
| accepted consumption | `CompactAcceptedTruthV4` 的 immutable boundary + represented/omitted exact partition；durable typed view 为 `ContextCompactedSemanticPayload.compacted_source_refs` | 只有进入 accepted boundary 的 refs 被消费；omitted 是已覆盖但未表示，protected/unselected 不在 boundary，不能伪装成 omitted |
| current input | strict payload `current_input_ref` | current input 是 accepted terminal 的首项 anchor，但不属于 `compacted_source_refs`，保持 raw |
| canonical raw material | `dayu.host.compact_material` 的 EventLog-backed projector | user/answer 使用 canonical event ref；tool evidence 使用 accepted evidence id；不得把二者当成同一种 id |
| atomic selection | Host selector 的 `host_run_id` turn group | eligible material 以完整 Run group进入或不进入 accepted boundary；不能拆组、乱序、跳过 oversized prefix 后继续选择 |
| latest compact terminal | canonical EventLog | 只拥有 accepted terminal identity、ledger order、artifact/rolling provenance；不拥有 material coverage frontier |
| Memory cursor | Conversation Memory projection | 只拥有 projection checkpoint/catch-up；不得作为 compactor coverage cursor |

frontier 是上述 accepted truth 与 canonical raw material的确定性派生值，不是新增 durable truth。`latest_compacted_event_id/sequence` 继续作为 terminal provenance 暴露；`post_compact_delta_start_sequence` 改为最早仍未消费 material 的 canonical sequence，二者不再相等或互相推导。

## 候选 plan 裁决

### 接受的共同部分

- AgentMiMo、AgentDS、AgentCodex 均确认修复边界在 Host material builder，不能修改 prompt、provider、UI 或 recent floor。
- 接受“遍历 accepted `CONTEXT_COMPACTED` strict payload，按 canonical accepted order累积 `compacted_source_refs`”以及“复用现有 Run group 原子选择”两点。
- 接受生命周期测试必须区分 accepted terminal 与 attempt-rejected / failed / cancelled / stale-late non-accepted events。

### 否决的路径

- 否决 `WHERE event_id NOT IN (compacted_source_refs)`：tool material 的 canonical source ref 是 evidence id，不是 producer EventLog id；这种 SQL 会把已消费 evidence 错判为 raw。
- 否决只读取 latest compact 的 aggregate evidence refs：它只表示 latest replacement facts 的 provenance，不等于 represented+omitted consumption，也丢失滚动链中已消费的 raw refs。
- 否决新建 persisted frontier/cursor：现有 accepted payload 已有完整 coverage 真源；新字段会形成第二套状态与迁移问题。
- 否决从 summary、source label、ref prefix、event adjacency、timestamp 或 terminal位置反推 coverage。
- 否决无界 giant `NOT IN` 参数与“每个 consumer各自过滤”实现；筛选必须集中在 material owner 内完成。

## Code-generation-ready implementation

### 1. 读取 accepted coverage chain

在 `dayu/host/compact_material.py` 内新增窄私有类型与模块级 helper：

```python
@dataclass(frozen=True, slots=True)
class _AcceptedCompactChainEntry:
    event: EventLogRow
    semantics: ContextCompactedSemanticPayload

def _accepted_compact_chain_before_current_input(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    before_event_sequence: int,
) -> tuple[_AcceptedCompactChainEntry, ...]: ...

def _accepted_compacted_source_refs(
    entries: tuple[_AcceptedCompactChainEntry, ...],
) -> tuple[str, ...]: ...
```

chain helper 一次读取当前 input 之前、当前 Session 的全部 canonical `CONTEXT_COMPACTED` rows，按 `event_sequence ASC` 排列，并通过现有 `resolve_context_compacted_payload` + `parse_context_compacted_semantic_payload` strict path 每条只解析一次。私有 entry 只是同一 read transaction 内的 typed read result，不持久化、不公开，也不成为第二 truth。

机械产生两个不同投影：

- latest typed entry 的 event / `accepted_replacement` / `accepted_evidence_mapping_refs`：直接服务 previous compact view 与“当前 replacement 已表示哪些 evidence fact”的既有投影语义；同一 build 不再通过多个 wrapper 重复 resolve/parse latest payload。
- accepted consumed source refs：把每个 strict payload 的 `compacted_source_refs` 按 accepted terminal order、boundary order做 ordered-unique union。该集合同时包含 represented 与 omitted coverage，但永不包含各次 `current_input_ref`，也不从 flat evidence aggregate生成。

读取过程中必须 fail closed：event class/type/session 不一致、EventLog row消失、payload/descriptor/artifact digest损坏、strict semantic binding失败均抛 `HostDurableError`。每个 `semantics.current_input_ref` 还必须 exact 指向同 Session、sequence 早于该 compact terminal 的 canonical `USER_INPUT_ACCEPTED`；多个 reactive accepted compacts可以合法复用同一current input。对 `source_boundary` 中 `source_kind` 为任一 `PREVIOUS_*` 的typed entry，其每个source ref必须exact指向同Session、sequence更早的canonical accepted compact；self/forward/cross-session/wrong-class reference fail closed。不得通过字符串prefix或“恰好能查到同名event”猜ref kind；trace/answer/evidence membership仍由各自typed material projector与atomic proof校验。

只有 canonical `CONTEXT_COMPACTED` 参与 chain；实际 rejected event type 是 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`，failed type 是 `CONTEXT_COMPACTION_FAILED`，它们以及 requested、cancel diagnostic与 late/stale no-op 均不进入查询。repair accepted 与 tier 1–3 accepted 最终都只产生一个正常 `CONTEXT_COMPACTED`，和 initial accepted 复用同一读取路径；rejected proposal从不先形成一个可被“推翻”的accepted terminal。

跨 rolling chain 的 union 不依赖 previous compact event ref替前序raw做传递推断：builder显式读取每一条 accepted terminal，各 terminal 自己的 `compacted_source_refs` 直接贡献当轮实际覆盖。previous compact event ref只保留rolling provenance，并接受上述back-reference校验。

### 2. 从 accepted coverage 派生 raw frontier

仍由 `build_pre_dispatch_compact_material_view` 统一构造 source boundary，固定采用两阶段算法；不得在implementation时改成全payload历史扫描或recent-window估算：

#### 2.1 metadata-first conservative frontier

1. 读取 current input 与 accepted chain，得到 cumulative `consumed_source_refs`。
2. `_post_compact_delta_rows` 改为读取 current input 之前全部 relevant canonical row metadata，事件种类仍严格限于 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`，保持 EventLog canonical order；本阶段只构造 `EventLogRow`，不调用payload resolver或tool evidence projector。
3. 新增 `_conservative_unconsumed_row_start_sequence(rows, consumed_source_refs, current_input_sequence) -> int`。它按首次出现位置归并 `run_id`：
   - 可被跳过的 group 必须有且仅有一个 canonical `USER_INPUT_ACCEPTED` anchor；该 user block 的 consumable ref 按既有typed projector contract就是 `row.event_id`。
   - `anchor.event_id in consumed_source_refs` 是该group已经由既有whole-group selector进入某次accepted boundary的proof。因为selector对`_AtomicMaterialUnit`只允许整组selected/omitted coverage，已覆盖user anchor不要求在metadata阶段解析同组tool payload即可安全跳过整组。
   - 当前EventLog-backed raw projector从不设置显式`protected_recent_raw_turn=True`；recent floor只由`protected_recent_turn_group_ids_for_material_blocks`按各group最新canonical位置选取最新N组，因此protected groups必为suffix。若未来引入任意位置的显式保护，必须先修改本owner contract与proof，不能静默复用本算法。
   - 未覆盖user anchor的第一个group、`run_id=None`、缺user anchor或多个user anchor都不能跳过；其最早row成为保守扫描起点。
   - group状态必须是“已消费prefix，随后全为未消费”；未消费group之后再次出现user anchor已消费的group，说明accepted coverage与strict prefix/atomic contract矛盾，立即 `HostDurableError`。
4. 没有不可证明row时，保守起点为current input sequence。该算法不使用recent floor/cap估算、不用SQL `NOT IN`，也不解析已经由user anchor证明整组消费的历史tool payload。

#### 2.2 frontier 后 typed atomic proof

5. `_post_compact_delta_rows` 的返回rows在内存中从保守起点切片，只对这些rows调用 `_pre_dispatch_delta_material_blocks`。该 projector删除`represented_evidence_refs`参数与内部early skip；`_accepted_tool_evidence_delta_blocks`也删除同名过滤参数。原因是early skip会隐藏partial-group corruption。tool row必须继续通过 `project_accepted_tool_result` 得到真实 `evidence_id`，再形成 `canonical_source_refs=(evidence_id,)`。
6. 新增 `_unconsumed_atomic_material_blocks(material_blocks, consumed_source_refs) -> tuple[RunInputMaterialBlock, ...]`，复用 `_sorted_material_blocks` + `_atomic_material_units`：
   - 单个block的refs与consumed集合只能all-in或none-in；部分相交fail closed。
   - 一个atomic unit内所有blocks必须同为consumed或同为unconsumed；混合状态fail closed。
   - units状态只能是consumed prefix后接unconsumed suffix；unconsumed之后再出现consumed unit fail closed。
   - 删除consumed prefix，原样返回unconsumed suffix，保持group内`event_sub_index`与group间canonical order。
   - `RUN_SUCCEEDED`虽存在但没有continuity text时本来就不产生answer block；atomic proof只计算typed projector实际产生的eligible blocks，不把无block的raw row虚构为source ref。
7. `_post_compact_delta_start_sequence` 改为纯派生helper：返回第一条保留block的`event_sequence`；没有保留block时返回current input sequence。它不再接收latest compact terminal，也不再执行SQL。`CompactMaterialSourceBoundary.post_compact_delta_start_sequence`明确表示material coverage frontier，不是metadata扫描起点。

修订后的函数流固定为：

```text
validate current input
  -> strict accepted chain (parse once)
  -> ordered-unique consumed_source_refs
  -> relevant raw EventLog metadata rows
  -> conservative group-anchor start (no payload resolution)
  -> typed project only suffix rows
  -> existing atomic units + exact consumed proof
  -> unconsumed blocks + material frontier sequence
  -> one PreDispatchCompactMaterialView
```

实现不得把 `accepted_evidence_mapping_refs` 改名或改作 consumption truth；它继续只表示 latest accepted replacement逐 EvidenceFact refs union。cumulative consumption只来自chain的 `compacted_source_refs`。

### 3. 保持 downstream 同源

- `previous_compacted_view` 继续只从 latest strict `accepted_replacement` 构造。
- next compactor source boundary 由过滤后的 raw blocks + latest previous compact view + current input anchor构造；source labels继续是 prompt-local labels，canonical refs继续来自对应 block。
- artifact与 canonical terminal仍由 `CompactAcceptedTruthV4` 同一实例序列化；本 slice不修改 writer。
- Conversation Memory仍从 strict terminal投影 replacement，并以 `compacted_source_refs` 删除本次真正消费的 selected recent items；本 slice不新增 Memory rule。
- ordinary RunInput/reconnect与 fallback均复用 `build_pre_dispatch_compact_material_view`，不得各自计算 frontier。
- Tool Trace继续从 strict accepted terminal机械投影 accepted replacement；不修改 renderer。

### 4. 生命周期

```text
raw canonical Run groups
        |
        v
Host selector: old eligible prefix selected; recent floor/current protected
        |
        +-- reject / repair pending / failed / exhausted / cancel / stale-late
        |       -> no CONTEXT_COMPACTED -> coverage unchanged
        |
        `-- accepted (initial/repair/tier 1-3)
                -> one strict accepted boundary
                -> represented + omitted exact consumed refs
                -> current/protected refs remain raw
                -> later aging makes complete protected groups eligible again
```

restart/reconnect只重读 canonical accepted chain，不读取进程内cache。tier 4/5 fallback没有 accepted terminal，因此不推进。

## Implementation slice

本修复只有一个原子 slice。把 production owner、owner tests与规范一起完成，避免提交“frontier实现已变但设计/测试仍宣称terminal+1”的中间态。

### S1 — Host accepted coverage frontier

Allowed production files：

- `dayu/host/compact_material.py`

Allowed owner/integration tests：

- `tests/host/test_compact_material.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compaction_cancellation_scope.py`
- 仅在既有 shared test helper确有必要时修改其直接 owner文件

Allowed docs：

- `docs/host/design.md`
- `dayu/host/README.md`
- 本 work unit 的 `docs/gateflow/`、`docs/reviews/` artifacts

Explicitly forbidden：

- `dayu/engine/**`、`docs/engine/design.md`（只做 truth check，Engine owner未变化）
- `dayu/config/prompts/**`、provider/model、UI、Service、CLI、财报工具
- accepted Oracle、scenario predicate、旧 evidence bundle
- schema/public contract、DB migration、compatibility shim、第二 cursor/projector

## Owner test matrix

### A. F14 regression 与原子 frontier

1. 构造 accepted compact terminal 位于多个 raw Run groups之后，但其真实 boundary只覆盖较老 prefix；最近 protected groups不在boundary。fixture必须证明protected group各source sequence均早于terminal，并断言修复后`post_compact_delta_start_sequence`等于最早protected material sequence且完整groups仍在view；旧terminal+1实现会返回晚于terminal的起点并失败。不得新增“旧算法辅助函数”固化bug。
2. 让上述groups继续老化并构造第二次 accepted compact覆盖它们；断言后续view不再含已消费groups，且每个 user/answer/evidence block exact-once。
3. 多轮 rolling compact断言 frontier单调不回退，但只能跨越已消费完整groups；保留group内canonical order、不同group间EventLog order，无gap/duplicate。
4. source ref部分覆盖同一 block、同一atomic unit内只有部分blocks已消费、未消费group之后出现已消费group，或无法证明group原子消费时fail closed，不做局部过滤。
5. previous compact ref可以被下一次boundary消费，但不能把位于其terminal之前的未覆盖raw group一起标为消费。
6. 多个reactive accepted compacts复用同一`current_input_ref`合法；missing/cross-session/forward current input与self/forward/cross-session previous compact ref均fail closed。
7. accepted chain存在时，缺失/重复user anchor、`run_id=None`、无continuity answer与空material projection分别覆盖保守frontier与typed atomic proof边界。

coverage-sensitive test helper必须显式接收真实`current_input_ref`与per-label `source_refs`。所有声称“某raw已经消费”的fixture都要把真实user/answer event id与真实evidence id写进accepted boundary；`source:T1`等synthetic默认值只能用于不判断coverage的payload shape测试，不能倒逼生产兼容分支。

### B. evidence ownership

1. tool result EventLog id与accepted evidence id故意取不同值；只按 evidence id exact coverage过滤，防止 SQL/event-id方案误通过。
2. FY2024 old fact refs保持原值；FY2025 correction只能从新的 accepted tool evidence atom进入新的 replacement，refs非空且不借用旧ref。
3. 无tool evidence的21.7%不能构造 `CompactAcceptedEvidenceFactV4`；既有 strict owner test继续覆盖 non-empty与boundary binding。
4. represented与omitted均推进本次实际 boundary coverage；protected-but-unselected不进入omitted。

### C. 状态机

- accepted initial、repair accepted、tier 1–3 accepted：只按各自 committed boundary推进。
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED`、repair pending/exhausted、`CONTEXT_COMPACTION_FAILED`、cancelled、stale/late no-op、tier 4/5 fallback：没有 canonical `CONTEXT_COMPACTED`，frontier不变。
- restart：关闭并重新打开 durable store后构造相同view。
- reconnect：correction退出selected recent floor后，ordinary RunInput仍只能从正式 accepted replacement / Memory与正确raw frontier得到一致语义。

状态机writer已有精确测试时复用并补“没有accepted terminal就没有coverage变化”的owner断言；不得复制整套scheduler状态机到material单测。

### D. 同源投影

用同一 accepted terminal断言：artifact payload strict parse、EventLog semantic payload、Memory projection、RunInput/reconnect与Tool Trace看到相同 replacement fact claim+refs；material frontier只使用该payload的 `compacted_source_refs`。测试不得从raw JSON、aggregate refs或fixture默认值重建fact。

## Documentation decision

- 更新 `docs/host/design.md`：在 accepted `source_boundary_refs` 与 Conversation Memory规则附近明确区分 terminal sequence、accepted consumption与derived frontier，补protected raw生命周期和失败路径不推进。
- 不修改 `docs/engine/design.md`：Engine明确不拥有compact schema、coverage、memory或Host cursor，F14没有改变该边界。
- 按 `dayu/host/README.md` 的 Agent更新约束，更新 compact material / recent raw tail 的用户为Host开发者的实现概览。
- 不修改 `tests/README.md`：测试分层、运行方式和维护规则未变化。
- 不修改根README与`dayu/README.md`：无用户入口、CLI参数或分层装配变化。

## Validation plan

### Focused / union

所有命令先执行 `source .venv/bin/activate`：

- F14 owner regression与 `tests/host/test_compact_material.py`
- 受影响的 RunInput/reconnect、Memory projection、compaction operation/cancellation、dispatch scheduler测试union
- changed production file单文件coverage，目标 `>=80%`
- 根据union结果运行全仓 `pytest`
- 全仓 `pyright`
- Ruff、`python -m compileall dayu tests utils`、JSON parse scan、`git diff --check`

失败必须区分确定性回归、既有failure与provider/network flake；不得删除或放宽owner断言迎合实现。

### Fresh production CLI observation

1. 为 `interactive.interactive.g06.rolling-correction-replacement` 创建全新workspace/evidence root，不复用F13污染目录。
2. 使用 production `dayu-cli interactive`、POSIX PTY、真实 AAPL 2025 10-K corpus、production财报工具与真实 provider；优先 `mimo-v2.5-pro-plan`，不可用时使用真实DeepSeek。
3. 保存screen、精确argv/环境键名（secret值脱敏）、按键、stdout/stderr、exit code、文件diff、logs、Tool Trace request/response、EventLog、Memory、compact artifact、RunInput与SQLite前后摘要，并做跨进程reconnect。
4. 在correction退出recent floor后证明FY2025 current fact进入durable accepted replacement且每条新fact refs非空；FY2024旧current结论按既有Oracle语义supersede/omit；21.7%无evidence provenance。
5. 人工核对的最低机械标准为：该轮source boundary含此前protected correction group；不含已经消费后又重复展开的group；每条EvidenceFact的非空refs都属于该fact所选boundary evidence entries。summary/reference continuity只核对其声明labels存在于实际boundary；自然语言是否蕴含仍人工记录，不新增heuristic。provider输出差异与frontier correctness分开归因。
6. raw Host SQLite本机原件保留但不进入公开bundle；公开evidence排除或脱敏DB，对已知exact secret值运行scan。报告记录evidence root、公开入口、SHA-256与scan结果。

真实CLI observation是post-fix observed evidence，不等同Oracle formal acceptance；不得修改registry accepted/ready状态，只能给replacement candidate与fresh rerun入口。

## Review gates

1. plan：AgentMiMo、AgentDS独立planreview；Controller按直接证据裁决并在原reviewer re-review通过后提交accepted plan。
2. implementation：AgentCodex按本S1实现，不commit/push；Controller审计scope与测试。
3. code review：AgentMiMo、AgentDS独立deepreview；Controller另做adversarial code review，finding由AgentCodex修复后原reviewer re-review。
4. aggregate deepreview：对accepted plan commit以来全部diff做两路独立deepreview与Controller裁决。
5. draft PR：复用existing draft PR 190，仅push当前分支；不新建PR、不merge、不mark ready、不approve/request reviewers、不rebase/force-push、不删分支。
6. PR review：对PR 190做最终两路独立review与Controller裁决；任何代码finding回到AgentCodex fix并re-review。
7. final closeout：记录root-cause结论、唯一真源、schema/public contract状态、tests与real observation边界、fake/mock使用、formal adjudication、evidence digest/secret scan、全部commits与remaining risks。

## Risks and mitigations

| 风险 | 控制 |
| --- | --- |
| evidence id与EventLog id异构 | typed projector取得evidence id；测试故意使用不相等值 |
| accepted chain读取成本随历史增长 | accepted terminals仍须strict解析以恢复唯一coverage truth；raw side采用metadata-first user-anchor proof，只解析保守frontier后的payload。增加>=10轮rolling owner test并记录rows/blocks范围，不用recent cap估算、giant SQL `NOT IN`或已消费evidence payload重渲染 |
| fixture固化terminal+1偶然行为 | accepted test fixture必须给出真实source refs；旧fake boundary不得倒逼compatibility分支 |
| partial group/乱序 | 复用`turn_group_id`与existing atomic helpers；partial intersection fail closed，owner tests断言order/exact-once |
| provider非确定性 | deterministic owner tests证明frontier；真实run如实记录，不修改实现/Oracle迎合单次输出 |
|旧workspace已被F14污染 | unit/integration用fresh DB；production observation用fresh workspace；历史F13/F14 evidence只读保留provenance |

## Completion report contract

最终 closeout 必须明确回答：

- F14是否从root cause修复；
- frontier唯一真源及terminal sequence不再承担什么语义；
- schema/public contract是否变化；
- 哪些验证使用fake/mock，哪些是真实production CLI；
- formal scenario仍处于何种Oracle adjudication状态；
- evidence入口、digest、exact-value secret scan与raw DB发布边界；
- 当前分支全部新增commits与PR 190 head SHA；
- 未覆盖项、provider非确定性与remaining risks。
