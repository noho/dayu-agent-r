# WU-SEMANTIC-OWNERSHIP-01 / R08 Coverage-Statement Drift Corrected Plan Review — AgentMiMo

## 1. Review Target And Scope

- **Target**: `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`
- **Plan SHA-256**: `115a6429653e4011cf68fc9f3f7e9d7d08431696e0c1a80269c56d2de71dc401`
- **Scope**: 完整审阅最终计划，不是只审最后的 `--deselect` 修复。覆盖 R08-CR-PCF03 accepted finding、candidate 6 授权、prefix-five/prefix-six fresh proof、§6.6/§6.7 完整验收、dead-helper deletion、actual owner proof、no-touch 约束与全部 stop conditions。
- **Review posture**: constructively adversarial，默认假设 plan 可能在微妙或高成本的地方失败。

## 2. 入口锁验证

| Lock | Expected | Actual | Status |
|---|---|---|---|
| stopped 23-path binary diff | `3d9df8fe...ddf0` | `3d9df8fe...ddf0` | ✓ MATCH |
| `read_runtime_helpers.py` deletion SHA-256 | `1d7b4bf1...5ea9b` | `1d7b4bf1...5ea9b` | ✓ MATCH |
| `read_runtime.py` actual-owner SHA-256 | `27644d0d...0657` | `27644d0d...0657` | ✓ MATCH |
| guards test SHA-256 | `55318914...928d` | `55318914...928d` | ✓ MATCH |
| shared test SHA-256 | `01db5538...6692` | `01db5538...6692` | ✓ MATCH |
| S1 artifact SHA-256 | `d97eed50...5748` | `d97eed50...5748` | ✓ MATCH |
| S2 artifact SHA-256 | `08085bde...648` | `08085bde...648` | ✓ MATCH |
| staged tree | empty | empty | ✓ MATCH |
| plan SHA-256 | `115a6429...401` | `115a6429...401` | ✓ MATCH |

入口锁全部匹配。Stopped tree 未被污染。

## 3. Assumptions Tested

| # | Assumption | Evidence | Verdict |
|---|---|---|---|
| A1 | 旧 `_collect_available_document_types` 已从 `read_runtime_helpers.py` 删除 | `rg -n '\b_collect_available_document_types\b' dayu tests` 零命中；diff 确认 30 行 definition 已删除 | ✓ 成立 |
| A2 | 实际 owner `_collect_available_document_types_for_source_documents` 仍在 `read_runtime.py` 且保持 typed/sorted | 函数在 line 705，输入 `list[_SourceDocumentSummary]`，调用 `resolve_document_type_for_source`，返回 `sorted(doc_types)` | ✓ 成立 |
| A3 | `resolve_document_type_for_source` 是无下划线 public production owner | 定义在 `read_runtime_helpers.py:352`，无前导下划线，`read_runtime.py` line 119 import、line 723/886 调用 | ✓ 成立 |
| A4 | 三条 target branches 确实是 missing statements | `_resolve_document_type` 在 line 324-349：`source_kind == "material" → "material"`、`form_type is None → "other"`、`form_type in _CN_FORM_TYPE_TO_DOCUMENT_TYPE → e.g. "FY" → "annual_report"` | ✓ 成立 |
| A5 | S1/S2 实现已在 stopped tree 中完成，locator/internal-reason/total/dedup count 已从 production 删除 | `rg 'statement_locator\|StatementLocator\|statement_method_missing\|statement_empty\|processor_error:\|invalid_statement_result' dayu/fins/` 零命中；diff 确认 `StatementLocator` type、两个 internal reason 已删除 | ✓ 成立 |
| A6 | `_build_financials_payload` 无 production caller | `rg '_build_financials_payload' dayu/ tests/` 零命中 | ✓ 成立 |
| A7 | Guards 中原五个 stable-owner tests 全部存在 | `grep -n 'def test_' guards.py` 确认 1481/1566/1635/1730/1816 行五个 exact nodes | ✓ 成立 |
| A8 | 共享文件 test_fins_read_runtime.py 的六个 S2 nodes 已重命名（反映新 contract） | diff 确认六个 rename：如 `test_xbrl_query_payload_missing_total_fails_closed` → `test_xbrl_query_payload_missing_facts_fails_closed` | ✓ 成立 |
| A9 | 旧 `382/482`、`388/482` 值已被标为 superseded | 计划 §1.8 明确声明 "旧 `382/482 = 79.25%` 与 `388/482 = 80.50%` 预测全部 **superseded**" | ✓ 成立 |
| A10 | Issues 142/151/175/177/178、R09-R12、统一 authorization、Topic 8-9 均为 out-of-scope | §2.3 明确列出，control doc 确认 | ✓ 成立 |

## 4. Findings

### 4.1-未修复-低-candidate6 是否为 coverage padding

- **位置**: §4.1 accepted finding R08-CR-PCF03；§6.1 candidate 表第 6 项
- **问题类型**: 最佳实践偏离质疑（已关闭）
- **当前写法**: candidate 6 直接测试 `resolve_document_type_for_source` 的三条业务分类分支：material fallback、filing missing-form `other`、CN/HK `FY → annual_report`
- **反例/失败场景**: 如果这三个分支只是 coverage.py 的 missing lines 而非真实业务逻辑，则 test 只为 coverage padding
- **为什么有问题**: 需要确认这三条分支是否真实影响 LLM-facing `document_type`
- **直接证据**: `resolve_document_type_for_source` 是无下划线 production owner，在 `read_runtime.py` 有两个真实调用点（line 723、886），直接决定 LLM-facing `document_type` 字段。三条分支分别对应：(1) 未知 material form 归为通用 `material`；(2) filing 无 form 时归为 `other`；(3) CN/HK fiscal form `FY` 归为 `annual_report`。这些都是真实的业务分类语义，不是 coverage padding。
- **影响**: 无。Candidate 6 是 genuine public owner contract test。
- **建议改法和验证点**: 无需修改。Plan 的 §4 已明确说 "candidate 6 直接测试该 owner，是比恢复 compatibility/omnibus tests...更短且语义正确的阈值闭环"。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.2-未修复-低-prefix-five/prefix-six 命令集合正确性

- **位置**: §6.6 两段命令
- **问题类型**: 实施可执行性
- **当前写法**: prefix-five 与 prefix-six 均包含相同 8 个 test paths，无 `--deselect`；prefix-five 在 candidate 6 尚不存在时运行，prefix-six 在 candidate 6 已添加后运行
- **反例/失败场景**: 如果 prefix-five 命令意外包含 `--deselect` 排除某个 test，或 prefix-six 命令路径与 prefix-five 不一致
- **为什么有问题**: 中间版本曾残留 `--deselect`，导致 prefix-five 实际只形成 prefix-four
- **直接证据**: Controller validation (`wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-controller-validation.md` §2) 确认：最终计划 §6.6 中 prefix-five 与 prefix-six 命令各包含相同 8 个 test paths，均无 `--deselect`。当前 guards 仍为 entry hash 且 candidate 6 尚不存在，因此整文件 collection 必须包含原五个 exact nodes。
- **影响**: 无。命令集合已修正且受 controller 验证。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.3-未修复-低-387/485 与 390/485 数学正确性

- **位置**: §1.8、§6.6
- **问题类型**: 覆盖率算术验证
- **当前写法**: 删除 1 covered definition + 8 missing body statements 后：`all-five 388/494 - 9 = 387/485 = 79.79381443%`。candidate 6 新增 3 covered statements：`387 + 3 = 390/485 = 80.41237113%`
- **反例/失败场景**: 如果 coverage.py 对新 test 的计数与预期不符
- **为什么有问题**: Controller all-five 诊断实测 `387/485 = 79.79381443%`，与计划声称一致
- **直接证据**: Adjudication §3 明确记录 "1 个 covered definition statement + 8 个 missing body statements，共 9 statements"，Controller independent coverage data file 实测 387/485。三个 test assertions 覆盖三条 missing branches，预期增加 3 covered statements。
- **影响**: 无。数学一致。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.4-未修复-低-三断言可生成性

- **位置**: §6.1 candidate 表第 6 项；§6.6 prefix-six 命令后的断言模板
- **问题类型**: 实施可执行性
- **当前写法**: 三个直接调用断言：`form_type="UNLISTED_MATERIAL", source_kind=SourceKind.MATERIAL.value → "material"`；`form_type=None, source_kind=SourceKind.FILING.value → "other"`；`form_type="FY", source_kind=SourceKind.FILING.value → "annual_report"`
- **反例/失败场景**: 如果 implementation agent 无法从 plan 文本精确生成这三个 assertions
- **为什么有问题**: 断言模板已在 §6.6 中以 Python 代码形式给出，implementation agent 可直接复制
- **直接证据**: §6.6 包含完整 Python 代码块，精确指定三个 `resolve_document_type_for_source(...)` 调用及其预期返回值
- **影响**: 无。代码模板完整且可执行。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.5-未修复-低-唯一 import 约束

- **位置**: §6.1、§6.6、§6.7.F
- **问题类型**: 边界约束完整性
- **当前写法**: 只允许新增 `resolve_document_type_for_source` 一个 production import
- **反例/失败场景**: 如果 implementation agent 额外 import `_resolve_document_type`、`_CN_FORM_TYPE_TO_DOCUMENT_TYPE` 或其它 private symbols
- **为什么有问题**: Plan 多处明确禁止：§6.1 "不得直接测试 `_resolve_document_type`、读取 `_CN_FORM_TYPE_TO_DOCUMENT_TYPE` 或其它 mapping constant"；§6.7.F AST import assertion "相对 `55318914...928d` 唯一新增的 production symbol import 精确为 `{resolve_document_type_for_source}`"
- **直接证据**: §6.7.F 提供了 negative scan pattern 和 AST assertion script
- **影响**: 无。约束完整且可验证。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.6-未修复-低-§6.6/§6.7 从零验收完整性

- **位置**: §6.6、§6.7
- **问题类型**: 验收完整性
- **当前写法**: §6.6 指定 prefix-five proof → candidate 6 添加 → prefix-six proof → `coverage erase` → 完整 §6.6/§6.7 重跑
- **反例/失败场景**: 如果 implementation agent 在 prefix-six 过线后直接跳到 code review，不执行完整重跑
- **为什么有问题**: Plan §6.6 明确 "达标后停止新增测试，再次 `coverage erase`，从零完整重跑原 §6.6/§6.7"
- **直接证据**: §6.6 包含完整命令序列，§6.9 sequence 也明确 "再次 coverage erase，从零完整重跑原 §6.6/§6.7"
- **影响**: 无。Plan 顺序完整。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.7-未修复-低-dead-helper deletion 与 actual owner proof

- **位置**: §6.7.G
- **问题类型**: Owner 不变量验证
- **当前写法**: Source scan (`rg -n '\b_collect_available_document_types\b' dayu tests`) 预期零命中；AST proof 验证 old helper definition/caller/import 全零，actual owner definition/caller 各一
- **反例/失败场景**: 如果旧 helper 被意外恢复或 actual owner 被修改
- **为什么有问题**: Stopped tree 已锁定这两个文件的 SHA-256
- **直接证据**: 当前 `rg` 验证零命中；`read_runtime.py` 确认 `_collect_available_document_types_for_source_documents` 存在且 typed
- **影响**: 无。Deletion 和 owner 均已验证。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.8-未修复-低-Tests/README/product no-touch

- **位置**: §2.3、§6.1、§6.2.8、§6.8
- **问题类型**: 边界约束
- **当前写法**: Coverage-statement drift implementation 只允许修改 `tests/fins/test_read_runtime_semantic_ownership_guards.py` 新增 candidate 6 node 和唯一 import；production、shared test、其它 tests、README、S1/S2 artifacts 全部 immutable
- **反例/失败场景**: 如果 implementation agent 意外修改 production code 或其它 test files
- **为什么有问题**: Plan 多处明确禁止，且 §6.7.F 提供 exact diff scan 验证
- **直接证据**: §6.1 "后续 accepted implementation gate 只允许 `tests/fins/test_read_runtime_semantic_ownership_guards.py` 新增 candidate 6 exact node及唯一 `resolve_document_type_for_source` import"；§6.7.F "23-path stopped-tree manifest 做 exact diff scan"
- **影响**: 无。约束完整。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.9-未修复-低-R09-R12、deferred Issues、统一 authorization、Topic 8-9

- **位置**: §2.3
- **问题类型**: Scope boundary
- **当前写法**: 全部明确 out-of-scope
- **反例/失败场景**: 如果 implementation agent 顺手实现 Issue 175/177/178 或 R09 truncation routing
- **为什么有问题**: Plan §2.3 与 §8 stop conditions 均明确禁止
- **直接证据**: §2.3 "R09 direct-stream validator；R10 HKEX；R11 upload/placeholders；R12 init/reset；Issues 142、151、175、177、178；统一 authorization"；§8 "发现R09-R12/deferred issue → 记录out-of-scope并停止扩张 → 顺手实现" 为禁止补救
- **影响**: 无。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.10-未修复-低-旧 382/482、388/482、candidate4/5 first-prefix 已 superseded

- **位置**: §1.8、§5.4、§6.9
- **问题类型**: 历史值清理
- **当前写法**: §1.8 "旧 `382/482 = 79.25%` 与 `388/482 = 80.50%` 预测全部 **superseded**"；§6.9 "旧 incremental ledger、candidate-4 stop evidence与Controller all-five diagnostic只作historical/plan evidence"
- **反例/失败场景**: 如果 reviewer 或 implementation agent 误用旧值作为 acceptance criteria
- **为什么有问题**: 旧值基于错误的 statement count 假设
- **直接证据**: Adjudication §3 纠正了 root cause：旧 helper 是 9 statements 不是 12，旧预测全部 superseded
- **影响**: 无。旧值已明确标记。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

### 4.11-未修复-低-五项不可变双指令一致性

- **位置**: §6.1 candidate 表
- **问题类型**: 约束一致性
- **当前写法**: 原五个 stable-owner tests 的 owner、seam 与 exact business assertions 均不可弱化
- **反例/失败场景**: 如果 implementation agent 修改现有五个 tests 的断言或 seam
- **为什么有问题**: §6.1 明确 "原五项的单 owner、指定 seam 与 exact business assertions 都不可弱化"
- **直接证据**: Guards test SHA-256 锁定为 `55318914...928d`（implementation-entry lock），只允许因 candidate 6 node 和 import 改变
- **影响**: 无。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 无需修复
- **严重程度（低/中/高/严重）**: 无 finding

## 5. Open Questions

无。所有关键假设均有直接证据支持，所有边界约束均已明确指定。

## 6. Residual Risks

| # | Risk | Likelihood | Impact | Tracking |
|---|---|---|---|---|
| R1 | Fresh prefix-five/prefix-six 的 coverage.py 输出格式可能因环境差异而变化 | 低 | 高（fail-closed 回 Controller） | Plan §6.6 inline Python checker 处理标准 coverage.json 格式 |
| R2 | Implementation agent 可能错误编写 candidate 6 的中文 docstring | 低 | 低（pyright 不检查 docstring） | §6.7.F AST assertion 验证 node 存在性和 import |
| R3 | 未来 production 代码变更可能导致 485 statements 分母变化 | 不适用 | 不适用 | Stopped tree SHA-256 锁定，当前 gate 不允许 production 变更 |

## 7. Final Plan Review Conclusion

**Verdict: PASS**

Plan 是 code-generation-ready 的。所有 11 个 assumptions 全部有直接证据支持，0 个 material findings，0 个 open questions。

关键验证点：

1. **R08-CR-PCF03 完整性**: Accepted finding 完整记录了 root cause（旧 helper 是 9 statements 不是 12）、corrected arithmetic（387/485 = 79.79% < 80%）、candidate 6 必要性（三条 missing owner branches）和 stop conditions（drift fail-closed）。

2. **Candidate 6 是 genuine public owner contract**: `resolve_document_type_for_source` 是无下划线 production owner，有真实调用者，直接决定 LLM-facing `document_type`。三条 test assertions 覆盖 material/filing/CN-HK 三个业务分类分支。

3. **Prefix-five/prefix-six 命令集合正确**: 两段命令包含相同 8 个 test paths，无 `--deselect`。Prefix-five 在 candidate 6 不存在时收集原五项，prefix-six 在 candidate 6 添加后收集六项。

4. **387/485 与 390/485 数学一致**: Controller all-five 诊断独立验证 `387/485 = 79.79381443%`。Three new covered statements from candidate 6 → `390/485 = 80.41237113% ≥ 80%`。

5. **§6.6/§6.7 从零验收**: Plan 指定两次 `coverage erase`（prefix proof + 完整重跑），确保零残留。

6. **Dead-helper deletion/actual owner proof**: Source scan 和 AST proof 均已指定，当前验证零命中。

7. **No-touch 约束完整**: Production、shared test、其它 tests、README、S1/S2 artifacts 全部 immutable，§6.7.F 提供 exact diff scan 验证。

8. **旧值 superseded**: `382/482`、`388/482`、candidate-4/5 first-prefix 全部明确标记为历史证据。

9. **Scope boundary 清晰**: R09-R12、Issues 142/151/175/177/178、统一 authorization、Topic 8-9 code 全部 out-of-scope。

10. **Entry locks 全部匹配**: 8 个 SHA-256 哈希全部验证通过，staged tree 为空。
