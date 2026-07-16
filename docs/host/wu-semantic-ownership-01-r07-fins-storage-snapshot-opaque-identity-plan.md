# WU-SEMANTIC-OWNERSHIP-01 / R07 Fins storage snapshot 与 opaque identity remediation plan

## 0. Gate 身份、基线与结论

- **所属工作单元**：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`。
- **内部 sub-WU**：`R07`，只覆盖 Controller discussion Topic 6.3 / 6.7；不是新 WU。
- **当前 gate**：R07 plan finding fix已完成，等待Controller validation。本文仍未accepted，不授权implementation、control修改、stage、commit、push或PR。
- **R06 accepted completion commit**：`f1c56ea90c587314cc7cba35e5b4c790d13d2fc3`（`docs: complete R06 Fins transaction remediation`）。
- **R07 transition base / 当前审计 HEAD**：`5f09e2cc2e4edfc7dc1388e14744bf1300637093`（`docs: enter R07 Fins snapshot remediation plan`）。`f1c56ea9..5f09e2cc` 只有 control 文档变化，product、tests、README 与 R06 accepted implementation 一致。
- **裁决优先级**：Controller discussion Topic 6.3 / 6.7 与 `docs/fins/design.md` stable design truth > 当前 umbrella 的候选实现与候选 allowlist > 历史 artifact。若后续实现需要改变这个优先级中的 owner 决策，立即 stop 并回 Controller。
- **本计划写入边界**：plan fix gate只更新本文并新增对应fix artifact；不修改product、tests、README、design、control或旧artifact。

### 0.1 第一性原理结论

问题真实存在，严重性没有被高估，也没有 blocker：

1. **opaque identity 与路径组件不是同一语义。** 当前 storage 先把 ticker 业务归一，再把 ticker/document id 当作目录名、锁名、backup 名和 object key。它因此拒绝 `/`、`\\`、`.`、`..`、drive-like 与绝对样式字符串，并让目录名反向承担业务 identity。安全 containment 是必要的，但用“拒绝业务 identity”实现 containment 是 owner 错位；正确 owner 是 storage 内的持久化映射。
2. **内容字段 hash 不是 publication revision。** 当前 `_build_source_revision(...)` 由 consumer 需要的选定 meta/file 字段重算 SHA-256。它既冻结了字段选择，又把 storage 已经拥有的 R06 complete publication 事实交给 read consumer 间接推断。正确 revision 必须在 source publication owner 写入完整 source 时产生、随 batch commit 一次发布，consumer 只能读取 opaque 值。
3. **单次 guarded read/open 不等于一致 snapshot。** R06 已保证一次 published read/`LocalFileSource.open()` 在 rename 窗口只见完整 old 或 new；但 read runtime 仍分开读取 source kind、revision、meta、primary source 与 provenance，processor 仍可长期持有指向 published tree 的裸 `Path`。这些调用可跨 A/B publication，citation 也可来自另一版本。
4. **consumer double-read 不是正确修复。** `read_runtime.py` 现在做 `revision_before -> meta/source/processor -> revision_after`，变化即零重试失败；cross-document diagnosis 又单独读 revision。它没有形成 storage snapshot，只把 race 检测、字段 hash 与失败策略分散给 consumer。
5. **最小正确边界**：storage 唯一拥有 external opaque identity ↔ internal key 映射、published revision、完整 snapshot 的构造/验证/有界稳定读取；read/cache/processor/citation 只消费 storage snapshot。R06 writer mutex、complete-source validator 与 publication guard 是该边界的直接基础，不另造 transaction framework。

### 0.2 明确非目标

- 不实施 R08—R12：不改 financial/XBRL producer contract、Fins direct-stream terminal validator、HKEX cumulative discovery、CLI upload script/placeholder surface 或 CLI init。
- 不实施 Issue 142、151、175、177、178；不做 workspace migration、future assets、Fins long-operation process isolation、完整 TruncationManager 或 credential storage-state lifecycle。
- 不创建 speculative `BusinessSource`、第二套 provenance、第二套 citation 或统一 tool authorization。
- 不新增 batch snapshot/list snapshot API；list-only consumer 继续组合 storage 已有的 filing/material 两个 typed list projection。
- 不改变 SEC fiscal 的既有 filename/suffix/XML fallback 文件选择语义，也不引入 `has_xbrl_instance` 内容嗅探分类或新文件分类 schema。
- 不改变九个 Fins read tool 的业务 schema、tool name、参数、结果字段或 Host/Engine contract。
- 不削弱现有局部 filename、local URI、containment、symlink、atomic write/fsync、transaction/recovery、typed provenance/citation/read error 机制。
- fresh schema：不读取旧 `portfolio/<raw ticker>/.../<raw document_id>` 布局，不迁移旧库，不兼容旧 revision/hash，不提供 fallback、re-export、wrapper、test shim 或双写。

## 1. 当前 base 的可复现基线

所有命令均在仓库根目录执行；Python 命令先 `source .venv/bin/activate`。

| 类别 | 命令 | `5f09e2cc` 结果 |
|---|---|---|
| HEAD / 历史 | `git rev-parse HEAD`；`git show -s --format='%H %s' f1c56ea9 5f09e2cc` | HEAD 精确为 `5f09e2cc2e4edfc7dc1388e14744bf1300637093`；R06 completion 精确为 `f1c56ea90c587314cc7cba35e5b4c790d13d2fc3` |
| 初始 scope | `git status --short`；`git diff --check` | 初始 clean；diff check pass |
| R07 owner/consumer 核心测试 | `pytest -q tests/fins/test_fins_storage_provider.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_processor_read_consistency.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_financial_read_contracts.py` | `297 passed, 3 warnings in 9.24s` |
| 新增 allowlist refinement 的既有节点 | `pytest -q tests/fins/test_fins_ingestion_runtime.py::test_start_preprocess_allows_slash_in_document_ids tests/fins/test_fins_ingestion_runtime.py::test_start_preprocess_processes_source_document_to_processed_repository tests/fins/test_fins_ingestion_runtime.py::test_start_preprocess_missing_document_fails_terminal_record tests/fins/test_sec_pipeline_download.py::test_sec_pipeline_download_prefers_dei_fiscal_when_available tests/fins/test_sec_pipeline_download.py::test_standalone_6k_reconcile_publishes_source_and_processed_together` | `5 passed, 3 warnings in 0.90s` |
| full pyright | `pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff | `ruff check` 加本文 §8 的当前 proposed Python allowlist | 仅 `dayu/fins/tools/read_runtime.py:62` unused `QueryDiagnosis` 与 `:64` unused `SEARCH_MODE_AUTO`，共 `2 F401` |
| full Ruff fingerprint | `ruff check dayu tests utils --statistics` | `152`：`F401=72, E402=66, F841=10, F541=3, F821=1` |
| README 正式全量目录命令 | `pytest tests/contracts tests/cli tests/documents tests/fins tests/tools tests/host tests/runtime tests/service tests/engine -q` | `4821 passed, 3 failed, 3 skipped, 5 deselected, 3 warnings in 103.98s`；见 §1.1 inherited ledger |
| 裸 pytest 环境观察 | `pytest -q` | collection error：ignored `workspace/tmp/r06-base-9c07b88d/tests/conftest.py` 与正式 `tests/conftest.py` 形成 `ImportPathMismatchError`；R07 不删除、不修改该外部临时树 |

R06 completion artifact 的 accepted evidence 仍成立：accepted implementation `4f417e91`，R07 handoff `f1c56ea9`；R06 affected aggregate 为 `732 passed, 1 skipped, 3 warnings`、pyright 0、38 个 changed production file line coverage 全部 `>=80%`、accepted finding `9 closed / 0 open / 0 blocker`。本文不把历史数字冒充当前重跑结果。

### 1.1 inherited failure ledger

R07 最终 full-suite gate 只允许下列 base 指纹保持不变；它们不授权顺手修复：

| node | rule / error type | stable location | base text fingerprint | 隔离复核 |
|---|---|---|---|---|
| `tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default` | order-dependent `AssertionError` | `tests/runtime/test_log.py:101` | root logger 存在一个 Dayu marker `StreamHandler` | 与下面两个节点一起单跑时该节点通过；若最终全量仍出现，只允许相同 handler 指纹，新增/不同 handler 立即 stop |
| `tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets` | `ConfigFieldError` | `dayu/runtime/config_loader.py:2303` | `missing required fields: ['wait_poller_policy']` | 单跑仍失败 |
| `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers` | `AssertionError` | `tests/service/test_import_boundary.py:101` | 仅 `dayu.service.fins_wait_adapter` / `host_assembly` 导入 `dayu.fins.tools._ingestion_tool_helpers` 两项 | 单跑仍失败 |

基线复核命令：

```bash
pytest -q \
  tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default \
  tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets \
  tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers
```

最终若 R07 targeted tests、pyright 或任何 changed-owner test 失败，不得登记为 inherited；full suite 出现新 node、新 error type/rule、新 stable location 或新 text fingerprint 也立即 stop。

## 2. Semantic owner 与 contract 裁决

| 语义 | 唯一 owner | consumer 只允许做什么 | 明确禁止 |
|---|---|---|---|
| external ticker/document identity | caller/domain 产生业务值；storage identity mapping 持久化并定位 | 原样传递、比较业务值 | consumer/path adapter 大小写、strip、basename、split、replace、quote 或路径推断 |
| external identity ↔ internal storage key | `dayu.fins.storage` 私有 identity mapping owner | 通过 repository API 查找/枚举 | 直接 `Path / ticker`、`Path / document_id`；从目录/锁/backup 名反推业务 identity |
| internal key grammar | storage 私有实现 | 无 | 测试/README/schema/LLM 断言 prefix、字符集、长度、hash 或可解析结构 |
| source published revision | complete-source mutation/publication owner | 读取并按 opaque equality 比较 | producer 传入；consumer 选择字段 hash；README 承诺 grammar |
| revision publication point | `_prepare_complete_source_meta(...)` 或同 owner-boundary 等价 helper，随 R06 batch commit 可见 | 无 | processed/company/maintenance mutation 改 source revision；commit 后补写 revision |
| source snapshot descriptor/content/provenance | source storage repository | 取得 snapshot，按 snapshot 内的 typed 字段构建 processor/citation/result | 分开读 meta/source/provenance/revision；裸 Path 延迟指向 published tree |
| snapshot 稳定性与有界重取 | storage snapshot implementation | 捕获 storage typed failure | consumer before/after double-read、consumer retry、message parsing |
| `source_changed_during_read` LLM-facing code/文案 | `dayu/fins/tools/error_contract.py` 的 `ErrorCode` + read error projection | read runtime 仅把 storage 的专用 typed consistency exhaustion 映射一次 | storage import tools；多个 consumer 自造同名 error；按异常文本猜测 |
| provenance/citation | source meta → storage typed provenance → snapshot → read citation | citation 机械投影 snapshot provenance | 新 `BusinessSource`、provider guessing、citation 再读 repository |
| cache resource lifecycle | `FinsReadRuntime` 的私有 cached-entry/borrow lifecycle | cache 容器返回被替换/淘汰值供 owner retire | cache 返回已 retired/closed processor；eviction/clear 直接关闭仍在用资源 |

`SourceDocumentRevision` 只能表达“同一 published source 版本的 opaque equality token”。R07 在 S2 明确把 Python 字段从 `digest` 改为 `token`；`token` 只接受非空字符串并按 exact opaque equality 比较，不承诺 prefix、长度、字符集、hash 算法或其它 grammar。不得保留 `digest` alias、compat property、SHA-shaped compatibility token 或双字段。`token` 字段名仍不是业务、tool、README 或 LLM contract；具体 token 生成算法、retry budget、私有 resource/borrow/context-manager 类名也保持私有，测试只断言 owner 行为性质。

## 3. 当前代码与调用图完整 inventory

### 3.1 inventory 命令

```bash
rg -n "_normalize_(ticker|document_id)|_normalize_path_component|_list_directory_names|_published_ticker_directory_names|_parse_backup_directory_name" dayu/fins/storage --glob '*.py'
rg -n "portfolio_root /|source_root /|processed_root /|repo_batches_root /|backup|lock_path|publication_lock|local://" dayu/fins/storage --glob '*.py'
rg -n "get_source_revision|_build_source_revision|SourceDocumentRevision|revision_before|revision_after|source_changed_during_read" dayu/fins tests/fins
rg -n "get_source_(meta|revision|document_provenance|handle)|get_(primary_)?source\(" dayu/fins --glob '*.py'
rg -n "\.materialize\(" dayu --glob '*.py'
rg -n "workspace_root / \"portfolio\"|tmp_path / \"portfolio\"|portfolio_root|repo_batches|repo_backups|batch_locks|local://" tests/fins --glob '*.py'
rg -n "Fs(Source|Processed|DocumentBlob|CompanyMeta|FilingMaintenance|Batching).*Repository|build_fs_repository_set|DefaultFinsRuntime\.create" dayu/fins --glob '*.py'
rg -n -i "source[_ -]?revision|storage[_ -]?key|internal[_ -]?key|local://|\.digest" dayu/fins/tools dayu/config/prompts tests/fins
```

### 3.2 raw identity/path/layout inventory

当前 `_normalize_ticker/_normalize_document_id` 命中 7 个 storage 文件、合计 115 次：`_fs_blob_core.py` 5、`_fs_company_meta_core.py` 7、`_fs_maintenance_core.py` 19、`_fs_processed_core.py` 13、`_fs_source_document_core.py` 33、`_fs_storage_infra.py` 32、`_fs_storage_utils.py` 6。所有命中都必须在 S1 逐项分类为“业务 ticker alias 归一”或“storage identity 映射”；不得留下模糊 helper 名继续同时承担两种语义。

| namespace / path | 当前 producer / consumer | 当前 layout assumption | S1 disposition |
|---|---|---|---|
| published ticker target | `_FsStorageInfra._target_ticker_dir`、所有 core | `portfolio/<normalized ticker>` | `portfolio/<private ticker key>`；ticker descriptor 是 round-trip 真源 |
| company meta / inventory | `_company_meta_path*`、`_FsCompanyMetaMixin.scan_company_meta_inventory/_published_ticker_directory_names` | `meta.json.ticker == directory name`；目录名和 publication lock stem 被当 ticker 返回 | 先由 key 定位，再读 descriptor/`CompanyMeta.ticker`；永不返回 key/lock stem；malformed entry 只给无 key 的 typed status |
| writer / publication locks | `_ticker_lock_path`、`_publication_lock_path` | `<normalized ticker>.lock` / `.publication.lock` | lock 名只含 private ticker key；authority/state machine 不变 |
| batch staging | `begin_batch` / recovery | `.dayu/repo_batches/<transaction>/<normalized ticker>`；journal 保存 raw-normalized ticker | staging ticker 目录只含 private key + descriptor；journal 仍只保存 transaction/ticker/phase，ticker 是 exact external identity；不加兼容字段 |
| backup / orphan recovery | `<ticker>.bak.<transaction>`、`_parse_backup_directory_name` | backup 名反推 ticker；用 raw ticker 重建 target/staging/lock | backup 名只解析 private key + transaction；外部 ticker 必须从 journal或 backup 内 descriptor 读取并交叉验证；不能由 key 反推 |
| filing/material source | `_source_root*`、`_source_meta_path*`、list/manifest/validator | `filings|materials/<normalized document_id>`；child.name 即 document id | 文档目录只含 namespace-specific private key + descriptor；manifest/meta 保留 exact external id并与 descriptor双向校验 |
| source blob/object key | `_fs_blob_core.py`、`_handle_dir_path*`、`LocalFileStore` | `ticker/source-kind/document-id/filename` raw identity join；meta URI `local://<raw layout>` | object key/local URI 只含 private key与安全 filename；URI 是 storage internal locator，不进入 tool/LLM；filename contract不变 |
| processed | `_processed_dir*`、processed manifest/meta、clear/list/mark | `processed/<normalized document_id>`；child.name 返回 document id | processed namespace descriptor round-trip；manifest/meta external id双向校验 |
| rejection registry | `_download_rejections_path*`、save/load | 单 ticker JSON；dict key/document entry 经 path-component normalizer | JSON key保留 exact external document id并与 typed entry严格相等；它不是路径，无 separator 拒绝 |
| rejected artifacts | `.rejections/<normalized document_id>`、meta/files/list/read | child.name 返回 document id；object key拼 raw id | rejected namespace descriptor + private key；meta/entry external id双向校验 |
| maintenance cleanup | `cleanup_stale_filing_documents` | 对 child directory name 做 `fil_`业务前缀/valid-id判断 | 先用 descriptor恢复 external id，再应用已有 SEC业务规则；internal key不参与业务判断 |
| manifests / complete validator | `_validate_complete_source_tree/_read_complete_source_manifest/_validate_complete_source_directory` | source directory name、meta document_id、manifest document_id 三者相等 | directory key只与 descriptor派生key一致；descriptor external id、meta、manifest 三者 exact一致；identity file不计入business files |
| `LocalFileStore` / local URI | `_normalize_object_key`、`_local_path_from_uri`、`put/open/delete/list` | key segment严格路径组件 + resolved containment | 继续只接收 internal key/safe filename；absolute/empty/dot/dotdot/separator/symlink escape 仍拒绝 |

测试中的 raw layout assumptions 不是生产 contract。当前必须迁移的测试文件是：

- `tests/fins/test_fins_storage_atomicity.py`：直接构造 `.hidden/MISSING/INVALID` ticker dirs、raw target/backup/staging/lock paths、raw local URI。
- `tests/fins/test_fins_storage_provider.py`：直接读取 filing manifest/rejection registry，手写 raw `local://AAPL/...`。
- `tests/fins/test_sec_pipeline_download.py`：helper 及 20+ 调用直接拼 `portfolio/<ticker>/filings|processed/<document_id>`。
- `tests/fins/test_fins_ingestion_runtime.py`：preprocess corruption fixture 直接拼 raw processed path。

业务测试改为 repository public contract；只有 collision/corruption/recovery/security owner tests 可从 `portfolio_root` 枚举实际 private entry 后做黑盒损坏注入，且不得断言 key grammar。

### 3.3 revision producer/consumer 与 current zero-retry inventory

| owner/call point | 当前行为 | residual |
|---|---|---|
| `domain/document_models.py::SourceDocumentRevision` | `digest` 必须为 `sha256:<64 lowercase hex>` | grammar 被 public typed model冻结 |
| `_fs_source_document_core.py::_build_source_revision_file_payload/_build_source_revision` | 选择 required/optional meta、`ingest_complete/is_deleted` 与排序后的 file identity/content字段，canonical JSON后hash | revision依赖consumer-selected字段；非publication token |
| `_prepare_complete_source_meta` 三条 mutation汇合路径 | 产生完整meta但不产生 persisted revision | 正确 publication point尚未接通 |
| `get_source_revision` core/wrapper/protocol | 每次从 published meta重算hash | storage持有算法却没有持久化publication事实 |
| `read_runtime.py:2198/2230` | meta cache：before → meta → after | mismatch零重试并立即映射 error |
| `read_runtime.py:2558/2594` | processor：before → source/meta/processor → after | mismatch零重试；失败后清cache |
| `read_runtime.py:2503` | cross-document diagnosis单独取revision | 第三种freshness路径 |
| tests `901/951/995` | 断言字段hash变化、JSON/file排序稳定、hash字段格式fail-closed | 固化旧算法，必须改成publication语义 |

最终 source mutation create/update/replace/delete/restore 都必须经唯一 complete-meta preparation owner 生成新 revision；同 batch 中 source 未变化而只改 company/processed/maintenance 时保留原 revision；rollback/crash 不发布新 revision；reset/delete physical source 后 snapshot 不存在。producer 不新增 revision 参数，也不得在 pipeline/runtime 生成 token。

### 3.4 snapshot/materialize/open/path consumer inventory

当前 `.materialize()` 是 **8 个 production 文件、9 个调用**：

1. `dayu/documents/processors/bs_processor.py:135`
2. `dayu/documents/processors/docling_processor.py:148,1745`
3. `dayu/documents/processors/markdown_processor.py:112`
4. `dayu/fins/processors/sec_processor.py:157`
5. `dayu/fins/processors/bs_report_form_common.py:129`
6. `dayu/fins/processors/bs_six_k_processor.py:276`
7. `dayu/fins/processors/source_text.py:88`
8. `dayu/fins/pipelines/sec_fiscal_fields.py:349`

前 7 个 processor 文件不需要知道 storage：只要 registry 获得的 `Source` 指向 snapshot-owned temp tree，现有 materialize 调用就是安全 consumer。不得在每个 processor 内重复 copy/revision/retry。`dayu/documents/processors/source_snapshot.py` 已拥有“从单个 `Source.open()` 复制 EOF 到 spool”的 Documents contract，但它只覆盖一个 Source，不拥有 Fins 多文件 publication identity/revision/provenance，因此复用其分块读取思想，不把它冒充 R07 storage snapshot owner，也不修改它。

必须直接迁移的非-read consumers：

- `FinsIngestionRuntime._preprocess_one_document` (`ingestion_runtime.py:4106`)：当前 `get_source_meta` 与 `get_primary_source` 分开读；processor 从裸 published Source构造。
- `sec_fiscal_fields._build_download_local_file_map`：对 meta files逐个 `get_source(...).materialize()`，XBRL instance/schema/linkbase可跨版本。
- `sec_6k_primary_document_repair.reconcile_active_6k_primary_document/_collect_candidate_assessments/_assess_active_6k_candidate`：meta与每个候选 source分开读。

read runtime 当前另有：

- `_resolve_source_kind` 先 probing filing handle，再 probing material handle；同 document id 同时存在时隐式偏好 filing。
- `_create_processor` 再分开 `get_primary_source`、`get_source_meta`。
- `_build_citation` 再 `_resolve_source_kind`、meta cache、`get_source_document_provenance`。
- 8 个 public processor入口分别在 `read_runtime.py:753,818,987,1329,1432,1541,1619,1722` 取得裸 processor，随后另读 form/citation。
- 9 个 citation构造调用不得保留任何 repository reread。

### 3.5 cache 与资源生命周期 inventory

- `tools/cache.py::ProcessorLRUCache` 当前 `put` 静默丢弃替换/淘汰值，`evict` 只返回 bool，`clear` 不返回值；上层无法释放资源。
- `_CachedProcessor` 只持 processor/source_kind/revision；`_CachedSourceDocumentMeta` 是另一 cache，可能与 processor来自不同调用。
- processor 可在构造后延迟读取 materialized path；因此 snapshot temp tree必须至少活到 cached processor退休且最后一个 active read结束。
- 当前 `DefaultFinsRuntime` 没有 close；`_FinsReadProcessTarget.__call__` 每次创建 runtime，成功/业务失败/异常路径都不显式清 cache resource。

### 3.6 composition roots 与 producer inventory

四个真实 shared-core composition roots：

1. `DefaultFinsRuntime.create` (`service_runtime.py:350`)；read/download/preprocess/upload providers最终使用它。
2. `CnPipeline.__init__` (`cn_pipeline.py:378`)。
3. `SecPipeline.__init__` (`sec_pipeline.py:512`)。
4. standalone 6-K repair (`sec_6k_primary_document_repair.py:260`)。

它们都通过 `build_fs_repository_set(...)` 把 batching/company/source/blob/processed/maintenance wrappers绑定到同一个 core；R07 不增加第二 factory或跨层 registry。

source mutation producers 已审计：`ingestion_runtime.py` download/upload/preprocess foundation；`sec_pipeline.py`、`cn_pipeline.py`及 download workflows/rebuild；`docling_upload_service.py`；standalone 6-K repair；company/maintenance rebuild helpers。它们继续只提交业务 meta/files/provenance与显式 `batch=`；revision由storage complete-meta owner自动产生。无需修改 CN/SEC/Docling producer签名来传 revision。

### 3.7 LLM-facing exposure inventory

- 当前 tool schema/result/citation 不输出 source revision、internal key 或 local URI；revision 命中只在 internal code、tests 与 `dayu/fins/README.md`。
- `ErrorCode.SOURCE_CHANGED_DURING_READ` 是既有 LLM-facing typed code；必须保留 code 值，不把 revision token或internal key拼进 message/hint。
- `SourceDocumentProvenance` 继续产生业务可读 `source_type/source_provider`；snapshot不得新增 speculative provider层。
- 最终 9 个 read tool completed/failed/cancelled JSON recursive scan必须证明没有 `revision`、`storage_key`、private key、absolute temp path或 `local://`。

## 4. Allowlist refinement 裁决

umbrella 是 mandatory starting baseline，不是冻结实现。下列 refinement 全部由 `5f09e2cc` 直接代码证据触发，仍在 Topic 6.3/6.7 owner 内：

| refinement | 理由 | 不扩域证明 |
|---|---|---|
| 新增私有 `dayu/fins/storage/_fs_identity.py` | 7 个 storage 文件共115个 identity/path normalizer命中，需要唯一映射owner，避免继续把 `_fs_storage_utils.py` 变成混合god helper | 只依赖标准库、storage/domain低层契约；不进入包根/LLM |
| 新增私有 `dayu/fins/storage/_fs_source_snapshot.py` | `_fs_source_document_core.py` 已1456行且承担CRUD；多文件fd/copy/validation/temp cleanup是可独立验证资源owner | 只实现source repository snapshot；不新增业务source抽象 |
| 加入 `ingestion_runtime.py` | preprocess分开读meta/source且processor可能延迟读path | 只迁移既有source consumer，不改direct-stream terminal语义 |
| 加入 `sec_fiscal_fields.py` | 逐文件物化会混用XBRL同组文件 | 只消费一份snapshot，不改fiscal推断算法（R08不实施） |
| 加入 `sec_6k_primary_document_repair.py` | meta与每个6-K候选source分开读 | 只更换read source，不改6-K选文算法 |
| 加入 `service_runtime.py` / `fins_tools.py` | process-backed runtime当前无显式close，cache资源会泄漏到target结束 | 只接通R07 resource cleanup，不改tool envelope/Host治理 |
| 加入 4 个raw-layout测试文件 | 现有测试直接固化旧目录，fresh schema后必须迁移到repository contract | 生产算法不下放到fixture；corruption test只枚举实际entry，不断言key grammar |

审计后明确 **不改**：`local_file_store.py`、`file_store.py`、`local_file_source.py`、generic Documents processors、Fins processor classes、processor registry。它们分别继续拥有安全file/object IO或消费标准 `Source`；snapshot owner在上游一次性提供安全Source。若实现发现这些文件必须改变 public 语义，先 stop 回 plan review。

## 5. 目标 contract 与最小实现选择

### 5.1 storage-owned opaque identity mapping

1. storage 接收 exact、非空、可UTF-8持久化的 external identity；不 `strip`、不大小写转换、不Unicode normalization、不basename/split。上游 ticker resolver/业务请求仍可产生 canonical ticker，但 storage 不再重复拥有该业务规则。
2. 私有 identity owner 根据 `(namespace, exact external identity)` 派生 filesystem-safe internal key。派生算法必须确定性、namespace-separated并有足够collision resistance，但 prefix、长度、alphabet、digest算法与可解析性全部私有。
3. ticker目录以及 filing/material/processed/rejected document目录各持一个由 `_write_json` 原子写+file fsync+parent fsync 的identity descriptor。descriptor至少自解释记录 namespace 与 exact external identity；文件名/字段名属于fresh internal schema，不在README/tool/public package承诺。
4. lookup时先由external identity派生key，再读取descriptor并验证 namespace、exact identity、derived key与当前root一致；descriptor missing、JSON corruption、namespace mismatch、external mismatch或碰撞一律fail closed，禁止扫描fallback。
5. enumeration时遍历private-key目录，拒绝symlink/non-directory，读取descriptor恢复external identity；list/manifest/company inventory只返回external identity。未知/损坏entry不得泄漏private key。
6. ticker staging/target/backup之间复制同一descriptor。journal保持R06闭集 `{transaction_id,ticker,phase}`，其中ticker为exact external value；recovery由journal/backup内descriptor重新派生并交叉验证private key。`_published_ticker_directory_names` 扫到的lock stem只能发现private candidate key；business ticker只能从可验证的target或backup descriptor恢复并交叉验证。只有lock且没有可验证descriptor时，inventory沿用既有typed malformed/recovery category且business ticker缺失；不得新造状态名，也不能返回key/lock stem。
7. source/processed/rejected meta与manifest继续持业务external identity，并与descriptor exact匹配；它们不是mapping fallback。blob-first在写第一个文件前就创建/验证document descriptor，因此碰撞在任何payload落盘前fail closed。
8. filename、primary filename、manifest filename、object-key segment与local URI仍走现有单路径组件/containment验证。external id可以是Unicode、层级字符串、`/`、`\\`、drive-like、`.`、`..`或absolute-looking文本；同样文本若出现在filename/path/local URI channel仍必须拒绝。这两个contract不得混用。

### 5.2 storage-owned published revision

1. complete-source meta的storage私有revision字段是持久化真源；S2把 `SourceDocumentRevision.digest` 一次性改为 `SourceDocumentRevision.token`，只接受非空字符串并做opaque equality，不校验/承诺 `sha256:` 或任何其它grammar，且不保留字段别名、compat property或SHA-shaped兼容值。
2. `_prepare_complete_source_meta(...)` 或其同owner等价helper在每次 source create/update/replace/delete/restore 的最终完整meta写入前生成新opaque token。caller提供的同名字段必须拒绝或被owner彻底排除，不能信任producer。
3. R06 staging持有新token；只有batch commit把完整ticker tree发布后consumer可见。rollback/precommit crash不改变published token，recovery old/new与source content同版。
4. processed/company/rejection/maintenance-only batch复制并保留source token，不生成新token。source delete/reset后source、token与snapshot resource同时不存在，后续snapshot read明确抛 `FileNotFoundError`。
5. complete-source validator验证token存在、类型合法且meta/manifest/descriptor/files完整；不通过token grammar推断业务事实。
6. S2即删除consumer field-hash producer、`sha256:` grammar、排序/hash tests与README的SHA描述；同一slice内完成 `digest` 到 `token` 的breaking rename。S2过渡checkpoint内既有 `get_source_revision` 只可把persisted token机械装入新的 `SourceDocumentRevision(token=...)` 以保持full pyright；S3 consumer迁移完成后从protocol/wrapper/core一并删除，不保留compat facade。

### 5.3 单一 snapshot API 与资源生命周期

public storage repository只提供一个窄typed snapshot read语义；本plan选定协议方法 `read_source_snapshot(ticker, document_id, source_kind=None, *, materialize_files: bool)`。它返回由protocol按字段/操作约束的typed resource，但最终具体resource/lease/context-manager实现类名保持private，不进包根、README、tool或LLM contract：

- 输入：exact external ticker/document id；可选显式source kind；`materialize_files` 是直接布尔参数，不使用factory/profile/query bag。
- source kind缺省时由storage在同一publication guard内检查filing/material映射：0个为`FileNotFoundError`，1个返回其typed kind，2个为storage invariant/ambiguity failure；read runtime不再先filing后material guessing。
- 输出descriptor：exact external identity、typed source kind、深拷贝/immutable complete source meta、storage typed provenance、opaque persisted revision、完整有序business file descriptors、exact primary filename。
- `materialize_files=False`：只返回同一guard下的轻量descriptor，不暴露published Path/local URI；用于cache freshness。
- `materialize_files=True`：另持snapshot-owned temp directory，所有声明文件在其中保持原安全business filename；primary及named source都返回指向temp tree的标准 `Source`。任何 `materialize()` 都只能返回temp path，不得返回published path。
- snapshot resource显式、幂等close；关闭后source open/materialize失败。资源对象不跨process序列化，不写durable state，不被tool结果引用。

具体有界稳定读取策略由storage私有实现，选择如下最小算法：

1. 在一次publication guard内读identity/meta/provenance/persisted revision/file list，并打开全部declared regular file descriptors；拒绝symlink、non-regular、containment escape、meta/descriptor mismatch。
2. 释放guard后从这些fds复制到一个新temp root，逐文件记录真实EOF、declared size/sha256（字段存在时）以及copy前后`fstat`稳定性；不从published裸Path重开，也不在看到内容/`fstat`异常时先行决定重试分类。
3. 再在一次短publication guard内核对同一external identity的persisted revision/descriptor。只有revision/descriptor真实变化（包括source publication切换或删除）才关闭全部fds、删除整个attempt temp root并重取完整attempt。
4. 若post-copy核对证明revision/descriptor未变，则已打开inode内容变化、copy前后`fstat`变化、真实EOF与declared size/hash不匹配都不可能是R06 publication guard + atomic rename允许的publication race；立即沿既有corruption/validation边界fail closed，不重试、不伪装成 `source_changed_during_read`。静默文件修改测试必须使用真实fd-copy协调该优先级。
5. 内部attempt budget必须有界且大于1，以允许一次真实publication变化恢复；具体次数/退避不是contract，测试不得断言调用次数或magic数字。R07不做consumer retry。budget耗尽只抛一个storage专用typed consistency error，保留cause但不携带Path/key/revision。missing、corruption、symlink、permission与ordinary I/O继续各自typed/原生边界，不能都伪装为source changed。

这个算法在R06 atomic rename模型下即使A/B publication发生在copy中也不会把不同publication的fd混合；post-copy revision核对决定返回A、重取B或在持续churn下typed失败。

### 5.4 preprocess/SEC consumers

- preprocess在单文档workflow中先begin batch取得same-ticker writer mutex，再读取published full snapshot、构建processor/sections/tables、写processed并commit；begin发生在snapshot前，保证staging source与snapshot同一published revision。长processor构造不占publication guard，published readers仍畅通；它只序列化same-ticker writer。异常/取消在commit前close snapshot并exactly-once rollback，commit开始后不二次rollback。
- `sec_fiscal_fields` 对一个source document只取得一份full snapshot；`_build_download_local_file_map` 仍按snapshot descriptor声明的exact business filename建立lowercase map，`_pick_download_xbrl_file` 仍沿用既有排序、suffix优先级与XML fallback排除规则来选择instance/schema/linkbase。唯一变化是map中的全部temp paths来自同一full snapshot；函数结束/异常时close，不得逐文件重读repository。R07不引入 `has_xbrl_instance` 内容嗅探分类或新文件分类schema。
- active 6-K reconcile在caller-owned batch已持writer mutex的前提下取得一份full snapshot；meta、全部候选HTML与primary评分来自该snapshot，结束后close，再把选择写入同一staging。prepared prepublication payload路径保持现有临时payload owner，不套storage snapshot。
- processor registry及所有processor类继续只接收standard `Source`，不接revision/provenance/path provider参数。

### 5.5 read/cache/citation cutover

1. 每次document read先取lightweight storage snapshot。cache miss/revision mismatch时retire旧entry，再取得full snapshot并进入同document creation lock；锁内必须再次检查matching cached entry。若并发调用已经发布可借的matching entry，当前调用幂等close自己取得的full snapshot并借existing entry；否则才从当前full snapshot构建并发布唯一processor entry。构建成功后entry同时持processor、full snapshot descriptor/provenance/revision与resource。
2. cache hit只在lightweight snapshot revision/source kind与cached full snapshot完全相等时成立；之后获得一个private active borrow。若在borrow期间发生新publication，当前调用仍完整使用旧cached snapshot，下一调用才看到mismatch并切换。
3. 删除独立source meta cache；form type、source kind、provenance/citation都从当前borrow的full snapshot取得。`list_documents` 只对storage-owned `list_source_document_ids` 分别做filing/material两个typed list projection并组合业务列表；不得对每个document调用snapshot形成N+1，不新增batch snapshot API，也不恢复filing-first guess。只有单document read在 `source_kind=None` 时使用snapshot的0/1/2 typed resolution。list meta仍不能与processor citation拼成同一document read。
4. 8个processor入口必须在processor调用、semantic enrichment、cross-document diagnosis及citation/result构造完成后才释放borrow；processor对象不从private helper裸返回到borrow scope外。
5. generic LRU容器修改为把replacement/eviction/clear的旧值返回owner；它不直接猜测/调用resource close。read runtime entry负责active-borrow count与retired状态：retire后不再借出，active为0立即close，否则最后一个borrow release时close。
6. replacement、capacity eviction、source delete、runtime clear/close、processor build failure、cancellation、citation failure与process target异常都必须最终释放temp tree。cache不得持有已close resource或把retired entry重新提升LRU。
7. cross-document diagnosis若检查cached candidate，先取该candidate lightweight snapshot并按revision验证，再在borrow内查询；不得独立 `get_source_revision`。
8. citation只接收current borrowed snapshot，机械投影其provenance；不得再 `_resolve_source_kind/get_source_meta/get_source_document_provenance`。测试在publication barrier插入A/B变更，结果内容与citation provider必须来自同一snapshot。
9. storage consistency exhaustion由read runtime单点catch并映射既有 `ErrorCode.SOURCE_CHANGED_DURING_READ`；其它异常保持现有typed source decode/not found/citation/execution映射。错误message/hint不暴露revision/key/path。
10. `FinsReadRuntime.close()`（或等价内部lifecycle）幂等retire/clear cache；`DefaultFinsRuntime`只在自身已创建read runtime时close它；`_FinsReadProcessTarget.__call__` 用`finally`覆盖completed、typed failure、unexpected exception。长期provider runtime保持bounded cache并由其owner生命周期关闭，不用`__del__`兜底。

## 6. Security retained / modified matrix

| 机制 | R07 disposition | 验证 |
|---|---|---|
| external id拒绝separator/dot/drive/absolute | **有意修改**：identity channel改为exact round-trip；不再用业务拒绝实现path安全 | Unicode、层级、separator、drive-like、`.`/`..`、absolute-looking ticker/document ids跨所有namespace round-trip |
| filename/entry name | **保留** 单路径组件、非空、dot/dotdot、separator、absolute/drive拒绝 | source/blob/processed/rejected/primary filename负测 |
| local URI/object key | **保留并收紧owner**：只含internal keys+safe filename；resolve containment与symlink拒绝不变 | `local:///absolute`、`a//b`、`a/../b`、backslash、symlink escape拒绝 |
| path containment | **保留** `_require_contained_path/_is_contained_recovery_path/resolve().relative_to` | target/staging/backup/source/processed/rejected/temp root真实filesystem tests |
| symlink rejection | **保留** ticker/doc descriptor、meta、manifest、business files、recovery dirs均fail closed | existing + descriptor/source snapshot symlink nodes |
| atomic JSON/file write | **保留并复用** same-dir temp、file flush/fsync、`os.replace`、parent fsync | identity descriptor、revision meta与既有`LocalFileStore.put` ordering/failure tests |
| R06 writer mutex | **保留** same-ticker entire transaction；lock locator改用internal key | two external ids不碰撞；same exact id仍互斥；preprocess持锁一致性 |
| R06 publication guard | **保留** commit/recovery swap短窗与snapshot attempt两次短读；不在copy/processor阶段持有 | long copy/processor不阻塞published readers；A/B不mixed |
| journal/recovery | **保留状态机，修改locator**：minimal fields不变；descriptor提供round-trip | 每个crash phase、orphan backup、corrupt descriptor、key/meta mismatch |
| complete-source validator | **扩展同一owner**：加入identity descriptor与persisted revision invariant | incomplete/collision/corruption/meta mismatch均不能commit |
| typed provenance/citation | **保留并同源**：snapshot包含唯一provenance | source type/provider matrix + citation/result同版 |
| typed read errors | **保留**：仅consistency exhaustion映射既有code | transient成功、sustained失败、decode/not-found/cancel不改名 |
| tool/Host authorization | **不触碰** | import/diff/LLM scans证明无统一authorization |

## 7. 三个原子、累计 slices

S1—S3 是同一R07 breaking cutover的累计working-tree checkpoints，不是新sub-WU、release、green accepted commit或compat阶段。每slice结束先做Controller scope/验证与AgentMiMo/AgentDS双路cumulative review；accepted findings必须在同一working tree修复并双路re-review后才能进下一slice。**不创建slice accepted commit**；只有S3 complete final tree可以进入R07 accepted implementation commit裁决。

### 7.1 R07-S1 — storage-owned opaque key 全路径迁移

#### 输入与输出

- 输入：R06 fresh filesystem layout、exact external ticker/document ids、现有BatchToken与source/processed/rejected/company请求。
- 输出：所有physical locator只含private internal key；所有repository public handles/list/meta/manifest/registry仍round-trip exact external identity；mapping descriptor是唯一持久化round-trip真源。

#### exact production allowlist

```text
dayu/fins/domain/document_models.py
dayu/fins/storage/_fs_identity.py                         # new, private
dayu/fins/storage/_fs_storage_utils.py
dayu/fins/storage/_fs_storage_infra.py
dayu/fins/storage/_fs_blob_core.py
dayu/fins/storage/_fs_company_meta_core.py
dayu/fins/storage/_fs_maintenance_core.py
dayu/fins/storage/_fs_processed_core.py
dayu/fins/storage/_fs_source_document_core.py
```

`CompanyMetaInventoryEntry` 必须删除physical `directory_name`语义，改为external ticker可选投影+typed status；corrupt/unresolved entry不得输出private key。不要保留旧字段alias。

#### exact test allowlist

```text
tests/fins/test_fins_storage_provider.py
tests/fins/test_fins_storage_atomicity.py
tests/fins/test_fins_ingestion_runtime.py
tests/fins/test_sec_pipeline_download.py
```

#### producer-consumer迁移顺序

1. 新增identity owner及descriptor原子读写/验证。
2. ticker target/staging/backup/locks/recovery/company inventory先切key，确保transaction locator一致；显式迁移 `_published_ticker_directory_names`：lock stem只发现private candidate key，business ticker只从已验证target/backup descriptor恢复，lock-only且无descriptor时沿用既有typed malformed/recovery category并让business ticker缺失，绝不投影key/stem或新增状态名。
3. source filing/material及blob handle/URI/manifest/validator切document key。
4. processed、rejected artifact、rejection registry、maintenance cleanup切document key；`cleanup_stale_filing_documents` 必须先从每个child descriptor恢复exact external document id，再对该external id执行既有 `fil_` 业务分类与valid-id比较，private child key的prefix/value不参与业务判断。
5. 删除旧 `_normalize_document_id` path-component contract；ticker alias业务helper与identity helper分名分责。
6. 最后迁移raw-layout tests；业务tests走repository，owner corruption tests只黑盒枚举实际entry。

#### 状态、失败、并发、cleanup

- descriptor必须在首个payload前存在；existing exact identity幂等验证，different identity落到同key立即collision failure。
- corrupt/missing/mismatched descriptor、meta/manifest mismatch与symlink不做scan fallback；batch commit失败保留R06 old/recovery evidence语义。
- writer/publication lock acquisition/release、commit primary cause、rollback/recovery cleanup顺序不变；只是locator从external变internal。
- failed descriptor temp写入按既有atomic helper清理；不得留下可被list当业务entry的partial mapping。

#### 禁止项

- 禁止base64/URL quoting后把可逆string直接当“安全contract”并在consumer解析。
- 禁止全局reverse registry、SQLite catalog或第二mapping state machine；当前descriptor+deterministic locator已足够。
- 禁止旧layout探测、目录扫描fallback、basename替代、`hasattr/getattr`或test fixture反推key。
- 禁止在log/tool/citation暴露private key。

#### targeted pytest nodes

既有必须继续通过：

```text
tests/fins/test_fins_storage_atomicity.py::test_batch_token_fields_and_minimal_journal_are_closed_owner_contract
tests/fins/test_fins_storage_atomicity.py::test_single_component_owners_reject_invalid_values   # 改名/改义，仅filename/entry继续拒绝
tests/fins/test_fins_storage_atomicity.py::test_local_uri_owner_rejects_invalid_keys
tests/fins/test_fins_storage_atomicity.py::test_local_uri_owner_rejects_symlink_escape
tests/fins/test_fins_storage_atomicity.py::test_orphan_recovery_follows_journal_commit_point
tests/fins/test_fins_storage_provider.py::test_download_rejection_registry_roundtrips_typed_entries
tests/fins/test_fins_storage_provider.py::test_download_rejection_registry_rejects_mismatched_storage_key
tests/fins/test_sec_pipeline_download.py::test_sec_pipeline_download_writes_meta_and_manifest
```

新增/替换节点（名字作为测试实施目标，断言性质而非key grammar）：

```text
tests/fins/test_fins_storage_provider.py::test_opaque_ticker_and_document_identity_round_trip_all_storage_namespaces
tests/fins/test_fins_storage_provider.py::test_opaque_identity_round_trips_unicode_hierarchy_separator_drive_dot_and_dotdot
tests/fins/test_fins_storage_provider.py::test_identity_mapping_detects_collision_corruption_and_business_meta_mismatch
tests/fins/test_fins_storage_provider.py::test_company_inventory_never_projects_internal_storage_key
tests/fins/test_fins_storage_provider.py::test_lock_only_company_inventory_has_no_business_ticker_or_internal_key
tests/fins/test_fins_storage_provider.py::test_stale_filing_cleanup_uses_descriptor_external_id_in_opaque_layout
tests/fins/test_fins_storage_atomicity.py::test_recovery_round_trips_opaque_ticker_without_path_name_inference
tests/fins/test_fins_storage_atomicity.py::test_complete_validator_rejects_identity_descriptor_symlink_and_mismatch
tests/fins/test_fins_storage_atomicity.py::test_filename_absolute_and_local_uri_attacks_remain_rejected_for_opaque_id_documents
tests/fins/test_fins_ingestion_runtime.py::test_preprocess_request_round_trips_hierarchical_document_id_through_storage
```

#### S1 handoff contract

S2只可收到external identity、internal storage locator owner与fresh published tree；不得再发现raw identity path join。S1 review必须签字确认source/processed/blob/rejected/maintenance/company/meta/manifest/recovery全部已覆盖。

### 7.2 R07-S2 — persisted published revision + atomic stable snapshot

#### 输入与输出

- 输入：S1 mapping、R06 complete-source commit/publication guard、source complete meta/files/provenance。
- 输出：source mutation自动生成并随commit发布opaque revision；一个storage snapshot同时拥有identity/meta/provenance/revision/all files/primary；transient变化可恢复，持续变化typed失败；所有非-read processor consumers改用snapshot。

#### exact production allowlist（累计新增）

```text
dayu/fins/domain/document_models.py
dayu/fins/storage/repository_protocols.py
dayu/fins/storage/fs_source_document_repository.py
dayu/fins/storage/_fs_storage_infra.py
dayu/fins/storage/_fs_source_document_core.py
dayu/fins/storage/_fs_source_snapshot.py                  # new, private resource owner
dayu/fins/ingestion_runtime.py
dayu/fins/pipelines/sec_fiscal_fields.py
dayu/fins/pipelines/sec_6k_primary_document_repair.py
```

#### exact test allowlist（累计新增）

```text
tests/fins/test_fins_storage_provider.py
tests/fins/test_fins_storage_atomicity.py
tests/fins/test_fins_ingestion_runtime.py
tests/fins/test_sec_pipeline_download.py
tests/fins/test_processor_read_consistency.py
```

#### producer-consumer迁移顺序

1. 把 `SourceDocumentRevision.digest` breaking rename为 `SourceDocumentRevision.token`；`__post_init__`/owner validation只拒绝空字符串（非字符串由typed/schema边界拒绝），接受任意非空opaque token并按exact equality比较，不再校验 `sha256:` prefix、hex长度或hash grammar；不保留alias/property/双字段。complete-meta owner写persisted token，validator校验。
2. S2即删除 `_build_source_revision`、selected-field hash builder与SHA grammar；checkpoint中的 `get_source_revision` 只机械读取persisted token并构造 `SourceDocumentRevision(token=...)`，绝不重算，保证未迁移read runtime仍type-correct。S3只负责删除该临时method及consumer call，不把hash删除推迟到S3。
3. 实现light/full snapshot与typed consistency error；wrapper/protocol只暴露一个snapshot语义。
4. 迁移preprocess，确保begin batch在snapshot前并保持R06 rollback/commit ownership。
5. 迁移SEC fiscal multi-file与active 6-K candidate consumers；SEC只把 `_build_download_local_file_map` 的path source替换为同一snapshot temp tree，保留descriptor filename lowercase map及 `_pick_download_xbrl_file` 既有排序/suffix/XML fallback排除规则，不新增 `has_xbrl_instance` 分类；prepared payload路径不改。
6. 增加真实filesystem concurrency/cleanup tests；不通过fake Source固定storage策略。

#### 状态、失败、并发、cleanup

- revision随source complete mutation在staging产生；old/new publication与R06目录切换同一commit point。
- snapshot每个attempt拥有独立fds/temp root；失败只清自己的资源，不删除published文件。
- transient测试至少观察一次discarded attempt并最终返回一致B，但不assert固定attempt数；sustained churn只asserttyped exhaustion、所有temp/fd清理和无partial result。
- A/B每版包含至少两个相关文件、meta/provenance/primary不同marker；任何结果只能完整A或完整B。
- preprocess异常/cancel在commit前close snapshot再rollback；commit开始后storage owns outcome，caller不二次rollback。

#### 禁止项

- 禁止token内容hash、timestamp freshness、consumer-selected字段或wall-clock作为revision。
- 禁止full snapshot返回published Path，禁止cache/processor在snapshot close后继续使用。
- 禁止把retry次数写入public常量、README、error、test参数化expected count。
- 禁止把所有I/O/corruption/symlink错误都映射为source changed。

#### targeted pytest nodes

```text
tests/fins/test_fins_storage_provider.py::test_published_revision_is_persisted_and_changes_only_with_source_publication
tests/fins/test_fins_storage_provider.py::test_source_document_revision_accepts_nonempty_opaque_token_and_rejects_empty
tests/fins/test_fins_storage_provider.py::test_rollback_and_non_source_batch_preserve_published_revision
tests/fins/test_fins_storage_provider.py::test_snapshot_descriptor_meta_provenance_primary_and_files_share_one_revision
tests/fins/test_fins_storage_provider.py::test_snapshot_is_not_found_and_has_no_token_or_resource_after_source_delete_or_reset
tests/fins/test_fins_storage_atomicity.py::test_snapshot_concurrent_ab_publication_never_mixes_files
tests/fins/test_fins_storage_atomicity.py::test_snapshot_transient_change_recovers_and_cleans_discarded_attempt
tests/fins/test_fins_storage_atomicity.py::test_snapshot_sustained_change_raises_typed_consistency_failure_and_cleans_resources
tests/fins/test_fins_storage_atomicity.py::test_snapshot_rejects_symlink_containment_and_file_meta_mismatch
tests/fins/test_fins_storage_atomicity.py::test_snapshot_fd_copy_silent_mutation_is_corruption_without_revision_change
tests/fins/test_fins_ingestion_runtime.py::test_preprocess_snapshot_and_processed_publication_share_source_revision
tests/fins/test_sec_pipeline_download.py::test_sec_pipeline_download_prefers_dei_fiscal_when_available
tests/fins/test_sec_pipeline_download.py::test_sec_fiscal_files_consume_one_storage_snapshot
tests/fins/test_sec_pipeline_download.py::test_standalone_6k_reconcile_publishes_source_and_processed_together
tests/fins/test_sec_pipeline_download.py::test_active_6k_candidate_assessment_consumes_one_storage_snapshot
```

#### S2 handoff contract

S3只可消费storage snapshot与persisted revision。S2结束时允许旧read runtime仍机械调用persisted `get_source_revision`，但不允许任何field hash；这个checkpoint不可commit/accept。S3必须删除该旧method及全部before/after consumer。

### 7.3 R07-S3 — read/cache/citation migration 与旧路径删除

#### 输入与输出

- 输入：S2 light/full snapshot、typed consistency error、snapshot-owned Source。
- 输出：read processor/meta/provenance/citation/result同一snapshot；cache安全持有/retire资源；source kind由storage解析；旧double-read/hash/path/provider guessing全部删除；process target全路径cleanup。

#### exact production allowlist（累计新增）

```text
dayu/fins/storage/repository_protocols.py
dayu/fins/storage/fs_source_document_repository.py
dayu/fins/storage/_fs_source_document_core.py
dayu/fins/tools/cache.py
dayu/fins/tools/read_runtime.py
dayu/fins/tools/error_contract.py
dayu/fins/service_runtime.py
dayu/fins/tools/fins_tools.py
```

`read_runtime.py` 本slice既然被修改，顺带删除base两个unused imports，使changed-file scoped Ruff清零；不做其它搜索/financial语义清理。

这里的范围精确限定为删除 `QueryDiagnosis` 与 `SEARCH_MODE_AUTO` 两个已记录的unused imports；禁止借S3扩大清理其它legacy Ruff项。

#### exact test allowlist（累计新增）

```text
tests/fins/test_processor_read_consistency.py
tests/fins/test_fins_storage_provider.py
tests/fins/test_fins_read_runtime.py
tests/fins/test_read_runtime_semantic_ownership_guards.py
tests/fins/test_financial_read_contracts.py
tests/fins/test_fins_ingestion_runtime.py
```

#### exact README allowlist

```text
dayu/fins/README.md
tests/README.md
```

#### producer-consumer迁移顺序

1. generic LRU先改为向owner返回displaced values；不内置close猜测。
2. read runtime建立private cached entry/borrow retire状态与幂等close；同document creation lock内double-check matching entry，竞争失败调用关闭自己取得的full snapshot，只有一个调用构建并发布processor。
3. 逐一迁移8个processor入口和cross-document diagnosis，使processor/citation/result在borrow scope内；`list_documents` 继续组合filing/material两个 `list_source_document_ids` typed projections，不做per-document snapshot或新增batch API。
4. 删除独立meta cache、`_resolve_source_kind` probing、citation repository reread、consumer before/after与field-hash相关helper；单document snapshot继续保留 `source_kind=None` 的0/1/2 storage resolution。
5. 从source protocol/wrapper/core删除 `get_source_revision`；不得留deprecated wrapper。
6. error contract只更新业务可读说明，code值不变；storage typed exhaustion在read runtime单点映射。
7. Default/runtime process target接通finally close；验证success/failure/cancel/build-error cleanup。
8. 最后更新README current contract并执行LLM/source/AST scans。

#### 状态、失败、并发、cleanup

- cache entry状态最少表达live/retired/closed与active borrower数量，但具体enum/class名私有；closed不可逆。
- creation lock只序列化同document cache build；锁内必须double-check当前full snapshot对应的matching cached entry。已有可借entry时close当前调用的losing snapshot并borrow existing；没有时才允许一次processor build/publish。不持有publication guard执行processor。
- eviction/replacement/clear把entry retire；active调用可完成旧snapshot，最后release删除temp；新调用只能取新entry。
- processor build/UTF-8 validation/registry fallback失败时full snapshot不进cache并立即close。
- cancellation优先级保持；若取消发生在snapshot build后，close后继续现有typed cancellation，不映射source changed。
- `FinsReadRuntime.close` 后新read fail fast internal lifecycle error；process target不输出该内部名。

#### 禁止项

- 禁止cache保存裸`Path`、`LocalFileSource`指向published tree或close后resource。
- 禁止citation用ticker/doc重新读repository；禁止从source URI/provider string推断provenance。
- 禁止保留 `revision_before/revision_after`、`_build_source_revision`、SHA grammar或filing-first probing。
- 禁止tool result/schema加入revision/internal key/debug locator。

#### targeted pytest nodes

```text
tests/fins/test_processor_read_consistency.py::test_processor_cache_reuses_equal_revision_and_rebuilds_after_source_change
tests/fins/test_processor_read_consistency.py::test_independent_meta_cache_compares_revision_and_evicts_old_processor  # 替换为single snapshot entry contract
tests/fins/test_processor_read_consistency.py::test_cross_document_diagnosis_does_not_reuse_stale_cached_processor
tests/fins/test_processor_read_consistency.py::test_processor_build_revision_race_has_zero_retry_and_no_cache_artifact  # 替换为storage transient recovery
tests/fins/test_processor_read_consistency.py::test_independent_meta_revision_race_has_zero_retry_and_no_cache_artifact # 删除/合并
tests/fins/test_processor_read_consistency.py::test_concurrent_reads_after_revision_change_build_one_processor
tests/fins/test_processor_read_consistency.py::test_concurrent_initial_cache_miss_builds_one_processor_and_closes_losing_snapshot
tests/fins/test_processor_read_consistency.py::test_cached_processor_is_not_returned_after_source_deleted
tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_projects_provider_owned_source_types
tests/fins/test_fins_storage_provider.py::test_read_runtime_citation_reuses_single_cached_source_meta_read # 替换为same snapshot provenance
tests/fins/test_read_runtime_semantic_ownership_guards.py::test_read_runtime_source_meta_cache_is_bounded # 替换为snapshot processor cache bound/lifecycle
tests/fins/test_read_runtime_semantic_ownership_guards.py::test_read_runtime_source_meta_cache_is_partitioned_by_source_kind # 替换为storage kind resolution
```

新增节点：

```text
tests/fins/test_processor_read_consistency.py::test_cache_eviction_defers_snapshot_close_until_active_borrow_releases
tests/fins/test_processor_read_consistency.py::test_cache_clear_and_runtime_close_release_all_snapshot_resources
tests/fins/test_processor_read_consistency.py::test_transient_storage_change_recovers_without_consumer_retry_or_cache_artifact
tests/fins/test_processor_read_consistency.py::test_sustained_storage_change_maps_once_to_source_changed_during_read
tests/fins/test_processor_read_consistency.py::test_citation_and_result_use_the_same_borrowed_snapshot_during_publication
tests/fins/test_fins_storage_provider.py::test_read_outputs_never_expose_revision_internal_key_local_uri_or_temp_path
tests/fins/test_fins_storage_provider.py::test_fins_read_process_target_closes_runtime_on_success_and_failure
tests/fins/test_fins_ingestion_runtime.py::test_default_runtime_close_is_idempotent_and_preserves_lazy_read_creation
tests/fins/test_read_runtime_semantic_ownership_guards.py::test_read_runtime_has_no_revision_hash_double_read_or_source_kind_probe
tests/fins/test_read_runtime_semantic_ownership_guards.py::test_list_documents_uses_two_typed_storage_lists_without_per_document_snapshot
```

#### S3 / R07 implementation output

全部consumer只见snapshot；source revision method/hash、provider guessing、裸published path与独立citation reread零残留。只有此时可进入§9完整验证与双路完整code review。

## 8. 每 slice 强制验证矩阵

### 8.1 focused tests 与逐changed production file coverage

每slice先执行其§7 targeted nodes，再执行该slice exact test allowlist全文件。coverage必须用该slice累计test allowlist覆盖该slice累计changed production Python allowlist：

| checkpoint | coverage test files（完整路径） | 必须逐文件 `>=80%` 的 production files |
|---|---|---|
| S1 | `test_fins_storage_provider.py`、`test_fins_storage_atomicity.py`、`test_fins_ingestion_runtime.py`、`test_sec_pipeline_download.py` | `domain/document_models.py`；storage `_fs_identity.py`、`_fs_storage_utils.py`、`_fs_storage_infra.py`、`_fs_blob_core.py`、`_fs_company_meta_core.py`、`_fs_maintenance_core.py`、`_fs_processed_core.py`、`_fs_source_document_core.py` |
| S2 cumulative | S1四文件 + `test_processor_read_consistency.py` | S1九文件 + storage `repository_protocols.py`、`fs_source_document_repository.py`、`_fs_source_snapshot.py`；`ingestion_runtime.py`；pipelines `sec_fiscal_fields.py`、`sec_6k_primary_document_repair.py` |
| S3 cumulative | S2五文件 + `test_fins_read_runtime.py`、`test_read_runtime_semantic_ownership_guards.py`、`test_financial_read_contracts.py` | S2十五文件 + tools `cache.py`、`read_runtime.py`、`error_contract.py`、`fins_tools.py`；`service_runtime.py` |

表中相对前缀分别是 `tests/fins/` 与 `dayu/fins/`；命令中必须展开成完整路径，不能用目录aggregate百分比替代。

```bash
coverage erase
coverage run --branch -m pytest -q <该slice累计test files>
coverage json -o workspace/tmp/r07-sN-coverage.json
python -c 'import json; from pathlib import Path; p=json.loads(Path("workspace/tmp/r07-sN-coverage.json").read_text()); required=[<该slice累计changed production .py strings>]; line_pct={f:100.0*p["files"][f]["summary"]["covered_lines"]/p["files"][f]["summary"]["num_statements"] for f in required}; bad={f:v for f,v in line_pct.items() if v < 80.0}; assert not bad, bad'
```

规则：

- 每个changed production file必须用coverage JSON的 `covered_lines / num_statements` 复算line coverage并达到 `>=80%`；不能使用开启branch collection后会计入branch分母的 `summary.percent_covered` 充当line gate，也不能用aggregate平均数遮蔽低文件。
- `coverage run --branch` 继续收集branch数据供诊断；如Controller另记composite/branch指标，必须另名且不得替代上述line coverage门禁。
- 新 `_fs_identity.py`、`_fs_source_snapshot.py` 必须单列。
- `dayu/render`/`utils`例外与本R07无关。
- coverage data/JSON是本地验证产物，不stage、不commit；不得把临时Python脚本放到product/tests，若必须落脚本只能放`workspace/tmp/`。

### 8.2 pyright、Ruff、diff与full regression

每slice：

```bash
pyright dayu/ tests/ utils/
ruff check <该slice累计changed production/test Python files>
ruff check dayu tests utils --statistics
git diff --check
git status --short
git diff --name-only 5f09e2cc --
```

接受条件：

- full pyright始终 `0 errors`；不以累计cutover为由允许中间type error，不加ignore/cast/loose protocol逃避。
- changed-file scoped Ruff必须0。S3删除base两个F401后full Ruff允许最多150，且`F401<=70, E402<=66, F841<=10, F541<=3, F821<=1`；S1/S2不得超过base 152或增加任何rule/node。其它legacy failure只有§1六字段完全不变才可继承。
- `git diff --check` pass。
- diff只可含当前slice累计closed allowlist及当时Controller明确授权的review artifact；本文不授权control/design/old artifact变化。
- S3后执行§1正式全量目录pytest；新增tests使pass计数增加是预期，§1.1以外不得有failure。order-dependent logging若仍出现必须相同指纹且隔离通过。

### 8.3 source / AST / LLM scans

Identity source scan：

```bash
rg -n "_normalize_(ticker|document_id)|_list_directory_names|_published_ticker_directory_names|_parse_backup_directory_name" dayu/fins/storage tests/fins
rg -n "portfolio.*ticker|filings.*document_id|materials.*document_id|processed.*document_id|rejections.*document_id" dayu/fins/storage tests/fins
rg -n "directory_name|lock_path\.stem|child\.name" dayu/fins/storage tests/fins
```

允许项只可是：identity owner内部key/descriptor操作、ticker alias业务归一、safe filename/entry操作、明确的corruption/security test。任何raw external identity path join或目录名反推业务事实为stop。

AST audit必须输出每个storage `Path` `/` operation与f-string中包含ticker/document-id-like symbol的节点，逐项人工分类；最终除identity owner返回private key、business payload/meta serialization与error text外为0：

```bash
python - <<'PY'
import ast
from pathlib import Path

for path in sorted(Path("dayu/fins/storage").glob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        text = ast.unparse(node) if isinstance(node, (ast.BinOp, ast.JoinedStr)) else ""
        lowered = text.lower()
        if ("ticker" in lowered or "document_id" in lowered) and (
            isinstance(node, ast.JoinedStr) or (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div))
        ):
            print(f"{path}:{node.lineno}:{type(node).__name__}:{text}")
PY
```

Revision/snapshot consumer scan：

```bash
rg -n "get_source_revision|_build_source_revision|revision_before|revision_after|sha256:<|digest.*source revision" dayu/fins tests/fins dayu/fins/README.md tests/README.md
rg -n "\.digest" dayu/fins tests/fins
rg -n "get_source_(meta|document_provenance|handle)|get_(primary_)?source\(" dayu/fins/tools/read_runtime.py
rg -n "\.materialize\(" dayu/fins/pipelines dayu/fins/processors dayu/documents/processors
rg -n "_resolve_source_kind|SourceKind\.FILING.*SourceKind\.MATERIAL" dayu/fins/tools/read_runtime.py
```

期望：第一组最终0；第二组逐项分类且 `SourceDocumentRevision` / source revision字段访问的 `.digest` 残留为0（其它明确无关的digest算法不伪报）；read runtime repository旧calls为0；pipeline raw repository source materialize为0；processor内materialize仍允许但其source必须由snapshot tests证明；read runtime filing-first probe为0。

LLM-facing scan：

```bash
rg -n -i "source[_ -]?revision|storage[_ -]?key|internal[_ -]?key|local://|repo_batches|repo_backups|batch_locks" \
  dayu/fins/tools dayu/config/prompts tests/fins
rg -n "source_changed_during_read" dayu/fins
```

允许：internal implementation/test名称与 `ErrorCode.SOURCE_CHANGED_DURING_READ` owner；禁止tool schema/description/result/citation/error message暴露token/key/path。新增recursive result test必须逐一覆盖9个read tools的completed、failed、cancelled以及各自citation路径，对运行时JSON全部nested key与value递归遍历，禁止revision/private key/absolute temp path/`local://`泄露；不能只grep Python源码或只覆盖成功/失败路径。

### 8.4 真实 filesystem concurrency smoke

必须在`tmp_path`真实filesystem、真实storage repositories、真实thread/process与`threading.Event/Barrier`上运行；禁止`sleep`作为正确性oracle：

1. **A/B publication**：A、B各有至少两个互相关联文件、不同primary/meta/provenance marker；writer通过真实batch/atomic commit切换，reader在copy barrier读取。每个snapshot只允许全A或全B，不得A1+B2或A meta+B citation。
2. **短暂变化恢复**：第一次attempt fd/copy后触发一次真实B commit并停止；storage丢弃旧attempt、清temp/fd，返回完整B。只断言发生过变化且成功，不断言attempt总数。
3. **持续变化失败**：测试只在私有copy/verify seam设置barrier以协调真实A/B commits，每个attempt期间继续变化，直到storage自己的内部budget耗尽；断言唯一typed consistency failure、无cache entry、无temp/fd泄漏。monkeypatch只做调度，不复制production算法或注入测试专用policy。
4. **静态损坏优先级**：在没有任何publication/revision/descriptor变化时，用真实fd-copy barrier静默修改已打开inode内容或触发copy前后 `fstat` 变化；立即得到既有corruption/validation failure，不重试且不得映射为 `source_changed_during_read`。
5. **cache initial miss serialization**：两个线程对同revision初始cache miss并竞争同document creation lock；只构建/发布一个processor，losing调用自行取得的full snapshot被close，两个调用都借到同一matching entry。revision-change lifecycle另按下一项验证。
6. **cache lifecycle**：线程1持borrow并阻塞在processor，线程2发布B并触发evict/rebuild；旧temp在线程1release前存在且可读，release后删除；新call只见B。clear/runtime close同理。
7. **citation/result同版**：在processor result与citation构造之间发布B；当前borrow仍产出A result+A provenance，下一call产出B+B。
8. **recovery/security**：每个R06 crash phase在opaque ticker/key布局下仍只见完整old/new；descriptor/meta mismatch、symlink、filename/URI escape不触碰outside sentinel。

## 9. README 触发与写作边界

- `dayu/fins/README.md`：**必须更新**。当前第99/145/488/743行附近仍承诺consumer field-hash revision、zero-retry double-read、独立meta cache；第111行仍承诺document id单路径组件。S3完成后按其`Agent更新约束`只描述已实现current contract：storage mapping exact opaque identity、persisted published revision、single snapshot/provenance、bounded stable read、resource-aware cache、existing typed error；不写key/revision grammar、retry次数、private类名、计划/测试清单。
- `tests/README.md`：**必须更新**。将`tests/fins`当前“document id单路径组件”改为opaque mapping round-trip + filename/URI安全边界，并摘要snapshot/concurrency/cache/citation同版覆盖；不写文件级流水账。
- 根`README.md`：**不更新**。用户可见CLI、安装、工作区顶层`portfolio/`、命令、输出/排障均未改变；internal layout不属于用户手册。
- `dayu/README.md`：**不更新**。UI→Service→Host→Engine分层与Fins package位置/assembly未改变。
- `docs/fins/design.md`、control、umbrella、旧review/completion artifacts：**不更新**。它们是输入truth/history，不机械同步。

若实现实际改变最终用户命令/错误、跨层关系或design truth，当前plan失效并stop，不现场扩大README/control/design allowlist。

## 10. Review gates 与 accepted commit/handoff 闭集

### 10.1 plan gate

```text
本文 artifact-only validation
  -> Controller完整验证/allowlist裁决
  -> AgentMiMo + AgentDS 同一immutable plan双路完整review
  -> AgentCodex只修accepted plan findings
  -> Controller验证fix
  -> AgentMiMo + AgentDS双路完整re-review
  -> Controller adjudication
  -> Controller accepted-plan local commit
```

accepted plan commit闭集：本文、对应plan review/fix/re-review/controller artifacts，以及Controller自己的control transition；不得含product/tests/README/design/旧artifact或`workspace/tmp`。

### 10.2 implementation gate

每slice顺序执行：implementation handoff → Controller scope/targeted/coverage/pyright/Ruff/diff/scans/smoke验证 → MiMo/DS双路cumulative code review → accepted finding fix → Controller验证 → 双路cumulative re-review。S1/S2不得有accepted commit；S3 cumulative review就是R07完整树唯一一次双路final code review。其finding fix、Controller validation与双路complete re-review通过后，直接进入Controller adjudication与accepted implementation commit，不再重复安排等价的R07-only aggregate deepreview。

跨R01—R12的umbrella aggregate deepreview仍只在全部remediation sub-WU完成后执行；R07不得删除、提前执行或把S3 final code review冒充该umbrella gate。

accepted implementation commit闭集：§7三个slice的最终production/test/README allowlist、R07 implementation/validation/review/fix/re-review/controller artifacts及Controller control transition。不得含plan外product/test、design truth、old artifact、temporary coverage/smoke输出、R08+、Issue artifacts或统一authorization。

R07 completion commit闭集：R07 completion/final validation artifacts与Controller control transition；不重新混入product变更。实际commit、stage与control全部是Controller authority，不由本plan agent执行。

### 10.3 R08 handoff 必填闭集

完成artifact必须逐项列出：

1. accepted plan、implementation、completion SHA及parent/base；
2. 最终production/test/README exact allowlist与实际diff；
3. identity mapping semantic contract、fresh schema、descriptor corruption/collision行为，但不披露key grammar；
4. source revision publication point、全部source mutation入口与non-source preservation证据，但不披露token grammar；
5. snapshot protocol shape、source-kind ambiguity、bounded stability、typed error与resource lifecycle；
6. read/cache/citation producer-consumer图及已删除的hash/double-read/path/provider guessing清单；
7. 四个composition roots、全部producer inventory、无需修改的processor/source adapters及理由；
8. A/B、transient、sustained、cache lifecycle、citation/result同版、recovery/security真实filesystem证据；
9. 每changed production file coverage、full pyright、scoped/full Ruff delta、full pytest inherited ledger、diff/check/scans/LLM结果；
10. README decisions、security retained/modified matrix、双路review所有finding最终disposition；
11. residual owner表，明确R08只接financial/XBRL contract，不反向重做R07。

## 11. Stop conditions

任一命中立即停止当前实施/验证，保留证据并回plan review/Controller，不用fallback继续：

1. HEAD/base不是accepted `5f09e2cc`后继，或工作树出现非R07共享修改且无法隔离。
2. 正确identity/revision/snapshot/error/cache owner不清楚，或实现需要改`docs/fins/design.md`/Controller discussion裁决。
3. 需要§7 exact production/test/README allowlist之外文件；尤其generic processors、CN/SEC业务算法、Host/Service跨层contract、config/prompt/schema。
4. 任一raw external ticker/document id仍参与path/object-key/lock/backup/staging join，或list/recovery从private name反推业务identity。
5. mapping依赖旧layout、migration、双读、fallback扫描、reverse registry第二真源或test-only production seam。
6. collision/corruption/meta/manifest/descriptor mismatch不能fail closed，或错误信息/LLM结果暴露key/path。
7. revision由producer/consumer生成、根据字段hash/timestamp推断、non-source mutation误变、rollback可见或grammar被test/README冻结。
8. snapshot需要consumer before/after/retry、返回published裸Path、可混A/B、持续churn无界，或短暂变化不能恢复。
9. `source_changed_during_read`出现第二个LLM code owner、字符串解析映射，或ordinary I/O/corruption/cancel被误映射。
10. cache可返回retired/closed processor、eviction过早close active borrow、clear/process target泄漏resource，或必须依赖`__del__`正确性。
11. citation/provenance/result不来自同一snapshot，或出现speculative `BusinessSource`/provider guessing。
12. containment、symlink rejection、filename/URI拒绝、atomic write/fsync、R06 writer/publication/recovery/primary-cause/cancel语义回退。
13. targeted/changed-owner test失败、changed production file coverage<80、pyright非0、scoped Ruff非0、full Ruff新增/扩散、diff check/allowlist/source/AST/LLM scan失败。
14. full pytest出现§1.1以外failure或inherited六字段变化；ignored `workspace/tmp/r06-base-9c07b88d`不得被R07擅自删除来制造绿色。
15. 实现触及R08—R12、Issue 142/151/175/177/178、统一authorization、stage/commit/push/PR未经当前gate授权。

## 12. Residual owner

| residual | owner / future gate | R07 disposition |
|---|---|---|
| financial/XBRL producer contract与LLM质量字段 | R08 / Topic 6.4 | 不改processor业务结果，只保证输入snapshot一致 |
| direct-stream missing/duplicate/event-after-result终态validator | R09 / Topic 6.5 | 不改ingestion terminal语义 |
| HKEX cumulative `rowRange`完整性 | R10 / Topic 6.6 | 不改downloader |
| upload shell/cmd workflow与placeholder surface | R11 / Topic 7.1/7.2 | 不改CLI/packaging |
| current-schema init/secret/atomic reset | R12 / Topic 7.3 | 不改init/runtime config |
| workspace migration/future assets | Issue 142/151 | fresh schema，不迁移 |
| Fins long-operation process isolation | Issue 175 | 只关闭read process target snapshot资源 |
| output continuation/TruncationManager | Issue 177 | 不接通 |
| credential storage-state lifecycle | Issue 178 | 不触碰 |
| unified tool authorization | 无当前授权；仍是显式deferred | 不创建新WU/framework |
| base full-suite Service配置/import与logging order failures | 各现有Service/Runtime owner；§1.1 ledger | 不修、不豁免，只防扩散 |
| private key/revision算法未来演进 | storage owner | 只要descriptor round-trip/opaque equality contract不变，可在fresh schema future work调整；R07不把grammar承诺给consumer |

## 13. 本 plan gate 最终状态

plan fix完成后只允许Controller读取本文与fix artifact，复核内容SHA-256、`git diff --check`、scope、HEAD与`git status --short`。不得进入implementation、re-review、control或commit；双路complete re-review必须等待Controller validation另行授权。

**状态：PLAN_FIX_COMPLETE / READY_FOR_CONTROLLER_VALIDATION**
