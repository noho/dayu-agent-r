# Plan Re-Review — WU-SEMANTIC-OWNERSHIP-01 P3-G

## Scope

- Mode: plan re-review (fix verification)
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G`
- Plan artifact (updated): `docs/host/wu-semantic-ownership-01-p3-g-fins-domain-contracts-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-review-controller-adjudication.md`
- Original review: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-review-ds.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-rereview-ds.md`

## Verdict

**PASS** — 四个 controller 接受的 plan fix 全部正确关闭，无新增 material finding，无 residual ambiguity。

---

## Fix Verification

### P3-G-PF-01 — S4 XBRL `total` Contract Boundary ✅ FIXED

| Controller 要求 | 状态 | 直接证据（行号） |
| --- | --- | --- |
| Raw `total` 校验在 dedup/projection 之前 | ✅ | Design Decision 7（行 119）：“processor raw contract validation 必须在 read-runtime dedup/projection 之前执行” |
| 校验 raw `total` 存在、为 int、等于 raw `facts` 长度 | ✅ | S4（行 263）：“fail closed when raw `total` is missing, raw `total` is not an `int`, raw `facts` is not a list, or raw `total != len(raw_facts)`” |
| post-dedup shrink 不得导致 validator 报错 | ✅ | Design Decision 7（行 119）：“post-dedup count 可能小于 processor raw `total`，不得因此判定 processor result invalid”；S4（行 266）：“Post-dedup shrink is valid and must not fail processor contract validation” |
| read runtime 不得覆盖 processor `total` | ✅ | Design Decision 7（行 119）：“也不得覆盖 processor-owned `total`”；S4（行 264）：“must preserve processor-owned `total` after validation” |
| 派生 count 用独立字段 | ✅ | Design Decision 7（行 119）：“必须使用 `deduped_fact_count` 或等价的明确派生字段/summary term” |
| Test matrix 覆盖 5 个场景 | ✅ | S4 Tests（行 270-275）：missing `total`、non-int `total`、raw mismatch、valid raw result、valid post-dedup shrink |

**判定**: 两层 contract（raw validation → post-dedup projection）已明确分离，歧义消除。

### P3-G-PF-02 — S1 Form Normalizer Disposition And Source Scans ✅ FIXED

| Controller 要求 | 状态 | 直接证据（行号） |
| --- | --- | --- |
| 明确 `form_type_utils.py` 处置：删除，不允许兼容 wrapper | ✅ | S1（行 142）：“Explicit disposition: delete `dayu/fins/processors/form_type_utils.py` … A compatibility wrapper, compatibility re-export, or 'same file delegates to domain' path is not allowed” |
| 列出 S1 将更新的当前 import/call 站点 | ✅ | S1（行 143-149）：列出 5 个 import 站点 + 所有 `normalize_form_type(...)` / `_normalize_form_for_fiscal(...)` 调用站点 |
| 加强 source scans 覆盖定义、调用和 import | ✅ | S1 Validation（行 162-164）：3 个 rg 扫描分别覆盖定义、调用站点、import 引用 |
| Completion signal 明确 | ✅ | S1（行 168）：“`dayu/fins/processors/form_type_utils.py` is deleted, no production import references it” |

**代码证据核实**:
- 当前 5 个 import 站点：`sec_processor.py:47`、`bs_report_form_common.py:32`、`sec_report_form_common.py:26`、`sec_form_section_common.py:49`、`read_runtime_helpers.py:30` — 均在 plan 列举范围
- 当前 3 套 normalizer 定义：`form_type_utils.py:50`、`sec_form_utils.py:43`、`sec_fiscal_fields.py:546` — plan 要求将后两者也更新为消费 domain helper
- Source scan regex 覆盖：`normalize_form_type\(` / `_normalize_form\(` / `_normalize_report_form_type\(` / `_normalize_form_for_fiscal\(` — 覆盖所有已知别名

**判定**: 处置明确、source scan 全面、import 站点穷举。

### P3-G-PF-03 — S2 CN/HK Adapter Versus Pipeline Boundary ✅ FIXED

| Controller 要求 | 状态 | 直接证据（行号） |
| --- | --- | --- |
| 逐项分类：raw parsing 留在 downloader，business filtering 移到 pipeline | ✅ | S2（行 188-191）：详细列出 remains in downloader（HTTP/JSON/raw fields）和 moves to pipeline（`_is_title_blocked`、`_infer_fiscal_year`、`_infer_fiscal_period_from_text`、grouping、`CnReportCandidate` 构造） |
| 测试迁移路径 | ✅ | S2 Tests（行 194-197）：raw adapter 保留 HTTP/raw parsing 断言；pipeline helper 接收 business 断言且不用 HTTP mock；workflow 保留集成覆盖 |
| 迁移规则：每条移除的 downloader 断言必须有对应 pipeline helper 断言 | ✅ | S2（行 197）：“every downloader test assertion removed because it was business filtering/inference must have an equivalent pipeline helper assertion in the same slice” |
| Completion signal 记录迁移映射 | ✅ | S2（行 206）：“The implementation report must list migrated downloader assertions and their new pipeline helper test names” |

**判定**: 职责分类穷举、测试迁移策略明确、可追溯。

### P3-G-PF-04 — S3 Rejection Registry Consumer Scope ✅ FIXED

| Controller 要求 | 状态 | 直接证据（行号） |
| --- | --- | --- |
| `sec_sc13_filtering.py` 加入 S3 allowed files | ✅ | S3（行 220）：`dayu/fins/pipelines/sec_sc13_filtering.py` |
| SC13 filtering 加入 code evidence | ✅ | Direct Code Evidence（行 56）：SC13 filtering 的 `dict[str, dict[str, str]]` 签名证据 |
| SC13 不得使用 typed-registry-to-dict shim | ✅ | S3（行 229）：“no typed-registry-to-dict compatibility shim is allowed” |
| Source scan 覆盖 SC13 | ✅ | S3 Validation（行 241）：`rg` 扫描 `sec_sc13_filtering.py` 中的 `rejection_registry` / `DownloadRejection` |
| Completion signal 包含 SC13 | ✅ | S3（行 245）：“`sec_sc13_filtering.py` consumes typed registry without adapter shim” |
| Propagation audit 包含 SC13 | ✅ | Propagation Audit（行 319）：“including SC13 filtering and retry/browse-edgar supplemental paths in `sec_sc13_filtering.py`” |

**代码证据核实**: `sec_sc13_filtering.py` 当前有 7 处 `rejection_registry: Optional[dict[str, dict[str, str]]]` 签名 — 均在 S3 scope 内。

**判定**: SC13 过滤路径完整纳入 typed registry contract。

---

## New Defect Scan

对更新后 plan 的全体内容逐节走读：

- **S1: SEC form parser alias expansion vs. persisted single form**: Plan 明确 "persisted single form 只能是具体表单，不保存 group alias"（Design Decision 2）。与 source meta 字段不变策略一致。✅
- **S1: 列出的 import/call 站点完整性**: 5 个 import 站点 + 全部已知别名覆盖。`sec_form_section_common.py:2983` 的 `_normalize_form_type(form_type)` 调用已纳入。✅
- **S2: Downloader "can keep" 列表边界**: 包括 "provider source id/url/date/language raw normalization" — 这允许 downloader 继续做字段类型转换和归一化，与 HTTP adapter 职责一致。✅
- **S3: 未在 tests 中显式列出 SC13 测试**: Tests 节描述的是 registry round-trip + malformed entry 通用测试。SC13 filtering 的 typed registry 消费由 completion signal 和 source scan 保证，无需为 SC13 单列测试。✅
- **S4: "deduped_fact_count" 命名**: Design Decision 7 使用 `deduped_fact_count` 作为建议名。plan 正确标记为 "or equivalent"，未强制字段名。✅
- **Aggregate source scans**: 更新后的 aggregate 扫描矩阵（行 294-302）完整覆盖全部 4 个 slice 的 completion signal，无遗漏。✅

---

## Cross-Slice Consistency

| 检查项 | 状态 |
| --- | --- |
| S1 domain module 只依赖标准库（Design Decision 1）— 不会穿透到 pipeline/storage | ✅ |
| S2 迁移不与 S1 domain types 冲突 — fiscal period 在 S2 使用共享 domain parser（来自 S1） | ✅ |
| S3 typed entry 在 domain 层，S1 的 `document_models.py` 已在 allowed files | ✅ |
| S4 processor validation helper 不依赖 S2/S3 | ✅ |
| 所有 4 个 slice 的 non-goal 一致：不兼容旧 schema、不修改 P3-F | ✅ |

## Open Questions

无。

## Residual Risk

- **Plan 原始 4 个 risk 保持不变**：S1 import 扩散、S2 CN/HK 测试耦合、S3 protocol 变更波及、S4 既有测试假设 deduped `total`。PF-01 到 PF-04 的 fix 已直接处理了每个风险对应的 mitigation。
- **`form_type_utils.py` 删除后 processor 测试可能需要更新 mock/import** — S1 validation 的 pytest 命令已包含受影响的测试文件。
