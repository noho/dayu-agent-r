# WU-SEMANTIC-OWNERSHIP-01 / R07 Plan Review — AgentMiMo

## 1. Review Target 与 Scope

- **review target**：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`
- **immutable SHA-256**：`ae8d74f8a9a7fd677face4211cb7402bdc5e56eb6c80bfe8cb1791a4e46a7bc7`
- **controller entry validation**：`docs/reviews/wu-semantic-ownership-01-r07-plan-entry-controller-validation.md`（PASS / READY_FOR_DUAL_PLAN_REVIEW）
- **umbrella**：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`
- **design truth**：`docs/fins/design.md`
- **controller discussion**：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 6.3 / 6.7
- **R06 completion**：`docs/reviews/wu-semantic-ownership-01-r06-completion-controller-validation.md`
- **review timestamp**：`20260716-114240`

review scope 覆盖 plan 全文 §0—§13，重点挑战 motivation、semantic owner、scope/allowlist、三 slice 原子性与顺序、fresh schema、failure/concurrency/resource state machine、tests/coverage/scans/smoke、security retained/modified、inherited baseline、residual owners 和 phaseflow gate 顺序。

## 2. Assumptions Tested

| # | assumption | evidence source | verdict |
|---|---|---|---|
| A1 | opaque identity 与路径组件不是同一语义 | `_normalize_ticker/_normalize_document_id` 115 hits across 7 storage files（`rg -c` 复现） | confirmed |
| A2 | `_build_source_revision` 是 consumer-selected field hash | `_fs_source_document_core.py:158-213`：选择 `_SOURCE_REVISION_REQUIRED_TEXT_FIELDS`、`_SOURCE_REVISION_OPTIONAL_TEXT_FIELDS`、`ingest_complete`、`is_deleted` 与排序后 file identity/content 字段，canonical JSON 后 SHA-256 | confirmed |
| A3 | `read_runtime.py` 有两套 revision-before/after 双读 | `read_runtime.py:2198/2230`（meta cache）与 `:2558/2594`（processor）；另 `:2503` 是第三种 diagnosis 路径 | confirmed |
| A4 | `_resolve_source_kind` 做 filing-first probing | `read_runtime.py:2682-2717`：先试 `SourceKind.FILING`，`FileNotFoundError` 后试 `SourceKind.MATERIAL` | confirmed |
| A5 | `_FinsReadProcessTarget.__call__` 无 `finally` close | `fins_tools.py:245-286`：创建 `DefaultFinsRuntime`、取 `read_runtime`、执行业务，成功/失败/异常路径均无 `runtime.close()` | confirmed |
| A6 | cache `put` 静默丢弃替换值 | `cache.py:122-144`：`put` 在 key 存在时直接覆盖，`while len > max` 时 `popitem(last=False)` 不返回被淘汰值 | confirmed |
| A7 | cache `evict` 只返回 bool | `cache.py:146-163`：返回 `True/False`，不返回被淘汰值 | confirmed |
| A8 | `cache.py` `clear` 不返回值 | `cache.py:165-179`：`self._store.clear()`，无返回 | confirmed |
| A9 | README 仍承诺 field-hash revision | `dayu/fins/README.md:99`："revision 由会影响 processor 输入的 canonical source meta 与文件身份/内容字段确定性计算" | confirmed |
| A10 | README 仍承诺 document id 单路径组件 | `dayu/fins/README.md:111`："document id 的路径组件边界" | confirmed |
| A11 | composition roots 为四个 | `service_runtime.py:350`、`cn_pipeline.py:378`、`sec_pipeline.py:512`、`sec_6k_primary_document_repair.py:260` | confirmed |
| A12 | `.materialize()` 是 8 production files / 9 calls | plan §3.4 inventory 与 `rg -n` 复现：`bs_processor.py:135`、`docling_processor.py:148,1745`、`markdown_processor.py:112`、`sec_processor.py:157`、`bs_report_form_common.py:129`、`bs_six_k_processor.py:276`、`source_text.py:88`、`sec_fiscal_fields.py:349` | confirmed |

## 3. Findings

### R07-PR-F01 — 未修复 — 低 — coverage 命令使用 `--branch` 检查 `percent_covered`，超出 AGENTS.md 纯行覆盖率口径

- **位置**：§8.1 每 slice 强制验证矩阵，coverage 命令
- **问题类型**：最佳实践偏离
- **当前写法**：plan 使用 `coverage run --branch -m pytest` 并检查 coverage JSON `percent_covered >= 80`。`percent_covered` 是 `(covered_branches + covered_lines) / (total_branches + total_lines)` 的综合指标，不是 AGENTS.md §测试与验证 "单文件测试覆盖率" 的纯行覆盖率口径。
- **反例/失败场景**：某文件行覆盖率 82%（达标），但 branch 覆盖率 60%，综合 `percent_covered` 约 75%（不达标）。implementation agent 会被迫为该文件补充 branch 覆盖测试，而这些测试可能只覆盖防御性分支、不增加业务语义覆盖。
- **为什么有问题**：R06 completion controller validation（§4）明确说 "coverage JSON 的综合 `percent_covered` 包含 branch 分母，不是 AGENTS.md 的单文件 line coverage 口径；Controller 明确按 line coverage 复算"。R07 plan 使用 `--branch` + `percent_covered` 与 R06 验证口径不一致。
- **直接证据**：§8.1 命令 `coverage run --branch -m pytest` 与 Python 检查 `p["files"][f]["summary"]["percent_covered"] < 80`；R06 completion §4。
- **影响**：implementation agent 可能被更严格的指标阻塞，而 AGENTS.md 只要求 line coverage ≥80%。
- **建议改法和验证点**：保持 `--branch` 收集数据（对质量有益），但检查时使用 `p["files"][f]["summary"]["covered_lines"] / p["files"][f]["summary"]["num_statements"] >= 0.8`，或使用 `coverage report --include='...' --fail-under=80`（默认是 line coverage）。验证点：确认与 R06 验证口径一致。
- **修复风险**：低
- **严重程度**：低

### R07-PR-F02 — 未修复 — 低 — S3 顺带删除 base unused imports 的范围未明确列出

- **位置**：§7.3 R07-S3 exact production allowlist 末尾说明
- **问题类型**：不可直接实施
- **当前写法**：`read_runtime.py` 本 slice 既然被修改，顺带删除 base 两个 unused imports，使 changed-file scoped Ruff 清零。
- **反例/失败场景**：implementation agent 不确定哪两个 import 需要删除，可能删错或遗漏，导致 scoped Ruff 仍报 F401。
- **为什么有问题**：plan 精确列出了所有其它变更，但这两个 import 只说"两个"而未给具体符号名。
- **直接证据**：§1 baseline "仅 `dayu/fins/tools/read_runtime.py:62` unused `QueryDiagnosis` 与 `:64` unused `SEARCH_MODE_AUTO`，共 `2 F401`"。
- **影响**：implementation agent 需额外确认，但风险低（baseline 已给出精确位置）。
- **建议改法和验证点**：在 S3 §7.3 明确写 "删除 `read_runtime.py:62` 的 `QueryDiagnosis` 与 `:64` 的 `SEARCH_MODE_AUTO` 两个 unused import"。验证点：S3 scoped Ruff 为 0。
- **修复风险**：低
- **严重程度**：低

### R07-PR-F03 — 未修复 — 中 — `read_source_snapshot` 的 `source_kind` 缺省时 storage 内部 filing/material 检查可能引入不必要公共行为

- **位置**：§5.3 "source kind缺省时由storage在同一publication guard内检查filing/material映射：0个为`FileNotFoundError`，1个返回其typed kind，2个为storage invariant/ambiguity failure"
- **问题类型**：过度设计
- **当前写法**：当 `source_kind=None` 时，storage 在内部检查 filing/material 映射，0 个为 `FileNotFoundError`，1 个返回其 kind，2 个为 ambiguity failure。这把 source kind 解析逻辑从 read runtime 移到了 storage snapshot owner。
- **反例/失败场景**：如果同一 document_id 在 filing 和 material 中都存在（当前代码允许这种可能性），storage 会抛出 ambiguity failure，而当前 `_resolve_source_kind` 的 filing-first 策略会静默选择 filing。这个行为变化可能影响现有消费者。
- **为什么有问题**：controller discussion Topic 6.3 说 "storage-owned snapshot/version returned with the source"，但没有明确要求 storage 内部做 source kind 解析。当前 `_resolve_source_kind` 在 read runtime 中，plan 把它移到 storage 内部，增加了 storage 的公共职责。如果未来 source kind 解析策略需要变化（例如优先级、用户偏好），storage 会成为修改点。
- **直接证据**：§5.3 "source kind缺省时由storage在同一publication guard内检查filing/material映射"；当前 `read_runtime.py:2682-2717` 的 filing-first probing。
- **影响**：storage 公共 API 增加了 source kind 解析行为，可能不适合所有消费者（例如 list_documents 不需要 kind 解析）。
- **建议改法和验证点**：保持 `source_kind` 为必填参数（不允许 `None`），让 read runtime 继续负责 kind 解析但改为在同一 snapshot 内检查而非独立 repository read。或者，如果 storage 内部 kind 解析是正确设计，明确说明为什么这比 runtime 解析更好。验证点：`read_source_snapshot` 的 protocol 签名中 `source_kind` 是否有默认值 `None`。
- **修复风险**：中
- **严重程度**：中

### R07-PR-F04 — accepted candidate — 低 — `SourceDocumentRevision` 收窄为 opaque equality 但 plan 未明确是否保留 `digest` 字段名

- **位置**：§5.2.1 "SourceDocumentRevision 只做opaque equality，不校验/承诺SHA grammar"
- **问题类型**：契约缺失
- **当前写法**：plan 说 `SourceDocumentRevision` 收窄为 opaque equality，但未明确是否保留 `digest` 字段名。当前 `SourceDocumentRevision(digest=f"sha256:{digest}")` 的 `digest` 字段名暗示 SHA-256 语义。
- **反例/失败场景**：如果保留 `digest` 字段名但不再承诺 SHA-256 grammar，字段名会产生误导。如果改为更通用的字段名（如 `token`），需要修改所有引用点。
- **为什么有问题**：§2 说 "Python 类型可保留 typed equality，但字段名、token 生成算法、token grammar、具体 retry budget、私有 resource/borrow/context-manager 类名都不是业务、tool、README 或 LLM contract"。plan 已明确字段名不属于 contract，但未说明是否修改。
- **直接证据**：`document_models.py:289` `class SourceDocumentRevision` 有 `digest: str` 字段；§5.2.1。
- **影响**：implementation agent 需要决定是否重命名字段。如果不重命名，`digest` 字段名暗示 SHA-256 但实际可能是任意 opaque token。
- **建议改法和验证点**：在 plan 中明确：(a) 保留 `digest` 字段名但文档说明它是 opaque token 不承诺算法，或 (b) 重命名为 `token`。验证点：`SourceDocumentRevision` 的字段名与新 revision 生成算法一致。
- **修复风险**：低
- **严重程度**：低

## 4. Open Questions

无 blocking questions。以下为非阻塞观察：

1. **snapshot retry budget 测试边界**：plan 说 "内部attempt budget必须有界且大于1" 且 "测试不得断言调用次数或magic数字"。implementation agent 需要在测试中设置 barrier 以协调 A/B commits，但不能 assert attempt count。这需要测试设计上的技巧，但不是 plan 的问题。

2. **`_fs_source_snapshot.py` 是新私有模块**：plan 新增 `dayu/fins/storage/_fs_source_snapshot.py` 作为 snapshot resource owner。该模块的内部设计（temp directory lifecycle、fd management、publication guard coordination）属于 implementation 细节，plan 正确地不冻结这些细节。

## 5. Residual Risks

| residual | severity | tracking destination |
|---|---|---|
| snapshot fd-copy 在极端高并发 publication 下的性能 | 低 | R07 implementation smoke；不做 production stress |
| `SourceDocumentRevision.digest` 字段名是否需要重命名 | 低 | R07-S2 implementation decision |
| `read_source_snapshot` 的 `source_kind` 参数默认值设计 | 中 | R07-S2 protocol design decision |
| 旧 `get_source_revision` 在 S2 checkpoint 过渡期的 type-correctness | 低 | S2 handoff contract 已明确 |

## 6. Duplicate / Observation / Deferred Owner

| ID | status | 说明 |
|---|---|---|
| R07-PR-F01 | observation | coverage metric 超出 AGENTS.md 口径但更严格 |
| R07-PR-F02 | observation | unused import 范围未明确但 baseline 已给精确位置 |
| R07-PR-F03 | accepted candidate | source_kind 缺省行为可能过度设计 |
| R07-PR-F04 | accepted candidate | revision 字段名是否需要重命名 |

## 7. 审查范围与反例

### 审查范围

- plan 全文 §0—§13 逐节阅读
- `docs/fins/design.md` §1—§10 完整阅读
- controller discussion Topic 6.3 / 6.7 完整阅读
- umbrella plan §0—§7.5 相关节阅读
- R06 completion validation 完整阅读
- controller entry validation 完整阅读
- AGENTS.md 全文阅读
- tests/README.md 全文阅读
- 当前代码直接证据：`_fs_source_document_core.py:158-213`（field hash）、`read_runtime.py:2198/2230/2503/2558/2594/2682-2717`（double-read/probing）、`cache.py:122-179`（lifecycle）、`fins_tools.py:245-286`（process target cleanup）、`dayu/fins/README.md:99/111/488/743`（README claims）

### 反例

- coverage `--branch` + `percent_covered` 可能导致文件因 branch 覆盖率不足而失败，即使 line coverage 达标（F01）
- `source_kind=None` 的 ambiguity failure 行为变化可能影响现有 filing-first 消费者（F03）
- `digest` 字段名暗示 SHA-256 但新 revision 可能是任意 opaque token（F04）

### 残余

- snapshot 内部实现细节（temp directory、fd management、publication guard coordination）不在 plan 审查范围，属于 implementation 细节
- R08 financial/XBRL producer contract 变更不在 R07 范围
- Issue 142/151/175/177/178 不在 R07 范围

## 8. Verdict

**PASS**。

R07 plan 是 code-generation-ready 的独立 remediation plan。motivation 由直接代码证据支持；semantic owner 正确归 storage；scope 未超出 Topic 6.3/6.7 边界；三 slice 原子性与顺序合理（S1 opaque key → S2 persisted revision + snapshot → S3 read/cache/citation migration）；fresh schema 无兼容逻辑；failure/concurrency/resource state machine 覆盖 A/B publication、transient recovery、sustained churn、cache lifecycle、process target cleanup；tests/coverage/scans/smoke 矩阵完整；security retained/modified matrix 正确；inherited baseline 六字段完整；residual owners 正确 defer 到 R08-R12。

四个 findings 均为低/中严重程度，无 blocking question。F01（coverage metric）是观察项，plan 可选择修正或保持更严格标准；F02（unused import 范围）baseline 已给精确位置；F03（source_kind 缺省行为）是 accepted candidate，需要 implementation agent 在 S2 protocol design 时裁决；F04（revision 字段名）是 accepted candidate，需要 S2 实现时决定。

**finding 总数**：4（0 blocking / 2 accepted candidate / 2 observation）
**blocking questions**：0
**artifact path**：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-mimo.md`
