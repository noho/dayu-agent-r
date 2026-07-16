# WU-SEMANTIC-OWNERSHIP-01 R07-S2 implementation（Codex）

## 1. Gate 与基线

- 本文记录既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内 R07-S2 的 implementation 结果，不创建新 WU。
- 实现依据为 accepted plan `docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`；实现结束时复核 SHA-256 为 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- 实现前完整读取根 `AGENTS.md`、`docs/fins/design.md`、accepted plan、S1 re-review artifacts 与 `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-rereview-controller-adjudication.md`。
- 本轮只推进 R07-S2 implementation，未进入 S3、R08+、Issue 142/151/175/177/178 或统一 authorization。
- Controller validation 接受的同一 resource-owner findings `CV-F01`、`CV-F02`、`CV-F03` 已在本 artifact 内完成 follow-up；未开启 code review gate。
- 未 stage、commit、push 或创建 PR。本轮结束 gate 为等待 Controller validation。

## 2. Exact scope

### 2.1 Production

严格限制在 plan §7.2 的 S2 production allowlist：

- `dayu/fins/domain/document_models.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/_fs_source_snapshot.py`（新增）
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/sec_fiscal_fields.py`
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py`

workspace 中 `_fs_identity.py`、其它 storage core、S1 artifacts 与 Controller/control 变更属于进入本轮前已有的 S1 工作树状态；本轮未修改它们。

### 2.2 Tests

测试变更只落在以下四个获准文件；第五个获准文件只执行全文件测试，未因 S2 产生改动：

- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_processor_read_consistency.py`（仅验证）

### 2.3 Owner-boundary documentation

用户提供直接证据后，按 README 自身的 Agent 更新约束同步：

- `dayu/fins/README.md`：删除 canonical meta/file hash revision、zero-retry mixed-version 与旧 revision-aware 双 cache 的 storage 承诺；只记录 persisted opaque equality token、storage light/full snapshot，以及当前 read runtime 仍未持有 snapshot resource/borrow 的事实。
- `tests/README.md`：`tests/fins/` 的职责确实命中，更新为 opaque identity、persisted revision、snapshot 稳定读取、corruption 分类、资源清理与 path-free exception graph 覆盖。

未修改根 README、`dayu/README.md`、plan、design 或其它 README。

## 3. Owner、状态与发布语义

### 3.1 Persisted published revision

- `SourceDocumentRevision.digest` breaking rename 为 `token`，只校验非空字符串并承诺 exact opaque equality；没有 alias、property、双字段、prefix/长度/字符集/hash grammar 或兼容 shim。
- complete-source mutation owner 在 source create/update/replace/delete/restore 的最终 meta 中自动生成 token；producer 不能注入 token。
- token 与完整 source batch commit 原子发布。processed/company/maintenance-only batch 与 rollback 不改变已发布 token。
- `get_source_revision(...)` 只机械读取 persisted token，不再拥有 selected-field builder、canonical meta/file hash 或 SHA grammar。

### 3.2 Stable source snapshot

- `read_source_snapshot(..., materialize_files=...)` 是唯一 storage-owned 一致读取入口，返回 typed snapshot/resource。
- light snapshot 在同一 publication guard 下投影 exact identity、source kind、meta、provenance、persisted revision、有序 files 与 primary filename。
- full snapshot 从 guard 内打开的全部 regular-file FD 复制到私有系统临时树；不把 published `Path` 或 local URI 返回给 consumer。
- post-copy 只核对 acquire 已选 source kind 的 exact persisted revision、identity descriptor 与 deletion state。显式 source kind 下，filing/material 同 document ID 共存不会被误判；source kind 缺省时的 0/1/2 ambiguity 只在 acquire 阶段判定。
- publication 确实变化时可在 storage 内做有界且多于一次的稳定读取；次数不进入 public contract、异常或测试断言。持续变化抛出不含 path/key/revision 的 typed consistency error。
- 静态 inode/content/fstat、symlink、meta/file mismatch 等 corruption 保持其原始 corruption/I/O 分类，不伪装为 `source_changed`。
- full snapshot `close()` 幂等；关闭后其 `Source` 不能再 open/materialize。临时树路径仅属于 snapshot 私有物化资源，不是 published path。
- resource `close()` 先把资源置为不可读，但只有临时树真实删除成功后才清空 owner 内的 cleanup locator；首次删除失败会保留待清理 root，后续并发/重复 close 在同一锁内重试或幂等返回。

### 3.3 Cleanup 与 exception graph

- acquire guard release 遵循三态 primary-preservation：
  - acquire 已失败且 release 再失败：保留 acquire 为主，release 通过 `_append_secondary_error_note(...)` 只记录 action/type/errno；
  - acquire 成功但 release 失败：release 为主，并关闭已取得 FD；FD close 再失败只追加相同 path-free 安全诊断；
  - acquire/release 均成功：正常返回 attempt。
- snapshot attempt 通过单一私有 cleanup helper 统一关闭全部 FD、删除临时树，并保证第一个 cleanup 失败不会阻止后续 cleanup：
  - post-marker/read/copy/corruption 已是主失败时，close/remove 只能成为 path-free secondary diagnostics；
  - transient discard 没有既有主失败时，第一个 cleanup failure 成为主失败，另一项仍执行并作为安全 secondary diagnostic。
- post-copy marker guard 与 acquire guard 使用相同 primary-preservation：marker/meta/descriptor read 已失败时，guard release 失败只能通过 `_append_secondary_error_note(...)` 追加 action/type/errno；marker read 成功时 release failure 才是主失败。
- initial `fstat` 失败发生在新 stream 加入统一 FD list 之前；该路径显式保留 `fstat` 主失败并尝试 close，close 再失败只追加 path-free action/type/errno note。
- notes、args、cause、context 与 traceback graph 均不写入 workspace/private path，也不使用 raw secondary f-string；次级失败没有被吞掉。

Controller validation finding 状态：

- `CV-F01`：**已修复**。marker read + guard release 双失败保留 marker read 主因。
- `CV-F02`：**已修复**。close 删除失败不丢失 temp-root cleanup ownership，关闭后仍不可读，后续 close 可重试。
- `CV-F03`：**已修复**。initial fstat + 未登记 stream close 双失败保留 fstat 主因。

## 4. Consumer migration

- preprocess：先 begin caller-owned batch，再读 full snapshot；processor、source meta、sections/tables 消费同一 snapshot；commit 前先 close；commit 前失败 exactly-once rollback；commit 开始后不再二次 rollback。
- SEC fiscal multi-file：同一 fiscal calculation 的文件、meta、provenance 与 revision 来自单一 full snapshot，未改变 fiscal 业务算法或 `has_xbrl` 分类。
- active 6-K primary-document repair：同一 repair 读取单一 full snapshot，关闭后才 stage mutation；未改变 prepared payload owner。

## 5. Owner-level tests

新增/更新的真实 filesystem 覆盖包括：

- persisted token 的 create/update/delete/restore、rollback 与 non-source batch 保留；opaque model 无旧字段或 grammar；logical delete 后 revision/snapshot 不可读。
- light/full descriptor/meta/provenance/revision/files/primary 同版，full snapshot close 幂等且关闭后不可读。
- 显式 source kind 与另一 kind 同 document ID 共存时 post-check 不误报；缺省 kind 保持 ambiguity。
- 真实 publication A/B、一次 transient 变化后稳定、持续变化 typed failure；不断言内部稳定读取次数。
- symlink、meta mismatch、silent inode/content/fstat mutation 的 fail-closed 与非 `source_changed` 分类。
- acquire primary + release secondary、release primary + FD-close secondary、marker read primary + marker-guard release secondary、marker/copy primary + FD/temp-root 双 cleanup secondary、initial fstat primary + 未登记 stream close secondary、transient discard 双 cleanup failure 的 primary preservation；递归检查完整 exception graph 无 locator 泄漏。
- resource close 首次 rmtree 失败后保持 source 不可读并保留真实临时树；两个并发 retry 只完成一次真实删除，后续重复 close 幂等，首次 failure graph 不含 locator。
- preprocess batch/snapshot/close/commit/rollback 顺序与 exactly-once 语义；SEC fiscal multi-file 和 active 6-K consumer 单 snapshot 生命周期。

测试没有用 fake `Source` 固化 storage policy。

## 6. Validation evidence

### 6.1 Tests 与真实 filesystem smoke

五个获准测试文件全量执行结果：

```text
399 passed, 3 warnings in 25.65s
```

其中真实 filesystem owner tests 已覆盖 A/B、transient、sustained、显式 kind 共存、symlink/meta mismatch、silent mutation、resource cleanup 与 double-failure exception graph；它们同时构成本轮真实 storage smoke。

Controller follow-up 的三个新增节点连同原有四个 cleanup 双失败节点精确执行结果为 `7 passed in 0.48s`。

### 6.2 Changed-production line coverage

使用五个全量测试文件执行 branch instrumentation，并按 `covered_lines / num_statements` 核对每个 S2 production 文件：

| 文件 | line coverage |
| --- | ---: |
| `dayu/fins/domain/document_models.py` | 96.30% |
| `dayu/fins/storage/repository_protocols.py` | 100.00% |
| `dayu/fins/storage/fs_source_document_repository.py` | 96.20% |
| `dayu/fins/storage/_fs_storage_infra.py` | 86.14% |
| `dayu/fins/storage/_fs_source_document_core.py` | 83.47% |
| `dayu/fins/storage/_fs_source_snapshot.py` | 89.89% |
| `dayu/fins/ingestion_runtime.py` | 90.68% |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | 92.13% |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | 82.51% |

全部 changed production file 均达到不低于 80% 的 line coverage。

### 6.3 Static validation

- full Pyright：`pyright dayu/ tests/ utils/`，`0 errors, 0 warnings, 0 informations`。
- scoped Ruff：S2 production allowlist 与五个测试文件，`0`。
- full Ruff baseline：仍为既有 `152` 项（`F401 72`、`E402 66`、`F841 10`、`F541 3`、`F821 1`），相对实现前未扩散。
- `git diff --check`：通过。
- accepted plan SHA-256：匹配固定值。
- revision/snapshot scan：旧 `.digest` 与 selected-field revision/hash builder 无残留；持久化 token 和 snapshot API 只由 storage owner 产生/投影。
- path/identity/exception scan：无外部 identity 到路径的直接反推；snapshot public contract 与 failure graph 不暴露 published/private locator。
- resource-owner follow-up scan：marker guard 不再使用 raw `try/finally` release；initial-fstat close 使用 safe secondary note；temp root 只在删除成功后清空。
- LLM-facing scan：本轮未新增或改写 LLM-facing 财报业务语义；opaque token、私有 key 与 snapshot 资源状态未进入 tool output/prompt。
- deferred-scope scan：read runtime 的 before/after revision、独立 meta cache、processor cache 与 filing-first 路由仍存在，明确保留给后续 handoff，没有在 S2 旁路实现。

## 7. S3 handoff 与 residual

后续 slice 仍需让 read runtime 以 storage snapshot 统一 processor、meta、provenance/citation 与 borrow 生命周期，并届时移除当前 before/after `get_source_revision(...)` checkpoint、独立 meta cache 与 filing-first 路由。本轮没有提前实现这些行为。

Residual：

- full Ruff 仍有 152 项既有 baseline，但本轮 scoped Ruff 为零且 baseline 未扩散。
- 五文件 pytest 有 3 条既有 warning，不影响测试结果。
- 除上述明确 deferred 的 read-runtime consumer 迁移外，未发现 R07-S2 implementation blocker。

## 8. Handoff

R07-S2 implementation 已完成，停在 **Controller validation**；不继续进入 code review fix、S3、stage/commit/push/PR。
