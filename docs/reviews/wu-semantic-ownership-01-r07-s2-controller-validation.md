# WU-SEMANTIC-OWNERSHIP-01 R07-S2 Controller validation

## 1. Gate 与结论

- Active WU：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Internal remediation sub-WU：R07，slice：S2 persisted revision and stable snapshot。
- Accepted plan：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`。
- Accepted plan SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`，Controller 独立复算一致。
- Baseline HEAD：`386fef8d7a7ecbd977c455ca86bb8bab875d1a98`；S1/S2 依 accepted plan 均为未提交的累计 checkpoint。
- 结论：**PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_S1+S2_CODE_REVIEW**。
- 本结论不授权 S3、accepted implementation commit、R08+、Issue 142/151/175/177/178、统一 tool authorization、push 或 PR。

## 2. 实现边界复核

Controller 完整复核了 S2 implementation artifact、生产代码、测试与 README 变更，确认：

- `SourceDocumentRevision` 只保留 storage-persisted opaque `token`，仅作非空 exact equality；没有 hash grammar、alias、兼容字段或消费者重算。
- complete-source mutation owner 在 batch 原子发布时生成并持久化 revision；public source meta 不投影 storage 私有 revision 字段。
- storage owner 提供 light/full stable snapshot；full snapshot 的 descriptor、meta、provenance、revision、文件清单、primary 与文件内容来自同一稳定版本。
- preprocess 在 batch 内先获得 full snapshot，关闭 snapshot 后再 commit；SEC fiscal multi-file 与 active 6-K consumer 共用单一 snapshot 生命周期。
- S3 的 read-runtime snapshot/cache/borrow 迁移、before/after revision checkpoint 删除与 filing-first 路由删除仍未实施，边界保持 deferred。
- filesystem containment、symlink fail-close、atomic staging/swap/rollback、publication guard、path-free public exception graph 与 typed storage errors 均保留；没有引入统一权限框架。
- `dayu/fins/README.md` 与 `tests/README.md` 只陈述当前 S2 owner contract，未提前宣称 S3 完成。

## 3. Controller accepted findings 与修复

初轮 Controller 验证发现三个同属 snapshot resource owner 的 material findings，并在同一 S2 implementation gate 交回 AgentCodex 修复：

| ID | Finding | 最终状态 |
|---|---|---|
| `R07-S2-CV-F01` | `_read_published_marker()` 的 raw `try/finally` 会让 publication-guard release 次失败覆盖 marker/meta/descriptor 主失败。 | **closed**：三态保留 marker 主失败，release 次失败只追加 path-free action/type/errno note；marker 成功时 release failure 才成为主失败。 |
| `R07-S2-CV-F02` | snapshot `close()` 在 rmtree 成功前丢失唯一 temp-root cleanup locator，首次删除失败后无法重试并会泄漏临时树。 | **closed**：资源先进入不可读状态，cleanup locator 只在真实删除成功后清空；失败后的并发/重复 close 在同一锁边界重试且保持幂等。 |
| `R07-S2-CV-F03` | initial `fstat` 失败发生在 stream 加入统一 cleanup list 前，直接 close 可用次失败覆盖 fstat 主因。 | **closed**：保留 fstat 主因，close failure 只追加 path-free action/type/errno note。 |

新增 owner-level tests 分别断言双失败 exception graph、关闭后不可读、失败后并发重试只完成一次真实删除、后续幂等，以及完整 graph 无 workspace/private locator。

## 4. Controller 独立验证

### 4.1 精确回归

Controller 独立运行三个新增 finding 节点：

```text
3 passed in 0.36s
```

### 4.2 五文件累计测试

Controller 独立运行：

- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_processor_read_consistency.py`

结果：

```text
399 passed, 3 warnings in 23.72s
```

三条 warning 均来自既有 `edgar` deprecated import，不是本轮新增失败。

AgentCodex 的 branch coverage run 同样为 `399 passed, 3 warnings`；全部 S2 changed production files line coverage 为 `82.51%`–`100%`，其中 `dayu/fins/storage/_fs_source_snapshot.py` 为 `89.89%`。

### 4.3 静态与传播验证

- full `pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- cumulative S2 production/test allowlist scoped Ruff：`All checks passed!`。
- `git diff --check`：通过。
- revision/snapshot source scan：生产代码与测试无旧 `.digest`、revision hash builder 或 hash grammar 残留；命中只存在于 implementation artifact 对已删除语义的说明。
- snapshot temp-root scan：验证后无 `/tmp/dayu-source-snapshot-*` 残留。
- plan SHA-256：匹配 accepted fixed plan。

## 5. Controller 裁决

`R07-S2-CV-F01..03` 已全部关闭，S2 当前无 open accepted finding、无 blocker。下一 gate 是 AgentMiMo 与 AgentDS 并发执行完整的累计 R07-S1+S2 code review；任何 accepted finding 必须由 AgentCodex 修复并经双路完整 re-review 关闭。按 accepted plan，S1/S2 仍不得产生中间 commit，S3 与最终 R07 accepted implementation commit 均未授权。
