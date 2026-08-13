# Code Review — UF-FIX02 Aggregate Deepreview（AgentDS）

## Scope

- Mode: current changes（aggregate：覆盖起点到 HEAD 的 UF-FIX02 全部 commits 与 artifacts）
- Branch or PR: `codex/upload-filing-oracle`（本地未提交，无 PR）
- Base: `114430ce312ca6d8eb9c9f4cb7bb0a1f0bdba5a0`（冻结起点）
- HEAD: `8b0775f7e824c30aae4f7965c2c2aebf425cbabe`；工作树 clean
- Output file: `docs/reviews/code-review-20260813-191952-uf-fix02-aggregate-ds.md`
- Included scope（38 files, 4900+/136-）:
  - 生产：`dayu/fins/pipelines/docling_upload_service.py`（81 行变更）、`dayu/fins/storage/source_meta_contract.py`（新 35 行）、`dayu/fins/storage/_fs_source_snapshot.py`（27 行）、`dayu/fins/storage/__init__.py`（2 行）、`dayu/fins/ingestion_runtime.py`（1 行 usage message）
  - README：根 `README.md`、`dayu/fins/README.md`、`tests/README.md`
  - 测试：`tests/fins/test_docling_upload_service.py`、`tests/fins/test_sec_pipeline_upload_filing_stream.py`、`tests/fins/test_cn_pipeline.py`、`tests/fins/test_source_meta_contract.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/cli/test_fins_commands.py`
  - Gateflow/review artifacts：goal confirmation、plan、S1/S2 implementation/fix/adjudication、历次 DS/MiMo review（只读核对，未修改）
  - 沿真实主链路走读（非 diff 面）：`_fs_source_document_core.py`（`_upsert_source_document`/`_toggle_source_deleted`/`_reset_source_document_impl`/`_prepare_complete_source_meta`）、`fs_source_document_repository.py`、`fs_batching_repository.py`、`_fs_blob_core.py`、`_fs_storage_infra.py`（blob key/handle 目录）、`_fs_filing_upload_state_core.py`、`source_integrity.py`、`sec_upload_workflow.py`、`cn_pipeline.py`（filing+material 两条 stream）
- Excluded scope: UF-FIX03–08/10/11、UF-PF03–PF12（已分类非目标，per goal confirmation）；MiMo 并行 aggregate artifact（只读，未修改）
- Parallel review coverage: 无（单人完整走读；与 MiMo aggregate 仅交叉核对 predicates 清单，结论独立形成）
- Review date/time: 2026-08-13（系统时钟生成 artifact 时间戳 20260813-191952）

## Verdict

**PASS**

## Findings

未发现实质性问题。

逐项核验结论（每项含直接证据；无一条达到可绑定 file:line + 可复现场景 + owner 的 finding 标准）：

### 1. action-core：update admission 与 overwrite 解耦

- `evaluate_upload_overwrite_precondition`（`docling_upload_service.py:182-188`）对 `action == "update" and previous_meta is None` 无条件返回 `UPDATE_TARGET_MISSING`，`overwrite` 不再提供 upsert 权限；`prepare_upload:299-300` 在文件读取与 Docling 转换前 raise `FileNotFoundError`。
- 唯一 validator 入口 `validate_fins_upload_filing_request`（`ingestion_runtime.py:969-977`）在 conversion 前把该 disposition 映射为 typed `FinsUploadUsageCode.UPDATE_TARGET_MISSING`；usage message 同步改为“请改用 create”（`ingestion_runtime.py:753`），CLI 测试断言新文案与 exit 2。
- 测试：`test_prepare_upload_rejects_missing_update_before_shared_conversion`（filing/material × overwrite False/True，converter 0 calls）、`test_upload_filing_fresh_missing_update_fails_before_conversion`（CN/HK，±overwrite，conversion/batch 零调用）、CLI `test_upload_filing_state_conflict_exits_before_service_factory_without_mutation`（update-missing ±overwrite、create-existing，exit 2 + 零 mutation）。

### 2. renamed-update：update identity 不依赖 basename

- SEC/CN filing identity 由 `build_sec_filing_ids`/`build_cn_filing_ids` 从 ticker/year/period/amended 派生（`docling_upload_service.py:1215-1285`），material 由 `build_material_ids` 从 form_type/material_name/fiscal 派生，均不读文件名。
- fingerprint 含文件名（`_build_upload_source_fingerprint:1013-1023`），改名即 fingerprint 变化 → 不 skip → `_resolve_document_version` 递增 → replace。
- `_store_upload_assets:477-488`：`replace_existing = previous_meta is not None and (action == "update" or (action == "create" and overwrite))`，renamed update 无需 overwrite 即走 reset→create。
- 旧文件物理残留不可能：`_reset_source_document_impl`（`_fs_source_document_core.py:1319-1386`）删除整个 document_dir + manifest 条目；blob 物理路径与 source meta 同目录（`_fs_storage_infra.py:1967-1972` handle 目录、`:2254-2259` blob key 均在 `{ticker}/{source_kind}/{document_id}/` 下）。
- 测试：SEC `test_upload_filing_stream_renamed_update_without_overwrite_replaces_complete_set`（published names 精确 = `[q1_renamed.pdf, q1_renamed_docling.json]`，非目标 sibling filing 与 company tree 不变）、CN `test_upload_filing_stream_auto_resolves_create_update_skip`（renamed update 后 names 精确）、service `test_execute_upload_existing_full_input_replaces_exact_complete_set`。

### 3. auto-after-delete：auto 恢复 deleted

- `resolve_upload_action`（`:1190-1212`）对 previous_meta 非 None 的 deleted source 解析 update；filing fresh state 对逻辑删除仍返回含 `is_deleted=True` 的 meta（`_fs_filing_upload_state_core.py:88-96` 只按 meta 文件存在性）。
- `_can_skip_upload:994-995`：`require_source_meta_is_deleted(previous_meta)` 为 True 时强制不 skip（equal fingerprint 也进入 conversion）。
- `_build_upsert_meta:785-786` 显式写回 `is_deleted=False`、`deleted_at=None`；storage `setdefault("is_deleted", False)`（`_fs_source_document_core.py:1703-1704`）不覆盖。
- 测试：SEC `test_upload_filing_auto_after_delete_republishes_active_source`（equal/changed 均 ok、action=update、state 恢复 active）、service `test_execute_upload_deleted_input_republishes_complete_source`（filing equal/changed + material equal：is_deleted False、deleted_at None、version v2-or-keep、first_ingested_at/created_at 保留、integrity COMPLETE）。

### 4. fresh conflicts pre-conversion（UF-FIX01 无回归面）

- SEC/CN workflow 在 prepare 前经同一 `FilingUploadStateRepositoryProtocol` 重读 fresh state 并重跑 `validate_fins_upload_filing_request`（`sec_upload_workflow.py:167-175`、`cn_pipeline.py:787-795`），`_assert_authoritative_filing_identity` 核对 identity 不变；stale preflight 的 action/company decision 被丢弃。
- 测试：SEC `test_upload_filing_fresh_create_existing_fails_before_conversion_and_batch`（stale create-existing typed `CREATE_TARGET_EXISTS`、converter/batch 零调用、published tree SHA 不变）、CN stale update-missing（同上）。
- UF-FIX01 全套测试（含 frozen argv、prevalidation corruption、batch identity）全部通过（见验证记录），无回归。

### 5. exact complete-set atomic replacement

- 替换全流程在 caller-owned batch 内：`reset_source_document` → blob-first `store_file(…, batch=batch)` → `create_source_document(…, batch=batch)`，commit 时整体发布（`fs_batching_repository.py:63-81` 物理 swap）；published 只观察完整 old 或完整 new。
- 唯一 final source mutation 是 create（`_create_source_document`，`:789-836`）；`_resolve_upsert_mode` 与 `update_source_document` 死路径已删除且全仓无残留引用。
- reset 前 `previous_meta` 是 version/first_ingested_at/created_at 真源（`:773-780` 在 reset 前的 `_build_upsert_meta` 内派生；`_PreparedAssetMutation.previous_meta` 在 publish 前已持有）。
- 失败/取消原子性：`commit_prepared_upload_batch:868-892` 的 precommit 取消或异常走恰好一次 rollback，commit 开始后不再读取消。
- 测试：`test_existing_replacement_blob_failure_keeps_entire_published_tree`（fail_at 1/2，整树 SHA 不变）、`test_existing_replacement_cancellation_keeps_entire_published_tree`（cancel_at 2/4/5，整树 SHA 不变）、`test_execute_upload_update_failure_keeps_previous_document`（final create 失败，`create_failed` + 整树 SHA 不变）。

### 6. UF-FIX01 contracts 无回归

- `ingestion_runtime.py` 仅改一行 usage message；validator 结构、typed code、fresh recheck、零 mutation、batch identity、closed failure projection 均未被触及。
- 全部受影响测试 329 passed（203 + 126）；pyright 0 errors。

### 7. semantic ownership drift / 过度耦合 / public contract

- `is_deleted` 严格读取从 `_fs_source_snapshot._require_deleted_flag` 私有函数提升为 storage 公共契约 `source_meta_contract.require_source_meta_is_deleted`（`dayu.fins.storage.__init__` 导出、`dayu/fins/README.md` 记录 owner 语义）；snapshot（`_fs_source_snapshot.py:765,1089`）与上传 skip（`docling_upload_service.py:994`）两消费者复用同一 helper，字段缺失/非 bool fail-closed 不使用默认值或 loose truthiness。方向为收束而非漂移。
- `created_at`/`first_ingested_at` 保留唯一落在 reset 前持 `previous_meta` 的 `_build_upsert_meta` owner boundary（S2 code-review-fix 已裁决），storage 侧 `setdefault` 不形成第二真源。
- 依赖方向 pipelines → storage 公共契约，朴素直接传参，无反向依赖、无跨层穿透；SEC/CN/HK 与 material 共享同一 `DoclingUploadService` owner，无规则复制。
- 审计：changed 文件内无新增 `hasattr`/`getattr`/lazy import/兼容分支；被删符号（`_resolve_upsert_mode`、`_require_deleted_flag`）全仓无残留引用。

### 8. SEC/CN/HK propagation 与 material parity

- SEC 与 CN/HK filing 路径对称且均测试覆盖（renamed update、stale conflict、auto-after-delete）；HK 走 CN facade（market != US → `build_cn_filing_ids`）。
- material 只要求 shared-owner parity（plan 明确 non-goal：不新增 material typed usage），两个最小 owner 测试已覆盖（update-missing pre-conversion 失败、deleted equal 恢复）；material workflow 生产代码未改。

### 9. LLM-facing / README / typed error

- 无 prompt/tool schema 变更；usage message 为 CLI 用户可见文本且与实现同步。
- 根 README 新增一段用户可读语义说明（update 不 upsert、auto 恢复 deleted、完整集合原子替换、取消保留旧集合），与实现逐句一致（逐项核对见 1/2/3/5）。
- `dayu/fins/README.md` 记录 `require_source_meta_is_deleted` 契约与 mutation/complete-source 语义更新；`tests/README.md` 记录 S2 owner/workflow coverage。
- 新契约异常（KeyError/ValueError）在 pipeline 中经既有 typed failure projection 收敛为 closed failure，README 声明 fail-closed。

### 10. tests-first 与测试有效性

- S1/S2 fix artifacts 均记录 tests-first RED：update-missing ±overwrite（S1）、created_at 六参数集 6 failed（S2），RED 直接证明 root cause 后才改生产代码。
- 测试断言 owner 级 contract：published tree SHA-256 全量比对、typed usage code、converter/batch 零调用、确定性双时钟（`_set_upload_clock` monkeypatch upload owner 与 storage 两侧时钟，杜绝同秒假绿）、真实 FS 仓储种数据（CLI 测试经 `_seed_cli_filing_source` 走真实 storage API，非 fake 固化偶然行为）。
- 断言未为适配实现而削弱：deleted restore 同时断言 version 语义、first_ingested_at/created_at 保持、integrity COMPLETE；rename 替换断言 published names 精确集合而非仅“包含新文件”。

### 11. no-touch / scope / compat 审计

- 生产变更仅 5 个文件，全部属于 UF-FIX02 范围；无 UF-FIX03–08/10/11 内容混入（per-commit stat 核对：08316516 与 8b0775f7 的变更面与 gateflow 记录一致）。
- 无生产/测试/既有 artifact 修改（本 review 仅新增本文件）；MiMo 并行 artifact 未触碰。

## 验证记录（独立重跑）

- `pytest tests/fins/test_docling_upload_service.py tests/fins/test_source_meta_contract.py tests/fins/test_fins_ingestion_runtime.py`：**203 passed**
- `pytest tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/cli/test_fins_commands.py`：**126 passed**
- `pyright`：**0 errors, 0 warnings**
- coverage（本机独立实测）：`docling_upload_service.py` 83%（391 stmts）、`ingestion_runtime.py` 90%（2134 stmts）；`source_meta_contract.py` 由 S1/S2 gateflow 记录的独立 mktemp 证据为 100%。均 ≥80% 门槛。
- 环境噪声（非本 diff）：pytest-cov 组合收集时 pandas/numpy import 链报 `ImportError: Unable to import required dependency numpy`，同一测试无 coverage 全部通过、单模块 coverage 可正常产出；属验证工具环境现象，已记录不复现深挖。

## Open Questions

无。

## Residual Risk

- **baseline residual，非本 diff 引入或恶化**：
  - `read_runtime.py:643`、`ingestion_runtime.py:5102`、`cn_download_rebuild.py:151`、`sec_rebuild_workflow.py:395` 仍各自 loose parse `is_deleted`（`bool(meta.get("is_deleted", False))` 等），未收束到 `require_source_meta_is_deleted`；upload/snapshot 消费面已 fail-closed，这些消费面的 fail-open 行为与新旧契约的语义一致性差异属于后续已分类 WU 范畴。
  - material 显式 `create` 命中已存在目标（未 overwrite）：fingerprint 相同时返回 skipped、不同时在转换后由 storage `FileExistsError` 收敛为 failed event，无 typed usage admission（与 base 行为等价，plan 明确 material typed usage 归 UF-PF12）。
  - fresh state 读取与 `begin_batch` 之间不存在 optimistic revision 校验（same-request concurrency 为 UF-FIX02 non-goal）；per-ticker writer reservation 保证 staging 一致性，替换方向为 fail-safe（update 可能退化为 create 成功或 storage 层失败）。
- 环境：pytest-cov 组合运行受 pandas/numpy 插件 import 干扰，coverage 证据依赖单模块或独立运行方式。
