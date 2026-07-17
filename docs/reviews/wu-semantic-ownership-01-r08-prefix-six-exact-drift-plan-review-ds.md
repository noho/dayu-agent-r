# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift corrected plan — Plan Review (AgentDS)

## 1. Verdict

`CONDITIONAL PASS — 4 findings, 3 open questions, 0 blockers`

本 plan review 只审 final plan（SHA-256 `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd`），不审 implementation、code、S1/S2 artifact、prior review 或 control doc。Reviewer verdict 不授权 implementation。

Corrected plan 的语义 owner 边界、S1/S2 scope/sequence、fail-closed stop conditions、R07 no-touch、Topic 8-9 no-code、安全机制、Issues 142/151/175/177/178 与 R09-R12 deferred boundaries 均完整且内洽。391/485 exact arithmetic 与 [344,346,348,442] root evidence 已由两个 fresh coverage JSON 的 `executed_lines` 直接比较证实。Mutation-before prefix-five JSON 作为 predecessor proof 可审计且不要求回退 candidate 6。Candidate 6 no-touch continuation 与八文件零 deselect 392 passed prefix-six 的 spec 正确。

以下 4 个 findings 均为 plan 文档本身的文本一致性与 clarity 问题，不影响 plan 的 operational correctness。

---

## 2. Lock Verification

全部 lock 独立复核通过：

| Lock | Plan 预期值 | 实际值 | 匹配 |
|---|---|---|---|
| cumulative `dayu/fins + tests` binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` | ✅ |
| `read_runtime_helpers.py` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` | ✅ |
| `read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | ✅ |
| guards | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` | ✅ |
| shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | ✅ |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` | ✅ |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` | ✅ |
| staged tree | empty | empty | ✅ |
| final plan SHA-256 | `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd` | `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd` | ✅ |

`git diff --check` 通过。`git status --short` 显示 24 个 modified tracked 与 4 个 untracked review artifacts，与 plan correction artifact §7 的预期 manifest 一致。

---

## 3. Adversarial Challenge Results

### 3.1 391/485 exact arithmetic 与 checker — PASS

Direct source evidence 确认：

- Line 344: `return "material"` — `_resolve_document_type` material 分支
- Line 346: `return "other"` — `_resolve_document_type` other 分支
- Line 348: `return _CN_FORM_TYPE_TO_DOCUMENT_TYPE[form_type]` — CN FY 分支
- Line 442: `return None` — `_normalize_form_type_for_matching(None)` normalization

第 442 行位于 `_normalize_form_type_for_matching`（定义于 line 424），是 `form_type=None` 输入经 `resolve_document_type_for_source → _normalize_form_type_for_matching(None)` 的必经路径。Candidate 6 的 `form_type=None, source_kind=FILING` 断言必然执行此分支。

Checker（§6.6 Python script）使用 `covered == 391 and statements == 485 and percent >= 80.0` 的 exact comparison，逻辑正确。

**结论**：391/485 = 80.61855670% 是机械必然结果，不是 display rounding 或测试失败。

### 3.2 [344,346,348,442] root evidence — PASS

Evidence chain：
1. Coverage-statement-drift artifact §7：两个 fresh JSON 的 `executed_lines` direct comparison
2. Controller adjudication §3：确认 JSON 同源比较与 line semantics
3. Plan correction artifact §2：重复 root evidence
4. Controller validation §3：accepted finding closure

本 review 独立验证：`grep -n` 确认 lines 344/346/348/442 的 source 内容与 plan 描述一致。

**结论**：root evidence 链完整、可审计、无需重新运行 coverage。

### 3.3 Mutation-before prefix-five JSON 作为 predecessor proof — PASS

Coverage-statement-drift artifact §4 记录：

- 同一 implementation task、同一 locked tree、同一八文件零 deselect
- Candidate 6 mutation 前：`391 passed, 387/485 = 79.79381443% < 80.00%`
- JSON SHA-256: `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb`
- 时序证据：guards hash 从 `55318914...928d`（mutation 前）变为 `cc4c5267...9274`（mutation 后）

Plan 正确禁止回退 candidate 6 重跑 prefix-five；predecessor JSON 已在 mutation 前产生且不可伪造（guards hash 变化轨迹可审计）。

**结论**：predecessor proof 可审计、时序正确、不要求回退。

### 3.4 Candidate 6 no-touch continuation — PASS

Plan 在多处明确声明 candidate 6 已存在且 immutable：
- §1 accepted finding："保留已存在且正确的 candidate 6...不新增第七项、不回退 candidate 6"
- §6.1："已存在的 candidate 6 exact node及唯一 `resolve_document_type_for_source` import...continuation 不得再次实现、回退或修改它"
- §8 stop conditions："已存在的 candidate 6 import/test/三断言发生任何漂移...立即 stop 回 Controller"

本 review 独立验证：guards 文件确实包含 `test_document_type_resolver_projects_material_other_and_cn_categories`（line 1955）与 `resolve_document_type_for_source` import（line 57）。

**结论**：no-touch 约束清晰、可执行、已由 file hash lock 保护。

### 3.5 同一八文件零 deselect 392 passed prefix-six — PASS WITH NOTE

Plan §6.6 指定的八文件命令与 checker script 正确。Coverage-statement-drift artifact 已证明该命令在当前 locked tree 产生 `392 passed, 391/485 = 80.62%`。

**Note**：Exact `392` count 依赖于八文件中无其他 test 增减。若后续维护修改了这八个文件的 test count，exact check 会 fail closed——这是 plan 设计意图，但值得在 handoff 中提醒 implementer。

### 3.6 完整从零 §6.6/§6.7 — CONDITIONAL PASS

Validation matrix 覆盖完整：focused owner matrix、S2 focused/public、forced-truncation、real smokes、aggregate、full Fins regression、15-file exact-key coverage、pyright、Ruff、all scans。Plan 要求从零 fresh erase 重跑，不接受旧 incremental ledger。

**Condition**：§6.6 的 15-file exact-key coverage checker 依赖 `git diff --name-only` 产生的 manifest。如果 working tree 中存在 plan 文档本身的修改（当前 plan 为 modified），这些不会进入 manifest（paths 限定为 `dayu/fins/**/*.py`）。同理，如果未来任何 plan-only 修改引入新的 S1/S2 文件，manifest 将自动捕获。这是正确行为——但 implementer 必须在运行 §6.6 前确认 working tree 与 plan's expected 15 production files 一致。

### 3.7 First/shortest 结论 — PASS WITH CLARIFICATION

Plan 声称 candidate 6 是 "first/shortest threshold-crossing prefix"。这个结论对于 `read_runtime_helpers.py` 的 80% threshold 是正确的：
- 五个 stable-owner tests：387/485 = 79.79% < 80%
- 五个 + candidate 6：391/485 = 80.62% >= 80%
- 无需第七项

但该结论的范围仅限于 `read_runtime_helpers.py` 单文件。S2 的 public projection/read/tool tests 为其他 14 个 changed production 文件提供了大量 coverage（参见 S2 artifact §Validation ledger：`bs_report_form_common.py` 从 S1 的 65% 提升到 83.73%，`sec_processor.py` 从 42% 提升到 85.17%）。Plan 未明确区分"prefix proof 只针对单文件"与"full acceptance 针对全部 15 文件"——见 Finding M2。

### 3.8 Fail-closed — PASS

Plan §8 的 stop conditions table 覆盖完整：producer contract failures、method absent/empty、provider raw total、S1→S2 propagation、Host truncation coupling、旧 test compatibility、lock mismatch、candidate 6 drift、helper deletion revert、prefix-five/prefix-six exact drift、§6.6/§6.7 failures、out-of-scope discovery。每个 stop condition 都有明确的禁止补救列表。

### 3.9 Semantic owner — PASS

Plan §2.2 的 owner table 精确分配了每个语义的 owner：
- Financial producer → `financial_result_contract.py` + actual processors
- XBRL raw query → `xbrl_result_contract.py` + actual processor
- Public financial/XBRL → `result_types.py` typed projection
- List-documents → `read_runtime.py::_collect_available_document_types_for_source_documents`
- R07 storage identity/revision/snapshot/citation → no-touch

§2.3 明确列出 out-of-scope：R09-R12、Issues 142/151/175/177/178、统一 authorization、Host/Engine/Service/UI。

### 3.10 Scope/sequence/overcoupling — PASS WITH FINDINGS

S1→S2 顺序正确：producer contracts → all actual processors → public projection → read composition → tool schema。S1/S2 是同一 destructive cutover 的两个阶段，不设中间 commit。

Scope 约束严格：§5.1/§6.1 的 production/test/README allowlists 精确，§2.3 的 out-of-scope 清晰。

Overcoupling 检查：
- `result_types.py` 是唯一 public projection owner ✅
- `read_runtime_helpers.py` 是唯一 normalize/dedup owner ✅
- `fins_tools.py` 只消费 owner helper ✅
- Host truncation boundary（§6.4）通过 forced-truncation test 的 public seam 验证 ✅
- R07 snapshot/citation no-touch ✅

无过度耦合发现。但 §5.1 test name references 与 §6.2 temporal scope 存在问题——见 Findings M1、M3。

### 3.11 Product/tests/README no-touch — PASS

Plan §6.1："当前 continuation 不授权任何 production 或 test delta...prefix-six exact-drift continuation 不改 README"。§6.8 明确 README trigger check 结论为 no-update。Plan correction artifact §7 验证 product/tests/README/control/design/prior reviews 均为 no-touch。

本 review 独立验证：当前 working tree 的 production/test/README 修改均为 pre-existing stopped-tree 状态，非本 plan correction 造成。

### 3.12 Topic 8-9 no-code — PASS

Plan §2.3 out-of-scope 包含 "Topic 8-9 no-code"。Overdesign controller discussion 明确：Topic 8（Engine 240 chars）accepted as-is no code fix；Topic 9（Tool security）design clarification only, no code fix。Plan 不授权这些 topic 的 implementation。

### 3.13 安全机制 — PASS

Plan §6.7.E 要求 retained-security/no-touch scan 验证 R06/R07 storage、identity、revision、snapshot、citation、containment、symlink、atomic publication/recovery、Host truncation owner 均无语义变更。Plan 不删除任何安全机制，不引入新的 security-sensitive path。

### 3.14 R07 no-touch — PASS

Plan §6.7.D 要求 `git diff -U0` 核验 `read_runtime.py` 只改 financial/XBRL projection symbols。S2 artifact 记录 AST 比较证明 21 个 snapshot/borrow/release/revision/citation/source-changed 函数与 HEAD 相同。

### 3.15 Issues 142/151/175/177/178 与 R09-R12/deferred boundaries — PASS

Plan §2.3 明确 out-of-scope：R09 direct-stream validator、R10 HKEX、R11 upload/placeholders、R12 init/reset、Issues 142/151/175/177/178、统一 authorization。§6.7.E exact allowlist scan 确保无越界实现。§8 stop condition："发现R09-R12/deferred issue → 记录out-of-scope并停止扩张"。

---

## 4. Findings

### Finding M1 (MEDIUM) — §5.1 S2 test name references 全部 stale

**Severity**：MEDIUM
**Owner**：Plan §5.1（`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`）
**Fix destination**：同一 plan 的 §5.1

**Evidence**：

Plan §5.1 引用六个 S2 normalize/dedup test names：

```text
test_xbrl_query_payload_missing_total_fails_closed
test_xbrl_query_payload_non_int_total_fails_closed
test_xbrl_query_payload_mismatched_raw_total_fails_closed_before_dedup
test_xbrl_query_payload_preserves_processor_total_after_dedup
test_xbrl_query_payload_always_projects_dedup_count_and_owner_quality
test_xbrl_query_payload_rejects_producer_dedup_count
```

Direct grep 确认全部六个名称在 `tests/fins/test_fins_read_runtime.py`（SHA `01db5538...6692`）中 **均不存在**。实际文件中的六个对应测试使用不同名称：

```text
test_xbrl_query_payload_missing_facts_fails_closed
test_xbrl_query_payload_rejects_non_flat_query_params
test_xbrl_query_payload_preserves_raw_input_during_normalization
test_xbrl_query_payload_stable_dedup_projects_unique_fact_count
test_xbrl_query_payload_preserves_owner_quality_and_optional_reason
test_xbrl_query_payload_zero_hit_has_single_count_and_no_reason
```

新名称反映了 corrected contract（不再有 "total"、"deduped_fact_count"、"processor_total"、"producer_dedup_count" 等已删除字段），语义一致且更准确。但 plan 文本引用了从未存在的名称，使 §5.1 的 symbol boundary 描述与 locked tree 不一致。

**Why**：原始 plan 在 S2 实施前预测了 test names；S2 implementation 在 contract 收紧后使用了准确反映新 contract 的名称；历次 plan correction（CF01、PCF02、PCF03、PCF04）均未更新 §5.1 的这些 stale 引用——它们每次只修正了 coverage arithmetic 和 re-entry locks。

**How to apply**：§5.1 的六个 S2 test name 引用应更新为实际名称，或改为引用 shared test SHA lock（`01db5538...6692`）作为 authoritative spec 而不枚举具体名称。注意这属于 plan clarification，不改变任何 operational instruction 或 lock。

**Materiality**：不影响 implementation——shared test 的 content lock（`01db5538...6692`）是 operational truth，test name references 只是 human-readable annotation。但若未来有人按 §5.1 名称搜索而找不到测试，会浪费排障时间。

---

### Finding M2 (MEDIUM) — Coverage narrative conflates prefix proof scope with full acceptance scope

**Severity**：MEDIUM
**Owner**：Plan §1, §6.6（`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`）
**Fix destination**：同一 plan 的 §1 或 §6.6 添加 clarifying note

**Evidence**：

Plan §1 items 6-10 构建 narrative：candidate 6 是解决 coverage threshold 的 "first/shortest" 方案。该 narrative 的全部证据（prefix-five 387/485 < 80%，prefix-six 391/485 >= 80%）仅涉及 `read_runtime_helpers.py` 一个文件。

但 R08 的 full acceptance（§6.6）要求全部 15 个 changed production 文件 >= 80%。S2 artifact 的 coverage ledger 显示：

- S1-only tree 有 7 个 processor 文件在 41%–67%（S1 artifact §Blocking validation evidence B2）
- S1+S2 cumulative tree 的所有 15 个文件在 80.17%–100%（S2 artifact §Exact-key per-file coverage）

这意味着 S2 public projection/read/tool tests 贡献了 processor 文件的大部分 coverage。Candidate 6 只关闭了 `read_runtime_helpers.py` 的 80% gap；其他 14 个文件的 coverage 来自 S2 tests。

Plan 从未明确陈述"prefix proof 范围仅限于 `read_runtime_helpers.py` 单文件"。读者可能误以为 candidate 6 关闭了整个 R08 的 coverage gap。

**Why**：Plan 的 prefix-five/prefix-six proof 是为了证明无需恢复被删除的四个越界 omnibus tests（R08-CR-CF01 的决定）。Proof 的逻辑范围天然限于 `read_runtime_helpers.py`，而 full acceptance 的范围是所有 changed production files。Plan 在 §1 的 narrative summary 中未作此区分，在 §6.6 中才展示完整 coverage gate。

**How to apply**：在 §1 item 8 或 §6.6 添加一句："prefix proof 仅证明 `read_runtime_helpers.py` 无需恢复 compatibility tests 即可过 80% 阈值；全部 15 个 changed production 文件的 coverage 由累计 S1+S2 tests（owner tests + public projection tests + real smokes）共同提供，具体见 §6.6 exact-key coverage checker。"

**Materiality**：不影响 operational correctness——§6.6 的 15-file checker 是 authoritative gate。但 narrative 可能误导 future reader 对 coverage 来源的理解。

---

### Finding M3 (MEDIUM) — §6.1 "不授权任何 delta" 与 §6.2 "实施顺序" 存在 temporal scope ambiguity

**Severity**：MEDIUM
**Owner**：Plan §6.1, §6.2（`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`）
**Fix destination**：同一 plan 的 §6.1 添加 explicit state clarification

**Evidence**：

§6.1 开头声明：
> "当前 continuation 不授权任何 production 或 test delta"

紧接着 §6.2 列出 8 项 S2 implementation 步骤（建立 public types、description helpers、normalize/dedup pipeline、read composition、tool schema、R07 citation flow、README check、prefix-six rerun）。这些步骤在 §6.2 item 1-7 使用 implementation 语言描述具体代码变更。

矛盾在于：如果 S2 已实现（如 lock `e40de2a0...33f` 所证明），§6.2 items 1-7 不应被理解为"需要执行的步骤"；如果 S2 未实现，§6.1 的 "不授权任何 delta" 就与 §6.2 冲突。

实际 resolution（来自 plan correction artifact 与 Controller adjudication 的上下文）：S1+S2 已完整实现在 stopped tree 中。§6.1 的 "不授权任何 delta" 指 prefix-six exact-drift continuation 不应新增修改——只验证 coverage、运行 §6.6/§6.7。§6.2 的 items 1-7 描述的是 stopped tree 中已存在的 cumulative state（"累计历史闭集"），只有 item 8（prefix-six proof rerun）是当前 continuation 的实际动作。

但 plan 文本本身未做此区分。§6.2 通篇使用未来/祈使语气（"删除"、"建立"、"执行"、"保留"），读起来像是待执行的 implementation 指令。

**Why**：Plan 经历了多次 correction，S2 在较早轮次已实现。后续 correction（CF01、PCF02、PCF03、PCF04）在 plan 上叠加了 coverage/drift/lock 修正，但 §6.2 的原始 implementation 描述未改写成"已完成"时态。

**How to apply**：在 §6.1 的 "当前 continuation 不授权任何 production 或 test delta" 后添加："当前 stopped tree（cumulative diff `e40de2a0...33f`）已含完整 S1+S2 implementation；§6.2 items 1-7 描述该累计状态，§6.2 item 8 与 §6.6/§6.7 是本 continuation 需执行的 verification。"同时在 §6.2 items 1-7 前添加 "（已完成于 stopped tree）" 标记。

**Materiality**：MEDIUM——若 implementer 误解为"需要先 implement S2"，会重复已完成工作或在不匹配的 tree 上操作。但 lock verification 会 fail closed（production file hash 变化），因此实际风险可控。

---

### Finding L1 (LOW) — S2 artifact coverage numbers from different tree may not hold on current tree

**Severity**：LOW
**Owner**：Plan §7（`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`）
**Fix destination**：同一 plan 的 §7 添加 caveat

**Evidence**：

S2 artifact 记录 content hashes 与当前 locked tree 不同：

| File | S2 artifact SHA | Current lock SHA | Match? |
|---|---|---|---|
| `read_runtime_helpers.py` | `46e87c63...93b` | `1d7b4bf1...5ea9b` | ❌ |
| `test_fins_read_runtime.py` | `c099c628...a09a` | `01db5538...6692` | ❌ |
| `test_read_runtime_semantic_ownership_guards.py` | `4a076ca6...1ff` | `cc4c5267...9274` | ❌ |

Plan §7 引用 S2 artifact 的 coverage ledger（15 files 80.17%–100%）作为 "已审计baseline"。这些数字来自不同 tree state，可能不完全适用于当前 locked tree。Plan 正确要求 §6.6 从零 fresh validation——不依赖 S2 artifact numbers——但 §7 的 "已审计baseline仅用于增量判定" 措辞可能让读者误以为这些数字是当前 tree 的可靠 expectation。

**Why**：S2 artifact 来自更早的 implementation round；后续 CF01/PCF02/PCF03/PCF04 修改了 shared test 与 guards，导致 file hashes 变化。Coverage 数字可能随之漂移。

**How to apply**：在 §7 的 baseline 引用处添加："以下 baseline 来自不同 tree state（S2 artifact `08085bde...648`），仅作数量级参考；当前 tree 的 exact coverage 必须由 §6.6 fresh validation 独立产生。"

**Materiality**：LOW——§6.6 的 fresh validation 是唯一 acceptance gate。Plan 不依赖 S2 artifact numbers 做任何 decision。

---

### Finding L2 (LOW) — `read_runtime_helpers.py` SHA label "deletion 后内容" 不准确

**Severity**：LOW
**Owner**：Plan §0, §6.1（`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`）
**Fix destination**：同一 plan

**Evidence**：

Plan §0 table 将 `read_runtime_helpers.py` SHA `1d7b4bf1...5ea9b` 描述为 "deleted-helper SHA-256"。Plan §6.1 描述为 "`read_runtime_helpers.py` deletion 后内容 SHA-256"。

该文件不仅删除了 dead helper `_collect_available_document_types`——还包含 S2 cumulative changes（normalize/dedup pipeline、public projection helper、flat query params 等）。Label "deletion 后" 低估了该 SHA 的语义范围：它是 "S1+S2 cumulative state 的 content lock"。

**Why**：`R08-CR-PCF02` 的原始 scope 是 dead-helper deletion，该 label 在该 context 中准确。但在 corrected plan 的 broader context 中，该 SHA 代表整个 S1+S2 cumulative `read_runtime_helpers.py` state。

**How to apply**：将 label 改为 "S1+S2 cumulative state SHA-256（含 dead-helper deletion 与 S2 public projection changes）" 或等效措辞。

**Materiality**：LOW——lock value 是正确的，仅 label 不够精确。

---

## 5. Open Questions

### Q1：Prefix-six 后 full §6.6 的 15-file coverage checker 是否已在当前 locked tree 上验证过？

Current evidence：S2 artifact 的 15-file coverage（80.17%–100%）来自不同 tree state（不同 file hashes）。Plan 要求 §6.6 "从零 fresh erase" 重跑。但 fresh run 的结果是否恰好 >= 80% 对全部 15 文件——尚未在当前 tree 上验证。

**Risk**：如果当前 tree 的 coverage 与 S2 artifact 有差异（例如因 shared test 内容的 CF01 修改），某文件可能低于 80%。Plan 的 fail-closed 机制会正确处理——stop 回 Controller。但 implementer 应预期这种可能性。

**Recommendation**：Acceptance 不依赖此问题的答案——§6.6 的 fresh validation 会直接产生结果。不需要 plan 修改。

### Q2：Guards 文件 `cc4c5267...9274` 有 21 个 tests；plan §6.1 candidate table 只列 6 个。这 21 个 tests 中有没有依赖尚未在当前 tree 中完成的 S2 基础设施？

Current evidence：guards 文件 import 链包括 `result_types.py`（public types）、`read_runtime_helpers.py`（normalize/dedup pipeline）、`read_runtime.py`（read composition）。这些 import 在当前 locked tree 均可解析（S2 已实现）。但 guards 中的 S2-era tests（如 `test_public_result_builders_copy_inputs_and_preserve_optional_reason`、`test_public_projection_ast_has_new_types_and_single_count_assignment`）直接依赖 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`——这些类型已在当前 tree 的 `result_types.py` 中定义。

**Risk**：低。S2 已完全实现在当前 locked tree 中。Guards 所有 21 个 tests 应可收集和执行。

**Recommendation**：不需要 plan 修改。在 §6.6 fresh validation 时自然验证。

### Q3：两个 proof JSON（prefix-five `43986a2d...b59fb`、prefix-six `b4c10342...dee`）是否仍在 `workspace/tmp/` 中？

这两个 JSON 是 coverage-statement-drift implementation 的产物，不在 plan correction 的 authored paths 中。它们可能作为 workspace tmp 文件存在或已被清理。Plan 不再要求重跑 prefix-five；prefix-six 需要 fresh erase 重跑。

**Risk**：如果 prefix-six fresh rerun 产生不同的 `executed_lines`（例如因 coverage.py 版本差异），exact 391/485 可能漂移。这是 §8 stop condition 明确覆盖的场景。

**Recommendation**：不需要 plan 修改。但 implementer 应在 handoff 中记录使用的 coverage.py 版本。

---

## 6. Residual Risk Classification

| Risk | Severity | Owner | Destination |
|---|---|---|---|
| §6.6 fresh 15-file coverage 与 S2 artifact 漂移 | LOW | §6.6 fresh validation | Fail-closed → Controller adjudication |
| coverage.py 版本差异导致 statement counting 漂移 | LOW | §8 stop condition "任一 numerator/denominator drift" | Fail-closed → Controller adjudication |
| Guards S2-era tests 中有未发现的 production dependency | LOW | §6.6 pytest collection | Fail-closed → Controller adjudication |
| R09-R12/deferred issues 被后续实现引入 regression | MEDIUM | R09-R12 plan review gates | Out of current plan scope |
| Exact test count 392 因八文件中任一文件维护而漂移 | LOW | §8 stop condition | Fail-closed → Controller重新评估 |

---

## 7. Non-Findings（已裁决不予重新包装）

以下话题经审查确认不是新 findings，不予重新包装：

- **Exact proof portability**：391/485 的 exact arithmetic 基于两个 fresh JSON 的 `executed_lines` 直接比较，证据链完整。不再重新辩论。
- **重复 private regex scan**：§6.7 的 positive/negative scans（A–F）都是 exact-key 扫描，各有明确的 owner root 和预期（零命中或有五联证据），不存在"重复扫描同一事实"的问题。
- **未来 Issue 能力（142/151/175/177/178）**：已在 §2.3 明确 out-of-scope，§8 有 stop condition。Plan 不依赖这些 Issue 的实现。
- **统一 authorization**：Topic 9 已裁决为 design clarification only，no code fix。Plan 不实现 authorization framework。
- **Host truncation 边界**：§6.4 的 forced-truncation test 只通过 public seam（pre-Host callable、Host completed envelope、公开 fetch_more）验证组合行为，不读取 Host 私有状态。Plan 不修改 Host。
- **S1 block evidence (B1/B2)**：S1 artifact 记录的 collection failure 与 coverage gap 已被 Controller 裁决且通过 S2 cumulative tree 解决。Plan 不再要求 S1 独立 validation gate。

---

## 8. Final SHA and Locks

| 项目 | 值 |
|---|---|
| Reviewed plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| Final plan SHA-256 | `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd` |
| Cumulative binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| Guards lock | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| Shared test lock | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| Helper deletion lock | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| Actual owner lock | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |

---

## 9. Reviewer Stop

本 artifact 完成 plan review。不授权 implementation、test、coverage、pyright、Ruff、smoke、code review、aggregate deepreview、commit、push 或 PR。未修改 plan、control、product、tests、README 或 prior review artifacts。

下一 gate：Controller adjudication of findings M1–M3 + L1–L2 → plan fix（如需要）→ re-review → accepted-plan commit → implementation authorization。
