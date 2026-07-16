# WU-SEMANTIC-OWNERSHIP-01 / R07-S1 Controller Validation

## 1. Gate 与结论

- umbrella work unit：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal checkpoint：R07-S1 storage-owned opaque identity；不是新 WU，也不是独立 accepted sub-WU。
- accepted R07 plan：`3b52ab112e37233f4f6452793cb18c15c204636d`。
- implementation transition HEAD：`386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-r07-s1-implementation-codex.md`。
- Controller verdict：**PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_S1_CODE_REVIEW**。

该结论只授权 AgentMiMo / AgentDS 对当前累计 S1 working tree 做完整 code review；不表示 S1 finding 已关闭，不授权 S2、stage、commit、push 或 PR。R07 只有 S3 complete tree 通过最终累计 review 后才允许 accepted implementation commit。

## 2. Scope 与 owner 复核

Controller 独立核对 `git status --short`、`git diff --name-only`、accepted plan §7.1 与实际 diff：

- production 严格为 9 个 S1 allowlist 文件，其中新增唯一私有 mapping owner `dayu/fins/storage/_fs_identity.py`；
- tests 严格为 4 个 S1 allowlist 文件；
- 唯一新增实施证据为 AgentCodex artifact；
- 暂存区为空，HEAD 未移动；
- 没有 plan/control/design/README、S2/S3、R08+、deferred ISSUE、统一 authorization 或 allowlist 外代码改动。

直接实现证据确认 owner 位于 `dayu.fins.storage`：external ticker/document identity 只做 exact non-empty UTF-8 校验；namespace-separated deterministic private locator 与 `.identity.json` descriptor 共同由单一私有模块产生和校验。point lookup、enumeration、target/staging/backup、journal recovery、company inventory、source/material、processed、rejected、blob、manifest 与 maintenance cleanup 都通过同一 owner 恢复或核对 exact external identity，没有新增 reverse registry、scan fallback、compat shim 或 consumer-side normalization。

`CompanyMetaInventoryEntry.directory_name` 已 breaking cutover 为可选 external `ticker`，lock-only/corrupt evidence 使用既有 typed status 且不投影 private candidate。旧 `_normalize_document_id`、`_list_directory_names`、`_published_ticker_directory_names` 均无残留；115-hit baseline 收敛为 8 个已分类的 company-alias/private-backup parser 命中。

## 3. Controller 独立验证

### 3.1 Tests 与 line coverage

Controller 重新执行四个 exact full-file tests：

```text
tests/fins/test_fins_storage_provider.py
tests/fins/test_fins_storage_atomicity.py
tests/fins/test_fins_ingestion_runtime.py
tests/fins/test_sec_pipeline_download.py
```

结果：`336 passed, 3 warnings in 14.22s`。随后以 branch collection 重跑同一组 coverage tests，结果仍为 `336 passed, 3 warnings in 14.68s`。三个 warning 均来自已安装 `edgar` 包的既有 deprecation warning。

按 accepted plan 明确的 line gate `covered lines / statements` 复核，9 个 changed production files 分别为：

| file | line coverage |
| --- | ---: |
| `dayu/fins/domain/document_models.py` | 96.08% |
| `dayu/fins/storage/_fs_identity.py` | 82.52% |
| `dayu/fins/storage/_fs_storage_utils.py` | 87.22% |
| `dayu/fins/storage/_fs_storage_infra.py` | 88.29% |
| `dayu/fins/storage/_fs_blob_core.py` | 90.77% |
| `dayu/fins/storage/_fs_company_meta_core.py` | 91.11% |
| `dayu/fins/storage/_fs_maintenance_core.py` | 93.25% |
| `dayu/fins/storage/_fs_processed_core.py` | 91.60% |
| `dayu/fins/storage/_fs_source_document_core.py` | 84.45% |

全部达到逐文件 `>=80%` line coverage。`coverage report` 的 branch-inclusive 总表另显示 85% aggregate；该 composite 数值不替代 plan 规定的逐文件 line gate。

### 3.2 Static、diff 与 scans

- full pyright：`pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`；
- scoped Ruff：9 个 production + 4 个 test allowlist 文件 → `All checks passed!`；
- full Ruff fingerprint：`152`，精确为 `72 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`，未扩散；
- `git diff --check`：通过；
- staged path：空；
- legacy path owner scan：`_normalize_document_id`、`_list_directory_names`、`_published_ticker_directory_names` 为零；
- private-value scan：公开 raise interpolation 与 storage log private-value 命中为零；唯一 external-identity join candidate 位于 `_fs_identity.py`，其 RHS 是 namespace-separated `_derive_storage_key(...)`，不是 raw identity path join；
- S2 revision/snapshot 代码仍为 transition base 的既有实现，没有在 S1 提前切换或加入兼容分支。

## 4. Security、recovery 与 failure behavior

Controller 对实现与黑盒 tests 交叉复核：

- filename、entry name、object key 与 local URI 仍由单路径组件/containment owner 校验；opaque identity 放宽没有放宽物理 filename 或 URI；
- ticker/source/processed/rejected identity root、descriptor、固定子目录、target/staging/backup、copy tree 与 recovery evidence 对 symlink/non-regular/containment mismatch fail closed；
- descriptor 在首个 payload 前经既有 `_write_json` 原子写入、replace 与 fsync 路径发布，失败时不留下可枚举的 partial mapping；
- writer mutex、publication guard、terminal capability consumption、四个 journal phase、old/new publication、backup restore 与 malformed evidence preserve 语义保留；
- recovery journal 保存 exact external ticker，但 target/backup/staging 仍必须通过 descriptor 与派生 private key 交叉验证，不能只凭 journal、lock stem 或目录名投影业务 ticker；
- complete-source validator、processed/rejected meta、manifest/list 与 descriptor 做同源一致性校验；stale filing cleanup 先恢复 external document id，再执行既有 `fil_` 业务分类；
- storage public exception 不包含 workspace absolute path 或 private ticker/document locator，没有新增下游 sanitizer；
- 未删除 containment、symlink、atomic write、process fencing、resource budget、DNS/peer 或其它既有防御；未实现统一 tool authorization framework。

## 5. 双路 review mandatory focus

Reviewer 必须对当前完整累计 S1 diff 做 adversarial review，至少覆盖：

1. descriptor 是否真是 directory → external identity 的唯一 truth，所有 point lookup/list/meta/manifest/registry/maintenance/recovery 是否没有遗漏 raw path inference；
2. `expected_storage_key` 只在 caller 已从 target/backup locator 解析并绑定真实 private key时使用，不能成为任意目录跳过 basename 双向校验的入口；
3. target/staging/backup/lock candidate、orphan recovery、四个 crash phase 与 concurrent publication 中是否仍保持 R06 containment、锁顺序、primary-error 与 old/new atomicity；
4. source/material/processed/rejected/blob 的 descriptor 与业务 meta/manifest 双向核对是否完整，corrupt evidence 是否 fail closed 而非跳过或覆盖；
5. opaque ticker/document id 可含 Unicode、separator、drive-like、`.`、`..` 时，filename/object-key/local URI、exception、log 和 inventory 是否仍不泄漏 private locator或发生 traversal；
6. company alias normalization 是否只属于业务 alias，不再拥有 storage identity；public inventory breaking cutover是否没有 alias/compat；
7. 115-hit inventory、`_remove_manifest_items`、真实 filesystem recovery/security tests与全量四文件回归是否足以覆盖 S1 handoff；
8. 是否存在任何 S2 revision/snapshot、R08+、deferred ISSUE 或统一 authorization 偷带。

## 6. 下一 gate

唯一允许的下一步是 AgentMiMo / AgentDS 并发执行完整累计 S1 code review。Controller 统一裁决所有 findings；任何 accepted finding 必须由 AgentCodex 在同一 working tree 修复、经 Controller 验证并双路完整 re-review 后，才能进入 S2。S1 不创建 accepted commit。

## PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_S1_CODE_REVIEW
