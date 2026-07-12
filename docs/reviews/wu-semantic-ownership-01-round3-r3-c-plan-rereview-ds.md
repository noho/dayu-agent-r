# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Plan Re-Review

## Artifact Metadata

- Review type: adversarial plan re-review (post plan fix verification)
- Target: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-fix-codex.md`
- Original reviews:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-controller-adjudication.md`
- Reviewer: DS (planreview skill)
- Timestamp: 2026-07-12T23:32:46+08:00
- Risk profile: production-high
- Status: pass

## Review Scope

验证 controller adjudication 接受的 10 个 plan fix findings (R3-C-PF-01 到 R3-C-PF-10) 是否在修订后的 plan 中正确落地，以及 tool-security 四项是否保持 deferred 且未泄漏到任何 implementation slice。

本 re-review 不寻找新的 speculative architecture advice。仅当 plan fix 引入了真实的 implementation blocker 时才报告 material evidence-backed new findings。

## Verification Method

对每个 accepted finding：
1. 确认 PF marker 在 plan 中存在
2. 验证 fix 内容与 controller adjudication 的 required plan fix 一致
3. 检查 plan 中对应 assertion/validation 是否覆盖了原 finding 的反例/失败场景

## Finding Verification

### R3-C-PF-01 — S2 caller-batch contract for `commit_cn_filing_source_document`

- **Controller required fix**: 明确该函数只能在 caller-owned active document batch 内执行，不得创建第二个 commit owner；验证必须证明全过程使用同一个 active token。
- **Plan fix location**: 行 191（`R3-C-PF-01` marker）
- **Plan text**: "`commit_cn_filing_source_document()` 的 contract固定为'只在 caller-owned active document batch内 stage final source meta与processed reprocess marker'；它不得开启、提交或回滚第二个batch。fast-skip与normal-convert两个 call site都必须处在同一 caller batch，验证必须证明 reset -> source acknowledgement -> PDF/Docling blob -> final meta -> processed marker全过程使用同一个active token。"
- **Assertion coverage**: 行 345 要求 "fake/spy shared repository记录active token identity，证明全过程全部发生在同一个caller-owned active batch，且只有caller末尾调用一次commit。"
- **Verdict**: ✅ **Fixed** — 明确限定了函数的 contract、两个 call site 的约束，以及验证方法。

### R3-C-PF-02 — S2 token lifecycle and commit-failure rollback rule

- **Controller required fix**: caller 只回滚 commit 前的 operation exception；`commit_batch()` 调用后 token 归 storage owner，commit failure 只传播不做 invalid-token rollback。
- **Plan fix location**: 行 189（`R3-C-PF-02` marker）
- **Plan text**: "caller准备调用 `commit_batch()` 时即把生命周期所有权交给 storage；从调用开始，无论 success或failure，storage都负责消费 token与同步rollback/recovery，caller只原样传播 storage exception，绝不再调用 `rollback_batch()`。"
- **Assertion coverage**: 行 347 要求 "commit success/failure测试证明从`commit_batch()`调用开始token归storage owner；commit failure不会触发invalid-token二次rollback、不会返回uploaded/downloaded成功，并原样传播storage primary exception。"
- **Verdict**: ✅ **Fixed** — 明确 token 所有权交接点、caller 禁止二次 rollback，与原始 MiMo finding 001 的反例场景完全对应。

### R3-C-PF-03 — S2 active-batch exception/cancellation pattern

- **Controller required fix**: 指定 batch scope 的 try/finally 模式、commit_started 所有权切换、operation/cancellation rollback、双重错误 chain，以及 active token 期间零 yield/await。
- **Plan fix location**: 行 190（`R3-C-PF-03` marker）
- **Plan text**: "每个 caller采用显式 active-batch `try/finally` 结构：在进入同步 mutation段前保存 active token与 `commit_started=False`；operation抛出 `Exception`或`BaseException`子类 cancellation时记录 primary error；`finally`仅在 `commit_started=False` 且token仍由caller拥有时执行一次rollback，并按'primary保留、rollback为`__cause__`'传播双重错误；紧邻调用 `commit_batch()` 前把 `commit_started=True`，此后finally不得rollback。active token存在期间禁止任何 `yield`/`await`；取消测试通过同步 cancellation checker/注入点在mutation段内抛 `asyncio.CancelledError`，而不是靠增加batch内await制造窗口。"
- **Assertion coverage**: 行 346 要求 "operation exception与同步抛出的`asyncio.CancelledError`都在active-batch `finally`触发一次rollback；rollback自身失败不覆盖原业务异常，通过primary exception的note/`__cause__`保留两者；mutation段内无yield/await。"
- **Verdict**: ✅ **Fixed** — 完整的 try/finally 模式、所有权切换标志、双重错误 chain 和同步 CancelledError 注入策略，覆盖了 MiMo finding 002 的 cancellation-during-batch 反例。

### R3-C-PF-04 — S1 `SWAPPED_TARGET` recovery semantic reversal

- **Controller required fix**: 显式声明 recovery 对 `SWAPPED_TARGET` 在 `COMMITTED` 前删除 new target 并恢复 backup，与当前行为相反；加入 swap 与 `COMMITTED` 之间的 crash state 测试。
- **Plan fix location**: 行 161（`R3-C-PF-04` marker）
- **Plan text**: "特别地，`SWAPPED_TARGET` 且尚无 `COMMITTED` 时必须先删除本次 new target，再把 backup恢复为 target；这与 `dayu/fins/storage/_fs_storage_infra.py:725-728` 当前'保留 new target、删除 backup'的行为相反，是 S1 必须落地并测试的行为变更，而非注释整理。"
- **Assertion coverage**: 行 255 要求 "必须包含'swap已完成但`COMMITTED`尚未写'的`SWAPPED_TARGET` case，断言new target删除、old backup恢复；若pre-state不存在则new target删除且target保持不存在。" 行 265 再次用真实目录状态证明语义反转。
- **Verdict**: ✅ **Fixed** — 显式声明行为反转、引用当前代码证据、要求 crash-between-swap-and-COMMITTED 测试，完全覆盖 MiMo finding 003 和 DS finding 5（旧格式 journal 迁移被 controller 拒绝为 required fix，但新的 recovery 语义已包含正确行为）。

### R3-C-PF-05 — S1 dual commit/rollback error reporting

- **Controller required fix**: 指定 commit failure + rollback failure 的 Python 异常传播形状，包括哪个是 primary、rollback error 在哪、journal/backup 证据保留，测试必须断言两者可检查。
- **Plan fix location**: 行 162（`R3-C-PF-05` marker）
- **Plan text**: "传播形状固定为：原 commit exception仍是 caller捕获到的 primary exception；对它调用 `add_note()` 标明'rollback失败且recovery evidence已保留'，并以 `raise commit_error from rollback_error` 传播，使 rollback exception可从 primary的 `__cause__` 检查。不得只 log rollback error、不得让 rollback error替换 primary；journal、backup及任何无法安全判定的 staging/target证据均不得清理。测试必须按对象身份断言 primary与`__cause__`，并断言 recovery evidence仍存在。"
- **Assertion coverage**: 行 266 要求 "commit与rollback同时失败时，断言caller捕获对象是注入的原commit exception、其`__cause__`是注入的rollback exception、note明确evidence retained，且journal/backup仍可供下一次recovery检查。"
- **Verdict**: ✅ **Fixed** — 精确指定了 Python 异常传播形状（primary + `__cause__` + `add_note()`），测试断言具体到异常对象身份，完全覆盖 DS finding 2。

### R3-C-PF-06 — S2 `DownloadedReportAsset` impact scan

- **Controller required fix**: 识别 type owner 并要求全仓 attribute/reference scan，覆盖 `.pdf_path`、constructor、fixture 和 type annotations。
- **Plan fix location**: 行 197（`R3-C-PF-06` marker）
- **Plan text**: "`DownloadedReportAsset` 的唯一类型 owner 是 `dayu/fins/pipelines/cn_download_models.py:233-249`；在该 dataclass把 `pdf_path: Path` 改为 `pdf_bytes: bytes`。... 实施前后都必须对整个 `dayu/fins` 与 `tests` 扫描：类型定义/import与注解、全部 `DownloadedReportAsset(...)` constructor、`.pdf_path` attribute access、`pdf_path=` keyword、fixture/fake以及位置解包。当前直接constructor证据位于两个downloader及 `tests/fins/test_cn_download_runtime.py`、`test_cn_pipeline.py`、`test_cn_download_workflow.py`；任何额外命中必须先加入S2明确文件边界并更新对应owner测试，不得用兼容property/re-export或动态访问过渡。"
- **Assertion coverage**: 行 350-351 要求 "CNInfo/HKEX asset的`pdf_bytes`、sha256、length一致；类型owner、constructors、fixtures、type annotations和所有consumer不再引用当前contract的`pdf_path`或`tempfile`。" 行 362-366 三个 rg scan 覆盖 type owner、imports/annotations、constructor、attribute/keyword 和 fixture。
- **Verdict**: ✅ **Fixed** — 明确 type owner、要求全仓扫描类型/constructor/属性/keyword/fixture/位置解包、三段式 rg validation 覆盖所有引用形式，完全对应 DS finding 3 的遗漏风险。

### R3-C-PF-07 — S1 per-phase failure injection strategy

- **Controller required fix**: 指定推荐注入 seam，避免基于调用计数的 mock；要求真实文件系统状态断言。
- **Plan fix location**: 行 253（`R3-C-PF-07` marker）
- **Plan text**: "优先使用storage owner内按语义命名的私有rename/journal helper作为受控seam；若不为生产逻辑增加helper，则monkeypatch既有 `_write_batch_journal(token, phase)` 与选定atomic rename helper，并按明确的`phase`值、source path与target path触发。禁止依赖'第N次调用'才抛错的call-count mock。"
- **Assertion coverage**: 行 256 要求 "每例都断言target/backup/staging/journal的实际目录内容、token关闭状态和传播异常，不只断言mock调用。" 行 264 重复强调 "按上述owner-level seam注入每个pre-commit phase失败"，不依赖 call-count。
- **Verdict**: ✅ **Fixed** — 明确两种推荐注入 seam（owner helper 或 phase/path monkeypatch），禁止 call-count mock，每例断言真实目录内容，完全覆盖 DS finding 4。

### R3-C-PF-08 — S3 snapshot field/error contract

- **Controller required fix**: 指定 `created_at` 为 timezone-aware `datetime`（由 Host 从现有 durable timestamp parsing 产生）；非法 durable token/timestamp 在 Host snapshot projection 处 fail closed，使用具体 Host-owned error path。
- **Plan fix location**: 行 214-215（`R3-C-PF-08` marker, 两处）
- **Plan text**: "`WaitAdapterSnapshot` 在 Host `wait_adapter` module定义为 frozen/slots dataclass，字段严格为 `tool_name: str`、`resume_token: str`、`created_at: datetime`。Host projection使用现有 `dayu.host.durable.codec.parse_utc_timestamp()` 把 `WaitRecordRow.created_at: str` 转成 timezone-aware UTC `datetime`；Service不解析、补时区或回退到 `now`。" 以及 "Host `wait_adapter` 新增 typed `WaitAdapterSnapshotProjectionError(ValueError)` 作为具体fail-closed路径。projection先按Host-owned opaque-reference基础contract校验 `resume_token.strip()` 非空且原字符串长度不超过 `HOST_WAIT_RESUME_TOKEN_MAX_LENGTH`；trim只用于判空，不改写durable值，Host也不解析Fins私有handle语义。随后解析timestamp；非法durable token或timestamp统一由该Host error以原始校验/parse error为`__cause__`抛出。poll/abandon在调用Service adapter前捕获它，adapter不得被调用，并分别进入现有 `ADAPTER_ERROR` / `ABANDON_ERROR` release-with-backoff路径；不得把错误交给Service转成lost/pending或默认值。"
- **Assertion coverage**: 行 436 要求 "Host adapter fake只收到三个允许字段；...空/超长resume token与非法durable timestamp都抛`WaitAdapterSnapshotProjectionError`并保留原校验异常为`__cause__`。fake adapter调用次数为0，poll/abandon分别留下Host-owned error/backoff diagnostic；Service没有parser/default-now/token容错分支。"
- **Verdict**: ✅ **Fixed** — 精确指定三个字段类型、Host parser 来源、新增 `WaitAdapterSnapshotProjectionError`、token 校验规则（strip 只判空不改写、长度上限）、timestamp fail-closed 路径、以及 adapter 不被调用的断言，完全覆盖 MiMo finding 004 和 DS open question 3。

### R3-C-PF-09 — S3 sequencing and documentation sync

- **Controller required fix**: S1 -> S2 -> S3 改为 mandatory 串行依赖；S1/S2 不得为 S3 留 TODO/compatibility；README/docs sync 只在三个 production slice 全部 land 后执行。
- **Plan fix location**: 行 386（`R3-C-PF-09` marker）
- **Plan text**: "实施顺序强制为 `S1 -> S2 -> S3`：只有S1 production/tests已land且per-slice review accepted后才能开始S2；只有S2 production/tests已land且per-slice review accepted后才能开始S3。不得并行实施或以'无production依赖'为由提前S3。" 以及 "S1/S2不得为S3新增TODO、temporary import allowlist、compatibility branch/re-export或永久过渡行为。"
- **Additional enforcement**: 行 413 "以下文档只在S1、S2、S3全部production变更与对应测试均已land后做current-fact同步"；行 478 实施与review依赖链再次强制 "S1 production+tests -> S1 review accepted -> S2 production+tests -> S2 review accepted -> S3 production+tests -> S3 review accepted -> README/docs sync -> final validation"；行 511 "后续严格完成S1 -> S2 -> S3全部production与test变更并通过各slice review后，才执行以下文档同步"
- **Verdict**: ✅ **Fixed** — 从"建议"改为"强制"，在5处重复强制串行依赖，明确禁止 S1/S2 留兼容过渡，文档同步明确延后到全部 slice land 后，完全覆盖 MiMo finding 005 和 DS finding 6。

### R3-C-PF-10 — S1 journal directory sync and `DoclingUploadService` batch context clarity

- **Controller required fix**: journal 写入复用既有 atomic JSON + directory sync 模式，包括 `COMMITTED` 写入；明确 `_acknowledge_source_before_blob_write()` 在显式 batch 内的行为。
- **Plan fix location**: 行 157（`R3-C-PF-10` marker, journal sync）和行 188（`R3-C-PF-10` marker, upload acknowledgement）
- **Plan text (journal sync)**: "所有 phase journal（包括唯一 commit point `COMMITTED`）必须复用 `_write_json()` 的 same-directory unique temp -> file flush/fsync -> atomic replace -> journal parent-directory fsync 完整模式；不得把 `COMMITTED` 降级为只写文件内容而不刷新目录项。"
- **Plan text (upload ack)**: "该 helper 在 create/未完成 update 时调用 `stage_source_document()`；shared storage core 必须复用当前 active batch并只写其 staging tree，不得触发 auto-batch commit。旧 completed update可返回 handle，但后续 blob/final meta仍写同一 active batch。helper本身不得 begin/commit/rollback，也不接管 token。"
- **Assertion coverage**: 行 247 S1 要求 atomic rename primitive + parent directory refresh + 所有 journal phase 复用完整模式；行 268 要求 "所有journal（尤其`COMMITTED`）也断言atomic JSON replace后的parent-directory sync。" 行 322 S2 要求 "helper的`stage_source_document()`必须检测并复用shared core当前active batch，只stage、不auto-commit；create/update/overwrite都不得产生第二个batch。" 行 349 S2 要求 spy 证明没有 nested begin/commit。
- **Verdict**: ✅ **Fixed** — journal sync 要求覆盖到 COMMITTED 的 parent-directory sync，upload acknowledgement 明确只 stage 不 auto-commit，完全覆盖 DS open questions 1 和 2。

## Tool-Security Deferred Verification

- **Section location**: 行 523 `## Tool-Security Deferred Items`
- **Items listed**: 4 项全部存在（upload allowlist/file authority/symlink、URL/TLS/redirect/SSRF provenance、remote byte budget、LLM-facing security schema）
- **Deferred status**: 行 540 明确 "上述4项在R3-C状态均为`assigned to later work unit`，不是当前slice residual，也不得以'顺手加校验'的形式进入实现。"
- **Leakage scan**: `rg -n -i 'allowlist|file.authority|symlink|SSRF|egress|byte.budget|security.schema|security prompt|tool.security'` 在 plan 中零命中（仅在 Non-Goals 和 Deferred Items section 出现为排除项描述）。S1/S2/S3 的 allowed changes 和 required assertions 中无任何安全策略项。
- **Verdict**: ✅ **Tool-security 保持 deferred**，未泄漏到任何 implementation slice。plan fix 没有引入 upload allowlist、URL/TLS/SSRF、byte budget 或 LLM-facing security schema 变更。

## New Findings

经逐条验证，plan fix 引入的变更均为 specification clarification（补全 contract、异常传播形状、测试注入策略、类型扫描范围、强制顺序），未发现 material evidence-backed implementation blocker。

以下观察不构成 new finding，仅作为 residual note 记录：

- **Residual Note**: S1 commit_batch 的 journal 写入复用 `_write_json()` 的完整模式（unique temp + flush/fsync + atomic replace + dir sync），但 `_write_json()` 当前行为是针对具体 JSON content 文件。plan 使用"复用...完整模式"而非"调用 `_write_json()`"，implementation agent 需判断是抽取通用 journal write helper 还是在 commit_batch 内联实现相同模式。这是正常的实现细节判断，不构成 plan 级别缺陷。

## Open Questions

无。原始 review 的 open questions（DS open questions 1/2/3）已通过 R3-C-PF-08 和 R3-C-PF-10 的 plan fix 收敛。

## Residual Risks

原始 plan 的 residual risks 分类不变。plan fix 未引入新的 residual risk 类别。

## Plan Re-Review Conclusion

**Status: pass**

全部 10 个 controller-accepted plan fix findings (R3-C-PF-01 至 R3-C-PF-10) 已在修订后的 plan 中正确落地：
- 每个 PF marker 在 plan 中存在且语义完整
- Fix 内容与 controller adjudication 的 required plan fix 一一对应
- 对应的 assertion/validation 覆盖了原 finding 的反例/失败场景
- Tool-security 四项保持 deferred，未泄漏到任何 implementation slice
- 无新增 material evidence-backed implementation blocker

Plan 已达到 code-generation-ready 状态，可进入 S1 implementation gate。

---

## Completion Report

- **status**: pass
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-rereview-ds.md`
- **fixed findings count**: 10
- **remaining findings count**: 0
- **new findings count**: 0
- **blocking questions count**: 0
