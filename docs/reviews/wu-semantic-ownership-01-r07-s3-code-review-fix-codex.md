# WU-SEMANTIC-OWNERSHIP-01 R07 complete-tree code-review fix（Codex）

## 1. Gate、真源与结论

- 本文记录既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R07 complete-tree code-review fix gate；不是新 WU。
- finding 唯一裁决真源：`docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-controller-adjudication.md`，SHA-256 为 `f23602bd165a2ea11f028e6fc0a68fa0fcea07dbe0ecc02dce3f87256cc98673`。
- accepted plan：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`，SHA-256 为 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- HEAD / transition base：`386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- 本 gate 只修复 `R07-CR-F01..03`；没有实施 R08+、deferred Issues 或统一 authorization。
- 未修改 control、design、plan、README 或旧 artifact；未 stage、commit、push 或创建 PR。

结论：`R07-CR-F01..03` 全部 **已修复**，`3 closed / 0 open / 0 deferred / 0 blocker`。当前状态为 **CODE_REVIEW_FIX_COMPLETE / READY_FOR_CONTROLLER_VALIDATION**。

## 2. Exact changed scope

本 fix gate 只修改：

- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/fins_tools.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_fins_storage_provider.py`

唯一新增 artifact：

- `docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-fix-codex.md`

R07-S1/S2/S3 的其余累计 product/test/README/control/review working-tree 内容均原样保留，不属于本 fix gate 新改动。

## 3. Semantic owner 与修复

### 3.1 R07-CR-F01 — close 与 cache publication 的确定顺序

**Root cause**：processor build 在 document creation lock 内通过一次 `_ensure_open()` 后，可以在不持 read-runtime lifecycle owner lock 的情况下构建并发布 cache entry；`close()` 因而可能先设置 closed、清空 cache 并返回，随后 build 再发布 live entry。

**修复**：

- processor 构建继续不持 storage publication guard，也不持 read-runtime lifecycle lock；长构建不会扩大临界区。
- created entry 已取得 active borrow 后，在 `_lifecycle_lock` 内执行最终 `_ensure_open()` 与 `ProcessorLRUCache.put(...)`，使 closed-check + publication 与 `close()` 的 closed-state transition 形成同一线性化顺序。
- close 先发生时，最终 closed-check 抛出既有 `RuntimeError("Fins read runtime 已关闭")`；created borrow/entry 未转移进 cache，full snapshot 走既有 unowned cleanup。
- publication 先发生时，`close()` 能 clear/retire entry；已经取得的 active borrow 继续合法完成，最后 release 删除 snapshot。
- 没有修改 `_close_retired_entry`：Controller 已裁决该处不是本 finding 根因，既有 cleanup retry authority 保持不变。

**Owner tests**：

- `test_runtime_close_before_cache_publication_rejects_build_and_cleans_snapshot` 用真实 filesystem、`registry.before_return` 和两个 `threading.Event` 固定 close-first interleaving，无 sleep；断言 worker 完成、既有 close-state error、cache/retired/pending 全空且全部 full snapshot roots 删除。
- `test_cache_publication_before_runtime_close_preserves_active_borrow` 固定 publication/borrow-first 顺序；断言 close 后 cache 已空但 active snapshot 仍可读，调用完成后 root 删除且 retired/pending 全空。

最终状态：**已修复**。

### 3.2 R07-CR-F02 — creation-lock registry 生命周期

**Root cause**：`_creation_locks` 原为永久强引用 `dict`，任意 missing key 在 snapshot read 前即创建条目，cache eviction 也不回收，因此长期 runtime 的历史 key 数量可无界增长。

**修复**：

- registry 改为严格类型的 `WeakValueDictionary[ProcessorCacheKey, Lock]`。
- `_creation_locks_guard` 继续串行化 registry get/create；重叠 same-key caller 的局部变量和 `with lock` 全程持有强引用，因此共同取得同一个 lock。
- caller 结束且没有其它使用者后，registry 不再成为 lock 的永久 owner；新一轮非重叠调用可按需创建新 lock。
- 没有使用 `locked()` 猜 waiter、sweep、阈值、全局 striped lock 或 cache eviction 下游补偿。

**Owner tests**：

- 扩展 `test_concurrent_initial_cache_miss_builds_one_processor_and_closes_losing_snapshot`，记录两个重叠 same-key caller 的 lock identity，断言两者相同、只构建/发布一个 processor，losing full snapshot 删除。
- `test_creation_lock_registry_reclaims_missing_and_evicted_document_keys` 顺序访问 64 个 missing IDs，再访问 12 个真实 document IDs（cache 容量 4）；必要 GC 后两阶段 registry 均为 0，cache 仍严格为 0/4，evicted roots 删除、runtime close 后全部 roots 删除。

最终状态：**已修复**。

### 3.3 R07-CR-F03 — process target 消费公共 close retry authority

**Root cause**：process target 首次 `DefaultFinsRuntime.close()` 失败后没有再次消费公共幂等 cleanup authority；已有 primary failure 时还会静默吞掉 cleanup failure。

**修复**：

- 首次公共 close 失败后，固定调用一次 `_follow_up_process_runtime_close(...)`；该 helper 只再次调用 `DefaultFinsRuntime.close()`，不访问 read runtime、pending snapshot、retired entry 或其它 private state。
- completed 路径继续保持“首次 cleanup failure → `execution_error`”；typed/business 与 unexpected primary outcome 均保持原优先级，不被 cleanup secondary 覆盖。
- follow-up 仍失败时，仅用 `Log.warning` 记录 `action=runtime.close.follow_up type=<type> errno=<value|none>`；不记录 raw message、path、key、revision、cause 或 traceback。
- 没有新增 envelope/schema/cancel 语义，没有捕获 `BaseException` 或引入可配置/无限 retry policy。

**Owner tests**：

- `test_fins_read_process_target_closes_runtime_on_success_and_failure` 对 completed、typed/business failed、unexpected failed 三个独立 runtime 注入 transient first-close failure；每个 runtime 都发生恰好两次公共 close，真实第二次 close 完成，outcome 分别保持 `execution_error`、`invalid_argument`、`execution_error`。
- `test_fins_read_process_target_persistent_close_failure_logs_path_free_diagnostic` 让两次 close 都抛出含敏感 locator/key/revision/cause 的异常；断言 primary business outcome 不漂移、公共 close 恰好两次、日志只含 action/type/errno。
- `test_default_runtime_public_close_retries_real_snapshot_cleanup` 使用真实 `DefaultFinsRuntime` 和真实 filesystem snapshot，使 temp-root 删除首次失败；第一次公共 close 抛出且 root 保留，第二次公共 close 删除 root，第三次幂等 close 不再触发删除，证明 retry authority 已清空。

最终状态：**已修复**。

## 4. Validation

### 4.1 新增/修改精确 owner nodes

最终命令覆盖上述 7 个节点，结果：

```text
7 passed, 3 warnings in 1.15s
```

测试均使用真实 filesystem 与 Event 协调；没有 sleep correctness oracle，也没有新增 production test seam。

### 4.2 累计八文件与逐 production file line coverage

最终累计命令：

```text
coverage run --branch -m pytest -q \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_fins_storage_provider.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_sec_pipeline_download.py
```

结果：`494 passed, 3 warnings in 27.19s`。

coverage JSON：`workspace/tmp/r07-s3-code-review-fix-coverage.json`（本地临时验证产物，不 stage/commit）。逐文件 line coverage 按 `covered_lines / num_statements` 复算：

| production file | line coverage |
|---|---:|
| `dayu/fins/domain/document_models.py` | 96.30% |
| `dayu/fins/storage/_fs_identity.py` | 80.00% |
| `dayu/fins/storage/_fs_storage_utils.py` | 83.82% |
| `dayu/fins/storage/_fs_storage_infra.py` | 86.14% |
| `dayu/fins/storage/_fs_blob_core.py` | 88.06% |
| `dayu/fins/storage/_fs_company_meta_core.py` | 91.11% |
| `dayu/fins/storage/_fs_maintenance_core.py` | 92.39% |
| `dayu/fins/storage/_fs_processed_core.py` | 88.83% |
| `dayu/fins/storage/_fs_source_document_core.py` | 83.06% |
| `dayu/fins/storage/repository_protocols.py` | 100.00% |
| `dayu/fins/storage/fs_source_document_repository.py` | 96.10% |
| `dayu/fins/storage/_fs_source_snapshot.py` | 90.42% |
| `dayu/fins/ingestion_runtime.py` | 90.67% |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | 92.11% |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | 82.32% |
| `dayu/fins/tools/cache.py` | 96.83% |
| `dayu/fins/tools/read_runtime.py` | 82.56% |
| `dayu/fins/tools/error_contract.py` | 100.00% |
| `dayu/fins/tools/fins_tools.py` | 85.80% |
| `dayu/fins/service_runtime.py` | 87.61% |

20 个 changed production files 全部 `>=80%`。

### 4.3 Type、lint、diff 与 scans

- full pyright：`pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- cumulative scoped Ruff（20 production + 8 tests）：`All checks passed!`。
- full Ruff inherited ledger：仍为 `150`，精确分布 `F401=70`、`E402=66`、`F841=10`、`F541=3`、`F821=1`；未新增或扩散。
- `git diff --check`：通过。
- revision/source scan：`get_source_revision`、`_build_source_revision`、`revision_before`、`revision_after` 与 Fins source-revision SHA grammar 无残留；唯一命中仍是 `tests/README.md` 的层中立 UTF-8 文本 digest 说明。
- `.digest` 唯一命中仍是 guard test 的负断言。
- production `_resolve_source_kind` / filing-first probe：0。
- `fins_tools.py` 对 `_read_runtime`、`_pending_snapshots`、`_retired_entries` 的 private access：0。
- 本 fix diff 新增 `time.sleep` / `sleep(...)`：0。
- follow-up diagnostic 只由固定 action、异常 type 与 errno 组成；persistent failure owner test 验证 raw path/key/revision/cause/traceback 零泄漏。

### 4.4 Formal directory full suite 与 inherited ledger

正式命令：

```text
pytest tests/contracts tests/cli tests/documents tests/fins tests/tools \
  tests/host tests/runtime tests/service tests/engine -q
```

结果：`4883 passed, 3 failed, 3 skipped, 5 deselected, 3 warnings in 132.86s`。

三项 failure 与 accepted plan §1.1 的 node/type/location/text fingerprint 精确一致：

1. `tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default`：`AssertionError` at `tests/runtime/test_log.py:101`，仍为一个 Dayu marker `StreamHandler`。
2. `tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`：`ConfigFieldError` at `dayu/runtime/config_loader.py:2303`，仍缺 `wait_poller_policy`。
3. `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`：`AssertionError` at `tests/service/test_import_boundary.py:101`，仍只有 `fins_wait_adapter.py` / `host_assembly.py` 对 `_ingestion_tool_helpers` 的两项 import。

三节点隔离复核：`1 passed, 2 failed in 0.36s`；logging 节点隔离通过，另两项仍以相同指纹失败。没有新增 full-suite failure。相对 S3 implementation 的 pass 数增加 5，精确对应本 fix gate 新增的 5 个 owner tests。

## 5. README、风险与边界

- 用户明确禁止本 fix gate 修改 README；本 gate 没有修改任何 README。累计 working tree 中既有 R07 README 改动原样保留。
- 没有改变 storage snapshot/public revision/citation/tool schema/LLM-facing contract；没有新增兼容、fallback、下游补偿或公共状态机。
- persistent filesystem cleanup 连续两次失败时，process target 按 Controller 裁决保留 primary outcome并记录 path-free action/type/errno；本 gate 不引入第三次、无限或可配置 retry。这是已验证的 bounded failure contract，不是 open finding。
- full suite 三项 inherited failure与 full Ruff 150 项仍由既有 ledger owner处理，不属于 R07 fix scope。
- R08 financial/XBRL contract、R09—R12、Issues 142/151/175/177/178 与统一 authorization 均未触碰。

## 6. Final finding ledger 与 handoff

| Finding | Severity | Final status | Evidence |
|---|---:|---|---|
| `R07-CR-F01` post-close publication/temp leak | HIGH | **已修复** | lifecycle-linearized final check/publication；close-first + publication-first owner tests |
| `R07-CR-F02` unbounded creation-lock registry | MEDIUM | **已修复** | weak-value lifecycle；same-key identity/build + missing/over-capacity GC tests |
| `R07-CR-F03` process cleanup retry authority lost | LOW | **已修复** | one public follow-up close；三 outcome priority、persistent diagnostic、真实 snapshot cleanup tests |

最终 ledger：`3 closed / 0 open / 0 deferred / 0 blocker`。

下一 entry point：**Controller validation**。本 agent 到此停止；不得由本 gate 进入 dual re-review、accepted implementation commit、R08、stage、commit、push 或 PR。
