# WU-SEMANTIC-OWNERSHIP-01 R07-S3 implementation（Codex）

## 1. Gate、基线与结论

- 本文记录既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内 R07-S3 implementation 结果，不创建新 WU。
- 当前工作树 HEAD 为 `386fef8d7a7ecbd977c455ca86bb8bab875d1a98`；所有 R07-S1/S2 production、tests、README 与 review/control artifacts 均作为累计有意改动原样保留。
- accepted plan 为 `docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`；最终复核 SHA-256 为 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- 实施前已完整读取根 `AGENTS.md`、`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`、`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`、`docs/fins/design.md` 与 accepted plan，并按 plan §7.3、§8、§9、§10.2、§11 执行。
- 本轮身份是 AgentCodex implementation agent，不是 Controller；未派发其它 Agent，未推进 review/control，也未修改 `docs/host/issues-implementation-control.md`。
- 未 stage、commit、push 或创建 PR。实现和验证完成后停在 **Controller validation**。

第一性原理复核结论不变：问题确实位于 semantic owner 边界。storage 已拥有 publication revision 与完整 snapshot，一致性不能由 read consumer 分次读取 meta/source/provenance 后重算 hash 或做 before/after 比较来恢复；processor、meta、provenance、citation 与 result 必须在同一个 storage snapshot 及其 borrow 生命周期内消费。

## 2. Exact scope

### 2.1 R07-S3 production allowlist

S3 只修改 accepted plan §7.3 的八个 production 文件：

- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/tools/cache.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/error_contract.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/tools/fins_tools.py`

R07 累计 changed production allowlist 还包括以下 S1/S2 有意改动，全部保留且纳入累计测试、coverage、pyright、Ruff 与 scans：

- `dayu/fins/domain/document_models.py`
- `dayu/fins/storage/_fs_identity.py`
- `dayu/fins/storage/_fs_storage_utils.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_blob_core.py`
- `dayu/fins/storage/_fs_company_meta_core.py`
- `dayu/fins/storage/_fs_maintenance_core.py`
- `dayu/fins/storage/_fs_processed_core.py`
- `dayu/fins/storage/_fs_source_snapshot.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/sec_fiscal_fields.py`
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py`

### 2.2 Tests 与 README

按用户确认的 §7.3 累计八文件测试 allowlist 执行并只在其中补齐/迁移测试：

- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_read_runtime.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_financial_read_contracts.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_sec_pipeline_download.py`

其中 `test_financial_read_contracts.py` 纳入完整验证但本轮不需要产生 diff。README 只修改：

- `dayu/fins/README.md`
- `tests/README.md`

根 README、`dayu/README.md`、design、control、accepted plan、旧 artifact、R08+ 与 deferred Issues 均未修改。

## 3. S3 semantic owner 与实现

### 3.1 Generic LRU owner contract

- `ProcessorLRUCache.put(...)` 返回因同键 replacement 或容量 eviction 移出的泛型 values，按移出顺序交还 lifecycle owner。
- `evict(...)` 返回被移出的 value 或 `None`，`clear()` 返回 LRU 顺序的全部旧 values；generic cache 不猜测 `close()` 语义。
- 增加 identity-conditional `evict_if(key, expected)`，只移除 caller 先前观察到且仍未被并发替换的同一实例，避免旧 reader 清掉刚发布的新 entry。
- `ProcessorCacheKey` 只持 ticker/document ID；source kind 与 revision 由 snapshot entry 拥有，不再由 consumer 拼接第三维 cache key。

### 3.2 Read-runtime 私有 resource lifecycle

- 单一私有 cache entry 同时拥有 processor、解析后的 source meta、完整 storage snapshot 与 revision/source kind；删除独立 meta cache。
- active borrow 覆盖 processor 调用、result projection 与 citation 构造。entry 状态完整表达 live、retired、closing/closed 与 active borrower count；closed 不可逆。
- replacement、LRU eviction、explicit eviction、clear 与 runtime close 都先 retire entry。仍有 active borrow 时，旧 snapshot 保持可读；最后一个 borrow release 后才关闭并删除临时树。
- losing full snapshot、light snapshot、processor build/UTF-8 failure、取消以及 publish 前异常都由 runtime 关闭；cleanup 失败保留 retry authority，并只向既有主异常追加不含 locator/message 的安全 note。
- `FinsReadRuntime.close()` 幂等；第一次 close 清 cache 并 retire 全部 entry，后续 close 重试 pending cleanup；close 后的新 read fail fast。

### 3.3 Creation-lock 与并发 cache miss

- 每个 document 使用独立 creation lock，不持有 storage publication guard 构建 processor。
- caller 先各自取得 storage full snapshot；进入同 document creation lock 后，再用该 full snapshot double-check matching cached entry。
- 已有 matching entry 时，竞争失败 caller 立即关闭自己取得的 losing snapshot，再借用既有 entry；没有 matching entry 时才创建并发布一个 processor。
- stale reader 只用 `evict_if` retire 自己先前观察到的 entry，不会误删并发新发布 entry。

### 3.4 Processor/meta/provenance/citation/result 同版

- 八个 processor 入口全部迁移到同一个 borrow scope：`get_document_sections`、`read_section`、`search_document`、`list_tables`、`get_table`、`get_page_content`、`get_financial_statement`、`query_xbrl_facts`。
- form type、source kind、source meta、provenance、citation 与 result 都从当前 borrow 的同一 snapshot/entry 投影；citation 不再按 ticker/document ID 重读 repository。
- cross-document diagnosis 只对已缓存候选读取显式 source-kind lightweight snapshot，并且仅在 revision 匹配且成功取得 borrow 时诊断；失效候选会被安全 retire。
- `list_documents` 保持 filing/material 两个 typed list projection，再按文档读取轻量 meta；没有新增 batch/list snapshot API，也没有 per-document full snapshot N+1。
- exact document ID 由 storage 的 `source_kind=None` 0/1/2 resolution 决定；alias fallback 枚举两个 typed namespaces 并收集全部匹配，跨 kind 多文档匹配时明确拒绝歧义，不再 filing-first。

### 3.5 旧路径删除与 error mapping

- 从 source repository protocol、wrapper 与 core 删除 `get_source_revision`，无 deprecated wrapper、re-export 或 shim。
- 删除 consumer `revision_before/revision_after`、field hash、独立 meta cache、`_resolve_source_kind` probing、filing-first source-kind guessing 与 citation repository reread。
- storage `SourceSnapshotConsistencyError` 只在 read runtime 单点映射为既有 `ErrorCode.SOURCE_CHANGED_DURING_READ`；code 值保持不变，error message/hint 不含 revision token、private key、local URI 或 temp path。
- 按 plan 只删除 `read_runtime.py` 中 `QueryDiagnosis` 与 `SEARCH_MODE_AUTO` 两个已记录 unused imports，没有借机清理其它 legacy Ruff 项。

### 3.6 Composition-root close

- `DefaultFinsRuntime.close()` 保持 lazy：未创建 read runtime 时不会为了 cleanup 反向创建；若已创建则关闭它；close 幂等，close 后禁止再取得 read runtime。
- `_FinsReadProcessTarget.__call__` 在 `finally` 关闭本次创建的 `DefaultFinsRuntime`。测试分别覆盖 completed、typed/business failed 与 unexpected execution failed，三路各自创建且关闭一个 runtime。成功路径的 close 失败投影为 execution failure；已有业务/执行主失败时保留主失败优先级。
- process target 按既有 contract 只返回 completed/failed，不产出 cancelled envelope；Host 取消由父进程 process capsule 治理。full snapshot 已取得后的协作式取消 cleanup 由 read-runtime owner test 验证，不在 process target 中增加 cancellation shim。

## 4. Tests 与真实 filesystem smoke

### 4.1 Targeted nodes

plan §7.3 的迁移节点与新增节点按当前名称精确执行，共 `20 passed, 3 warnings in 1.36s`。覆盖内容包括：

- equal revision reuse/source change rebuild、single snapshot entry、stale cross-document diagnosis；
- transient recovery、sustained exhaustion、revision-change concurrency、initial miss serialization；
- active borrow eviction、clear/runtime close、citation/result same snapshot、source deletion；
- provider-owned citation、same-snapshot provenance、九工具输出递归泄漏扫描、process target close；
- Default runtime lazy/idempotent close、cache bound、storage kind ambiguity、旧算法源码 guard 与 list typed projections。

另新增 alias owner 节点，证明 filing/material 的两个不同文档命中同一 alias 时返回明确参数歧义，cache 保持为空，不隐式选择 filing。

Controller validation follow-up 的四个精确节点最终执行结果为 `4 passed, 3 warnings in 0.93s`：

- invalid UTF-8 / processor validation failure：typed decode failure 保持主因，cache 为空，storage probe 记录的 full snapshot temp root 已全部不存在；
- processor registry build failure：原始异常实例保持主因，processor 未发布、cache 为空，storage probe 记录的唯一 full snapshot temp root 已删除；
- full snapshot 已取得、processor 已构建但尚未 publish 时触发现有 cancellation token：`FinsReadCancelledError` 优先传播，cache 为空，唯一 full snapshot temp root 已删除；
- process target：completed、typed/business failed、unexpected execution failed 三路分别调用真实 `DefaultFinsRuntime.close()`，并保持各自 completed / `invalid_argument` / `execution_error` envelope。

### 4.2 S3 累计八文件

命令：

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

follow-up 最终重跑结果：`489 passed, 3 warnings in 27.15s`。

### 4.3 §8.4 真实 filesystem concurrency/lifecycle smoke

所有 storage publication smoke 都使用 `tmp_path` 真实文件系统、真实 repository/batch commit、真实线程以及 `threading.Event/Barrier`；没有以 `sleep` 作为 correctness oracle。

1. A/B publication：A、B 各含 primary/related 两个关联文件，并改变 meta fingerprint 与 provenance provider；真实 batch/atomic commit 切换，snapshot 只允许完整 A 或完整 B。
2. Transient：私有 `_copy_snapshot_files` seam 先执行真实 fd-copy，再用 Event 协调一次真实 B commit。storage 丢弃变化 attempt、清理资源并自行返回完整 B；read consumer 只发起一次 full snapshot 调用且只构建一个 processor。
3. Sustained：monkeypatch 只包装真实 `_copy_snapshot_files` 并用双向 Barrier 调度；每个真实 copy/verify attempt 后交替提交真实 A/B，直到 storage 自己的 `_STABLE_READ_ATTEMPT_LIMIT` 耗尽。测试没有直接注入 typed failure、policy 或 outcome；最终只由 storage 抛出 typed consistency exhaustion，runtime 映射一次，cache 为空，未留下 full snapshot root。
4. Static corruption：真实 fd-copy barrier 下的 silent inode/content/fstat mutation、symlink、descriptor/meta/file mismatch 保持既有 corruption/I/O failure，不重试、不映射为 source changed。
5. Initial miss：两个线程各自取得 full snapshot并竞争同 document creation lock；只发布一个 processor，losing snapshot 被关闭，两个 caller 借到同一 entry。
6. Lifecycle：旧 borrow 阻塞期间发布 B 并触发 replacement/eviction；旧 snapshot 在 release 前可读、release 后删除。clear/runtime close 同样按最后一个 active borrow 延迟关闭。invalid UTF-8 validation failure、processor registry build failure 与 full snapshot 取得后、cache publish 前的 cancellation 都断言 cache 为空且真实 temp root 已立即删除。
7. Citation/result：processor 产生 A result 后发布 B；当前 borrow 仍返回 A result + A provenance，下一次调用返回 B + B。
8. Recovery/security：R06 crash/recovery phases、opaque identity descriptor、symlink/filename/local-URI containment 与 outside sentinel 测试全部保留并在累计八文件中通过。

## 5. Changed-production line coverage

coverage 开启 branch instrumentation；follow-up 门禁严格从 `workspace/tmp/r07-s3-followup-coverage.json` 读取每个文件的 `covered_lines / num_statements`，不使用 branch composite 百分比替代 line gate：

| 文件 | line coverage |
| --- | ---: |
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
| `dayu/fins/tools/read_runtime.py` | 81.09% |
| `dayu/fins/tools/error_contract.py` | 100.00% |
| `dayu/fins/tools/fins_tools.py` | 84.57% |
| `dayu/fins/service_runtime.py` | 87.61% |

覆盖率门禁通过：上述 20 个 changed production 文件均达到 `>=80%`。

## 6. Static validation

- full pyright：`pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- scoped Ruff：20 个累计 production 文件 + 8 个累计 test 文件 → `All checks passed`。
- full Ruff ledger：精确 `150`，规则分布为 `F401=70`、`E402=66`、`F841=10`、`F541=3`、`F821=1`；满足 plan 的总量和逐规则上限，相对 base 恰好删除两个获准 F401。
- `git diff --check`：通过。
- 文本卫生：`_retire_entries` docstring 只保留一个 `Raises` 段；删除 `read_section` 重复 path 注释；coverage 结论只保留一处；`DefaultFinsRuntime.get_read_runtime` 的 `Raises` 已记录 close 后 `RuntimeError`。
- HEAD：精确 `386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- accepted plan SHA-256：精确 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。

## 7. Source、AST、allowlist 与 LLM-facing scans

### 7.1 Identity source scan

- `_normalize_(ticker|document_id)` 旧 storage path normalizer 为 0；剩余命中只有 ticker alias 业务归一、private backup-name parser 及其 corruption/recovery tests。
- `portfolio/filings/materials/processed/rejections` scan 的 apparent ticker/document ID 命中均分类为 repository API 参数/业务 error text、descriptor/meta round-trip、固定 storage namespace 或 corruption/security tests；没有 raw external identity path join。
- `directory_name/lock_path.stem/child.name` 命中均为 identity owner 的 hidden/private entry 枚举、固定 namespace、安全 business filename/manifest 条目或明确 corruption/security test；没有从 private directory/lock name 反推业务 identity。

### 7.2 AST audit

按 plan 原样运行 AST 脚本，共输出 `125` 个候选节点：`82 JoinedStr`、`43 BinOp`。逐项分类结果：

- path `BinOp` 只使用 identity owner 返回的 private `ticker_key/document_key`、已解析的 private staging/ticker/source directory，或在这些 owner helper 后拼固定 namespace/manifest/meta filename；
- `JoinedStr` 只用于业务 payload/meta validation/error/log text，或由 private key/staging entry 构造 storage-internal URI/lock/backup 名；
- raw external ticker/document ID 直接进入 path/object-key/lock/backup/staging join：`0`；
- 从 directory/lock/backup private name 反推业务 identity：`0`；
- 未分类或违规节点：`0`。

### 7.3 Revision/snapshot consumer scan

- `get_source_revision`、`_build_source_revision`、`revision_before`、`revision_after`、source-revision SHA grammar：`0`。唯一 `sha256:<hex>` 命中是 `tests/README.md` 对层中立 UTF-8 文本 digest 的无关测试说明，未涉及 Fins source revision。
- `.digest` 唯一命中是 guard test 的负断言字符串 `assert ".digest" not in source`；source revision 字段访问残留为 `0`。
- read runtime repository scan 只剩 alias/list typed projection 的两个 `get_source_meta`，以及 `snapshot.get_primary_source()`；direct repository source/provenance/handle/citation reread为 `0`。
- pipeline/processor materialize scan只剩 snapshot 提供的 `Source` consumer 与既有 processor materialize；pipeline raw repository source materialize 为 `0`。
- `_resolve_source_kind` 与 filing-first tuple/probe：`0`。

### 7.4 LLM-facing scan

- production 命中只包含 read runtime 内部 docstring 与唯一 error mapping owner；其余命中是 tests、security URI fixtures、negative scan tokens 或测试 helper 名。
- tool schema、description、result、citation、error message/hint 均未输出 revision token、storage/private key、`local://`、repo internal namespace 或 absolute temp path。
- recursive runtime JSON test逐一覆盖 9 个 read tools 的 completed、failed、cancelled outcome 及 nested citation/value，全部通过。
- `source_changed_during_read` code 只由 `error_contract.py` 定义，并只在 read runtime 映射 storage typed exhaustion；无字符串解析或第二 code owner。

### 7.5 Allowlist/status

- 实际 product/test/README diff 全部位于本 artifact §2 的累计 allowlist。
- `docs/host/issues-implementation-control.md` 与 S1/S2 review/control artifacts 是进入 S3 前已有的 Controller/累计有意工作树状态，本轮未修改、覆盖、stage 或 commit。
- 本轮只新增当前 implementation artifact；未产生其它 review/control artifact，未触碰 design、accepted plan、旧 artifact、R08+ 或 deferred Issues。

## 8. Full regression 与 inherited ledger

正式命令：

```text
pytest tests/contracts tests/cli tests/documents tests/fins tests/tools \
  tests/host tests/runtime tests/service tests/engine -q
```

follow-up 最终重跑结果：`4878 passed, 3 failed, 3 skipped, 5 deselected, 3 warnings in 122.24s`。

三项 failure 与 plan §1.1 inherited ledger 的 node、rule/error type、stable location 与 text fingerprint 精确一致：

1. `tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default`：`AssertionError` at `tests/runtime/test_log.py:101`；root logger 仍多一个 Dayu marker `StreamHandler`。
2. `tests/service/test_host_admin.py::test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`：`ConfigFieldError` at `dayu/runtime/config_loader.py:2303`；仍为 `missing required fields: ['wait_poller_policy']`。
3. `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers`：`AssertionError` at `tests/service/test_import_boundary.py:101`；仍只有 `fins_wait_adapter.py` / `host_assembly.py` 导入 `_ingestion_tool_helpers` 两项。

三节点隔离命令结果为 `1 passed, 2 failed in 0.35s`：logging 节点通过；另两项以相同 type/location/text 继续失败。没有新增 full-suite failure。

按 §1 同时复核裸 `pytest -q`：collection 仍因 `workspace/tmp/r06-base-9c07b88d/tests/conftest.py` 与正式 `tests/conftest.py` 产生同一 `ImportPathMismatchError`；未删除或修改该外部临时树来制造绿色。

## 9. README current contract

- `dayu/fins/README.md` 只记录已实现 current contract：exact opaque identity mapping、persisted opaque publication revision、storage-owned stable snapshot、processor/meta/provenance/citation/result same-snapshot borrow、resource-aware cache 与既有 typed source-changed failure；不承诺 private key/token grammar、retry 次数或私有类名。
- `tests/README.md` 只更新 `tests/fins` owner-level coverage 摘要：opaque identity round-trip、snapshot consistency、真实 filesystem publication、cache/borrow lifecycle 与 citation/result 同版；不写文件级流水账。
- 根 README 与 `dayu/README.md` 不触发：用户命令、安装、顶层 workspace、UI→Service→Host→Engine 分层和 Fins package 位置均未改变。

## 10. Risk、stop-condition 与 handoff

- R07-S3 changed-owner tests、逐文件 coverage、pyright、scoped Ruff、full Ruff ledger、diff check、identity/source/AST/LLM scans 与真实 filesystem smoke 均满足 accepted plan；未发现新的 R07 blocker 或 §11 stop condition。
- full suite 仍有三项精确 inherited failures，裸 pytest 仍有精确 inherited collection mismatch；它们不属于 R07 owner/allowlist，未顺手修复。
- full Ruff 仍有 150 项 inherited repository ledger，但 S3 scoped Ruff 为 0，且总量与逐规则均未扩散。
- 私有 key/revision 算法、R08 financial/XBRL producer contract、R09—R12 与 Issues 142/151/175/177/178 均保持 deferred，没有反向塞入 R07。

**状态：R07-S3 IMPLEMENTATION COMPLETE / READY FOR CONTROLLER VALIDATION。**

本 agent 到此停止；不进入双路 code review、Controller adjudication、control 更新、stage、commit、push 或 PR。
