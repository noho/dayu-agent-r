# WU-SEMANTIC-OWNERSHIP-01 R06-S2 累计 Code Re-Review — 第二路 (DS)

## 1. 审查身份与范围

- **审查者**: AgentDS（第二路 re-reviewer）
- **Work unit**: 同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R06-S2 累计 checkpoint；不是新 WU，不进入 S3
- **审查基线**: `d048adf7ec1135aaf575384432ebf1137f8a34f2` → 当前完整未暂存 working tree（累计 S1+S2 + code-review fix）
- **只允许写入本 artifact**: `docs/reviews/wu-semantic-ownership-01-r06-s2-code-rereview-ds.md`
- **不修改 product/test/control/design/他人 artifact，不 stage/commit/push**

### 1.1 裁决优先级（已完整读取并逐文件应用）

1. `AGENTS.md`
2. `docs/host/issues-implementation-control.md` 当前 R06 rows
3. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
4. `docs/fins/design.md`
5. `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`（accepted R06 plan）
6. `docs/reviews/wu-semantic-ownership-01-r06-s2-implementation-codex.md`（S2 implementation）
7. `docs/reviews/wu-semantic-ownership-01-r06-s2-controller-validation.md`（S2 controller validation）
8. `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-ds.md`（S2 initial DS review）
9. `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-controller-adjudication.md`（S2 controller adjudication: FIX REQUIRED）
10. `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-fix-codex.md`（fix implementation）
11. `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-fix-controller-validation.md`（fix controller validation: PASS）
12. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-ds.md`（S1 initial DS review）
13. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-controller-adjudication.md`（S1 controller adjudication）
14. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-ds.md`（S1 DS re-review: PASS）
15. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-controller-adjudication.md`（S1 controller re-review adjudication: PASS）

### 1.2 审查方法

- 完整走读所有累计 S1（15 production）与 S2（7 authored production）文件的当前 working tree 状态
- 逐项对 R06-S2-CR-F01 做直接代码证据证伪/确认：`_resolve_primary_uri` 本体、两个 production caller、owner test、public contract test
- 逐一复验 R06-S1-CR-F01..03 在 S2 cumulative tree 中保持关闭
- 对 S2 blob-first、final complete source、prepublication validator、failure token consumption、old preservation、reader barrier 逐项回归
- 独立运行四个累计 allowlist tests、scoped pyright、full pyright
- 执行 ambient authority、storage acknowledgement/false-completion、first-file fallback、compat shim、Issue boundary crossing、R07 snapshot/revision boundary 精确扫描
- 执行 public read self-call AST 扫描、`git diff --check` 检查

## 2. Verdict

**PASS**

current material finding = **0**，blocking question = **0**。

累计 S1+S2 tree 的 R06-S2-CR-F01 在唯一 `_resolve_primary_uri` owner 正确闭合。R06-S1-CR-F01..03 全部保持关闭。S2 全部 owner contract 无回归。无 ambient authority、first-file fallback、compat shim、统一 authorization 或 Issue 142/151/175/177/178 越界。

**READY_FOR_CONTROLLER_ADJUDICATION**

## 3. R06-S2-CR-F01 逐项闭合确认

### 3.1 状态：CLOSED

Controller accepted finding 要求：`_resolve_primary_uri` 只在显式 primary name 精确命中文件时返回 URI，missing/mismatch 返回 `None`；不得在 caller 补条件、不得放宽 validator、不得添加兼容分支。

### 3.2 唯一 owner（`_resolve_primary_uri`）直接代码证据

`dayu/fins/storage/_fs_storage_utils.py:396-416`：

| 检查项 | 结论 | 直接证据（行号） |
| --- | --- | --- |
| primary_name 缺失返回 `None` | **PASS** | line 410-411: `if not primary_name: return None` — 空/None/falsy 统一返回 None |
| primary_name 非空且精确命中 entry name → 该 entry URI | **PASS** | line 412-415: for 循环精确 `name == primary_name` 比较，命中返回 `str(item.get("uri"))` |
| primary_name 非空但未精确命中 → `None` | **PASS** | line 416: `return None` — 遍历完所有条目无命中后显式返回 None |
| 无 `file_payloads[0]` first-file fallback | **PASS** | 全文 `file_payloads[0]` scan: `0` 命中 |
| 无 `file_payloads[0].get("uri")` 猜测 | **PASS** | 旧 line 417 fallback 已删除 |
| docstring 与实现一致 | **PASS** | line 404: `Returns: 主文件 URI；若未找到返回 None` |

### 3.3 Caller 无补偿

`dayu/fins/storage/_fs_source_document_core.py` 两个 production caller：

| Caller | 检查项 | 结论 | 直接证据（行号） |
| --- | --- | --- | --- |
| `_upsert_source_document` | 无条件补偿 | **PASS** | line 1339-1343: `_resolve_primary_uri(...) if selected_primary_document is not None else None` — 仅当 primary 已确定时才调用，不额外补条件 |
| `_toggle_source_deleted` | 无条件补偿 | **PASS** | line 1416-1418: `_resolve_primary_uri(file_payloads, str(meta.get("primary_document", "")).strip() or None)` — 直接传播结果，不补偿 |
| 两个 caller | 不修改 `primary_file_uri` 赋值 | **PASS** | 均写入 `DocumentHandle.primary_file_uri`，类型 `Optional[str]` 已接受 None |
| 两个 caller | 不绕过 None 另取路径 | **PASS** | 无 `if primary_file_uri is None: primary_file_uri = ...` 补偿 |

### 3.4 Commit validator 未放宽

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| validator 仍独立校验 primary | **PASS** | `_fs_storage_infra.py:644-649`: `primary_document` 必须非空且精确命中 `file_names` |
| 无 first-file primary fallback | **PASS** | `_select_primary_document`（line 1714-1736）只接受 explicit_primary 或 previous_primary，两者均无效返回 None |
| validator failure → fail closed | **PASS** | commit_batch 的 outer `except`（line 381-386）调用 `_rollback_precommit_batch` + `_close_active_batch` |

### 3.5 Owner 与 public contract tests

| 测试 | 覆盖 | 结论 | 直接证据 |
| --- | --- | --- | --- |
| `test_primary_uri_owner_requires_exact_explicit_primary_name` | exact match 成功 + mismatch→None + primary缺失→None | **PASS** | `test_fins_storage_atomicity.py:700-719` — 三格全部断言 |
| `test_final_source_rejects_wrong_primary_keeps_old_absent_or_present` | 错误 primary→`primary_file_uri is None` + validator fail closed + token 已消费 + old 保留 | **PASS** | `test_fins_storage_provider.py:1391-1405` — `projected_handle.primary_file_uri is None`、`commit_batch` 抛出 `primary_document 未精确命中 files`、二次 rollback 被拒、old source/blob 不变 |
| `test_material_create_with_explicit_primary_hits_exact_match_and_completes_lifecycle` | exact match create → `primary_file_uri == file_meta.uri` | **PASS** | `test_fins_storage_atomicity.py:633` — 精确命中断言 |
| logical delete/restore | 保持 | **PASS** | material lifecycle test 含既有 delete/restore 断言 |

## 4. R06-S1-CR-F01..03 关闭回归确认

逐项验证全部 S1 accepted findings 未被 S2 code-review fix 回退：

### 4.1 R06-S1-CR-F01 — maintenance read graph: CLOSED 保持

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| public entry 只做 normalize + guard + delegate + release | **PASS** | `_fs_maintenance_core.py:401-411`: `_normalize_ticker` → `_normalize_document_id` → `_acquire_publication_guard` → `_read_rejected_filing_file_bytes_unguarded(...)` → `finally: _release_lock_token` |
| private helper 拥有全部 path/branch/I/O | **PASS** | line 436-445: `_rejected_filing_file_path_for_read`、exists/is_dir/read_bytes——全部在 unguarded helper |
| 无 ambient "guard held" marker | **PASS** | helper 签名只有三个显式 `str` 参数 |
| 无 public read self-call | **PASS** | AST scan: `[]` |

### 4.2 R06-S1-CR-F02 — processed meta 唯一读取 contract: CLOSED 保持

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| docstring 只承诺 `tool_snapshot_meta.json` | **PASS** | `_fs_processed_core.py:184`: `只读取 published ``tool_snapshot_meta.json``。` |
| 实现只读取一个路径 | **PASS** | line 227-230: 只从 `_PROCESSED_META_FILENAME` 构造路径 |
| 无 "meta.json" fallback | **PASS** | full fallback wording scan: 0 命中 |
| `_PROCESSED_META_FILENAME` 只有一个值 | **PASS** | `_fs_storage_utils.py`: 唯一 `"tool_snapshot_meta.json"` |

### 4.3 R06-S1-CR-F03 — reprocess marker 统一 None: CLOSED 保持

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| protocol 声明 `-> None` | **PASS** | `repository_protocols.py`: `) -> None:` |
| wrapper 声明 `-> None` | **PASS** | `fs_processed_document_repository.py`: `) -> None:` |
| core public 声明 `-> None` | **PASS** | `_fs_processed_core.py:241`: `) -> None:` |
| core private impl 声明 `-> None` | **PASS** | `_fs_processed_core.py:268`: `) -> None:` |
| `required=False` no-op 返回 `None` | **PASS** | line 259-260: `if not required: return` |
| 无生产返回值消费者 | **PASS** | 全仓 production call 均为 statement expression |

### 4.4 S1 全量 owner contract 回归

| S1 contract | S2 回归状态 | 直接证据 |
| --- | --- | --- |
| opaque BatchToken（仅 `transaction_id` + `ticker`） | **保持** | `document_models.py:415-424`，`frozen=True` |
| registry-only mutation authority | **保持** | `_resolve_active_batch`（line 919-959）不检查 ContextVar、task/thread identity |
| writer/publication lock 分离 | **保持** | 两个不同锁文件，锁序 writer → publication |
| published/private read graph | **保持** | AST public self-call scan: `[]`；全部 public read outer guard + private unguarded |
| LocalFileSource delayed opener | **保持** | `_PublicationGuardedBinaryOpener`（line 97） + `_publication_guarded_binary_opener`（line 1160） |
| minimal journal（三字段） | **保持** | `_JOURNAL_FIELDS = frozenset({"transaction_id", "ticker", "phase"})` |
| VF-01..04 recovery/error precedence | **保持** | 全部对应代码路径未变更 |
| containment/symlink | **保持** | `_normalize_path_component`、`_require_contained_path`、`_is_contained_recovery_path` 不变 |

**结论**: S2 code-review fix 未回退或放宽任何 S1 accepted finding。全部 CLOSED 保持。

## 5. S2 Complete-Source Contract 回归确认

### 5.1 Blob-first staging

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| SourceHandle blob 写不要求 meta | **PASS** | `_fs_blob_core.py:214-215`: `isinstance(handle, ProcessedHandle)` 守卫——只有 ProcessedHandle 调用 `_get_handle_meta_for_state` |
| ProcessedHandle 仍要求 meta | **PASS** | 同上，processed 路径不变 |
| 入口只校验 batch authority | **PASS** | `store_file` → `_resolve_active_batch`（line 180），不做 SourceHandle meta 存在性检查 |

### 5.2 Final complete source — typed provenance + true completion

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| `_prepare_complete_source_meta` 强制 `ingest_complete=True` | **PASS** | `_fs_source_document_core.py:1447-1454`: `meta.get("ingest_complete", True)` → 显式 false → `ValueError` → `normalized["ingest_complete"] = True` |
| typed provenance 校验 | **PASS** | line 1455: `SourceDocumentProvenance.from_meta(...)` — 未知 method/provider 由 Enum 构造抛出 |
| 三个 mutation entry 统一收敛 | **PASS** | `_upsert_source_document:1319`、`_toggle_source_deleted:1392`、`replace_source_meta:695` — 全部调用 `_prepare_complete_source_meta` |

### 5.3 Prepublication validator

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| validator 在 publication guard 前运行 | **PASS** | `_fs_storage_infra.py:345-346`: `_validate_complete_source_tree(state)` → 通过后才 `_acquire_publication_guard` |
| 完整遍历 staged ticker tree | **PASS** | validator 枚举 filing + material 两个 source root 全部子目录 |
| 双向 source↔manifest | **PASS** | `source_ids - manifest_ids` + `manifest_ids - source_ids` |
| 双向 files↔physical | **PASS** | 每条 file 校验 physical regular file; 反向遍历 directory children |
| 22 格 failure matrix | **PASS** | meta/files/primary/provenance/manifest/URI/size/sha/symlink/escape/dangling——全部 fail-closed |

### 5.4 Failure token consumption

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| validator failure → token 消费 | **PASS** | commit_batch outer `except`（line 381-386）→ `_rollback_precommit_batch` + `_close_active_batch` |
| 二次 rollback 被拒绝 | **PASS** | `_close_active_batch` 先 pop registry（line 982），再释放 writer lock |
| caller 不二次 rollback | **PASS** | public contract test 覆盖：commit 失败后 rollback 抛出 `未在当前 storage core 登记` |

### 5.5 Old preservation

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| validator 失败 → old target 保留 | **PASS** | `_rollback_precommit_batch` 从 backup 恢复 old target（line 850-853） |
| published reader 在 validator 期间读到 old | **PASS** | `test_concurrent_published_read_ignores_long_writer_staging_and_sees_old` 通过 |
| old-absent 格 | **PASS** | 新 source validator 失败 → `list_source_document_ids` 为空、meta/blob 不可见 |

### 5.6 Reader barrier

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| reader 在长 staging/validator 不阻塞 | **PASS** | 测试在 1s deadline 内读到 old |
| reader 在两个 rename barrier 阻塞 | **PASS** | `test_concurrent_reader_blocks_at_each_publication_rename_barrier` 通过 |
| barrier 释放后只见 old/new 完整 | **PASS** | 同上，不观察 missing/half |

### 5.7 Commit 顺序

| 步骤 | 保护 | 证据 |
| --- | --- | --- |
| lifecycle → commit_started | registry | line 338 |
| validator 遍历 | 无 publication guard | line 345 |
| acquire publication guard | short swap window | line 346 |
| target→backup → journal | guard 内 | line 349-351 |
| staging→target → journal | guard 内 | line 352-353 |
| journal COMMITTED → release guard | guard 内/释放 | line 354, 361-364 |
| cleanup + close batch | registry | line 388-391 |

## 6. Adversarial 扫描与边界检查

### 6.1 Ambient authority

| 扫描目标 | 命中 | 归属 |
| --- | ---: | --- |
| `ContextVar`、`_BATCH_OWNER_CONTEXT`、`owner_scope_id`、`owner_token` | 0 | — |
| `asyncio.current_task()`、`threading.get_ident()`、`thread.*ident` | 0 | — |
| `_execute_with_auto_batch`、`auto_batch` | 0 | — |
| `_require_batch_owner`、`_bind_batch_owner`、`_unbind_batch_owner` | 0 | — |

### 6.2 Storage acknowledgement/false-completion

| 扫描目标 | 命中 (storage) | 命中 (all) |
| --- | ---: | ---: |
| `stage_source_document` | 0 | 7（全部在 S3 deferred test files: `test_docling_upload_service.py`、`test_sec_pipeline_download_stream.py`） |
| `_STAGING_STABLE_META_FIELDS` | 0 | 0 |
| `staging.*ack`、`acknowledge_source` | 0 | 0 |
| `ingest_complete.*false\|ingest_complete.*False` (storage) | 0 | — |

Aggregate ack scan 的 35 命中精确归因：14 条 S3 producer、15 条 S3 tests、4 条 README 旧叙述、2 条 fail-closed owner tests。无 storage owner 残留。

### 6.3 First-file fallback / compat shim

| 扫描目标 | 命中 |
| --- | ---: |
| `file_payloads[0]` primary fallback | **0**（已从 `_resolve_primary_uri` 删除） |
| `setdefault(primary\|completion)` | **0** |
| `files[0]` primary 选择 | **0** |
| `hasattr`/`getattr` in storage | **0** |
| `compat`/`shim`/`fallback`/`re-export` in storage | **0** |

### 6.4 统一 authorization / Issue 边界

| 扫描目标 | 命中 |
| --- | ---: |
| `authorization`/`authorize`/`permission`/`role_based` in storage | **0** |
| `Issue.*142\|Issue.*151\|Issue.*175\|Issue.*177\|Issue.*178` in storage owner files | **0** |
| `process.isolation\|subprocess\|child.process` in storage | **0** |
| `TruncationManager\|truncation\|max_source_bytes\|input.budget` in storage | **0** |
| `snapshot\|revision\|selector\|retry.*read\|lease.*api\|opaque.*id.*map` in storage | **0** |

### 6.5 Public read graph self-call

AST scan 对所有 `_fs_*_core.py` 中 `self.get_*`/`self.load_*`/`self.list_*`/`self.read_rejected*` 调用: **`[]`**。

### 6.6 git diff

`git diff --check d048adf7ec1135aaf575384432ebf1137f8a34f2 --`: **通过**。Staged diff: **空**。

## 7. 独立验证证据

| 证据类型 | 结果 |
| --- | --- |
| 四个累计 S1/S2 allowlist tests 完整运行 | `235 passed, 3 warnings in 9.60s` |
| 3 条 warning 来源 | 第三方 `edgar` deprecated imports，非本 gate 新增 |
| Scoped pyright（storage/ + 4 tests） | `0 errors, 0 warnings, 0 informations` |
| Full pyright | `108 errors, 0 warnings, 0 informations`（全部精确归属 S3 deferred） |
| Ambient authority scan | `0` 命中 |
| Storage acknowledgement scan | `0` 命中 |
| First-file fallback scan | `0` 命中 |
| Compat shim scan (`hasattr`/`getattr`/compat keywords) | `0` 命中 |
| Unified authorization scan | `0` 命中 |
| Issue boundary crossing scan (142/151/175/177/178) | `0` 命中（in storage owner files） |
| R07 boundary scan (snapshot/revision/selector) | `0` 命中 |
| Public read self-call AST | `[]` |
| `git diff --check` | pass |
| Staged diff | 空 |
| Changed files from baseline | 20 files（16 production + 4 tests）— 全部在 accepted plan allowlist |
| Coverage（逐文件） | `82.62%`-`100%`（全部 ≥ 80%） |

## 8. Full pyright 108 与 ack residual 归因

Full pyright `108 errors` 与 accepted S2 baseline 完全一致，changed owner/test 命中 0：

- 63 项: mutation 缺 required `batch`（S3 producer/callback）
- 27 项: producer/test fake 调已删除 lifecycle（S3 propagation）
- 4 项: 引用已删除 `stage_source_document`（S3 propagation）
- 12 项: callback/override 缺 explicit batch（S3 propagation）
- 2 项: 测试读旧 `token_id`（S3 propagation）

Aggregate ack scan 35 命中同样精确归因于 S3 producer/tests、README 旧叙述和 fail-closed owner tests。

这些都是 **accepted R06-S3 residual**，不是 S2 re-review finding。S2 owner 边界无 ack/ambient/fallback 残留。

## 9. 与第一路 Re-Review (MiMo) 的交叉验证

本路独立审查确认 MiMo 的 PASS 结论成立。两路在以下关键点上一致：

- R06-S2-CR-F01 在唯一 `_resolve_primary_uri` owner 闭合；missing/mismatch→None、exact match 保留
- R06-S1-CR-F01..03 全部保持关闭，无回归
- Blob-first staging、final complete source、prepublication validator 全部保持
- 无 ambient authority、first-file fallback、compat shim、统一 authorization
- 无 Issue 142/151/175/177/178 或 R07 snapshot/revision 越界
- Scoped pyright 0、full pyright 108（S3 residual，不变）
- 235 tests passed
- `git diff --check` 通过

## 10. Residual Risk

1. **S3 producer propagation**: full pyright 108 与 aggregate ack scan 35 是 S3 唯一已知传播风险。S3 cumulative tree 必须清零。

2. **R07 snapshot/revision**: 8 个 production 文件/9 个 `.materialize()` 调用点在拿到裸 `Path` 后的延迟/多次读取没有 snapshot consistency。这是 accepted R06 plan 的显式 R07 residual，R06 publication guard 只保证单次 read/open 的 old/new 完整性。

3. **README 旧叙述**: `dayu/fins/README.md` 和 `tests/README.md` 的旧 acknowledgement 描述保留到 S3/final cumulative tree 同步更新。这是 accepted S2 checkpoint 的有意决定，不是 finding。

4. **`_select_primary_document` 的 `previous_primary: Any`**: 既有 JSON 反序列化边界类型。本轮未触及该参数，也不是当前 S2 finding。

5. **测试对 `_ActiveBatchState` 私有字段的依赖**: crash-injection 测试需要内部物理 layout。这是 accepted S1 intentional design，不影响生产行为。

## 11. 最终 Ledger

| 类别 | 数量/状态 |
| --- | --- |
| material finding | **0** |
| blocking question | **0** |
| R06-S2-CR-F01 | **CLOSED**（唯一 owner 闭合，missing/mismatch→None，exact hit 保留，无 caller/validator 补偿） |
| R06-S1-CR-F01 (maintenance read graph) | **CLOSED 保持**（0 回退） |
| R06-S1-CR-F02 (processed meta contract) | **CLOSED 保持**（0 回退） |
| R06-S1-CR-F03 (reprocess marker None) | **CLOSED 保持**（0 回退） |
| S1 全量 owner contract | **全部保持**（opaque token、registry authority、lock order、read graph、journal、recovery、VF-01..04、containment） |
| S2 blob-first / final complete source / validator / token consumption / old preservation / reader barrier | **无回归** |
| ambient authority / first-file fallback / compat shim / unified authorization | **0 命中** |
| Issue 142/151/175/177/178 boundary | **0 越界**（in storage owner files） |
| R07 snapshot/revision boundary | **0 越界** |
| full pyright 108 / ack 35 | **accepted S3 residual**（未误报为 S2 finding） |
| Verdict | **PASS** |

**READY_FOR_CONTROLLER_ADJUDICATION**
