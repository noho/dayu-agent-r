# WU-SEMANTIC-OWNERSHIP-01 R06 Plan Review — AgentDS

## 0. Review Identity

- **reviewer**: AgentDS (second independent route)
- **umbrella**: `WU-SEMANTIC-OWNERSHIP-01`
- **target plan**: `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`
- **plan SHA-256**: `f147079bd9870f14402feb0782a3568109ccb710fa67d3bfe97add120f2336cd` ✓ verified
- **base commit**: `9c07b88d9e855f19f0b828f671022119cc5599a1`
- **controller entry validation**: `docs/reviews/wu-semantic-ownership-01-r06-plan-entry-controller-validation.md` — `PASS / READY_FOR_DUAL_PLAN_REVIEW`
- **this artifact**: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-ds.md`
- **method**: independent adversarial review with direct code evidence; no MiMo reading, no plan self-description as evidence, no Controller adjudication
- **scope**: Plan only. No code implementation, no test modification, no stage/commit/push/PR.

## 1. Evidence Baseline

### 1.1 Plan Motivation Verification

All five motivation points confirmed by direct code evidence:

| Plan claim | Code evidence | Verdict |
|---|---|---|
| Public `BatchToken` leaks internal state | `document_models.py:416-443` — exposes `owner_token`, `owner_scope_id`, all physical `Path` fields, `created_at` | **Confirmed** |
| `ContextVar` + `current_task()`/`get_ident()` = second authority | `_fs_storage_infra.py:64-67` (`_BATCH_OWNER_CONTEXT`), `:89-108` (`_current_execution_scope_id`), `:501-522` (`_require_batch_owner`) | **Confirmed** |
| `_execute_with_auto_batch()` blurs explicit/implicit | `_fs_storage_infra.py:423-464` — auto-begin on nil token, ambient owner join | **Confirmed** |
| `stage_source_document()` leaks `ingest_complete=false` into business schema | `_fs_source_document_core.py:1115` sets `ingest_complete = False`; `document_models.py:930` `FilingManifestItem.ingest_complete` field exists | **Confirmed** |
| Two-rename commit creates online reader window | `_fs_storage_infra.py:261-264` — `target->backup` then `staging->target` with no reader guard between | **Confirmed** |

Root cause characterization is correct: the same transaction authority fact is owned by three layers (public token, ambient execution context, source business meta). Plan's proposed single-owner convergence into `dayu.fins.storage` is the correct remedy.

### 1.2 Additional Evidence Discovered During Independent Review

These are code facts the plan does not explicitly cite but which materially affect plan feasibility:

**E1. `_ticker_dir_for_read` routes active-batch reads to staging** (`_fs_storage_infra.py:1376-1379`):
```python
token = self._active_batches.get(ticker)
if token is not None:
    self._require_batch_owner(ticker)
    return token.staging_ticker_dir
return self._target_ticker_dir(ticker)
```
This means `published read` is not truly separated from transaction-internal read today — even `_source_meta_path_for_read` and `_source_root_for_read` leak into staging. Plan's proposed separation (read methods default to published-only) will need to touch every `_for_read` path method, not only the public protocol.

**E2. `_get_handle_meta` in `store_file` creates blob-before-meta deadlock** (`_fs_blob_core.py:143`):
```python
self._get_handle_meta(handle)  # requires existing meta.json
```
Plan correctly identifies this and proposes blob-first staging. Implementation must verify that `store_file`'s `_build_store_key_from_normalized_filename` and `_build_file_store` do not internally depend on meta state.

**E3. `FsBatchingRepository` is not currently used in ANY production code** — verified by searching all `dayu/` and `tests/` Python files. `build_fs_repository_set` IS used (`service_runtime.py:347`, `cn_pipeline.py:373`, `sec_pipeline.py:509`) to create `_FsRepositorySet` shared across wrappers. But no production entry point creates `FsBatchingRepository`; current producers call `source_repo.begin_batch()` on `SourceDocumentRepositoryProtocol` which proxies to core. R06 must introduce NEW `FsBatchingRepository` construction at each production composition root — this is more invasive than signature propagation alone.

**E4. `LocalFileSource.open()` is currently a plain `Path.open("rb")`** (`local_file_source.py:32` and `dayu/documents/processors/local_file_source.py:49`). There is no existing guard/lock infrastructure on the read path. Plan §4.2 proposal to add publication swap guard to `Source.open()` must introduce a new lock type. The plan does not specify whether this guard uses the same `RuntimeFileLockToken` mechanism or another approach — implementation must resolve this.

**E5. `_write_json` already uses atomic temp+replace+fsync** (`_fs_storage_utils.py:524-551`). This is good — the existing atomic write pattern is proven.

**E6. Containment is already enforced** via `_normalize_path_component` (string-level) and `.resolve().relative_to()` (path-level) in `_resolve_handle_child_path` and `_local_path_from_uri`. No current symlink resolution that would bypass containment was found.

**E7. `SourceDocumentRepositoryProtocol` duplicates `begin_batch`/`commit_batch`/`rollback_batch`** (`repository_protocols.py:134-170`). Plan correctly identifies this must be deleted.

**E8. No other repository wrapper duplicates batching** — `FsDocumentBlobRepository`, `FsCompanyMetaRepository`, `FsProcessedDocumentRepository`, `FsFilingMaintenanceRepository` do not have their own begin/commit/rollback. Only `FsSourceDocumentRepository` does.

**E9. `DoclingUploadService` currently owns its own lifecycle** (`docling_upload_service.py:331` calls `begin_batch`). Plan §6 correctly identifies this must change to consume caller-provided batch.

**E10. `build_store_file` callback uses `functools.partial`** to capture `repository` and `source_handle` (`sec_download_persistence.py:156`), but has no `batch` parameter. Plan correctly identifies this must change to explicit batch parameter.

**E11. `Source.materialize()` is consumed by real processors**: `bs_processor.py` calls `source.materialize(suffix=".html")`, `docling_processor.py` calls `source.materialize(suffix=".json")`, `markdown_processor.py` calls `source.materialize(suffix=".md")`, and `source_snapshot.py` wraps `materialize()` with temp-file caching. The `Source` protocol (`dayu/documents/processors/source.py:57`) defines `materialize()` as returning `Path`. These consumers hold the returned path and use it for subsequent I/O — if a publication swap occurs between `materialize()` and that I/O, they read the new version. This is inherently a R07 snapshot/revision concern; R06's publication swap guard on `open()` does not cover `materialize()` callers.

**E12. Plan §6 final sentence already covers internal manifest routing**: "wrapper必须required batch并传给同一 core；core entry统一resolve active state；private manifest helper接显式 state/batch/path，不查询ambient". This closes the concern about manifest mutation routing under required batch. Plan §7.1 S1 production allowlist also includes all relevant core files.

## 2. Material Findings

Each finding has a stable ID, severity, direct evidence, and required plan correction.

---

### F-DS-001: Publication swap guard multi-core/multi-process ownership is underspecified

**Severity**: HIGH — blocking question

**Evidence**:
- Plan §4.2 describes a "storage-owned publication swap guard" that must protect: (a) commit physical swap, (b) recovery physical swap, (c) every published repository read/materialize, and (d) `LocalFileSource.open()`.
- Plan states guard must work "across multiple cores/processes" (Controller question 1).
- Current codebase uses `RuntimeFileLockToken` (file-based lock via `dayu.runtime.filelock`) for the writer transaction mutex — this is inherently cross-process.
- The current codebase has **no existing publication swap guard** — it must be newly introduced.
- The plan does not specify:
  - Whether the guard key is per-ticker, per-core, or global.
  - Whether the guard is held during the entire `read_file_bytes`/`get_source_meta` I/O, or released after fd open.
  - How the guard avoids deadlock when `get_source` internally calls `get_source_handle` + `get_primary_file`.
- **Critically**: The publication swap guard is a concurrency mechanism, NOT an authority mechanism. It must not be confused with the `BatchToken` authority. Unlike the writer transaction mutex (which excludes concurrent writers), the swap guard only serializes physical swap against published readers — it never authorizes any operation.

**Required plan correction**:
1. Specify guard key topology: per-ticker cross-process file lock (separate lock path from writer transaction lock), using the same `RuntimeFileLockToken` mechanism.
2. Define clear guarded/unguarded helper boundary: **public read API entry points acquire the guard once; internal `_for_read` path helpers are unguarded and must only be called from already-guarded public methods**. A public method that internally calls another public read method must release and re-acquire (or the inner call must detect outer guard via a private internal parameter, not via ambient/thread-local state).
3. Specify guard hold duration: for `get_source_meta`/`read_file_bytes`/`get_primary_file` etc., guard held for full I/O; for `LocalFileSource.open()`, guard held only until fd open succeeds, then released.
4. State explicitly: the publication swap guard IS a concurrency mechanism, NOT an authority check. It does not verify `BatchToken` or any caller identity. Its sole purpose is preventing readers from entering the rename gap between `target->backup` and `staging->target`.

**Without (2), implementation risks self-deadlock when `get_source` internally calls `get_source_handle` + `get_primary_file` which both try to acquire the same non-reentrant per-ticker file lock.**

---

### F-DS-002: `LocalFileSource.open()` stable-fd vs. `materialize()` — R07 already-owner residual

**Severity**: HIGH — residual/deferred owner

**Evidence**:
- Plan §4.2 says "`LocalFileSource` 必须带 required storage-owned open guard：`Source.open()` 获取同一 publication swap guard"
- Plan §1.3 says R06 does NOT implement R07 snapshot/revision — "一次 `Source.open()` 得到的 fd属于 old 或 new；多个先后独立 read call是否绑定同一版本不是 R06 contract"
- `LocalFileSource.materialize()` (`dayu/fins/storage/local_file_source.py:34-47` and `dayu/documents/processors/local_file_source.py:51-65`) simply returns `self.path` — no guard.
- **Real consumers of `materialize()`**: `bs_processor.py` (`source.materialize(suffix=".html")`), `docling_processor.py` (`source.materialize(suffix=".json")`), `markdown_processor.py` (`source.materialize(suffix=".md")`), and `source_snapshot.py` (wraps `materialize()` with temp-file caching). These processor implementations hold the returned `Path` and perform subsequent I/O outside any guard.
- If a publication swap occurs between `materialize()` returning a path and the processor reading from that path, the processor reads the new version — this is exactly the gap R06 acknowledges it cannot close.
- R07 (`docs/fins/design.md` §4) is the **already-designated owner** of "source snapshot 与 revision/version" and "concurrent update 期间 bounded retry". R06 correctly does not own this.

**Required plan correction**:
1. Explicitly state: `materialize()` returns a point-in-time `Path` with no snapshot or read-consistency guarantee. The returned path is valid only at the instant of the call. All current `materialize()` consumers in `bs_processor.py`, `docling_processor.py`, `markdown_processor.py`, and `source_snapshot.py` are R07's consumers — R06 does not change or guard their behavior.
2. State: R06's publication swap guard covers only `Source.open()` — the fd is stable for the lifetime of the returned `BinaryIO`. This is sufficient for callers that use `open()` and close promptly.
3. Add to R07 handoff (§12): "R07 must ensure long-lived processor reads (including all current `materialize()` consumers) use storage snapshot/revision, not bare paths. R06's online rename barrier ensures every single `open()` sees old-or-new complete; R07 adds cross-read snapshot binding."
4. **Do not** require R06 to change `materialize()` contract — that is R07's responsibility per `docs/fins/design.md` §4.

---

### F-DS-003: Complete-source validator manifest cross-check is a new commit invariant

**Severity**: MEDIUM — clarification

**Evidence**:
- Plan §5.2 rule 4: "`primary_document` 非空，精确命中 files manifest且对应物理文件存在；不得以第一文件 fallback掩盖缺失 primary" — **this is already explicitly specified in the plan**. No plan correction needed.
- Plan §5.2 rule 5: "filing/material ticker manifest 与 source 目录一一对应；无 dangling manifest、无 source 缺 manifest，identity、provenance 和完成态投影一致"
  - Current `upsert_filing_manifest` / `upsert_material_manifest` write manifest entries during every `_upsert_source_document` and `_toggle_source_deleted` call, and `_reset_source_document_impl` removes entries. The manifest is a write-side projection — it is not independently verified against the staged directory tree at commit time.
  - The proposed validator adds a **second consistency check**: at commit time, verify that every staged source has a manifest entry AND every manifest entry has a corresponding staged source directory. This is a new invariant that current code does not enforce.
- Plan §5.2 rule 3 already covers files manifest non-empty/no-duplicates — no gap.

**Required plan correction**:
1. In §5.2 rule 5, note that the manifest cross-check is a **new** commit-time invariant (not codifying existing read-time behavior), and that the implementation must verify bidirectional consistency (source→manifest and manifest→source). This is clarification only, not a design gap.
2. No other changes needed — rules 1-4 and 6 are already self-contained and supported by current schema.

---

### F-DS-004: Upload + Docling transaction boundary has "implementation 再裁决" gap

**Severity**: MEDIUM — blocking question

**Evidence**:
- Plan §6 row for CN `upload_filing_stream` / `upload_material_stream`: "转换/校验边界若无法在不新增通用 callback/profile 的前提下保持 transaction 短小，plan review 必须裁决；不得退回 implicit begin"
- This is an explicit deferral inside the plan text. The plan says the reviewer must adjudicate.
- Current code: `DoclingUploadService._execute_upload_operation` does `begin_batch` at line 331, runs ack → blob → final source → commit/rollback ALL inside one transaction.
- The plan's proposal (Docling consumes caller batch) is correct IN PRINCIPLE, but the CN upload flow's intermediate "转换/校验边界" (conversion/validation boundary between company meta write and Docling service call) is the unresolved part.

**Adjudication**:
- **Decision**: CN upload uses separate short transactions — company meta write is one transaction; each per-document Docling upload is another transaction with caller-provided batch.
- **Failure-mode acceptance**: company meta write success + Docling failure = retryable; no cross-transaction rollback needed. This is consistent with current code patterns.
- Docling service consumes caller-provided batch with no internal `begin_batch`.

**Required plan correction**:
1. Replace the deferral text in §6 CN upload row with: "Company meta write as short separate transaction; each per-document Docling upload consumes caller-provided batch."
2. Remove the "plan review 必须裁决" text — adjudicated here by AgentDS.

---

### F-DS-005: Manifest mutation internal routing — plan already covers this

**Severity**: NO-ACTION — confirmed in plan

**Evidence**:
- Plan §6 final row explicitly states: "wrappers/core internal manifest methods: wrapper必须required batch并传给同一 core；core entry统一resolve active state；private manifest helper接显式 state/batch/path，不查询ambient"
- Plan §7.1 S1 production allowlist includes all storage core files (`_fs_storage_infra.py`, `_fs_source_document_core.py`, `_fs_processed_core.py`, `_fs_blob_core.py`, `_fs_company_meta_core.py`, `_fs_maintenance_core.py`) where manifest helpers live.
- `_execute_with_auto_batch` removal is already a S1 goal — manifest methods that currently use it will be converted as part of the core refactoring.
- **Verified**: E12 confirms the plan addresses internal manifest routing at the contract level.

**Required plan correction**: None. S1 implementation task list should include a checklist item referencing §6 final row: "verify all internal manifest helpers accept explicit state/batch/path; `_execute_with_auto_batch` removed from manifest path."

---

### F-DS-006: S1/S2/S3 cumulative diff — per-slice review as reviewability gate

**Severity**: MEDIUM — sequencing risk

**Evidence**:
- Plan requires S1→S2→S3 as cumulative breaking cutover, no intermediate deployable state, S3 final tree only. This is correct — the three slices are one atomic cutover, not three independent releases.
- S1 touches 17 production files + 4 test files.
- S2 overlaps with 7 of S1's files.
- S3 touches 22 production files + 17 test files (including S1/S2 test files as fixture migration).
- Combined diff could exceed 3000 changed lines across 40+ files.
- Plan §7.0 states: "双路 code review 最终审查完整 R06 diff；是否需要 slice-level额外review由 accepted plan gate决定".
- Plan §12 review gate only mentions final review of "完整 R06 diff".

**Analysis**: The umbrella requires all product diffs be finally reviewed as a complete entity. Per-slice review is NOT a request for intermediate green/accepted commits — it is a **reviewability gate**: ensuring each slice's diff is small enough to be meaningfully reviewed before the next slice builds on it.

**Required plan correction**:
1. Add to §7.0 or §12: "Each slice S1/S2/S3 produces a focused per-slice review (diff < ~1500 lines) before the next slice begins implementation. These are reviewability gates only; no slice is independently accepted, committed, or claimed green. The final unified review of the complete R06 diff remains the acceptance gate."
2. This aligns with plan's existing per-slice testing strategy (§7.1/7.2/7.3 focused commands) while making review scope explicit.

---

### F-DS-007: `FsBatchingRepository` is a NEW production composition — not currently used anywhere

**Severity**: MEDIUM — evidence-invalid observation (allowlist refinement is required but more invasive than plan suggests)

**Evidence**:
- **Verified**: `FsBatchingRepository` is not imported or instantiated in ANY production or test code. The class exists in `fs_batching_repository.py` but has zero consumers.
- `build_fs_repository_set` IS used in production entry points:
  - `service_runtime.py:347` — `DefaultFinsRuntime._create()` creates `_FsRepositorySet`, passes to wrappers. Does NOT create `FsBatchingRepository`.
  - `cn_pipeline.py:373` — CN pipeline creates `_FsRepositorySet`. Does NOT create `FsBatchingRepository`.
  - `sec_pipeline.py:509` — SEC pipeline creates `_FsRepositorySet`. Does NOT create `FsBatchingRepository`.
- Current producers call `source_repo.begin_batch()` on `SourceDocumentRepositoryProtocol`, which proxies to core via `FsSourceDocumentRepository.begin_batch()`. Under R06, producers must instead call `batching_repo.begin_batch()` on `BatchingRepositoryProtocol`, and `SourceDocumentRepositoryProtocol` must drop `begin_batch`/`commit_batch`/`rollback_batch`.
- This means R06 must not only ADD `batch=` to existing methods but also INTRODUCE a new `FsBatchingRepository` composition at every production entry point — a more invasive change than "allowlist refinement."

**Required plan correction**:
1. In §7.3, add explicit note: "`FsBatchingRepository` is NEW composition in production entry points; it is not currently used anywhere. S3 must introduce `FsBatchingRepository` construction alongside existing `_FsRepositorySet` construction, sharing the same core, in `service_runtime.py`, `cn_pipeline.py`, `sec_pipeline.py`, and `sec_6k_primary_document_repair.py`."
2. Specifically reference `service_runtime.py:347`, `cn_pipeline.py:373`, `sec_pipeline.py:509` as the exact lines where new `FsBatchingRepository` construction must be added.

---

### F-DS-008: Baseline Ruff — `_fs_processed_core.py` IS in S1 allowlist

**Severity**: NO-ACTION — evidence-invalid

**Evidence**:
- Plan §7.1 S1 production allowlist line 289 explicitly includes `dayu/fins/storage/_fs_processed_core.py`.
- My initial review incorrectly stated this file was NOT in any allowlist. It is present in S1.
- All 10 scoped Ruff baseline items are in files that R06 touches in S1 or S3 — no unrelated churn.

**Required plan correction**: None. This finding is withdrawn.

---

### F-DS-009: Smoke test barrier mechanism — plan already specifies Event/barrier

**Severity**: NO-ACTION — plan adequate

**Evidence**:
- Plan §8.4 smoke test phase 5: "同步依赖 Event/barrier 与 deadline，不以 sleep 碰运气".
- Plan §8.4 phase 2: "用 test-only barrier 分别停在 validator前、target已backup、staging已target、COMMITTED journal后/cleanup前".
- The specific `threading.Event` vs `multiprocessing.Event` choice is a test implementation detail — the plan's contract (Event/barrier + deadline, no sleep-based timing) is sufficient.
- No direct impossibility evidence exists.

**Required plan correction**: None.

---

### F-DS-010: `replace_source_meta` → `upsert_filing_manifest` internal call chain — plan already covers

**Severity**: NO-ACTION — confirmed in plan

**Evidence**:
- Same as F-DS-005: Plan §6 final row covers internal manifest routing with explicit state/batch/path.
- `replace_source_meta` will propagate its `batch=` to internal manifest helpers as part of the S1 contract (all core entries resolve active state uniformly).
- The specific concern about `_fs_source_document_core.py:618,641` calling `upsert_filing_manifest`/`upsert_material_manifest` is a S1 implementation detail — the plan's contract already requires these internal calls to go through explicit state, not `_execute_with_auto_batch`.

**Required plan correction**: None. S1 implementation task list should reference this call site as a specific verification point.

---

## 3. Controller Mandatory Questions — DS Answers

### Q1: Publication swap guard multi-core/multi-process

**Answer**: See F-DS-001. Plan is underspecified on: per-ticker key topology, guarded/unguarded helper boundary, and deadlock avoidance when public read methods compose. Resolution: per-ticker cross-process file lock (separate path from writer lock); public read API entry points acquire guard; internal `_for_read` path helpers are unguarded. Publication swap guard is a concurrency mechanism, not authority — it never checks `BatchToken` or caller identity.

### Q2: `LocalFileSource.open()` stable-fd vs `materialize()`

**Answer**: See F-DS-002. `open()` guard covers fd acquisition moment; `materialize()` returns bare `Path` — unguarded by R06 design. Four real processor consumers (`bs_processor`, `docling_processor`, `markdown_processor`, `source_snapshot`) use `materialize()` today. R07 (`docs/fins/design.md` §4) is the already-designated owner of cross-read snapshot/revision. R06 must explicitly document this as a deferred residual; R06 must NOT change `materialize()` contract.

### Q3: Complete-source validator staged-tree/manifest closure

**Answer**: See F-DS-003. Rules 1-4 and 6 are self-contained and supported by current schema. Rule 5 (manifest cross-check) is a new commit-time invariant — the plan should note this explicitly but no design gap exists. Plan §5.2 rule 4 already explicitly forbids "first file fallback" — no plan correction needed.

### Q4: CN/SEC upload + Docling transaction boundaries

**Answer**: See F-DS-004. AgentDS adjudicates: separate short transactions for company meta + per-document Docling; Docling consumes caller-provided batch with no internal `begin_batch`. Plan's deferral text must be replaced with this decision.

### Q5: S1/S2/S3 cumulative breaking cutover

**Answer**: See F-DS-006. Cumulative approach is sound. Recommend per-slice review as **reviewability gates only** (not acceptance gates, not green intermediate commits). Each slice diff < ~1500 lines for meaningful review; final unified review remains the acceptance gate. Plan's per-slice testing strategy already supports this.

### Q6: Allowlist completeness and callback batch explicitness

**Answer**: Allowlist is correct. Key finding: `FsBatchingRepository` is a NEW composition (see F-DS-007, E3) — zero current production usage. Callback patterns correctly identified: current `partial(callback, repo, handle)` captures repository; R06 requires explicit `batch` parameter passed at each callback invocation. Plan §6 already covers internal manifest routing (F-DS-005, F-DS-010 are no-action).

### Q7: Baseline snapshot hygiene

**Answer**: Plan correctly references the single baseline mechanism in `issues-implementation-control.md`. All 10 scoped Ruff items are in files R06 touches. F-DS-008 was evidence-invalid — `_fs_processed_core.py` IS in S1 allowlist. No unrelated churn.

## 4. Non-Objectives Verification

Verified that plan does NOT authorize:
- ❌ R07 storage revision/snapshot/opaque-id — plan §1.3 and §4.2 boundary clearly defer to R07
- ❌ R08 financial/XBRL contract — not in scope
- ❌ R09 terminal validator — not in scope
- ❌ R10 HKEX — not in scope
- ❌ R11 CLI upload — not in scope
- ❌ Issue 142/151/175/177/178 — not in scope
- ❌ Unified authorization — not in scope
- ❌ Old schema migration/compatibility — plan explicitly forbids
- ❌ `hasattr`/`getattr` fallback — plan explicitly forbids
- ❌ Optional/default batch — plan explicitly forbids

## 5. Safety Regression Check

Plan claims retained safety mechanisms are not regressed:

| Mechanism | Current state | R06 impact | Verdict |
|---|---|---|---|
| Containment (`_normalize_path_component`, `.resolve().relative_to()`) | Present | Unchanged | ✓ Safe |
| Atomic write (`_write_json` temp+replace+fsync) | Present | Unchanged | ✓ Safe |
| Symlink escape prevention | String-level `_normalize_path_component` | Unchanged | ✓ Safe |
| Writer transaction mutex (ticker lock) | Present via `RuntimeFileLockToken` | Retained, semantics narrowed | ✓ Safe |
| Crash recovery journal | Present | Fields reduced to minimal set | ✓ Safe |
| Process fencing | Not present | Not introduced or removed | N/A |

No regression found. The plan removes `owner_pid`, `hostname`, and absolute paths from the journal — a security improvement (reduces information leakage in crash artifacts).

## 6. Finding Summary

| ID | Severity | Type | Summary |
|---|---|---|---|
| F-DS-001 | HIGH | Blocking question | Publication swap guard multi-core/multi-process design underspecified — per-ticker lock key, guarded/unguarded helper boundary, deadlock avoidance not defined |
| F-DS-002 | HIGH | Residual/deferred owner | `materialize()` consumed by 4 real processors; R07 already-designated owner; R06 must explicitly document as deferred residual, not change `materialize()` contract |
| F-DS-003 | MEDIUM | Clarification | Validator rule 5 manifest cross-check is a new commit invariant — plan should note explicitly |
| F-DS-004 | MEDIUM | Blocking question | CN upload transaction boundary has explicit plan deferral — adjudicated: separate short transactions |
| F-DS-006 | MEDIUM | Sequencing risk | 40+ file cumulative diff benefits from per-slice reviewability gates (not acceptance gates) |
| F-DS-007 | MEDIUM | Evidence-invalid observation | `FsBatchingRepository` is NEW composition — zero current production usage; plan should note this explicitly |
| F-DS-005 | NO-ACTION | Confirmed in plan | Manifest internal routing already covered by plan §6 final row |
| F-DS-008 | NO-ACTION | Evidence-invalid | `_fs_processed_core.py` IS in S1 allowlist — reviewer error |
| F-DS-009 | NO-ACTION | Plan adequate | Plan already specifies Event/barrier+deadline — cross-process Event type is implementation detail |
| F-DS-010 | NO-ACTION | Confirmed in plan | Same as F-DS-005 — plan §6 covers internal manifest routing |

## 7. Verdict

**PASS-WITH-FINDINGS**

The plan is fundamentally sound: motivation is confirmed by direct code evidence, root cause analysis is correct, the proposed single-owner storage convergence is the right approach, and the three-slice breaking cutover strategy is viable with the corrections listed above.

Two HIGH findings (F-DS-001, F-DS-002) and four MEDIUM findings (F-DS-003, F-DS-004, F-DS-006, F-DS-007) require plan amendment before implementation can be code-generation-ready. Four findings (F-DS-005, F-DS-008, F-DS-009, F-DS-010) are no-action — plan already covers them.

Specifically, the plan CANNOT proceed to implementation until:
1. Publication swap guard design is fully specified — per-ticker lock key, guarded/unguarded helper boundary, deadlock avoidance (F-DS-001)
2. `materialize()` deferred residual is explicitly documented with real consumer inventory and R07 ownership reference (F-DS-002)
3. CN upload transaction boundary deferral is replaced with adjudicated decision (F-DS-004)
4. `FsBatchingRepository` is noted as NEW production composition, not mere refinement (F-DS-007)

The plan correctly excludes all non-R06 concerns (R07-R11, Issues 142/151/175/177/178, unified authorization, old schema compatibility) and does not regress existing safety mechanisms.

---

*Review artifact only. No plan/control/product/test/README modification. No stage/commit/push/PR.*
