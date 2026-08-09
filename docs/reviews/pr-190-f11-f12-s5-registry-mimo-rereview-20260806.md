# PR 190 F11/F12 S5 Registry/Docs MiMo Re-Review

## Scope

- Mode: re-review（MiMo 独立复核，不依赖 DS review 或 adjudication 的中间结果）
- Branch: `codex/interactive-oracle`
- Base: `1a79ff1859117027340910152c0ce208a7f37b5d`
- Output file: `docs/reviews/pr-190-f11-f12-s5-registry-mimo-rereview-20260806.md`
- Re-review scope：
  1. 独立验证 accepted documentation-count precision fix（implementation artifact validation 措辞精度修正）
  2. 确认 registry/docs/readiness 内容与 SHA-256 未从初始 S5 review 变更
  3. 重跑决定性 count matrix：historical referenced subset 611/768/29、current command=interactive 612/768/28、full registry 1059/1614/64、accepted owner-defined 66 with exact owner distributions
  4. 检查 0 dangling/duplicate、JSON、graph、evidence refs/digests、git diff --check
  5. 确认 rejected DS frozen-ref concern 正确保留未变更，无 scope drift
- Included scope: 5 files（`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/cli_ci.md`、`docs/reviews/wu-interactive-memory-postfix-readiness.md`、`docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md`）
- Excluded scope: No Python code, schema, tests, README or production files modified
- Parallel review coverage: 无

## Review Artifacts Read

| Artifact | Path |
|---|---|
| MiMo initial review | `docs/reviews/pr-190-f11-f12-s5-registry-mimo-review-20260806.md` |
| DS adversarial review | `docs/reviews/pr-190-f11-f12-s5-registry-ds-review-20260806.md` |
| Controller adjudication | `docs/reviews/pr-190-f11-f12-s5-registry-review-adjudication-20260806.md` |
| Implementation artifact | `docs/reviews/pr-190-f11-f12-s5-registry-implementation-20260806.md` |
| Fix artifact | `docs/reviews/pr-190-f11-f12-s5-registry-fix-20260806.md` |

## Verdict

**PASS**

---

## Independent Verification: Documentation-Count Precision Fix

### Accepted Finding

Adjudication 接受了一个低严重度文档歧义：implementation artifact 原 validation 表把变更前历史引用子集（611/768/29）、当前 `command=interactive` inventory（612/768/28）、当前完整 registry（1059/1614/64）、owner-defined predicates（66）与 scenario-referenced predicate ids 压在两行中，导致数字看似冲突。

### Fix Verification

Implementation artifact（第 111-114 行）现在包含四个互斥、可复核的口径：

| 口径 | Records | Refs | Referenced IDs | Owner Distribution |
|---|---|---|---|---|
| historical referenced subset | 611 | 768 | 29 | refs: 766 interactive@2 + 2 prompt@1; ids: 28 interactive@2 + 1 prompt@1 |
| current `command=interactive` | 612 | 768 | 28 | 全部 → interactive@2 |
| current full registry | 1059 | 1614 | 64 | refs: 770 interactive@2 + 728 prompt@1 + 116 init@1; ids: 28 interactive@2 + 26 prompt@1 + 10 init@1 |
| accepted owner schema inventory | — | — | — | 66 owner-defined: 30 interactive@2 + 26 prompt@1 + 10 init@1 |

**独立机器验证结果**：全部四个口径的数字与我独立重跑的 JSON inventory 完全一致（见下方 count matrix 节）。Fix 只提高了 validation 叙述精度，没有改变 registry 字段、lifecycle、predicate contract、current-owner resolution 或任何 accepted contract。

---

## Decisive Count Matrix（独立重跑）

### 1. JSON Validity

| File | Result |
|---|---|
| `docs/cli_ci_oracles.json` | **PASS** — `python -m json.tool` succeeds |
| `docs/cli_ci_scenarios.json` | **PASS** — `python -m json.tool` succeeds |

### 2. Registry SHA-256

| File | Expected | Actual | Match |
|---|---|---|---|
| `docs/cli_ci_oracles.json` | `3404e241dbd71c6244da24b0dbb080022d4c57b36f040ac3456e7a18dbc97acf` | `3404e241dbd71c6244da24b0dbb080022d4c57b36f040ac3456e7a18dbc97acf` | **PASS** |
| `docs/cli_ci_scenarios.json` | `f4363fc5e7026ad075f4b7f855342cae493a4852d21bd72ef6e53b3f2d588e37` | `f4363fc5e7026ad075f4b7f855342cae493a4852d21bd72ef6e53b3f2d588e37` | **PASS** |

SHA-256 与 MiMo initial review、DS review、fix artifact 声称完全一致。Registry 内容未从初始 S5 review 变更。

### 3. Evidence SHA-256

| File | Expected | Actual | Match |
|---|---|---|---|
| `observed-report.md` | `bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411` | `bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411` | **PASS** |
| `digest.json` | `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d` | `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d` | **PASS** |

### 4. Inventory

| Metric | Count |
|---|---|
| Oracle records | 4 |
| Scenario records | 1059 (1053 accepted + 3 superseded + 3 unadjudicated) |
| Oracle key uniqueness | 0 duplicate |
| Scenario key uniqueness | 0 duplicate |

### 5. Supersedes Graph

| Check | Result |
|---|---|
| Oracle dangling refs | **0** |
| Oracle asymmetric edges | **0** |
| Scenario dangling refs | **0** |
| Scenario asymmetric edges | **0** |

Supersedes edges:
- Oracle: `cli.interactive.core-execution@2` → `cli.interactive.core-execution@1` (symmetric)
- Scenario: `tool-trace-formal@2` → `tool-trace-formal@1` (symmetric)
- Scenario: `rolling-correction-replacement@1` → `drop-superseded@1` (symmetric)
- Scenario: `cap-constrained-memory-replacement@1` → `drop-policy-limit@1` (symmetric)

### 6. Historical Referenced Subset

| Metric | Value |
|---|---|
| Scenarios referencing at least one `interactive.*` predicate (excluding 3 new) | **611** |
| Total `oracle_predicate_refs` | **768** |
| Referenced predicate ids | **29** (28 interactive.* + 1 prompt.*) |
| Ref owner: `cli.interactive.core-execution@2` | 766 |
| Ref owner: `cli.prompt.core-execution@1` | 2 |
| Referenced id owner: `cli.interactive.core-execution@2` | 28 |
| Referenced id owner: `cli.prompt.core-execution@1` | 1 |

### 7. Current `command=interactive` Inventory

| Metric | Value |
|---|---|
| Scenarios | **612** |
| Total `oracle_predicate_refs` | **768** |
| Referenced predicate ids | **28** |
| All refs resolve to | `cli.interactive.core-execution@2` |

### 8. Current Full Registry Inventory

| Metric | Value |
|---|---|
| Scenarios | **1059** |
| Total `oracle_predicate_refs` | **1614** |
| Referenced predicate ids | **64** |
| Ref owner: `cli.interactive.core-execution@2` | 770 |
| Ref owner: `cli.prompt.core-execution@1` | 728 |
| Ref owner: `cli.init.workspace-initialization@1` | 116 |
| Referenced id owner: interactive@2 | 28 |
| Referenced id owner: prompt@1 | 26 |
| Referenced id owner: init@1 | 10 |

### 9. Accepted Owner Schema Inventory / Stable Resolution

| Metric | Value |
|---|---|
| Total owner-defined predicates | **66** |
| Owner: `cli.interactive.core-execution@2` | 30 |
| Owner: `cli.prompt.core-execution@1` | 26 |
| Owner: `cli.init.workspace-initialization@1` | 10 |
| Dangling refs | **0** |
| Duplicate current owners | **0** |
| All 1614 refs resolved | **PASS** |

### 10. Readiness Frozen Prefix

```text
diff <(git show HEAD:docs/reviews/wu-interactive-memory-postfix-readiness.md) \
     <(head -130 docs/reviews/wu-interactive-memory-postfix-readiness.md)
→ 0 differences (EXIT:0)
```

Frozen finding text（lines 1-130）逐字节保留。Appended section 正确声明："both registries remain `calibration`; this artifact does **not** mark interactive, Oracle or registry readiness as ready."

### 11. `git diff --check`

**PASS** — 无 whitespace errors。

---

## Rejected DS Finding Verification

### S5-DS-02: frozen `accepted_oracle_refs` 指向 superseded oracle

**裁决：rejected-with-reason**。这是用户确认的 lifecycle contract，不是实现偏差。

**独立验证**：
- `docs/cli_ci.md` 新增文本明确 `accepted_oracle_refs` 是历史冻结字段，不参与 current owner resolution
- `docs/cli_ci.md` 新增文本明确 current resolution 按 stable `predicate_id` 解析
- Registry 数据中 609 条 active scenario 的 frozen `accepted_oracle_refs` 确实指向 `cli.interactive.core-execution@1`（已 superseded）
- 同时全部 1614 个 `oracle_predicate_refs` 通过 stable predicate ID 正确解析到 current accepted owner（0 dangling, 0 duplicate）
- 实现未做批量改写 frozen refs——符合 docs 声明

**结论**：rejected finding 正确保留未变更。Registry 数据、docs 和 implementation artifact 均未因该 rejected concern 而发生任何修改。

---

## Scope Drift Check

| Check | Result |
|---|---|
| Modified files count | 5（与初始 S5 scope 一致） |
| Registry data modified by fix | **否** — `cli_ci_oracles.json` 和 `cli_ci_scenarios.json` SHA-256 与初始 S5 review 一致 |
| `cli_ci.md` modified by fix | **否** — 只有初始 S5 的新增文本，fix 未触及 |
| Readiness modified by fix | **否** — 只有初始 S5 的 appended section，fix 未触及 |
| Implementation artifact modified by fix | **是** — validation 表措辞精度修正（第 111-114 行），符合 adjudication required fix scope |
| Fix artifact | 新增，记录 fix 过程与验证结果 |
| Python/schema/test/README changes | 无 |
| Stage/commit/push | 无 |

**结论**：无 scope drift。Fix 只修改了 adjudication 要求的 implementation artifact validation 措辞，未触及任何 registry 数据、docs、readiness 或 accepted contract。

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

## Residual Risk

1. **Oracle controller 裁决 pending**：三条 replacement scenario 仍为 `unadjudicated`。这是正确行为——Oracle controller 拥有 formal adjudication。不影响 S5 re-review 结论。

2. **Immutable evidence root 持续保留**：evidence root 当前可访问且 digest 匹配。长期保留由 CLI CI evidence-retention owner 负责。

---

## Overall Verdict

**PASS**。所有决定性机器检查独立重跑并通过：

| Check | Result |
|---|---|
| JSON validity (2/2) | PASS |
| Registry SHA-256 unchanged | PASS |
| Evidence SHA-256 unchanged | PASS |
| Supersedes graph (0 dangling, 0 asymmetric) | PASS |
| Historical referenced subset: 611/768/29 | PASS |
| Current command=interactive: 612/768/28 | PASS |
| Full registry: 1059/1614/64 | PASS |
| Owner-defined: 66 (30+26+10) | PASS |
| Stable resolution: 1614 refs, 0 dangling, 0 duplicate | PASS |
| Readiness frozen prefix preserved | PASS |
| git diff --check | PASS |
| Documentation-count precision fix verified | PASS |
| Rejected DS frozen-ref concern correctly unchanged | PASS |
| No scope drift | PASS |

S5 registry/docs implementation 与 fix 正确。Ready for Oracle controller dual code review completion。
