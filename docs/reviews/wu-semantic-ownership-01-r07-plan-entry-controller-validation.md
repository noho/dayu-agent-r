# WU-SEMANTIC-OWNERSHIP-01 / R07 Plan Entry Controller Validation

## 1. Gate 与 verdict

- umbrella work unit：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal remediation sub-WU：R07 Fins storage-owned snapshot/revision 与 opaque identity；不是新 WU。
- plan artifact：`docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`。
- transition base：`5f09e2cc2e4edfc7dc1388e14744bf1300637093`。
- R06 completion commit：`f1c56ea90c587314cc7cba35e5b4c790d13d2fc3`。
- plan content SHA-256：`ae8d74f8a9a7fd677face4211cb7402bdc5e56eb6c80bfe8cb1791a4e46a7bc7`。
- Controller verdict：**PASS / READY_FOR_DUAL_PLAN_REVIEW**。

这只表示计划已达到可被两路独立 reviewer 完整挑战的最低证据与闭集，不表示计划已 accepted，也不授权 implementation、stage、commit、push 或 PR。

## 2. Motivation 与 semantic owner 复核

直接代码证据确认问题真实存在：

1. `dayu.fins.storage` 仍把 ticker/document id 同时当业务 identity 与 filesystem 单路径组件，115 个 `_normalize_ticker/_normalize_document_id` 命中分布在 7 个 storage 文件；这会拒绝合法 opaque business identity，却不能替代 containment owner。
2. `_fs_source_document_core.py` 仍从 consumer-selected meta/file fields 计算 SHA-256 `SourceDocumentRevision`，而 R06 complete publication 没有持久化 storage-owned publication revision。
3. `read_runtime.py` 仍有两套 revision-before/after 双读路径和一个独立 diagnosis revision consumer；source kind、meta、primary source、provenance 与 citation 仍可分开读取。
4. 8 个 production files / 9 个 `.materialize()` 调用中，Fins processor 仍可持有指向 published tree 的裸 path；`ingestion_runtime.py`、`sec_fiscal_fields.py` 与 standalone 6-K repair 还有直接多次 repository read residual。

因此唯一正确 owner 是 storage：它产生并验证 external identity↔internal key mapping、published revision 和一致 snapshot；read/cache/citation 只消费同一 snapshot。计划没有通过 consumer fallback、兼容 shim、第二 provenance 或 speculative `BusinessSource` 掩盖 owner 错位。

## 3. Scope、inventory 与 slice closure

Controller 独立复核结果：

| evidence | result |
| --- | --- |
| plan scope | 当前唯一 workspace change 是新 plan artifact；HEAD 未变 |
| identity inventory | 7 个 storage files / 115 个 normalizer matches，与 plan 一致 |
| materialize inventory | 8 个 production files / 9 个 calls，与 plan 一致 |
| revision inventory | production `get_source_revision` 命中 9；read runtime before/after related matches 12；计划逐 owner 删除而非只做文本替换 |
| composition roots | Default Fins runtime、CN pipeline、SEC pipeline、standalone 6-K repair 四个 root 保持 shared repository core |
| allowlist refinement | 新 identity/snapshot 私有 owner及 ingestion/fiscal/6-K/process-target cleanup 都有直接当前调用证据；未扩大到 R08 financial semantics 或跨层 Host contract |
| slices | S1 opaque key；S2 persisted revision + stable snapshot；S3 read/cache/citation migration，最多三 slice且有累计验证边界 |

计划明确 fresh schema，不读取/迁移/兼容 raw layout，不双写；filename/local URI/containment/symlink/atomic write/fsync 与 R06 writer/publication/recovery state machine均保留。R08-R12、Issue 142/151/175/177/178 和统一 tool authorization 均明确不实施。

## 4. Contract sufficiency

计划已经给出 code-generation-ready 的最低 contract：

- exact external identity 不被 storage strip/case-fold/Unicode normalize/basename；唯一 private mapping owner 生成 namespace-separated key，并以同一 persisted descriptor round-trip/交叉验证。
- raw identity 不再参与 target/staging/backup/lock/source/processed/rejected/object-key path join；enumeration/recovery 不从 private name 反推业务 identity。
- complete-source publication owner生成并持久化 opaque revision；consumer 不生成、不挑字段 hash，也不把 grammar 暴露为业务/README/LLM contract。
- storage snapshot 同源提供 identity、kind、complete meta、provenance、revision、declared files和primary；full snapshot resource不暴露published path，显式幂等 close。
- transient publication change由storage有界重取，持续变化产生专用typed consistency exhaustion；read runtime单点映射既有 `source_changed_during_read`，ordinary I/O/corruption/cancel不混淆。
- cache retirement/borrow/close owner防止active read使用已关闭资源；citation/result机械投影同一borrowed snapshot。

具体internal key/revision grammar、attempt次数、退避、私有resource类名没有成为business/tool/LLM contract。计划对具体最小 API/实现算法所作的选择属于本次 independent plan 的可 review 决策，而非 umbrella 预先冻结。

## 5. Baseline 与 validation entry

AgentCodex 在 `5f09e2cc` 实际运行并记录：

- R07核心测试：`297 passed, 3 warnings`。
- allowlist refinement直接节点：`5 passed, 3 warnings`。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- scoped Ruff：`read_runtime.py` 两个既有 F401；full fingerprint 152。
-正式测试目录全量：`4821 passed, 3 failed, 3 skipped, 5 deselected, 3 warnings`。

Controller 独立复现两个稳定 inherited failure：

- `test_prepare_host_admin_loads_only_host_runtime_without_models_or_secrets`：缺少 `wait_poller_policy`，首个稳定 owner在 `config_loader.py:2303`。
- `test_service_does_not_import_forbidden_layers`：仅两条既有 Service→Fins helper import violation，稳定在 `test_import_boundary.py:101`。

第三个 logging failure 是正式全量顺序相关且定向组合单跑通过；计划只允许同一 node/handler 指纹，不把它豁免为当前正确行为。裸 `pytest -q` 被 ignored `workspace/tmp/r06-base-9c07b88d/tests` 与正式 conftest 的 import-path mismatch 污染；该有意保留证据目录不属于 R07，不得通过删除它制造绿色。任何 changed-owner failure、新 full-suite node/rule/location/fingerprint都必须 stop。

每 slice 已列 targeted/full allowlist tests、每 changed production file coverage、full pyright、scoped/full Ruff delta、diff/scope、README、source/AST/LLM scans和真实filesystem A/B/transient/sustained/cache/citation/recovery security smoke。

## 6. 双路 review 必须重点挑战

以下是 reviewer 的 mandatory adversarial focus，不是 Controller 预先裁决的 finding：

1. descriptor + deterministic locator 是否真是单一最小 mapping truth，是否遗漏 ticker/document namespace、manifest、recovery、lock-only inventory 或 collision path。
2. chosen snapshot protocol、`materialize_files` 参数和 source-kind ambiguity contract 是否保持 storage ownership，没有把 private implementation或不必要 public surface冻结。
3. fd-copy + post-copy revision check 是否在 R06 rename model下排除 A/B mixed version，并正确区分 transient change、static corruption与ordinary I/O；是否存在无界resource/latency或过度复制。
4. preprocess先持writer mutex再取published snapshot、SEC fiscal/6-K direct consumers以及read runtime borrow/cache lifecycle是否覆盖取消、build/citation failure、eviction/clear/process target cleanup。
5. revision变化边界是否只对应有效source publication，delete/reset/rollback/recovery/non-source mutation是否无歧义。
6. coverage命令、累计allowlist、full-suite inherited ledger和per-slice cumulative review/最终deepreview顺序是否与AGENTS.md及umbrella phaseflow精确一致，且没有用更严格指标的名称混淆line coverage真值。
7. README/LLM scans是否既不暴露key/revision/path，也不把internal storage术语写成模型必须理解的业务事实。

reviewer 必须阅读全文和真实代码，不得把上述问题当成已接受 finding，也不得因计划很详细而跳过overdesign/semantic ownership检查。

## 7. 下一 gate

唯一允许的下一步：AgentMiMo 与 AgentDS 对同一个 immutable plan 并发执行完整 plan review。Controller 之后统一裁决；所有 accepted findings 由 AgentCodex 修复并双路完整 re-review。计划 accepted local commit 之前不得进入 implementation。

## PASS / READY_FOR_DUAL_PLAN_REVIEW
