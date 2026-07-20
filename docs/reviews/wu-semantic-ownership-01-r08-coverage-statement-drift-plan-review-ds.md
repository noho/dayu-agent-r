# WU-SEMANTIC-OWNERSHIP-01 R08 Coverage-Statement Drift Plan Review — AgentDS

## 元数据

| 项 | 值 |
|---|---|
| 审查人 | AgentDS（第二路独立完整 plan review） |
| 审查目标 | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| 目标 SHA-256 | `115a6429653e4011cf68fc9f3f7e9d7d08431696e0c1a80269c56d2de71dc401` |
| 审查时间 | 2026-07-17 09:48:22 CST |
| 审查类型 | Adversarial complete plan review（非新 WU，非仅 deselect 修复审查） |
| Controller adjudication | `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-controller-adjudication.md` |
| Controller validation | `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-controller-validation.md` |
| 先前 MiMo review | 尚未产出（本 review 与其并发） |

## 1. 审查范围与方法

### 1.1 已读取前置文档

- `AGENTS.md` — 项目硬约束与语义所有权规则
- `docs/host/issues-implementation-control.md`（节选：真源层级、工作流、管理范围）
- `docs/phaseflow-umbrella-optimization-control.md` — umbrella 优化约束
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — Topic 1-9 最终裁决
- `docs/fins/design.md` — Fins 设计真源
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-controller-adjudication.md` — Controller 裁决
- `docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-controller-validation.md` — Controller plan validation

### 1.2 已核对代码事实

| 核对项 | 方法 | 结果 |
|---|---|---|
| 23-path stopped binary diff SHA-256 | `git diff --binary -- dayu/fins tests \| shasum -a 256` | `3d9df8fefc485d0d19421fe6d2a3fe0402bf6f27d3b821d51125e039fa52ddf0` ✓ |
| `read_runtime_helpers.py` deletion 后 SHA-256 | `shasum -a 256` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` ✓ |
| `read_runtime.py` actual-owner SHA-256 | `shasum -a 256` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` ✓ |
| guards SHA-256 | `shasum -a 256` | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` ✓ |
| shared test SHA-256 | `shasum -a 256` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` ✓ |
| S1 artifact SHA-256 | `shasum -a 256` | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` ✓ |
| S2 artifact SHA-256 | `shasum -a 256` | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` ✓ |
| staged tree | `git diff --staged --check` | empty, exit 0 ✓ |
| 旧 helper `_collect_available_document_types` | `rg -n '\b_collect_available_document_types\b' dayu tests` | 零命中 ✓ |
| `resolve_document_type_for_source` in guards | `rg` | 不存在（candidate 6 尚未实现） ✓ |
| actual owner callers | `rg 'resolve_document_type_for_source' read_runtime.py` | 3 处引用（import + 2 call sites） ✓ |

所有入口锁与受保护 tree hash 逐一匹配 plan §0 声明的值。plan §10 的自检要求全部满足。

## 2. Assumptions 压力测试

### A. Coverage arithmetic: 1 covered + 8 missing = 9 statements

**测试**: 直接阅读 coverage.py statement 计数规则，核验 `_collect_available_document_types` 的函数体行数。

**结论**: 成立。旧 helper 的函数体含 8 个可执行语句行（assignments、for loop、if branches、return），加上 definition 行共 9 个 statements。plan 的 `388/494 → 387/485` 算术自洽。

### B. `_resolve_document_type` 的三个 missing branch 恰好是 candidate 6 覆盖的三条路径

**测试**: 直接阅读 `read_runtime_helpers.py` 第 324-349 行的 `_resolve_document_type`，逐条验证。

**结论**: 成立。
- Line 344 `return "material"` — 由 candidate 6 assertion 1 覆盖（UNLISTED_MATERIAL + MATERIAL → material fallback）
- Line 346 `return "other"` — 由 candidate 6 assertion 2 覆盖（None + FILING → other）
- Line 348 `return _CN_FORM_TYPE_TO_DOCUMENT_TYPE[form_type]` — 由 candidate 6 assertion 3 覆盖（FY + FILING → annual_report）
- Line 342、349 已被既有测试覆盖（guards test 中 EARNINGS_CALLS→earnings_call 和 10-K→annual_report）

三条 assertion 精确对齐三个 missing branch。✓

### C. candidate 6 通过 public owner `resolve_document_type_for_source` 间接覆盖 private `_resolve_document_type`

**测试**: 追踪调用链 `resolve_document_type_for_source → _normalize_form_type_for_matching → _normalize_json_scalar_text → _resolve_document_type`。

**结论**: 成立。`resolve_document_type_for_source` 是无下划线 production owner，在 `read_runtime.py` 有两个真实调用点（line 723、886），符合 owner-level contract test 要求。

### D. prefix-five 命令不含 `--deselect`，正确收集原五项

**测试**: 直接阅读 plan §6.6 prefix-five 命令。

**结论**: 成立。Controller validation 已确认中间版本的 `--deselect` 缺陷已修复。当前 plan 中 prefix-five 与 prefix-six 命令使用完全相同的 8 个 test paths，均无 `--deselect`。

### E. 387/485 和 390/485 硬编码值依赖 Controller 诊断

**测试**: 评估 coverage.py 版本、Python 版本、测试集合差异对 coverage statement 计数的影响。

**结论**: 假定成立但存在残余风险（见 §5.3）。plan 的 fail-closed 设计（任一 numerator/denominator/threshold drift 均 `SystemExit(1)` 回 Controller）将风险转化为可检测的 stop condition，而非静默通过。这使风险可控但不是零风险。

## 3. 重点 Adversarial 检查

### 3.1 R08-CR-PCF03 完整性

| 子项 | plan 覆盖 | 证据 |
|---|---|---|
| 保留 dead-helper deletion | §6.7.G source/AST proof, §8 stop condition | 零命中 scan + AST definition/caller/import=0 proof |
| 保留 actual typed/sorted owner | §6.7.G AST proof: `list[_SourceDocumentSummary] → list[str]`, calls `resolve_document_type_for_source`, `sorted()` | 完整 Python AST verification script |
| 保留原五项 stable-owner tests | §6.1 candidate table 1-5, §6.6 prefix-five proof | guards entry hash lock `5531...928d` |
| candidate 6 exact node | §6.1 candidate table row 6, §6.6 implementation block | 三断言精确文本、中文 docstring、禁止列表 |
| 唯一 `resolve_document_type_for_source` import | §6.1, §6.6, §6.7.F | AST import assertion + negative scan |
| fresh prefix-five `387/485 < 80` | §6.6 Python verification script | exact numerator/denominator/threshold check |
| fresh prefix-six `390/485 >= 80` | §6.6 Python verification script | exact check |
| 达标后停止新增 | §6.6 "过线后立即停止新增测试" + §8 stop condition | 明确禁止追求 100% 或补其它 missing line |
| 完整 §6.6/§6.7 从零验收 | §6.6 累计 validation 命令块 | coverage erase → full run → exact-key per-file checker |

**结论**: R08-CR-PCF03 完整覆盖。所有 Controller 裁决均已转化为可执行、可验证的计划指令。

### 3.2 candidate 6 是否为 public owner contract（非 coverage padding）

| 检查维度 | 结论 | 证据 |
|---|---|---|
| 被测函数是否 production owner | 是 | `resolve_document_type_for_source` 无下划线，在 `read_runtime.py` 有两个真实调用点 |
| 断言是否业务语义 | 是 | 三条断言分别验证 material fallback、filing missing-form→other、CN/HK FY→annual_report——全是 LLM-facing `document_type` 分类 |
| 是否绕过 public API | 否 | plan 明确禁止直测 `_resolve_document_type`、读 mapping constants、用 fake/monkeypatch |
| 是否只追求 coverage | 否 | plan 明确要求完整中文 docstring、精确断言业务分类、禁止 empty execution |
| 是否可独立于 coverage 存在 | 是 | 三条分类是 `resolve_document_type_for_source` 的稳定业务语义，即使阈值已满足也应存在 |

**结论**: candidate 6 是正当的 owner-level contract test，不是 coverage padding。

### 3.3 三断言 / 唯一 import / 禁区可生成性

**三断言**:
```python
resolve_document_type_for_source(
    form_type="UNLISTED_MATERIAL", source_kind=SourceKind.MATERIAL.value,
) == "material"
resolve_document_type_for_source(
    form_type=None, source_kind=SourceKind.FILING.value,
) == "other"
resolve_document_type_for_source(
    form_type="FY", source_kind=SourceKind.FILING.value,
) == "annual_report"
```

- `SourceKind` 已由既有 guards imports 提供（line 33: `from dayu.fins.domain.enums import SourceKind`）
- 三条调用均为 `resolve_document_type_for_source` 的直接 keyword-argument 调用
- 业务语义自明：material 未知子类型→通用 material；filing 无表单→other；CN/HK 财期 FY→annual_report

**唯一 import**: 在既有 `from dayu.fins.tools.read_runtime_helpers import (...)` block 中新增 `resolve_document_type_for_source`。

**禁区**: plan §6.1 candidate 6 行明确列举禁止项，且 §6.7.F 的 compatibility/private-helper negative scan 覆盖了 `_build_table_data_payload`、`_normalize_document_types`、`_normalize_periods`、`_normalize_section_children`、`_normalize_taxonomy_name`、`_resolve_default_xbrl_concepts`、`\b_collect_available_document_types\b` 等禁止符号。但注意 `_resolve_document_type`（带下划线前缀）不在该 scan 的 regex 列表中——需由 Controller validation 人工核验。

**结论**: 三断言、唯一 import 和禁区均可生成且可自动验证，但 `_resolve_document_type` 的禁止依赖人工审查（见 finding DS-R08-PR-01）。

### 3.4 prefix-five / prefix-six 命令集合

**prefix-five**（§6.6 第一个命令块）:
```bash
pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_processor_registry.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py
```
共 8 个 test paths，无 `--deselect`。✓

**prefix-six**（§6.6 第二个命令块）:
同上 8 个 test paths，无 `--deselect`。区别仅在于 guards 已包含 candidate 6。✓

Controller validation 已确认中间版本的 `--deselect` 缺陷已修复，两段命令完全一致。

### 3.5 387/485 与 390/485 fail-closed proof

**prefix-five Python verification**:
```python
if covered != 387 or statements != 485 or percent >= 80.0:
    raise SystemExit(1)
```
- 精确检查 numerator=387、denominator=485、percent < 80.0
- 三项任一不匹配 → `SystemExit(1)` → 停止回 Controller ✓

**prefix-six Python verification**:
```python
if covered != 390 or statements != 485 or percent < 80.0:
    raise SystemExit(1)
```
- 精确检查 numerator=390、denominator=485、percent >= 80.0
- 三项任一不匹配 → `SystemExit(1)` → 停止回 Controller ✓

**fail-closed 强度**: 两个 proof 互锁——prefix-five 必须失败（< 80）且 prefix-six 必须通过（>= 80），共同证明 candidate 6 是 first/shortest threshold-crossing prefix。任一 proof 意外通过或失败都会触发 stop。

### 3.6 完整 §6.6 / §6.7 从零验收

plan §6.6 累计 validation 命令块包含：
- S1 focused owner matrix
- S2 focused/public matrix
- 三段 forced-truncation public chain
- AAPL/HTML/no-statement real smokes
- R08 aggregate matrix
- 完整 Fins regression（`pytest tests/fins -q`）
- `coverage erase` + full coverage run
- Git pathspec manifest + exact-key per-file coverage checker（15-file whole-file >= 80%）
- Full pyright
- NUL-safe Ruff manifest + scoped Ruff
- `git diff --check`

plan §6.7 双向 scans：
- A. Internal raw-total positive inventory scan
- B. Public/tool/schema/serializer/LLM negative scan
- C. `fact_count` 唯一 owner scan
- D. R07 no-touch propagation scan
- E. AST/README/security/scope scan
- F. `R08-CR-PCF01` correction-specific source/AST scans
- G. `R08-CR-PCF02` retained deletion + actual-owner source/AST proof

**结论**: §6.6/§6.7 覆盖完整，且明确要求从零（`coverage erase`）执行，不复用旧 incremental ledger。✓

### 3.7 dead-helper deletion / actual typed-sorted owner / source scans

**dead-helper deletion**:
- Source scan: `rg -n '\b_collect_available_document_types\b' dayu tests` → 预期零命中 ✓
- AST proof: definition=0, callers=0, imports=0 ✓
- Content lock: `read_runtime_helpers.py` SHA-256 固定为 `1d7b4bf1...5ea9b` ✓

**actual typed-sorted owner**:
- AST proof: definition=1, callers=1 ✓
- Typed input: `list[_SourceDocumentSummary]` ✓
- Typed return: `list[str]` ✓
- Calls `resolve_document_type_for_source` ✓
- Uses `sorted()` for return ✓
- Content lock: `read_runtime.py` SHA-256 固定为 `27644d0d...0657` ✓

**source scans**: 全部 §6.7.A-G 均有精确命令和预期结果。

### 3.8 测试 / README / product no-touch

| 目标 | plan 约束 | 可验证性 |
|---|---|---|
| shared test | SHA-256 lock `01db...6692` | 自动（hash 比较） |
| 其它 tests | 除 guards candidate 6 外 no-touch | stopped-tree diff scan (§6.7.F) |
| README | §6.8 明确 no-touch，并解释理由 | README trigger check + diff scan |
| production | "不授权任何 production delta"（§6.1） | stopped-tree diff scan（只允许 guards） |
| S1/S2 artifacts | SHA-256 lock | 自动（hash 比较） |

**结论**: no-touch 约束明确且可自动验证。✓

### 3.9 R09-R12、Issues 边界检查

plan §2.3 明确 out-of-scope:
- R09 direct-stream validator
- R10 HKEX
- R11 upload/placeholders
- R12 init/reset
- Issues 142、151、175、177、178
- 统一 authorization
- Host/Engine/Service/UI

plan §6.7.E scope scan 拒绝 allowlist 外路径。✓

### 3.10 Topic 8-9 code 未越界

- Topic 8（Engine 240-char truncation）: plan §2.3 明确 "predates 当前 WU range，不是 R08 scope"。✓
- Topic 9（tool security）: plan §2.3 明确 "统一 authorization out-of-scope"。✓
- 两者均只出现在 out-of-scope 声明中，plan 未授权任何相关修改。✓

### 3.11 旧值 superseded 检查

plan 明确标记为 superseded：
- §0: "旧 `382/482`、`388/482`、candidate-4/5 first-prefix、五项不可变/无test-delta等相冲突指令已删除或明确 superseded"
- §6.6: "旧增量 ledger、Agent candidate-4 stop JSON 与 Controller all-five diagnostic 都只作 historical/plan evidence"
- §10: 确认 plan 中不再存在这些旧值作为 stop/acceptance 条件

全文搜索确认：plan 中提及 `382/482`、`388/482` 仅在 superseded 声明和 root-cause 解释中，不作为 gate 条件。✓

## 4. Findings

### DS-R08-PR-01 — 低 — `_resolve_document_type` 禁止缺乏自动扫描覆盖

- **位置**: §6.1 candidate 6 行、§6.7.F compatibility/private-helper negative scan
- **问题类型**: 测试缺口（scan 覆盖不全）
- **当前写法**: plan 明确禁止 "不得直接测试 `_resolve_document_type`"，但 §6.7.F 的 guards negative scan 正则列表不包含 `_resolve_document_type`。该 scan 覆盖了 `_build_table_data_payload`、`_normalize_document_types` 等 helpers，却遗漏了 candidate 6 最相关的禁止对象。
- **反例/失败场景**: 实现 agent 可能在 candidate 6 中同时 import `_resolve_document_type`（而非仅通过 `resolve_document_type_for_source` 间接调用），scan 不会捕获。
- **为什么有问题**: 直接测试 `_resolve_document_type` 违反 owner boundary——该函数是 private helper，plan 要求只通过 public `resolve_document_type_for_source` 断言业务语义。
- **直接证据**: §6.7.F scan regex 包含 `\b_collect_available_document_types\b`（针对已删除 helper），但不包含 `\b_resolve_document_type\b`（针对 candidate 6 禁止直测的 private helper）。
- **影响**: 低——Controller validation 可人工核验 import 列表；AST import assertion（§6.7.F 末尾）要求 "唯一新增的 production symbol import 精确为 `{resolve_document_type_for_source}`"，可间接捕获多余的 `_resolve_document_type` import。
- **建议改法和验证点**: 在 §6.7.F 的 guards negative scan regex 中新增 `\b_resolve_document_type\b`（使用 word boundary 避免匹配 `resolve_document_type_for_source`），或在 AST import assertion 中显式断言 `_resolve_document_type` 不出现在 guards imports 中。
- **修复风险**: 低（纯 scan 增强，不影响 plan 逻辑）
- **严重程度**: 低

### DS-R08-PR-02 — 低 — 硬编码 387/485、390/485 对 coverage.py 版本敏感

- **位置**: §6.6 prefix-five/prefix-six Python verification scripts
- **问题类型**: 不可直接实施（环境敏感性）
- **当前写法**: proof scripts 的 `if covered != 387 or statements != 485` 做 exact match。
- **反例/失败场景**: 不同 coverage.py 版本可能对同一源码产生不同 statement 计数（尤其是 multi-line calls、decorators、comprehensions 的计数规则在不同版本间有差异）。若实现 agent 的 coverage.py 版本与 Controller 诊断时的版本不同，可能产生例如 `386/485` 或 `388/485`，导致 prefix-five 意外失败。
- **为什么有问题**: plan 的 fail-closed 将环境差异转化为 stop condition，增加不必要的 Controller 往返。
- **直接证据**: plan 未指定 coverage.py 版本要求。Controller validation artifact 记录了其 coverage data SHA-256 (`475590a2b188e43ce28a3cef9aa97ca133be9056e9b6fa76a2e94cf0770c4710`) 但 plan 未纳入。
- **影响**: 低——fail-closed 设计使风险可检测（不会静默通过），但可能导致不必要的排查往返。实际 coverage.py 版本差异概率较低（项目使用固定 Python 3.11 和依赖锁定）。
- **建议改法和验证点**: 在 plan §6.6 中增加 coverage.py 版本声明（如 `python -m coverage --version` 输出要求），或将 Controller 的 coverage data 文件 SHA-256 纳入 proof 前置检查。若 environmental drift 被证实，Controller 可在新环境重跑诊断并更新 plan 的预期值。
- **修复风险**: 低（仅增加环境声明，不改变 proof 逻辑）
- **严重程度**: 低

## 5. Open Questions

无。plan 在所有关键维度均已收敛。

## 6. Residual Risks

### RR-1: coverage.py 版本敏感性（见 DS-R08-PR-02）

- **风险**: 环境差异导致 prefix-five proof 产生非预期的 numerator/denominator
- **缓解**: fail-closed design → stop 回 Controller；Controller 可在新环境重跑诊断
- **跟踪**: 无需独立 issue；若发生则在 implementation artifact 中记录

### RR-2: `_resolve_document_type` 直测绕过（见 DS-R08-PR-01）

- **风险**: 实现 agent 在 candidate 6 中直接 import 并测试 private helper
- **缓解**: AST import assertion（§6.7.F）可检测非 `resolve_document_type_for_source` 的新增 import；Controller validation 可人工核验
- **跟踪**: Controller validation gate 人工检查

### RR-3: forced-truncation 测试复杂度（§6.4）

- **风险**: `_tool_runtime` helper 修改与 pre-Host/post-Host 三段验证链路复杂，实现 agent 可能因 public seam 不可观测而触发 stop
- **缓解**: plan §6.4 末尾和 §8 已有明确 stop condition；该测试属于原 S2 scope 而非 coverage drift continuation
- **跟踪**: 若触发 stop，Controller 需裁决是否调整 §6.4 方案或接受当前可观测范围

### RR-4: prefix-five 阶段 8 文件集合中可能存在非确定性测试

- **风险**: 若 8 个测试文件中存在依赖外部状态或顺序的测试，可能导致 coverage 计数不稳定
- **缓解**: plan 要求 `coverage erase` 从零开始；pytest 默认按文件名字母序收集
- **跟踪**: 若 prefix-five proof 不稳定（同一 tree 多次运行产生不同 coverage），需排查非确定性测试

## 7. Final Verdict

**PASS-WITH-RISKS**

### 通过理由

1. **R08-CR-PCF03 完整**: 所有 Controller 裁决均已转化为可执行、可验证的计划指令。candidate 6 的 exact node、唯一 import、三条断言、禁止列表均明确且自洽。

2. **入口锁全部匹配**: 23-path stopped binary diff、helper/owner/guards/shared/S1/S2 content SHA-256、staged empty——7 个锁全部与实际 tree 一致。

3. **candidate 6 是正当 owner contract test**: `resolve_document_type_for_source` 是无下划线 production owner，有真实调用者，三条断言覆盖三个稳定业务分类语义。不是 coverage padding。

4. **fail-closed proof 自洽**: prefix-five 必须 `387/485 < 80%`，prefix-six 必须 `390/485 >= 80%`，任一 drift → `SystemExit(1)` → 回 Controller。双 proof 互锁证明 candidate 6 是 first/shortest threshold-crossing prefix。

5. **§6.6/§6.7 完整且可从零验收**: 累计 validation 包含 focused/aggregate/full regression tests、real smokes、per-file exact-key coverage、full pyright、scoped Ruff、全部双向/AST/LLM/README/security/no-touch scans。

6. **边界清晰**: R09-R12、Issues 142/151/175/177/178、统一 authorization、Topic 8-9 code——全部在 §2.3 明确 out-of-scope，§6.7.E scope scan 可自动验证。

7. **旧值已 superseded**: `382/482`、`388/482`、candidate-4/5 first-prefix、五项不可变双指令——全部在 plan 中标记为 historical evidence，不再作为 gate 条件。

8. **测试/README/product no-touch 可自动验证**: shared test SHA-256 lock + stopped-tree diff scan + README trigger check。

### 残余风险

两个低严重度 finding（DS-R08-PR-01、DS-R08-PR-02）和四个 residual risk 已在 §4 和 §6 中记录。均不影响 plan 进入 implementation gate，但建议 Controller 在 implementation handoff 时提醒实现 agent 注意：

- 使用与 Controller 诊断相同的 coverage.py 版本
- 不在 candidate 6 中直接 import `_resolve_document_type`

### 建议

本 plan 可以进入下一 gate（双路 complete plan review 闭环 → accepted plan commit → implementation gate）。建议 Controller 在 accepted plan commit 前确认 AgentMiMo 的独立 review 结论，并对两路 review 的 accepted findings 做 adjudication。
