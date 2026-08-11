# AgentDS Deep Review — WU-CLI-DOWNLOAD-01 Slice 4

- **Reviewer**: AgentDS（第二路独立 review）
- **Date**: 2026-08-10
- **Baseline**: `afde13dfeeb50f18bb35364ee15d8dcd23a7bcc2`
- **Scope**: 当前未提交 working tree diff（20 files, +3358/-1195）
- **Base plan**: `docs/gateflow/wu-cli-download-01-plan-20260809.md` §5.6, Slice 4, §9
- **Amendment v1**: `docs/gateflow/wu-cli-download-01-slice4-plan-amendment-20260810-060259.md`
- **Amendment v2**: `docs/gateflow/wu-cli-download-01-slice4-plan-amendment-v2-20260810-072924.md`
- **Implementation artifact**: `docs/gateflow/wu-cli-download-01-slice4-implementation-20260810-085724.md`
- **Verdict**: **PASS**（条件通过，含 3 项 finding 需修复后 rereview）

## 1. 审查方法

本 review 独立于 AgentMiMo 进行，不依赖其 findings 或中间结论。审查覆盖：

1. 完整 diff 逐行阅读（全部 20 个文件的 +3358/-1195 行）
2. 对 base plan §5.6、v1 §4-§8、v2 §5-§9 的逐项对照
3. Adversarial failure pass：并发 race、锁释放、取消、边界条件、异常路径
4. Semantic ownership 检查：每类事实的 owner boundary
5. 静态证据：`rg` 枚举、AST 调用链、pyright zero-error 结果
6. 测试覆盖：deterministic barrier tests、race 矩阵、corruption 矩阵

## 2. 架构/语义 owner 检查

### 2.1 Transport/storage 分离（v1 核心）

| 检查项 | 证据 | 判决 |
|---|---|---|
| `prefetch_files_stream` 无 batch/callback/repository | `sec_downloader.py:1548` 签名无这些参数 | **PASS** |
| `materialize_prefetched_event` 是唯一 event materializer | `sec_downloader.py:1673` 定义，三处调用（`download_files_stream:1786`、`sec_download_filing_workflow.py:569`、`sec_download_persistence.py:247`） | **PASS** |
| `sec_sc13_filtering.py` 无 batch/persistence/registry mutation | `rg` 枚举 `begin_batch/commit_batch` 在该文件命中为 0 | **PASS** |
| SEC rejected persistence prefetch 在 `begin_batch` 前 | `sec_download_persistence.py:226-237`：prefetch 完整结束后才 begin | **PASS** |
| CN PDF/Docling 在 writer lock 外 | `cn_download_filing_workflow.py:107,216,302` PDF/Docling 调用均在 `:563` begin 之前 | **PASS** |

### 2.2 并发模型（base §5.6）

| 检查项 | 证据 | 判决 |
|---|---|---|
| `_acquire_ticker_lock` 改为 `blocking=True` | `_fs_storage_infra.py:1512` | **PASS** |
| recovery try-lock 保持 `blocking=False` | `_fs_storage_infra.py:1877` | **PASS** |
| per-ticker Condition reservation | `_fs_storage_infra.py:1244-1263` `_reserve_batch_ticker` | **PASS** |
| 所有出口 release/notify_all | `_fs_storage_infra.py:1280` `_close_active_batch` finally 块统一处理 | **PASS** |
| lock ordering: reservation → writer → staging → publication guard | `begin_batch:450→512` 顺序固定 | **PASS** |
| 不同 ticker 不共享 condition | `_reserve_batch_ticker:1260` 只检查当前 ticker | **PASS** |

### 2.3 Whole-tree preflight / repair-first（v2 核心）

| 检查项 | 证据 | 判决 |
|---|---|---|
| SEC company 移到 preflight + repair 之后 | `sec_download_workflow.py:486` 旧 company batch 已删除；`:695-707` 新位置在 post-repair gate 后 | **PASS** |
| CN company 移到 preflight + repair 之后 | `cn_download_workflow.py:196` 旧 company batch 已删除；`:226-228` `repair_document_id is None` 时才发布 | **PASS** |
| SC13 selection 无 side effect | `sec_sc13_filtering.py:40-87` typed decisions；`:496-501` cache identity 校验 | **PASS** |
| 拒绝 registry skip 在 selection 阶段处理 | `sec_download_workflow.py:572-578` 将已注册 filing 移入 `rejected_filing_ids` | **PASS** |
| 6-K selected-then-rejected 抛 typed error | `sec_download_filing_workflow.py:378` 在 persistence 前 raise `SELECTED_REJECTED_REPAIR_REQUIRED` | **PASS** |
| no-filing+corruption fail closed | `classify_source_integrity_preflight` 在 `accepted_filing_ids` 为空时仍检查 inventory | **PASS** |

### 2.4 Phase A/B identity-first（base §5.6 + v1 §6）

| 检查项 | 证据 | 判决 |
|---|---|---|
| SEC Phase A published classification | `sec_download_filing_workflow.py:230` | **PASS** |
| SEC Phase B staged classification 是首个 target operation | `sec_download_filing_workflow.py:494` | **PASS** |
| identity 变化 rollback 并回 Phase A | `sec_download_filing_workflow.py:500-509` rollback + 递归 `_identity_round+1` | **PASS** |
| same-identity COMPLETE+False skip | `sec_download_filing_workflow.py:519-539` | **PASS** |
| same-identity COMPLETE+True/REPAIR_REQUIRED/MISSING apply | 后续 materialize 路径 | **PASS** |
| 3 轮上限 typed conflict | `_MAX_SOURCE_IDENTITY_ROUNDS = 3` + raise `SourceIntegrityRevisionConflictError` | **PASS** |
| CN Phase A skip (COMPLETE+False) 不进行 PDF/Docling | `cn_download_filing_workflow.py:173-196` 直接 return | **PASS** |
| CN Phase B identity check | `cn_download_filing_workflow.py:563-581` `_commit_cn_filing_assets_batch` 内 | **PASS** |
| CN repair unconditional | `cn_download_filing_workflow.py:173` COMPLETE+False skip 不触发 → 走完整下载 | **PASS** |

### 2.5 Rejection durable unit（v2 §5.4）

| 检查项 | 证据 | 判决 |
|---|---|---|
| SC13 artifact+registry 同 batch | `sec_download_persistence.py:296-300` `save_download_rejection_registry` 与 artifact 在同一 batch | **PASS** |
| SC13 listing/transport 失败 → registry-only | `sec_download_workflow.py:863-877` 独立 registry batch | **PASS** |
| 6-K artifact+registry 同 batch | `sec_download_filing_workflow.py:411-429` `registry_after` 传入 persistence | **PASS** |
| 无无条件尾部 maintenance batch | `sec_download_workflow.py:678-691` 旧 `maintenance_batch` 已删除 | **PASS** |

## 3. Adversarial Failure Pass

### 3.1 并发 race

| 场景 | 分析 | 判决 |
|---|---|---|
| 同 ticker 双 writer（同进程） | 第二个 writer 在 `_reserve_batch_ticker` 等待；第一个完成后 `notify_all` 唤醒 | **PASS** |
| 同 ticker 双 writer（跨进程） | 文件锁 `blocking=True` 序列化；先完成者释放锁后第二个获取 | **PASS** |
| writer lock 释放后到 in-process cleanup 之间跨进程写入 | `_close_active_batch` 先 `_release_lock_token` 再 `with _batch_condition` 清理；此窗口内同进程线程仍被 `_active_transaction_by_ticker` 阻塞 | **PASS** |
| `_release_lock_token` 失败 + `primary_error is None` | `_close_active_batch` 在 finally cleanup 后 `raise release_error`；in-process state 已清理 | **PASS** |
| `_release_lock_token` 失败 + `primary_error is not None` | `release_error` 作为 secondary note 附加到 primary_error；不覆盖主异常 | **PASS** |
| `_batch_condition` 内操作失败 | `dict.pop(default)` 和 `set.discard` 不抛异常；`notify_all()` 也不抛 | **PASS** |

### 3.2 取消

| 场景 | 分析 | 判决 |
|---|---|---|
| `prefetch_files_stream` 首 descriptor 前取消 | `_raise_if_download_cancelled` → `SecDownloadCancelledError` → 被 `except` 捕获 → `return` | **PASS** |
| `prefetch_files_stream` 中途取消 | 循环内 `_raise_if_download_cancelled` → `return`；已 prefetched events 被调用方丢弃（`cancel_checker` 在消费后检查） | **PASS** |
| SEC prefetch 完成后、`begin_batch` 前取消 | `sec_download_filing_workflow.py:491` `cancel_checker` → `return`；无 durable 副作用 | **PASS** |
| CN PDF/Docling 期间取消 | `cn_download_filing_workflow.py` 内 `_raise_if_cancelled` 在 begin 前已有 checkpoint | **PASS** |
| 6-K rejection batch 内取消 | `sec_download_persistence.py` 内 `_raise_if_cancelled` → `SecDownloadCancelledError` → rollback | **PASS** |

### 3.3 边界条件

| 场景 | 分析 | 判决 |
|---|---|---|
| `_PrefetchedFile` content 为空 | `__post_init__` raise `ValueError`；构造时由 `bytes(payload)` 保证非空 | **PASS** |
| malformed sha256 | `_require_canonical_sha256` → `ValueError`；不降级为 REPAIR_REQUIRED | **PASS** |
| `ingest_complete=False` 的 published source | `_classify_source_integrity_unguarded:517` raise `ValueError`；严格结构错误 | **PASS** |
| source directory 存在但 meta.json 缺失 | `_classify_source_integrity_unguarded:488` raise `ValueError` | **PASS** |
| manifest 与 identity directories 不一致 | `_validate_published_source_manifest_unguarded` 双向校验 | **PASS** |
| meta 声明文件但 physical 不存在 | `PHYSICAL_FILE_MISSING` reason；REPAIR_REQUIRED status | **PASS** |
| `begin_batch` 在 `_ensure_batch_storage_dirs` 失败 | `finally: if not registered: _release_batch_ticker_reservation` 确保 reservation 释放 | **PASS** |
| `begin_batch` 在 `_acquire_ticker_lock` 前失败 | `lock_token is None` → skip lock release；reservation 由 finally 释放 | **PASS** |
| `begin_batch` 在 `_write_batch_journal` 失败 | `lock_token is not None` → release；reservation 由 finally 释放 | **PASS** |

### 3.4 CN 特殊路径

| 场景 | 分析 | 判决 |
|---|---|---|
| CN Phase A 删除 `_can_skip_by_pdf_sha` 与 `_commit_cn_filing_metadata_batch` | 已被 integrity-based Phase A/B 替代；旧 PDF-SHA 复用路径在 REPAIR_REQUIRED 时通过完整 assets batch 重新写 PDF+Docling tree | **PASS** |
| CN `previous_completed_meta` 在 Phase A 为 COMPLETE+False 时未使用 | Phase A skip 不调用 `_resolve_previous_completed_meta`，正确 | **PASS** |
| CN repair target 失败后 company 保持旧值 | `repair_gate_completed` 保持 False；company 未发布 | **PASS** |
| CN repair 成功但 post-repair 仍 `SelectedSourceRepairRequired` | raise `SourceIntegrityRevisionConflictError` | **PASS** |

## 4. Findings

### DS-F01（Medium）：`_publish_sec_post_repair_mutations` 含不可达 dead code

- **文件/行号**: `dayu/fins/pipelines/sec_download_workflow.py:863-877`
- **触发条件**: `Sc13DirectionRejectedWithArtifact` 的 `_persist_rejected_filing_artifact` 调用**永远**不会返回 `(False, ...)`——新实现将所有异常路径做 rollback + raise，唯一正常返回是 `(True, None)`。因此 `if artifact_saved:` 之后的 fallback registry-only 路径对该 variant 不可达。
- **影响**: 不影响正确性（atomic artifact+registry 在 persistence 内已保证），但给未来维护者造成困惑：会认为 artifact persist 可能返回 False 并走 registry-only fallback。
- **Root cause**: v1 将 `persist_rejected_filing_artifact` 从"可能返回 (False, error)"改为"失败即 raise"，但 v2 `_publish_sec_post_repair_mutations` 保留了兼容旧语义的控制流。
- **Owner-boundary 修复要求**: 在 `_publish_sec_post_repair_mutations` 中，对 `Sc13DirectionRejectedWithArtifact` 分支：移除不可达的 registry-only fallback 代码；将 `artifact_saved` 变量限定为只在 `RegistryOnly` 分支使用；对 `WithArtifact` 分支直接 `continue`（persist 成功即 artifact+registry 已同批发布）或在 persist 返回后加 `assert artifact_saved`。

### DS-F02（Low）：`cn_download_workflow.py` `_publish_cn_company_after_repair` 使用 `ticker_to_company_id` 但未保留旧 `company_meta.company_id` 语义

- **文件/行号**: `dayu/fins/pipelines/cn_download_workflow.py:203` vs 旧 `:199`
- **触发条件**: 旧代码 `company_meta = upsert_company_meta_for_cn_download(...)` 返回的 `company_meta.company_id` 来自 upsert 内部逻辑；新代码 `ticker_to_company_id(normalized)` 来自 ticker normalization。若两者产生不同 company_id，则 `company_info["company_id"]` 在 preflight/repair gate 之前的 observable 值可能不同。
- **影响**: `company_info` 用于日志/event payload，不进入 durable storage。若 company_id 不同，log/event 中的 company_id 与后续存入的 company meta 可能不一致（但后续 `_publish_cn_company_after_repair` 仍调用 `upsert_company_meta_for_cn_download`，其内部会 persist 正确的 company_id）。这是一个非 durable 的中间表示不一致。
- **Root cause**: `company_info` 的 `company_id` 字段语义 owner 应该是 `upsert_company_meta_for_cn_download` 的返回值，但当前代码改为从 ticker normalization 推导。
- **Owner-boundary 修复要求**: 两种修复方向二选一：(a) 将 `company_info["company_id"]` 的赋值移到 `_publish_cn_company_after_repair` 之后，从实际 upsert 结果获取；(b) 如果 `ticker_to_company_id` 与 upsert 逻辑保证同源，需在此处加注释说明不变量，并在 test 中断言二者一致。

### DS-F03（Low）：`prefetch_files_stream` cancel 路径使用 `return` 而非显式异常传播

- **文件/行号**: `dayu/fins/downloaders/sec_downloader.py:1561-1563`（首 descriptor 前 cancel）、`:1628`（无条件路径中 cancel）、`:1698`（conditional 路径中 cancel）
- **触发条件**: cancel checker 在 prefetch 中途触发 → `SecDownloadCancelledError` → `except` 后 `return`。调用方需在消费完 async generator 后通过 `cancel_checker()` 自行判断是否被取消。若调用方忘记检查 `cancel_checker()`，会看到部分 prefetch events 但不知道发生了取消。
- **影响**: 两条消费路径（`sec_download_filing_workflow.py:491` 和 `sec_download_persistence.py:233`）均在消费后检查 `cancel_checker()`，因此当前 call site 安全。但这是**convention-based safety**，不是 typed contract。未来若新增 prefetch 消费方，可能遗漏检查。
- **Root cause**: `prefetch_files_stream` 的 cancel 语义"return on cancel"未反映在类型签名或返回值中。
- **Owner-boundary 修复要求**: 考虑在 `prefetch_files_stream` docstring 中增加显式约束：**调用方必须在完全消费 generator 后通过 `cancel_checker()` 判断是否被取消；generator 提前 return 不代表成功**。或考虑返回一个 `(events, was_cancelled: bool)` tuple 替代裸 generator。

## 5. 静态证据摘要

| 检查 | 命令/结果 |
|---|---|
| 全仓 pyright | `0 errors, 0 warnings, 0 informations` |
| Ruff check | `All checks passed!` |
| Ruff format | `22 files already formatted` |
| compileall | exit 0 |
| JSON validation | exit 0 |
| `BatchToken(` 构造 | sec_downloader/sc13_filtering 命中 0 |
| `begin_batch(` in transport | sec_downloader/sc13_filtering 命中 0 |
| `getattr/hasattr` in critical files | 命中 0 |
| `prepared/replay/compat` in critical files | 命中 0（`select_prepared_6k_primary_document` 是函数名，非 prepared pattern） |
| Protocol implementer inventory | 唯一 production implementer: `FsSourceDocumentRepository` → `_FsSourceDocumentCore`；test subclasses 均继承 wrapper |

## 6. 测试覆盖评估

| 维度 | 覆盖 | 评价 |
|---|---|---|
| same-target 双 overwrite | barrier 控制时序 | **PASS** |
| different-target union | barrier 验证并集 | **PASS** |
| 三轮 revision churn | per-round Event pairing | **PASS** |
| overwrite policy (COMPLETE+True/False, REPAIR_REQUIRED, MISSING) | 全矩阵 | **PASS** |
| corruption (size/digest/physical missing) repair | production snapshot 可读 | **PASS** |
| malformed sha256 strict | provider/batch 调用为 0 | **PASS** |
| cancel after prefetch/before begin | Event placement + begin/callback 计数为 0 | **PASS** |
| SC13 hidden mutation | `sc13_decision_ready` Event 阻塞 | **PASS** |
| SC13 artifact+registry atomicity | store/meta/registry/validator 各阶段注入失败 | **PASS** |
| CN/HK 顶层路径 | CN 全覆盖，HK 共享 workflow 回归 | **PASS** |
| no-filing clean/corrupt | company 分别提交/fail closed | **PASS** |
| 10x deterministic repeat | SEC pipeline/stream + CN workflow + storage atomicity，全部稳定 | **PASS** |
| process/recovery 10x repeat | cross-process blocking/recovery nonblocking 全部稳定 | **PASS** |

**未覆盖但有合理理由的场景**:
- `persist_rejected_filing_artifact` 的 partial file failure（`store_file` 回调失败）→ 现有 `test_sec_downloader.py` 覆盖了 callback OSError/ValueError 传播
- `download_files_stream`（旧 API wrapper）的独立测试 → 其行为完全由 `prefetch_files_stream` + `materialize_prefetched_event` 组合决定，shared-core integration test 已覆盖

## 7. 与计划的对账

| Plan 要求 | 代码实现 | 对账 |
|---|---|---|
| v1: prefetch 无 batch/callback/repository | `prefetch_files_stream` 签名与 body | ✓ |
| v1: 唯一 materializer | `materialize_prefetched_event`，三处调用 | ✓ |
| v1: `download_files_stream` 只组合 shared core | 实现为 prefetch + materialize | ✓ |
| v1: rejected prefetch-before-batch | `persist_rejected_filing_artifact:226-237` | ✓ |
| v1: repair unconditional (`allow_not_modified=False`) | `sec_download_filing_workflow.py:480-483` | ✓ |
| v2: SC13 selection 无 durable side effect | typed decisions，无 batch | ✓ |
| v2: whole-tree preflight 在 company 前 | `list_source_integrity` + `classify_source_integrity_preflight` | ✓ |
| v2: repair-first stable partition | sorted with `repair_document_id` key | ✓ |
| v2: post-repair re-check | `classify_source_integrity_preflight` 二次调用 | ✓ |
| v2: 6-K selected-then-rejected fail closed | `SELECTED_REJECTED_REPAIR_REQUIRED` raise | ✓ |
| v2: artifact+registry 同 batch | `save_download_rejection_registry` 在 persistence batch 内 | ✓ |
| v2: 无无条件尾部 maintenance batch | 旧代码已删除 | ✓ |
| base: blocking writer 无业务 timeout | `blocking=True`，无 timeout 参数 | ✓ |
| base: recovery try-lock nonblocking | `blocking=False` | ✓ |
| base: release/notify_all 统一 | `_close_active_batch` finally 块 | ✓ |

## 8. Residual Risks

| 风险 | 分类 | 处置 |
|---|---|---|
| 全 filing prefetch bytes 内存峰值 | 已知 bounded risk | 每个 filing 单次 consume；大型 6-K/SC13 artifact 沿用既有 per-filing 边界 |
| `_close_active_batch` 先释放跨进程锁再清理进程内状态 | 正确但微妙 | 时序窗口内跨进程可写入，同进程线程被 Condition 阻塞；建议在 `_close_active_batch` docstring 显式记录此顺序的语义 |
| OS/file lock 永久 I/O 卡死 | assigned to later WU | 不在此 slice 修复 |
| `download_files_stream` 仍保留旧签名 | 当前仍有消费者 | Slice 4 closeout 检查调用点 inventory |
| AST 脚本不可形式化证明 Python dynamic call graph | accepted with controls | rg+AST+pyright+人工+barrier 共同举证 |

## 9. 判决

**PASS**（条件通过）

3 项 finding 中：
- **DS-F01**（Medium）：建议修复，消除死代码以免误导未来维护。
- **DS-F02**（Low）：建议修复或加注释证明 `company_id` 同源性。
- **DS-F03**（Low）：建议加强 `prefetch_files_stream` 的 cancel contract 文档。

所有 finding 均不阻断 correctness：并发模型、Phase A/B identity-first、whole-tree preflight、repair-first gate、SC13 typed decisions、rejection atomicity 以及 transport/storage 分离均经 adversarial failure pass 验证通过。测试覆盖（592 passed, 10x repeat 稳定）、静态检查（pyright 0 error）和 plan 对账均无遗漏。

无未裁决 blocking finding。等待 AgentMiMo review 与总控裁决。
