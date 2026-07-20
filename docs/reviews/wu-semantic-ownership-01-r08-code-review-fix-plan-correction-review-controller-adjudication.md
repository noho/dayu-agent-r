# WU-SEMANTIC-OWNERSHIP-01 R08 Corrected-Plan Review Controller Adjudication

## 1. Gate 与证据锁

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`；本次仍是 R08 cumulative code-review fix 的 plan correction continuation，不是新 WU、feature、issue 或独立 sub-WU。
- corrected plan：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`。
- review-entry plan SHA-256：`86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65`。
- protected `dayu/fins + tests` binary diff SHA-256：`7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`。
- AgentMiMo review：`docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-mimo.md`，SHA-256 `69af2c4ac91cf48b291dec6e134f7dc69842ca62d625d94bcb29ba494a286c9f`。
- AgentDS review：`docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-ds.md`，SHA-256 `3c4d2dd8bfc7d9268abb7322c9bfc01a8f5f5cc623d98c3f370240eedec9a83c`。
- 两路 reviewer 均独立重算并匹配 plan 与 protected diff；review 期间 plan、product、tests、README、control 与 prior artifacts 未发生 reviewer 修改。

## 2. 第一性原理裁决

本次 correction 的真实动机仍成立：删除 plan-external shared-file tests 后，窄 changed-symbol closure 的 whole-file coverage 理论上限低于既定 80%，因此必须在同一 owner test path 以最小 stable-owner evidence 补足，而不能恢复 compatibility/omnibus tests、降低阈值或用 coverage bypass。

五个 ordered candidate 的 public seam、最短连续前缀、首次达到 80% 即停止、五项耗尽仍不足则回 Controller、完整累计验证与 security/deferred no-drift 均已由两路 review 核对为可执行。当前没有产品裁决冲突，也不需要重新向用户确认。

## 3. Findings 逐项裁决

### 3.1 AgentMiMo

AgentMiMo 报告 `0 material finding / 0 blocker`。接受其正向证据，不产生新的 fix 项。

### 3.2 AgentDS M1 — `available_document_types` 顺序

**裁决：REJECTED AS FACTUALLY INCORRECT / ALREADY GUARDED。**

直接证据：

- `dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types` 使用 `set[str]` 去重并明确 `return sorted(doc_types)`；public suggestion 的 `available_document_types` 不继承 repository iteration order。
- corrected plan §6.1 candidate 1 已明确写出“不得依赖 repository 返回顺序”。

因此 finding 所述 public output 顺序依赖不存在；再强制 `set()`/`sorted()` assertion 只是重复实现细节，并可能削弱对 owner 已承诺 canonical sorted projection 的验证。无需修改计划。

### 3.3 AgentDS M2 — section/table fixture 异常转换输入

**裁决：ACCEPTED，编号 `R08-CR-PCPR-F01`。**

直接证据：

- `FinsReadRuntime._read_section_with_borrow` 只捕获 processor `read_section` 的 `KeyError`，随后投影为 public `FinsReadArgumentError`。
- `FinsReadRuntime._get_table_with_borrow` 对 processor `read_table` 使用相同 `KeyError -> FinsReadArgumentError` 转换。
- 当前 candidate 2/3 只规定最终 public typed failure，没有把 typed processor fixture 的协议输入异常写清；若 fixture 使用其它异常，会测试错误路径而非 production owner 的转换链。

精确修复要求：

1. 只修改 corrected plan 与新的 Codex plan-fix artifact；不得修改 product/tests/README/prior artifacts/control。
2. 在 candidate 2 与 candidate 3 的 fixture 输入中明确：未知 section/table ref 必须由 typed `DocumentProcessor` fixture 抛 `KeyError`，由 public runtime 精确转换为 `FinsReadArgumentError`。
3. assertion 必须观察 public runtime failure；不得直接断言 fixture，不得引入 loose exception、private method/state 或第二套 failure normalization。
4. 不改变五候选顺序、exact node names、coverage ledger、80% stop condition、path/symbol allowlist、protected tree 或产品契约。

### 3.4 AgentDS L1 — candidate 4 form type 间接驱动

**裁决：REJECTED AS ALREADY COVERED OBSERVATION。**

计划已要求通过真实 document metadata 与 typed taxonomy-capable processor 提供明确 form/taxonomy business facts，并禁止 private state。该观察只说明 fixture 装配复杂度，没有缺失 owner、错误 API 或不可执行证据。

### 3.5 AgentDS L2 — AST import assertion 的“新增”限定

**裁决：REJECTED AS ALREADY PRECISE。**

§6.7F 已明确比较 correction-entry tree 的“新增” imports，并允许只在实际进入 candidate 5 时新增 `build_search_next_section_fields`；既有 imports 不属于增量集合。无需增加静态白名单或放宽 scan。

### 3.6 AgentDS L3 — coverage 非单调理论风险

**裁决：REJECTED AS ALREADY CLOSED BY MECHANICAL LEDGER/STOP。**

§6.6 要求每步记录 `covered / statements / percent / decision`，§8 要求任何 gate 失败即停回 Controller；这不依赖 statement count 恒定。没有代码证据表明当前 node 增量会改变 production statement inventory。

## 4. Gate 结论

- accepted finding：仅 `R08-CR-PCPR-F01`。
- rejected findings/observations：DS M1、L1、L2、L3；MiMo 无 material finding。
- 当前 gate：AgentCodex plan-only finding fix。
- 修复后必须由 Controller 核对 plan SHA、protected diff、精确文案与无越界，再由 AgentMiMo / AgentDS 对完整修订计划并发 re-review；不能只看修改段落。
- product/test continuation、累计 code re-review、aggregate deepreview、implementation commit、R09-R12、deferred issue、统一 authorization、push 与 PR 继续未授权。
