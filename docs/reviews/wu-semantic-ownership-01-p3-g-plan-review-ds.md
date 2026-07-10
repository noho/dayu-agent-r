# Plan Review — WU-SEMANTIC-OWNERSHIP-01 P3-G

## Scope

- Mode: plan review (adversarial)
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G - Fins form/domain typed rules and processor result contracts`
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-g-fins-domain-contracts-plan.md`
- Upstream: P3-F accepted deepreview commit `1f00491b`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-review-ds.md`

## Verdict

**PASS with findings** — 计划动机成立、owner boundary 正确、slice 拆分合理。3 个 medium finding 需在进入 implementation gate 前处置或记录为显式 residual risk，无 blocking finding。

---

## Findings

### P3-G-PLAN-F01 — 中 — S2 CN/HK migration 的测试拆分策略未明确化

- **来源**: Review focus question 2; plan S2 测试描述
- **问题**: Plan S2 要求"Downloader adapters keep HTTP fetch/JSON decode/provider raw field normalization only"，将产品级过滤/推断移到 pipeline helper。CN/HK downloader 测试当前混合了 HTTP mock、raw field 解析、title blocking、fiscal inference 和 candidate 构造的断言。Plan 的 risks 章节提到"first add raw adapter tests, then move existing assertions to pipeline helper tests"，但 S2 的 Tests 节只描述了最终状态（"CNInfo raw adapter returns raw announcements without title block/fiscal inference"），未说明迁移过程中如何保证既有断言不丢失。

- **直接证据**:
  - `cninfo_downloader.py:873` `_is_title_blocked`、`:1030` `_infer_fiscal_year` 当前在 downloader 模块内
  - `hkexnews_downloader.py:996` `_infer_fiscal_year`、`:1050` `_infer_fiscal_period_from_text` 当前在 downloader 模块内
  - 既有测试对这些函数的断言可能嵌入在 HTTP mock + downloader 集成测试中

- **影响**: 若实现时简单删除 downloader 内函数并移动代码到 pipeline helper，而测试未对应拆分，可能导致：
  - raw HTTP adapter 缺少独立测试（依赖 pipeline 集成测试间接覆盖）
  - pipeline helper 测试复用了旧的 mock 策略（HTTP 层 mock 不适合纯 domain 测试）
  
- **建议处置**: 
  1. 在 plan 中明确：先为 pipeline helper 写独立单元测试（不依赖 HTTP mock），再迁移 downloader 测试为"只测 HTTP 到 raw DTO"。
  2. 在 completion signal 中增加一条：迁移后既有 downloader 测试覆盖的行为在新 pipeline helper 测试中有对应的断言。
  3. 如果 CN/HK downloader 测试文件当前过大，考虑在 S2 计划中允许拆分测试文件。

- **严重程度**: 中

### P3-G-PLAN-F02 — 中 — S4 XBRL total 校验规则的实现边界存在歧义

- **来源**: Review focus question 6; plan S4 描述
- **问题**: Plan S4 Design Decision 7 和 Tests 节之间存在一个小但可导致实现走偏的歧义：
  - Design Decision 7: "processor payload 缺少 `total`、`total` 非 int、或与 processor-owned facts count/contract不一致时抛明确错误" — 这要求校验 `total == len(facts)`（processor contract）
  - Tests 节: "Processor result `total != len(facts)` fails closed or is rejected by the validation helper" — 表述为 `total != len(facts)` 即失败
  - 但同时 Design Decision 7: "若 deduped 后需要单独数量，应新增非 contract 字段" — 这承认 dedup 后 count 可能不同于 processor `total`
  
  歧义点：Processor 返回 `total == len(facts)` 永远为 `True`（processor 始终 `total=len(facts)`，见 `sec_processor.py:726` / `bs_report_form_common.py:331`）。所以 `total != len(facts)` 这个校验在正常 processor 中永远通过——它只能捕捉 processor 的 bug（如忘记设置 total 或设置了错误值）。真正的差异发生在 dedup 之后：`len(deduped_facts) < total` 是预期行为（正常情况）。但 plan 用"重新计算 total 会掩盖 processor 违约"来证明 S4 的动机，却没有清楚区分"processor 违约"（total 字段错误）和"正常 dedup 导致的 count drift"。

- **直接证据**:
  - `sec_processor.py:726`: `"total": len(facts)` — processor contract 始终 true
  - `read_runtime_helpers.py:1413`: `normalized_payload["total"] = len(deduped_facts)` — 当前行为是覆盖 processor total
  - Plan S4: 同时提到"fail closed on total != len(facts)"和"expose derived deduped count"

- **影响**: 如果 implementer 把 "dedup 后 count < processor total" 理解为 `total != len(facts)` 的 violation，会误判正常 processor 结果为违约。如果 implementer 只做 `total == len(facts)` 校验而不做 deduped count 处理，LLM-facing `total` 仍会被覆盖（因为当前代码在行 1413 会覆盖）。

- **建议处置**:
  1. 明确区分两个层次：(a) processor contract 校验（`total` 存在且为 int，`total == len(facts_raw)` 在 `facts` 类型为 list 时），(b) 展示层 deduped count（不覆盖 processor `total`，可新增 `deduped_fact_count` 字段）
  2. 在 Tests 节中分开列出 processor 校验测试和 deduped count 测试
  3. 将 Design Decision 7 的 `total` 校验限制在 processor contract 层：缺字段/非 int/与 raw facts 数量不一致时 fail；不要将 dedup 后的 count 差异当触发条件

- **严重程度**: 中

### P3-G-PLAN-F03 — 中 — S1 "移除三套 form normalizer" 的完成信号可能不反映全部真实调用依赖

- **来源**: Review focus question 3; plan S1 描述
- **问题**: Plan S1 的 completion signal 是 "One SEC form truth remains; duplicate source-scan matches are classified as tests, deleted files, or deliberate call sites into the domain helper." 但 S1 source scan regex 是：
  ```
  rg -n "form_type_utils|def normalize_form\\(|_normalize_form_for_fiscal|normalize_form_type" dayu/fins tests/fins
  ```
  这个 regex 只能匹配函数定义和模块 import 文本，不能匹配**函数调用**。如果某个调用方如 `sec_download_filing_workflow.py` 或 `sec_6k_rules.py` 在行内使用 `normalize_form(some_str)` 而不是直接 import 模块名，regex 不会命中。此外 `normalize_form_type` 在 `read_runtime_helpers.py:494` 不是模块名而是函数名——如果 domain helper 使用不同的函数名，regex 同样漏判。

- **直接证据**:
  - Plan S1 source scan regex: `"form_type_utils|def normalize_form\\(|_normalize_form_for_fiscal|normalize_form_type"`
  - `_normalize_form_for_fiscal` 在 `sec_fiscal_fields.py:546` 是 `def _normalize_form_for_fiscal(...)` — 模块私有函数，调用方不会 import 模块名，只会调用函数
  - `normalize_form_type` 在 `read_runtime_helpers.py:494` 已存在——如果 S1 新增的 domain helper 不叫这个名字，regex 会产生假阴性

- **影响**: Completion signal 可能给出"已收敛"的假象，但实际残留的 form 处理逻辑未被发现。属于验证方法的设计缺陷，不是 plan 的 logical 错误。

- **建议处置**:
  1. 将 source scan regex 扩展为覆盖函数调用模式，例如增加 `rg -n "normalize_form\\(|_normalize_form_for_fiscal\\(|normalize_form_type\\("` 扫描 `dayu/fins`。
  2. 明确 completion signal 的分类要求：每个保留的 form 处理调用必须能追踪到统一 domain helper（不是旧的三套实现之一）。
  3. 或者，在完成信号中增加一条反向验证：确认旧三套实现所在模块的 import 在 `dayu/fins` 全部模块中归零。

- **严重程度**: 中

---

## Source Finding Adjudication 核实

逐项检查 plan 对 controller adjudication 中 P3-G 来源 findings 的处置：

| Source Finding | Plan Disposition | 核实 |
| --- | --- | --- |
| AgentCodex 11: XBRL `total` masking | current — S4 | ✅ 问题陈述正确，S4 覆盖 |
| AgentDS 7: SEC form normalization in 3 places | current — S1 | ✅ S1 覆盖，设计决策正确 |
| AgentDS 8: naked strings for `fiscal_period`, `form_type`, `quality` | current-partial — S1 | ✅ S1 覆盖 domain validation，不覆盖 storage schema expansion（non-goal 正确） |
| AgentMiMo BI-1: downloader-owned filtering/inference | current — S2 | ✅ S2 覆盖，owner boundary 正确 |
| AgentMiMo SS-10: rejection registry dict shape | current — S3 | ✅ S3 覆盖 |

**未发现遗漏或错判**。Plan 正确映射了所有 5 个 source finding 到对应 slice。

---

## Owner Boundary 评估

### SEC Form Type (S1)

| 层 | Owner | Plan 处置 |
| --- | --- | --- |
| Producer | SEC filing record, user upload | 保持现有 producer，不改变 |
| Validator | Domain SEC form parser | ✅ S1 新增 `filing_semantics.py` |
| Persistence | Source/rejected/processed meta | ✅ "Keep source meta JSON field names unchanged" |
| Projection | Processor selection, read filtering | ✅ 更新 import 到 domain truth |

**边界正确**：form 语义从三套分散 normalizer 收口到 domain parser，下游只消费 typed truth。

### Fiscal Period (S1)

| 层 | Owner | Plan 处置 |
| --- | --- | --- |
| Producer | Upload args, SEC/CN/HK extraction | 保持 |
| Validator | Shared fiscal period parser (`FY/H1/Q1-Q4`) | ✅ S1 domain module |
| Persistence | Source/processed meta | ✅ |
| Projection | List/search/read filters | ✅ |

**边界正确**：CN 现有 `CnFiscalPeriod` 应迁移为消费共享 domain 类型（Design Decision 3）。

### Financial-Report Filtering (S2)

| 层 | Owner | Plan 处置 |
| --- | --- | --- |
| Producer (raw) | HTTP downloader adapter | ✅ "keep HTTP fetch/JSON decode only" |
| Validator/Classifier | Pipeline/domain helper | ✅ 移到 `cn_report_selection.py` |
| Persistence | `CnReportCandidate`, source meta | ✅ |
| Projection | Download stream result | ✅ |

**关键约束**：Plan 明确 "Do not turn HTTP adapters into pipeline wrappers" — S2 只移动 owner 边界，不新增抽象层。

### Rejection Registry (S3)

| 层 | Owner | Plan 处置 |
| --- | --- | --- |
| Producer | SEC pipeline rejection decision | 保持 |
| Validator | Typed registry entry constructor | ✅ S3 新增 typed entry |
| Persistence | Maintenance repository JSON | ✅ 保留 JSON 格式，通过 typed entry `to_dict()` |
| Projection | `_is_rejected`, diagnostics, wrappers | ✅ 消费 typed entry |

**边界正确**：typed entry 在 domain 层定义，repository 负责 load/save，pipeline 消费 typed values。

### XBRL Facts Result (S4)

| 层 | Owner | Plan 处置 |
| --- | --- | --- |
| Producer | Processor `query_xbrl_facts` | 保持 |
| Validator | Processor result contract helper | ✅ S4 validation helper |
| Projection | Read runtime normalization + dedup | ✅ 不覆盖 `total`，可选 derived count |
| LLM-facing | `query_xbrl_facts` read tool result | ✅ |

**边界正确**：`total` ownership 从 read runtime 回到 processor contract。

---

## Slice 可行性检查

### S1 — SEC Form / Domain Typed Values

**Scope 评估**: 看似"广"（domain parser + fiscal period + document quality + 三套 normalizer 收敛），实际执行路径清晰：
- 新增一个 domain 模块（`filing_semantics.py`）
- 替换 3 处 form 处理调用点
- 为 `DocumentSummary.from_dict` / `ProcessedManifestItem` 的 decode 增加 quality/fiscal_period 校验

**风险**: S1 的 "Validate domain model decode paths" 可能触发大量的 `from_dict` 调用方更新，因为当前很多调用方直接构造 `Optional[str]` 而不走 typed parser。

**Plan 处理**: Design Decision 1 明确新模块 "只依赖标准库和 typing，不得 import pipeline/storage/processor/tool" — 这避免了 domain 模块穿透依赖。Non-goal 明确 "不为旧 import path 增加兼容 re-export"。

**判定**: 可行。建议在实现时优先从 pipeline 入口校验开始（producer 边界），再逐步收紧 decode 路径，避免一口气改造所有 `from_dict` 调用方。

### S2 — CN/HK Report Selection

**Scope 评估**: CN/HK downloader 的 `list_report_candidates` 包含多步骤逻辑：HTTP fetch → 年报过滤 → title block → language filter → fiscal inference → per-period grouping → `CnReportCandidate` 构造。S2 需要把这些步骤的 owner 边界画准。

**风险**: CNInfo 和 HKEXNews 的 `list_report_candidates` 内部逻辑不完全对称（CN 有 `_is_title_blocked`，HK 有 `_looks_like_english_report_text`），统一迁移到 pipeline helper 时需要考虑两层逻辑的差异。

**Plan 处理**: S2 明确了 "Downloader adapters keep HTTP fetch/JSON decode/provider raw field normalization only"，pipeline helper 做 product-level 分类。允许为 raw announcements 引入 DTO。

**判定**: 可行。S2 是 P3-G 中最复杂的 slice，建议按 CNInfo 和 HKEXNews 分两步实现，每步独立验证。

### S3 — Typed Rejection Registry

**Scope 评估**: 涉及 repository protocol 变更 → 存储实现变更 → pipeline consumer 变更。链路清晰，改动集中。

**风险**: Repository protocol 的 `load/save_download_rejection_registry` 变更可能影响测试中的 mock/repository builder。

**Plan 处理**: Design Decision 6 明确了 typed entry 的结构和 `to_dict()` 序列化方式。Plan 要求 "fail closed on malformed entries"。

**判定**: 可行。这是最 straightforward 的 slice。

### S4 — XBRL Result Contract

**Scope 评估**: 只改 read_runtime_helpers + processor validation。改动最小。

**风险**: 见 P3-G-PLAN-F02。

**判定**: 可行。但需要在实现前解决 F02 的歧义。

---

## Over-Coupling / Architecture Risks

| 风险 | 评估 |
| --- | --- |
| Domain 模块 import pipeline/storage | Plan Design Decision 1 明确禁止 — ✅ |
| S2 pipeline helper 变成新的 god class | Plan 使用窄模块 `cn_report_selection.py` — ✅ 可进一步拆分为 `cn_report_selection.py` + `hk_report_selection.py`，但当前 plan scope 可行 |
| S3 typed entry 耦合到 repository 实现 | Plan 明确 typed entry 在 domain 层，repository 只做 load/save — ✅ |
| S4 导致 read runtime 承担 processor 校验 | Plan 用独立的 validation helper，read runtime 调用它 — ✅ 但建议 helper 放在 processor 层（不是 read_runtime_helpers），确保 processor contract owner 能独立演化 |

**建议**: S4 的 typed validation helper 应该放在 `dayu/fins/processors/` 而不是 `dayu/fins/tools/read_runtime_helpers.py`，因为它是 processor contract 校验器（processor owner），不是 read runtime 投影逻辑。Plan 允许的文件列表包含了 `financial_base.py` 和 `sec_processor.py`，但没有强制新 helper 的放置位置。建议实现时考虑放在 processor 层。

---

## Non-Goals / Scope Boundaries

| Non-goal | 核实 |
| --- | --- |
| 不做旧 schema 兼容读取 | ✅ 与项目编码约束一致 |
| 不把 SEC/CN/HK 改写成 mega classifier | ✅ S2 保留现有算法行为，只移动 owner |
| 不修改 P3-F 语义 | ✅ P3-F 文件不在 allowed files 中 |
| 不更改 Host/Engine 架构 | ✅ 所有改动在 `dayu/fins/` |
| 不为旧 import path 增加兼容 re-export | ✅ 与项目编码约束 "禁止兼容性 re-export" 一致 |
| 不把 read runtime 变成 source meta 修复器 | ✅ S4 只校验 processor contract，不修复 source meta |

---

## Test / Pyright / Source Scan Coverage

**Pyright**: Plan 在每个 slice 的 validation 中正确包含了 `pyright dayu/ tests/ utils/`。

**Source scans**: 每个 slice 都有针对性的 source scan（form_type_utils、fiscal inference、dict shape、total recompute）。见 P3-G-PLAN-F03 关于 S1 source scan regex 的发现。

**Tests**: 
- S1: SEC form parser 覆盖正常/异常输入 — ✅
- S2: CN/HK raw adapter + pipeline helper 测试 — ⚠️ 见 P3-G-PLAN-F01
- S3: Round-trip + malformed entry rejection — ✅
- S4: Missing total / invalid total / valid result — ✅ 但需澄清 `total != len(facts)` 的语义（F02）

**README**: Plan 正确识别了 `dayu/fins/README.md` 更新触发条件。`tests/README.md` 只在测试组织变更时更新 — 正确。

---

## Residual Risks

1. **S1 import 扩散**: 更新所有 form normalizer 调用方可能导致超过预期的文件改动。Plan 的 mitigation（mechanical import update + source scan）合理。
2. **S2 CN/HK 测试迁移** (P3-G-PLAN-F01): 详见 finding。
3. **S4 total 语义歧义** (P3-G-PLAN-F02): 详见 finding。
4. **S1 source scan 完整性** (P3-G-PLAN-F03): 详见 finding。
5. **CN `CnFiscalPeriod` 迁移**: Plan Design Decision 3 要求 CN/HK 迁移到共享 domain fiscal period 类型。这是正确的 ownership 方向，但 CN 代码中对 `CnFiscalPeriod` 的引用可能较多——需要 S1 实现时评估影响面。
6. **P3-G 完成后不关闭 umbrella**: Plan 明确说明 "P3-G 完成后不关闭 umbrella WU-SEMANTIC-OWNERSHIP-01"。这是正确的——P3-H/P3-I/P3-J/P3-K 和 full-repo deepreview 仍在队列中。

## Open Questions

1. S4 validation helper 应放在 `dayu/fins/processors/` 还是 `dayu/fins/tools/`？reviewer 建议放在 processor 层以 align processor contract ownership。
2. S2 是否需要为 CNInfo 和 HKEXNews 各建一个独立的 report_selection 模块（`cn_report_selection.py` + `hk_report_selection.py`），还是合并为一个？当前 plan 未强制，建议实现时评估两个 downloader 的 candidate 逻辑差异程度。
