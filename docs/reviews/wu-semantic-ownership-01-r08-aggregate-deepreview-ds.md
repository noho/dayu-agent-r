# WU-SEMANTIC-OWNERSHIP-01 / R08 cumulative aggregate deepreview — AgentDS

## 1. 结论

**PASS / 零 accepted candidate / 零 material finding**

本路 aggregate deepreview 对 immutable 23-path cumulative tree（`dayu/fins` + `tests` + README）执行了完整 adversarial failure pass、overcoupling pass、semantic ownership drift pass 与 artifact-to-code evidence chain 审计。未发现需当前 fix 的 R08-scope material defect。全部已接受 finding（`R08-CR-CF01`、`R08-CR-PCF02..04`、`R08-VAL-PY-F01..F03`）已确认关闭。

Topic 6 七项设计决策的逐 owner/时序状态：

| 决策 | 实现 owner | 状态 |
|------|-----------|------|
| §6.1 批次所有权（显式 token，去 ambient identity） | R06 batch/source（prior accepted commit） | R06 已交付；R08 no-regression ✓ |
| §6.2 源发布（staging 不泄漏到 business meta） | R06 batch/source（prior accepted commit） | R06 已交付；R08 no-regression ✓ |
| §6.3 provenance/citation（typed，不猜前缀） | R07 provenance/revision/opaque mapping（prior accepted commit） | R07 已交付；R08 no-regression ✓ |
| §6.4 revision/read consistency（storage-owned snapshot） | R07（prior accepted commit） | R07 已交付；R08 no-regression ✓ |
| §6.5 financial statement minimal contract（去 statement_locator/diagnostics，收窄 reason） | **R08**（本 tree） | R08 实现到位 ✓ |
| §6.6 XBRL facts minimal contract（唯一 fact_count=len(facts)，去 raw total/deduped_fact_count） | **R08**（本 tree） | R08 实现到位 ✓ |
| §6.7 direct-stream terminal（唯一 Fins-owned validator） | R09（planned sub-WU） | R08 no-touch；当前三层检查为 R09 accepted target |
| §6.8 HKEX cumulative rowRange continuation | R10（planned sub-WU） | R08 no-touch；`hkexnews_downloader.py` 未被修改 |
| §6.9 containment + storage key mapping | R07 opaque mapping（prior accepted commit）；containment 为 pre-existing | R07 已交付 identity→private locator + descriptor 双向校验；R08 no-regression ✓ |
| §6.10 upload batch plan / script rendering | R11（planned sub-WU） | R08 no-touch |

R07 snapshot/citation 无回归。Topic 8/9 no-code 边界与 Issues 142/151/175/177/178 及 R09-R12 no-scope-creep 边界完整无泄漏。

Reviewer verdict 不授权 commit。

## 2. Scope

- **Mode**: current changes（immutable 23-path `dayu/fins` + `tests` + README cumulative tree）
- **Base**: `b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD` + current working tree
- **Branch**: `phaseflow/host-issues-control`
- **Review timestamp**: 2026-07-17T12:16:04+08:00
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-ds.md`

### 2.1 Immutable Locks（已验证，全部匹配）

| Lock | Expected SHA-256 | Status |
|------|-----------------|--------|
| cumulative `git diff --binary -- dayu/fins tests` | `01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d` | ✓ |
| guards `test_read_runtime_semantic_ownership_guards.py` | `44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a` | ✓ |
| controller code re-review adjudication | `9fb0afe89ff73207f895b9a540133fbecdc0bde799248092b24991f825a8f82e` | ✓（artifact-only normalization：3 处 Markdown 行尾空格删除，semantic content / verdict 不变；产品 tree 仍为 `01c2a1d5...092d`） |
| shared test `test_fins_read_runtime.py` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | ✓ |
| 23 tracked paths | 23 paths | ✓ |
| staged empty | zero staged | ✓ |

### 2.2 真源优先级（已完整读取）

1. `AGENTS.md` — 语义所有权约束、编码硬约束、LLM-facing 文本约束
2. `docs/host/issues-implementation-control.md` — R08 gate 状态、已接受 finding ledger、next entry point
3. `docs/phaseflow-umbrella-optimization-control.md` — umbrella 级别约束（已读取，R08 无新增约束）
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — Topic 6 七项最终裁决（§6.1–§6.7）
5. `docs/fins/design.md` — §1–§10 稳定 Fins 设计真源
6. 已接受 R08 plan/review/adjudication/implementation/validation artifacts — 完整链条
7. 旧三路原始 review — 仅作代码证据，冲突时以 controller discussion 为准

### 2.3 并行审查覆盖

| Agent | 范围 | 状态 |
|-------|------|------|
| Adversarial failure pass | 全部 production domain/tools/read_runtime 文件，逐函数入参→分支→返回值→副作用 | 完成 |
| Overcoupling pass | 全部 production 文件的 import 图、层依赖、Protocol 边界、test 耦合 | 完成 |
| Semantic ownership drift pass | 全部 production domain + tools + processors + pipelines，对照设计 §1–§10 | 完成 |
| Evidence chain audit（主 reviewer） | accepted finding 闭包、prefix/coverage/pyright/Ruff/scans 证据链、R07/Topic 8-9/R09-R12/Issues 边界 | 完成（审计 AgentCodex/Controller locked evidence，本路未独立重跑覆盖率） |

## 3. Accepted Finding 闭包确认

全部七个已接受 finding 均已独立验证关闭：

| Finding | 验证方法 | 结论 |
|---------|---------|------|
| `R08-CR-CF01` | shared test hash `01db5538...6692` 匹配；四个 generic/compat test node 零命中；九个 forbidden import 零命中 | 已关闭 |
| `R08-CR-PCF02` | dead `_collect_available_document_types` 定义/caller/import 全零命中；actual typed/sorted owner `_collect_available_document_types_for_source_documents` 唯一定义/caller 各一 | 已关闭 |
| `R08-CR-PCF03` | candidate 6 `test_document_type_resolver_projects_material_other_and_cn_categories` 存在且含三条精确断言（material/other/CN annual）；唯一 `resolve_document_type_for_source` import 存在 | 已关闭 |
| `R08-CR-PCF04` | prefix-five predecessor `387/485` + fresh prefix-six `391/485` 与四行差集 `[344,346,348,442]` 一致 | 已关闭 |
| `R08-VAL-PY-F01` | optional public keys 先做 membership proof（guards test `_TaxonomyCapableProcessor` 等） | 已关闭 |
| `R08-VAL-PY-F02` | test processor constructor 对 protocol-valid calls 可调用 | 已关闭 |
| `R08-VAL-PY-F03` | test-local XBRL success TypeGuard 只按必有 public field 收窄 | 已关闭 |

## 4. Topic 6 设计决策逐项验证

### 4.1 批次所有权（§6.1 → 设计 §1）

- **Owner**: R06 batch/source（prior accepted commit）。R08 no-touch，仅验证 no-regression。
- **验证通过**。Storage transaction 使用显式 `BatchToken` authority；未发现 `ContextVar`/task/thread ambient identity 作为第二写入权限源。`fs_batching_repository.py` 所有 mutation 方法均要求 `batch=` 参数。

### 4.2 源发布与 Blob 所有权（§6.2 → 设计 §2）

- **Owner**: R06 batch/source（prior accepted commit）。R08 no-touch，仅验证 no-regression。
- **验证通过**。`ingest_complete=false` 不出现在任何 LLM-facing schema 或 tool description 中。Read runtime 的 `_build_citation`（`read_runtime.py:2610`）检查 `provenance.ingest_complete` 仅为 fail-closed 防御。

### 4.3 Provenance 与 Citation（§6.3 → 设计 §3）

- **Owner**: R07 provenance/revision/opaque mapping（prior accepted commit）。R08 no-touch，仅验证 no-regression。
- **验证通过**。Citation 从 `snapshot.provenance.source_provider` 的 typed `FinsSourceProvider` 枚举派生，经 `_FILING_SOURCE_TYPES_BY_PROVIDER` 与 `_CITATION_PROVIDER_LABELS` 单点映射。零处从 `document_id` 前缀、路径或文件名猜测 provider。

### 4.4 Revision 与 Read Consistency（§6.4 → 设计 §4）

- **Owner**: R07（prior accepted commit）。R08 no-touch，仅验证 no-regression。
- **验证通过**。Revision 由 storage-owned `SourceSnapshotProtocol` 持有；read runtime 不自行 hash 选中字段。`SourceSnapshotConsistencyError` 由 storage 抛出，read runtime 转换为 typed `FinsReadBusinessError(code=SOURCE_CHANGED_DURING_READ)`（`read_runtime.py:3138-3139`、`3427`）。全仓零命中 read runtime 自行构建 revision hash。

### 4.5 财务报表结果（§6.5 → 设计 §5）

- **Owner**: **R08**（本 tree）。
- **验证通过**。LLM-facing `PublicFinancialStatementResult`（`result_types.py:250-263`）仅包含 `ticker`、`document_id`、`citation`、`statement_type`、`periods`、`rows`、`currency`、`units`、`scale`、`data_quality`，以及 `NotRequired` 的 `reason`。
- `statement_locator` **已完全移除**：全仓零命中（production + tests + README）。
- `statement_method_missing` / `statement_empty` **已统一为 `statement_not_found`**。
- `determine_financial_statement_quality`（`financial_result_contract.py:159`）是 quality/reason 矩阵的**唯一 canonical owner**。
- `_FINANCIAL_STATEMENT_RESULT_DESCRIPTION`（`result_types.py:284-307`）为 LLM-facing 自足描述。

### 4.6 XBRL Facts 结果（§6.6 → 设计 §6）

- **Owner**: **R08**（本 tree）。
- **验证通过**。LLM-facing `PublicXbrlQueryResult`（`result_types.py:271-281`）仅暴露 `fact_count`（=`len(facts)`），**零处暴露 producer raw `total` 或 read-side `deduped_fact_count`**。
- AST 级验证（`test_read_runtime_semantic_ownership_guards.py:1269-1328`）：`result_types.py` 中 `fact_count` keyword 仅出现一次，值为 `len(...)` 调用。全仓零命中 `deduped_fact_count` / `raw_total`。

### 4.7 Direct Stream Terminal（§6.7 → 设计 §7）

- **N/A — deferred to R09**。当前 `ingestion_runtime._run_direct_stream`、`service._ensure_result_event`、`CLI._consume_fins_direct_events` 三层判断仍存在，这正是 R09 的 accepted target。R08 tree 无这些路径的改动，且未偷带。
- 设计 §7 明确了未来唯一 Fins-owned validator owner；R08 不实现、不验证、不声称 pass。

### 4.8 HKEX Discovery Completeness（§6.8 → 设计 §8）

- **N/A — deferred to R10**。`hkexnews_downloader.py` 不在 R08 diff 中（`git diff HEAD -- dayu/fins/downloaders/hkexnews_downloader.py` 为空）。当前 fail-closed 行为（满页且缺少总数时拒绝）是 pre-existing 状态，R10 将替换为 cumulative continuation。

### 4.9 Containment 与 Storage Key（§6.9 → 设计 §9）

- **Owner**: containment 为 pre-existing storage 边界；external identity → filesystem-safe private locator + descriptor 双向校验由 R07 accepted commit `64dbfbaf` / completion `28b6fc19` 的 `dayu/fins/storage/_fs_identity.py` 实现。R08 no-touch，仅验证 no-regression。
- **验证通过**。`_normalize_path_component`（`_fs_storage_utils.py:30-53`）拒绝 `.`、`..`、`/`、`\`、绝对路径与盘符——这是 private locator 的 path-component 层校验，不是 external opaque identity 的限制。External identity 到 private locator 的 mapping 与 descriptor 双向校验已在 R07 交付。`test_opaque_identity_round_trips_unicode_hierarchy_separator_drive_dot_and_dotdot`（`test_fins_storage_provider.py:2135`）证明 external opaque identities（含 Unicode、hierarchy、separator、drive、dot、dotdot 字符）可 exact round-trip 通过系统；仅派生 private locator path component 受 path normalizer 限制。`test_identity_mapping_detects_collision_corruption_and_business_meta_mismatch` 验证 identity descriptor fail-closed。R08 tree 中这些路径未变。

### 4.10 Upload Batch Plan（§6.10 → 设计 §10）

- **N/A — deferred to R11**。Fins typed batch plan 与 CLI script rendering 的最终裁决由 R11 承担。R08 no-touch，不验证、不声称 pass。

## 5. Adversarial Failure Pass 结论

### 5.1 已确认无缺陷的关键路径

| 路径 | 验证点 | 结论 |
|------|--------|------|
| `validate_financial_statement_result_payload` | exact keys、必填字段类型、quality/reason 矩阵、units≠scale、空 rows 拒绝 | 完整 |
| `validate_xbrl_facts_result_payload` | exact keys、扁平 query_params、fiscal_period 闭集校验、xbrl_not_available 零 facts | 完整 |
| `determine_financial_statement_quality` | scale/period 四象限矩阵、空 rows → ValueError（caller-owned）、直接证据原因三值独立 | 完整 |
| `infer_financial_scale_from_decimals` | bool/None/INF/float/string/out-of-range 全覆盖 | 完整 |
| `_deduplicate_xbrl_facts` | 去重键七元组、period_end 抑制 fiscal_period、六维优先级评分、稳定排序 | 完整 |
| `_build_citation` | `ingest_complete` fail-closed、typed provenance 映射、source kind 分支 | 完整 |
| `_normalize_xbrl_query_payload` | validate→copy→normalize→dedup→project 五步链，每步独立复制输入 | 完整 |
| `_raise_if_fins_cancelled` | 协作取消贯穿主要慢边界 | 完整 |
| `_normalize_document_identity` | ticker/document_id 标准化、ticker 未收录 → typed business error | 完整 |

### 5.2 Reviewer candidate observations（无当前 accepted finding）

以下为 adversarial failure pass 中识别到的 reviewer candidate observations。均标为 reviewer candidate，无当前 accepted finding。Controller 将基于 accepted plan / no-unrelated-change 边界逐项裁决。

| # | 位置 | 描述 | 严重程度 |
|---|------|------|---------|
| A1 | `read_runtime.py:2132-2211` | XBRL concepts 空/whitespace 列表（如 `[""]`）静默回退默认值，不报错也不提示 | reviewer candidate, LOW |
| A2 | `read_runtime.py:2221-2230` | XBRL filter 参数（`fiscal_year`、`min_value`/`max_value`）传入 processor 前未 pre-validate | reviewer candidate, MEDIUM |
| A3 | `read_runtime_helpers.py:720-724` | `_normalize_periods` 接受非字符串 list 元素，`normalize_optional_text` 将其静默转为字符串后下游过滤失败 | reviewer candidate, MEDIUM |
| A4 | `read_runtime_helpers.py:347` | `_CN_FORM_TYPE_TO_DOCUMENT_TYPE` 未 gate 在 source_kind；当前无实际 collision 但缺乏 defense-in-depth | reviewer candidate, LOW |
| A5 | `read_runtime_helpers.py:808` | `_to_optional_float` 使用 `except Exception`（过宽；应 `except (ValueError, TypeError)`） | reviewer candidate, LOW |
| A6 | `read_runtime_helpers.py:1334` | `_deduplicate_xbrl_facts` 排序 fallback key 在当前逻辑下不可达 | reviewer candidate, LOW |
| A7 | `xbrl_result_contract.py:337-338` | `_optional_fiscal_period` 中不可达的 `None` 检查（`FISCAL_PERIODS` membership 已保证非 None） | reviewer candidate, LOW |
| A8 | `read_runtime_helpers.py:1165` | `_normalize_xbrl_query_payload` 中冗余的 `query_params.copy()` | reviewer candidate, LOW |
| A9 | `financial_result_contract.py:244-245` | quality 一致性错误消息不含 expected vs actual 值 | reviewer candidate, LOW |

以上为 raw reviewer candidate observations。其中 A1–A6 位于 R08 未修改或 minimal-touch 的 pre-existing 路径；A7（`xbrl_result_contract.py` dead-code 分支）、A8（`read_runtime_helpers.py` 冗余 copy）、A9（`financial_result_contract.py` 错误消息）位于 R08 新/改实现文件。全部九项均无直接 material correctness / contract failure evidence，不构成 accepted finding。最终 acceptance 由 Controller 基于 accepted plan / no-unrelated-change 边界逐项裁决。

## 6. Overcoupling Pass 结论

### 6.1 Reviewer candidate observations（非 R08 引入或 minor maintainability，不阻塞）

1. **`fins_tools.py` → `DefaultFinsRuntime`**：process-backed execution 模型中子进程构造完整 service runtime，为有意的架构选择。Pre-existing。
2. **`FinsReadRuntime` 类体量（~3,400 行）**：职责可进一步拆分，但当前保持了 search/sub-runtime 的模块化分离。Pre-existing。
3. **`PageContentResult` 暴露 `SectionSummary`/`TableSummary`**：pre-existing 契约耦合。
4. **`_validate_exact_keys` / `_require_field` / `_is_json_value` 在两处 domain contract 中重复**：三个小函数在 `financial_result_contract.py` 与 `xbrl_result_contract.py`（均为 R08 修改文件）中独立维护。Minor maintainability concern，不构成 material defect。

### 6.2 R08 范围内的模块依赖

| 检查项 | 结论 |
|--------|------|
| `dayu.fins` → `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui` 跨层 import | 仅 `fins_tools.py` → `dayu.fins.service_runtime.DefaultFinsRuntime`（process-backed target）与 `ingestion/wait_adapter.py` → `dayu.host`（经 controller 授权的窄例外） |
| 循环 import | 无循环 |
| 兼容性 re-export / wrapper facade | 零命中 |
| `hasattr`/`getattr` 在生产代码中的使用 | 5 处 pre-existing，均为外部库对象交互 |

## 7. Semantic Ownership Drift Pass 结论

### 7.1 已确认语义 owner 正确的关键边界

| 语义 | Owner | 验证 |
|------|-------|------|
| 财务报表 quality/reason | `determine_financial_statement_quality`（`financial_result_contract.py`） | 单一 canonical owner |
| 财务报表 scale | `infer_financial_scale_from_decimals`（`financial_result_contract.py`） | 单一 source of truth |
| citation source_type/source_provider | `_build_citation`（`read_runtime.py`，从 `snapshot.provenance` 派生） | typed provenance → 单点映射 |
| XBRL fact_count | `project_xbrl_query_result`（`result_types.py:401`） | AST 级验证唯一赋值点 |
| document_type | `resolve_document_type_for_source`（`read_runtime_helpers.py:352`） | 统一 typed 入口 |
| XBRL concept 默认包 | `_resolve_default_xbrl_concepts`（`read_runtime_helpers.py:1115`） | 单点按 `(form_type, taxonomy)` 解析 |
| processor capability | 4 个 typed Protocol | `isinstance` 检查，零 `hasattr` 字符串探测 |

### 7.2 Pre-existing 语义漂移（非 R08 引入，reviewer candidate observations）

1. **`sec_fiscal_fields.py` fiscal year/period 三源 fallback 链**：pre-existing。Storage ingestion 应拥有 canonical fiscal fields；pipeline 只应读取。
2. **`_CN_FORM_TYPE_TO_DOCUMENT_TYPE`**：上传链路将财期写入 `form_type` 字段，read runtime 以映射表补偿。pre-existing。
3. **`resolve_has_financial_data` 四级兼容回退链**：含旧 `has_xbrl` / `has_financial_statement` 字段兼容。pre-existing。
4. **`_MATERIAL_FORM_TYPE_ALIASES`**：历史数据 typo 变体的别名映射。pre-existing。

## 8. Evidence Chain 审计

### 8.1 Prefix/Coverage Evidence（审计 AgentCodex/Controller locked evidence）

以下数值来自最终 immutable pyright-fix tree 的 AgentCodex fresh run 与 Controller 独立 re-run 的 locked evidence；本路 reviewer 审计 JSON hash 与差集一致性，未独立重跑覆盖率。

- prefix-five predecessor proof：`387/485 = 79.79381443% < 80.00%`，JSON hash `43986a2d...b59fb`
- prefix-six continuation proof（最终 tree）：`392 passed`，`391/485 = 80.61855670% >= 80.00%`，四行差集 `[344,346,348,442]`
- 15/15 changed production files 均达 `>=80.00%` exact-key coverage（minimum `80.17%`）
- Full Fins：`859 passed / 1 existing environment skip`
- Aggregate：`392 passed`

### 8.2 Pyright / Ruff / Scans（审计 Controller locked evidence）

- Full pyright：`0 errors`
- Changed Python Ruff：`0`
- `git diff --check`：pass
- Old-symbol deletion scans：`statement_locator`、`raw_total`、`deduped_fact_count`、`statement_method_missing`、`statement_empty` 全仓零命中
- Retained-owner scans：snapshot/citation/provenance 引用保留完整

### 8.3 R07 Snapshot/Citation No-Regression

- `_build_citation` 仍从 storage-owned provenance 派生
- `SourceSnapshotConsistencyError` → typed business error 路径保留
- R07 相关测试文件全覆盖

### 8.4 Security / No-Code / Deferred Boundaries

| 边界 | 验证 | 结论 |
|------|------|------|
| Topic 8（Engine 240-char） | `dayu/engine/agent.py:220` 未变 | ✓ |
| Topic 9（tool authorization） | 零 unified authorization framework 实现 | ✓ |
| Containment/symlink | `_normalize_path_component` + `_normalize_object_key` 保留完整 | ✓ |
| R09-R12 | R08 diff 不含 `dayu/engine/`、`dayu/host/`、`dayu/service/`、`dayu/ui/`、`dayu/cli/` 变更 | ✓ |
| Issues 142/151/175/177/178 | 无对应 scope 的实现代码 | ✓ |
| Host truncation owner | 未修改 | ✓ |

### 8.5 README 同步

- `dayu/fins/README.md`：`statement_locator` 已移除；`reason` 改为仅在 `partial` 时出现；`raw total`/`deduped_fact_count` 替换为 `fact_count=len(facts)`
- `tests/README.md`：新增 Financial/XBRL contract 测试覆盖说明
- 两处 README 变更均准确反映当前 contract 语义

## 9. Open Questions

无。

## 10. Planned Scope Status 与 Residual Risk

### 10.1 Planned sub-WU scope（非 R08 residual）

以下为 Topic 6 设计决策中已明确分配给后续 sub-WU 的 planned open scope，不属于 R08 defect 或 residual：

| Planned scope | Owner | 说明 |
|---------------|-------|------|
| Direct-stream terminal validator | R09 sub-WU | 当前三层检查为 R09 accepted target；R08 no-touch |
| HKEX cumulative rowRange continuation | R10 sub-WU | 当前 fail-closed 行为保留；R08 no-touch |
| Upload batch plan / script rendering | R11 sub-WU | R08 no-touch |

### 10.2 Reviewer candidate observations（pending Controller adjudication）

以下为三路审查中识别到的 reviewer candidate observations。均无当前 accepted finding，不构成 R08 accepted residual。Controller 将基于 accepted plan / no-unrelated-change 边界逐项裁决：

| # | 来源 | 描述 | 位置 |
|---|------|------|------|
| O1 | Semantic ownership | `sec_fiscal_fields.py` fiscal year/period 三源 fallback 链 | pre-existing，R08 no-touch |
| O2 | Semantic ownership | `_CN_FORM_TYPE_TO_DOCUMENT_TYPE` 补偿 CN form_type→fiscal_period 误写 | pre-existing |
| O3 | Semantic ownership | `resolve_has_financial_data` 四级兼容回退链 | pre-existing |
| O4 | Semantic ownership | `_MATERIAL_FORM_TYPE_ALIASES` 历史 typo 别名映射 | pre-existing |
| O5 | Overcoupling | `_validate_exact_keys` / `_require_field` / `_is_json_value` 在两处 domain contract 中重复 | R08-modified files，minor maintainability |
| A1–A9 | Adversarial | 见 §5.2 完整表格 | A1–A6 pre-existing；A7/A8/A9 在 R08 新/改文件 |

### 10.3 R08 actual accepted residual

**零。** 全部七个已接受 finding 已关闭；planned scope items（R09/R10/R11）为 next sub-WU entry，非 R08 residual；reviewer candidate observations O1–O5 与 A1–A9 均无直接 material correctness / contract failure evidence，待 Controller 裁决后决定是否进入 fix gate。

## 11. 附录：三路 Agent 审查交叉验证

本路 aggregate deepreview 独立执行并交叉验证了以下子审查的结论：

- **Overcoupling pass**（9 observations）：4 项 pre-existing 架构模式，其中 duplicate validation helpers 位于 R08 修改文件（minor maintainability，无 material defect）。HIGH labels 为有意的架构选择。
- **Semantic ownership drift pass**（11 observations，含 3 POSITIVE）：4 项 pre-existing 语义漂移在 R08 no-touch 文件中。POSITIVE observations 确认 Protocol-based capability check、LLM-facing description 清洁度、typed provenance citation 全部正确。
- **Adversarial failure pass**（9 reviewer candidate observations: A1–A6 pre-existing，A7/A8/A9 在 R08 新/改文件）：全部无直接 material correctness / contract failure evidence。无 CRITICAL 或 HIGH。

三路审查无冲突结论。本路未形成 material finding。零 accepted candidate。R08 范围内的 financial/XBRL minimal contract cleanup、diagnostic removal、LLM-facing schema 收窄与 semantic ownership 边界经逐文件走读确认正确实现。
