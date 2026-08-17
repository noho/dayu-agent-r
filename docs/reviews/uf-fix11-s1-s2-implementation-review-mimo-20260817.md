# UF-FIX11 S1+S2 Implementation Review — MiMo

## Review metadata

- Work unit: `UF-FIX11 company-metadata-ignored-change-warning`
- Slice: `S1+S2 — atomic authoritative company identity commit and filing warning`
- Gate: `implementation review`
- Reviewer: MiMo
- Date: 2026-08-17
- Branch: `codex/upload-filing-oracle`
- Implementation artifact: `docs/gateflow/uf-fix11-s1-s2-implementation-20260817.md`
- Reviewed scope: all dirty production (12 files) and test (11 files) diffs plus 1 new file
- Decision: **PASS — 0 blocking, 2 non-blocking observations**

## Review methodology

1. 逐行读取所有 22 个 dirty 文件的完整 git diff。
2. 对照 plan §1-§16 的 typed contract、owner boundary、state machine、invariants 与 stop conditions 逐项验证。
3. 以 adversarial 视角检查 §12.5 static boundary checks 覆盖的所有维度。
4. 对关键路径（SKIP+preserve capability transfer、failure/cancel/rollback no-warning、SEC/CN terminal producer、parser closed codec、四个 SourceKind callsite、commit_batch 全量收敛）做直接代码证据追踪。

---

## Finding 001: `_normalize_optional_requested_company_name` 与 `_require_upload_company_name` 的校验文案不一致

- **严重度**: 非阻塞
- **类型**: 一致性/可维护性
- **文件:行号**: `dayu/fins/domain/company_meta_contract.py:248` vs `dayu/fins/pipelines/upload_company_meta.py:228`
- **证据**: domain 层 `_normalize_optional_requested_company_name` 在空白输入时抛出 `ValueError("requested_company_name 必须为非空字符串")`；pipeline 层 `_require_upload_company_name` 抛出 `ValueError("upload 公司名称必须为非空字符串")`。两者都是非空校验但文案不同。
- **影响**: 不影响正确性（domain 校验是 pipeline 校验的下游备份）。但两处对同一语义（"名称为空"）使用不同错误消息，增加下游错误匹配的认知负担。
- **建议修复**: 统一为同一常量或至少同一表述模式。不是 blocker，可在 S3 或后续清理。
- **Residual risk**: `assigned to later work unit`。

## Finding 002: `_optional_upload_company_name` 对空白输入返回 `None`，domain 层对同一输入抛异常——路径差异被消除但语义边界有微隙

- **严重度**: 非阻塞
- **类型**: 边界防御
- **文件:行号**: `dayu/fins/pipelines/upload_company_meta.py:231-248` vs `dayu/fins/domain/company_meta_contract.py:240-250`
- **证据**: `_optional_upload_company_name(" 　 ")` 返回 `None`（"无名称提交"语义），而 `_normalize_optional_requested_company_name(" 　 ")` 抛出 `ValueError`（"空白非法"语义）。pipeline 层在 fresh keep 路径中，空白输入通过 `_optional_upload_company_name` 返回 `None`，不进入 `build_company_meta_commit_intent`，因此 domain 校验不会被触发。在 fresh stage 路径中，`_optional_upload_company_name` 也先执行，空白输入同样返回 `None`，不进入 intent 构造。
- **影响**: 实际上两条路径都不会让空白字符串到达 domain 校验。`_optional_upload_company_name` 作为 pipeline 边界守卫已拦截了空白输入。domain 层的 `_normalize_optional_requested_company_name` 是 intent 构造的二次防御，两者分工正确。但 "空白 = None = 无提交" 的决策在 pipeline 层隐含做出，未在 plan 中明确声明。
- **建议**: 不需要修复。两条防线不冲突，pipeline 层的"空白视为无提交"语义是合理的（用户未实质输入名称）。只需确认测试覆盖：`test_fresh_upload_equivalent_or_missing_name_keeps_metadata` 参数化了 `company_name=None` 但没有覆盖空白字符串。测试覆盖可考虑补充但不阻塞当前 slice。
- **Residual risk**: `assigned to later work unit`（测试覆盖补充）。

---

## 逐维度审查结论

### 1. 语义 owner 是否真在 final-lock storage outcome

**PASS**。直接证据链：

- `dayu/fins/storage/_fs_storage_infra.py:762-776`：`_prepare_company_identity_commit` 在 publication guard 内调用 `merge_company_meta_for_commit`，从 `current_published`（authoritative re-read）和 `intent` 生成 `CompanyMetaCommitOutcome`。warning predicate 使用 `_build_company_meta_commit_outcome` 内的 `company_names_are_equivalent`，该函数只做 NFKC/空白/casefold 比较，不持久化。
- `merge_company_meta_for_commit` 的返回值从 `CompanyMeta` 改为 `CompanyMetaCommitOutcome`（`company_meta_contract.py:191`）。
- `_fs_storage_infra.py:611`：`commit_batch` 仅在完整成功（无 commit error、cleanup error 不改变 committed phase）后返回 `company_meta_outcome`；任何异常路径不返回 outcome。
- `_warnings_from_commit_outcome`（`filing_upload_publication.py:94-116`）使用 `type(outcome) is not CompanyMetaCommitOutcome` 精确类型检查。
- 无任何消费者在 publication lock 外重算 warning。

### 2. 是否有 early/preflight snapshot 泄漏

**PASS**。直接证据：

- SKIP 路径（`filing_upload_publication.py:770-799`）使用 `fresh_request.company_meta_decision`（post-revalidation view），不是 initial request 或 preflight snapshot。
- `FilingUploadPublicationOutcome.__post_init__`（`filing_upload_publication.py:174-184`）强制 `self.warnings == _warnings_from_commit_outcome(self.result.company_meta_commit_outcome)`。
- cancelled 路径（`filing_upload_publication.py:745-757`）使用 `warnings=()`，`result.company_meta_commit_outcome` 为 `None`，invariant 通过。
- SEC/CN workflow 的 early cancelled/delete 分支显式 `completed_warnings = ()`（`sec_upload_workflow.py:238,262`、`cn_pipeline.py:869,893`）。

### 3. success/skip/failure/cancel/kill/rollback warning invariant

**PASS**。完整覆盖矩阵：

| 终态/路径 | warnings 来源 | 证据 |
| --- | --- | --- |
| PUBLISH success | `_warnings_from_commit_outcome(result.company_meta_commit_outcome)` | `filing_upload_publication.py:838-844` |
| SKIP + keep | `warnings=()`（无 outcome） | `filing_upload_publication.py:777-780` |
| SKIP + preserve | `_warnings_from_commit_outcome(company_meta_commit_outcome)` | `filing_upload_publication.py:795-799` |
| CANCELLED | `warnings=()`（无 outcome） | `filing_upload_publication.py:751-757` |
| CONFLICT/FAIL | `_raise_failure_after_rollback`（不返回 outcome） | `filing_upload_publication.py:800-808` |
| SEC failure event | `warnings=[]` | `sec_upload_workflow.py:409` |
| CN failure event | `warnings=[]` | `cn_pipeline.py:1875` |
| SEC early terminal | `completed_warnings = ()` | `sec_upload_workflow.py:238,262` |
| CN early terminal | `completed_warnings = ()` | `cn_pipeline.py:869,893` |
| Pipeline parser | ok/skipped 允许；failed/cancelled/deleted 拒绝 | `ingestion_runtime.py:1737-1741` |

### 4. metadata-only skip 的 capability transfer/atomic rollback

**PASS**。关键顺序在 `filing_upload_publication.py:781-799`：

```python
stage_upload_company_meta_decision(...)  # L781-785: stage intent
batch_terminal_started = True             # L787: capability 转交
company_meta_commit_outcome = _require_skip_company_meta_outcome(
    batching_repository.commit_batch(batch)  # L788-790: commit
)
```

- `batch_terminal_started = True` 严格早于 `commit_batch`。
- outer `finally`（L845-851）在 `batch_terminal_started is True` 时不 rollback。
- 测试 `test_metadata_only_skip_commit_failure_never_rolls_back_consumed_capability`：commit 消费 capability 后抛 OSError，断言 `rollback_tokens == []`。
- 测试 `test_metadata_only_skip_stage_failure_rolls_back_once_before_capability_transfer`：stage 失败在 capability 转交前，断言 `rollback_tokens == begin_tokens`。
- SKIP 路径不调用 `publish_prepared_upload`、`commit_prepared_upload_batch` 或 stage 任何 filing/source asset（`source.stage_tokens == []` 由多测试断言）。

### 5. fresh different name 和 equivalent/missing name

**PASS**。直接证据：

- `upload_company_meta.py:92-107`：fresh existing meta + identity equal 时，检查 `name_change_requested`。不同名称 → `stage/preserve_published` intent with `requested_company_name`；等价/缺失名称 + no new alias → `keep`。
- `company_names_are_equivalent`（`company_meta_contract.py:168-185`）：NFKC + 空白折叠 + casefold。
- 测试 `test_company_name_equivalence_normalizes_only_presentation_forms`：Unicode 全角/半角、NBSP、ß→SS。
- 测试 `test_company_name_equivalence_rejects_semantic_guessing`：标点、后缀、翻译不等价。
- 测试 `test_fresh_upload_equivalent_or_missing_name_keeps_metadata`：None 与 `ＤＥＬＴＡ ＩＮＣ.` → keep。
- 测试 `test_fresh_upload_different_name_without_alias_preserves_requested_intent`：不同名称 → stage/preserve，`requested_company_name == "Delta Holdings"`。

### 6. alias merge/invalid/collision/concurrent winner

**PASS**。直接证据：

- `_canonical_skip_requirements_are_met`（`filing_upload_publication.py:444-455`）允许 `keep/no intent` 或 `stage/preserve_published intent`。
- 测试 `test_upload_filing_identical_skip_atomically_commits_new_alias_only`：alias-only skip，`final_meta.ticker_identity.accepted_aliases == ("APPL",)`。
- 测试 `test_skip_alias_collision_after_capability_transfer_is_typed_and_atomic`：barrier 控制，MSFT 先占 SHARED alias → AAPL skip collision → typed failure + `warnings == []`。
- 测试 `test_concurrent_auto_rejects_nonidentical_candidate_but_commits_valid_alias_intent`：company mismatch → skipped，`frozenset(accepted_aliases) == {"MSFT", "GOOG"}`。

### 7. CompanyMeta bytes/updated_at/source tree

**PASS**。直接证据：

- `_company_meta_from_published`（identity 不变时保留原 `updated_at`）：`company_meta_contract.py` 中 `preserve_published` 调用 `_company_meta_from_published(current_published, final_identity, committed_at)`，但该 helper 在 identity unchanged 时保持原非身份字段。
- SEC blocker 测试 `test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision`（`sec_pipeline_upload_filing_stream.py:1752-1799`）：
  - `before_company_meta_bytes == after_company_meta_bytes`（逐字节 JSON 相同）
  - `before_company_meta.updated_at == after_company_meta.updated_at`
  - `before_source_state == after_source_state`
  - `published_tree_sha256` 不变
- CN blocker 测试同结构（`cn_pipeline.py:1604-1639`）。
- alias-only skip 测试中 `before_source_tree == after_source_tree`（排除 `meta.json` 后 source tree 不变）。

### 8. SEC/CN 全 terminal producer

**PASS**。直接证据：

- SEC `_build_sec_filing_failure_event`（`sec_upload_workflow.py:364-409`）：`warnings=[]`。
- CN `_build_cn_filing_failure_event`（`cn_pipeline.py:1829-1875`）：`warnings=[]`。
- SEC 正常 ok/skipped：`warnings=company_metadata_warnings_to_json(completed_warnings)`（`sec_upload_workflow.py:303`）。
- CN 正常 ok/skipped：同模式（`cn_pipeline.py:934`）。
- SEC early cancelled/delete：`completed_warnings = ()`（`sec_upload_workflow.py:238,262`）。
- CN early cancelled/delete：`completed_warnings = ()`（`cn_pipeline.py:869,893`）。
- 测试 `test_sec_filing_failure_event_roundtrips_typed_reason_with_empty_warnings`：从真实 SEC workflow 触发 failure，断言 `raw warnings == []`，parser roundtrip `parsed.warnings == ()`，failure reason code/kind/message preserved。
- 测试 `test_cn_filing_failure_event_roundtrips_typed_reason_with_empty_warnings`：同结构。
- 多个已有测试补充断言 `result["warnings"] == []`（alias conflict、corrupt primary、fresh read failure、cancel、delete 等路径）。

### 9. closed codec 和 filing/material parser

**PASS**。直接证据：

- `company_metadata_warning_from_json`（`company_metadata_warning.py:88-114`）：closed shape（`set(value) != {"kind", "message"}` → fail）；kind enum check；message 规范常量 check。
- `company_metadata_warnings_from_json`（`company_metadata_warning.py:117-137`）：非数组 → fail；`len > 1` → fail；kind 重复 → fail。
- `from_pipeline_json`（`ingestion_runtime.py:1767-1774`）：
  - filing + missing warnings → `ValueError("filing terminal result 必须显式包含 warnings")`
  - material + missing warnings → `warnings = ()`
  - filing/material + `warnings: null` → `company_metadata_warnings_from_json(None)` → `ValueError("warnings 必须是 JSON array")`
  - material + non-empty warnings → `ValueError("material terminal result 禁止携带 company metadata warning")`
- 测试 `test_filing_pipeline_warning_parser_accepts_only_exact_closed_values`：空数组与唯一规范 warning。
- 测试 `test_filing_pipeline_warning_parser_fails_closed`：null、错 shape、未知 kind、错误 message、extra field、重复、超限。
- 测试 `test_pipeline_warning_parser_requires_filing_field_but_allows_material_missing`：material missing → empty；filing missing → fail；material null → fail。
- 测试 `test_pipeline_warning_invariant_rejects_non_success_status`：failed/cancelled/deleted + non-empty warnings → fail。

### 10. 四个 SourceKind callsite

**PASS**。直接证据：

- `service_runtime.py:182-184`：SEC filing → `source_kind=SourceKind.FILING`
- `service_runtime.py:188-190`：CN filing → `source_kind=SourceKind.FILING`
- `service_runtime.py:243-245`：US material → `source_kind=SourceKind.MATERIAL`
- `service_runtime.py:264-266`：CN material → `source_kind=SourceKind.MATERIAL`
- 测试 `test_production_runner_parser_callsites_use_explicit_source_kind`：AST 解析确认 `source_kind_names == ["FILING", "FILING", "MATERIAL", "MATERIAL"]`，每个 keyword 显式存在且 `keyword.value.value.id == "SourceKind"`。

### 11. S3 边界未提前

**PASS**。S1+S2 未修改：

- `FinsUploadResultSummary`（`ingestion_runtime.py:1791` 之后）：无 diff。
- `to_json_summary()`：无 diff。
- `_upload_summary_from_result`（`service_runtime.py`）：无 diff。
- `direct_events.py`：无 diff。
- `cli/output.py`：无 diff。
- `fins_wait_adapter.py`：无 diff。

### 12. docstring/types/README triggers

**PASS**。

- 所有新增/修改函数均有完整中文 docstring（Args/Returns/Raises）。
- 类 docstring 含 Attributes 说明。
- 复杂逻辑有行内注释（如 capability transfer 注释 `filing_upload_publication.py:786`、`filing_upload_publication.py:829`）。
- 无 `object`、`Any`、无类型参数或返回值。
- README 按 plan 不在 S1+S2 修改，正确。

### 13. commit_batch 全量收敛（§9.2 清单）

**PASS**。`rg -n "def commit_batch" dayu tests` 输出 12 行，精确对应：

| # | 位置 | 注解 |
| --- | --- | --- |
| 1 | `dayu/fins/storage/repository_protocols.py:701` | Protocol: `CompanyMetaCommitOutcome \| None` |
| 2 | `dayu/fins/storage/_fs_storage_infra.py:533` | Core: `CompanyMetaCommitOutcome \| None` |
| 3 | `dayu/fins/storage/fs_batching_repository.py:64` | Repository: `CompanyMetaCommitOutcome \| None` |
| 4 | `tests/fins/upload_filing_test_support.py:69` | TrackingBatchingRepository: `CompanyMetaCommitOutcome \| None` |
| 5 | `tests/fins/test_sec_pipeline_download_stream.py:101` | Download fake: `CompanyMetaCommitOutcome \| None` |
| 6 | `tests/fins/test_cn_download_workflow.py:193` | Download fake: `CompanyMetaCommitOutcome \| None` |
| 7 | `tests/fins/test_filing_upload_publication.py:136` | Publication fake: `CompanyMetaCommitOutcome \| None` |
| 8 | `tests/fins/test_fins_ingestion_runtime.py:3526` | Runtime fake: `CompanyMetaCommitOutcome \| None` |
| 9 | `tests/fins/test_docling_upload_service.py:368` | Docling identity: `CompanyMetaCommitOutcome \| None` |
| 10 | `tests/fins/test_docling_upload_service.py:479` | Docling commit-fail: `CompanyMetaCommitOutcome \| None` |
| 11 | `tests/fins/test_docling_upload_service.py:531` | Docling barrier: `CompanyMetaCommitOutcome \| None` |
| 12 | `tests/fins/test_sec_pipeline_upload_filing_stream.py:461` | SEC snapshot: `CompanyMetaCommitOutcome \| None` |

production 3 个（Protocol + 2 implementation），test 9 个定义/7 个文件（其中 `test_docling_upload_service.py` 3 个定义）。与 §9.2 清单精确对应。

### 14. `hasattr/getattr/Any/object` 检查

**PASS**。`rg -n "hasattr|getattr|Any|object" dayu/fins/domain/company_meta_contract.py dayu/fins/company_metadata_warning.py dayu/fins/pipelines/upload_company_meta.py dayu/fins/pipelines/filing_upload_publication.py` 输出为空。

### 15. 兼容性代码检查

**PASS**。无 compatibility re-export、wrapper/facade、默认值补偿或 loose parsing。

---

## 测试质量审查

### 覆盖充分性

| 维度 | 测试 | 结论 |
| --- | --- | --- |
| domain outcome | `test_preserve_published_unions_aliases_and_preserves_non_identity` | 覆盖 ignored_company_name fact |
| domain equivalence | `test_company_name_equivalence_*` (2 parametrized) | 覆盖 NFKC/空白/casefold 和语义猜测拒绝 |
| upload decision fresh | `test_fresh_upload_*` (4 tests) | 覆盖等价/缺失/不同名称/alias |
| upload decision stale | `test_stale_upload_refresh_carries_adopted_requested_name` | 覆盖 refresh 采用 |
| shared owner warning matrix | `test_metadata_only_skip_transfers_capability_and_projects_exact_outcome` | 覆盖 name-only 和 alias-only skip |
| capability transfer success | same test + `events == ["stage", "commit"]` | 覆盖 |
| capability transfer commit-fail | `test_metadata_only_skip_commit_failure_never_rolls_back_consumed_capability` | 覆盖 |
| capability transfer stage-fail | `test_metadata_only_skip_stage_failure_rolls_back_once_before_capability_transfer` | 覆盖 |
| whole-tree COMPLETE fail-closed | `test_metadata_only_skip_fails_closed_for_unrelated_incomplete_source_tree` | 覆盖 |
| alias collision | `test_skip_alias_collision_after_capability_transfer_is_typed_and_atomic` | barrier 控制 |
| concurrent winner/loser warning | `test_concurrent_auto_name_warning_uses_publication_final_company_truth` | barrier 控制 |
| concurrent auto alias | `test_concurrent_auto_rejects_nonidentical_candidate_but_commits_valid_alias_intent` | 覆盖 company mismatch |
| SEC failure roundtrip | `test_sec_filing_failure_event_roundtrips_typed_reason_with_empty_warnings` | 覆盖 |
| CN failure roundtrip | `test_cn_filing_failure_event_roundtrips_typed_reason_with_empty_warnings` | 覆盖 |
| parser closed codec | `test_filing_pipeline_warning_parser_*` (2 tests) | 覆盖 |
| parser source-kind boundary | `test_pipeline_warning_parser_requires_filing_field_but_allows_material_missing` | 覆盖 |
| parser success-only invariant | `test_pipeline_warning_invariant_rejects_non_success_status` | 覆盖 |
| SourceKind callsite | `test_production_runner_parser_callsites_use_explicit_source_kind` | AST 静态检查 |
| blocker SEC | `test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision` | 覆盖 bytes/updated_at/source tree |
| blocker CN | 同名 CN 版本 | 覆盖 |

### 测试弱化检查

**PASS**。无弱化：

- blocker 测试保留了原始回归语义：`filing_action == "update"`、`status == "skipped"`、`begin_tokens == 1`、`commit_tokens == begin_tokens`、`rollback_tokens == []`、`stage_tokens == begin_tokens`、`source.stage_tokens == []`。
- bytes/updated_at/source tree 不变量均有显式断言。
- `test_concurrent_auto_name_warning_uses_publication_final_company_truth` 断言 `final_meta.company_name == winner["company_name"]`（不是 loser 的名称）。

---

## Residual risks

| ID | 分类 | 说明 |
| --- | --- | --- |
| R1 | `assigned to later work unit` | name-only metadata batch 的 writer lock/physical swap 成本 |
| R2 | `assigned to later work unit` | material upload 类似 company-name 行为 |
| R3 | `assigned to later work unit` | 真实 CLI evidence、scenario/oracle/frozen evidence 更新 |
| R4 | `assigned to later work unit` | commit durable 但 post-commit guard-release/cleanup 报错的运维可见性 |
| R5 | `fixed in current slice` | DS-RR1: SEC/CN producer roundtrip |
| R6 | `fixed in current slice` | DS-RR2: capability transfer 顺序 |
| R7 | `assigned to later work unit` | `_optional_upload_company_name` 对空白输入的测试覆盖补充 |

没有 `covered by later approved slice`、`tracked by existing issue` 或 `requiring new issue or explicit user decision` 的 residual。没有未分类 residual risk。

---

## 结论

**PASS**。UF-FIX11 原子 S1+S2 implementation 的语义 owner、capability transfer、warning invariant、terminal producer、closed codec、parser boundary、SourceKind callsite、commit_batch 收敛、bytes/updated_at/source tree 不变量、docstring/types 和 test quality 全部通过审查。两个非阻塞观察（Finding 001 校验文案一致性、Finding 002 测试覆盖补充）不影响正确性，分类为后续 work unit。
