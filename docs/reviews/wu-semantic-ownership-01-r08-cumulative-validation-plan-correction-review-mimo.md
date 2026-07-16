# WU-SEMANTIC-OWNERSHIP-01 R08 Cumulative Validation Plan Correction — AgentMiMo Review

## 1. Review target and scope

- reviewed target: `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（corrected plan, SHA-256 `4ff2c00c5999cf20ff314afd7e9a0fa041c32d2f36c23566d21752887c997e3d`）
- scope: complete corrected plan adversarial review, not incremental diff
- context artifacts read:
  - `docs/reviews/wu-semantic-ownership-01-r08-s1-validation-plan-drift-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-controller-validation.md`
  - `docs/host/issues-implementation-control.md`（R08 相关行）
- SHA verification:
  - corrected plan SHA-256: `4ff2c00c5999cf20ff314afd7e9a0fa041c32d2f36c23566d21752887c997e3d` — **PASS**
  - protected 14-path binary diff SHA-256: `0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57` — **PASS**
  - `git diff --cached --name-only`: empty — **PASS**

## 2. Assumptions tested

1. S1→S2 实现顺序保留且无中间 commit/checkpoint
2. S1 artifact 定位为 blocked intermediate evidence，不冒充 acceptance
3. §6.6 成为唯一累计 validation 真源
4. Coverage 对每个实际 changed production Python 文件独立 `>=80.00%`
5. shared test file `test_fins_read_runtime.py` 的 S1/S2 symbol 边界无歧义
6. cumulative code review → fix/re-review → aggregate deepreview → commit 顺序正确
7. forced-truncation、R07 no-touch、retained security、deferred/no-code scope 未被削弱
8. §4 product contracts、§5.1/§6.1 allowlists 未改变
9. coverage JSON 逐文件读取/阈值判定可执行

## 3. Findings

### 1-未修复-低-Ruff 命令使用占位符而非具体文件列表

- **位置**: §6.6 累计 validation gate 命令矩阵，第 635 行
- **问题类型**: 不可直接实施
- **当前写法**: `python -m ruff check <S1+S2全部实际修改的Python文件>`
- **反例/失败场景**: 实施 Agent 可能误解占位符范围——是只包含 production+test allowlist 的并集（16+7=23 文件），还是包含所有 `git diff --name-only` 的 Python 文件（包括 `docs/host/issues-implementation-control.md` 不含 Python 但需确认）。若 Agent 只传 production 文件，遗漏 test 文件中的 Ruff 违规则无法通过 scoped Ruff 归零的要求。
- **为什么有问题**: 计划在 §5.1 和 §6.1 分别定义了 S1/S2 production 和 test allowlists，但 §6.6 的 Ruff 命令没有显式枚举最终文件列表，迫使实施 Agent 重新推导。
- **直接证据**: plan 第 635 行 `<S1+S2全部实际修改的Python文件>`；§5.1 列出 12 个 S1 production + 3 个 S1 tests；§6.1 列出 4 个 S2 production + 4 个 S2 tests + 3 个零 diff regression。
- **影响**: 低。实施 Agent 可从 allowlists 推导，但占位符增加了歧义风险。
- **建议改法和验证点**: 在 §6.6 Ruff 命令旁注明最终文件列表为 S1+S2 production/test allowlists 的并集（去重），或直接列出 16+7 个文件。验证点：命令执行 exit 0。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-§6.6 与 §6.7 scans 内容重叠可能导致执行混淆

- **位置**: §6.6 累计 validation gate 与 §6.7 双向 scans 与唯一同源证明
- **问题类型**: 最佳实践偏离
- **当前写法**: §6.6 命令矩阵末尾提到 "source/AST/LLM/README/security/no-touch scans"，§6.7 又详细定义了 A-E 五组 scan 命令。
- **反例/失败场景**: 实施 Agent 可能在 §6.6 运行"简化版" scans 后认为已通过，跳过 §6.7 的详细 scan 命令；或反过来在 §6.7 重复运行 §6.6 已跑的测试。
- **为什么有问题**: §7 明确 "§6.6 是唯一累计/aggregate validation 真源；不得在本节复制或缩减另一份命令矩阵"，但 §6.7 的详细 scan 命令与 §6.6 的 scan 概述形成两层描述，增加了"哪一层是 authoritative"的歧义。
- **直接证据**: §6.6 第 643 行提到 scans；§6.7 第 646-702 行定义具体 scan 命令；§7 第 720-721 行声明 §6.6 是唯一真源。
- **影响**: 低。§6.7 是 §6.6 scans 的详细展开，逻辑上一致，但两层描述可能让实施 Agent 困惑。
- **建议改法和验证点**: 在 §6.6 scans 提及处加一句 "具体命令见 §6.7"，消除两层描述歧义。验证点：§6.7 每个 scan 命令在 §6.6 累计 validation 中恰好执行一次。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-中-S1/S2 并发修改共享 test file 的行号偏移风险

- **位置**: §5.1 shared test file symbol boundary（第 370-374 行）、§6.1 S2 entry condition（第 458-459 行）
- **问题类型**: 切片过粗 / 隐藏耦合
- **当前写法**: S1 修改 `test_fins_read_runtime.py` 的 import 行与 fiscal node；S2 修改同文件的另一组 import 行与六个 normalize/dedup nodes。两个 implementation step 共享同一文件但 symbol 边界固定。
- **反例/失败场景**: S1 修改的 import 行（如从 `from dayu.fins.domain.financial_result_contract import StatementLocator` 删除）会改变文件行号。S2 随后修改的 normalize/dedup nodes 如果使用行号引用（如 LSP 或 editor 定位），可能因行号偏移而定位错误。更实际的风险是：S1 对 import block 的删除可能影响 S2 对同一 import block 的修改（如添加新 import），导致 git merge conflict 或意外覆盖。
- **为什么有问题**: 计划假设 S1 和 S2 的修改在文件内不重叠，但两者都修改 import 区域（文件顶部）。S1 删除 `StatementLocator` import，S2 可能需要添加 `PublicFinancialStatementResult` import。如果这些修改在相邻行，可能产生 conflict。
- **直接证据**: §5.1 第 370-374 行定义 symbol 边界；S1 implementation artifact 确认 S1 修改了 import 行和 fiscal node；§6.2 S2 实施顺序第 1 步修改 `result_types.py` 的 import 和 public type。
- **影响**: 中。如果 S1 和 S2 由同一 Agent 在同一 tree 上顺序执行（计划要求），Agent 可以处理行号变化。但如果 Agent 使用固定行号引用，可能出错。
- **建议改法和验证点**: 在 §5.1 symbol boundary 定义中明确：S1 和 S2 对共享文件的 import 修改必须在同一 import block 内协调；S2 必须基于 S1 完成后的文件状态工作，不能使用 S1 前的行号引用。验证点：S2 完成后 `test_fins_read_runtime.py` 的 import block 同时包含 S1 和 S2 的修改。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 4-未修复-低-coverage JSON 路径格式与 git diff 路径格式的隐式对齐假设

- **位置**: §6.6 coverage enforcement 逻辑（第 638-641 行）
- **问题类型**: 契约缺失
- **当前写法**: "从当前 `git diff --name-only --diff-filter=ACMR -- dayu/fins` 生成实际 changed production manifest，再逐项读取 `workspace/tmp/r08-cumulative-coverage.json`"
- **反例/失败场景**: `python -m coverage json` 输出的 JSON 中，文件路径 key 格式取决于 coverage 的 `source` 配置。如果 coverage 测量时 source 路径与 git diff 输出的相对路径格式不一致（如一个用 `./dayu/fins/...`，另一个用 `dayu/fins/...`），逐项匹配会失败。
- **为什么有问题**: 计划没有显式声明 coverage JSON 中文件路径的预期格式，也没有提供路径规范化步骤。
- **直接证据**: §6.6 第 633 行 `python -m coverage json -o workspace/tmp/r08-cumulative-coverage.json`；第 638-641 行 coverage enforcement 逻辑。`coverage json` 默认使用相对于 `source` 配置的路径。
- **影响**: 低。两者都从 repo root 运行，路径格式通常一致。但缺少显式规范化步骤使该假设脆弱。
- **建议改法和验证点**: 在 §6.6 coverage enforcement 描述中加一句：实施 Agent 必须确认 coverage JSON 中的文件路径 key 与 git diff 输出使用相同相对路径基准（均为 repo root 相对），必要时做路径规范化。验证点：coverage JSON 中每个 changed production 文件的 key 精确匹配 git diff 输出。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 4. Controller §4 六项挑战点逐项审查

### 4.1 changed-production manifest 是否只含 Python

**结论：PASS。**

§6.6 使用 `git diff --name-only --diff-filter=ACMR -- dayu/fins`。`--name-only` 输出纯文件路径；`--diff-filter=ACMR` 只含 Added/Copied/Modified/Renamed；`-- dayu/fins` 限制路径范围。输出的全部是 `.py` 文件（`dayu/fins/` 目录下无非 Python 生产文件被修改）。§6.1 的 README diff 闭集 `dayu/fins/README.md`、`tests/README.md` 不在此 git diff 范围内。Coverage 只对 production Python 文件执行，README 等非 Python path 不会误入 coverage target。

### 4.2 coverage JSON 逐文件阈值是否可执行

**结论：PASS（有低风险假设）。**

计划明确：从 git diff 生成 manifest → 逐项读取 coverage JSON → 每个文件 `summary.percent_covered >= 80.00` → 缺失或低于阈值即失败。`python -m coverage json` 输出标准 JSON 格式，`files` key 下每个文件有 `summary.percent_covered`。实施 Agent 可用 `json.load()` + 字典遍历实现。禁止 aggregate `--fail-under`、changed-line coverage、pragma/omit、fake-only padding、skip/xfail 或阈值豁免。

**低风险假设**：coverage JSON 路径 key 与 git diff 输出路径格式一致。见 Finding #4。

### 4.3 累计测试与 test diff allowlist 是否无歧义

**结论：PASS。**

§6.6 命令矩阵清晰分层：
1. S1 focused owner matrix（§6.6 第一段命令）
2. S2 focused/public matrix（§6.6 第二段命令）
3. 三段 forced-truncation + AAPL/HTML/no-statement smokes（§6.6 第三段命令）
4. R08 aggregate matrix + complete Fins regression（§6.6 第四段命令）
5. Coverage session（§6.6 第五段命令）

test diff allowlist 分为 S1（§5.1：3 文件）和 S2（§6.1：4 文件），零 diff regression（§6.1：3 文件）单独列出。§6.6 最后一行明确："只有新增/修改测试才限于 S1/S2 test diff allowlist 并直连 owner"。无歧义。

### 4.4 S1/S2 symbol/entry boundary

**结论：PASS（有中等风险点）。**

- S1 production allowlist（12 文件）与 S2 production allowlist（4 文件）无交集
- S1 test allowlist（3 文件）与 S2 test allowlist（4 文件）有 1 个共享文件：`test_fins_read_runtime.py`
- 共享文件的 symbol 边界在 §5.1 第 370-374 行明确定义：S1 只改 fiscal node，S2 只改六个 normalize/dedup nodes
- S2 entry condition 要求 protected 14-path diff SHA 不变（已验证 PASS）

**中等风险点**：S1/S2 都修改共享文件的 import 区域，存在行号偏移风险。见 Finding #3。

### 4.5 immutable code review → fix/re-review → aggregate deepreview → commit 顺序

**结论：PASS。**

§6.9 定义的顺序：
1. AgentCodex S2 implementation/self-check
2. §6.6/§6.7 累计 validation 全绿
3. Controller 记录 changed-path content SHA-256 与 binary diff SHA-256
4. AgentMiMo/AgentDS 并发完整 code review
5. Controller adjudication
6. AgentCodex 修复全部 accepted findings
7. 新 hash 上重跑完整累计 validation
8. 两路完整 re-review
9. Controller 逐条关闭
10. Aggregate deepreview（§7）
11. exact-scope accepted local implementation commit

该顺序满足用户指定的 review → fix → re-review 闭环。关键保障：任一 production/test/README/artifact 变化都使先前 lock/review 失效，必须在新 hash 上重跑。

### 4.6 forced-truncation/R07/security/deferred/no-code 是否保持

**结论：PASS。**

- **forced-truncation**：§6.4 完整保留，包括 pre-Host 等式、Host cursor envelope、fetch-more remainder 三段验证。Test 实现机制（`_tool_runtime` helper 扩展、`_FORCED_XBRL_MAX_ITEMS = 1` 常量、exact node `test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation`）未改变。
- **R07 no-touch**：§2.2 不可回改的 owner 表完整保留；§6.1 明确 "R07 snapshot acquire/borrow/release、cache/revision、citation 与 source-changed symbols 也不允许修改"；§6.7.D R07 no-touch propagation scan 保留。
- **retained security**：§6.7.E retained-security/no-touch scan 保留。
- **deferred scope**：§2.3 out-of-scope 完整保留 R09-R12、Issues 142/151/175/177/178、Host/Engine/Service/UI。
- **no-code**：Topic 8-9 no-code 边界未改变（§6.9 第 9 项、correction artifact §4.2 第 9 项）。

## 5. Open questions

无。所有假设均有直接证据支撑或已通过验证。

## 6. Residual risks

| 风险 | 严重程度 | 跟踪目的地 |
|---|---|---|
| S1/S2 并发修改共享 test file import 区域的行号偏移 | 中 | R08 S2 cumulative implementation（实施时注意） |
| coverage JSON 路径格式与 git diff 路径格式隐式对齐 | 低 | R08 S2 cumulative implementation（实施时验证） |
| Ruff 命令占位符需要推导最终文件列表 | 低 | R08 S2 cumulative implementation（从 allowlists 推导） |
| §6.6/§6.7 scans 两层描述可能混淆 | 低 | 可选 plan clarification |

## 7. Plan review conclusion

**PASS**

Corrected plan 是 code-generation-ready 的。Controller §4 六项挑战点全部通过。§4 product contracts、§5.1/§6.1 allowlists、R07 no-touch、Host truncation owner、deferred/no-code boundaries 均未改变。S1→S2 实现顺序保留，S1 独立 gate 已删除，§6.6 成为唯一累计 validation 真源，coverage 逐文件 `>=80.00%` 规则完整。四个 findings 均为低/中严重程度，不构成 blocker，可在实施时处理。
