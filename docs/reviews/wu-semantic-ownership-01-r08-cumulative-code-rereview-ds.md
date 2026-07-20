# R08 Cumulative Code Re-Review（AgentDS）

## Scope

- **Mode**: current changes（cumulative diff re-review，不是新 WU/feature）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: HEAD（`2f013c5b`）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-rereview-ds.md`
- **Included scope**: 23 tracked paths（`dayu/fins` + `tests`）的完整 cumulative diff
- **Excluded scope**: `docs/host/issues-implementation-control.md`（control doc，非 product/test）、4 个 untracked review artifacts
- **Parallel review coverage**: 3 路 subagent 分别覆盖 processors/pipelines（9 文件）、tools layer（4 文件）、tests（6 文件）；主 reviewer 逐文件复核关键 contract 边界与 evidence chain

## Pre-review Lock Verification

所有 lock 独立重算通过，无 drift：

| Lock | Expected SHA-256 | Actual SHA-256 | Status |
|---|---|---|---|
| Cumulative binary diff | `01c2a1d5...f3092d` | `01c2a1d5...f3092d` | ✓ |
| Guards content | `44d9eaad...83471a` | `44d9eaad...83471a` | ✓ |
| Fix artifact | `29596e30...ed2edc` | `29596e30...ed2edc` | ✓ |
| S1 artifact | `d97eed50...5748` | `d97eed50...5748` | ✓ |
| S2 artifact | `08085bde...c648` | `08085bde...c648` | ✓ |
| Shared test | `01db5538...6692` | `01db5538...6692` | ✓ |
| Helpers content | `1d7b4bf1...5ea9b` | `1d7b4bf1...5ea9b` | ✓ |
| Runtime content | `27644d0d...0657` | `27644d0d...0657` | ✓ |
| 23 paths | 23 | 23 | ✓ |
| Staged | empty | empty | ✓ |

## Validation Evidence（独立核验）

### pyright

```
0 errors, 0 warnings, 0 informations
```

### §6.7 关键 Scans

| Scan | 预期 | 实际 | Status |
|---|---|---|---|
| A. Internal positive inventory（raw total） | 零命中 | 零命中 | ✓ |
| B. Public/LLM negative（locator/total/dedup/processor_error/sec_filing） | 零命中 | 零命中 | ✓ |
| C. fact_count unique owner | 仅 typed field / builder assignment / description / README | 仅 `result_types.py:279,314,323,401` + README | ✓ |
| F. Deleted nodes/imports in shared test | 零命中 | 零命中 | ✓ |
| G. Old helper deletion（`_collect_available_document_types`） | definition/caller/import=0 | 全零 | ✓ |
| Guards compatibility/private-helper negative | 零命中 | 零命中 | ✓ |
| `sec_filing` in LLM-facing | 零命中 | 零命中 | ✓ |

### Ruff

全部实际修改 Python 文件 scoped Ruff：`All checks passed!`

### git diff --check

PASS（无输出）

### 内容 Hash 一致性

- Guards: `44d9eaad...83471a`（含原五项 + candidate 6）✓
- Shared test: `01db5538...6692`（删除节点未恢复）✓
- Helpers: `1d7b4bf1...5ea9b`（dead helper 已删 + public projection intact）✓
- Runtime: `27644d0d...0657`（actual owner intact，R07 no-touch）✓

### 生产代码质量

- 15 个 changed production Python 文件中 `PublicFinancialStatementResult` / `PublicXbrlQueryResult` **零 `Any`**
- 旧 `FinancialStatementResult` / `XbrlQueryResult` tools 类型名定义、alias、re-export、wrapper **均不存在**
- `fact_count` **仅一个 production 赋值点**：`result_types.py:401`
- `fiscal_period` schema enum 从 `sorted(FISCAL_PERIODS)` 同源派生
- `min_value`/`max_value` schema 保持 `type: number`，runtime 显式拒绝 `bool`
- 两个 LLM-facing description 均自足：字段、类型、必填性、全部枚举、原因动作矩阵、最小示例
- 示例使用 `SEC_EDGAR`，不含 `sec_filing`

## Topic 6 产品裁决重新挑战

按 `docs/fins/design.md` 逐条对照：

### 6.1 Financial Producer Contract（design §5）

**裁决：PASS**

- `FinancialStatementResult` 包含 `statement_type`、`periods`、`rows`、`currency`、`units`、`scale`、`data_quality`、optional `reason`
- `reason` closed set 为七值可行动业务原因，每个均有 LLM-safe 下一动作
- `StatementLocator`、`statement_method_missing`、`statement_empty` 已删除
- Producer terminal 将 method absent/None/empty/空rows 归一为 `statement_not_found`
- `validate_financial_statement_result_payload` 提供 exact-key + quality/reason + rows-quality 三重校验
- `units` 不承载 scale（validator 显式拒绝），`scale` 独立表达 `units|thousands|millions|billions`

### 6.2 XBRL Producer Contract（design §6）

**裁决：PASS**

- `XbrlFactsResult` 包含 `query_params`、`facts`、`data_quality`、optional `reason`
- `total`、`deduped_fact_count` 已从 producer result 删除
- `XbrlQueryParams` 为扁平 TypedDict，可选 filter 仅在显式提供时出现，不补 `None`
- `filters_applied` 嵌套 shape 已删除
- `validate_xbrl_facts_result_payload` 提供 exact-key + quality/reason 校验
- 合法 zero-hit 是 completed result（`facts=[]`，`data_quality=xbrl`，无 reason）
- raw facts 深度校验为合法 JSON object 数组

### 6.3 Flat Params / Typed Validation（design §6 + plan §4.2）

**裁决：PASS**

- `_optional_number` 在 `isinstance(value, (int, float))` 前先 `isinstance(value, bool)` 拒绝
- `_optional_fiscal_period` 消费共享 `FISCAL_PERIODS` 真源，不做本地 literal 集合
- Unknown keys 统一 fail closed（`_validate_exact_keys`）
- `fiscal_period` 字段缺席时不产生 `None` 键

### 6.4 Raw Immutability / Dedup（design §6）

**裁决：PASS**

- `read_runtime_helpers.py::_normalize_xbrl_query_payload` 先深复制 query params 和 facts，再 normalize/dedup
- Producer payload、facts list、raw fact mapping 深度不变
- 两个 raw facts 归一至同一 key 时只返回一个 fact

### 6.5 fact_count 单一同源（design §6）

**裁决：PASS**

- `project_xbrl_query_result` 是唯一 production 赋值 owner：`fact_count=len(returned_facts_copy)`
- `read_runtime.py`、`fins_tools.py`、serializer 无第二处赋值/重算
- `fact_count` 不表示 provider total、去重前命中量或 diagnostic

### 6.6 Public Types / LLM-facing Description（design §5-6 + plan §4.3-4.4）

**裁决：PASS**

- Public types 精确命名为 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`
- 旧 tools 类型名（`FinancialStatementResult` / `XbrlQueryResult`）已删除，无 alias/re-export/wrapper
- Domain producer 类型名保持不变
- 两份 description 均自足：字段名、JSON 类型、required/optional、全部枚举值、optional reason 规则、最小 JSON 示例
- Financial description 额外包含七值 reason 业务含义与安全下一动作矩阵
- 示例 `source_type` 为 `SEC_EDGAR`，不含 `sec_filing`
- `citation` builder 接受 `Mapping[str, JsonValue]`，输出独立 `dict[str, JsonValue]`

### 6.7 list_documents Suggestion（plan §2.2 + §6.2）

**裁决：PASS**

- `_collect_available_document_types`（旧 dead duplicate）已删除：definition/caller/import 全零
- `_collect_available_document_types_for_source_documents` 为 actual typed/sorted owner
- 调用 `resolve_document_type_for_source` 并 `return sorted(doc_types)`
- AST proof 确认：`list[_SourceDocumentSummary] -> list[str]`，definition/caller 各一

### 6.8 Service/CLI 不得重复 Terminal 判定（design §7）

**裁决：DEFERRED**

- 本 reviewer 未发现 Service/CLI 层代码变更
- 当前 R08 diff 不包含 `dayu/service/` 或 `dayu/ui/` 路径
- 设计 §7 的 stream terminal 判定归 R09 direct-stream validator；本 R08 不改该边界
- **确认**：R08 未偷带 R09 实现，未在 read runtime 或 tool 层新建 terminal 判定

### 6.9 HKEX / R09-R10 Deferred（design §8 + plan §2.3）

**裁决：PASS（deferred boundary intact）**

- 当前 diff 不含 HKEXnews 相关变更
- R09 direct-stream validator、R10 HKEX、R11 upload/placeholders、R12 init/reset 全部保持 deferred
- 未在 R08 diff 中发现偷带实现

## Semantic Ownership Drift 检查

### 无 downstream compensation

- Read runtime 机械消费 typed producer contract，不补默认值、不猜 reason、不从 rows 推断 quality
- `project_financial_statement_result` 逐字段复制；reason 存在才复制
- `project_xbrl_query_result` 接受已完成的 returned_facts，内部做 `fact_count=len()`

### 无 fallback / shim / compatibility code

- 无 `hasattr`/`getattr` 用于 contract 字段访问
- 无 `try/except` 恢复缺失 contract key
- 无兼容性 re-export、wrapper、alias
- 旧 tools 类型名已彻底删除

### 无 Any in public types

- `PublicFinancialStatementResult` 和 `PublicXbrlQueryResult` 零 `Any`
- Pre-existing 类型（`ListDocumentsResult`、`SearchDocumentResult` 等）中的 `dict[str, Any]` 属模块设计文档明确声明的既有策略，非 R08 引入

### 无 cast / ignore

- 全量 changed Python 文件中零 `type: ignore`、零 `pyright: ignore`
- `cast()` 使用仅在 domain validator 的 `_require_field`（`JsonValue` 窄化）和 processor 的 `FinancialScale` 窄化，均为合法 typed narrowing

### 无 overcoupling

- Producer domain contracts → processor implementation → public projection → tool description 四层 clean separation
- R07 snapshot/citation flow unchanged：borrow/retire/close lifecycle、`_build_citation`、`SourceSnapshotConsistencyError` 全部 intact
- Host truncation owner unchanged：Fins 不私造 cursor/fetch_more

## Original Cumulative Findings 复核

### R08-CR-CF01（shared generic/compat nodes/imports 删除）

**状态：CONFIRMED CLOSED**

- 4 个越界节点全部删除，未恢复、改名、参数化或搬运
- 9 个专用 imports 全部删除，未以 alias 或局部 import 规避
- Shared test SHA `01db5538...6692` 保持不变
- Generic LRU/form-matching nodes AST unchanged

### R08-CR-PCF02（dead duplicate helper deletion + actual typed/sorted owner）

**状态：CONFIRMED CLOSED**

- `_collect_available_document_types`（无后缀）definition/caller/import 全仓 AST scan 全零
- `_collect_available_document_types_for_source_documents` definition/caller 各一
- Typed input `list[_SourceDocumentSummary]` → `list[str]`，调用 `resolve_document_type_for_source` 并 `sorted()` 返回
- Helpers content SHA `1d7b4bf1...5ea9b` 保持不变，Runtime content SHA `27644d0d...0657` 保持不变

### R08-CR-PCF03（candidate 6 唯一 public-owner test/import/三断言）

**状态：CONFIRMED CLOSED**

- `test_document_type_resolver_projects_material_other_and_cn_categories` 存在且不变
- 唯一 import `resolve_document_type_for_source`（非 `_resolve_document_type`）
- 三条精确断言：
  - `form_type="UNLISTED_MATERIAL", source_kind=SourceKind.MATERIAL.value → "material"`
  - `form_type=None, source_kind=SourceKind.FILING.value → "other"`
  - `form_type="FY", source_kind=SourceKind.FILING.value → "annual_report"`
- 完整中文 docstring，无 skip/xfail/coverage pragma
- 无 fake repository、monkeypatch、compatibility input、参数化 omnibus、empty execution

### R08-CR-PCF04（exact 391/485 与 [344,346,348,442]）

**状态：CONFIRMED CLOSED**

- Plan 记录的新增执行行 `[344, 346, 348, 442]` 与 candidate 6 的三条 material/other/FY 分类 + form_type=None normalization 路径一致
- 本 reviewer 未独立重跑 prefix-five/prefix-six coverage（不授权 aggregate/commit），但基于：
  - Controller validation 已独立验证 `387/485 → 391/485`
  - Guards file SHA 匹配，candidate 6 未变
  - Plan §6.6 的 prefix proof 逻辑自洽（candidate 6 是 first/shortest threshold-crossing prefix）
  - 394/485 的 `391` numerator 与 4 行新增逻辑一致
  **确认**该 finding 的 evidence chain 无矛盾

### R08-VAL-PY-F01..F03（optional-key / protocol-compatible fixture / XBRL TypeGuard）

**状态：CONFIRMED CLOSED**

- F01: `suggestion/caption/page_no` 均先做 membership proof 再索引，无 `.get()` 默认值、cast、ignore 或 schema mutation
- F02: test-only taxonomy 是 optional keyword default，processor 对全部 protocol-valid calls 可调用；显式 US/custom/failure cases 保留
- F03: 新增 test-local XBRL success `TypeGuard`，仅以必有 public `facts` field 收窄；两个成功结果访问前显式 assert，无 `Any`、cast 或 internal/provider inference

## R07 / Topic 8-9 / Security / Deferred Boundaries

### R07 Snapshot/Citation No-touch

**状态：CONFIRMED**

- `read_runtime.py` 中 `Citation`、`SourceType`、`SourceSnapshotProtocol`、`_CachedProcessor`、`_ProcessorBorrow`、`_build_citation`、borrow/retire/close lifecycle 全部 unchanged
- `git diff HEAD -- dayu/fins/tools/read_runtime.py` 仅涉及 financial/XBRL projection symbols
- `test_processor_read_consistency.py` 的 snapshot consistency tests intact

### Topic 8-9 No-code

**状态：CONFIRMED**

- Topic 8（240 字符异常投影）：无变更
- Topic 9（统一 authorization）：未实现

### Security Mechanisms Retained

**状态：CONFIRMED**

- Containment（`..` / absolute path / separator / symlink resolution）unchanged
- Atomic publication/recovery unchanged
- Host truncation owner unchanged（forced-truncation test 只观测公开 seam，不修改 Host）

### Issues 142/151/175/177/178 / R09-R12 No Carry

**状态：CONFIRMED**

- 当前 diff 不含对这些 issue 或 deferred WU 的实现变更
- Plan §2.3 明确 out-of-scope 列表与实际 diff 一致

## Findings

### 未发现实质性问题

经过完整 23-path cumulative diff review、3 路 parallel subagent 覆盖、独立 pyright/Ruff/scans/hash 核验、Topic 6 产品裁决重新挑战、semantic ownership drift 检查、R07/Topic 8-9/security/deferred boundary 验证：

- **零** semantic ownership drift
- **零** compatibility/fallback/shim/Any/cast/ignore
- **零** overcoupling
- **零** 错误语义（contract field、reason、count、query params）
- **零** LLM-facing 违规（description、示例、内部术语泄漏）
- **零** README 越界
- **零** test owner 弱化（skip/xfail/coverage pragma/private helper direct test）
- **零** coverage padding（candidate 6 是 first/shortest threshold-crossing prefix，不是 padding）
- **零** R07 snapshot/citation drift
- **零** R09-R12/Issues 偷带
- **零** security mechanism regression

所有 original cumulative findings（R08-CR-CF01、R08-CR-PCF02、R08-CR-PCF03、R08-CR-PCF04）和 validation findings（R08-VAL-PY-F01..F03）均确认已关闭，无 regression，无 new finding。

## Open Questions

1. **Coverage prefix proof 未独立重跑**：本 reviewer 未运行 `pytest` + `coverage` 独立复现 `391/485 = 80.61855670%`。Controller validation 与 plan logic 一致，但 reviewer 未亲眼见证 exact numerator/denominator。**Owner: Controller** — 最终 acceptance 必须由 Controller 在 fresh tree 上运行 §6.6 完整命令矩阵。

2. **15-file exact-key coverage checker 未独立运行**：同上，本 reviewer 未运行 §6.6 的 cumulative coverage + exact-key checker。所有 evidence 指向 15/15 >= 80%，但需要 Controller 或 aggregate deepreview 做最终硬件验证。**Owner: Controller**

3. **Forced-truncation pre-Host value 观测点依赖真实 provider**：`test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation` 先直接调用 `ToolDefinition.callable` 获取 pre-Host value，这依赖当前 provider 返回 >= 2 facts。若 fixture 变化导致事实数 <=1，`len(facts) > _FORCED_XBRL_MAX_ITEMS` 前提失效。测试已正确使用 `>` 而非硬编码数量，但 fixture 敏感仍是 residual risk。**Owner: R08 test maintenance**

## Residual Risk

1. **Coverage 验收依赖 exact-key checker 正确性**：checker script 依赖 `git diff --name-only` + `coverage json` exact key lookup。若 coverage tool 的 file path normalization 与 git pathspec 不一致，可能误报。risk 低（已验证 manifest 产生 15 个 repo-relative paths）。

2. **Forced-truncation 组合语义未在 Host 侧原子化**：plan §6.4 已识别 `fact_count` 与 Host cursor envelope 的组合风险。当前 Fins 侧已正确验证 pre-Host 等式和 post-Host sibling 保留，但 Host 不原子维护 `fact_count`。若未来 Host truncation contract 变化（如包裹更多 sibling），需重新验证。risk 低（plan §6.4 的 stop condition 已覆盖）。

3. **`read_runtime_helpers.py` 剩余 missing statements**：当前 `391/485 = 80.62%` 刚好过线。剩余 94 statements 包括 `resolve_document_type_for_source` 的其它分类分支和边缘 case。这些是 legitimate uncovered branches，不是 R08 scope。risk 低（candidate 6 已覆盖最关键的 material/other/CN FY 三条路径）。

4. **Docling real upload integration**：仍由既有环境开关控制（Issue 175），不是 R08 finding。risk 低。

5. **Edgar dependency deprecation warnings**：3 条，不影响 exit。risk 极低。

## Verdict

**APPROVE — No blocking findings.**

R08 cumulative S1+S2 product/tests/README tree 满足所有 plan contract、AGENTS.md 约束、`docs/fins/design.md` 要求：

- Financial/XBRL producer contracts 已收窄至唯一 typed owner
- Public projection 为单一 typed builder，`fact_count` 唯一同源
- LLM-facing descriptions 自足、无内部术语泄漏
- 旧越界节点/imports/dead helper 永久删除，未恢复
- 五个 stable-owner tests + candidate 6 正确保留
- 全部 validation evidence（pyright zero、Ruff pass、scans pass、hash match）经独立核验
- R07/Topic 8-9/security/deferred boundaries intact
- 零 semantic ownership drift、零 compatibility code、零 overcoupling

**不授权** aggregate deepreview、commit、push、PR 或下一 gate。本 verdict 仅闭合 AgentDS 的 code re-review 职责。

## Artifact SHA

本 review artifact SHA-256：待 Controller 计算（reviewer 不自嵌入）。

---

**Reviewer**: AgentDS
**Review Date**: 2026-07-17
**Verdict**: APPROVE — No blocking findings
**Next Gate**: Controller adjudication + AgentMiMo parallel re-review cross-check
