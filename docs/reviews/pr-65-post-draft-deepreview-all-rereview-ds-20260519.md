# PR 65 Post-draft Deepreview-all Re-review (DS) - 2026-05-19

## Scope

- Branch: `feat/host-phase-11-recovery`
- HEAD: `8c4860e` gateflow: fix PR 65 post-draft deepreview docs
- Re-review target: PDA-F1 / PDA-F2 / PDA-F3 documentation fix as recorded in:
  - `docs/reviews/pr-65-post-draft-deepreview-all-controller-adjudication-20260519.md`
  - `docs/reviews/pr-65-post-draft-deepreview-all-fix-controller-20260519.md`
- Re-review mode: adversarial, read-only, no file modifications.

## Evidence

### PDA-F1: Root README stale Host status and broken links

**Claim**: Root `README.md` removed stale "Host 层正在重写中" wording, replaced broken `docs/host/interface-discussion-notes.md` with `docs/host/discussion-note.md`, and removed broken `docs/fmp_integration_research.md` link.

**Verification**:

```bash
rg -n "Host 层正在重写中|interface-discussion-notes|fmp_integration_research" README.md
# no matches
```

- Line 5 now reads: "`大愚 Agent` 的 Host 层提供 Session / Run / Attempt / EventLog、admission、dispatch、tool governance、memory / context governance 与 recovery 治理能力。" (correct, current capability statement)
- Line 19: `docs/host/discussion-note.md` — file exists at `docs/host/discussion-note.md` (61008 bytes, 2026-05-13)
- `docs/host/design.md` — file exists at `docs/host/design.md` (237337 bytes, 2026-05-19)
- Line 33-34: FMP 工具 section no longer carries `docs/fmp_integration_research.md` link

**Verdict**: FIX VERIFIED. All three sub-items addressed. No stale host status phrasing remains.

### PDA-F2: Host README code reading order omits recovery modules

**Claim**: `dayu/host/README.md` added recovery scanner / orphan proof / liveness helper to low-level diagnostic path list, and `dayu.host.recovery_process` / `dayu.host.recovery` to code reading order.

**Verification**:

- Low-level diagnostic path (line 269): "recovery scanner、orphan proof classifier、Host instance liveness helper 与 startup recovery diagnostic" — present
- Code reading order:
  - Item 8 (line 293): "dayu.host.recovery_process 与 dayu.host.recovery：理解 positive orphan proof、startup recovery scan、RECOVERING dispatch 与 recovery truth source" — present
  - Item 9 (line 294): "dayu.host.durable" — correctly renumbered
- Dispatch section (line 181): full recovery process description with `dayu.host.recovery_process` and `dayu.host.recovery` semantics — present

**Verdict**: FIX VERIFIED. Recovery modules correctly integrated into code navigation and diagnostic path list.

### PDA-F3: dayu/README.md references non-existent fins README

**Claim**: `dayu/README.md` removed reading-order link to absent `dayu/fins/README.md`.

**Verification**:

```bash
rg -n "dayu/fins/README" dayu/README.md
# no matches
```

- Code reading order now:
  - 1. dayu.contracts
  - 2. dayu.engine/README.md
  - 3. docs/host/design.md + dayu.host/README.md
  - 4. dayu.host + dayu.host.open_host
  - 5. dayu.runtime
  - 6. tests/README.md
- No reference to `dayu/fins/README.md` or `dayu.fins.storage` in code reading order
- Item numbering compacted correctly (old 5-7 → 5-6)

**Verdict**: FIX VERIFIED. Non-existent reference removed cleanly.

## Extended adversarial scan

### Stale term sweep

```bash
rg -n "Host 层正在重写|正在重写|重写中" README.md dayu/README.md dayu/host/README.md docs/host/design.md docs/host/discussion-note.md
# no matches

rg -n "interface-discussion-notes|fmp_integration_research" README.md dayu/README.md dayu/host/README.md
# no matches

rg -n "尚未实现.*见.*\.md" dayu/host/README.md dayu/README.md README.md
# no matches
```

### Whitespace hygiene

```bash
git diff --check
# clean

git diff --check main...HEAD
# clean
```

### Type check

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# 0 errors, 0 warnings, 0 informations
```

### Pre-existing issues (not blocking this re-review)

- `README.md` line 316 references `dayu/web/README.md` which does not exist in this repository. This reference is present on `main` branch as well (verified via `git show main:README.md`), and was not introduced by the PDA-F1/F2/F3 doc fix. It is out of scope for this re-review.
- `docs/host/design.md` was modified on this branch (Phase 11 recovery policy additions), not as part of the documentation fix — no concerns.

## Conclusion

PDA-F1 / PDA-F2 / PDA-F3 documentation fixes are **verified complete**. All three findings are correctly addressed with no regressions, no new blocked terms, and no stale references.

- stale term sweep: clean
- whitespace: clean
- pyright: 0 errors
- targeted verification: all three fix claims substantiated

**PASS**
