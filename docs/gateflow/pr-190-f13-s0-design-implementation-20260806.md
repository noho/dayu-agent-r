# PR 190 F13 S0 Design Truth 实施记录

## Gate metadata

- Gate：`implementation`，slice `S0 — 设计真源切到 v4`
- Work unit：PR 190 F13，修复 rolling compaction EvidenceFact provenance丢失与无证据事实污染
- Goal Confirmation：`docs/gateflow/pr-190-f13-evidence-provenance-goal-confirmation-20260806.md`
- Accepted plan：`docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md`
- Implementation base：`2d914beefb7bdee3e762df06f5f1ef0d115da143`
- Branch：`codex/interactive-oracle`
- Artifact path：`docs/gateflow/pr-190-f13-s0-design-implementation-20260806.md`
- Completion status：S0 implementation与双路re-review complete；等待accepted slice commit，未push

## Preflight

- 当前分支不是 protected trunk。
- S0开始前工作树 clean；没有覆盖用户既有 dirty changes。
- 用户把 allowed write scope固定为 `docs/host/design.md` 与本 implementation artifact；`docs/engine/design.md`只做 truth check。

## First-principles judgment and semantic owner

动机成立且严重性为高。EvidenceFact 的业务承诺是 accepted claim绑定 canonical accepted evidence；旧设计允许模型把任意新 claim绑定 `previous_evidence_fact`，同时 durable / Memory又以 compact event级 flat union作为逐 fact provenance。该组合允许 claim laundering、空 refs与多 fact共享无关 refs，并跨 rolling / reconnect持续污染。

正确 owner链固定为：

- `compact_structure`：LLM output exact shape。
- compaction domain：v4 input / proposal / accepted fact / replacement / truth types。
- Context Governance：proposal到 accepted replacement的唯一原子展开与强约束 owner。
- compact material：上一 accepted atom到 rolling source boundary的同源重建。
- compact payload / canonical terminal：schema-5 durable写入与 strict reconstruction。
- Conversation Memory、RunInput / reconnect、Tool Trace：同一 accepted replacement的 read-model / public projection consumers，不补偿、不重算。
- Engine：generic Runner transport；不拥有 compact schema、五类 Memory、coverage、repair、artifact或 Host attempt budget。

因此本 S0在 Host设计真源原地替换冲突规范，没有修改 Engine设计。

## Changed design truth

### `docs/host/design.md`

1. §13 durable / EventLog contract
   - compactor input projection改为持久化 v4 input；`CONTEXT_COMPACTED` event contract明确 proposal digest与 accepted replacement分离。
2. §24.2 LLM-facing compact boundary
   - previous EvidenceFact只允许 retain selector；new EvidenceFact support只允许本轮 `evidence_material`；accepted refs完全归 Host。
3. §24.3 Compact v4 I/O与 Accepted Replacement Contract
   - 用 `CompactInputV4` / `CompactCandidateV4` 七字段 exact shape原地替换 v3 normative contract。
   - 定义 Host-internal `source_refs` / `canonical_evidence_refs`、LLM projection省略规则与 previous atom同源构造。
   - 定义 `CompactAcceptedEvidenceFactV4`、`CompactAcceptedReplacementV4`、`CompactAcceptedTruthV4`、retained/new atom完整构造顺序与逐 fact strict binding。
   - 冻结 retain-only合法、combined duplicate / information / caps、多 source refs公式、accepted aggregate等式与 request-boundary ordered-subset关系。
   - proposal降为 audit input；replacement成为 rolling、Memory、RunInput / reconnect与 public provenance的唯一消费对象。
4. §24.4 Snapshot / persistence
   - artifact整数 schema前移到5；durable shape固定为 `accepted_proposal` + `accepted_replacement` + internal source boundary + coverage / policy audit + aggregate projection。
   - 删除 `accepted_candidate`、v3/schema-4 reader的 normative路径；strict parser重验所有 binding。
   - rolling、multi-pass、Memory、reconnect、RunInput与 Tool Trace全部从 strict typed replacement投影。
5. §24.5–§24.6 Memory与 prompt assembly
   - EvidenceFact Memory逐 atom读取自己的 claim + refs；rolling selector保留 atom、未选择即 omit。
   - initial / repair使用同一 v4 structure；每次 repair从 strict parse重新执行完整 Host binding链。
   - rejected / failed、tier 4/5 fallback、stale / late与 single-terminal无污染语义保持不变。
6. §24.7 tests / observations
   - 增加 retain / omit / new current-evidence、多 source、aggregate subset、schema-5、rolling / Memory / reconnect / Trace同源、repair / fallback / stale / late owner tests边界。
   - 真实 provider只报告 observed behavior；Oracle formal scenarios继续由 Oracle独立裁决。
7. §25–§25.1 Context Governance
   - orchestration owner切到 v4 atomic expansion与 accepted replacement；canonical terminal、reactive multi-pass与 public Tool Trace都禁止退回 proposal或 flat refs。

### Goal Confirmation逐项映射

| Confirmed goal | Design owner / section | S0固定结果 |
|---|---|---|
| 1. accepted EvidenceFact是含非空per-fact refs的原子事实 | §24.3 accepted types / accept chain | `CompactAcceptedEvidenceFactV4`同形保存claim、selection、context与非空refs；truth只由private permit构造。 |
| 2. rolling旧fact只可keep/omit且claim+refs同源 | §24.2、§24.3 source boundary、§24.4 rolling | required retain selector只选previous label；Host从同一accepted atom复制claim与refs，模型没有旧claim字段。 |
| 3. new fact只选当前真实evidence且逐fact解析 | §24.3 proposal / strict binding | `support_labels`只允许`evidence_material`；refs等于该fact自己所选entries的boundary-order union。 |
| 4. durable前完整barrier、repair与fallback | §24.3 accept chain、§24.6 repair、§25状态机 | boundary构造先fail closed；proposal完整重验；可修复reject受bounded repair约束，耗尽走既有deterministic fallback。 |
| 5. 无工具证据的用户/assistant修正不得升级 | §24.2、§24.3 source-kind规则、§24.5 Memory | non-evidence source只可进入相应非evidence section；new EvidenceFact拒绝引用这些source kind。 |
| 6. rejected/failed/stale/late无污染和单terminal | §24.3 repair末段、§24.6、§25 | invalid / transient result无accepted读取入口；exhaustion只写一个failed terminal；tier 4/5不物化Memory。 |
| 7. artifact/EventLog/Memory/reconnect/Trace同源 | §24.4 persistence / consumers | schema-5保存proposal+replacement；strict parser重验；全部consumer读取同一typed replacement，aggregate仅为受验union。 |
| 8. owner tests、真实provider与Oracle边界 | §24.7 | 冻结mandatory owner / integration矩阵；真实provider只记observed evidence，formal scenarios继续unadjudicated。 |

### `docs/engine/design.md`

- 只读 truth check通过，没有修改。
- §15已经明确 Engine不做 compact / retry / Host budget，只表达 provider context overflow；Host compactor只消费 generic structured-output transport，Engine不知道 compact input/output schema、五类 Memory、coverage、repair、artifact或 Host attempt budget。
- 因 semantic owner未变化，修改 Engine design会制造无必要跨层耦合。

## Frozen contract decisions

- previous EvidenceFact只能由 required `retained_previous_evidence_fact_labels`选择；Host按 boundary顺序原样复制 claim与非空 refs，模型没有改写路径。
- new EvidenceFact只能引用当前 `evidence_material`；用户输入、assistant answer、anchor、summary与普通 trace/context不能形成无证据新 fact。
- 每条 accepted fact自包含 claim、selection、context与非空 canonical evidence refs；多 source refs按该 fact selected entries做 boundary-order unique union。
- accepted aggregate只等于 replacement逐 fact refs的 ordered unique union，并且是 request available evidence union的有序子集；它不是逐 fact真源。
- artifact schema 5与 `accepted_replacement` 是 fresh contract；不读 schema 4，不保留 `accepted_candidate` alias、migration shim或 loose parser。
- rolling、reactive multi-pass、五类 Memory、RunInput / reconnect、audit与 public Tool Trace从同一 strict accepted replacement投影。
- bounded repair、repair exhaustion、deterministic fallback、tier 4/5无 Memory、stale / late no-op与 single canonical terminal保持原状态机。

## Validation

- design terminology / reference scan：PASS。扫描范围为`docs/host/design.md`全文；使用`rg -n`定位命中并用`rg -c`逐pattern计数：active v3 type/schema/function pattern（`CompactInputV3|CompactCandidateV3|CompactAcceptedTruthV3|CompactOutputCapsV3|compact_output_template_v3|compact_output_json_schema_v3|parse_compact_candidate_v3|dayu.context_compaction.input.v3|dayu.context_compaction.output.v3`）为0；`CompactInputV4` 10、`CompactCandidateV4` 7、`CompactAcceptedTruthV4` 6、`CompactAcceptedReplacementV4` 3、`retained_previous_evidence_fact_labels` 2、`canonical_evidence_refs` 10、`accepted_replacement` 4、artifact schema-5固定语句1。`accepted_candidate`与`schema-4`各2次，均只出现在fresh reader明确拒绝旧shape及对应negative owner test中，不是active contract。previous fact / support与aggregate / fact组合扫描只有“禁止previous support”和“禁止aggregate反填”的normative否定命中，无自由support或反向填写路径。
- Engine truth check：PASS。扫描`docs/engine/design.md`全文的`compact`、`context_compaction_requested`、`Host budget`与`Context Governance`owner语句；§15明确Engine只发overflow transport且不做compact/retry/Host budget，generic runner不知道Host schema。owner不变，`docs/engine/design.md`无 diff。
- changed-file scope：PASS；只有 `docs/host/design.md` 与本 artifact。
- `git diff --check`：PASS；新建 artifact另以 `git diff --no-index --check /dev/null <artifact>`检查，PASS。
- 本 slice只修改 design文档；未修改生产代码或测试，因此未运行 pytest、pyright、Ruff或 coverage。

## Docs and scope decision

- 精确修改 `docs/host/design.md` 并新建本 artifact。
- 未修改 `docs/engine/design.md`、生产代码、tests、README、其它设计 / gateflow / review artifact。
- README trigger未命中：S0只切换 future implementation design truth，没有落地用户可见或 production runtime行为。
- S0 review / adjudication artifacts属于同一Gateflow evidence scope；未修改其它设计、生产代码、tests或README。
- 按用户要求尚未push；accepted slice commit由Controller在review gate通过后创建。

## Residual risks and uncovered areas

- 本 S0只冻结设计；v4 structure、Host binding、schema-5 persistence与所有 consumers尚未在生产代码实现，由 accepted plan S1 / S2负责。
- owner tests、完整 pyright / Ruff / compileall、真实 provider observation由后续 slices执行；当前不能声称 runtime已修复。
- schema-4 compact payload / Session replay明确不兼容；若产品要求迁移，owner是独立 migration work unit，不在 F13范围。
- Oracle formal replacement scenarios保持 `assigned to later Oracle adjudication`，当前未接受。
- 两路独立review的accepted findings均已修复并由原reviewer逐项re-review通过；S0尚未创建accepted slice commit。

## Completion signal

S0 design truth implementation与review gate完成：后续 S1 / S2不需要重新发明 v4 selector、Host accepted replacement、逐 fact provenance、schema-5 persistence或 rolling / Memory / reconnect / Tool Trace ownership。下一入口是S0 accepted slice commit，随后进入S1 production contract implementation。
