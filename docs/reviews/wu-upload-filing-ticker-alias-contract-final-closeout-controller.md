# upload-filing-ticker-alias-contract Final Closeout（Controller）

## Metadata

- work unit：`upload-filing-ticker-alias-contract`；
- branch：`codex/upload-filing-oracle`；
- base：`main@256786b255021ee429a20f22aad726b1ad33916c`；
- accepted plan commit：`5508d0445bd1d649fee54f4ec3d65f99e2484493`；
- accepted S1 commit：`c5446b77`；
- accepted S2 commit：`2b11cb21`；
- accepted aggregate deepreview commit：`c297ea501498be37f38cc037e9ec7769c978a2c0`；
- decision：`final-closeout-pass-local-no-pr`；
- blocking questions：None。

## Gate closure

- preflight：无 merge/rebase/cherry-pick；初始工作树 clean；`main == github/main == 256786b2`；
  当前 feature branch 包含 main、非 protected trunk；
- goal confirmation：用户确认目标、动机、十项业务 contract、非目标与 evidence 边界；
- accepted plan：`5508d044`；
- accepted S1：`c5446b77`；
- accepted S2：`2b11cb21`；
- aggregate deepreview：
  - `docs/reviews/code-review-20260815-023308.md`：PASS；
  - `docs/reviews/code-review-20260815-023958.md`：发现两项中、两项低 finding；
- aggregate fix：
  `docs/reviews/wu-upload-filing-ticker-alias-contract-s2-fix-codex.md` §9；
- aggregate re-review：
  - `docs/reviews/code-review-20260815-032921.md`：PASS；
  - `docs/reviews/code-review-20260815-033322.md`：代码 PASS，并发现一个 README low finding；
- README narrow fix/re-review：low finding 已修复，两路 reviewer 均 PASS；
- controller adjudication：
  `docs/reviews/wu-upload-filing-ticker-alias-contract-aggregate-deepreview-controller-adjudication.md`；
- accepted aggregate deepreview：`c297ea50`。

## Delivered outcome

- `CompanyTickerIdentity` 成为 canonical ticker、用户声明 alias、跨市场 alias 与 resolver alias 的
  唯一合并 contract；公共 ticker normalizer 唯一拥有 US/CN/HK grammar、长度边界与语法变体。
- `--ticker` CSV 第一项稳定解释为 canonical corpus ticker，后续项稳定解释为用户明确声明的同公司
  查询 alias；系统不联网核验、不猜测、不纠正现实公司归属，因此 `DELTA,MSFT` 被接受。
- canonical-equivalent 与重复 aliases 在 owner boundary 稳定去重；不同且已接受的 aliases 不被丢弃。
- `CompanyMeta`、durable state、resolver、CLI/tool/pipeline、storage unique index 与 read route 都从
  同一 identity contract 派生；重复 grammar、read fallback、SEC/Docling loose normalizer 与兼容 seam
  已删除。
- storage 在首次 published swap 前构建 authoritative unique identity index；同一 normalized alias 被
  多个 corpus 声明时原子拒绝，不依赖入口、扫描顺序或偶然覆盖。
- canonical ticker 与任一 accepted alias 调用 `list_documents` 均路由到同一 canonical corpus，返回
  同一文档集合。
- descriptor、CompanyMeta 与 target structure corruption 由 storage owner 统一 typed 分类；上传 tool、
  CLI、filing prepare 与 material terminal 只投影 bounded、path-free、可行动错误。
- material 与 filing 共用 ticker/alias 启动前准入；zero-mutation SEC/CN publication rollback，避免
  无意义 full-tree swap。
- 根 README 已同步两条上传命令的 ticker CSV、grammar、100 个 alias 上限与 usage error 语义；
  `dayu/fins/README.md` 已在 S2 说明 identity/storage owner 与 typed failure。

## Final validation evidence

- Controller 最终 relevant suite：`1753 passed, 1 skipped, 3 warnings`；warnings 均来自 `edgar`
  dependency deprecation；
- identity/storage atomicity focused：`190 passed`；
- 所有修改生产文件 branch coverage：`81%`–`100%`；
- Controller 最终全量 pyright：`0 errors, 0 warnings, 0 informations`；
- Ruff format/check、residue scan、`git diff --check`：通过；
- aggregate 双路 re-review：PASS / PASS；README 窄复核：PASS / PASS；
- accepted deepreview commit 后工作树 clean。

## Residual risks

1. 按用户明确范围，本 work unit 未执行 UF-PF05 真实 CLI evidence、未刷新 oracle/scenario registry、
   未修改冻结 evidence；这些动作不属于本次正确性验收。
2. 旧 CompanyMeta schema 不做兼容读取，遵守 fresh schema 起库约束。
3. workspace identity route 当前扫描 published corpora；没有本次引入的性能退化证据，未来只有在有
   实测瓶颈时才应另立 cache/index work unit。
4. ACL/NFS 真实跨平台行为未外部验证；owner 的 errno 分型与 fail-closed 行为已有注入测试。
5. resolver version 常量不一致、material company-name admission 与既有 project-wide 6 个 baseline
   failures 均不属于本 work unit；用户明确要求不处理其它 finding。

所有 residual risk 均已分类，不阻塞本地 closeout。

## External action boundary

用户明确要求“在当前 git 分支上提交代码，无需创建 PR”。因此本次：

- 已创建本地 accepted plan、accepted slices 与 accepted aggregate deepreview commits；
- 未 push；
- 未创建或修改 PR；
- 未执行 PR review、request reviewer、approve、merge、外部 comment、部署或发布；
- 未修改 issue、oracle/scenario registry 或冻结 evidence。

该用户 override 优先于 Gateflow 默认 draft PR 链；本 closeout 不声称存在 `draft-PR-pass`。

## Next entry point

work unit 已在当前分支本地完成。后续若用户选择发布，可自行 push/创建 PR；若继续处理 residual 或其它
finding，应从新的独立 work unit preflight 与 goal confirmation 开始，不能在本 contract fix 中扩 scope。

## Final decision

`final-closeout-pass-local-no-pr`。`upload_filing` 与 `list_documents` 的 ticker alias contract 漂移已在
唯一 Company Identity / CompanyMeta owner 边界闭环；代码、测试、必要文档与 Gateflow artifacts 已完成，
无未裁决 blocker。
