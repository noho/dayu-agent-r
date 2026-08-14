# upload-filing-ticker-alias-contract plan fix

## Gate metadata

| 字段 | 值 |
| --- | --- |
| Gate | `plan fix` |
| Work unit | `upload-filing-ticker-alias-contract` |
| Fixed plan | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-codex.md` |
| Controller adjudication | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-review-controller-adjudication.md` |
| Reviewer artifacts | `docs/reviews/plan-review-20260814-215912.md`; `docs/reviews/plan-review-20260814-220204.md` |
| Completion status | `plan fix complete` |
| Current gate / next entry point | `plan re-review` |
| Artifact path | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-fix-codex.md` |

## Scope and evidence

本fix完整读取controller adjudication、两份timestamp plan review artifact与当前plan，并以review引用的直接代码事实复核：prevalidation在writer lock前生成`company_meta_decision`，SEC/CN在`begin_batch`后stage旧决策，`begin_batch`才持有same-ticker writer；现有storage commit直接swap staged tree；read runtime仍有normalize/upper fallback；inventory能产生`missing_meta`/`invalid_meta`；6-K repair直接消费`CompanyMeta.ticker`。

本轮只修改plan并新增本artifact，不修改生产代码、测试或README，不执行implementation，也不创建commit。该“本轮不提交”不改变修订后plan的Gateflow contract：plan re-review accepted后在当前分支创建protected local commit并自动继续S1/S2；用户只排除PR/push。

## Finding fixes

### A1 — 已修复：同canonical prevalidation snapshot lost-update

- 直接修改：新增唯一domain owner `dayu/fins/domain/company_meta_contract.py`，冻结`CompanyMetaNonIdentitySnapshot`、`CompanyMetaCommitIntent`、merge mode与`merge_company_meta_for_commit` public contract；prevalidation最终只产生declared alias/explicit refresh intent和typed optimistic precondition，不产生最终CompanyMeta。
- Authoritative时点：same-canonical writer已由`begin_batch`持有；commit先持recovery guard并完成sweep，再持workspace identity guard，随后在incoming publication guard下读取current published CompanyMeta。
- Storage边界：`_ActiveBatchState`只保存transaction-local intent；storage向pure domain helper机械传入authoritative current、intent与commit时点，再写final staged meta，不在storage自创resolver/field/alias merge语义。
- Final rule：current aliases在前、intent aliases在后稳定union；`preserve_published`永远保留current非identity字段；`refresh_if_stale`只在current missing且expected absent、或current exact nonidentity snapshot未变化时应用显式refresh；current已变fresh则保留current，changed-but-still-stale则抛`CompanyMetaConcurrentUpdateError`，避免覆盖更晚durable facts；无真实mutation保留`updated_at`。
- Validation：新增`spawn`跨进程barrier test，固定P1 fresh-alias prevalidation暂停、P2提交alias/fresh facts、P1继续，要求aliases全保留且P2 durable facts不被P1旧snapshot覆盖；另测changed-but-still-stale时P1 typed fail-closed且P2 tree hash不变，禁止silent loss/stale overwrite。

### A2 — 已修复：6-K primary repair漏项

- 直接修改：把`dayu/fins/pipelines/sec_6k_primary_document_repair.py`加入affected files与S1 allowed files，限定为`entry.company_meta.ticker_identity.canonical_ticker`机械迁移。
- Validation：纳入`tests/fins/test_sec_pipeline_download.py`既有repair regression、CompanyMeta residue scan与全量pyright；不发明新的repair业务行为。

### A3 — 已修复：S1 route中间契约

- 直接修改：S1保留`resolve_existing_ticker(list[str])` public签名、direct canonical probe、`dict[str, list[str]]` index与duplicate-owner late `ValueError`。
- 唯一输入：`_resolve_existing_ticker_by_company_alias`/`_build_company_alias_index_from_meta`只消费`CompanyMeta.ticker_identity.lookup_tickers()`，S1即删除旧storage grammar helpers。
- 切换点：plan列出S1 residue临时允许项；S2一次删除旧public/internal route与两个list-index helpers，切换`resolve_company_ticker(str)`及唯一`_build_unique_company_identity_index -> dict[str, str]`。

### A4 — 已修复：incoming conflict与published corruption分型

- 直接修改：`CompanyTickerAliasConflictError`只服务valid published owner与incoming commit intent的冲突；新增`CompanyTickerIdentityCorruptionError`及closed corruption kinds服务missing/invalid/mismatch/duplicate durable identity。
- Read projection：新增`workspace_identity_corrupted`与`storage_unavailable` ErrorCode；read runtime分别把typed corruption与identity/publication guard failure投影为path-free、有界、可行动`FinsReadBusinessError`，tool outcome复用现有business-error owner，不落入`execution_error`。
- Upload projection：incoming conflict仍唯一是`storage/ticker_alias_conflict`；published corruption映射既有`storage/storage_io`及修复workspace metadata提示，不能归责incoming alias。
- Validation：补durable duplicate/invalid、identity guard acquire failure的read owner与tool outcome tests。

### A5 — 已修复：company-name-required reason收窄

- 直接修改：新增并只捕获`UploadCompanyNameRequiredError`；它只在missing/stale meta需要explicit refresh且缺company name时产生。
- Validation：invalid alias稳定投影`INVALID_TICKER_ALIAS`；builder/corruption/lock error不得被误报为`COMPANY_NAME_REQUIRED`，不依赖校验偶然顺序兜底。

### A6 — 已修复：invalid published meta commit fail closed

- 直接修改：commit identity scan只枚举`portfolio/`实际published corpus；任何missing/invalid CompanyMeta、descriptor mismatch或durable duplicate均在backup/swap前抛typed corruption。backup/lock-only locator不视为published corpus，避免把新增storage locator误判为missing meta。
- Validation：分别注入missing meta、invalid JSON/schema、identity mismatch，断言incoming与corrupt corpus tree SHA不变、首次replace调用为零；read/commit对同一corruption同为fail closed。

### A7 — 已修复：recovery-read与guard failure tests

- 直接修改：recovery对每个recovered ticker tree在recovery guard + nonblocking writer后、publication mutation前统一取得identity guard；不依赖不可恢复的transaction-local fact。
- Validation：barrier固定recovery已持identity guard但尚未physical restore，alias read必须等待并只观察恢复后的完整route；identity guard acquire failure时第一次restore/delete/swap为零且evidence保留；release failure验证恢复结果、最早primary与secondary note规则。

### A8 — 已修复：S1/S2完成语义

- 直接修改：S1被定义为reviewed local checkpoint，明确仍保留late conflict与A1窗口，不可部署、不可close、不可进入final closeout；accepted S1 commit后必须立即继续S2。
- Gateflow语义：删除“用户要求plan complete后停止/不提交”的错误表述；恢复plan re-review、accepted plan local commit与后续local gate自动推进，只排除PR/push。

## Rejected reasons preserved

- R1 `rejected-with-reason`：未采用“存在`meta.json`才给orphan recovery取identity guard”。batch staging会复制旧tree，文件存在不拥有mutation语义；recovery对所有recovered ticker trees统一guard。潜在contention只有实测后才能进入独立性能WU。
- R2 `rejected-with-reason`：`_STORAGE_FAILURE_CODES`仍明确是S2新增contract，未把尚未实现的新storage code误列为当前遗漏；mapper unit/e2e validation保持在plan内。

## Validation and docs decision

- Plan status已更新为`plan fix complete`，next entry point为`plan re-review`。
- Affected/allowed files补齐domain merge owner、read ErrorCode owner与6-K repair consumer。
- Test matrix补齐same-canonical cross-process lost-update、invalid published meta、durable corruption read projection、recovery-read barrier及guard acquire/release failure。
- S1/S2 residue规则、coverage逐文件`>=80%`、全量pyright与README触发决策均保留并精确到对应slice。
- 本fix不修改README；implementation触及Fins public/CLI语义时仍按plan更新`dayu/fins/README.md`与根`README.md`，不更新其它README。

## Residual risks

| Risk / uncovered area | Classification | Owner / destination |
| --- | --- | --- |
| 旧workspace歧义alias/旧CompanyMeta schema | `assigned to later work unit` | fresh schema边界；如需升级另立migration WU |
| UF-PF05真实CLI evidence | `assigned to later work unit` | 用户明确排除 |
| oracle/scenario registry、冻结evidence、其它finding | `assigned to later work unit` | 用户明确排除 |
| CompanyMeta workspace scan成本 | `assigned to later work unit` | 仅在真实profile超标后另立性能WU，不新增durable index/cache |
| recovery对所有orphan tree取得identity guard的等待 | `assigned to later work unit` | R1 correctness优先；只有实测contention后优化且不得用文件存在猜mutation |

没有unclassified residual risk，没有blocking open question。

## Completion status

Plan fix完成，A1–A8均为`已修复`，R1/R2的rejected reasons保持有效。next entry point为`plan re-review`；本轮未进入implementation、未创建commit、未执行PR/push。
