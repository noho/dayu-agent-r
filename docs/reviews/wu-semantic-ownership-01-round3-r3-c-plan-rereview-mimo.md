# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Plan Re-Review

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-C`
- Gate: plan re-review (post-fix)
- Reviewer: AgentMiMo
- Generated: `20260712-233250`
- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-controller-adjudication.md`
- Original reviews:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-ds.md`

## Review Scope

Re-review the plan after Codex plan fix to verify all 10 accepted findings (R3-C-PF-01 through R3-C-PF-10) are fixed. Also verify tool-security remains deferred and is not implemented/planned in any slice. Do not look for new speculative architecture advice; only report material evidence-backed new findings if the plan fix introduced a real implementation blocker.

## Finding Verification Matrix

### R3-C-PF-01 — S2 caller-batch contract for `commit_cn_filing_source_document`

- **Source**: DS finding 1 (high)
- **Required fix**: S2 must execute `commit_cn_filing_source_document()` only inside the caller-owned document batch; it must not create a second commit owner. Verification must prove reset → ack → blob → final meta → processed marker all occur under the same active batch.
- **Plan evidence**:
  - Line 191: "fast-skip与normal-convert两个call site都必须处在同一 caller batch，验证必须证明 reset -> source acknowledgement -> PDF/Docling blob -> final meta -> processed marker全过程使用同一个active token"
  - Line 326: "`commit_cn_filing_source_document()`在fast-skip与normal-convert路径都只能stage到该caller batch，且不得成为第二个commit owner"
  - Line 345: "fake/spy shared repository记录active token identity，证明reset -> acknowledgement -> PDF/Docling blob -> final meta -> processed marker（含`commit_cn_filing_source_document()`两个call site）全部发生在同一个caller-owned active batch"
- **Verdict**: **FIXED**. The plan now explicitly states the function can only stage into the caller-owned batch, forbids a second commit owner, and requires spy-based verification for both call sites.

### R3-C-PF-02 — S2 token lifecycle and commit-failure rollback rule

- **Source**: MiMo finding 001 (medium)
- **Required fix**: Callers rollback only operation exceptions before commit. After `commit_batch()` is called, success or failure is owned by storage; caller must propagate the storage exception and must not attempt invalid-token rollback.
- **Plan evidence**:
  - Line 189: "caller准备调用 `commit_batch()` 时即把生命周期所有权交给 storage；从调用开始，无论 success或failure，storage都负责消费 token与同步rollback/recovery，caller只原样传播 storage exception，绝不再调用 `rollback_batch()`"
  - Line 324: "operation exception/cancellation的`finally` rollback active token；调用`commit_batch()`前切换为storage-owned生命周期，此后不清空token绕状态，也绝不在commit failure后caller rollback"
  - Line 347: "commit success/failure测试证明从`commit_batch()`调用开始token归storage owner；commit failure不会触发invalid-token二次rollback"
- **Verdict**: **FIXED**. Token ownership boundary is now explicit: caller owns pre-commit, storage owns post-commit-call. Test assertion covers the invalid-token scenario.

### R3-C-PF-03 — S2 active-batch exception/cancellation pattern

- **Source**: MiMo finding 002 (low)
- **Required fix**: Specify batch scope pattern with `try/finally`, `commit_started` flag, no yield/await, sync CancelledError injection for tests.
- **Plan evidence**:
  - Line 190: "每个caller采用显式 active-batch `try/finally` 结构：在进入同步 mutation段前保存 active token与 `commit_started=False`；operation抛出 `Exception`或`BaseException`子类 cancellation时记录 primary error；`finally`仅在 `commit_started=False` 且token仍由caller拥有时执行一次rollback"
  - Line 190: "紧邻调用 `commit_batch()` 前把 `commit_started=True`，此后finally不得rollback。active token存在期间禁止任何 `yield`/`await`"
  - Line 190: "取消测试通过同步 cancellation checker/注入点在mutation段内抛 `asyncio.CancelledError`，而不是靠增加batch内await制造窗口"
  - Line 346: "operation exception与同步抛出的`asyncio.CancelledError`都在active-batch `finally`触发一次rollback"
- **Verdict**: **FIXED**. The pattern is fully specified with ownership switching, cancellation injection strategy, and required test assertions.

### R3-C-PF-04 — S1 `SWAPPED_TARGET` recovery semantic reversal

- **Source**: MiMo finding 003 (low)
- **Required fix**: Explicitly state that recovery for `SWAPPED_TARGET` before `COMMITTED` must delete the new target and restore backup, contrary to current behavior. Add required test for crash between swap and `COMMITTED`.
- **Plan evidence**:
  - Line 161: "恢复语义与同步 commit 同源：`STARTED/BACKED_UP_TARGET/SWAPPED_TARGET` 恢复 pre-batch 状态；只有 `COMMITTED` 保留 target并清理 backup。特别地，`SWAPPED_TARGET` 且尚无 `COMMITTED` 时必须先删除本次 new target，再把 backup恢复为 target；这与 `dayu/fins/storage/_fs_storage_infra.py:725-728` 当前'保留 new target、删除 backup'的行为相反，是 S1 必须落地并测试的行为变更，而非注释整理"
  - Line 265: "orphan recovery对STARTED/BACKED_UP/SWAPPED回滚，对COMMITTED保留target并清backup；crash-between-swap-and-`COMMITTED`用真实目录状态证明`SWAPPED_TARGET`执行语义反转"
  - Line 255: "必须包含'swap已完成但`COMMITTED`尚未写'的`SWAPPED_TARGET` case，断言new target删除、old backup恢复"
- **Verdict**: **FIXED**. The semantic reversal is explicitly called out as a behavior change (not cosmetic), with direct code reference to current behavior and required test coverage.

### R3-C-PF-05 — S1 dual commit/rollback error reporting

- **Source**: DS finding 2 (medium)
- **Required fix**: Specify propagation shape for commit failure plus rollback failure, including which error is primary, where rollback error is preserved, and that journal/backup evidence remains.
- **Plan evidence**:
  - Line 162: "原 commit exception仍是 caller捕获到的 primary exception；对它调用 `add_note()` 标明'rollback失败且recovery evidence已保留'，并以 `raise commit_error from rollback_error` 传播，使 rollback exception可从 primary的 `__cause__` 检查。不得只 log rollback error、不得让 rollback error替换 primary；journal、backup及任何无法安全判定的 staging/target证据均不得清理"
  - Line 266: "commit与rollback同时失败时，断言caller捕获对象是注入的原commit exception、其`__cause__`是注入的rollback exception、note明确evidence retained，且journal/backup仍可供下一次recovery检查"
- **Verdict**: **FIXED**. The propagation shape is precisely specified: primary = commit error, `__cause__` = rollback error, `add_note()` for evidence marking, journal/backup preserved. Test assertions are object-identity based.

### R3-C-PF-06 — S2 `DownloadedReportAsset` impact scan

- **Source**: DS finding 3 (medium)
- **Required fix**: Identify type owner and require full attribute/reference scans for `.pdf_path`, constructor usages, fixtures, and type annotations across `dayu/fins` and `tests`.
- **Plan evidence**:
  - Line 197: "`DownloadedReportAsset` 的唯一类型 owner 是 `dayu/fins/pipelines/cn_download_models.py:233-249`"
  - Line 200: "实施前后都必须对整个 `dayu/fins` 与 `tests` 扫描：类型定义/import与注解、全部 `DownloadedReportAsset(...)` constructor、`.pdf_path` attribute access、`pdf_path=` keyword、fixture/fake以及位置解包"
  - Lines 361-366: Three `rg` scans covering `NamedTemporaryFile|dayu_cn_downloads|dayu_hk_downloads|pdf_path`, `.pdf_path` attribute access and `pdf_path=` keyword, and `DownloadedReportAsset(` constructor — across `dayu/fins` and `tests`
  - Line 366: "三个scan共同覆盖type owner、imports/type annotations、constructor、attribute/keyword与fixture"
- **Verdict**: **FIXED**. Type owner identified, three complementary scans specified covering string literals, attribute access, and constructor patterns across the full scope.

### R3-C-PF-07 — S1 per-phase failure injection strategy

- **Source**: DS finding 4 (medium)
- **Required fix**: Specify preferred injection seams; use owner-level controlled helpers or journal/rename monkeypatches with explicit filesystem state assertions; avoid call-count-only mocks.
- **Plan evidence**:
  - Line 253: "优先使用storage owner内按语义命名的私有rename/journal helper作为受控seam；若不为生产逻辑增加helper，则monkeypatch既有 `_write_batch_journal(token, phase)` 与选定atomic rename helper，并按明确的`phase`值、source path与target path触发。禁止依赖'第N次调用'才抛错的call-count mock"
  - Line 254: "同步commit测试分别注入：旧target -> backup rename失败、`BACKED_UP_TARGET` journal失败、staging -> target rename失败、`SWAPPED_TARGET` journal失败、`COMMITTED` journal失败，以及commit error后的backup restore失败。每例都断言target/backup/staging/journal的实际目录内容、token关闭状态和传播异常，不只断言mock调用"
  - Line 256: "directory fsync/atomic JSON行为用helper spy按path/phase断言；底层rename仍在真实临时filesystem执行。不得用platform-specific chmod/ENOSPC技巧作为唯一覆盖，也不得mock掉最终filesystem state"
- **Verdict**: **FIXED**. Injection strategy is specified with preferred seams, explicit ban on call-count mocks, and mandatory filesystem state assertions.

### R3-C-PF-08 — S3 snapshot field/error contract

- **Source**: MiMo finding 004 + DS open question 3 (low)
- **Required fix**: Specify `created_at` as timezone-aware `datetime` produced by Host from existing durable timestamp parsing; invalid durable timestamp or resume token must fail closed at Host snapshot projection with a concrete error path.
- **Plan evidence**:
  - Line 214: "`WaitAdapterSnapshot` 在 Host `wait_adapter` module定义为 frozen/slots dataclass，字段严格为 `tool_name: str`、`resume_token: str`、`created_at: datetime`。Host projection使用现有 `dayu.host.durable.codec.parse_utc_timestamp()` 把 `WaitRecordRow.created_at: str` 转成 timezone-aware UTC `datetime`"
  - Line 215: "Host `wait_adapter` 新增 typed `WaitAdapterSnapshotProjectionError(ValueError)` 作为具体fail-closed路径。projection先按Host-owned opaque-reference基础contract校验 `resume_token.strip()` 非空且原字符串长度不超过 `HOST_WAIT_RESUME_TOKEN_MAX_LENGTH`；trim只用于判空，不改写durable值...非法durable token或timestamp统一由该Host error以原始校验/parse error为`__cause__`抛出。poll/abandon在调用Service adapter前捕获它，adapter不得被调用，并分别进入现有 `ADAPTER_ERROR` / `ABANDON_ERROR` release-with-backoff路径"
- **Verdict**: **FIXED**. Snapshot fields are precisely typed, Host uses its own durable parser, a concrete `WaitAdapterSnapshotProjectionError` error type is specified with fail-closed behavior, and poll/abandon map it to existing error/backoff paths.

### R3-C-PF-09 — S3 sequencing and documentation sync

- **Source**: MiMo finding 005 + DS finding 6 (low)
- **Required fix**: State S1 → S2 → S3 is mandatory for implementation. README/doc sync must occur only after all three production slices have landed. S1/S2 must not leave permanent TODO-style compatibility behavior for S3.
- **Plan evidence**:
  - Line 386-387: "实施顺序强制为 `S1 -> S2 -> S3`：只有S1 production/tests已land且per-slice review accepted后才能开始S2；只有S2 production/tests已land且per-slice review accepted后才能开始S3。不得并行实施或以'无production依赖'为由提前S3"
  - Line 387: "S1/S2不得为S3新增TODO、temporary import allowlist、compatibility branch/re-export或永久过渡行为；S3在既有文件最终删除Fins->Host特判"
  - Lines 413-421: Documentation files listed with explicit constraint "只在S1、S2、S3全部production变更与对应测试均已land后做current-fact同步"
  - Line 478: "实施与review的依赖链是强制 `S1 production+tests -> S1 review accepted -> S2 production+tests -> S2 review accepted -> S3 production+tests -> S3 review accepted -> README/docs sync -> final validation`"
- **Verdict**: **FIXED**. Sequencing changed from "recommended" to mandatory with explicit enforcement chain. Documentation sync is deferred to after all three slices land. No TODO/compatibility behavior allowed.

### R3-C-PF-10 — S1 journal directory sync and `DoclingUploadService` batch context clarity

- **Source**: DS open questions 1 and 2 (low)
- **Required fix**: Specify journal writes use the existing atomic JSON + directory sync pattern, including `COMMITTED` writes. Clarify how `_acknowledge_source_before_blob_write()` behaves when called inside an explicit batch during create/update.
- **Plan evidence**:
  - Line 157: "所有 phase journal（包括唯一 commit point `COMMITTED`）必须复用 `_write_json()` 的 same-directory unique temp -> file flush/fsync -> atomic replace -> journal parent-directory fsync 完整模式；不得把 `COMMITTED` 降级为只写文件内容而不刷新目录项"
  - Line 188: "`_acknowledge_source_before_blob_write()` 在 create/未完成 update 时调用 `stage_source_document()`；shared storage core 必须复用当前 active batch并只写其 staging tree，不得触发 auto-batch commit。旧 completed update可返回 handle，但后续 blob/final meta仍写同一 active batch。helper本身不得 begin/commit/rollback，也不接管token"
  - Line 349: "`_acknowledge_source_before_blob_write()`在create、update与overwrite显式batch内只stage到同一token；spy证明它没有触发nested begin/commit，ack失败走operation rollback"
- **Verdict**: **FIXED**. Journal durability contract explicitly includes COMMITTED with the full `_write_json` pattern. Acknowledgement helper behavior is clarified for all three paths (create, update, overwrite) with spy-based verification.

---

## Tool-Security Deferral Verification

Verified that tool-security remains deferred and is not implemented or planned in any slice:

1. **Non-Goals section** (lines 107-118): All four tool-security items explicitly listed as non-goals.
2. **Tool-Security Deferred Items section** (lines 523-540): All four items listed with evidence and deferred destination WU. Status: "assigned to later work unit"，"不是当前slice residual，也不得以'顺手加校验'的形式进入实现"
3. **S2 Stop Conditions** (line 376): "若修复要求引入URL/security/byte-budget policy或LLM schema变化，停止并记录到deferred tool-security WU"
4. **S1 allowed changes** (line 249): "不修改source/processed/blob repository public方法集合，不新增transaction facade"
5. **Final validation** (line 500): `git diff -- dayu/config/prompts dayu/fins/tools dayu/config/tool_discovery.json` verifies no LLM-facing changes
6. **Success signal** (line 103): "无 tool schema、prompt、LLM-facing upload/download security text或安全配置变化"
7. **CN/HK asset contract** (line 198): "不是 remote byte-budget实现：不改变 `response.content` 读取方式、不增加大小上限、不改变 retry/redirect/TLS/URL行为"

**Verdict**: Tool-security is comprehensively excluded from all three slices with multiple enforcement layers (non-goals, stop conditions, deferred items, validation commands). No slice introduces, plans, or enables tool-security implementation.

---

## New Findings Check

The plan fix addressed 10 specification-completeness findings. The changes were:

1. Clarified token lifecycle ownership boundary (PF-02)
2. Specified active-batch `try/finally` pattern with `commit_started` flag (PF-03)
3. Made SWAPPED_TARGET recovery reversal explicit as behavior change (PF-04)
4. Specified dual error propagation shape with `raise ... from ...` (PF-05)
5. Identified `DownloadedReportAsset` type owner and expanded scan scope (PF-06)
6. Added per-phase failure injection strategy with preferred seams (PF-07)
7. Specified `WaitAdapterSnapshot` fields, parser, and `WaitAdapterSnapshotProjectionError` (PF-08)
8. Changed sequencing from "recommended" to mandatory (PF-09)
9. Clarified journal COMMITTED durability and acknowledgement helper behavior (PF-10)
10. Clarified `commit_cn_filing_source_document` as stage-only in caller batch (PF-01)

These are all specification-completeness improvements within the existing plan architecture. None introduced new architectural decisions, new dependencies, new slice boundaries, or new scope items. No material evidence-backed new implementation blockers were found.

---

## Residual Risks

All residual risks from the original reviews remain valid and are unchanged:

| Risk | Classification | Owner / Destination |
|---|---|---|
| OS/hardware rollback rename failure | covered by S1 recovery contract | `dayu.fins.storage` orphan recovery |
| Directory fsync best-effort on unsupported platforms | accepted, tracked | Fins filesystem backend portability WU |
| Prior committed document not rolled back on later failure | accepted non-goal | multi-document transaction WU |
| CN/HK Docling conversion cannot be hard-interrupted | tracked by existing deferred finding | future process/subprocess isolation WU |
| Tool-security four items | assigned to later work unit | see plan "Tool-Security Deferred Items" |
| DR-024 Docling converter builder fallback | assigned to later work unit | umbrella controller decides future WU |
| R3-D financial/read semantics | covered by later approved sub-WU | `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D` |

No new residual risks introduced by the plan fix.

---

## Plan Re-Review Conclusion

**Status: pass**

All 10 accepted findings (R3-C-PF-01 through R3-C-PF-10) are verified as fixed in the plan. Each fix is backed by specific plan text at identified line locations. Tool-security remains comprehensively deferred across all slices with multiple enforcement layers. No new material implementation blockers were introduced by the plan fix.

The plan is now code-generation-ready for the three implementation slices.

---

## Completion Report

- **status**: pass
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-rereview-mimo.md`
- **fixed findings count**: 10
- **remaining findings count**: 0
- **new findings count**: 0
- **blocking questions count**: 0
