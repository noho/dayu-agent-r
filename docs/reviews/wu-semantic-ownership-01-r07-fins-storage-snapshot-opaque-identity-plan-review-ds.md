# WU-SEMANTIC-OWNERSHIP-01 / R07 Plan Review — AgentDS 第二路完整 adversarial review

## 0. 元数据

- **review target**: immutable plan `docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`
- **target SHA-256**: `ae8d74f8a9a7fd677face4211cb7402bdc5e56eb6c80bfe8cb1791a4e46a7bc7`
- **transition base**: `5f09e2cc2e4edfc7dc1388e14744bf1300637093`
- **R06 completion**: `f1c56ea90c587314cc7cba35e5b4c790d13d2fc3`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-r07-plan-entry-controller-validation.md` (PASS / READY_FOR_DUAL_PLAN_REVIEW)
- **reviewer**: AgentDS（第二路）
- **timestamp**: 2026-07-16T11:44:57+08:00
- **裁决优先级**: Controller discussion Topic 6.3/6.7 与 `docs/fins/design.md` > umbrella §14 > 本 plan

## 1. 审查范围

完整阅读并逐项挑战:

- 本 immutable plan 全文（§0—§13）
- Controller entry validation
- `docs/fins/design.md` 稳定设计真源
- umbrella remediation plan 全局及 §14 R07 节
- Controller discussion Topic 6.3（provenance/revision/citation/read errors）与 6.7（path containment + opaque ID mapping）
- R06 completion evidence（`f1c56ea9` accepted implementation `4f417e91`）
- 当前 production code（下列文件全文或关键段）:
  - `dayu/fins/storage/_fs_storage_utils.py`（115+ normalizer 命中，含 `_normalize_ticker`、`_normalize_document_id`、`_list_directory_names`）
  - `dayu/fins/storage/_fs_storage_infra.py`（`_parse_backup_directory_name`、lock locator、journal/recovery contract）
  - `dayu/fins/storage/_fs_source_document_core.py`（1456 行；`_build_source_revision`、`_build_source_revision_file_payload`、`_prepare_complete_source_meta`）
  - `dayu/fins/storage/_fs_company_meta_core.py`（`_published_ticker_directory_names`、`scan_company_meta_inventory` 用 `directory_name` 暴露 identity）
  - `dayu/fins/storage/_fs_maintenance_core.py`（`cleanup_stale_filing_documents` 用 `child.name` + `fil_` 前缀做业务判断）
  - `dayu/fins/storage/repository_protocols.py`（`get_source_revision`、`get_source_meta`、`get_primary_source`、`get_source_document_provenance` 等当前 public surface）
  - `dayu/fins/domain/document_models.py`（`SourceDocumentRevision` 固化 `sha256:<64 hex>` grammar、`CompanyMetaInventoryEntry` 暴露 `directory_name`）
  - `dayu/fins/tools/read_runtime.py`（双 revision-before/after 路径、`_resolve_source_kind` filing-first probing、cross-document diagnosis 独立 revision read）
  - `dayu/fins/tools/cache.py`（`ProcessorLRUCache.put/evict/clear` 静默丢弃 displaced values）
  - `dayu/fins/README.md`（承诺 consumer field-hash revision、document_id 单路径组件）
  - `tests/README.md`（当前 tests/fins 描述）
- 当前测试文件 `tests/fins/test_fins_storage_provider.py`（4498 行）、`test_fins_storage_atomicity.py`（3043 行）、`test_fins_ingestion_runtime.py`（4697 行）、`test_sec_pipeline_download.py`（3382 行）

## 2. Assumptions tested

| # | assumption | 压力测试方法 | 结果 |
|---|---|---|---|
| A1 | descriptor + deterministic locator 是唯一最小 mapping truth | 遍历 plan §3.2 全部 12 个 namespace/layout，检查每个是否需额外 identity bookkeeping | PASS — 但有两个边界遗漏（见 F-R07-DS-01、F-R07-DS-02） |
| A2 | fd-copy + post-copy revision check 在 R06 rename 模型下排除 A/B mixed | 对照 R06 atomic swap 语义 (two-rename window + publication guard)，检查 plan §5.3 算法步骤 1-5 | PASS — 算法正确隔离 fd 持有期与 post-copy revision 核对，但 budget 耗尽后的 typed error 分类需要更精确的区分机制（见 F-R07-DS-03） |
| A3 | 三个 slice 顺序与原子性可实施 | 逐一检查每个 slice 的输入/输出契约、handoff contract 及禁止项 | PASS — 但 S2 的 "persisted revision 暂时只读但不 field-hash" checkpoint 存在模糊性（见 F-R07-DS-04） |
| A4 | preprocess/SEC/6-K consumers 迁移后不丢失现有正确性 | 检查 plan §5.4 的三个 consumer 迁移描述与实际调用图 | PASS — 但 `sec_fiscal_fields._build_download_local_file_map` 的逐文件物化改为单 snapshot 后 XBRL instance/schema/linkbase 文件选择语义需明确（见 F-R07-DS-05） |
| A5 | cache lifecycle 改造不引入 use-after-close | 对照当前 `ProcessorLRUCache` put/evict/clear 语义与 plan §5.5 的 borrow/retire/close 模型 | PASS — 但 `creation_lock` 的 serialization 范围与 LRU 条目级别的互斥粒度不一致（见 F-R07-DS-06） |
| A6 | README/LLM scan 不泄露 internal key/revision/path | 检查 plan §8.3 的 scan 命令覆盖面和 §5.1.8 的 filename/URI 边界 | PASS — 但 plan 缺少对 `_CachedProcessor`/`_CachedSourceDocumentMeta` 内部字段（当前持有 `source_kind`/revision）在 tool result JSON 中的泄露检查（见 F-R07-DS-07） |
| A7 | revision 只随有效 source publication 变化 | 对照 plan §5.2 规则 2-4 与当前 `_prepare_complete_source_meta` 的三条调用路径 | PASS — 但 `delete/reset` 后 snapshot 不存在的语义需要显式测试覆盖（plan §5.2.4 提到但 §7.2 targeted tests 未单独列出 delete 场景）（见 F-R07-DS-08） |

## 3. Material findings

---

### F-R07-DS-01 — 高 — `_published_ticker_directory_names` lock-stem 反推 ticker 在 S1 迁移规划中覆盖不足

- **位置**: plan §3.2 row "writer / publication locks" + §7.1 S1 exact production allowlist
- **问题类型**: 状态机漏洞 / 契约缺失
- **当前写法**: plan §3.2 lock row 写 "lock 名只含 private ticker key；authority/state machine 不变"。plan §5.1.6 写 "lock-only inventory 先以 key 加 guard，再从恢复后的 target descriptor 取业务 identity，不能返回 lock stem。"
- **反例/失败场景**: 当前 `_published_ticker_directory_names()` (`_fs_company_meta_core.py:340-362`) 从 `portfolio_root` 扫描目录名 AND 从 `batch_lock_root` 扫描 `*.publication.lock` 文件，去掉后缀得到 ticker name。S1 迁移后，lock 文件名变为 private key，但 `_published_ticker_directory_names()` 仍会把这些 private key 当作 ticker name 返回给 `scan_company_meta_inventory`（line 102 调用），导致:
  1. 在 portfolio 目录为空但存在 publication lock 的情况下，private key 被当作 ticker name 进入 inventory entry 的 `directory_name` 字段
  2. `_normalize_ticker(private_key)` 可能通过 `try_normalize_ticker` 把 private key 误解析为合法 ticker
  3. plan §7.1 S1 的 exact production allowlist 包含 `_fs_company_meta_core.py` 但未在其 producer-consumer 迁移顺序中单独列出 lock-only inventory 的完整迁移步骤
- **为什么有问题**: `_published_ticker_directory_names` 是唯一一个跨 directory + lock 两个 namespace 聚合 ticker identity 的函数。plan §5.1.6 说明了"不能返回 lock stem"的原则，但 S1 的 6 步 producer-consumer 迁移顺序没有显式包含这个函数的改造。当前 `scan_company_meta_inventory` 依赖它来枚举 ticker，而 plan §3.2 company meta/inventory row 只说了"malformed entry 只给无 key 的 typed status"，没有明确说明 lock-only ticker 如何从 descriptor 恢复 identity。
- **直接证据**:
  - `_fs_company_meta_core.py:340-362` — `_published_ticker_directory_names()` 直接读 `lock_path.name[: -len(suffix)]` 作为 ticker name
  - `_fs_company_meta_core.py:102` — `scan_company_meta_inventory` 对每个 `directory_name` 调用 `_normalize_ticker(directory_name)`
  - plan §3.2 row "writer / publication locks": "lock 名只含 private ticker key" — 但未说明该函数如何从 lock-only key 恢复 business identity
- **影响**: 实施 Agent 在 S1 中可能保留 `_published_ticker_directory_names` 的 lock stem → ticker 路径，导致 S2/S3 review 发现时返工；更严重的是，lock-only inventory entry 可能把 private key 泄漏到 `CompanyMetaInventoryEntry.directory_name`
- **建议改法和验证点**:
  1. 在 plan §7.1 S1 producer-consumer 迁移顺序的 step 2（"ticker target/staging/backup/locks/recovery/company inventory 先切 key"）下显式列出 `_published_ticker_directory_names` 的迁移: lock 文件名只用于发现候选 key，business ticker 必须从 target descriptor（若 target 存在）或 backup descriptor 读取并验证
  2. lock-only entry（target 不存在但 lock 存在）必须有专门的 typed status（如 `recovery_pending`），其 `directory_name` 不得为 private key
  3. 新增 targeted test 覆盖 lock-only inventory 场景: `test_company_inventory_never_projects_internal_storage_key` 已列出但未明确覆盖 lock-only 路径
- **修复风险**: 低 — 只需在 S1 step 2 添加一个子步骤说明
- **严重程度**: 高

---

### F-R07-DS-02 — 高 — `cleanup_stale_filing_documents` 的 `fil_` 前缀与 `child.name` identity 比较在 S1 迁移后失效

- **位置**: plan §3.2 row "maintenance cleanup" + plan §7.1 S1 exact production/test allowlist
- **问题类型**: 契约缺失 / 状态机漏洞
- **当前写法**: plan §3.2 maintenance cleanup row 写 "先用 descriptor 恢复 external id，再应用已有 SEC 业务规则；internal key 不参与业务判断"。plan §7.1 S1 exact production allowlist 包含 `_fs_maintenance_core.py`。
- **反例/失败场景**: 当前 `_cleanup_stale_filing_documents_impl` (`_fs_maintenance_core.py:523-582`) 做两件事:
  1. `child.name.startswith("fil_")` (line 556) — 用 internal key 前缀判断是否 filing
  2. `child.name in normalized_valid_document_ids` (line 568) — 用 internal key 与 external document id 集合比较
  S1 迁移后 `child.name` 是 private key，既不以 `fil_` 开头，也不等于外部 `document_id`。`normalized_valid_document_ids` 当前通过 `_normalize_document_id(document_id)` 构造（line 547-549），S1 后这些变成 private key 的集合，但 `child.name` 也是 private key — 比较仍然正确。然而 `fil_` 前缀过滤会永远不匹配，导致所有 stale filing 都无法清理。
- **为什么有问题**: plan §3.2 row 描述了正确原则，但 §7.1 S1 的 6 步迁移顺序没有把 "maintenance cleanup 的 `fil_` 前缀判断与 `child.name` identity 比较改为 descriptor-based" 列为显式步骤。`_fs_maintenance_core.py` 在 S1 allowlist 中，但迁移顺序最后一步是"删除旧 normalizer"，maintenance 的改造细节被隐含在 "source filing/material 切 document key" 中，而没有单独列出 `cleanup_stale_filing_documents` 的具体迁移。
- **直接证据**:
  - `_fs_maintenance_core.py:556` — `if not child.is_dir() or not child.name.startswith("fil_"):`
  - `_fs_maintenance_core.py:568` — `if child.name in normalized_valid_document_ids:`
  - plan §3.2 row "maintenance cleanup": "先用 descriptor 恢复 external id，再应用已有 SEC 业务规则"
- **影响**: S1 实施后 `cleanup_stale_filing_documents` 静默失效（不清理任何文档），SEC 下载的窗口清理功能回归。如果实施 Agent 没有单独为这个函数写测试，可能到 full-suite 才暴露。
- **建议改法和验证点**:
  1. 在 plan §7.1 S1 step 3（source filing/material 切 document key）下显式添加子步骤: "`cleanup_stale_filing_documents` 改为先读 descriptor 恢复 external id 再应用 `fil_` 业务前缀与 form_type 过滤；`child.name` 与 `normalized_valid_document_ids` 的比较改为 descriptor-derived external id 比较"
  2. 新增 targeted test 覆盖 stale cleanup 在 opaque key 布局下正确删除过时 filing
- **修复风险**: 低
- **严重程度**: 高

---

### F-R07-DS-03 — 中 — fd-copy 后 `fstat` 变化但 revision 未变的 corruption 分类边界依赖实现细节

- **位置**: plan §5.3 算法步骤 2—4
- **问题类型**: 并发恢复风险
- **当前写法**: plan §5.3 step 2 写 "逐文件验证真实 EOF、declared size/sha256（字段存在时）与 copy 前后 `fstat` 稳定性"。step 3 写 "再在一次短 publication guard 内只核对同一 external identity 的 persisted revision/descriptor 仍与本 attempt 相同"。step 4 写 "若 revision 未变而 declared size/hash 持续不匹配，这是静态 storage corruption，立即以原有 corruption/validation 边界 fail closed，不伪装成 source changed。"
- **反例/失败场景**: step 2 的 `fstat` 稳定性检查发生在 publication guard 释放后。如果 copy 期间文件被 truncate 且 inode 复用（R06 rename 模型下不可能，但 plan 未声明此依赖），`fstat` 前后 st_dev/st_ino 相同但 st_size 变化 — step 2 检测到并标记该文件"有变化"。然后 step 3 检查 revision 未变。这是 transient 还是 corruption?
  - 如果文件被另一个 writer 通过非 publication 路径直接修改（违反 R06 contract，但 plan 没有防御性假设声明），这是 transient corruption
  - 如果文件系统静默损坏（bit rot），这是 static corruption
  - plan step 4 只说了 "revision 未变而 declared size/hash 持续不匹配" 的判断，但未定义"持续"的含义 — 单次 attempt 内看到 fstat 变化但 revision 未变，应该立即 fail closed（static corruption）还是重试（transient）？
- **为什么有问题**: 当前 plan 算法把"fstat 变化 → 重试"和"revision 未变 + 持续 mismatch → corruption"作为两个独立分支，但没有明确两者同时出现时的优先级。如果 fstat 变化但 revision 未变（在 R06 rename 模型下不可能，但作为 defensive code 没有显式处理），算法可能进入未定义行为。
- **直接证据**:
  - plan §5.3 step 2: "复制前后 `fstat` 稳定性" — 如果 fstat 不稳定，是否触发 attempt 重试？
  - plan §5.3 step 4: "若 revision 未变而 declared size/hash 持续不匹配" — "持续"的定义依赖于跨 attempt 观察
  - R06 保证一次 published read/`LocalFileSource.open()` 在 rename 窗口只见完整 old 或 new（plan §0.1.3），但 fd 持有跨 publication guard 的场景没有在 R06 中显式契约
- **影响**: 实施 Agent 可能在区分 transient/static corruption 时引入过度重试或过早 fail，导致本可恢复的场景被错误分类
- **建议改法和验证点**:
  1. 在 plan §5.3 step 2 中明确: fstat 变化且 revision 未变 → 立即 fail closed 为 static corruption（不重试），因为 R06 publication guard + atomic rename 模型下不存在"文件内容变但 revision 不变"的合法路径
  2. 在 §8.4 smoke 中增加一个 case: 模拟 copy 期间文件静默损坏（非 publication），验证立即 fail closed 为 typed corruption 而非 `source_changed_during_read`
- **修复风险**: 低
- **严重程度**: 中

---

### F-R07-DS-04 — 中 — S2 checkpoint 的 "persisted revision 暂时只读" 过渡状态与 `get_source_revision` 删除时序模糊

- **位置**: plan §7.2 S2 producer-consumer 迁移顺序 step 2 + S2 handoff contract
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: plan §7.2 step 2 写 "S2 checkpoint 中 `get_source_revision` 暂时只读 persisted 字段，绝不重算，保证未迁移 read runtime 仍 type-correct"。S2 handoff contract 写 "S2 结束时允许旧 read runtime 仍机械调用 persisted `get_source_revision`，但不允许任何 field hash；这个 checkpoint 不可 commit/accept。S3 必须删除该旧 method。"
- **反例/失败场景**: 当前 `SourceDocumentRevision` (`document_models.py:289-318`) 固化 `sha256:<64 hex>` grammar。S2 把 revision 改为 storage-owned opaque token 后:
  1. 新 persisted token 可能不是 `sha256:` 格式 — `SourceDocumentRevision.__post_init__` 会拒绝
  2. 如果 plan 意图在 S2 改 `SourceDocumentRevision` 为 opaque equality（收窄 grammar），则 step 2 的 "暂时只读 persisted 字段" 意味着 `get_source_revision` 仍返回 `SourceDocumentRevision(digest=...)` 但 digest 不再是 SHA-256 — 与 `__post_init__` 的 validation 冲突
  3. 如果 plan 意图在 S2 保留 `sha256:<64 hex>` 格式（即用 SHA-256 作为 opaque token），则与 §5.2.1 "不校验/承诺 SHA grammar" 矛盾
- **为什么有问题**: plan §5.2.1 说 `SourceDocumentRevision` 只做 opaque equality 不校验 SHA grammar，§7.2 step 1 说 "收窄为 opaque equality"，但 §7.2 step 2 又说 `get_source_revision` 暂时只读 persisted 字段。这三个描述对应的 `SourceDocumentRevision.__post_init__` 行为不同:
  - 如果 `__post_init__` 在 S2 就删除 SHA 校验 → `get_source_revision` 返回 opaque digest，对旧 read runtime type-correct
  - 如果 `__post_init__` 保留到 S3 → S2 的 persisted token 必须是 `sha256:<64 hex>`，违反 §5.2.1
- **直接证据**:
  - `document_models.py:298-318` — `SourceDocumentRevision.__post_init__` 硬编码 `sha256:<64 hex>` 校验
  - plan §5.2.1: "`SourceDocumentRevision` 只做 opaque equality，不校验/承诺 SHA grammar"
  - plan §5.2.6: "S2 过渡 checkpoint 内既有 `get_source_revision` 只可机械读 persisted token 以保持 full pyright"
  - plan §7.2 step 1: "把 `SourceDocumentRevision` 收窄为 opaque equality"
- **影响**: 实施 Agent 在 S2 面临两难: 要么在 S2 就改 `__post_init__`（与 "S3 删除 method" 时序一致），要么用 SHA-256 作为 opaque token（与 §5.2.1 矛盾）。需要明确 S2 的 `__post_init__` 行为
- **建议改法和验证点**:
  1. 在 plan §7.2 step 1 中明确: S2 修改 `SourceDocumentRevision.__post_init__` 为仅拒绝空字符串和非字符串类型，不再校验 `sha256:` 前缀和 hex 长度
  2. S2 step 2 中 `get_source_revision` 机械读 persisted token（新格式），通过放宽后的 `__post_init__` 校验
  3. 在 S2 targeted tests 中增加: `test_source_document_revision_accepts_opaque_token_rejects_empty`
- **修复风险**: 低
- **严重程度**: 中

---

### F-R07-DS-05 — 中 — `sec_fiscal_fields._build_download_local_file_map` 改为单 snapshot 后 XBRL 同组文件选择语义未定义

- **位置**: plan §3.4 item 5 + plan §5.4 bullet 2 + plan §7.2 S2 step 5
- **问题类型**: 契约缺失
- **当前写法**: plan §3.4 item 5 写 "`sec_fiscal_fields._build_download_local_file_map`：对 meta files 逐个 `get_source(...).materialize()`，XBRL instance/schema/linkbase 可跨版本。" plan §5.4 bullet 2 写 "`sec_fiscal_fields` 对一个 source document 只取得一份 full snapshot，再从其 named sources 选择 instance/schema/linkbase；函数结束/异常时 close。不得逐文件重新读 repository。"
- **反例/失败场景**: 当前 `_build_download_local_file_map` 对 meta files 逐个 materialize。如果这些 materialize 调用发生在 publication 之间，XBRL instance、schema、linkbase 可能来自不同 publication 版本。plan 正确识别这个问题。但 plan §5.4 bullet 2 只说"从其 named sources 选择 instance/schema/linkbase"，没有定义"选择"语义:
  1. snapshot 的 `named sources` 是什么？是指 snapshot descriptor 中的 file descriptors 列表吗？
  2. 如何从 file descriptors 中识别哪些是 XBRL instance、哪些是 schema、哪些是 linkbase？当前依赖 `has_xbrl_instance` 和文件扩展名 — 这些逻辑在哪里执行？
  3. 如果 snapshot 中有多个 `.xsd` 或 `.xml` 文件，"选择"算法是什么？
- **为什么有问题**: plan 正确识别了逐文件 materialize 的跨版本风险，但将"选择 instance/schema/linkbase"的语义推给了 `sec_fiscal_fields` 的既有逻辑。如果该逻辑依赖多次 repository read（如通过 `get_source` 检查文件内容判断是否为 XBRL instance），则 plan 需要在 snapshot API 层面提供文件类型识别能力，或明确该逻辑在 snapshot 层面如何工作。
- **直接证据**:
  - `_fs_source_document_core.py:38` — import `has_xbrl_instance`
  - plan §5.4 bullet 2 — "再从其 named sources 选择 instance/schema/linkbase"
  - plan §3.4 item 5 — "XBRL instance/schema/linkbase 可跨版本"（识别问题但未给出文件选择 contract）
- **影响**: 实施 Agent 可能需要在 `sec_fiscal_fields` 内实现文件类型嗅探逻辑（读取 snapshot temp tree 中的文件内容判断 XBRL 类型），这可能超出 plan 的 scope 边界
- **建议改法和验证点**:
  1. 在 plan §5.4 bullet 2 中明确: snapshot 提供有序 file descriptors 列表（含 filename），`sec_fiscal_fields` 通过 filename 扩展名（`.xml`/`.xsd`）和 `has_xbrl_instance` 内容检查选择文件；内容检查通过读取 snapshot temp tree 中的文件完成，不重新访问 repository
  2. 或者: 确认 `sec_fiscal_fields` 不需要修改（plan §4 说 "不改 `sec_fiscal_fields.py` 的 fiscal 推断算法"），只需将逐文件 materialize 替换为从 snapshot 获取 temp paths — 如果是这样，需要在 plan 中显式确认
- **修复风险**: 低（只是澄清）
- **严重程度**: 中

---

### F-R07-DS-06 — 低 — `creation_lock` + LRU 条目级互斥的粒度不一致可能导致 processor 重复构建

- **位置**: plan §5.5.2 + plan §7.3 S3 step 2
- **问题类型**: 并发恢复风险
- **当前写法**: plan §5.5.2 写 "cache hit 只在 lightweight snapshot revision/source kind 与 cached full snapshot 完全相等时成立；之后获得一个 private active borrow。" plan §7.3 S3 step 1 写 "generic LRU 先改为向 owner 返回 displaced values；不内置 close 猜测。" plan §7.3 S3 状态/失败/并发/cleanup 写 "creation lock 只序列化同 document cache build；不持有 publication guard 执行 processor。"
- **反例/失败场景**: 当前 `FinsReadRuntime._get_creation_lock` (`read_runtime.py:2719-2738`) 使用 `ProcessorCacheKey(ticker, document_id)` (source_kind=None) 作为 lock key。S3 后:
  1. 线程 A lightweight snapshot 命中 cache miss，获取 creation lock，取 full snapshot，构建 processor — 但还未 put 进 cache
  2. 线程 B lightweight snapshot 也命中 cache miss（因为 A 还没 put），等待 creation lock
  3. A 释放 lock，B 获取 lock，再次取 full snapshot 并构建 processor — 但此时 A 已 put 进 cache
  4. B 在 put 前应检查 cache 是否已有 entry（double-check），但 plan 未描述此行为
  5. 如果 B 不做 double-check，会重复构建 processor 并覆盖 cache entry，且 B 的 full snapshot temp tree 泄漏
- **为什么有问题**: plan §7.3 S3 step 2 写 "read runtime 建立 private cached entry/borrow retire 状态与幂等 close"，但没有提到 creation lock 内的 double-check 模式。当前 read runtime 的 `_get_creation_lock` 是纯粹锁获取，double-check 逻辑在锁外（processor build 路径约 2558-2614 行）。plan 没有说明 lock 持有者是否应在 put 前检查 cache。
- **直接证据**:
  - `read_runtime.py:2719-2738` — `_get_creation_lock` 只返回 `Lock`，不包含 double-check 逻辑
  - plan §7.3 S3 step 2 — "read runtime 建立 private cached entry/borrow retire 状态与幂等 close"（未提 creation lock double-check）
  - plan §7.3 状态/失败/并发/cleanup — "creation lock 只序列化同 document cache build"（正确但不够）
- **影响**: 低概率下（高并发 read + cache miss race）出现重复 processor 构建和 snapshot temp tree 泄漏
- **建议改法和验证点**:
  1. 在 plan §7.3 S3 step 2 中或 §7.3 状态/失败/并发/cleanup 中添加: "creation lock 内做 double-check: 获取锁后再次检查 cache 是否已有 matching entry，有则使用已有 entry 的 borrow 并 close 自己的 full snapshot"
  2. 新增 targeted test: `test_concurrent_reads_after_revision_change_build_one_processor` 已覆盖，但需确保它也覆盖同一 revision 下的并发 cache miss 场景
- **修复风险**: 低
- **严重程度**: 低

---

### F-R07-DS-07 — 低 — 缺少对 tool result JSON 中 internal state 字段的 recursive scan

- **位置**: plan §8.3 LLM-facing scan
- **问题类型**: 测试缺口
- **当前写法**: plan §8.3 LLM-facing scan 使用 `rg` 搜索 `source_revision`、`storage_key`、`internal_key`、`local://` 等在源码中的出现。plan §3.7 写 "最终 9 个 read tool completed/failed/cancelled JSON recursive scan 必须证明没有 `revision`、`storage_key`、private key、absolute temp path 或 `local://`。"
- **反例/失败场景**: 当前 `_CachedProcessor` 持有 `source_kind` 和 `revision`（`read_runtime.py:204/219`）。如果 processor 构建失败时，异常消息中包含这些字段名，可能通过 error projection 进入 tool result JSON。`rg` 源码搜索可以找到源码中的字段名，但无法检测运行时 JSON 输出。plan §3.7 提到了 "recursive scan" 但 §8.3 的 scan 命令只做源码 grep，没有运行时 JSON recursive scan 的具体命令。
- **为什么有问题**: 字段名 `revision`、`source_kind` 在源码中合法出现（internal code），但不应出现在 tool result JSON 中。源码 grep 不足以证明运行时 JSON 不泄露这些字段。
- **直接证据**:
  - `read_runtime.py:204` — `_CachedProcessor.revision: SourceDocumentRevision`
  - plan §3.7 — "最终 9 个 read tool completed/failed/cancelled JSON recursive scan"
  - plan §8.3 — LLM-facing scan 只有 `rg` 命令，没有运行时 JSON recursive scan 命令
- **影响**: tool result JSON 可能意外包含 `revision` key（例如通过 dataclass asdict 或 serialization bug），源码 grep 无法检测
- **建议改法和验证点**:
  1. 在 plan §8.3 LLM-facing scan 中增加运行时 scan: 对 9 个 read tools 执行 success/failure/cancellation 路径，序列化 result JSON，递归遍历所有 key 验证不含 `revision`、`storage_key`、`internal_key`、`local://` 和绝对路径
  2. 在 S3 targeted tests 中增加 `test_read_outputs_never_expose_revision_internal_key_local_uri_or_temp_path`（已列出），但需明确这个测试必须做 recursive JSON key 遍历而非只 grep 源码
- **修复风险**: 低
- **严重程度**: 低

---

### F-R07-DS-08 — 低 — source delete/reset 后 snapshot 不存在的行为缺少 targeted test

- **位置**: plan §5.2.4 + plan §7.2 targeted pytest nodes
- **问题类型**: 测试缺口
- **当前写法**: plan §5.2.4 写 "source reset 使 source 及 token 一起不存在"。plan §7.2 targeted pytest nodes 包含 `test_published_revision_is_persisted_and_changes_only_with_source_publication` 和 `test_rollback_and_non_source_batch_preserve_published_revision`，但没有专门覆盖 delete/reset 后 read snapshot 的行为。
- **反例/失败场景**: source delete 后:
  1. `read_source_snapshot(ticker, document_id)` → 应 raise `FileNotFoundError`
  2. 如果 cache 中仍有该 document 的 cached entry → 应在 lightweight snapshot 阶段检测到并 evict
  3. plan §7.2 targeted tests 覆盖了 revision 的 create/update/non-source preservation，但没有覆盖 delete/reset → snapshot not found → cache eviction 的完整路径
- **为什么有问题**: plan §5.5.6 提到 "source delete" 必须触发 cache cleanup，§5.2.4 提到 "source reset 使 source 及 token 一起不存在"，但 §7.2 的 targeted tests 没有对应的 delete 场景覆盖。S3 的 `test_cached_processor_is_not_returned_after_source_deleted` 覆盖了 cache 端，但 storage 端的 delete → snapshot not found 行为没有被 S2 test 覆盖。
- **直接证据**:
  - plan §5.2.4: "source reset 使 source 及 token 一起不存在"
  - plan §7.2 targeted pytest nodes — 无 delete/reset 后 read snapshot 的 test
  - plan §7.3 targeted nodes — `test_cached_processor_is_not_returned_after_source_deleted` (cache side only)
- **影响**: delete 后 snapshot read 的 typed error 可能未经测试验证
- **建议改法和验证点**:
  1. 在 plan §7.2 targeted pytest nodes 中增加: `test_snapshot_not_found_after_source_delete_and_reset`
  2. 或者: 在 S3 `test_cached_processor_is_not_returned_after_source_deleted` 中明确包含 storage snapshot not found 的 upstream 行为
- **修复风险**: 低
- **严重程度**: 低

---

### F-R07-DS-09 — 低 — `read_runtime.py` 中 `source_kind` probing 删除后 `list_documents` 的来源类型展示逻辑未定义

- **位置**: plan §5.5.3 + plan §7.3 S3 step 4
- **问题类型**: 契约缺失
- **当前写法**: plan §5.5.3 写 "删除独立 source meta cache；form type、source kind、provenance/citation 都从当前 borrow 的 full snapshot 取得。list-only 路径可用 lightweight snapshot/现有 storage list projection，但不能把 list meta 与 processor citation 拼成同一 document read。"
- **反例/失败场景**: `list_documents` 工具当前通过 `list_source_document_ids` 返回文档列表，其中包含 `source_kind` 信息（filing/material）。plan §5.5.3 说 list-only 路径可用 lightweight snapshot/现有 storage list projection。但 plan §5.1 的 snapshot API `read_source_snapshot` 需要 `source_kind=None` 时由 storage 解析 — 如果 list_documents 返回 100 个文档，对每个文档都调用 `read_source_snapshot`（即使 lightweight）会是 N+1 查询。
- **为什么有问题**: plan 没有定义批量 list 场景下的 source kind 解析策略。当前 `_resolve_source_kind` 对单个文档先 filing 后 material probing；S3 删除 probing 后，list 路径需要一种批量解析方法（如 storage 提供 `list_documents_with_kinds`），但 plan 的 snapshot API 是 per-document 的。
- **直接证据**:
  - plan §5.5.3 — "list-only 路径可用 lightweight snapshot/现有 storage list projection"
  - plan §5.1 snapshot API — `read_source_snapshot(ticker, document_id, source_kind=None, *, materialize_files: bool)` 是 per-document
  - `repository_protocols.py:472` — `list_source_document_ids(ticker, source_kind)` 按 source kind 分别列出 — 两种 kind 各调一次
- **影响**: list_documents 的 source_kind 解析可能变慢（N+1），或者需要 storage 提供新的批量接口
- **建议改法和验证点**:
  1. 在 plan §5.5.3 中明确: `list_documents` 路径是否继续使用 `list_source_document_ids` 分别查询 filing 和 material（两个 lightweight list 调用，而非 N 个 per-document snapshot）
  2. 或者: 在 plan §5.1 中增加批量 snapshot descriptor API `list_source_snapshots(ticker)` 返回 `(document_id, source_kind, revision)` 列表
  3. 当前 plan 的现有 storage list projection 已支持按 source_kind 分别 list，无需修改 — 但需要显式确认 plan 意图
- **修复风险**: 低（只需澄清）
- **严重程度**: 低

---

## 4. Mandatory focus area 逐项结论

### 4.1 descriptor + deterministic locator 是否唯一最小 truth

**覆盖度检查**: plan §3.2 的 12 个 namespace/layout row 覆盖了 target、staging、backup、locks、recovery、company、source（filing+material）、processed、rejected（registry+artifacts）、blob/object key、manifests、maintenance cleanup。逐一核验:

| namespace | 当前 raw identity pattern | plan disposition | 审查结论 |
|---|---|---|---|
| ticker target | `portfolio/<normalized ticker>` | `portfolio/<private ticker key>` + descriptor | PASS |
| company meta/inventory | `meta.json.ticker == directory name`; lock stem → ticker | key → descriptor → business ticker; malformed entry typed status | **F-R07-DS-01**: lock-only inventory 迁移细节不够 |
| writer/publication locks | `<normalized ticker>.lock` / `.publication.lock` | private key + descriptor | PASS（原则正确） |
| batch staging | `<transaction>/<normalized ticker>` | private key + descriptor; journal ticker 是 exact external identity | PASS |
| backup/orphan recovery | `<ticker>.bak.<transaction>`; parse backup name → ticker | private key + transaction; ticker 从 journal/descriptor 交叉验证 | PASS（原则正确，需确认 backup 内 descriptor 的写入时机） |
| filing/material source | `filings\|materials/<normalized document_id>` | private key + descriptor; manifest/meta external id 双向校验 | PASS |
| source blob/object key | `ticker/source-kind/document-id/filename` raw join; `local://<raw>` | private key + safe filename; URI 是 internal locator | PASS |
| processed | `processed/<normalized document_id>`; child.name → document id | descriptor + private key; external id 双向校验 | PASS |
| rejection registry | dict key 经 path-component normalizer | JSON key = exact external id; typed entry 严格相等 | PASS |
| rejected artifacts | `.rejections/<normalized document_id>`; child.name → document id | descriptor + private key; external id 双向校验 | PASS |
| maintenance cleanup | `fil_` prefix + child.name identity compare | descriptor → external id → 业务规则 | **F-R07-DS-02**: `fil_` 前缀与 `child.name` 比较的迁移细节不够 |
| manifests/complete validator | directory name、meta、manifest 三者相等 | directory key ↔ descriptor key; external id、meta、manifest 三者一致 | PASS |

**反例**: 除了 F-R07-DS-01 和 F-R07-DS-02，未发现其他 namespace 遗漏。

### 4.2 snapshot API public surface 是否冻结不必要细节

- `materialize_files: bool` 是直接布尔参数，符合朴素接口原则。PASS。
- `source_kind=None` 时 storage 解析: 0 个 → `FileNotFoundError`；1 个 → typed kind；2 个 → storage invariant failure。plan 明确禁止 read runtime 的 filing-first probing。PASS。
- snapshot resource 的类名保持 private，不进包根/README/tool/LLM。PASS。
- **潜在问题**: 当前 protocol `get_source_meta`、`get_primary_source`、`get_source`、`get_source_revision`、`get_source_document_provenance` 是 5 个独立方法。S3 后它们被一个 `read_source_snapshot` 取代。但 `fs_source_document_repository.py`（wrapper）和 protocol 中的旧方法签名需要在 S3 删除。plan §7.2 step 2 说 S2 checkpoint 保留 `get_source_revision` "暂时只读" 以保证 type-correct — 这意味着 S2 新增 snapshot 方法但不删除旧方法。到 S3 step 5 才从 protocol/wrapper/core 删除。这个两阶段过渡是合理的。PASS。

### 4.3 fd-copy + post-copy revision check 的 A/B 混版排除

分析 plan §5.3 算法 5 个步骤:

1. publication guard 内读 identity/meta/provenance/revision/file list + 打开全部 fd — **fd 持有期在 guard 内**，R06 atomic rename 保证此时看到的文件属于同一 publication
2. 释放 guard 后从 fd 复制到 temp — **fd 已持有，即使 publication 切换到 B，fd 仍指向旧 inode**（R06 rename 不影响已打开的 fd）
3. 短 guard 内核对 revision/descriptor — 若 revision 未变，copy 一致；若 revision 变化，当前 attempt 的 fd 指向旧版，新版在下次 attempt 获取
4. budget 有界重试
5. budget 耗尽 → typed consistency error

**结论**: 在 R06 atomic rename + fd 持有模型下，A/B 不会混版。step 2 的逐文件验证（EOF、declared size/sha256、fstat 稳定性）进一步防御文件 corruption。PASS，但 F-R07-DS-03 的 fstat+revision 分类需澄清。

### 4.4 preprocess writer mutex、SEC fiscal/6-K consumers、read cache lifecycle cleanup

- **preprocess writer mutex**: plan §5.4 bullet 1 写 "begin 发生在 snapshot 前，保证 staging source 与 snapshot 同一 published revision"。但 plan 未说明如果 begin batch 成功但 snapshot 失败时是否 rollback batch。当前 `ingestion_runtime.py` 的 preprocess 路径持有 batch 并在异常时 rollback — plan §5.4 写 "异常/取消在 commit 前 close snapshot 并 exactly-once rollback"，确认了这一点。PASS。
- **SEC fiscal consumer**: F-R07-DS-05 覆盖。
- **6-K consumer**: plan §5.4 bullet 3 写 "caller-owned batch 已持 writer mutex 的前提下取得一份 full snapshot"。确认 snapshot 在 writer mutex 保护下，因此不会看到并发 publication。PASS。
- **cache lifecycle**: F-R07-DS-06 覆盖。plan §5.5.1-10 的 borrow/retire/close 模型是完整的。PASS。

### 4.5 revision 变化边界

对照 plan §5.2:

| 事件 | revision 行为 | 审查 |
|---|---|---|
| source create/update/replace | 新 token 生成 | PASS |
| source delete | token 随 source 一起不存在 | PASS（但缺 targeted test — F-R07-DS-08） |
| source restore | 新 token（因为是新 complete-source publication） | PASS |
| rollback/precommit crash | 不改变 published token | PASS |
| processed/company/rejection-only batch | 复制保留 source token | PASS |
| non-source mutation | 不生成新 token | PASS |

**反例**: 未发现歧义。唯一风险是 F-R07-DS-04（`__post_init__` 时序）。

### 4.6 coverage 命令与 branch percent、累计 allowlist、full-suite inherited ledger

逐一核验 plan §8.1 的 coverage 命令:

- plan §8.1 的 `coverage run --branch` + `coverage json` + Python assertion 检查逐文件 `percent_covered >= 80%`。这是正确的逐文件 line coverage 检查，没有用 aggregate 平均数。PASS。
- plan §8.2 的 inherited failure ledger（§1.1）只允许三个已知节点，且要求相同指纹。PASS。
- plan §8.2 的 full Ruff fingerprint 从 152 → S3 后 ≤150，且 `F401<=70, E402<=66, F841<=10, F541<=3, F821<=1`。PASS。
- S1/S2 不允许超过 base 152 或增加任何 rule/node。PASS。

**潜在问题**: plan 使用 `coverage json` 的 `percent_covered`。这通常是 line coverage percentage，不是 branch coverage。plan §8.1 的 `coverage run --branch` 启用了 branch coverage，但 `percent_covered` 在 `coverage json` 输出中对应 `summary.percent_covered`，默认是 line coverage。如果要 branch coverage，需要检查 `"summary"` 中的 `"branch_covered"` / `"num_branches"` 或使用 `--show-missing` 格式。不过 plan 最终目标是 "line coverage >= 80%"（plan §8.1），所以使用 `percent_covered`（line coverage）是正确的。`--branch` flag 只是同时收集 branch data 作为额外诊断。PASS。

### 4.7 LLM-facing 不泄露 internal key/revision/path

- plan §3.7 确认了当前 tool schema/result/citation 不输出 revision/internal key/local URI
- plan §8.3 LLM-facing scan 命令覆盖了 `source_revision`、`storage_key`、`internal_key`、`local://` 等关键词
- plan §8.3 明确 "新增 recursive result test 必须对 9 个 read tools 的 success/failure/citation dict 遍历 key/value"
- F-R07-DS-07 覆盖了运行时 JSON recursive scan 的缺失

**总体**: PASS（F-R07-DS-07 是补充性建议）

## 5. 遗漏检查: raw identity path join、revision double-read consumer、裸 published Path、provider guess

| 遗漏类别 | scan 结果 |
|---|---|
| raw identity path join 残留 | plan §8.3 identity source scan 的三组 `rg` 命令覆盖了 `_normalize_ticker/document_id`、`portfolio.*ticker`、`filings.*document_id`、`directory_name`、`lock_path.stem`、`child.name` 等全部已知 pattern。PASS |
| revision double-read consumer 残留 | plan §8.3 revision/snapshot consumer scan 覆盖了 `get_source_revision`、`_build_source_revision`、`revision_before/after`、`sha256:` 等。最终期望第一组为 0。PASS |
| 裸 published Path 残留 | plan §8.3 的 `.materialize(` scan 期望 pipeline raw repository source materialize 为 0，processor 内 materialize 仍允许但 source 必须来自 snapshot。PASS |
| provider guess 残留 | plan §8.3 的 `_resolve_source_kind` scan 期望 read runtime filing-first probe 为 0。PASS |
| source kind ambiguity | plan §5.3 明确当 source kind 缺省时由 storage 在 publication guard 内检查，0 个 → `FileNotFoundError`，1 个 → typed kind，2 个 → storage invariant failure。这取代了 `_resolve_source_kind` 的 filing-first implicit preference。PASS |
| `materialize_files` 参数 | plan §5.3 写 "直接布尔参数，不使用 factory/profile/query bag"。PASS |
| 裸 published `Path` | plan §5.3 写 "任何 `materialize()` 都只能返回 temp path，不得返回 published path"。PASS |

## 6. S1—S3 顺序与原子性总评

| slice | 输入 | 输出 | handoff contract | 审查 |
|---|---|---|---|---|
| S1 | R06 fresh layout + exact external ids | 所有 physical locator 只含 private key；public API round-trip external identity | S2 不可再发现 raw identity path join | **F-R07-DS-01, F-R07-DS-02** 需补充 |
| S2 | S1 mapping + R06 publication guard | persisted revision + stable snapshot + non-read consumers 迁移 | S3 消费 snapshot；允许旧 `get_source_revision` 机械读 | **F-R07-DS-04, F-R07-DS-05** 需澄清 |
| S3 | S2 snapshot + typed consistency error | 全部 consumer 只见 snapshot；旧 double-read/hash/path/provider 零残留 | R07 complete tree 可进入 accepted commit 裁决 | **F-R07-DS-06, F-R07-DS-07** 补充性 |

三个 slice 的依赖链正确：S1 必须先完成（否则 S2 的 snapshot API 需要处理两种 locator），S2 必须先完成（否则 S3 的 cache 仍需兼容 field-hash revision）。PASS。

## 7. Security retained / modified matrix 核验

逐一核验 plan §6 的 13 个安全机制:

| 机制 | plan disposition | 审查 |
|---|---|---|
| external id 拒绝 separator | 有意修改为 exact round-trip | PASS — 正确 owner 转移 |
| filename/entry name 拒绝 | 保留 | PASS |
| local URI/object key 拒绝 | 保留并收紧 owner | PASS |
| path containment | 保留 | PASS |
| symlink rejection | 保留并扩展至 descriptor/snapshot | PASS |
| atomic JSON/file write | 保留并复用至 identity descriptor | PASS |
| R06 writer mutex | 保留，lock locator 改用 internal key | PASS — two external ids 不碰撞待验证 |
| R06 publication guard | 保留 | PASS |
| journal/recovery | 保留状态机，修改 locator | PASS |
| complete-source validator | 扩展加入 identity descriptor + revision invariant | PASS |
| typed provenance/citation | 保留并同源 | PASS |
| typed read errors | 保留，仅 consistency exhaustion 映射既有 code | PASS |
| tool/Host authorization | 不触碰 | PASS |

**反例**: 无。所有 retained 机制都有对应的验证计划。

**特别关注 — two external ids 不碰撞**: plan §5.1.3 写 descriptor 记录 namespace + exact external identity。如果两个不同 external id 因 deterministic key derivation 碰撞到同一 internal key → collision failure。这要求 key derivation 算法有足够 collision resistance。plan 没有指定算法，但碰撞检测（"blob-first 在写第一个文件前就创建/验证 document descriptor，因此碰撞在任何 payload 落盘前 fail closed"）是足够的。PASS。

## 8. Residual owners 边界检查

plan §12 的 10 个 residual 逐项核验:

- R08/R09/R10/R11/R12: 明确不实施，owner 归属正确。PASS。
- Issue 142/151/175/177/178: 明确不实施，归于各自 issue owner。PASS。
- unified tool authorization: 明确不创建。PASS。
- base full-suite Service 配置/import/logging failures: §1.1 ledger 只允许防止扩散。PASS。
- private key/revision 算法未来演进: 只要 descriptor round-trip/opaque equality contract 不变即可。PASS。

**反例**: 无。

## 9. Phaseflow gate 顺序核验

plan §10 的 gate 顺序:

```
plan gate (§10.1): artifact-only → Controller validation → MiMo+DS 双路 review → Codex fix → Controller verify → MiMo+DS re-review → Controller adjudication → accepted-plan commit
implementation gate (§10.2): S1→S2→S3 逐 slice: handoff → Controller scope/targeted/coverage/pyright/Ruff/diff/scans/smoke → MiMo+DS cumulative review → fix → Controller verify → re-review
S1/S2 不得有 accepted commit; S3 完整树通过后 aggregate validation → 双路 deepreview → fix/re-review → Controller adjudication → accepted implementation commit
R07 completion commit (§10.2): completion/final validation artifacts + control transition
```

对照 AGENTS.md 与 umbrella plan §7.3:
- AGENTS.md 不需要遵循特定 phaseflow gate 顺序 — phaseflow 是项目的 gateflow skill 约定
- umbrella plan §1.3 要求每个 sub-WU 独立完成 plan/review/fix/re-review/accepted-plan-commit 与 implementation/review/fix/re-review/accepted-sub-WU-commit
- plan §10 的 gate 顺序与 umbrella 要求一致

PASS。

## 10. Open questions

1. **Q-R07-DS-01**: S2 中 `_build_source_revision` 的删除时机。plan §5.2.6 说 "S2 过渡 checkpoint 内既有 `get_source_revision` 只可机械读 persisted token" — 是否意味着 `_build_source_revision`（私有函数）也在 S2 删除？还是保留到 S3？建议明确。
2. **Q-R07-DS-02**: plan §5.1.7 说 "blob-first 在写第一个文件前就创建/验证 document descriptor" — 当前 blob 写入路径（`_fs_blob_core.py`）不使用 document descriptor。S1 的 descriptor 创建时机是否需要在 blob 写入前？如果是，blob core 需要感知 identity mapping owner。建议在 S1 step 3 中明确 blob 写入与 descriptor 创建的时序。
3. **Q-R07-DS-03**: plan §5.5.7 说 "cross-document diagnosis 若检查 cached candidate，先取该 candidate lightweight snapshot 并按 revision 验证" — 当前 cross-document diagnosis (`read_runtime.py:2503`) 使用独立 `get_source_revision`。S3 后，如果 candidate 不在 cache 中（从未被读过），lightweight snapshot 是否也足够（不需要 full snapshot + processor）？建议明确 cross-document diagnosis 的 lightweight/full snapshot 选择逻辑。

## 11. Residual risks and suggested tracking

| 风险 | 建议追踪 |
|---|---|
| 两个不同 external identity 通过 deterministic key derivation 碰撞 | R07 implementation 的 collision test（plan 已列出 `test_identity_mapping_detects_collision_corruption_and_business_meta_mismatch`） |
| `_fs_identity.py` 的 key derivation 算法被 consumer 间接依赖（如通过 backup directory name 格式） | S1 review 重点检查是否有 consumer 断言 key format |
| R06 writer mutex 改用 internal key 后，两个不同 external ticker 的 lock 文件不会冲突，但 `try_normalize_ticker` 的 alias 归一仍在 storage 外（`dayu/fins/ticker_normalization.py`），可能导致同一 business ticker 的两个 alias 获得两个不同 internal key | plan §5.1.1 写 "storage 不再重复拥有该业务规则" — 上游 ticker resolver 必须保证同一 business entity 使用同一 exact external ticker。这是正确的 owner 分离，但需在 R07 closeout 中显式说明此依赖 |
| `cleanup_stale_filing_documents` 的 `fil_` 前缀判断改为 descriptor-based 后，性能可能下降（需要读每个 child 的 descriptor） | S1 implementation 的性能评估 |

## 12. Final verdict

**Verdict: PASS-WITH-FINDINGS**

计划整体是 code-generation-ready。motivation 由 115+ normalizer 的 direct code evidence、consumer field-hash revision、double-read pattern、directory-name identity leakage、filing-first probing 等 7 个当前代码事实充分支持。semantic owner 裁决正确（storage 拥有 identity mapping、published revision、snapshot；consumer 只消费）。三个 slice 的依赖链正确，S1→S2→S3 的 handoff contract 闭合。

9 个 findings 中:
- **2 个高严重度** (F-R07-DS-01, F-R07-DS-02): `_published_ticker_directory_names` 的 lock-stem 反推和 `cleanup_stale_filing_documents` 的 `fil_` 前缀/`child.name` 比较的 S1 迁移细节不足。不阻塞 plan acceptance，但必须在 plan fix 中补充显式迁移子步骤，否则 S1 implementation 可能遗漏。
- **3 个中严重度** (F-R07-DS-03, F-R07-DS-04, F-R07-DS-05): fstat/revision 分类边界、`__post_init__` 时序、SEC fiscal 文件选择语义需要澄清。不阻塞 plan acceptance，但建议在 plan fix 中明确。
- **4 个低严重度** (F-R07-DS-06, F-R07-DS-07, F-R07-DS-08, F-R07-DS-09): 补充性改进，不阻塞。

**必须阻塞 implementation 的条件**: 无。所有 findings 都是 plan 文本层面的澄清/补充，不需要重新设计。

**Finding 总计**: 9（2 高 + 3 中 + 4 低），0 blocking questions。

**Artifact path**: `docs/reviews/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan-review-ds.md`
