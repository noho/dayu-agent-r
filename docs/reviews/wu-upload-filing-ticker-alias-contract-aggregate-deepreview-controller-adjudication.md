# upload-filing-ticker-alias-contract Aggregate Deepreview Controller Adjudication

## Scope

- Work unit：`upload-filing-ticker-alias-contract`。
- design sources：`docs/host/design.md`、`docs/engine/design.md`。
- accepted plan：`5508d0445bd1d649fee54f4ec3d65f99e2484493`。
- accepted slices：S1 `c5446b77`、S2 `2b11cb21`。
- aggregate review artifacts：
  - `docs/reviews/code-review-20260815-023308.md`；
  - `docs/reviews/code-review-20260815-023958.md`。
- aggregate fix report：
  `docs/reviews/wu-upload-filing-ticker-alias-contract-s2-fix-codex.md` §9。
- aggregate re-review artifacts：
  - `docs/reviews/code-review-20260815-032921.md`；
  - `docs/reviews/code-review-20260815-033322.md`。

## First-principles decision

本 work unit 的动机成立。直接数据流证据表明，修复前 `--ticker` CSV、resolver alias、
`CompanyMeta`、storage 查询路由与 `list_documents` 分别拥有部分 grammar、归一化或 fallback，
使同一 alias 事实可能因入口不同而产生不同 durable/query 结果。正确边界不是在
`list_documents` 增加兼容推断，而是让 ticker grammar 只属于公共 normalizer，让 canonical 与
accepted aliases 的合并只属于 `CompanyTickerIdentity`，让 durable uniqueness 与 route 只属于
storage，并让所有入口消费这些 owner contract。

最终实现保持该边界，没有新增联网核验、现实公司归属推断、兼容 shim、alias cache 或旧 schema
迁移。

## Aggregate finding decisions

### AGG-F1：durable corruption 在上传入口投影漂移

- 原始 severity：中；
- decision：`accepted`；
- final status：`已修复`。

`CompanyMeta`、identity descriptor、published target symlink/non-regular 等 durable corruption
现由 storage owner 统一产生 closed `CompanyTickerIdentityCorruptionError`。真实 filing
prepare/start/tool/CLI 与 SEC material terminal 测试证明该分支可达，错误均 bounded、path-free，
不再落为 `invalid_argument`、`unexpected_runtime`，也不泄露 `CompanyMeta` 或 schema 字段原文。

### AGG-F2：material 准入不对称及 SEC/Docling loose ticker fallback

- 原始 severity：中；
- decision：`accepted`；
- final status：`已修复`。

filing 与 material 现共用唯一 upload ticker identity admission；grammar、normalization 与 dedupe
继续只委托公共 ticker owner。`SecDownloader.normalize_ticker`、Docling 私有 normalizer、
browse-EDGAR 的 ticker `strip().upper()` fallback 与相应 protocol/stub seam 已删除。material 的非法
ticker、非法 alias 与超过 100 个 aliases 都在 observation/job 创建前投影 typed usage failure。

### AGG-F3：zero-mutation download 仍执行 full-tree swap

- 原始 severity：低；
- decision：`accepted`，因为现有 `CompanyMetaCommitIntent | None` 已提供明确 mutation signal，
  可在 caller 边界最小闭环；
- final status：`已修复`。

SEC/CN 重复 publication 在 intent 为 `None` 时 rollback，不再无意义 commit/swap。owner-level 测试
断言首次 publication 只 commit、重复 publication 只 rollback，且 published `meta.json` bytes 不变；
document/registry mutation 仍由各自 batch 管理。

### AGG-F4：staging CompanyMeta locator 死路径

- 原始 severity：低；
- decision：`accepted`；
- final status：`已修复`。

未被调用的 `_FsStorageInfra._company_meta_path(...)` 已删除；staging CompanyMeta 的真实写入路径
只保留在 identity commit owner 内。

### AGG-RR-F1：根 README 未同步 material 启动前 usage 校验

- 原始 severity：低；
- decision：`accepted`；
- final status：`已修复`。

该行为改变 CLI 用户的参数校验与排障预期，命中根 README 更新触发。根 README 现自足说明两条
单份上传命令的 ticker CSV 语义、支持 grammar、100 个 alias 上限及非法输入退出 `2`；没有暴露
内部 contract/type 名。两路 reviewer 的窄文档复核均为 PASS。

## Contract closure

1. CSV 第一项为 canonical corpus ticker，后续项为用户声明的同公司查询 alias；系统不联网核验、
   不猜测现实公司归属。
2. US/CN/HK、跨市场 alias、语法变体与 `V.BA` 类 alias 共用唯一 grammar；长度边界一致。
3. canonical-equivalent 与重复 alias 在 `CompanyTickerIdentity` owner 稳定去重，不丢弃不同 accepted
   alias。
4. `CompanyMeta` durable state、storage unique index、resolver、CLI/tool/pipeline 与 read route 均从
   同一 identity contract 派生。
5. 同一 normalized alias 的多 canonical 冲突在首次 published swap 前 typed、原子拒绝；并发与
   recovery 路径保持确定性。
6. canonical 或任一 accepted alias 调用 `list_documents` 均路由到同一 canonical corpus，并返回同一
   文档集合。
7. duplicate grammar/helper、read-time guessing、downloader fallback 与兼容 seam 的 residue scan 为零。
8. owner-level、真实入口、冲突、并发、recovery、zero-mutation 与 end-to-end route 测试均已覆盖。

## Validation evidence

- final relevant branch suite：`1753 passed, 1 skipped`；
- identity/storage atomicity focused：`190 passed`；
- 修改生产文件逐文件 branch coverage：`81%`–`100%`，全部达到 `>=80%`；
- 全量 `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`；
- 25 个修改 Python 文件的 Ruff check/format check：通过；
- residue scan 与 `git diff --check`：通过；
- aggregate re-review：MiMo PASS、DS PASS，无 blocker；
- README narrow re-review：两路 PASS。

## Residual risks and exclusions

- 按用户明确范围，不执行 UF-PF05 真实 CLI evidence，不刷新 oracle/scenario registry，不修改冻结
  evidence；这些不是本次 closeout 的缺失证据。
- 不兼容读取旧 CompanyMeta schema；本任务按 fresh schema 起库约束实现。
- workspace identity 查询仍需扫描 published corpora；当前没有性能退化证据，不在本次预建 cache。
- ACL/NFS 的真实跨平台文件系统行为未外部验证；errno 注入已覆盖 owner 分型。
- resolver version 字面量不一致与 material company-name admission 属既有、用户明确排除的其它 finding，
  由后续独立 Fins work unit 负责，本次未修改。
- 早期 project-wide 验证仍可复现 6 个与本 work unit 无直接数据流关系的 baseline failure（workspace
  init、`upload_filings_from` containment 文案、service import boundary）；本次 relevant suite 全绿，
  未为保住基线失败引入兼容代码。

所有 residual risk 已分类，无本 work unit blocker 或未裁决 finding。

## Controller decision

`aggregate-deepreview-pass`。全部 accepted findings 已修复并经双路 re-review；代码、测试、必要 README
与 Gateflow artifacts 可进入 accepted deepreview commit。

用户明确要求不创建 PR，因此 Gateflow 的 draft PR / PR review 外部链路不进入；这是一项用户 scope
override，不授权 push、创建 PR、request reviewer、approve、merge 或其它外部状态变更。accepted
deepreview commit 后的下一入口为本地 final closeout。
