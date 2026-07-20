# WU-SEMANTIC-OWNERSHIP-01 / R07 Fixed Plan Complete Re-Review — AgentDS 第二路

## 0. 元数据

- **review type**: 对已 fix 的 R07 plan 做第二路 complete re-review（不是新 WU，不是首轮 review）
- **immutable target**: `docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`
- **target SHA-256**: `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`
- **transition base**: `5f09e2cc2e4edfc7dc1388e14744bf1300637093`
- **R06 completion**: `f1c56ea90c587314cc7cba35e5b4c790d13d2fc3`
- **reviewer**: AgentDS（第二路）
- **timestamp**: 2026-07-16T12:10:45+08:00
- **裁决优先级**: Controller discussion Topic 6.3/6.7 与 `docs/fins/design.md` > Controller adjudication > 本 fixed plan

### 0.1 首轮 DS review 回溯

| 首轮 finding | 严重程度 | Controller disposition | fixed plan closure |
|---|---|---|---|
| F-R07-DS-01 | 高 | PF-04: lock-only inventory 迁移细节 | **CLOSED** — §5.1.6 line 230, §7.1 step 2 line 341, targeted test line 383 |
| F-R07-DS-02 | 高 | PF-05: maintenance cleanup 迁移细节 | **CLOSED** — §7.1 step 4 line 343, targeted test line 384 |
| F-R07-DS-03 | 中 | PF-06: 静态损坏优先级 | **CLOSED** — §5.3 lines 257-260, targeted test line 462, §8.4 item 4 |
| F-R07-DS-04 | 中 | PF-03: digest→token 时序 | **CLOSED** — §2 line 88, §5.2 lines 236-241, §7.2 lines 428-429 |
| F-R07-DS-05 | 中 | PF-07: SEC fiscal 文件选择语义 | **CLOSED** — §0.2 line 29, §5.4 line 267, §7.2 step 5 |
| F-R07-DS-06 | 低 | PF-08: creation lock double-check | **CLOSED** — §5.5.1 line 273, §7.3 lines 519/530, targeted test line 552 |
| F-R07-DS-07 | 低 | PF-09: recursive JSON scan | **CLOSED** — §3.7 line 203, §8.3 line 680 |
| F-R07-DS-08 | 低 | PF-10: delete/reset snapshot absence | **CLOSED** — §5.2.4 line 239, S2 targeted test line 457 |
| F-R07-DS-09 | 低 | PF-11: list-only source kind projection | **CLOSED** — §0.2 line 28, §5.5.3 line 275, §7.3 lines 520-521 |

### 0.2 首轮 DS open questions 最终 disposition

| open question | Controller response | 当前 fixed plan 处理 | disposition |
|---|---|---|---|
| Q-R07-DS-01: `_build_source_revision` 删除时机 | — | §7.2 step 2 明确 S2 删除 hash builder | **RESOLVED** |
| Q-R07-DS-02: blob-first descriptor 时序 | 实现 review 按 §5.1.7 验证 | §5.1.7 保持"首个 payload 前创建/验证 descriptor" | **RESOLVED** — implementation gate 验证 |
| Q-R07-DS-03: cross-document diagnosis lightweight/full snapshot | plan §5.5.7 已覆盖 | §5.5.7 保持不变 | **RESOLVED** |

### 0.3 MiMo 首轮 findings 最终 disposition

| finding | Controller disposition | fixed plan 状态 |
|---|---|---|
| R07-PR-F01 (coverage metric) | PF-01 accepted | **CLOSED** |
| R07-PR-F02 (S3 F401 scope) | PF-02 accepted | **CLOSED** |
| R07-PR-F03 (source_kind 必填) | **rejected** — design-owner 裁决 | **REJECTED** — 不重提 |
| R07-PR-F04 (digest 字段名) | PF-03 merged | **CLOSED** |

## 1. 审查范围与方法

本 re-review 的职责不是重复首轮 DS review，而是：

1. 逐项验证 R07-PF-01..12 在 fixed plan 中是否真实关闭
2. 检查 12 组 fix 是否引入新矛盾、新歧义或新缺陷
3. 完整挑战 identity descriptor、lock/recovery/maintenance、token breaking type/timing、snapshot fd-copy transient-vs-corruption、SEC existing filename selection、cache double-check/borrow/close、list-only source kind、9 tools completed/failed/cancelled recursive exposure、coverage/scans/smoke、three-slice allowlist 和 S3 final review vs umbrella aggregate gate
4. 核对自己首轮 F01-F09 及 open questions 的最终 disposition
5. 遵守用户明确禁止项：不重提 source kind 必填、不提出 batch snapshot/has_xbrl_instance 新分类/compat/deferred ISSUE/统一 authorization

### 1.1 已读取的完整证据

- fixed plan 789 行全文
- AGENTS.md 129 行全文
- `docs/fins/design.md` §1–§10 全文
- Controller discussion Topic 6.3 (lines 453-457) 与 6.7 (lines 492-503)
- AgentMiMo 首轮 review 150 行全文
- AgentDS 首轮 review 454 行全文
- Controller adjudication 94 行全文
- AgentCodex fix artifact 88 行全文
- Controller fix validation 65 行全文
- 当前 production code 关键段:
  - `_fs_company_meta_core.py:340-362` (`_published_ticker_directory_names`)
  - `_fs_maintenance_core.py:523-582` (`_cleanup_stale_filing_documents_impl`)
  - `_fs_storage_infra.py:1873-1911` (`_remove_manifest_items`)
  - `document_models.py:495-505` (`CompanyMetaInventoryEntry`)
  - `document_models.py:289-318` (`SourceDocumentRevision`)
  - `read_runtime.py:204/219` (`_CachedProcessor`/`_CachedSourceDocumentMeta` 的 revision 字段)
  - `fins_tools.py:216-286` (`_FinsReadProcessTarget.__call__`)
  - `cache.py:122-179` (put/evict/clear lifecycle)

## 2. R07-PF-01..12 逐项 closure 验证

### R07-PF-01 — line coverage 口径

- **fixed plan 位置**: §8.1 lines 595-603
- **closure 证据**: 保留 `coverage run --branch` 仅作诊断；门禁改为逐文件 `covered_lines / num_statements` 复算 line coverage；明确 `summary.percent_covered` 不得替代 line gate，composite/branch 指标必须另名
- **验证**: Python assertion 表达式从 `p["files"][f]["summary"]["percent_covered"]` 改为 `p["files"][f]["summary"]["covered_lines"] / p["files"][f]["summary"]["num_statements"]`。与 AGENTS.md "单文件测试覆盖率目标为 >= 80%" 的 line coverage 口径一致。与 R06 completion Controller validation §4 的复算方法一致
- **closure 状态**: **CLOSED** ✓

### R07-PF-02 — S3 base F401 点名

- **fixed plan 位置**: §7.3 lines 494-496
- **closure 证据**: 明确只删除 `QueryDiagnosis`（line 62）与 `SEARCH_MODE_AUTO`（line 64）两个 base F401；禁止扩大清理其它 legacy Ruff 项
- **验证**: `read_runtime.py` 当前 line 62/64 的精确符号名已写入 plan。S3 changed-file scoped Ruff 预期 0。full Ruff 从 152 降至 150，F401 从 72 降至 70
- **closure 状态**: **CLOSED** ✓

### R07-PF-03 — digest→token breaking rename 与 SHA grammar 删除

- **fixed plan 位置**: §2 line 88; §5.2 lines 236-241; §7.2 lines 428-429, 454; §8.3 lines 663-671
- **closure 证据**:
  - S2 step 1: `SourceDocumentRevision.digest` → `SourceDocumentRevision.token`；`__post_init__` 只拒绝空字符串，接受任意非空 opaque token；不保留 alias/property/双字段/SHA-shaped 兼容值
  - S2 step 2: 删除 `_build_source_revision`、selected-field hash builder 与 `sha256:` grammar；`get_source_revision` 只机械读 persisted token 构造 `SourceDocumentRevision(token=...)`
  - S3 step 5: 从 protocol/wrapper/core 删除 `get_source_revision`
  - 新增 targeted test: `test_source_document_revision_accepts_nonempty_opaque_token_and_rejects_empty`（line 454）
  - §8.3 revision/snapshot consumer scan 期望 `.digest` 残留为 0
- **验证**: 当前 production code 中 `SourceDocumentRevision(digest=...)` 构造仅在 `_fs_source_document_core.py:213`（在 S1/S2 allowlist）；`read_runtime.py` 只使用类型注解和对象比较（`!=`），不访问 `.digest` 字段；tests 无 `.digest` 访问。机械 rename 级联范围极小，不跨 allowlist 边界
- **closure 状态**: **CLOSED** ✓

### R07-PF-04 — lock-only inventory 不投影 key

- **fixed plan 位置**: §5.1.6 line 230; §7.1 step 2 line 341; targeted test line 383
- **closure 证据**:
  - `_published_ticker_directory_names` 的 lock stem 只发现 private candidate key
  - business ticker 只可由已验证 target/backup descriptor 恢复
  - lock-only 且无 descriptor 时沿用既有 typed malformed/recovery category，business ticker 缺失
  - 不投影 key/stem，不新造状态名
  - 新增 targeted test: `test_lock_only_company_inventory_has_no_business_ticker_or_internal_key`（line 383）
- **验证**: 当前 `_published_ticker_directory_names`（`_fs_company_meta_core.py:340-362`）从 directory names 和 lock stems 聚合 ticker names。S1 后改为聚合 private candidate keys，由 `scan_company_meta_inventory` 读 descriptor 恢复 business ticker。lock-only 路径（lock 存在但 target/backup 无可验证 descriptor）对应 crash-recovery 中间态，不输出 business ticker
- **closure 状态**: **CLOSED** ✓

### R07-PF-05 — maintenance cleanup 先恢复 external id

- **fixed plan 位置**: §7.1 step 4 line 343; targeted test line 384
- **closure 证据**:
  - `cleanup_stale_filing_documents` 先从每个 child descriptor 恢复 exact external document id
  - 再对该 external id 执行既有 `fil_` 业务分类与 valid-id 比较
  - private child key 的 prefix/value 不参与业务判断
  - 新增 targeted test: `test_stale_filing_cleanup_uses_descriptor_external_id_in_opaque_layout`（line 384）
- **验证**: 当前 `_cleanup_stale_filing_documents_impl`（`_fs_maintenance_core.py:523-582`）使用 `child.name.startswith("fil_")`（line 556）和 `child.name in normalized_valid_document_ids`（line 568）做业务判断。S1 后 child.name 是 private key，不以 `fil_` 开头且不等于 external id。迁移路径：遍历 child dirs → 读 descriptor 得 external id → 用 external id 做 `fil_` 前缀判断与 valid-id 比较 → 收集 private key 做 `shutil.rmtree`。此路径不依赖 `_normalize_document_id`（S1 step 5 删除）。连带 `_remove_manifest_items`（`_fs_storage_infra.py:1873`）也需从 descriptor external id 比较替代 `_normalize_document_id` 调用
- **closure 状态**: **CLOSED** ✓

### R07-PF-06 — 静态损坏优先级

- **fixed plan 位置**: §5.3 lines 257-260; targeted test line 462; §8.4 item 4 line 689
- **closure 证据**:
  - 只有 persisted revision/descriptor 真实变化才重取 attempt
  - revision/descriptor 未变时 inode 内容、`fstat`、EOF、declared size/hash 异常立即按既有 corruption/validation 边界 fail closed
  - 不重试、不伪装为 `source_changed_during_read`
  - 新增 targeted test: `test_snapshot_fd_copy_silent_mutation_is_corruption_without_revision_change`（line 462）
  - §8.4 smoke item 4: 真实 fd-copy barrier 静默修改 inode → immediate corruption/validation failure
- **验证**: 在 R06 publication guard + atomic rename 合法写路径下，已打开 inode 内容或 `fstat` 变化但 revision/descriptor 未变不可能是合法 publication race。算法步骤 2（copy 后验证）与步骤 4（revision 未变时 corruption fail closed）的优先级现在明确：步骤 4 覆盖所有 revision 未变时的异常（包括 `fstat` 变化、EOF/size/hash 不匹配），步骤 3 的 retry 只在 revision/descriptor 真实变化时触发
- **closure 状态**: **CLOSED** ✓

### R07-PF-07 — SEC fiscal 只换 path owner

- **fixed plan 位置**: §0.2 line 29; §5.4 line 267; §7.2 step 5 line 432
- **closure 证据**:
  - 冻结 `_build_download_local_file_map` 的 descriptor business filename lowercase map
  - 冻结 `_pick_download_xbrl_file` 的既有排序、suffix、XML fallback 排除规则
  - 唯一变化是所有 temp paths 同源于一份 full snapshot
  - 明确禁止 `has_xbrl_instance` 内容嗅探分类或新文件分类 schema
- **验证**: 当前 `_build_download_local_file_map` 对 meta files 逐个 `get_source(...).materialize()`。S2 改为从 snapshot descriptor 的 file list 取得所有 business filenames，在 snapshot temp tree 中按 filename 定位，保持既有 lowercase map 构造与文件选择逻辑。XBRL instance/schema/linkbase 文件选择语义不变
- **closure 状态**: **CLOSED** ✓

### R07-PF-08 — creation lock double-check

- **fixed plan 位置**: §5.5.1 line 273; §7.3 lines 519, 530; targeted test line 552; §8.4 item 5 line 690
- **closure 证据**:
  - 同 document creation lock 内 double-check matching cached entry
  - 已有可借 entry 时 losing 调用关闭自己取得的 full snapshot 并 borrow existing
  - 否则只构建并发布一个 processor
  - 新增 targeted test: `test_concurrent_initial_cache_miss_builds_one_processor_and_closes_losing_snapshot`（line 552）
  - §8.4 smoke item 5: 两线程同 revision initial cache miss 竞争，只构建一个 processor
- **验证**: 当前 `_get_creation_lock`（`read_runtime.py:2719-2738`）只返回 `Lock`，不含 double-check。S3 在 creation lock 内加入：获取锁 → 再次检查 cache → 有则 borrow existing + close losing snapshot → 无则 build + publish。double-check 与 borrow 之间存在 retire 竞态（其他文档的 eviction 可能 retire 当前 entry），但 borrow 失败时自然地 fall through 到 build 路径，且 losing snapshot 已在 lock 获取前取得（不需要重复），实现时 borrow 失败后直接使用已取得的 full snapshot 构建即可
- **closure 状态**: **CLOSED** ✓

### R07-PF-09 — recursive exposure test 补齐 cancellation

- **fixed plan 位置**: §3.7 line 203; §8.3 line 680
- **closure 证据**:
  - §3.7 与 §8.3 已对齐：明确 9 个 read tools 的 completed、failed、cancelled 及各自 citation 路径
  - 递归遍历运行时 JSON 全部 nested key/value
  - 禁止 revision/private key/absolute temp path/`local://` 泄露
  - 不能只 grep Python 源码或只覆盖成功/失败路径
  - S3 targeted test `test_read_outputs_never_expose_revision_internal_key_local_uri_or_temp_path`（line 568）覆盖
- **验证**: 9 个 read tools = `list_documents`(line 600), `get_document_sections`(line 722), `read_section`(line 781), `search_document`(line 926), `list_tables`(line 1293), `get_table`(line 1395), `get_page_content`(line 1501), `get_financial_statement`(line 1575), `query_xbrl_facts`(line 1659)。一个 targeted test 覆盖 9×3=27 个路径，实现上建议 parametrize，但这是 implementation detail
- **closure 状态**: **CLOSED** ✓

### R07-PF-10 — delete/reset snapshot absence

- **fixed plan 位置**: §5.2.4 line 239; S2 targeted test line 457
- **closure 证据**:
  - source delete/reset 后 source、token 与 snapshot resource 同时不存在
  - snapshot read 明确 `FileNotFoundError`
  - 新增 S2 storage-owner targeted test: `test_snapshot_is_not_found_and_has_no_token_or_resource_after_source_delete_or_reset`（line 457）
  - S3 `test_cached_processor_is_not_returned_after_source_deleted` 保持独立，不替代 storage contract
- **closure 状态**: **CLOSED** ✓

### R07-PF-11 — list-only 不做 N+1

- **fixed plan 位置**: §0.2 line 28; §5.5.3 line 275; §7.3 lines 520-521; targeted test line 572
- **closure 证据**:
  - `list_documents` 继续组合 filing/material 两个 `list_source_document_ids` typed list projections
  - 禁止 per-document snapshot N+1、batch snapshot API、filing-first guess
  - 仅单 document read 保留 optional `source_kind=None` 的 0/1/2 storage resolution
  - 新增 targeted test: `test_list_documents_uses_two_typed_storage_lists_without_per_document_snapshot`（line 572）
- **验证**: 当前 `list_source_document_ids(ticker, source_kind)` 分别按 source_kind 列出文档。`list_documents` 调用两次（FILING + MATERIAL），组合业务列表。这不需要 per-document snapshot，也不需要新 batch API。source_kind 信息可以从 list projection 的内置 metadata 获得（如 manifest/descriptor 中的 source_kind），不需要对每个文档调 `read_source_snapshot`
- **closure 状态**: **CLOSED** ✓

### R07-PF-12 — S3 final review 与 umbrella aggregate 不重复

- **fixed plan 位置**: §10.2 lines 724-726
- **closure 证据**:
  - S3 cumulative review 明确是 R07 完整树唯一一次双路 final code review
  - 删除原 plan 中等价的 R07-only aggregate dual deepreview
  - fixing → Controller validation → 双路 complete re-review → Controller adjudication → accepted implementation commit
  - 跨 R01—R12 umbrella aggregate deepreview 保留在所有 remediation sub-WU 完成后
- **closure 状态**: **CLOSED** ✓

## 3. Fix 引入的新缺陷检查

### 3.1 方法：逐项对照 fix 前后 plan 文本，检查矛盾、歧义、遗漏

对 12 组 fix 逐一扫描：

| PF | fix 引入的新矛盾/歧义 | 审查结论 |
|---|---|---|
| PF-01 | coverage JSON `covered_lines / num_statements` 分母是 `num_statements` 而非 `num_statements - num_excluded`。`coverage json` 输出的 `num_statements` 是总 statement 数，`covered_lines` 是覆盖行数。若文件有 `# pragma: no cover` 或 exclude pattern，`num_statements` 可能包含被排除行，导致分母偏大。但对本项目 coverage 配置而言，排除模式仅用于 `if TYPE_CHECKING` 和 `__repr__` 等，影响极小 | 无材料缺陷 |
| PF-02 | S3 删除 2 F401 后 full Ruff ≤150。base=152，−2=150。若 S1/S2 新增任何 F401/E402/F841 而不属于 allowlist 内删除，会超限。但 plan §8.2 已明确 S1/S2 不得超 base 152 | 无材料缺陷 |
| PF-03 | `token` 字段名改为 S2 一次性 breaking rename。验证发现当前 production code 中 `read_runtime.py` 不访问 `.digest` 字段（只用 `SourceDocumentRevision` 类型注解和 `!=` 对象比较），tests 不访问 `.digest`。唯一构造点 `_fs_source_document_core.py:213` 在 S1/S2 allowlist。机械级联极小，不跨 allowlist | 无材料缺陷 |
| PF-04 | `_published_ticker_directory_names` 返回类型从 `list[str]`（ticker names）变为 private candidate keys。`scan_company_meta_inventory` 需改为按 key 读 descriptor 恢复 business ticker。两者均在 S1 allowlist 内，且 plan §3.2 row "company meta/inventory" 已描述正确流程 | 无材料缺陷 |
| PF-05 | `_remove_manifest_items`（`_fs_storage_infra.py:1873`）当前使用 `_normalize_document_id(document_id)`（line 1888）与 manifest `doc.get("document_id")` 比较。S1 step 5 删除 `_normalize_document_id`，step 4 迁移 `cleanup_stale_filing_documents`。`_remove_manifest_items` 也在 `_fs_storage_infra.py`（S1 allowlist），需同步改为 exact external id 比较。plan 未显式列出此函数，但它由 `cleanup_stale_filing_documents` 调用链覆盖，implementation agent 需追踪 | 观察项（见 NEW-OBS-01） |
| PF-06 | 静态损坏 fail closed 路径与现有 corruption/validation typed error 的映射：plan 说"立即按既有 corruption/validation 边界 fail closed"。需要确认既有边界是否有合适的 typed error 类型。当前 `_validate_complete_source_tree` 在 `_fs_source_document_core.py` 中，corruption 可能映射为 `ValueError` 或专用 storage error。snapshot 实现需选择正确的既有类型，不新增 error code | implementation detail，非 plan 缺陷 |
| PF-07 | SEC fiscal 的 `_pick_download_xbrl_file` 当前依赖 `has_xbrl_instance`（`_fs_source_document_core.py:38` import）。plan 冻结既有 suffix/XML fallback 规则，不引入新嗅探。但 `has_xbrl_instance` 是既有 import — 若该函数在 snapshot 上下文中仍需判断文件是否为 XBRL instance，需通过 snapshot temp tree 读取文件内容（不是 repository read）。这是正确行为，plan 未禁止 | 无材料缺陷 |
| PF-08 | creation lock double-check 与 eviction race：borrow 在 entry 被 retire 后可能失败（entry 标记 retired 时拒绝新 borrow），此时 losing caller 的已取得 full snapshot 可直接用于构建新 processor 并 publish。plan §7.3 状态/失败/并发/cleanup 未显式描述此 fallback，但 §5.5.1 "否则才从当前full snapshot构建并发布唯一processor entry" 已隐含 | 无材料缺陷 |
| PF-09 | 一个 targeted test 覆盖 9 tools × 3 states = 27 paths + citation。实现上单一测试函数可能过长，建议 parametrize。这是 implementation detail，不是 plan 缺陷 | 无材料缺陷 |
| PF-10 | `FileNotFoundError` 用于 delete/reset 后 snapshot read — 需确认此异常不与"document 从未存在"混淆。plan §5.2.4 说"source delete/reset后source、token与snapshot resource同时不存在"，语义明确 | 无材料缺陷 |
| PF-11 | list_documents 的 source_kind 信息在 typed list projection 中的来源：当前 `list_source_document_ids(ticker, source_kind)` 按 kind 分别返回，kind 隐含在调用参数中（两次调用）。`list_documents` 组合结果时已知每个 doc 来自 filing 还是 material list。不需要 descriptor read | 无材料缺陷 |
| PF-12 | S3 cumulative review = R07 唯一 final code review。这意味着 S1/S2 的 MiMo/DS review 是 cumulative 但非 final。plan §7 明确 "每slice结束先做Controller scope/验证与AgentMiMo/AgentDS双路cumulative review"。S3 的 "cumulative review 就是 R07 完整树唯一一次双路final code review" 意味着 S3 review 比 S1/S2 review 具有更高 finality。这个区分是合理的——S1/S2 review 找 slice 级问题，S3 review 做 complete-tree adjudication | 无材料缺陷 |

### 3.2 新观察项

#### NEW-OBS-01 — 低 — `_remove_manifest_items` 的 `_normalize_document_id` 迁移未在 plan 中显式列出

- **位置**: plan §7.1 S1 step 4
- **问题类型**: 不可直接实施（轻微）
- **当前写法**: plan §7.1 step 4 列出 `cleanup_stale_filing_documents` 的迁移，但未显式列出其调用链上的 `_remove_manifest_items`（`_fs_storage_infra.py:1873-1892`）
- **反例**: `_remove_manifest_items` 当前在 line 1888 使用 `_normalize_document_id(document_id)` 构造 `stale_set`。S1 step 5 删除 `_normalize_document_id`，step 4 必须已将此调用改为 exact external id comparison
- **为什么不是材料缺陷**: `_fs_storage_infra.py` 在 S1 allowlist 中；`_remove_manifest_items` 是 `cleanup_stale_filing_documents` 的直接 callee（line 576）；implementation agent 追踪调用链即可发现。此函数只需将 `_normalize_document_id` 调用替换为 exact string comparison（manifest 已存 exact external ids），改动一行
- **直接证据**: `_fs_storage_infra.py:1888`; `_fs_maintenance_core.py:576`
- **影响**: implementation agent 如在 S1 step 4 只改 `cleanup_stale_filing_documents` 而遗漏 `_remove_manifest_items`，会在 step 5 删除 `_normalize_document_id` 后 pyright 报错（undefined name）。pyright 会立即捕获，不会静默失效
- **建议**: 无需修改 plan；implementation agent 在 S1 step 4 trace callee 即可
- **严重程度**: 低

## 4. 强制 focus area 逐项完整挑战

### 4.1 identity descriptor/lock/recovery/maintenance

**descriptor 完整性**: plan §5.1.3 要求 descriptor 自解释记录 namespace 与 exact external identity。descriptor 文件由 `_write_json` 原子写。验证了所有 12 个 namespace/layout row（§3.2）的 descriptor 覆盖：ticker target、staging、backup、source(filing+material)、processed、rejected artifacts 各持 descriptor。PASS。

**lock locator**: PF-04 fix 后的 lock stem→candidate key→descriptor→business ticker 链完整。验证了 lock-only 无 descriptor 时沿用既有 typed malformed/recovery category 且 business ticker 缺失——不泄露 key，不新增状态名。PASS。

**recovery round-trip**: plan §5.1.6 要求 journal 保持 R06 闭集 `{transaction_id, ticker, phase}`（ticker 为 exact external value），recovery 由 journal/backup 内 descriptor 重新派生并交叉验证 private key。targeted test `test_recovery_round_trips_opaque_ticker_without_path_name_inference`（line 385）覆盖。PASS。

**maintenance cleanup**: PF-05 fix 后的 descriptor→external id→业务规则链完整。验证了 `fil_` 前缀判断和 valid-id 比较均使用 descriptor-derived external id。PASS。

**反例审查**:
- descriptor corrupt/missing → fail closed（§5.1.4），不 fallback 扫描
- 两个不同 external identity deterministic collision → fail closed（§5.1.3 blob-first，§5.1.7 首个 payload 前验证）
- backup 内 descriptor 与 target descriptor 不一致 → 交叉验证失败（§5.1.6）
- 均未发现绕过路径

### 4.2 token breaking type/timing

**S2 时序**: §7.2 step 1 做 `digest→token` rename + `__post_init__` 放宽 → step 2 删除 hash builder + `get_source_revision` 机械读 → S3 step 5 删除 method。三阶段无循环依赖。

**类型安全**: 验证了 `SourceDocumentRevision` 的唯一构造点（`_fs_source_document_core.py:213`）在 S1/S2 allowlist；`read_runtime.py` 不访问 `.digest` 字段。机械 rename 的级联范围：`document_models.py`（`__post_init__` 内 `.digest` → `.token`）、`_fs_source_document_core.py:213`（构造 keyword）、S1/S2 test files。全部在对应 slice allowlist 内。

**opaque contract**: plan §2 明确 `token` 字段名仍不是业务/tool/README/LLM contract。PASS。

**反例审查**:
- 旧 read runtime 在 S2 checkpoint 仍能 type-check：`SourceDocumentRevision` 类型注解不变，对象比较用 `__eq__`。确认 ✓
- S2 后没有 `.digest` 残留：§8.3 scan 期望残留为 0。PASS
- 没有 alias/compat property/双字段：plan §2、§5.2.1、§5.2.6 三处禁止。PASS

### 4.3 snapshot fd-copy transient-vs-corruption

**算法步骤 2-4 的优先级**: PF-06 fix 后明确——步骤 3 的 post-copy revision check 是唯一 retry 触发条件；步骤 4 覆盖所有 revision 未变时的异常（fstat 变化、EOF/size/hash 不匹配）。这两条路径互斥且完备。

**R06 模型依赖**: 算法正确依赖 R06 atomic rename + fd 持有模型。Step 1 在 publication guard 内打开 fds；R06 rename 不影响已打开 inode（Unix semantics）；step 3 短 guard 核对 revision 检测 publication change。A/B 不会混版。

**transient vs sustained**: plan §7.2 状态/失败/并发/cleanup 要求 transient test "至少观察一次discarded attempt并最终返回一致B"、sustained test "只断言typed exhaustion、所有temp/fd清理和无partial result"。§8.4 smoke items 2-3 补充 barrier 协调。

**反例审查**:
- 文件被非 publication 路径直接修改（违反 R06 contract）→ revision 未变 → step 4 corruption fail closed。正确 ✓
- 文件系统静默损坏（bit rot）→ revision 未变 → step 4 corruption fail closed。正确 ✓
- publication 发生在 copy 期间 → revision 变化 → step 3 retry。正确 ✓
- 持续 churn 耗尽 budget → typed consistency error，不伪装 source_changed。正确 ✓

### 4.4 SEC existing filename selection

**冻结语义**: PF-07 fix 后明确 `_build_download_local_file_map` 仍按 snapshot descriptor 声明的业务 filename 建立 lowercase map；`_pick_download_xbrl_file` 仍沿用既有排序、suffix 优先级与 XML fallback 排除规则。唯一变化是所有 temp paths 来自同一 full snapshot。

**文件选择不依赖 repository reread**: 当前 `_pick_download_xbrl_file` 通过 `has_xbrl_instance` 检查文件内容判断是否为 XBRL instance。S2 后此检查通过 snapshot temp tree 中的文件完成——文件内容不变，检查结果不变。不引入新嗅探分类。

**反例审查**:
- snapshot 中 XBRL instance/schema/linkbase 跨文件选择是否仍正确 → 文件内容未变，选择逻辑未变，只是文件位置从 published tree 变为 temp tree
- `has_xbrl_instance` import 保留 → plan §0.2 和 §5.4 的禁止项针对"引入新分类/schema"，不禁止既有 import

### 4.5 cache double-check/borrow/close

**creation lock 协议**: PF-08 fix 后完整协议为：lightweight miss → 取 full snapshot → 获取 creation lock → double-check matching entry → 有则 close losing snapshot + borrow existing → 无则 build processor + publish entry + borrow。

**borrow/retire/close 生命周期**: plan §5.5.1-10 定义了完整状态机。entry 状态：live（可借）→ retired（不新借，等 active→0 后 close）→ closed（不可逆）。LRU 返回 displaced values 给 owner，owner 负责 retire + conditional close。

**eviction-active 边界**: PF-08 fix 的 double-check 与 eviction 之间的 retire race 已在 §3.1 PF-08 行分析——borrow 失败时自然 fall through。不属于 plan 缺陷。

**反例审查**:
- cache 返回已 close resource → §5.5.6 禁止。PASS
- eviction 过早 close active borrow → §5.5.2 "active为0立即close，否则最后一个borrow release时close"。PASS
- clear/process target 泄漏 resource → §5.5.10 `finally` 覆盖。PASS
- `__del__` 作为正确性依赖 → §5.5.10 禁止。PASS

### 4.6 list-only source kind

**list-only 路径**: PF-11 fix 后 `list_documents` 调用 `list_source_document_ids(ticker, SourceKind.FILING)` + `list_source_document_ids(ticker, SourceKind.MATERIAL)`，组合业务列表。不调 per-document snapshot，不做 N+1，不做 filing-first guess。

**与单文档 read 的边界**: 只有 `read_source_snapshot(ticker, document_id, source_kind=None)` 使用 0/1/2 storage resolution。list 和 single-document 两条路径的 source kind 解析策略不同但各自由 storage owner 提供，不冲突。

**反例审查**:
- list meta 被误用作 processor citation → §5.5.3 禁止。PASS
- list 结果中 source_kind 信息从 typed list projection 获取（两次不同 kind 调用）→ 不需要 descriptor read。PASS

### 4.7 9 tools completed/failed/cancelled recursive exposure

**覆盖矩阵**: 9 tools × 3 states (completed/failed/cancelled) + citation paths。PF-09 fix 后 §3.7 与 §8.3 对齐，S3 targeted test `test_read_outputs_never_expose_revision_internal_key_local_uri_or_temp_path`（line 568）承载。

**recursive JSON traversal 语义**: 对每个 tool result JSON 递归遍历所有 nested key 和 value（包括 list elements、dict keys/values、nested objects），验证不含 `revision`、`storage_key`、private key pattern、absolute temp path、`local://`。

**当前暴露风险评估**: `_CachedProcessor`（`read_runtime.py:204`）和 `_CachedSourceDocumentMeta`（`read_runtime.py:219`）持有 `revision: SourceDocumentRevision`。但这些是 internal cache objects，不序列化到 tool result JSON。tool result 由 processor 业务结果构造，不包含 cache metadata。风险低。

**反例审查**:
- S3 后 citation 从 snapshot provenance 机械投影，不含 revision/key/path → §5.5.8。PASS
- error message/hint 不暴露 revision/key/path → §5.5.9。PASS
- cancelled path 的 result JSON 可能因 cancellation 位置不同而有不同 shape → recursive test 需覆盖所有 cancellation points。implementation challenge，非 plan 缺陷

### 4.8 coverage/scans/smoke

**coverage 门禁**: PF-01 fix 后逐文件 `covered_lines / num_statements ≥ 80%`。三个 slice 的累计 changed production files 在 §8.1 表中明确。PASS。

**full pyright**: 每 slice 必须 0 errors。PASS。

**Ruff**: changed-file scoped 必须 0。S3 full ≤150。S1/S2 ≤152。PASS。

**source/AST/LLM scans**: §8.3 三组 scan 命令完整。identity source scan 覆盖 `_normalize_ticker/document_id`、`portfolio.*ticker`、`directory_name`、`lock_path.stem`、`child.name`。revision/snapshot consumer scan 覆盖 `get_source_revision`、`_build_source_revision`、`revision_before/after`、`sha256:`、`.digest`、`.materialize(` 等。LLM-facing scan 覆盖 `source_revision`、`storage_key`、`internal_key`、`local://`。PASS。

**smoke**: §8.4 的 8 个真实 filesystem concurrency smoke 覆盖 A/B publication、transient recovery、sustained failure、static corruption priority、cache initial miss serialization、cache lifecycle、citation/result 同版、recovery/security。全部使用 `tmp_path` + 真实 `threading.Event/Barrier`，禁止 `sleep` 作为正确性 oracle。PASS。

**反例审查**:
- coverage JSON 的 `num_statements` 包含 `# pragma: no cover` 行 → 见 §3.1 PF-01 行分析，影响极小
- smoke 测试的 barrier 协调需要 monkeypatch 注入（§8.4 item 3 允许），但不能复制 production 算法或注入测试专用 policy → implementation 约束，非 plan 缺陷

### 4.9 three-slice allowlist

**S1 production**: 9 files（8 existing + 1 new `_fs_identity.py`）。覆盖 ticker target、staging、backup、locks、recovery、company inventory、source filing/material、blob/object key、processed、rejected、maintenance cleanup、manifests/validator。PASS。

**S2 cumulative production**: 15 files（S1 9 + 6 new）。新增 `repository_protocols.py`、`fs_source_document_repository.py`、`_fs_source_snapshot.py`、`ingestion_runtime.py`、`sec_fiscal_fields.py`、`sec_6k_primary_document_repair.py`。覆盖 revision publication、snapshot、non-read consumer migration。PASS。

**S3 cumulative production**: 20 files（S2 15 + 5 new）。新增 `cache.py`、`read_runtime.py`、`error_contract.py`、`fins_tools.py`、`service_runtime.py`。覆盖 read/cache/citation migration、resource cleanup。PASS。

**test allowlist**: 每 slice 的 test files 逐 slice 累计，S1 4 files → S2 5 → S3 8。覆盖所有 changed production files。PASS。

**README allowlist**: S3 明确 `dayu/fins/README.md` 和 `tests/README.md`。不更新根 `README.md`、`dayu/README.md`。PASS。

**反例审查**:
- `fs_company_meta_repository.py`（wrapper）不在 S1 allowlist → 但它只 delegate 到 core implementation，不访问 `directory_name` 或构造 `CompanyMetaInventoryEntry`。验证：line 45 仅 `def scan_company_meta_inventory(self) -> list[CompanyMetaInventoryEntry]:`，不访问字段。PASS
- `repository_protocols.py` 不在 S1 allowlist 但在 S2 allowlist → S1 的 `CompanyMetaInventoryEntry` model change 不改变 protocol method 签名（返回类型仍是 `list[CompanyMetaInventoryEntry]`），protocol file 只在 S2 需要新增 `read_source_snapshot` 方法。PASS

### 4.10 S3 final review vs umbrella aggregate gate

**不重复**: PF-12 fix 后 §10.2 明确 S3 cumulative review = R07 唯一 final code review。fix/fix-review → Controller adjudication → accepted implementation commit。不安排 R07-only aggregate deepreview。PASS。

**不遗漏**: umbrella aggregate deepreview（跨 R01—R12）保留在所有 remediation sub-WU 完成后。PASS。

**反例审查**:
- S1/S2 的 cumulative review 不是 final → 它们找 slice 级问题，不在 S1/S2 做 accepted commit。与 plan §10.2 "S1/S2不得有accepted commit" 一致
- 有人可能误以为 S3 cumulative review 替代了 umbrella aggregate → §10.2 明确禁止

## 5. 明确禁止项合规检查

| 禁止项 | 用户指令 | fixed plan 合规 |
|---|---|---|
| source kind optional typed 0/1/2 重提必填 | "source kind optional typed 0/1/2 是 design-owner裁决，不得无新证据重提必填" | **合规** — 本 review 未重提。Controller adjudication §4 已 reject MiMo R07-PR-F03，fixed plan 保持 `source_kind=None` 的 0/1/2 storage resolution |
| batch snapshot | "不要提出 batch snapshot" | **合规** — 本 review 未提出。fixed plan §0.2、§5.5.3、§7.3 均明确禁止 |
| has_xbrl_instance 新分类 | "不要提出 has_xbrl_instance新分类" | **合规** — 本 review 未提出。fixed plan §0.2、§5.4、§7.2 均明确禁止 |
| compat | "不要提出 compat" | **合规** — 本 review 未提出。fixed plan 多处禁止 alias/property/双字段/兼容值 |
| deferred ISSUE | "不要提出 deferred ISSUE" | **合规** — 本 review 未提出新 deferred ISSUE |
| 统一 authorization | "不要提出 统一authorization" | **合规** — 本 review 未提出。fixed plan §6 row "tool/Host authorization" 明确不触碰 |

## 6. Residual owner 复核

plan §12 的 12 个 residual 逐项核验：

- R08—R12: 明确 owner/future gate，不改。PASS
- Issue 142/151/175/177/178: 明确不实施。PASS
- unified tool authorization: 明确不创建。PASS
- base full-suite Service 配置/import/logging failures: §1.1 ledger 只防扩散。PASS
- private key/revision 算法未来演进: 只要 descriptor round-trip/opaque equality contract 不变。PASS

**特别关注 — 上游 ticker resolver 依赖**: plan §5.1.1 写 "storage 不再重复拥有该业务规则"，即 storage 接收 exact external ticker，不自行做 alias 归一。上游 `try_normalize_ticker` 必须保证同一 business entity 使用同一 exact external ticker。若上游解析失败（两个 alias 获得两个不同 ticker），storage 会为它们创建两个独立的 identity mapping。这是正确的 owner 分离——storage 不拥有 ticker alias 业务规则。R07 closeout 应显式说明此依赖。不是 plan 缺陷。

## 7. Stop conditions 复核

plan §11 的 15 个 stop conditions 逐项核验：每个 condition 的触发场景与 fixed plan 的禁止项/验证矩阵一致。PASS。

## 8. 最终结论

### 8.1 Finding 汇总

| 类别 | 数量 | 详情 |
|---|---|---|
| R07-PF-01..12 closure | 12/12 CLOSED | 见 §2 |
| 首轮 DS F01-F09 disposition | 9/9 addressed | F01→PF-04, F02→PF-05, F03→PF-06, F04→PF-03, F05→PF-07, F06→PF-08, F07→PF-09, F08→PF-10, F09→PF-11 |
| 首轮 DS open questions | 3/3 RESOLVED | 见 §0.2 |
| 首轮 MiMo F01-F04 disposition | 3 accepted + 1 rejected | F01→PF-01, F02→PF-02, F03 rejected, F04→PF-03 |
| 新 material findings | **0** | — |
| 新观察项 | 1 (低) | NEW-OBS-01: `_remove_manifest_items` 迁移未显式列出 |
| blocking questions | **0** | — |

### 8.2 Verdict

**PASS**

R07 fixed plan（SHA-256 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`）是 code-generation-ready。全部 12 组 Controller accepted fix 已真实关闭；fix 未引入新材料缺陷；identity descriptor、lock/recovery/maintenance、token breaking type/timing、snapshot fd-copy transient-vs-corruption、SEC filename selection、cache double-check/borrow/close、list-only source kind、9 tools recursive exposure、coverage/scans/smoke、three-slice allowlist 和 S3 final review vs umbrella aggregate gate 全部通过完整反例审查。首轮 DS findings F01-F09 及 open questions 已全部收敛。design-owner 裁决（source kind optional、禁止 batch snapshot/has_xbrl_instance/compat/deferred ISSUE/统一 authorization）全部遵守。

唯一新观察项 NEW-OBS-01（`_remove_manifest_items` 迁移未显式列出）不阻塞——pyright 会在 S1 step 5 删除 `_normalize_document_id` 后立即捕获遗漏。

### 8.3 Residual risk

| risk | severity | owner |
|---|---|---|
| `_remove_manifest_items` 的 `_normalize_document_id` 调用可能被遗漏 | 低（pyright 立即捕获） | S1 implementation agent |
| S1 后 `_published_ticker_directory_names` 返回类型语义变化可能影响未被 allowlist 覆盖的 indirect caller | 低（stop condition §11.3 覆盖） | S1 implementation agent |
| snapshot transient/sustained smoke tests 的 barrier 协调可能依赖 implementation 细节 | 低（§8.4 smoke 已约束） | S2 implementation agent |

### 8.4 Artifact path

`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-ds.md`

### 8.5 Immutable target

- **文件**: `docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`
- **SHA-256**: `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`
