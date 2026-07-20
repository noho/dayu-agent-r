# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift corrected plan review

## 1. Verdict

`PASS / ZERO_MATERIAL_FINDING`

本 artifact 是对 final plan SHA-256 `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd` 的完整、独立、adversarial plan review。审查覆盖整个计划，不是只看 patch。Reviewer verdict 不授权 implementation。

## 2. Review scope 与方法

### 2.1 审查范围

完整 final plan `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（1267 行），以及以下关联 artifacts：

- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-controller-adjudication.md`
- AgentCodex correction: `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-correction-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-correction-controller-validation.md`
- Stopped implementation: `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-implementation-codex.md`
- Prior coverage drift artifacts: `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-codex.md`, `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-controller-validation.md`

### 2.2 审查方法

独立验证、不依赖任何 prior reviewer verdict、不信任 plan 自报值。逐项匹配 SHA-256 locks、arithmetic、source/AST evidence、scope boundaries。

## 3. SHA-256 lock 独立验证

| Lock | Plan 声称值 | Reviewer 独立计算值 | 匹配 |
|---|---|---|---|
| Final plan | `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd` | `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd` | ✅ |
| Cumulative `dayu/fins + tests` binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` | ✅ |
| `read_runtime_helpers.py` deletion 后 | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` | ✅ |
| `read_runtime.py` actual owner | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | ✅ |
| Guards (candidate 6 后) | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` | ✅ |
| Shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | ✅ |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` | ✅ |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` | ✅ |
| Staged tree | empty | empty | ✅ |
| `git diff --check` | PASS | PASS | ✅ |

## 4. 391/485 exact arithmetic 验证

### 4.1 数学正确性

- prefix-five: `387/485 = 79.79381443%`。Reviewer 验算: 387 ÷ 485 = 0.7979381443... ✅
- candidate 6 增量: +4 covered statements
- prefix-six: `391/485 = 80.61855670%`。Reviewer 验算: (387+4) ÷ 485 = 391 ÷ 485 = 0.8061855670... ✅
- 阈值判定: `80.61855670% >= 80.00%` ✅
- Checker 条件: `covered == 391`, `statements == 485`, `percent >= 80.0` ✅

### 4.2 Fresh JSON 直接证据验证

Plan 声称两个 fresh JSON 的 `executed_lines` 同源比较证明新增行为 `[344, 346, 348, 442]`：

| 行号 | 代码 | 语义归属 |
|---|---|---|
| 344 | `return "material"` | `_resolve_document_type` material 分类分支 |
| 346 | `return "other"` | `_resolve_document_type` other 分类分支 |
| 348 | `return _CN_FORM_TYPE_TO_DOCUMENT_TYPE[form_type]` | `_resolve_document_type` CN FY 分类分支 |
| 442 | `return None` | `_normalize_form_type_for_matching(None)` normalization 短路 |

Reviewer 判断：前三行是 candidate 6 三条 assertion 的直接业务分类覆盖；第 442 行是 `form_type=None` 经 public owner `resolve_document_type_for_source` 进入 `_normalize_form_type_for_matching` 时的 normalization `return None`，之后同一调用才进入 `_resolve_document_type -> "other"`。该行是 public-owner 调用链的必经路径，不是 coverage padding 或偶然执行。四条 statements 构成不可分割的 public-owner 调用语义。

Plan 正确拒绝了把 checker 从 exact `391` 放宽到 `>=80%` 的提议，也正确拒绝了修改断言以避免覆盖第 442 行的提议。

## 5. [344,346,348,442] root evidence 验证

Root evidence 来源是同一 implementation task 在 candidate 6 mutation 前后分别产生的 fresh prefix-five 和 prefix-six coverage JSON 的 `executed_lines` 直接比较。这不是间接推断，而是同源文件的机械集合差。

Reviewer 确认：
- 证据来源是同一 locked tree、同一八文件、零 deselect 命令的两次 coverage run
- 比较方法是 `executed_lines` 集合差，不是 display rounding 或 aggregate 指标
- 第 442 行的归属已由 `resolve_document_type_for_source -> _normalize_form_type_for_matching` 的调用链直接证明
- 该证据链不依赖旧 Controller diagnostic、旧 incremental ledger 或旧 session JSON

## 6. 同一 task mutation-before prefix-five JSON 作为 predecessor proof 审计

### 6.1 可审计性

Plan 声称 prefix-five proof 由同一 implementation task 在 candidate 6 mutation 前、同一 locked tree 上产生。Reviewer 验证：

- Stopped implementation artifact（§2）记录了 re-entry locks 全部匹配后才执行 prefix-five
- Prefix-five JSON SHA-256 `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb` 被固定在 plan 中
- 实现 artifact（§4）完整记录了命令、输出和 SHA
- Guards SHA 在 prefix-five 前和 candidate 6 后分别记录为 `55318914...928d` 和 `cc4c5267...9274`，证明 mutation 发生在两次 coverage run 之间

该 predecessor proof 的可审计性通过：有完整命令、输出、SHA 和时序证据。

### 6.2 不要求回退

Plan §6.2.8 明确：continuation 保留 prefix-five JSON 为进入证据，不回退 candidate 6 重跑。Reviewer 判断合理：回退会破坏已证明正确的 owner contract test，且 predecessor evidence 已由 fresh JSON 和 guards SHA 变化完整记录。

## 7. Candidate 6 no-touch continuation 验证

### 7.1 Guards 文件验证

Reviewer 独立确认 `tests/fins/test_read_runtime_semantic_ownership_guards.py`：

- 唯一 production symbol import `resolve_document_type_for_source` 出现在 line 57 ✅
- 五项原 stable-owner tests 全部存在（lines 1482, 1567, 1636, 1731, 1817）✅
- Candidate 6 `test_document_type_resolver_projects_material_other_and_cn_categories` 存在于 line 1955 ✅
- Candidate 6 具有完整中文 docstring ✅
- Candidate 6 精确包含三条 assertions：material、other、annual_report ✅
- 无 `_resolve_document_type`、mapping constant、fake repository、monkeypatch、compat input ✅

### 7.2 Negative scans

| 扫描目标 | 预期 | 实际 |
|---|---|---|
| `_collect_available_document_types` in `dayu/` and `tests/` | 零命中 | 零命中 ✅ |
| Compatibility/private markers in guards | 零命中 | 零命中 ✅ |
| `sec_filing` in tools/prompts/READMEs/tests | 零命中 | 零命中 ✅ |
| `statement_locator` etc. in domain/processors/pipelines/tests | 零命中 | 零命中 ✅ |
| Deleted test nodes/imports in shared test | 零命中 | 零命中 ✅ |

### 7.3 八文件零 deselect 验证

Plan §6.6 prefix-six 命令使用八个测试文件、零 `--deselect`。Reviewer 确认该命令收集的测试集包含：

- S1 fiscal node: `test_sec_fiscal_inference_consumes_countless_xbrl_contract`
- S2 六个 normalize/dedup nodes
- Guards 六项（原五项 + candidate 6）
- 所有其它既有 focused/aggregate/回归 tests

该命令不包含 `--deselect`，不跳过任何 node，不参数化 omnibus。

## 8. First/shortest 结论验证

- Prefix-five: `387/485 = 79.79381443% < 80.00%` → 未过线
- Prefix-six: `391/485 = 80.61855670% >= 80.00%` → 精确过线
- 增量: candidate 6 是唯一新增测试，贡献 +4 covered statements
- 结论: candidate 6 是 first/shortest threshold-crossing prefix ✅

Plan 正确拒绝了新增第七项测试或追求 100% coverage 的提议。

## 9. Fail-closed 机制验证

Plan §8 定义了 18 项 stop conditions。Reviewer 逐项审查：

| 类别 | 覆盖完整性 |
|---|---|
| Producer essential field 缺失 | ✅ stop + 禁止 read 默认 |
| Method absent/empty | ✅ terminal 统一 `statement_not_found` |
| Provider raw total | ✅ internal inventory + 禁止 public 暴露 |
| S1 type change → S2 error | ✅ blocked intermediate + 继续 S2 |
| Dedup 需修改 fact | ✅ 深复制后修改 public fact |
| Description 字段清单 | ✅ 消费 owner helper |
| Host 截断 cursor envelope | ✅ §6.4 验证或 stop |
| 旧测试期待 locator/count | ✅ 迁移 fixture/assertion |
| Cumulative diff/lock 不匹配 | ✅ 不运行 proof，回 Controller |
| Candidate 6 drift | ✅ 立即 stop |
| Dead helper 复活 | ✅ stop 回 Controller |
| Prefix-five/six 不匹配 | ✅ 保留现场，stop 回 Controller |
| Numerator/denominator/threshold drift | ✅ fail closed |
| Dead-helper deletion 后 gate 失败 | ✅ 在 owner boundary 修复 |
| R09-R12/deferred issue | ✅ 记录 out-of-scope |

所有 stop conditions 均有明确的正向处置和禁止补救。无遗漏。

## 10. Semantic owner 验证

### 10.1 Financial producer contract (§4.1)

- Owner: `dayu.fins.domain.financial_result_contract` + actual processor ✅
- 删除 `statement_locator`、`statement_method_missing`、`statement_empty` ✅
- `reason` 改为 optional，七值闭集 ✅
- `data_quality` 三值闭集 ✅
- `scale` 消费唯一真源 `FinancialScale` ✅
- Terminal validator fail closed ✅

### 10.2 XBRL processor contract (§4.2)

- Owner: `dayu.fins.domain.xbrl_result_contract` + actual processor ✅
- 删除 `total`、`deduped_fact_count` ✅
- Flat typed query params ✅
- `fiscal_period` 消费 `FISCAL_PERIODS` 真源 ✅
- `min_value`/`max_value` 显式拒绝 bool ✅
- Unknown keys 统一失败 ✅

### 10.3 Public projection (§4.3)

- Owner: `dayu.fins.tools.result_types` ✅
- `PublicFinancialStatementResult` / `PublicXbrlQueryResult` 精确命名 ✅
- 旧 tools 类型名已删除，无 alias/re-export/wrapper ✅
- Domain producer 类型名保持不变 ✅
- `fact_count = len(returned_facts_copy)` 唯一赋值点 ✅
- Citation 使用 `Mapping[str, JsonValue]` 输入、独立 `dict[str, JsonValue]` 输出 ✅

### 10.4 Tool description (§4.4)

- 七值 reason 均有业务含义和 LLM-safe 下一动作 ✅
- 示例使用 `SEC_EDGAR`，不存在 `sec_filing` ✅
- `fiscal_period.enum` 从 `FISCAL_PERIODS` 派生 ✅
- Description 从 owner metadata/helper 派生，不手写第二份 ✅

## 11. Scope/sequence/overcoupling 验证

### 11.1 Scope

- S1 production diff 闭集: 12 个文件 ✅
- S2 production diff 闭集: 4 个文件 ✅
- S1 tests diff 闭集: 3 个文件 ✅
- S2 tests diff 闭集: 4 个文件 ✅
- README diff 闭集: 2 个文件 ✅
- Out-of-scope 明确列举: R09-R12、Issues 142/151/175/177/178、统一 authorization、Host/Engine/Service/UI ✅

### 11.2 Sequence

- S1→S2 是同一次破坏性 cutover ✅
- S1 不是独立 validation/review gate ✅
- S1/S2 之间不 stage/commit ✅
- 累计 S1+S2 tree 是唯一 acceptance validation ✅

### 11.3 Overcoupling

Plan 将 S1 和 S2 显式绑定为同一 destructive cutover，不允许中间 checkpoint。这消除了 S1 独立 acceptance 后 S2 延迟导致的 contract 不一致风险。Reviewer 判断这是正确的设计选择，不是 overcoupling：financial/XBRL contract 变更必须与 public consumer 迁移原子完成，否则中间状态会把旧 public consumer 与新 producer 组合声明为可接受。

## 12. Product/tests/README no-touch 验证

- Plan §10 明确：本 gate 只允许修改 plan 和新增 correction artifact ✅
- `git status` 显示 24 个 tracked modified + 4 个 untracked，其中本 gate 只增加两条 authored docs ✅
- 其余 22 个 tracked modified 是 pre-existing protected stopped-tree 状态 ✅
- `issues-implementation-control.md` 的修改是 pre-existing，不是本 gate 产生 ✅
- Staged tree 为空 ✅
- `git diff --check` PASS ✅

## 13. Topic 8-9 no-code 验证

- Topic 8 (Engine 240 chars): accepted as-is, no code fix ✅
- Topic 9 (Tool security wording): design clarification only, no unified authorization framework ✅
- Plan §2.3 明确将两者列为 out-of-scope ✅

## 14. 安全机制验证

- Path containment 保持（Fins design §9）✅
- DNS pin/peer proof 可配置（Topic 2）✅
- Web egress private/local blocking 可配置（Topic 2）✅
- Storage-state lifecycle 行为移至 Issue #178（Topic 2）✅
- R06/R07 storage/identity/revision/snapshot/citation owner no-touch ✅
- §6.7.E retained-security scan 覆盖 ✅

## 15. R07 no-touch 验证

Plan §6.1 明确：即使 `read_runtime.py` 在 allowlist，R07 snapshot acquire/borrow/release、cache/revision、citation 与 source-changed symbols 不允许修改。§6.7.D 的 `git diff -U0` propagation scan 验证只改 financial/XBRL projection symbols。

Reviewer 确认 `read_runtime.py` content SHA 保持 `27644d0d...0657`，证明无 R07 owner drift。

## 16. Issues 142/151/175/177/178 与 R09-R12/deferred boundaries 验证

| Item | Plan 声称状态 | Reviewer 确认 |
|---|---|---|
| Issue 142 (workspace migration) | out-of-scope | ✅ §2.3 |
| Issue 151 (write/upload assets) | out-of-scope | ✅ §2.3 |
| Issue 175 (Docling process isolation) | out-of-scope | ✅ §2.3, Fins design §7 reference |
| Issue 177 (Doc truncation) | out-of-scope | ✅ §2.3 |
| Issue 178 (storage-state lifecycle) | out-of-scope | ✅ §2.3 |
| R09 (direct-stream validator) | out-of-scope | ✅ §2.3 |
| R10 (HKEX) | out-of-scope | ✅ §2.3 |
| R11 (upload/placeholders) | out-of-scope | ✅ §2.3 |
| R12 (init/reset) | out-of-scope | ✅ §2.3 |
| 统一 authorization | out-of-scope | ✅ §2.3, Topic 9 |

## 17. 挑战项逐项审查

### 17.1 391/485 exact arithmetic 与 checker

**挑战**: 精确到 391/485 是否过于脆弱？coverage.py 版本升级可能导致 statement 计数变化。

**Reviewer 判断**: 这是 intended fail-closed 设计。Plan §8 明确 "任一 numerator、denominator...drift 都 fail closed 回 Controller"。精确匹配是防止环境/工具链 drift 伪装通过的安全机制。如果 coverage.py 升级改变了 statement 计数，正确响应是在新环境中重新建立 baseline，而不是放宽 checker。

### 17.2 [344,346,348,442] root evidence

**挑战**: 第 442 行 (`return None` in `_normalize_form_type_for_matching`) 是否真的属于 candidate 6 的业务语义？

**Reviewer 判断**: 是。`form_type=None` 的调用必须经过 `resolve_document_type_for_source -> _normalize_form_type_for_matching(None) -> return None` 才能进入 `_resolve_document_type -> "other"`。第 442 行是 public-owner 调用链的 normalization 短路，不是独立的、可删除的 coverage padding。删除第 442 行意味着 `_normalize_form_type_for_matching(None)` 不再返回 `None`，会改变 `form_type=None` 的业务语义。

### 17.3 同一 task mutation-before prefix-five JSON 作为 predecessor proof

**挑战**: 不在同一 session 重跑 prefix-five 是否削弱了 proof 可信度？

**Reviewer 判断**: 不削弱。Predecessor proof 由以下证据链完整支撑：
1. Guards SHA 从 `55318914...928d` 变为 `cc4c5267...9274`，证明 mutation 发生在两次 run 之间
2. 两次 run 的命令完全相同（同一八文件、零 deselect）
3. Prefix-five JSON SHA 被固定在 plan 中
4. 实现 artifact 记录了完整命令和输出

要求回退 candidate 6 重跑 prefix-five 会破坏已证明正确的测试，且不会产生新的信息。

### 17.4 Candidate 6 no-touch continuation

**挑战**: 不修改 candidate 6 但重跑 coverage 是否违反 "不授权任何 test delta"？

**Reviewer 判断**: 不违反。Plan §6.1 的 "不授权任何 production 或 test delta" 指不修改代码。重跑 coverage 是 validation 动作，不是 code delta。Plan §6.2.8 明确授权 "fresh erase 重跑同一八文件、零 deselect prefix-six"。

### 17.5 同一八文件零 deselect 392 passed prefix-six

**挑战**: 如何保证重跑时 test count 精确为 392？

**Reviewer 判斷**: 八个测试文件、零 deselect、零 skip/xfail 意味着收集的 test 集合是确定性的。392 = 391 (prefix-five 集合) + 1 (candidate 6)。如果 count drift，说明有 test 被新增、删除、skip 或 xfail，触发 fail-closed stop condition。

### 17.6 通过后完整从零 §6.6/§6.7

**挑战**: prefix-six proof 通过后还要从零重跑完整 validation 是否冗余？

**Reviewer 判断**: 不冗余。Prefix-six proof 只验证 `read_runtime_helpers.py` 的 coverage 阈值。§6.6/§6.7 的完整 validation 覆盖：15-file exact-key coverage、full pyright、scoped Ruff、三段 forced-truncation smoke、AAPL/HTML/no-statement real smokes、全部双向 source/AST/LLM/README/security/no-touch scans。这些维度不能由单一 coverage JSON 替代。

### 17.7 First/shortest 结论

**挑战**: 是否可能存在更短的 prefix（少于六个测试）也过线？

**Reviewer 判断**: 不可能。原五个 stable-owner tests 已经全部存在且贡献了 prefix-five 的 387/485。它们是按 owner family 顺序排列的完整连续前缀。要得到更短的 prefix，需要删除某个现有测试，但那会减少 covered statements，不会帮助过线。

### 17.8 Fail-closed

**挑战**: 18 项 stop conditions 是否有遗漏？

**Reviewer 判断**: 覆盖完整。涵盖了：producer contract drift、provider raw total、S1→S2 propagation、dedup mutation、description drift、Host truncation、旧测试兼容、tree lock drift、candidate 6 drift、dead helper 复活、prefix proof drift、threshold drift、gate failure、deferred scope 八个维度。无遗漏。

### 17.9 Semantic owner

**挑战**: Financial/XBRL/public 三层 owner 边界是否清晰？

**Reviewer 判断**: 清晰。
- Financial producer: `financial_result_contract.py` + actual processor → 只产出业务字段
- XBRL producer: `xbrl_result_contract.py` + actual processor → 只产出 query params + raw facts
- Public projection: `result_types.py` → 机械消费 producer，不重算、不补默认
- Tool description: `result_types.py` metadata → 从 public contract 派生

每层有唯一 owner，无双重赋值、无 fallback 补偿。

### 17.10 Scope/sequence/overcoupling

**挑战**: S1 和 S2 绑定为同一 cutover 是否过度耦合？

**Reviewer 判断**: 不是。Financial/XBRL producer contract 变更会立即破坏旧 public consumer 的 import graph。S1 独立 acceptance 会把 "新 producer + 旧 consumer" 声明为可接受状态，这是语义错误。原子 cutover 是正确的设计。

### 17.11 Product/tests/README no-touch

**挑战**: 本 gate 是否真的没有修改 product/tests/README？

**Reviewer 判断**: 确认。`git status` 中 22 个 tracked modified 是 pre-existing protected stopped-tree 状态，不是本 gate 产生。本 gate 只增加了两条 authored docs（plan 和 correction artifact）。

## 18. Findings

无 material finding。

### 18.1 已审查并确认无问题的项

| 审查项 | 结论 |
|---|---|
| 391/485 arithmetic | 数学正确，checker 精确匹配 |
| [344,346,348,442] root evidence | 直接 JSON 同源比较，第 442 行是必要 normalization |
| Predecessor proof 可审计性 | 完整命令/输出/SHA/时序证据 |
| Candidate 6 no-touch | Guards SHA 精确匹配，三条 assertions 完整 |
| 八文件零 deselect | 确定性 test 集合，392 = 391 + 1 |
| First/shortest | Prefix-five 未过线，prefix-six 精确过线 |
| Fail-closed | 18 项 stop conditions 覆盖完整 |
| Semantic owner | 三层边界清晰，无双重赋值 |
| Scope/sequence | S1+S2 原子 cutover 正确 |
| Overcoupling | 消除中间状态风险，非过度耦合 |
| Product/tests/README no-touch | 本 gate 只增加两条 authored docs |
| Topic 8-9 no-code | 正确保持 |
| 安全机制 | Path containment、DNS、egress 均保持 |
| R07 no-touch | Content SHA 不变 |
| Deferred boundaries | Issues 142/151/175/177/178 + R09-R12 全部 out-of-scope |
| Host truncation (§6.4) | Pre-Host/post-Host/fetch-more 三段验证设计合理 |
| 15-file coverage checker | Exact-key lookup，无 loose fallback |
| Ruff/pyright | Full pyright zero、scoped Ruff zero 要求正确 |

## 19. Open questions

无 open question。所有计划声称的 SHA-256 locks 均已独立验证匹配；所有 arithmetic、evidence、scope、security 和 deferred boundaries 均已审查确认。

## 20. Review metadata

| 项目 | 值 |
|---|---|
| Reviewer | AgentMiMo |
| Review type | Complete independent adversarial plan review |
| Reviewed plan SHA-256 | `bbbaeee260037544fbc7d0b0bfcb5d759240fa51ed793810468040fe7f191cdd` |
| Cumulative diff SHA-256 | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| Guards SHA-256 | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| Shared test SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| Helper SHA-256 | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| Actual owner SHA-256 | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| S1 artifact SHA-256 | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact SHA-256 | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| Staged tree | empty |
| `git diff --check` | PASS |
| Findings | 0 material, 0 accepted |
| Verdict | PASS / ZERO_MATERIAL_FINDING |
