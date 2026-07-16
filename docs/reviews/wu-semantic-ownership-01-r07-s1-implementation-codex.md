# WU-SEMANTIC-OWNERSHIP-01 R07-S1 implementation（Codex）

## 1. 实施结论与停止点

- Work unit：既有 `WU-SEMANTIC-OWNERSHIP-01`，内部 checkpoint `R07-S1 opaque storage identity`；不是新 WU。
- accepted plan commit：`3b52ab112e37233f4f6452793cb18c15c204636d`。
- transition HEAD：`386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- plan 文件 SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- 实施范围：仅 plan §7.1 S1 的 exact production/test allowlist，以及本文件。
- 当前 gate：**Implementation complete，等待 Controller validation**。
- 明确停止：未实施且不得自行进入 S2 token/revision/snapshot，也未实施 S3 cache/read/citation、R08+、deferred ISSUE、统一 authorization。
- Git 状态：未 stage、未 commit、未 push、未创建 PR。

## 2. Owner 判定

问题成立且严重性与 plan 一致：external ticker/document identity 过去同时承担业务 identity 与本地路径组件职责，导致路径字符校验、目录名枚举、lock/backup 名称反推等 filesystem 偶然行为侵入业务 contract。正确 owner 是 `dayu.fins.storage` 的文件系统 identity boundary，而不是 tools、ingestion、调用者或测试夹具。

本次实现建立唯一 owner：

1. external identity 只做非空、UTF-8 可编码校验，并保持 exact 字符串；不 strip、不大小写折叠、不做 Unicode 归一化。
2. storage owner 按 namespace 派生 filesystem-safe private locator。
3. 每个 identity directory 的 `.identity.json` descriptor 是 directory → external identity 的唯一 round-trip truth。
4. lookup、枚举、恢复、target/staging/backup 校验都必须验证 descriptor 与 namespace、external identity、private locator 的双向一致性。
5. 缺失或损坏 descriptor 一律 fail closed；fresh schema 不提供 migration、fallback 或 compatibility branch。

## 3. 实际 diff

在新增本 artifact 前，implementation/test diff 共 13 个文件：`2570 insertions / 753 deletions`。其中 tracked diff 为 `2258 insertions / 753 deletions`，新文件 `_fs_identity.py` 为 312 行。

| 文件 | 实际变更 |
| --- | --- |
| `dayu/fins/domain/document_models.py` | `CompanyMetaInventoryEntry.directory_name` breaking cutover 为 `ticker: Optional[str]`；lock-only/损坏 evidence 不再伪装成业务 ticker。 |
| `dayu/fins/storage/_fs_identity.py`（new） | 唯一拥有 exact external identity 校验、namespaced private key 派生、descriptor-first 原子创建、双向读取校验与 descriptor-only 枚举。 |
| `dayu/fins/storage/_fs_storage_utils.py` | 删除旧 document-id path normalizer 与通用目录名枚举；公司 alias helper 改名以明确只属于业务 alias；JSON/atomic 错误不再暴露 private path。 |
| `dayu/fins/storage/_fs_storage_infra.py` | target/staging/backup/lock/recovery/ticker/source/processed/rejected/manifest 路径全面切换 private locator；journal 保留 exact external ticker 作为 transaction evidence，但不得从路径反推；补齐 symlink、containment、regular-file、copy、publication/recovery 校验；迁移 `_remove_manifest_items`。 |
| `dayu/fins/storage/_fs_blob_core.py` | blob handle、entry、read/write/local URI 均通过 descriptor-verified private directory；identity descriptor 不作为业务文件列出；公开错误不含 private locator。 |
| `dayu/fins/storage/_fs_company_meta_core.py` | company read/upsert/resolve/inventory 使用 exact descriptor identity；alias normalization 仅用于公司 alias 查询；published/backup/lock 只产生 private candidate，lock-only 投影 `ticker=None`。 |
| `dayu/fins/storage/_fs_maintenance_core.py` | rejected filing identity、registry、list/read/upsert 与 stale cleanup 使用 external ID + descriptor；`cleanup_stale_filing_documents` 及其 callee `_remove_manifest_items` 完成 cutover。 |
| `dayu/fins/storage/_fs_processed_core.py` | processed CRUD/handle/meta/mark/delete/clear 使用 exact identity；meta 必须与 descriptor 一致；create/update 以业务 meta 存在性判定，不能把 descriptor directory 误判为既有产物。 |
| `dayu/fins/storage/_fs_source_document_core.py` | source/material/filing CRUD、list、handle、meta、XBRL、reset 全部使用 exact identity；processed list 双向核对 manifest、descriptor enumeration 与 meta document ID。 |
| `tests/fins/test_fins_storage_provider.py` | 迁移 owner fixtures；覆盖全部 storage namespace opaque round-trip、Unicode/层级分隔符/drive/dot/dotdot、collision/corruption/meta mismatch、inventory 不泄露 private key、lock-only、stale cleanup、公开异常不泄露 locator。 |
| `tests/fins/test_fins_storage_atomicity.py` | recovery 四 phase、opaque journal、orphan backup、descriptor symlink/mismatch、filename/local URI attack、processed/rejected corruption 与真实文件系统安全测试。 |
| `tests/fins/test_fins_ingestion_runtime.py` | fixture 改用 storage owner locator；增加 hierarchical document ID 从 ingestion request 到 storage 的 round-trip。 |
| `tests/fins/test_sec_pipeline_download.py` | SEC pipeline fixtures/断言改用 storage owner path helpers，不再固化 external ID 等于目录名。 |

未修改 plan、control、design、旧 review、README、R08+ 或 allowlist 外生产/测试文件。

## 4. 调用图与真源

```text
external ticker / document_id
  -> _require_external_identity                 # exact，不把业务 ID 当路径组件
  -> _derive_storage_key(namespace, identity)   # storage-private locator
  -> _identity_directory_path

write
  -> _ensure_identity_directory
       -> create private directory
       -> _write_json(.identity.json)            # 先 descriptor，原子 replace + fsync
       -> _read_identity_descriptor              # 写后双向验证

point read
  -> _identity_directory_for_read
       -> _read_identity_descriptor
            -> exact descriptor fields
            -> namespace match
            -> requested external identity match（若 caller 已知）
            -> derived private key match

enumeration
  -> _list_external_identities
       -> enumerate private candidates
       -> reject symlink/corrupt/duplicate evidence
       -> project external identity only from descriptor

ticker transaction
  begin_batch(external ticker)
    -> private writer/publication lock
    -> private target/staging/backup locators
    -> descriptor-verified copy / publication / rollback

recovery
  journal exact ticker + private candidate locator
    -> descriptor verification
    -> publication guard
    -> STARTED / BACKED_UP_TARGET / SWAPPED_TARGET / COMMITTED recovery
    -> never infer external ticker from directory/lock/backup name

company inventory
  target / backup / lock private candidates
    -> publication guard by private key
    -> target/backup descriptor evidence
    -> external ticker, or lock-only ticker=None

source / material / processed / rejected / blob
  ticker descriptor root
    -> fixed owner subdirectory
    -> document namespace private locator + descriptor
    -> business meta/manifest exact identity cross-check
```

descriptor 是 directory → external identity 的唯一 round-trip truth。Journal 中的 exact ticker 只属于 transaction state；recovery 仍须用 descriptor 验证，不能以 journal 或 private locator 单独投影 published identity。

## 5. 行为与安全保留

- **Containment**：所有派生 locator 仍受固定 root containment 约束；transaction copy 前递归拒绝 symlink 与特殊文件。
- **Symlink**：identity namespace root、identity directory、descriptor、ticker 固定子目录、source root、staging/target/backup 与 recovery evidence 均 fail closed。
- **Filename / entry name**：opaque document ID 放宽不影响物理 filename、manifest entry name、object key 的单路径组件规则。
- **Local URI**：URI 仍由 storage owner 生成并验证；绝对路径、路径穿越、symlink escape 与非 regular file 均拒绝。
- **Atomic / fsync**：descriptor 使用既有 `_write_json` 原子临时文件 + replace + fsync 路径；descriptor 失败时仅清理由当前调用创建的空目录。
- **Writer/publication**：writer capability、ticker 级 writer mutex、独立 publication guard、terminal capability consumption 与 reader publication window 保留。
- **Recovery**：四个 journal phase、backup restore、committed cleanup、malformed evidence preserve、dry-run 与锁顺序保留；identity 改为 descriptor 驱动。
- **Manifest**：external IDs 原样持久化；source/processed/rejected list 与 meta/descriptor 做一致性校验；stale cleanup 不从目录名反推 document ID。
- **公开错误**：本次 S1 可触达 storage exception 只包含业务可读 identity/filename 或不含值的诊断，不插入 `Path`、workspace path 或 private key；没有新增下游 sanitizer。

## 6. Controller 并行发现的收敛

1. `get_processed_meta` contract 返回 `dict`：owner test 改为 `processed_meta["document_id"]`，未在生产代码加入 attribute compatibility。
2. filename/local URI attack：测试断言 `ValueError`、不发布 target、terminal capability 已消费；不绑定 complete validator 的内部验证顺序或具体 message。
3. private locator exception leak：在 storage producer boundary 清理 `_fs_storage_utils`、company、processed、blob、maintenance、source、infra 的可触达异常；新增黑盒测试确认经 `str(exc)` 也不出现 workspace path、target path 或 private key。

## 7. 测试证据

### 7.1 Targeted 与 exact full-file

- S1 targeted convergence：`45 passed, 3 warnings`。
- exact full-file：
  - `tests/fins/test_fins_storage_provider.py`
  - `tests/fins/test_fins_storage_atomicity.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `tests/fins/test_sec_pipeline_download.py`
- 最终结果：`336 passed, 3 warnings in 14.15s`。
- 三个 warning 均来自已安装 `edgar` 包的既有 deprecation warning，本 diff 未新增 warning 类型。

### 7.2 真实 filesystem recovery/security smoke

独立选择 14 个 owner tests；含参数化后共 `18 passed, 3 warnings in 1.31s`。覆盖：

- 全 namespace opaque round-trip；
- Unicode、层级分隔符、Windows drive、`.`、`..`；
- collision/corrupt descriptor/business meta mismatch；
- company inventory 与 lock-only private key 不投影；
- public exception private locator leak；
- stale filing cleanup + `_remove_manifest_items`；
- local URI symlink escape；
- opaque journal containment；
- orphan backup descriptor recovery；
- STARTED/BACKED_UP_TARGET/SWAPPED_TARGET/COMMITTED 四 phase；
- descriptor symlink/mismatch；
- filename/absolute/local URI attack fail-closed + capability consumption；
- ingestion hierarchical document identity round-trip。

### 7.3 Changed production file line coverage

计算口径严格为 `covered_lines / num_statements`。该 coverage run 已包含最终运行逻辑；其后只修正 changed helper docstring 的异常说明，按 Controller 指示未重复 full pytest/coverage。

| Changed production file | covered_lines | num_statements | 比例 |
| --- | ---: | ---: | ---: |
| `dayu/fins/domain/document_models.py` | 417 | 434 | 96.08% |
| `dayu/fins/storage/_fs_identity.py` | 85 | 103 | 82.52% |
| `dayu/fins/storage/_fs_storage_utils.py` | 157 | 180 | 87.22% |
| `dayu/fins/storage/_fs_storage_infra.py` | 814 | 922 | 88.29% |
| `dayu/fins/storage/_fs_blob_core.py` | 59 | 65 | 90.77% |
| `dayu/fins/storage/_fs_company_meta_core.py` | 123 | 135 | 91.11% |
| `dayu/fins/storage/_fs_maintenance_core.py` | 152 | 163 | 93.25% |
| `dayu/fins/storage/_fs_processed_core.py` | 120 | 131 | 91.60% |
| `dayu/fins/storage/_fs_source_document_core.py` | 353 | 418 | 84.45% |

全部 changed production file 均达到 `>= 80%`。

## 8. 静态检查与 source/AST scans

### 8.1 类型、lint 与 diff

- full pyright：`pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- scoped Ruff：全部 9 个 production allowlist 文件与 4 个 test allowlist 文件 → `All checks passed!`。
- full Ruff fingerprint：仍为既有 `152`：
  - `72 F401`
  - `66 E402`
  - `10 F841`
  - `3 F541`
  - `1 F821`
- 与实施前 fingerprint 相同，没有新增或扩散。
- `git diff --check`：通过。

### 8.2 旧 115-hit inventory 收敛

使用 plan 指定 symbol family 对七个 storage 文件逐文件复扫：

| 文件 | baseline hits | final hits | final 分类 |
| --- | ---: | ---: | --- |
| `_fs_blob_core.py` | 5 | 0 | 旧路径 identity 逻辑清零。 |
| `_fs_company_meta_core.py` | 7 | 2 | 仅 private backup parser import/call。 |
| `_fs_maintenance_core.py` | 19 | 0 | 旧路径 identity 逻辑清零。 |
| `_fs_processed_core.py` | 13 | 0 | 旧 document ID normalizer/目录枚举清零。 |
| `_fs_source_document_core.py` | 33 | 0 | 旧 document ID normalizer/目录枚举清零。 |
| `_fs_storage_infra.py` | 32 | 3 | private backup parser definition + 两个 caller。 |
| `_fs_storage_utils.py` | 6 | 3 | 仅 `try_normalize_ticker` import/doc/call，属于 company alias 业务真源，pattern 名称重叠。 |
| **合计** | **115** | **8** | 8 个均已逐项分类，不是 external identity → path fallback。 |

关键 symbol 结果：

- `_normalize_document_id`：0；实现已删除。
- `_list_directory_names`：0；实现已删除。
- `_published_ticker_directory_names`：0；由 private candidate + descriptor 投影替代。
- `_normalize_ticker`：无旧 storage path normalizer；仅 `try_normalize_ticker` 三个文本命中，用于 company alias 查询。
- `_parse_backup_directory_name`：5 个命中，只解析 private `<key>.bak.<transaction>` locator，不产生 external ticker。

### 8.3 Identity/path/private leak AST scan

- public raise private-value interpolation：`[]`。
- storage log private-value argument：`[]`。
- external identity path-join candidate：仅 `_fs_identity.py` 一处，AST 同时确认 RHS 是 `_derive_storage_key(namespace, external_identity)`；即先派生 private key 后 join，不是 raw external identity join。
- `lock_path.name` 仅用于发现 private candidate key；company inventory 随后必须读取 target/backup descriptor，lock-only 返回 `ticker=None`。
- directory `child.name` 的残余使用仅属于固定 owner filenames、blob business entry name 或 descriptor enumeration candidate；不从目录名恢复 external identity。
- 黑盒 source-to-tool 风险由 `test_public_storage_errors_never_expose_internal_locator_or_workspace_path` 覆盖，因为现有 tools/ingestion 会直接消费 `str(exc)`。

## 9. Residual、非目标与 handoff

- Fresh schema 明确无 migration/fallback/compat：旧 raw identity-as-directory 数据若存在会 fail closed；这是 accepted S1 contract，不是待补兼容项。
- private key 格式只属于 storage implementation；公共 model、异常、inventory 与测试 contract 均不承诺其格式。
- full Ruff 的 152 个既有错误与 edgar 的三个 deprecation warning 未在本 WU 扩散；按 scope 不处理。
- 未修改任何 README。S1 不改变最终用户工作流，且用户明确禁止 README 改动。
- 未修改 plan/control/design/旧 review；未实施 S2/S3/R08+/deferred ISSUE/统一 authorization。
- 当前没有已知 S1 correctness blocker；剩余动作仅为 **Controller validation**。
- Controller 若通过，应由 Controller 决定后续 gate；本实现代理在此停止，严禁自行进入 S2。
