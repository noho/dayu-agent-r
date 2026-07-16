# WU-SEMANTIC-OWNERSHIP-01 R08 Cumulative Code Review — AgentMiMo

## 0. Review Lock Verification

| 项 | 预期值 | 独立重算 |
|---|---|---|
| tracked `git diff --binary` SHA-256 | `4d346f2bd05d26673ed0a1ec680cd6a1fe68d976340dfea302c55ad912354d4b` | `4d346f2bd05d26673ed0a1ec680cd6a1fe68d976340dfea302c55ad912354d4b` ✓ |
| S1 artifact SHA-256 | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` ✓ |
| S2 artifact SHA-256 | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` ✓ |

三个 hash 全部精确匹配，tree 未漂移。

## 1. 审查范围

覆盖完整 23 tracked changed paths + 2 implementation artifacts：

- **Production（15）**：domain contracts 2 + processors 8 + pipeline 1 + tools 4
- **Tests（6）**：全部 S1/S2 授权 test files
- **README（2）**：`dayu/fins/README.md`、`tests/README.md`
- **Artifacts（2）**：S1 + S2 implementation codex

## 2. Verdict

**PASS — 0 Critical, 0 High (R08-scope), 2 Medium (pre-existing), 12 Low, 4 Info**

R08 S1+S2 cumulative implementation 的核心 contract 变更正确、完整、语义所有权清晰。所有计划要求的 producer contract 收窄、terminal unification、public projection 建立、唯一 `fact_count` owner、tool description 自足性、R07 no-touch、forced-truncation 组合验证均已满足。无 accepted-candidate 需要阻塞。

## 3. Findings

### 3.1 Correctness 与 Producer/Public Contract（全部 PASS）

| 检查项 | 结果 | 证据 |
|---|---|---|
| Financial producer 恰好 7 required + optional reason | PASS | `financial_result_contract.py:53-64`，所有 producer 构造一致 |
| StatementLocator 完全删除 | PASS | `grep -rn` 全 dayu/fins/ + tests/fins/ 零命中 |
| Financial reason 七值闭集 | PASS | `financial_result_contract.py:28-36` |
| complete 无 reason / partial 有 reason | PASS | validator lines 226-229，所有 producer 一致 |
| method absent/None/empty → `statement_not_found` | PASS | sec_processor:612-653, bs_report_form_common:372-385, bs_six_k_processor:351-393 |
| `_build_financials_payload` 删除 | PASS | `grep -rn` 零命中 |
| XBRL flat query params（无 nested `filters_applied`） | PASS | `xbrl_result_contract.py:40-48` |
| XBRL result 无 count 字段 | PASS | `xbrl_result_contract.py:52-58`，`total`/`deduped_fact_count` 零命中 |
| `min_value`/`max_value` 显式拒绝 bool | PASS | `xbrl_result_contract.py:362-363` |
| `fiscal_period` 消费共享 `FISCAL_PERIODS` | PASS | `xbrl_result_contract.py:334`，`fins_tools.py:1723-1725` |
| `PublicFinancialStatementResult` / `PublicXbrlQueryResult` 精确命名 | PASS | `result_types.py:250,271` |
| 旧 tools 类型名无 alias/re-export/wrapper | PASS | domain import alias 仅用于 builder 参数类型，非 re-export |
| `fact_count` 唯一赋值 `len(returned_facts_copy)` | PASS | `result_types.py:401`，read_runtime/helpers/fins_tools 零赋值 |
| Builder citation 独立 dict 副本 | PASS | `result_types.py:352,399`，`dict(citation)` 不 alias 输入 |
| Tool description 自足（字段/类型/必填/枚举/reason矩阵/SEC_EDGAR示例） | PASS | `result_types.py:284-324` |
| `sec_filing` 不在 tools/prompts/README/test 扫描目标 | PASS | `grep -rn` 零命中 |

### 3.2 Input Deep Immutability 与 Stable Dedup（全部 PASS）

| 检查项 | 结果 | 证据 |
|---|---|---|
| Financial validator 不修改 raw payload | PASS | 只读 `_require_field` + `dict(raw_row)` 副本 |
| XBRL validator 不修改 raw payload | PASS | `_required_query_params` 构造新 dict，`dict(item)` 副本 facts |
| Read XBRL 路径：validate → copy → normalize → dedup → builder | PASS | `read_runtime_helpers.py:1194-1208` |
| Normalize 不覆盖 raw fact | PASS | `_normalize_single_fact` 返回新 dict |
| Stable dedup 前后 raw payload 深度相等 | PASS | test `test_xbrl_query_payload_preserves_raw_input_during_normalization` |
| Zero-hit XBRL：`facts=[]`, `fact_count=0`, `data_quality=xbrl`, reason 缺席 | PASS | test `test_xbrl_query_payload_zero_hit_has_single_count_and_no_reason` |

### 3.3 R07 No-Touch（PASS）

| 检查项 | 结果 | 证据 |
|---|---|---|
| Snapshot acquire/borrow/release 零变更 | PASS | `_CachedProcessor`/`_ProcessorBorrow` 完整生命周期在 diff 外 |
| Cache revision 零变更 | PASS | `_CachedProcessor.matches()` line 225 不在 diff |
| Citation generation 零变更 | PASS | `_build_citation` line 2585 不在 diff |
| Source-changed paths 零变更 | PASS | `_raise_source_changed_during_read` line 3427 不在 diff |
| 21 个 R07 函数 AST 与 HEAD 相同 | PASS | S2 artifact 证据 |
| Storage/Host/Engine/Service/UI/prompts 零 diff | PASS | S2 artifact 证据 |

### 3.4 Host Truncation Composition（PASS）

| 检查项 | 结果 | 证据 |
|---|---|---|
| Pre-Host `fact_count == len(facts)` | PASS | `test_fins_storage_provider.py:3788` |
| Host 只替换 `facts` 为 cursor envelope | PASS | `test_fins_storage_provider.py:3815-3818` sibling 等式 |
| `fetch_more` remainder 拼接恢复原 facts | PASS | `test_fins_storage_provider.py:3852` |
| 未读取私有 TruncationManager/cursor 状态 | PASS | 测试只使用公开 seam |

### 3.5 Scans（全部 PASS）

| Scan | 范围 | 结果 |
|---|---|---|
| Internal raw-total positive inventory | 6 owner roots | 0 命中 |
| Financial/internal negative | domain+processors+pipeline+tests | 0 命中 |
| Public/tool/schema/serializer/LLM forbidden | tools+prompts+READMEs+4 tests | 0 命中 |
| `fact_count` unique owner | result_types+helpers+read_runtime+fins_tools+prompts+READMEs | 仅 result_types.py builder 赋值 |
| R07 no-touch propagation | read_runtime.py diff | 仅 financial/XBRL projection symbols |
| Exact allowlist | 全 tree | 无 R09-R12/Issues/Host/Engine/Service/UI 越界 |

### 3.6 Test Quality 审计

| 检查项 | 结果 | 备注 |
|---|---|---|
| Public contract exact key assertions | PASS | `_assert_financial_result_contract()` 使用 `set(result)=={...}` |
| 无 compat locking（locator/total/deduped_fact_count） | PASS | 零断言旧字段 |
| 无 fake-only paths（AAPL 真实 fixture） | PASS | `test_real_sec_processor_reads_and_projects_aapl_fixture` 使用真实 fixture |
| Stable dedup assertions | PASS | `deepcopy` + equality + `fact_count==len(facts)` |
| Forced-truncation 三段链路 | PASS | 见 §3.4 |
| R07 same-snapshot citation | PASS | `test_citation_and_result_use_the_same_borrowed_snapshot` |
| 无 skip/xfail/pragma/omit | PASS | 全部 6 文件零 |
| 无 coverage-only 空执行 | PASS | 所有 test 函数含实质断言 |

## 4. Accepted-Candidate Findings（不阻塞，记录备查）

### F-01 | Severity: LOW | Duplicated `_is_json_value` / `_validate_exact_keys`

- **文件**：`financial_result_contract.py:435,260` 与 `xbrl_result_contract.py:454,146`
- **证据**：两个模块含逐字符相同的私有 helper
- **Root owner**：R08 implementor
- **风险**：未来修改时可能 drift。但两个 domain contract 设计为自包含，当前无第三个消费者
- **修复方向**：若出现第三个消费者，抽取到 `dayu/fins/domain/_json_validation.py`

### F-02 | Severity: LOW | `_required_xbrl_data_quality` 缺少显式 `isinstance(value, str)` guard

- **文件**：`xbrl_result_contract.py:420-424`
- **证据**：直接比较 string literal 而不先检查类型；`financial_result_contract.py:494` 有显式 guard
- **Root owner**：R08 implementor
- **风险**：运行时无影响（Python equality 自然拒绝非 string），但与 financial contract 防御模式不一致
- **修复方向**：在 equality check 前加 `if not isinstance(value, str)` guard

### F-03 | Severity: LOW | `_resolve_processor_taxonomy` 使用 bare `object` 类型

- **文件**：`read_runtime_helpers.py:1103`
- **证据**：`def _resolve_processor_taxonomy(processor: object)` 但函数体内已有 `isinstance(processor, XbrlTaxonomyProcessor)` guard
- **Root owner**：R08 implementor
- **风险**：违反 AGENTS.md "禁止使用 `object`" 约束
- **修复方向**：改为 `XbrlTaxonomyProcessor` 或带 Protocol 的 Union 类型

### F-04 | Severity: LOW | XBRL builder 双重 copy

- **文件**：`read_runtime_helpers.py:1195-1196` + `result_types.py:394,400`
- **证据**：helpers 先 copy query_params/facts，builder 再 copy 一次
- **Root owner**：R08 implementor
- **风险**：无功能影响，仅冗余 copy。builder 的 copy 是 public contract 保证，helpers 的 copy 是防御性的
- **修复方向**：可删除 helpers 层 copy，但保留也无害

### F-05 | Severity: LOW | `_optional_fiscal_period` 返回类型注解含不可能的 `None`

- **文件**：`xbrl_result_contract.py:317`
- **证据**：返回 `FiscalPeriod | None` 但 `None` 分支是 dead code（`value not in FISCAL_PERIODS` guard 已拒绝）
- **Root owner**：R08 implementor
- **风险**：无运行时影响
- **修复方向**：可收紧为 `FiscalPeriod` 或保留防御 guard

## 5. Pre-Existing Findings（不在 R08 scope，记录备查）

### F-06 | Severity: MEDIUM | Processor 层广泛使用 `Any` / `object` 类型注解

- **文件**：`html_financial_statement_common.py:155,240,287,804,1722`、`six_k_form_common.py:469,889,1920`、`report_form_financial_statement_common.py:191,258,328`、`sec_processor.py:811`、`sec_xbrl_query.py:129,215,262,307`、`bs_report_form_common.py:67,418,437`、`bs_six_k_processor.py:449,483,541,567`
- **证据**：约 20+ 处 `list[Any]`、`table: Any`、`value: Any`、`-> Any` 等
- **Root owner**：各 processor 文件原有作者（R08 scope 之外的 pre-existing 问题）
- **风险**：违反 AGENTS.md "禁止使用 `Any`" 约束，但 full pyright 为 0 errors，不影响类型安全
- **修复方向**：应作为独立 cleanup WU 或纳入后续 processor 类型收紧工作。R08 不应顺手修改超出 contract scope 的签名

### F-07 | Severity: MEDIUM | `result_types.py` 二级 TypedDicts 使用 `dict[str, Any]`

- **文件**：`result_types.py:107,120,146,171,193,214,242` 等（`ListDocumentsResult`、`DocumentSectionsResult` 等 7 个类型）
- **证据**：模块 docstring line 8 已记录为 intentional deferral
- **Root owner**：result_types.py 原有作者
- **风险**：pre-existing，且两个 public financial/XBRL 类型正确使用 `JsonValue`
- **修复方向**：后续 cleanup 中替换为 `dict[str, JsonValue]`

### F-08 | Severity: LOW | `read_runtime_helpers.py` 多处 helper 函数使用 `Any` 参数

- **文件**：`read_runtime_helpers.py:454,514,700,819,850,912,938,972,1006,1052,1121,1404,1423,1445,1469`
- **证据**：normalizer/coercion 函数接收 raw JSON 输入
- **Root owner**：read_runtime_helpers.py 原有作者
- **风险**：pre-existing，可用 `JsonValue` 替代
- **修复方向**：后续 cleanup

### F-09 | Severity: LOW | `sec_processor.py:_parse_document` 返回 `Any`

- **文件**：`sec_processor.py:811`
- **证据**：返回 edgartools `Document` 对象但标注为 `Any`；具体类型 import 可用
- **Root owner**：sec_processor.py 原有作者
- **风险**：pre-existing
- **修复方向**：标注为具体 edgartools 类型或 `object`

### F-10 | Severity: LOW | `bs_report_form_common.py:_get_xbrl` 静默吞异常

- **文件**：`bs_report_form_common.py:497`
- **证据**：`except Exception: self._xbrl = None` 无日志；`sec_processor.py:783` 有 `Log.warn`
- **Root owner**：bs_report_form_common.py 原有作者
- **风险**：XBRL 加载失败时丢失诊断可见性
- **修复方向**：添加 `Log.warn` 日志

## 6. Coverage Closure 质量审计

### 6.1 公共 processor contract 路径（接受）

- `SecProcessor`：真实 AAPL fixture 经 `supports/list/read/search/get_financial_statement/query_xbrl_facts/get_xbrl_taxonomy`
- `BsSixKFormProcessor`：经 `supports/list/read/search/get_financial_statement` 观察 HTML、低置信 terminal、OCR fallback
- 未直接调用 `_collect_*` / `_get_xbrl()` 私有方法

### 6.2 稳定业务规则唯一 owner（接受）

- `_normalize_xbrl_query_payload`：S2 normalize/dedup/public projection composition owner，六个 nodes 断言 fail-closed、输入不变、stable dedup、optional reason、zero-hit
- HTML/6-K helpers：`_extract_first_date`、`_extract_fiscal_period_year` 等为稳定格式解析规则唯一 owner
- `_normalize_document_types` / `_normalize_periods` / `_normalize_section_children` 等为 public tool filters 规则唯一 owner

### 6.3 测试私有方法访问（accepted-candidate）

- `test_processor_read_consistency.py` 和 `test_fins_storage_provider.py` 大量访问 `_borrow_processor`、`_processor_cache` 等私有内部
- 原因：snapshot 生命周期、cache eviction、并发 build dedup 无公开检查 API
- 状态：accepted，若有公开 debug surface 应迁移

### 6.4 无 coverage-only 空执行 / skip/xfail / pragma/omit

全部 6 个 test 文件、390 个 collected nodes 均含实质断言。

## 7. README 审计

| 检查项 | 结果 |
|---|---|
| `dayu/fins/README.md` 只陈述 current contract | PASS |
| `tests/README.md` 只陈述 current owner-level tests | PASS |
| 无 locator/raw-total/dedup count/processor 术语 | PASS |
| 无 R08/gate/review/未来计划 | PASS |
| 无 `sec_filing` source type | PASS |

## 8. Deferred Boundaries（未实施，正确保持 out-of-scope）

R09-R12、Issues 142/151/175/177/178、统一 tool authorization、Host/Engine/Service/UI 变更、storage transaction/publication/identity/revision/snapshot/citation/provenance owner 均未触及。正确。

## 9. 综合评估

R08 S1+S2 cumulative implementation 是一次精确的 producer→public contract 收窄：

1. **Producer owner** 删除了 locator、内部 method/empty reasons、raw count，terminal 统一为 `statement_not_found`
2. **Public projection** 建立了唯一 typed owner，`fact_count` 单一赋值，citation 独立副本
3. **Tool description** 自足说明所有字段、枚举、七值 reason 矩阵和 SEC_EDGAR 示例
4. **Read composition** 固定为 validate→copy→normalize→dedup→builder，不猜不补
5. **R07 snapshot/citation/provenance** 完全 no-touch
6. **Host truncation** 通过三段公开链路验证，Fins 未越界

所有 findings 均为 LOW 或 pre-existing MEDIUM，无阻塞项。
