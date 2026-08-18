# UF-FIX11 S1+S2 Implementation Re-Review — MiMo

## Re-review metadata

- Work unit: `UF-FIX11 company-metadata-ignored-change-warning`
- Slice: `S1+S2 — atomic authoritative company identity commit and filing warning`
- Gate: `implementation re-review`
- Reviewer: MiMo
- Date: 2026-08-17
- Branch: `codex/upload-filing-oracle`
- Fix artifact: `docs/gateflow/uf-fix11-s1-s2-implementation-review-fix-20260817.md`
- Prior reviews:
  - `docs/reviews/uf-fix11-s1-s2-implementation-review-mimo-20260817.md` (PASS, 0 blocking / 2 non-blocking)
  - `docs/reviews/uf-fix11-s1-s2-implementation-review-ds-20260817.md` (findings, 3 low-severity test gaps)
- Reviewed scope: fix diff (4 test files), controller decisions, prior review findings status
- Decision: **PASS — 0 blocking, all accepted findings closed, rejected findings合理**

---

## 方法论

1. 读取 fix artifact 的全部 controller decisions（3 accepted + 1 accepted suggestion + 2 rejected-with-reason）。
2. 逐项对照 fix 后的增量 test diff，验证 accepted findings 的测试是否真正覆盖声明的分支/路径。
3. 确认 rejected findings 的理由是否符合 plan 语义 owner 与"不改 production"约束。
4. 验证 fix 未修改 production 文件、未弱化既有测试、未越过 S3 边界。
5. 复用初轮 review 的已验证 evidence（15 维度全 PASS），不重跑昂贵全套。

---

## Finding 状态裁决

### DS Finding-001 — material 非空 warnings 的 fail-closed 拒绝分支无测试

**状态: 已修复 ✓**

修复证据（`test_fins_ingestion_runtime.py`，`test_pipeline_warning_parser_requires_filing_field_but_allows_material_missing`）：

- 新增 `MATERIAL + warnings=[规范 warning 对象]` → `pytest.raises(ValueError, match="material terminal result")` 断言。
- 新增 `MATERIAL + warnings=[]` → `assert explicit_empty_material.warnings == ()`（空数组合法）。
- 保留原有 `MATERIAL + missing → ()`、`FILING + missing → fail`、`MATERIAL + null → fail` 三个分支。

`ingestion_runtime.py:1773-1774`（`if source_kind is SourceKind.MATERIAL and warnings: raise`）现在有直接 owner-level 测试覆盖。

### DS Finding-002 — cancelled-outcome invariant 与 closed codec 的 raise 分支缺直接测试

**状态: 已修复 ✓**

修复证据（`test_filing_upload_publication.py`，4 个新测试函数）：

1. **`test_publication_outcome_rejects_cancelled_warning`**：构造 `status="cancelled"` + 非空 warning 的 `FilingUploadPublicationOutcome` → `pytest.raises(ValueError, match="cancelled publication outcome")`。直接测试 `__post_init__` L181-182 的 cancelled invariant。

2. **`test_publication_outcome_rejects_warning_commit_outcome_mismatch`**：构造 `company_meta_commit_outcome` 携带 `CompanyNameIgnoredChange` 但 `warnings=()` 的 outcome → `pytest.raises(ValueError, match="必须与内部 commit outcome 同源")`。直接测试 `__post_init__` L183-187 的同源 invariant。

3. **`test_company_metadata_warning_rejects_noncanonical_constructor_values`**：参数化覆盖 kind 类型错误（`cast` 非 enum）和 message 非规范文案 → `pytest.raises(TypeError/ValueError)`。直接测试 `CompanyMetadataWarning.__post_init__` 的 closed value 拒绝。

4. **`test_company_metadata_warning_json_projection_rejects_invalid_collections`**：参数化覆盖 `company_metadata_warnings_to_json` 接收 >1 个元素（重复 kind）和非精确类型元素 → `pytest.raises(ValueError/TypeError)`。

5. **`test_company_name_ignored_warning_projection_rejects_nonexact_domain_fact`**：`cast` dict 为 `CompanyNameIgnoredChange` 传入 `project_company_name_ignored_warning` → `pytest.raises(TypeError, match="CompanyNameIgnoredChange")`。

DS review 指出的所有未覆盖 raise 分支（`filing_upload_publication.py:178,182,187`、`company_metadata_warning.py:56,58,97,103,135,156,158,160,180`）现在都有直接 owner-level 测试。

### DS Finding-003 — service parser callsite 结构测试按顺序断言

**状态: 已修复 ✓**

修复证据（`test_fins_service_runtime.py`，`test_production_runner_parser_callsites_use_explicit_source_kind` 完全重写）：

- 先定位唯一 `ProductionFinsUploadRunner` class（`assert len(runner_classes) == 1`）。
- 按所属 `_run_filing_upload` / `_run_material_upload` 方法收集 `from_pipeline_json` callsites。
- 断言 `set(source_kinds_by_method) == {"_run_filing_upload", "_run_material_upload"}`。
- 断言每个方法内 callsite 数量（2）和 kind 集合（`{"FILING"}` / `{"MATERIAL"}`）。

旧测试用物理顺序列表 `["FILING", "FILING", "MATERIAL", "MATERIAL"]` 断言；新测试用方法绑定 + 集合断言。顺序重排不再假阳性，单点 kind 漂移仍假阴性变红。

### MiMo Finding-002 测试建议 — 空白输入覆盖

**状态: 已修复 ✓**

修复证据（`test_company_meta_contract.py`，`test_fresh_upload_equivalent_or_missing_name_keeps_metadata` 参数矩阵扩展）：

- 旧参数: `(None, "  ＤＥＬＴＡ ＩＮＣ.  ")`
- 新参数: `(None, "   ", " 　  ", "  ＤＥＬＴＡ ＩＮＣ.  ")`
- 新增 ASCII 纯空白 `"   "` 和 U+3000 + U+00A0 混合空白 `" 　  "` 两个 case。
- 断言不变：`decision.disposition == "keep"` 且 `decision.company_meta_intent is None`。

直接证明 pipeline owner 把空白输入视为"未提交"，不产生 intent，因此不进入 domain 校验。

### MiMo Finding-001 — 校验文案不一致

**状态: REJECTED-WITH-REASON ✓**

Controller 理由：两处错误分别属于不同 contract（pipeline 校验用户输入必填值 vs domain 防御绕过上游的非法 intent），不是同一公共错误 contract。统一文案会把不同 owner 强耦合。

**裁定合理**。pipeline 层 `_require_upload_company_name` 和 domain 层 `_normalize_optional_requested_company_name` 确实是不同 owner 的不同防御边界。前者是用户输入验证，后者是 intent 构造的二次防御。下游没有按内部错误文案做匹配的授权。不修改是正确决策。

### MiMo Finding-002 production 语义变更建议

**状态: REJECTED-WITH-REASON ✓**

Controller 理由：pipeline owner 明确把空白输入折叠为 missing；domain constructor 对绕过 pipeline 的空白 intent fail closed。两层职责不同，统一行为会削弱 domain 防御不变量或改变既定用户输入语义。

**裁定合理**。初轮 review 已确认实际调用路径不会让空白字符串到达 domain 校验（pipeline 先拦截）。测试补充已覆盖空白输入场景，production 语义边界无需变更。

---

## Fix 边界验证

### 未修改 production 文件

**PASS**。`git diff HEAD --stat -- dayu/` 输出与初轮 review 完全一致：11 个 modified + 1 个 untracked（`company_metadata_warning.py`），381 insertions / 53 deletions。Fix artifact 声明"本 fix 未修改任何 Python production 文件"与事实一致。

### 未弱化既有测试

**PASS**。Fix diff 全部为新增测试代码，无删除或修改既有断言：

- `test_fresh_upload_equivalent_or_missing_name_keeps_metadata`：参数矩阵扩展（新增 2 个 case），原有 2 个 case 和所有断言不变。
- `test_production_runner_parser_callsites_use_explicit_source_kind`：完全重写，新断言严格超集旧断言（方法绑定 + 集合 > 顺序列表）。
- `test_pipeline_warning_parser_requires_filing_field_but_allows_material_missing`：新增 2 个分支（material+empty、material+non-empty），原有 3 个分支不变。
- 其余新增测试为全新函数，不影响既有测试。

### 未越过 S3 边界

**PASS**。Fix 只修改 4 个 S1+S2 allowed test 文件：

- `tests/fins/test_company_meta_contract.py` ✓
- `tests/fins/test_filing_upload_publication.py` ✓
- `tests/fins/test_fins_ingestion_runtime.py` ✓
- `tests/fins/test_fins_service_runtime.py` ✓

未修改 S3 才允许的文件（`direct_events.py`、`cli/output.py`、`fins_wait_adapter.py`、`test_fins_direct_stream.py`、`test_cli_output.py`、`test_fins_wait_adapter.py`）。

### 修复未新增 production 修改

**PASS**。Fix artifact 的"Changed files in this fix"只有 4 个测试文件和 1 个 artifact 文件。`git status --short -- dayu/` 与初轮 review 一致。

---

## 复用已有验证 evidence

初轮 review 的 15 个维度全部 PASS，本 re-review 确认以下 evidence 仍然有效（fix 未修改 production，所有 production-level 断言不变）：

| 维度 | 初轮结论 | 本 re-review 确认 |
| --- | --- | --- |
| 语义 owner at final-lock storage outcome | PASS | 未变 |
| early/preflight snapshot 泄漏 | PASS | 未变 |
| warning invariant | PASS | 不变；新增 cancelled/mismatch direct test 强化 |
| capability transfer/atomic rollback | PASS | 未变 |
| fresh different/equivalent/missing name | PASS | 不变；新增空白参数强化 |
| alias merge/invalid/collision/concurrent | PASS | 未变 |
| CompanyMeta bytes/updated_at/source tree | PASS | 未变 |
| SEC/CN 全 terminal producer | PASS | 未变 |
| closed codec | PASS | 不变；新增 constructor/serializer/projection direct test 强化 |
| 四个 SourceKind callsite | PASS | 不变；方法绑定重写强化 |
| S3 边界未提前 | PASS | 未变 |
| docstring/types/README | PASS | 未变 |
| commit_batch 全量收敛 | PASS | 未变 |
| hasattr/getattr/Any/object | PASS | 未变 |
| 兼容性代码 | PASS | 未变 |

---

## Fix 质量评估

### 测试增量统计

- focused suite: 706 → 715 passed（+9 个新测试节点，参数展开后更多）
- combined regression: 2129 → 2138 passed（+9）
- 全仓 pyright: 0 errors（不变）

### 测试结构质量

- 所有新测试直接调用 owner constructor/serializer/projection/parser，不通过 SEC/CN workflow、service runtime 或 CLI 层间接推断。
- 参数化测试覆盖 fail-closed raise 分支的多种输入（类型错误、超限、不一致等）。
- 方法绑定的 AST 测试比顺序列表测试更鲁棒。

---

## Residual risks（继承 + 更新）

| ID | 分类 | 说明 | 变化 |
| --- | --- | --- | --- |
| R1 | `assigned to later work unit` | name-only metadata batch 的 writer lock/physical swap 成本 | 不变 |
| R2 | `assigned to later work unit` | material upload 类似 company-name 行为 | 不变 |
| R3 | `assigned to later work unit` | 真实 CLI evidence、scenario/oracle/frozen evidence 更新 | 不变 |
| R4 | `assigned to later work unit` | commit durable 但 post-commit guard-release/cleanup 报错的运维可见性 | 不变 |
| R5 | `fixed in current slice` | DS-RR1: SEC/CN producer roundtrip | 不变 |
| R6 | `fixed in current slice` | DS-RR2: capability transfer 顺序 | 不变 |
| R7 | `fixed in current slice` | `_optional_upload_company_name` 空白输入测试覆盖 | **已关闭**（fix 补齐） |
| R8 | `fixed in current slice` | DS-001: material non-empty warnings fail-closed 测试 | **已关闭**（fix 补齐） |
| R9 | `fixed in current slice` | DS-002: cancelled invariant / closed codec raise 测试 | **已关闭**（fix 补齐） |
| R10 | `fixed in current slice` | DS-003: SourceKind callsite 方法绑定测试 | **已关闭**（fix 重写） |

没有未分类 residual risk。所有 controller accepted findings 的 residual 已从 `assigned to later work unit` 或测试缺口状态转为 `fixed in current slice`。

---

## 结论

**PASS**。UF-FIX11 原子 S1+S2 implementation review-fix 的所有 controller accepted findings 已真正关闭：

- DS Finding-001/002/003 各有直接 owner-level 测试覆盖其声明的分支/路径。
- MiMo Finding-002 测试建议已补齐空白输入参数。
- 两个 rejected-with-reason findings 理由充分，符合 plan 语义 owner 与"不改 production"约束。
- Fix 未修改 production 文件、未弱化既有测试、未越过 S3 边界。
- 初轮 review 的 15 个维度 PASS evidence 全部仍然有效。

可以进入 accepted S1+S2 slice commit。
