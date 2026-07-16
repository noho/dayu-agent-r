# WU-SEMANTIC-OWNERSHIP-01 / R07 Fixed Plan Complete Re-Review — AgentMiMo

## 0. 元数据

- **review target**：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`
- **immutable SHA-256**：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`
- **review type**：complete re-review（非新 WU）
- **controller validation**：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-fix-controller-validation.md`（PASS / READY_FOR_DUAL_COMPLETE_REREVIEW）
- **AgentCodex fix artifact**：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-fix-codex.md`
- **design truth**：`docs/fins/design.md`
- **controller discussion**：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 6.3 / 6.7
- **review timestamp**：`20260716-121156`

## 1. 审查范围

完整阅读并逐项挑战：

- fixed plan 全文 §0—§13（789 行）
- Controller adjudication 12 个 accepted fix groups
- AgentCodex fix artifact（R07-PF-01..12 closure）
- Controller validation（PASS）
- `docs/fins/design.md` 稳定设计真源
- Controller discussion Topic 6.3（provenance/revision/citation/read errors）与 6.7（path containment + opaque ID mapping）
- 原两路完整 review（AgentMiMo: 4 findings; AgentDS: 9 findings）

重点验证：

1. R07-PF-01..12 是否真实关闭，fix 是否引入新矛盾
2. identity descriptor/lock/recovery/maintenance owner 是否唯一
3. token breaking type/timing 是否闭合
4. snapshot fd-copy transient-vs-corruption 优先级是否确定
5. SEC existing filename selection 是否冻结
6. cache double-check/borrow/close 是否完整
7. list-only source kind 是否正确
8. 9 tools completed/failed/cancelled recursive exposure 是否覆盖
9. coverage/scans/smoke 是否闭合
10. three-slice allowlist 是否精确
11. S3 final review vs umbrella aggregate gate 是否既不重复也不遗漏

## 2. R07-PF-01..12 Closure 验证

### R07-PF-01 — coverage metric — **CLOSED**

**验证**：fixed plan §8.1 lines 595—603 明确改为 `covered_lines / num_statements` 复算逐文件 line coverage，禁止 `summary.percent_covered` 替代 line gate。`coverage run --branch` 仅收集诊断数据，composite/branch 指标必须另名。

**证据**：§8.1 line 597 Python 检查 `p["files"][f]["summary"]["covered_lines"]/p["files"][f]["summary"]["num_statements"]`；line 602 明确 "不能使用开启 branch collection 后会计入 branch 分母的 `summary.percent_covered` 充当 line gate"。

**反例**：无。门禁命令与 R06 completion controller validation §4 口径一致。

---

### R07-PF-02 — S3 F401 — **CLOSED**

**验证**：fixed plan §7.3 lines 494—496 精确点名删除 `QueryDiagnosis` 与 `SEARCH_MODE_AUTO` 两个 unused imports，禁止扩大清理其它 legacy Ruff 项。

**证据**：line 496 "这里的范围精确限定为删除 `QueryDiagnosis` 与 `SEARCH_MODE_AUTO` 两个已记录的 unused imports"。

**反例**：无。§1 baseline 已给出精确位置（`:62` 和 `:64`）。

---

### R07-PF-03 — digest→token breaking rename — **CLOSED**

**验证**：fixed plan 在 §2（line 88）、§5.2（lines 236—241）、§7.2（lines 428—429、454）、§8.3（lines 663—671）四处同步关闭。

**关键内容**：
- §2：`SourceDocumentRevision` 只能表达 opaque equality token，字段从 `digest` 改为 `token`，只接受非空字符串，不承诺 SHA grammar
- §5.2.1：S2 一次性 `digest→token`，不校验/承诺 `sha256:` 或任何其它 grammar
- §5.2.6：S2 删除 consumer field-hash producer、`sha256:` grammar、排序/hash tests
- §7.2 step 1：明确 S2 修改 `__post_init__` 为仅拒绝空字符串
- §7.2 step 2：S2 过渡 checkpoint 的 `get_source_revision` 只机械构造 `SourceDocumentRevision(token=...)`
- §8.3：增加 `.digest` / SHA grammar 残留 scan

**证据**：§7.2 lines 428—429 "把 `SourceDocumentRevision.digest` breaking rename 为 `SourceDocumentRevision.token`；`__post_init__` / owner validation 只拒绝空字符串"。

**反例**：无。S2 时序已明确：`__post_init__` 在 S2 放宽，`get_source_revision` 机械读 persisted token，S3 删除该 method。无字段别名、compat property、双字段或 SHA-shaped 兼容值。

**原 DS F-R07-DS-04 关闭确认**：fixed plan §7.2 step 1 明确 "S2 修改 `SourceDocumentRevision.__post_init__` 为仅拒绝空字符串和非字符串类型，不再校验 `sha256:` 前缀和 hex 长度"，消除了原 review 的两难问题。

---

### R07-PF-04 — lock-only company inventory — **CLOSED**

**验证**：fixed plan 在 §5.1.6（line 230）、§7.1 step 2（line 341）、targeted test（line 383）三处同步关闭。

**关键内容**：
- §5.1.6：`_published_ticker_directory_names` 的 lock stem 只发现 private candidate key；business ticker 只从 target/backup descriptor 恢复
- §7.1 step 2：显式迁移 `_published_ticker_directory_names`，lock-only 无 descriptor 时沿用既有 typed malformed/recovery category 且 business ticker 缺失
- targeted test：`test_lock_only_company_inventory_has_no_business_ticker_or_internal_key`

**证据**：§7.1 line 341 "显式迁移 `_published_ticker_directory_names`：lock stem 只发现 private candidate key，business ticker 只从已验证 target/backup descriptor 恢复"。

**反例**：无。不允许新增状态名（如 `recovery_pending`），不投影 key/stem。

**原 DS F-R07-DS-01 关闭确认**：fixed plan 明确列出 `_published_ticker_directory_names` 的迁移步骤，覆盖了原 review 的高严重度 finding。

---

### R07-PF-05 — maintenance cleanup — **CLOSED**

**验证**：fixed plan 在 §7.1 step 4（line 343）、targeted test（line 384）两处同步关闭。

**关键内容**：
- §7.1 step 4：`cleanup_stale_filing_documents` 必须先从每个 child descriptor 恢复 exact external document id，再对该 external id 执行既有 `fil_` 业务分类与 valid-id 比较
- targeted test：`test_stale_filing_cleanup_uses_descriptor_external_id_in_opaque_layout`

**证据**：line 343 "`cleanup_stale_filing_documents` 必须先从每个 child descriptor 恢复 exact external document id，再对该 external id 执行既有 `fil_` 业务分类与 valid-id 比较，private child key 的 prefix/value 不参与业务判断"。

**反例**：无。`fil_` 前缀过滤和 `child.name` 比较都改为 descriptor-derived external id。

**原 DS F-R07-DS-02 关闭确认**：fixed plan 明确迁移步骤，消除了原 review 的 `fil_` 前缀失效风险。

---

### R07-PF-06 — fd-copy corruption priority — **CLOSED**

**验证**：fixed plan 在 §5.3（lines 257—260）、targeted test（line 462）、§8.4 item 4（line 689）三处同步关闭。

**关键内容**：
- §5.3 step 3：只有 revision/descriptor 真实变化才重取 attempt
- §5.3 step 4：revision/descriptor 未变时，inode 内容、`fstat`、EOF、declared size/hash 异常立即按 corruption/validation fail closed，不伪装 `source_changed_during_read`
- targeted test：`test_snapshot_fd_copy_silent_mutation_is_corruption_without_revision_change`
- §8.4 item 4：真实 fd-copy 静默修改验证

**证据**：§5.3 line 259 "若 post-copy 核对证明 revision/descriptor 未变，则已打开 inode 内容变化、copy 前后 `fstat` 变化、真实 EOF 与 declared size/hash 不匹配都不可能是 R06 publication guard + atomic rename 允许的 publication race；立即沿既有 corruption/validation 边界 fail closed"。

**反例**：无。优先级已确定：revision/descriptor 未变 → 静态 corruption → 立即 fail closed。

**原 DS F-R07-DS-03 关闭确认**：fixed plan 消除了原 review 的 fstat+revision 分类模糊性。

---

### R07-PF-07 — SEC fiscal frozen — **CLOSED**

**验证**：fixed plan 在 §0.2（line 29）、§5.4（line 267）、§7.2 step 5（line 432）三处同步关闭。

**关键内容**：
- §0.2：不改变 SEC fiscal 的既有 filename/suffix/XML fallback 文件选择语义，不引入 `has_xbrl_instance` 内容嗅探分类
- §5.4：`_build_download_local_file_map` 仍按 snapshot descriptor 的 exact business filename 建立 lowercase map，`_pick_download_xbrl_file` 仍沿用既有排序/suffix/XML fallback 排除规则
- §7.2 step 5：唯一变化是 temp paths 同源于一份 full snapshot

**证据**：§5.4 line 267 "`_pick_download_xbrl_file` 仍沿用既有排序、suffix 优先级与 XML fallback 排除规则来选择 instance/schema/linkbase。唯一变化是 map 中的全部 temp paths 来自同一 full snapshot"。

**反例**：无。明确禁止 `has_xbrl_instance` 新分类/schema。

**原 DS F-R07-DS-05 关闭确认**：fixed plan 冻结了文件选择语义，消除了原 review 的契约缺失问题。

---

### R07-PF-08 — cache double-check — **CLOSED**

**验证**：fixed plan 在 §5.5.1（line 273）、§7.3（lines 519、530）、targeted test（line 552）、§8.4 item 5（line 690）四处同步关闭。

**关键内容**：
- §5.5.1：同 document creation lock 内 double-check matching cached entry；已有 entry 时 losing 调用 close 自己的 full snapshot 并借 existing entry
- §7.3 step 2：creation lock 内 double-check
- targeted test：`test_concurrent_initial_cache_miss_builds_one_processor_and_closes_losing_snapshot`
- §8.4 item 5：同 revision initial cache miss 并发测试

**证据**：§5.5.1 line 273 "锁内必须再次检查 matching cached entry。若并发调用已经发布可借的 matching entry，当前调用幂等 close 自己取得的 full snapshot 并借 existing entry"。

**反例**：无。double-check 模式明确，losing snapshot close 已验证。

**原 DS F-R07-DS-06 关闭确认**：fixed plan 明确了 creation lock 内的 double-check 行为，消除了原 review 的 processor 重复构建风险。

---

### R07-PF-09 — recursive exposure — **CLOSED**

**验证**：fixed plan 在 §3.7（line 203）、§8.3（line 680）两处同步关闭。

**关键内容**：
- §3.7：9 个 read tool completed/failed/cancelled JSON recursive scan 必须证明没有 `revision`、`storage_key`、private key、absolute temp path 或 `local://`
- §8.3：明确覆盖 9 个 read tools 的 completed、failed、cancelled 及各自 citation 路径，递归遍历全部 nested JSON key/value

**证据**：§8.3 line 680 "新增 recursive result test 必须逐一覆盖 9 个 read tools 的 completed、failed、cancelled 以及各自 citation 路径，对运行时 JSON 全部 nested key 与 value 递归遍历，禁止 revision/private key/absolute temp path/`local://` 泄露"。

**反例**：无。不能只 grep 源码，必须做运行时 JSON recursive scan。

**原 DS F-R07-DS-07 关闭确认**：fixed plan 明确了运行时 JSON recursive scan 覆盖范围。

---

### R07-PF-10 — delete/reset snapshot — **CLOSED**

**验证**：fixed plan 在 §5.2.4（line 239）、S2 targeted test（line 457）两处同步关闭。

**关键内容**：
- §5.2.4：source delete/reset 后 source、token 与 snapshot resource 同时不存在，后续 snapshot read 明确抛 `FileNotFoundError`
- S2 targeted test：`test_snapshot_is_not_found_and_has_no_token_or_resource_after_source_delete_or_reset`

**证据**：line 239 "source delete/reset 后 source、token 与 snapshot resource 同时不存在，后续 snapshot read 明确抛 `FileNotFoundError`"。

**反例**：无。S2 storage-owner test 与 S3 cache retirement test 保持独立。

**原 DS F-R07-DS-08 关闭确认**：fixed plan 增加了 S2 targeted test，消除了原 review 的 delete/reset 测试缺口。

---

### R07-PF-11 — list-only source kind — **CLOSED**

**验证**：fixed plan 在 §0.2（line 28）、§5.5.3（line 275）、§7.3（lines 520—521）、targeted test（line 572）四处同步关闭。

**关键内容**：
- §0.2：不新增 batch snapshot/list snapshot API
- §5.5.3：`list_documents` 继续组合 filing/material 两个 `list_source_document_ids` typed list projections，不做 per-document snapshot
- §7.3：禁止 N+1、batch snapshot API 与 filing-first guess
- targeted test：`test_list_documents_uses_two_typed_storage_lists_without_per_document_snapshot`

**证据**：§5.5.3 line 275 "`list_documents` 只对 storage-owned `list_source_document_ids` 分别做 filing/material 两个 typed list projection 并组合业务列表；不得对每个 document 调用 snapshot 形成 N+1"。

**反例**：无。list 路径不使用 per-document snapshot，单 document read 才使用 0/1/2 typed resolution。

**原 DS F-R07-DS-09 关闭确认**：fixed plan 明确了 list-only 路径使用 storage list projection，消除了原 review 的 N+1 风险。

---

### R07-PF-12 — S3 final review gate — **CLOSED**

**验证**：fixed plan §10.2（lines 724—726）。

**关键内容**：
- S3 cumulative review 是 R07 完整树唯一一次双路 final code review
- finding fix、Controller validation、双路 complete re-review 后直接 adjudication/accepted implementation commit
- 不再安排等价 R07-only aggregate deepreview
- 跨 R01—R12 umbrella aggregate deepreview 仍保留在所有 remediation sub-WU 完成之后

**证据**：line 724 "S3 cumulative review 就是 R07 完整树唯一一次双路 final code review。其 finding fix、Controller validation 与双路 complete re-review 通过后，直接进入 Controller adjudication 与 accepted implementation commit，不再重复安排等价的 R07-only aggregate deepreview"。

**反例**：无。gate 既不重复也不遗漏。

---

## 3. Fix 引入的新缺陷检查

### 3.1 identity descriptor/lock/recovery/maintenance

**检查项**：S1 迁移是否覆盖所有 12 个 namespace/layout。

**验证**：fixed plan §3.2 的 12 行表格逐一覆盖 target、company meta/inventory、writer/publication locks、batch staging、backup/orphan recovery、filing/material source、source blob/object key、processed、rejection registry、rejected artifacts、maintenance cleanup、manifests/complete validator。每个 namespace 的 S1 disposition 均已明确。

**结论**：无新缺陷。descriptor 是唯一 round-trip 真源，lock stem 只发现 candidate key，recovery 由 journal/backup 内 descriptor 交叉验证。

---

### 3.2 token breaking type/timing

**检查项**：S2 的 `digest→token` breaking rename 时序是否自洽。

**验证**：
- S2 step 1：修改 `SourceDocumentRevision.__post_init__` 为仅拒绝空字符串
- S2 step 1：删除 `sha256:` grammar、selected-field hash builder
- S2 step 2：`get_source_revision` 机械读 persisted token 并构造 `SourceDocumentRevision(token=...)`
- S3 step 5：删除 `get_source_revision` method

**时序分析**：S2 放宽 `__post_init__` → S2 生成新 opaque token → S2 的 `get_source_revision` 机械读取 → S3 删除 method。无矛盾。

**结论**：无新缺陷。breaking rename 在 S2 一次完成，无字段别名、compat property 或 SHA-shaped 兼容值。

---

### 3.3 snapshot fd-copy transient-vs-corruption

**检查项**：§5.3 算法步骤 2—4 的优先级是否确定。

**验证**：
- step 2：释放 guard 后从 fd 复制到 temp，记录 EOF、size/sha256、fstat 稳定性
- step 3：短 guard 内核对 revision/descriptor
- step 4：revision/descriptor 未变 → 立即 corruption fail closed；revision/descriptor 变化 → 重取 attempt

**优先级**：revision/descriptor 变化是唯一合法重取条件。其它异常（inode 内容、fstat、EOF、size/hash）在 revision 未变时立即 fail closed。

**结论**：无新缺陷。优先级已确定，无模糊性。

---

### 3.4 SEC existing filename selection

**检查项**：`_build_download_local_file_map` 和 `_pick_download_xbrl_file` 是否冻结。

**验证**：
- §5.4：仍按 snapshot descriptor 的 exact business filename 建立 lowercase map
- §5.4：`_pick_download_xbrl_file` 仍沿用既有排序、suffix 优先级与 XML fallback 排除规则
- §0.2：明确禁止 `has_xbrl_instance` 内容嗅探分类或新文件分类 schema

**结论**：无新缺陷。文件选择语义完全冻结。

---

### 3.5 cache double-check/borrow/close

**检查项**：creation lock 内 double-check、borrow/retire/close 生命周期是否完整。

**验证**：
- §5.5.1：creation lock 内 double-check matching cached entry
- §5.5.2：cache hit 只在 lightweight snapshot revision/source kind 与 cached full snapshot 完全相等时成立
- §5.5.5：generic LRU 返回 displaced values 给 owner
- §5.5.6：replacement/eviction/clear/close 都必须最终释放 temp tree
- §5.5.10：`FinsReadRuntime.close()` 幂等 retire/clear cache

**结论**：无新缺陷。borrow/retire/close 状态机完整，closed 不可逆。

---

### 3.6 list-only source kind

**检查项**：`list_documents` 是否避免 N+1 snapshot。

**验证**：
- §5.5.3：`list_documents` 继续组合 filing/material 两个 `list_source_document_ids` typed list projections
- §0.2：不新增 batch snapshot/list snapshot API
- §5.1：单 document read 的 `source_kind=None` 才使用 snapshot 的 0/1/2 typed resolution

**结论**：无新缺陷。list-only 路径使用 storage list projection，不使用 per-document snapshot。

---

### 3.7 9 tools completed/failed/cancelled recursive exposure

**检查项**：§8.3 的 LLM-facing scan 是否覆盖运行时 JSON。

**验证**：
- §3.7：明确 9 个 read tool 的 completed/failed/cancelled JSON recursive scan
- §8.3：新增 recursive result test 必须逐一覆盖 9 个 read tools 的 completed、failed、cancelled 及各自 citation 路径，递归遍历全部 nested JSON key/value
- §8.3：不能只 grep 源码，必须做运行时 JSON recursive scan

**结论**：无新缺陷。覆盖范围已明确。

---

### 3.8 coverage/scans/smoke

**检查项**：§8 的验证矩阵是否闭合。

**验证**：
- §8.1：逐文件 line coverage >= 80%（`covered_lines / num_statements`）
- §8.2：pyright 0 errors、scoped Ruff 0、full Ruff delta 控制、diff check
- §8.3：identity source scan、revision/snapshot consumer scan、LLM-facing scan
- §8.4：真实 filesystem concurrency smoke（A/B publication、transient recovery、sustained churn、static corruption、cache lifecycle、citation/result 同版、recovery/security）

**结论**：无新缺陷。验证矩阵完整。

---

### 3.9 three-slice allowlist

**检查项**：S1/S2/S3 的 exact production/test allowlist 是否精确。

**验证**：
- S1：9 production files + 4 test files
- S2 cumulative：15 production files + 5 test files
- S3 cumulative：19 production files + 8 test files + 2 README files

**每个 slice 的 producer-consumer 迁移顺序**：已明确列出。

**结论**：无新缺陷。allowlist 精确，迁移顺序合理。

---

### 3.10 S3 final review vs umbrella aggregate gate

**检查项**：R07 final code review 与 umbrella aggregate deepreview 是否既不重复也不遗漏。

**验证**：
- §10.2：S3 cumulative review 是 R07 唯一 complete-tree code review
- §10.2：不再安排 R07-only aggregate deepreview
- §10.2：跨 R01—R12 umbrella aggregate deepreview 仍保留在所有 remediation sub-WU 完成之后

**结论**：无新缺陷。gate 既不重复也不遗漏。

---

## 4. 旧 Finding Final Status

| finding | 来源 | final status | 说明 |
|---|---|---|---|
| `R07-PF-01` | MiMo F01 | **CLOSED** | coverage metric 已修正 |
| `R07-PF-02` | MiMo F02 | **CLOSED** | S3 F401 已点名 |
| `R07-PF-03` | MiMo F04 + DS F04 | **CLOSED** | digest→token breaking rename 已闭合 |
| `R07-PF-04` | DS F01 | **CLOSED** | lock-only inventory 已迁移 |
| `R07-PF-05` | DS F02 | **CLOSED** | maintenance cleanup 已迁移 |
| `R07-PF-06` | DS F03 | **CLOSED** | fd-copy corruption 优先级已确定 |
| `R07-PF-07` | DS F05 | **CLOSED** | SEC fiscal 文件选择已冻结 |
| `R07-PF-08` | DS F06 | **CLOSED** | cache double-check 已明确 |
| `R07-PF-09` | DS F07 | **CLOSED** | recursive exposure 已覆盖 |
| `R07-PF-10` | DS F08 | **CLOSED** | delete/reset snapshot 已有 targeted test |
| `R07-PF-11` | DS F09 | **CLOSED** | list-only source kind 已明确 |
| `R07-PF-12` | Controller direct | **CLOSED** | S3 final review gate 已修正 |

## 5. New Findings

### R07-RR-F01 — 未修复 — 低 — `read_source_snapshot` 的 `source_kind=None` 行为在原 MiMo review 中是 accepted candidate，但 Controller 已拒绝必填

- **位置**：§5.3 "source kind 缺省时由 storage 在同一 publication guard 内检查 filing/material 映射"
- **问题类型**：观察项（非 material finding）
- **当前写法**：`source_kind=None` 时 storage 在内部做 0/1/2 typed resolution
- **反例/失败场景**：无。Controller adjudication 已明确拒绝必填 `source_kind`，理由是 storage-owned typed resolution 符合唯一 owner
- **为什么不是问题**：Controller 裁决优先于 reviewer 建议。plan 的 optional typed 0/1/2 机制正确，不恢复 filing-first guess
- **直接证据**：Controller adjudication §4 "MiMo `R07-PR-F03` — rejected with design evidence"
- **影响**：无
- **建议改法和验证点**：无需修改
- **修复风险**：N/A
- **严重程度**：N/A（观察项，不计入 finding 统计）

---

## 6. 反例审查

### 6.1 identity descriptor 碰撞

**反例**：两个不同 external ticker 通过 deterministic key derivation 碰撞到同一 internal key。

**plan 防御**：§5.1.4 "collision 一律 fail closed"；§5.1.7 "blob-first 在写第一个文件前就创建/验证 document descriptor"；targeted test `test_identity_mapping_detects_collision_corruption_and_business_meta_mismatch`。

**结论**：碰撞检测在 payload 落盘前 fail closed，足够安全。

---

### 6.2 snapshot A/B 混版

**反例**：fd 持有期间 publication 切换到 B，导致 A/B 文件混版。

**plan 防御**：§5.3 算法 step 1 在 publication guard 内打开 fd → step 2 从 fd 复制（fd 仍指向旧 inode）→ step 3 核对 revision。R06 atomic rename 不影响已打开的 fd。

**结论**：A/B 不会混版。post-copy revision 核对决定返回 A 或重取 B。

---

### 6.3 cache retired processor 重用

**反例**：cache 返回已 retired/closed processor。

**plan 防御**：§5.5.2 "cache hit 只在 lightweight snapshot revision/source kind 与 cached full snapshot 完全相等时成立"；§5.5.5 "retire 后不再借出"；§5.5.6 "cache 不得持有已 close resource 或把 retired entry 重新提升 LRU"。

**结论**：retired entry 不会被重用。

---

### 6.4 citation/provenance 不同源

**反例**：citation 来自一个 snapshot revision，result 来自另一个。

**plan 防御**：§5.5.8 "citation 只接收 current borrowed snapshot，机械投影其 provenance"；§8.4 item 7 "在 processor result 与 citation 构造之间发布 B；当前 borrow 仍产出 A result + A provenance"。

**结论**：citation 和 result 来自同一 snapshot。

---

### 6.5 process target 资源泄漏

**反例**：`_FinsReadProcessTarget.__call__` 异常路径不释放 snapshot 资源。

**plan 防御**：§5.5.10 "`_FinsReadProcessTarget.__call__` 用 `finally` 覆盖 completed、typed failure、unexpected exception"。

**结论**：finally 覆盖所有路径，资源不会泄漏。

---

### 6.6 raw external id 参与 path join

**反例**：S1 后仍有 raw ticker/document id 参与 `Path / ticker`。

**plan 防御**：§11 stop condition 4 "任一 raw external ticker/document id 仍参与 path/object-key/lock/backup/staging join"；§8.3 identity source scan。

**结论**：stop condition 阻止实施继续。

---

## 7. 残余 Owner

| residual | owner / future gate | R07 disposition |
|---|---|---|
| financial/XBRL producer contract | R08 / Topic 6.4 | 不改 processor 业务结果 |
| direct-stream terminal validator | R09 / Topic 6.5 | 不改 ingestion terminal 语义 |
| HKEX cumulative discovery | R10 / Topic 6.6 | 不改 downloader |
| upload shell/cmd workflow | R11 / Topic 7.1/7.2 | 不改 CLI/packaging |
| current-schema init/secret/atomic reset | R12 / Topic 7.3 | 不改 init/runtime config |
| workspace migration/future assets | Issue 142/151 | fresh schema，不迁移 |
| Fins long-operation process isolation | Issue 175 | 只关闭 read process target snapshot 资源 |
| output continuation/TruncationManager | Issue 177 | 不接通 |
| credential storage-state lifecycle | Issue 178 | 不触碰 |
| unified tool authorization | 无当前授权 | 不创建新 WU/framework |
| private key/revision 算法未来演进 | storage owner | 只要 descriptor round-trip/opaque equality contract 不变即可 |

---

## 8. Verdict

**PASS**。

R07 fixed plan 是 code-generation-ready 的完整 remediation plan。R07-PF-01..12 全部真实关闭，fix 未引入新矛盾。identity descriptor/lock/recovery/maintenance owner 唯一；token breaking type/timing 闭合；snapshot fd-copy transient-vs-corruption 优先级确定；SEC existing filename selection 冻结；cache double-check/borrow/close 完整；list-only source kind 正确；9 tools completed/failed/cancelled recursive exposure 覆盖；coverage/scans/smoke 闭合；three-slice allowlist 精确；S3 final review vs umbrella aggregate gate 既不重复也不遗漏。

12 个旧 finding 全部 CLOSED。1 个新观察项（source_kind optional 行为）不计入 finding 统计。0 blocking questions。

**旧 finding 总数**：12（全部 CLOSED）
**新 finding 总数**：0（1 个观察项不计入）
**blocking questions**：0
**verdict**：PASS
**immutable SHA-256**：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`
**artifact path**：`docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-rereview-mimo.md`
