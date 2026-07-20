# WU-SEMANTIC-OWNERSHIP-01 / R07-S1 code review Controller adjudication

## 结论

`FIX REQUIRED`

第一路 AgentMiMo artifact 为
`docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-mimo.md`，结论为
`PASS-WITH-FINDINGS`，报告 5 个 finding。第二路 AgentDS artifact 为
`docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-ds.md`，结论为
`PASS-WITH-FINDINGS`，报告 8 个 finding。

Controller 逐项复核 accepted R07 plan、当前 production/test tree 与异常传播链后，接受
2 个 reviewer finding group，并新增 1 个由独立真实文件系统 smoke 证实的 Controller
finding group。当前 ledger 为：accepted/fix-required `3`、rejected-with-reason `11`、
deferred `0`、blocker `0`。产品裁决与设计真源没有矛盾，不需要用户重新裁决。

## 动机与 owner 复核

三个 accepted group 都是当前 S1 实现的真实 owner-boundary 缺口：

- bulk/stale cleanup 是 destructive mutation owner；它必须在任何删除前证明整个候选集合
  可识别且一致，不能先删一部分再遇到损坏，也不能把缺失/损坏 meta 当作不存在而跳过；
- `begin_batch` 是 writer capability 初始化 owner；初始化主失败不能被 lock release 的次级失败
  替换；
- filesystem storage 是 private locator 的产生 owner；它不能把 workspace absolute path 或
  private storage key 放进可被 ingestion/tool/trace 字符串化的异常，再要求下游猜测和脱敏。

这些修复不改变 opaque identity、业务 filing 分类、R06 四 phase、fresh schema 或
S1/S2/S3 切片边界，也不引入通用 LLM-safe normalization、兼容分支或 authorization
framework。

## Accepted finding ledger

### R07-S1-CR-F01 — 接受：destructive cleanup 缺少 complete preflight，stale cleanup 静默跳过损坏 owner evidence

- 来源：AgentMiMo `R07-S1-MIMO-F02`，加上 Controller 对同一 destructive owner 的完整调用链
  复核。
- 裁决：`ACCEPTED / FIX REQUIRED`。
- 直接证据：
  - `_clear_filing_documents_impl` 与 `_clear_processed_documents_impl` 目前边遍历边
    `rmtree/unlink`，没有在第一次 mutation 前验证所有 identity directory、symlink、
    预期 control files 与 rejected-artifact 子树；遇到后续损坏时会产生 partial deletion；
  - `_cleanup_stale_filing_documents_impl` 对缺失 source meta 或 `_read_json_object` 的
    `ValueError/OSError` 直接 `continue`，与 accepted plan §5.1、§7.1、§11 的
    descriptor/meta/manifest corruption fail-closed 约束冲突。
- owner-boundary 修复：
  1. filing/processed clear 在任何 unlink/rmtree 前完成 whole-candidate preflight；拒绝 symlink、
     非法 entry、缺失/损坏/namespace 或 external identity 不匹配的 descriptor/meta，且
     `.rejections` 作为唯一已知 container 单独验证其全部 rejected identity entries；
  2. 只有全部 preflight 成功才开始删除，因此验证失败保持 transaction staging tree 未被本操作
     部分清理；
  3. stale cleanup 对候选 filing 的缺失/损坏/mismatch meta fail closed，不再静默跳过；
  4. 保留 manifest、download-rejection registry 与 `.rejections` 的既有业务角色，不把 control
     file 当 identity directory，也不改变 atomic staging/swap/rollback owner。
- 必须验证：filing、processed、nested rejected 三类坏 descriptor/meta/symlink/unexpected-entry
  场景都在第一项物理删除前失败；stale meta missing/corrupt 失败；valid clear/stale 行为和
  R06 rollback/commit 不回退。

### R07-S1-CR-F02 — 接受：`begin_batch` cleanup failure 可掩盖初始化 primary failure

- 来源：AgentDS `R07-S1-DS-F04`。
- 裁决：`ACCEPTED / FIX REQUIRED`。
- 直接证据：`_FsStorageInfra.begin_batch` 的初始化 `except Exception` 先删除 staging，随后平铺
  调用 `_release_lock_token(lock_token)`；release 抛错时，调用方只见 release error，原始 journal、
  descriptor、copy 或 containment failure 被替换。当前模块 `_close_active_batch` 已有同 owner 的
  primary-error 保留模式。
- owner-boundary 修复：初始化失败始终保持原始异常为主异常；staging cleanup 和 writer-lock
  release failure 只作为附加诊断，不得改变主异常 identity。不得吞掉 cleanup failure，也不得
  添加通用 exception sanitizer 或下游补偿。
- 必须验证：至少覆盖 descriptor/copy/journal 初始化失败与 release failure 同时发生；断言主异常
  不变且 release failure 可诊断，active-batch maps 未发布，staging 尽力清理。

### R07-S1-CR-F03 — 接受：raw filesystem `OSError` 泄漏 workspace path 与 private storage key

- 来源：Controller 独立复核；两路 review 均未报告。
- 裁决：`ACCEPTED / FIX REQUIRED`。
- 直接证据：Controller 在真实临时 workspace 创建有效 opaque ticker，公司 meta 写入后令
  `meta.json` 不可读，再调用 public `get_company_meta`。实际 `PermissionError.__str__` 同时包含
  absolute workspace path 和由 storage 派生的 private directory key。`_read_json` 仅处理
  `JSONDecodeError`；`Path.read_text/read_bytes/iterdir/open` 等原生 `OSError` 也可携带 locator。
  `scan_company_meta_inventory` 还会把 `str(exc)` 直接写入 typed inventory detail；
  `ingestion_runtime` 的 terminal error projection 会字符串化上游异常，因此泄漏可以离开
  storage boundary。
- owner-boundary 修复：
  1. 在本 S1 touched storage owner 内把 raw filesystem failure 投影成 path-free storage error；
     保留有意义的原生异常类别/`errno` 和 exception chaining，但 message、args、typed detail 不得
     含 workspace absolute path、internal key、staging/backup/lock locator；
  2. 覆盖 JSON/descriptor enumeration、company/source/processed/rejected/blob read 与 batch
     initialization/maintenance 中可跨 public repository boundary 的 raw filesystem operations；
  3. 已有显式 business-readable `FileNotFoundError`/`ValueError` contract 保持业务 ticker、
     document id、safe filename 语义，不改为 digest/key；
  4. 不在 ingestion、tool、trace、Engine 或测试 fixture 添加字段名 blacklist、regex sanitizer、
     fallback 或另一套 LLM-safe normalization。locator 的 producer 必须在 storage 边界关闭泄漏。
- 必须验证：用真实 filesystem permission/I/O failure 黑盒覆盖至少 company、source/processed、
  blob/rejected/list/batch 中的代表路径；对 `str(exc)`、`exc.args` 与 typed inventory detail 断言
  无 workspace root、无实际 private key/backup/staging/lock locator，同时异常类别/`errno`、
  cause 与正常 missing/corruption contract 保持。

## Rejected-with-reason ledger

### AgentMiMo

- `R07-S1-MIMO-F01`：拒绝。Accepted plan §3.2 maintenance inventory、§7.1 step 4 与
  `R07-PF-05` 明确要求 descriptor 先恢复 exact external id，随后应用既有 SEC `fil_` 业务分类。
  当前 SEC/CN producer 也显式产生该业务 id；storage mapping opaque 不等于删除 maintenance
  owner 的业务分类。
- `R07-S1-MIMO-F03`：拒绝。Accepted exact contract 是“非空且可 UTF-8 持久化”，并明确不
  `strip`、不 normalization。固定 namespace 与 exact identity 的长度编码/hash 输入不存在
  `NUL` 碰撞歧义；新增 whitespace/control-character blacklist 会改变已裁决业务 identity。
- `R07-S1-MIMO-F04`：拒绝。S1 exact test allowlist 只有四个现有文件，新增第五个 test file
  未获授权；核心 helper 的 owner contract 已由真实 repository 黑盒覆盖，Controller 独立行覆盖率
  为 `82.52%`，达到逐文件目标。CR-F01..03 的新增测试必须继续放入既有四文件。
- `R07-S1-MIMO-F05`：拒绝为 evidence false。当前 `_fs_storage_infra.py` 不导入
  `SourceDocumentRevision`，scoped Ruff 的 `F401` 为 0。

### AgentDS

- `R07-S1-DS-F01`：拒绝。Accepted plan 要求 target/backup recovery evidence 交叉验证，且
  corrupt/missing/mismatch fail closed。损坏 backup 表示 unresolved recovery evidence；静默忽略
  会把 ambiguous old/new state 当成健康 published target。
- `R07-S1-DS-F02`：拒绝。Per-artifact skip-warn 是旧 fallback；fresh descriptor schema 明确
  要求 enumeration corruption fail closed。恢复 skip 会隐藏损坏并产生 incomplete inventory。
- `R07-S1-DS-F03`：拒绝。`_processed_dir_for_write` 在存在性判断前保证 descriptor directory，
  若以 directory existence 判断，create 会恒定失败。processed meta 是业务 record existence owner；
  descriptor-only directory 只是 pre-payload identity。删除时缺失 meta 应保留可诊断损坏证据，
  不能把它当正常 orphan 静默清除。
- `R07-S1-DS-F05`：拒绝。Generic `_get_document_meta_unguarded` 可合法读取没有 ticker 的
  processed meta，因此是 optional guard；source-specific `_get_source_meta_unguarded` 的 source
  meta contract 必须有 exact ticker/source kind。两处服务不同 typed owner。
- `R07-S1-DS-F06`：拒绝。当前所有 production same-ticker mutation 由 writer capability 序列化；
  同一 batch 并发创建同一 identity 不是合法调用 contract。单独改 `exist_ok=True` 不能安全解决
  descriptor publication race，反而会接受未验证竞争者。没有当前可达 correctness failure。
- `R07-S1-DS-F07`：拒绝为当前 finding。不存在目录时返回 deterministic missing locator 是随后
  `FileNotFoundError` contract 的必要输入；无 workspace-root 写权限的调用方不能制造竞态，有
  本地 root 写权限的攻击者可竞态所有 filesystem validation。这是既有 local trust boundary，
  不是 S1 mapping 绕过。CR-F03 仍要求任何最终异常不泄漏 locator。
- `R07-S1-DS-F08`：拒绝。SEC producer contract 本来就把 external document id 定义为
  `fil_` + accession、internal id 定义为 accession。fixture 的 `removeprefix` 编码该业务 producer
  关系，不是从 storage private path/key 推断 external identity。

## Fix scope 与硬约束

AgentCodex 只可修改当前 S1 production allowlist 中直接受 accepted findings 影响的文件：

```text
dayu/fins/storage/_fs_identity.py
dayu/fins/storage/_fs_storage_utils.py
dayu/fins/storage/_fs_storage_infra.py
dayu/fins/storage/_fs_blob_core.py
dayu/fins/storage/_fs_company_meta_core.py
dayu/fins/storage/_fs_maintenance_core.py
dayu/fins/storage/_fs_processed_core.py
dayu/fins/storage/_fs_source_document_core.py
```

若 `dayu/fins/domain/document_models.py` 无 owner contract 变更则不得格式化或顺带修改。测试只可修改：

```text
tests/fins/test_fins_storage_provider.py
tests/fins/test_fins_storage_atomicity.py
tests/fins/test_fins_ingestion_runtime.py
tests/fins/test_sec_pipeline_download.py
```

AgentCodex 另写唯一 fix artifact：
`docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-fix-codex.md`。不得修改 plan、design、
README、control、旧 review/validation artifact；不得进入 S2/S3、R08+、Issue 142/151/175/177/178、
统一 authorization、commit、push 或 PR。

验证必须包括 accepted finding 精确节点、四个 exact full test files、九个 S1 production file
逐文件行覆盖率 `>=80%`、full pyright `0 errors`、changed-file scoped Ruff `0`、full Ruff baseline
不超过既有 `152` 且 rule fingerprint 不扩散、`git diff --check`、scope/source/propagation/private
locator scans，以及真实 permission/I/O failure smoke。任何 raw locator 仍可从 public storage
异常或 typed detail 观察到都视为 fix 未完成。

## 下一 gate

进入 AgentCodex `R07-S1 code-review fix`。Controller 独立验证通过后，AgentMiMo / AgentDS
必须并发完整 re-review 累计 S1 tree，明确关闭 `R07-S1-CR-F01..03` 并检查 rejected alternatives
未被误实现。S1 不创建 accepted commit；只有两路 re-review 与 Controller 最终裁决均通过，才能
进入 R07-S2。
