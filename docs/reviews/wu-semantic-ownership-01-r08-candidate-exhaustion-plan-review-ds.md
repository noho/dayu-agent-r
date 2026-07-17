# WU-SEMANTIC-OWNERSHIP-01 R08 Candidate-Exhaustion Corrected Plan Review — AgentDS

## 1. Review Gate

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` |
| sub-WU | 既有 remediation `R08` |
| gate | 完整 corrected-plan independent adversarial review（第二路） |
| review target | 最终计划真源 `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| review scope | 完整累计计划（§0–§10），不是仅审新增段落 |
| review type | adversarial — 重点挑战 plan assumptions、反例、scope、sequencing、implementation slices、architecture boundaries、过度耦合、state machines、testing gaps 与 residual risks |
| 本 artifact 路径 | `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-review-ds.md` |

## 2. Protected Locks — Independent Verification

所有锁由本 reviewer 独立重算并精确匹配：

| 锁项 | 计划声明的值 | 本 reviewer 独立重算 | 结果 |
|---|---|---|---|
| 最终计划 SHA-256 | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` | **PASS** |
| stopped cumulative diff `dayu/fins + tests` | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` | **PASS** |
| guards test SHA-256 | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` | **PASS** |
| shared runtime test SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | **PASS** |
| staged paths | empty | empty（`git diff --cached --stat` 无输出） | **PASS** |

## 3. Review Methodology

按用户指定的 adversarial check 清单逐条审查，并结合以下维度做独立判断：

- 第一性原理：问题是否真实、方案是否最小、owner 是否正确。
- 反例搜索：是否存在违反 plan assumption 的代码/import/caller 证据。
- 架构边界：是否越界引入 Host/Engine/Service/UI 改动或 deferred issue 实现。
- 可执行性：命令、scan、deselect、threshold 是否真实可在当前 tree 执行。
- 完整性：validation matrix 是否覆盖所有 affected owners 与回归路径。

## 4. Material Findings

---

### R08-CE-PR-DS-F01 — Coverage numerator/denominator 硬编码依赖 coverage.py 计数语义

**Severity**: LOW

**Evidence**:

计划 §6.6 candidate-4 proof 硬编码期望精确值 `382/482=79.25%`：

```python
if covered != 382 or statements != 482 or percent >= 80.0:
    raise SystemExit(1)
```

同理 all-five proof 硬编码 `>=388/482=80.50%`。

这些数字来自 stopped tree 上 coverage.py 的单次计数。coverage.py 对不同 Python 构造（如 multi-line call、decorator、comprehension）的 statement 计数语义可能因版本变化。若 coverage.py 版本、Python 版本或 AST 处理差异导致 `num_statements` 变为 481 或 483，plan 会因硬相等检查而误失败，即使语义上 candidate-4 未过线、candidate-5 已过线的结论仍成立。

**Direct code evidence**:

```text
$ python3 -c "import coverage; print(coverage.__version__)"  # 当前环境版本
# 不同 coverage.py 版本对同一源码的 num_statements 计数可能不同
```

此外，plan 的 stop condition（§8）将 `Fresh candidate-4 proof 不是 382/482=79.25%<80` 列为必须停止条件，不允许因计数差异导致的微小偏移。

**Required fix**:

1. Candidate-4 proof 的 equality check 改为 inequality-only：断言 `percent < 80.0`，不硬编码 `covered` 和 `statements` 的精确值。保留 `statements` 的范围合理性检查（例如 `480 <= statements <= 490`）以防意外 large drift。
2. Candidate-5 proof 改为断言 `percent >= 80.0` 和 `covered >= 388`（最小覆盖行数不降级），但不硬编码 `statements` 精确值。
3. §8 stop condition 文本同步更新：将"不是 `382/482=79.25%<80`"改为"candidate-4 proof 未严格低于 80.00% 或 candidate-5 proof 未达到 >=80.00%"。
4. 实施 artifact 记录实际使用的 coverage.py 版本和实际 numerator/denominator，作为可复现证据而非 gate 判断依据。

**Controller note**: 当前 plan 的硬编码值在确定性的 stopped tree 上可精确复现，因此本 finding 是防御性改进而非阻塞性缺陷。若 Controller 确认当前 coverage.py 版本已锁定且后续不会变化，可降级为 INFO 并直接 PASS。

---

### R08-CE-PR-DS-F02 — Forced-truncation test 的 fixture 数据规模前置条件未受保护

**Severity**: LOW

**Evidence**:

计划 §6.4 段 2：

```python
_FORCED_XBRL_MAX_ITEMS = 1
# ...
# 测试不得硬编码当前 fixture 恰有三条 facts，只断言 pre-Host len(facts) > _FORCED_XBRL_MAX_ITEMS
```

test precondition 依赖 `len(pre_value["facts"]) > 1`。若 AAPL XBRL fixture 数据源变化导致只有 0 或 1 条 facts，该测试会因自身 precondition 失败而非因被测 contract 缺陷失败。测试的 failure signal 不够精确：precondition 失败与 contract 失败会产生混淆的诊断。

计划有 stop condition（§8）："若实施时 post-Host key set 改变、`fact_count` 缺失/变值，或任一公开 seam 无法同时观测 pre-Host typed value、Host completed envelope 与公开 fetch-more 结果，即与本 owner 裁决冲突，立即 stop 回 Controller"。但 fixture 数据量不足导致的 precondition 失败不在此 stop condition 覆盖范围内。

**Required fix**:

1. 测试前置条件失败时必须产出明确的 skip/诊断消息，说明 fixture 数据不足（例如 `pytest.skip("AAPL XBRL fixture has insufficient facts for truncation test")`），区别于 contract 断言失败。
2. 在 plan §6.4 或 §8 增加对应 stop condition：若 fixture 数据不足导致无法验证 forced-truncation，应记录为 blocked-by-fixture residual risk 而非停止整个 R08。
3. 或者：在测试中显式构造足够数量的 facts 而非依赖外部 fixture 的数据规模。但 plan 明确要求"复用 `_build_fins_aapl_xbrl_workspace` 与真实 fixture"，因此接受 fixture 依赖但需增加 skip guard。

---

### R08-CE-PR-DS-F03 — S1 中间 tree 的不可验证性增加了 cumulative cutover 的 blast radius

**Severity**: INFO（非阻塞，但需记录为 residual risk）

**Evidence**:

计划 §5.4 明确声明 S1 为"blocked intermediate evidence，不是 validation/review gate"：

> S1 中间 tree 定位：实现证据，不是 validation/review gate

> 不为 S1 中间 tree 运行或要求独立 exact-node collection、whole-file coverage session、full-pyright propagation-ledger pass、Controller immutable-tree lock、双路 code review、fix/re-review

计划承认 S1 的 full pyright 有五条红色诊断（"全部是新 producer contract 向尚未迁移 S2 consumer 的直接传播"），这五条在 S1 中间 tree 上无法修复——必须等到 S2 恢复 public import graph 后才能归零。

**Architectural assessment**:

该设计在架构上是正确的：producer contract 变更必然先于 consumer 迁移，中间状态的 pyright 红色是预期传播而非意外回归。S1 不单独 commit 也避免了"将 broken intermediate state 声明为可接受历史"的反模式。

但 residual risk 仍然存在：若 S2 实现时发现 S1 的 contract 设计存在根本性缺陷（例如 `fact_count` 字段类型与 consumer 期望冲突），回改 S1 的 cost 会被放大，因为 S1 已经完成了所有 processor 迁移且没有独立验证 gate 来提前发现。

**Required fix**:

无需修改 plan。但 aggregate deepreview（§7）和 Controller final closeout 必须显式确认：S1→S2 cumulative cutover 期间没有因缺乏 S1 独立验证而引入的隐蔽 contract defect。建议在 aggregate deepreview checklist 中增加此项。

---

### R08-CE-PR-DS-F04 — R08-CR-PCF02 是真正的 owner-boundary root fix，误删风险可控

**Severity**: N/A（确认性 finding，PASS）

**Evidence**:

本 reviewer 独立执行了以下 source/AST scan：

1. **旧 helper 零 caller/import 证明**：

```text
$ rg -n '\b_collect_available_document_types\b' dayu tests
dayu/fins/tools/read_runtime_helpers.py:393:def _collect_available_document_types(...)
```

仅定义行，全仓无 caller、无 import。确认 dead code。

2. **Actual owner 存在性证明**：

```text
$ rg -n '\b_collect_available_document_types_for_source_documents\b' dayu
dayu/fins/tools/read_runtime.py:705:def _collect_available_document_types_for_source_documents(
dayu/fins/tools/read_runtime.py:925:            available = _collect_available_document_types_for_source_documents(base_documents)
```

一个 definition、一个 production caller。typed 签名：`list[_SourceDocumentSummary] -> list[str]`，调用 `resolve_document_type_for_source` 并 `return sorted(...)`。

3. **`resolve_document_type_for_source` 仍有 caller**：

```text
$ rg -n 'resolve_document_type_for_source' dayu/fins/tools/read_runtime.py
119:    resolve_document_type_for_source,
723:            resolve_document_type_for_source(
886:                "document_type": resolve_document_type_for_source(
```

定义在 `read_runtime_helpers.py:352`，被 `read_runtime.py` 三处引用。删除 dead helper 后该函数仍有 production caller。

4. **旧 helper 函数体结构**：

```text
Line 409: doc_types: set[str] = set()        # AnnAssign
Line 410: for doc in documents:                # For (lines 410-419 body)
Line 420: return sorted(doc_types)             # Return
```

函数体内 12 个 executable lines（lines 409–420），全部在 stopped tree coverage 中为 missing。删除后 coverage 分母减少 12，数学闭包正确。

5. **`_optional_number` 已拒绝 bool**：

```text
dayu/fins/domain/xbrl_result_contract.py:362:    if isinstance(value, bool):
dayu/fins/domain/xbrl_result_contract.py:363:        raise ValueError(...)
```

plan §4.2 要求的 bool 显式拒绝已存在于当前代码中，S1 只需补 owner tests。

**Conclusion**:

`R08-CR-PCF02` 的动机成立，删除目标精确，无 false positive（不会误删有 caller 的代码），无 false negative（旧 helper 确实全仓零引用）。唯一的 production delta 可机械验证。**PASS**。

---

### R08-CE-PR-DS-F05 — Plan 正确地禁止了所有禁止模式

**Severity**: N/A（确认性 finding，PASS）

**Evidence**:

逐条核验 plan 对以下禁止模式的处置：

| 禁止模式 | Plan 处置 | 证据位置 |
|---|---|---|
| compatibility test / re-export / wrapper | 显式禁止 | §2.3 明确 out-of-scope，§4.3 禁止 alias/re-export |
| fake-only test | 显式禁止 | §6.1 "不得形成 fake-only test" |
| private-helper direct test | 显式禁止 | §6.1 只允许 public seam；第 5 项是唯一 module-helper 例外 |
| 第六个 coverage node | 显式拒绝 | §2 controller adjudication 明确拒绝，§6.6 证明五项是 first/shortest prefix |
| 无关 dead-code cleanup | 显式拒绝 | §2.3 "除 `R08-CR-PCF02` 唯一授权...外的任何 dead-code 清理" |
| 降低 80% threshold / pragma / omit | 显式拒绝 | §2 controller adjudication，§8 stop conditions |
| 恢复/搬运原四 shared-file nodes | 显式禁止 | §5.1 固定 symbol boundary，§6.7.F source scan |
| deferred Issues (142/151/175/177/178) | 显式 out-of-scope | §2.3, §6.7.E allowlist scan |
| 统一 tool authorization | 显式 out-of-scope | §2.3 |
| Topic 8-9 code | 显式 out-of-scope | §0 notes，§2.3 |
| S1/S2 artifacts 修改 | 显式 no-touch | §6.1 re-entry locks，§6.7.F SHA-256 verification |
| Host/Engine/Service/UI 修改 | 显式 out-of-scope | §2.3, §6.7.E no-touch scan |
| `dayu/config/prompts/**` 修改 | 显式不改 | §3.4, §6.7.B negative scan |
| compatibility shim / cast / ignore / skip / xfail | 显式禁止 | §5.4, §6.1, §8 stop conditions |

**Conclusion**: 所有禁止模式均有显式 plan 文本阻止，且有对应的 scan/stop condition 作为 enforcement。**PASS**。

---

### R08-CE-PR-DS-F06 — Candidate-4/Candidate-5 coverage proof 命令真实可执行

**Severity**: N/A（确认性 finding，PASS）

**Evidence**:

1. **Deselect 语法**：`--deselect tests/fins/test_read_runtime_semantic_ownership_guards.py::test_search_next_section_projection_ranks_business_evidence_per_query` 是标准 pytest node ID 格式。

2. **Coverage 命令**：`python -m coverage erase && python -m coverage run -m pytest ... && python -m coverage json` 是标准 coverage.py workflow。

3. **JSON checker**：使用 `json.loads(Path(sys.argv[1]).read_text())["files"][target]["summary"]` 读取 coverage JSON 的标准字段 `covered_lines`、`num_statements`、`percent_covered`。这些字段在 coverage.py ≥5.0 中稳定存在。

4. **Manifest generation**：`git diff --name-only -z --diff-filter=ACMR -- ':(top,glob)dayu/fins/**/*.py'` 正确使用 NUL 分隔符和 top-level glob pathspec。

5. **Exact-key checker**：以 repo-relative path 对 coverage JSON `files` 做 exact key lookup，拒绝 basename/suffix/absolute-path/路径规范化等 loose fallback。这是正确的严格匹配策略。

6. **Threshold assertion**：两个 proof 都使用 `raise SystemExit(1)` 在条件不满足时非零退出，可被 shell `&&` chain 正确捕获。

7. **测试集组成**：八个测试文件覆盖所有 S1/S2 affected areas：
   - `test_financial_read_contracts.py` — S1 owner contracts + actual processors
   - `test_sec_pipeline_download.py` — S1 fiscal extraction
   - `test_fins_read_runtime.py` — S1 fiscal node + S2 normalize/dedup nodes
   - `test_read_runtime_semantic_ownership_guards.py` — S2 stable-owner guards
   - `test_processor_read_consistency.py` — S2 snapshot consistency
   - `test_processor_registry.py` — registry propagation (expected zero diff)
   - `test_fins_ingestion_tools.py` — ingestion regression (expected zero diff)
   - `test_fins_storage_provider.py` — AAPL/HTML/no-statement smokes + forced-truncation

**Conclusion**: 所有命令语法正确、可执行、可机械验证。**PASS**。

---

### R08-CE-PR-DS-F07 — §6.6/§6.7 完整 acceptance validation 足以覆盖全部 affected tests 与 scans

**Severity**: N/A（确认性 finding，PASS）

**Evidence**:

逐项核验 coverage：

| 验证项 | Plan 覆盖 | 证据 |
|---|---|---|
| S1 focused owner matrix | §6.6: `pytest ... -k 'financial or statement or xbrl or quality or reason or fiscal'` | 覆盖 financial/XBRL contract owner tests |
| S1 fiscal exact node | §6.6: `pytest ...::test_sec_fiscal_inference_consumes_countless_xbrl_contract` | 覆盖 S1 唯一 shared-test node |
| S2 focused/public matrix | §6.6: 六个测试文件全集 | 覆盖所有 S2 public projection/consumer |
| Forced-truncation smoke | §6.6: 显式 `test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation` | 覆盖 §6.4 组合风险 |
| AAPL/HTML/no-statement real smokes | §6.6: 三个显式 node IDs | 覆盖真实 fixture 路径 |
| R08 aggregate matrix | §6.6: 八个测试文件全集 | 覆盖所有 affected tests |
| Full Fins regression | §6.6: `pytest tests/fins -q` | 覆盖零 diff 回归 |
| 15-file whole-file exact-key coverage | §6.6: `git diff --name-only` + exact-key JSON checker | 每个 changed production 文件 ≥80% |
| Full pyright | §6.6: `pyright`（隐式，通过项目配置） | 零错误 |
| Changed Python scoped Ruff | §6.6: `git diff --name-only` + `ruff check` | 零 |
| Internal positive inventory scan | §6.7.A: raw total 六文件扫描 | 零保留项 |
| Public/LLM negative scan | §6.7.B: tools + prompts + READMEs + tests | 零命中 |
| `fact_count` unique owner scan | §6.7.C: tools + prompts + READMEs | 单一赋值 owner |
| R07 no-touch scan | §6.7.D: `git diff -U0` on `read_runtime.py` | 零语义 diff |
| AST/README/security/scope scans | §6.7.E | 全覆盖 |
| R08-CR-CF01 correction scans | §6.7.F: shared file deletion scan + guards negative scan + AST assertions | 零命中 |
| R08-CR-PCF02 scans | §6.7.G: source scan + AST proof | 全零 + actual owner verified |
| README trigger check | §6.8 | 无机械修改 |
| `git diff --check` | §6.6 末尾 | 零 |

**Conclusion**: 验证矩阵完整，无遗漏。**PASS**。

---

### R08-CE-PR-DS-F08 — 旧 plan/ledger/green/review 已明确标记失效

**Severity**: N/A（确认性 finding，PASS）

**Evidence**:

Plan 显式声明以下旧 artifact/lock 失效：

1. §0 记录 accepted plan lineage：`a79268ea...2a02`（correction 前）→ `0145d1de...a3e9`（correction 后）。
2. §6.9 显式声明：`R08-CR-CF01` 已使原 review lock `4d346f2b...d4b`、原 Controller validation 与两路 code review 失效。
3. §6.9 显式声明：`65a92406...6dff` stopped tree 仍因 `388/494=78.54%` 未完成 §6.6/§6.7，不能复用旧 incremental ledger 或旧绿色。
4. §6.6 显式要求：`R08-CR-PCF01` 的旧增量 ledger 只作 historical evidence，不得复用为新 tree acceptance。
5. §6.9 明确顺序：corrected-plan review → accepted-plan commit → delete helper → fresh proofs → full validation → new lock → dual code review。
6. §6.9 明确：删除使 stopped diff `65a92406...6dff` 失效，Controller 必须只在最终全绿 tree 上建立新 lock。
7. §9 checklist 显式要求标记：旧 plan SHA/reviews、`4d346f...d4b` review lock、`7a7ebf...1d6d` validation/reviews 与 `65a92406...6dff` stopped incremental ledger 均标记失效。

**Conclusion**: 旧 artifact/lock 失效声明完整，无矛盾。**PASS**。

---

### R08-CE-PR-DS-F09 — State/gate/stop conditions 整体一致，存在一处边界模糊

**Severity**: LOW

**Evidence**:

Plan §6.9 定义了精确的 gate 顺序：

```text
AgentCodex plan-only correction
-> Controller plan-diff/protected-tree validation
-> AgentMiMo + AgentDS complete corrected-plan review
-> accepted plan findings fix（若有）
-> complete corrected-plan re-review / Controller adjudication
-> corrected-plan accepted local commit
-> AgentCodex 从 65a92406...6dff stopped tree 只删除 dead duplicate helper
-> §6.7.G source/AST proof
-> §6.6 fresh exclude-candidate-5 proof
-> §6.6 fresh all-five proof
-> 再次 coverage erase，从零完整重跑原 §6.6/§6.7
-> Controller 锁定新的 changed-path content manifest / binary diff hash
-> AgentMiMo + AgentDS 对完整 S1+S2+fix tree code re-review
-> Controller 逐条关闭
-> aggregate deepreview
```

该顺序清晰且无内部矛盾。

**但是**，存在一处边界模糊：corrected-plan accepted local commit 的时机。§0 说"新计划 accepted local commit 前，不得删除 helper"，§6.9 也说"Corrected plan 未经双路 review/re-review 与 accepted-plan commit 前，不得删除 helper"。但 §0 同时说本 gate 是"plan-only correction；完成后停回 Controller，由 Controller 派发两路完整 corrected-plan review"。这里"本 gate 完成后"指的是 plan correction artifact 写入完成后 → Controller validation → 两路 review。commit 应该发生在两路 review + fix + re-review 全部关闭之后。

当前顺序是正确的：Controller validation（已完成）→ 两路 review（当前 gate）→ fix（若有）→ re-review → accepted-plan commit → delete helper → implementation。无矛盾。

**Required fix**:

无需修改 plan 逻辑。建议在 Controller adjudication 中显式确认：commit 的 exact trigger 是"两路 review 均已 PASS 或 accepted findings 全部 fix/re-review 关闭且 Controller 逐条确认"。

---

### R08-CE-PR-DS-F10 — Import 清理边界存在轻微歧义

**Severity**: LOW

**Evidence**:

Plan §6.1 授权：

> 不得修改 `resolve_document_type_for_source`，不得修改
> `dayu/fins/tools/read_runtime.py::_collect_available_document_types_for_source_documents`，也不得修改
> 任何其它 production symbol。

同时 §6.6 要求"全部实际修改 Python 文件 scoped Ruff 必须零"。

删除 `_collect_available_document_types` 后，`read_runtime_helpers.py` 中该函数使用的 builtin names（`set`、`sorted`）不会产生 unused import。函数体内调用的 `resolve_document_type_for_source` 是同一文件内定义的函数，不是 import。因此删除该函数不会产生新的 unused import。

**Direct verification**:

```text
# _collect_available_document_types 使用的 names：
# - resolve_document_type_for_source: defined in same file (line 352), still used by read_runtime.py
# - isinstance: builtin
# - set: builtin
# - sorted: builtin
# - Mapping, JsonValue: used by many other functions in the same file
```

**Conclusion**: 删除 dead helper 不会产生 unused import，Ruff scoped check 可自然通过。本 finding 不构成实际风险。**PASS**（经 direct verification 消除歧义）。

---

### R08-CE-PR-DS-F11 — Whole-file coverage 与 changed-line coverage 的边界决策正确

**Severity**: N/A（确认性 finding，PASS）

**Evidence**:

Plan §6.1 和 §6.6 坚持 whole-file exact-key `>=80.00%` 阈值，拒绝 changed-line coverage、aggregate `--fail-under`、pragma/omit 或其它 bypass。

该决策的动机在 §1.6 中有清晰说明：R08 normalize/dedup changed-owner 的完整调用闭包即使全部覆盖也至多 `351/494 = 71.05%`，当前 whole-file 80% gate 与稳定 owner 测试授权数学上冲突。但这不是降低阈值的理由——而是说明需要修测试授权（通过增加 stable-owner tests）或修 production（通过删除 dead code）。

Plan 选择的路径（五种 stable-owner tests + 删除 dead duplicate）是在不弱化验收标准的前提下解决冲突的最小正确方案。AGENTS.md 明确要求单文件测试覆盖率目标 `>= 80%`，plan 未弱化该约束。

**Conclusion**: 边界决策正确，符合 AGENTS.md。**PASS**。

---

### R08-CE-PR-DS-F12 — `FiscalPeriod` / `FISCAL_PERIODS` 共享 owner 方案已验证存在

**Severity**: N/A（确认性 finding，PASS）

**Evidence**:

```text
$ rg -n 'FISCAL_PERIODS' dayu/fins/domain/filing_semantics.py
79:FISCAL_PERIODS: Final[frozenset[FiscalPeriod]] = frozenset(

$ rg -n 'FISCAL_PERIODS' dayu/fins/domain/xbrl_result_contract.py
11:from dayu.fins.domain.filing_semantics import FISCAL_PERIODS, FiscalPeriod, normalize_fiscal_period
327:        ValueError: 字段不是 ``FISCAL_PERIODS`` 中的精确值时抛出。
334:    if not isinstance(value, str) or value not in FISCAL_PERIODS:
```

`FISCAL_PERIODS` 已存在于 `dayu.fins.domain.filing_semantics`，值集为 `FY|H1|Q1|Q2|Q3|Q4`（standard `FiscalPeriod` Literal）。`xbrl_result_contract.py` 已有 import 和 validator 使用。Plan 要求 tool schema 的 `fiscal_period.enum` 也从同一 owner 派生（`sorted(FISCAL_PERIODS)`），不自写第二份 literal。该方案在架构上正确且当前代码已部分实现。

**Conclusion**: 共享 owner 方案技术上可行且已有代码基础。**PASS**。

---

## 5. Findings Summary

| ID | Severity | 简述 | 处置 |
|---|---|---|---|
| R08-CE-PR-DS-F01 | LOW | Coverage 硬编码 numerator/denominator 依赖 coverage.py 版本 | NEEDS FIX — 改为 inequality-only check |
| R08-CE-PR-DS-F02 | LOW | Forced-truncation test 的 fixture 数据规模前置条件未受保护 | NEEDS FIX — 增加 skip guard 或 stop condition |
| R08-CE-PR-DS-F03 | INFO | S1 中间 tree 不可验证，cumulative cutover blast radius | 记录为 residual risk，aggregate deepreview 检查 |
| R08-CE-PR-DS-F04 | PASS | R08-CR-PCF02 是真正的 owner-boundary root fix | 无需修改 |
| R08-CE-PR-DS-F05 | PASS | 所有禁止模式均被正确禁止 | 无需修改 |
| R08-CE-PR-DS-F06 | PASS | Coverage proof 命令真实可执行 | 无需修改 |
| R08-CE-PR-DS-F07 | PASS | §6.6/§6.7 完整 acceptance validation 覆盖充分 | 无需修改 |
| R08-CE-PR-DS-F08 | PASS | 旧 plan/ledger/green/review 已明确标记失效 | 无需修改 |
| R08-CE-PR-DS-F09 | PASS | State/gate/stop conditions 一致（经澄清） | 无需修改 |
| R08-CE-PR-DS-F10 | PASS | Import 清理无实际歧义（经 direct verification） | 无需修改 |
| R08-CE-PR-DS-F11 | PASS | Whole-file coverage 边界决策正确 | 无需修改 |
| R08-CE-PR-DS-F12 | PASS | FiscalPeriod/FISCAL_PERIODS 共享 owner 可行 | 无需修改 |

## 6. Overall Verdict

**NEEDS FIX** — 两个 LOW severity findings (F01, F02) 需要 plan 修正。其余所有 adversarial checks 均 PASS。

两个 LOW findings 都不阻塞 plan 的核心正确性：
- F01 是防御性改进，防止 coverage.py 版本差异导致 false failure。
- F02 是 fixture precondition guard，防止测试因数据不足产生混淆诊断。

所有 HIGH/MEDIUM severity 检查项（owner-boundary correctness、误删风险、禁止模式、validation completeness、state consistency、deferred scope isolation）均 PASS。

## 7. Residual Risks (beyond plan scope)

| Risk | 分类 | Destination |
|---|---|---|
| S1→S2 cumulative cutover 期间缺乏独立 S1 gate，隐蔽 contract defect 可能延迟到 aggregate validation 才发现 | architectural decision, accepted | aggregate deepreview 显式检查 |
| coverage.py 版本变化导致 exact statement count 偏移 | tooling dependency | F01 fix 后缓解 |
| AAPL XBRL fixture 数据源变化 | external fixture dependency | F02 fix 后缓解 |
| forced-truncation public seam 在三段链路中任一段不可观测 | Host API contract dependency | plan §6.4 stop condition 已覆盖 |
| 15-file whole-file coverage 在 `read_runtime_helpers.py` 以外的 changed files 可能已有缺口 | prior cumulative tree state | aggregate validation 逐文件 checked |

## 8. Artifact Integrity

本 artifact 自身 SHA-256 应在写入完成后由外部命令重算，不在 body 中自嵌入。

Review locks verified at review start:
- Plan SHA-256: `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9`
- Stopped cumulative diff: `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff`
- Guards: `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d`
- Shared test: `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`
- Staged: empty
