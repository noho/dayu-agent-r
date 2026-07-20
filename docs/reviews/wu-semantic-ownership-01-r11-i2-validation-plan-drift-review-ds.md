# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 validation plan-drift corrected plan — AgentDS adversarial review

## 1. Review target

- **Target**: corrected plan `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- **Lines**: 925
- **SHA-256**: `20f35e55573321ddfa474f772742097bb55963165936195de73785c39bc031dd`
- **Review scope**: 完整 925-line plan，不只看 plan-drift delta
- **Artifact identity**: 本 review 只输出 `docs/reviews/wu-semantic-ownership-01-r11-i2-validation-plan-drift-review-ds.md`；不修改 plan、code、test、README、packaging、workflow、control，不 stage/commit

## 2. Context and gate chain

Read and verified:

| Artifact | Lines | SHA-256 | Status |
|---|---|---|---|
| `AGENTS.md` | 128 | `cb26618a...c45e` | read / constraints applied |
| Accepted plan (corrected) | 925 | `20f35e55...31dd` | complete read |
| Controller adjudication | 63 | `f7741283...4c69` | verified |
| AgentCodex fix artifact | 142 | `32d7080d...9acb` | verified |
| Controller fix validation | 38 | `73968d95...6ad3` | verified |
| Control doc `## 当前状态` | rows 153–256 | read | gate = R11-I2 validation plan-drift dual complete plan review |

Independent lock verification:

| Lock | Expected | Actual | Match |
|---|---|---|---|
| HEAD | `a527ec03...5d65` | `a527ec03...5d65` | ✓ |
| Stopped product diff | `718846cd...8332` | `718846cd...8332` | ✓ |
| `tests/cli/test_arg_parsing.py` | `7cdc4c1d...ece6` | `7cdc4c1d...ece6` | ✓ |
| `dayu/cli/upload_script.py` (untracked) | `dfe0508d...ea65` | `dfe0508d...ea65` | ✓ |
| Windows workflow (untracked) | `4026da55...0953` | not independently verified (untracked, not in git) | — |
| Plan lines | 925 | 925 | ✓ |
| Staged set | empty | empty | ✓ |

## 3. Assumptions tested

1. **R11-I2-VAL-PD-F01 is truly closed by the plan correction** — verified by tracing every plan owner change in §4, §7.1, §7.2, §7.3, §8, §9.1, §10.
2. **22/8/15 path counts are internally consistent and match the stopped diff** — verified by enumerating tracked (20) and untracked (2) paths.
3. **Single shared path opens only `test_root_readme_matches_current_cli_public_contract`** — verified by checking the function's actual assertions against the plan's before/after contract.
4. **Batch-only infer / no JSON / executable script test contract is sufficient** — verified by reading the stale test function and the plan's exact replacement contract.
5. **Other I1 owners are protected** — verified by checking the before-lock mechanism, node-level diff review requirements, and the 7 non-shared I1 path hash invariants.
6. **Stopped product diff is preserved** — verified by independent hash recomputation.
7. **Review/commit/Windows release-blocker sequence is sound** — verified by tracing the complete §9 state machine.

## 4. Evidence

### 4.1 Path count verification

Tracked paths in stopped diff (`git diff --name-status HEAD`):

```
M  README.md, dayu/README.md, dayu/cli/arg_parsing.py, dayu/cli/commands/fins.py,
   dayu/fins/README.md, dayu/fins/upload_batch.py, pyproject.toml, requirements.txt,
   tests/README.md, tests/cli/test_arg_parsing.py, tests/cli/test_fins_commands.py,
   tests/cli/test_public_package_entrypoints.py, tests/cli/test_upload_filings_from_command.py,
   tests/fins/test_upload_batch.py
D  dayu/render/__init__.py, dayu/render/render.py,
   dayu/web/__init__.py, dayu/web/__main__.py,
   dayu/wechat/__init__.py, dayu/wechat/main.py
```

Tracked count: 20. Untracked: `dayu/cli/upload_script.py`, `.github/workflows/r11-upload-script-windows.yml`. Cumulative unique: 22. ✓

**I1 = 8**:
1. `dayu/fins/upload_batch.py`
2. `tests/fins/test_upload_batch.py`
3. `dayu/cli/commands/fins.py`
4. `dayu/cli/arg_parsing.py`
5. `dayu/cli/upload_script.py` (untracked, new)
6. `tests/cli/test_upload_filings_from_command.py`
7. `tests/cli/test_fins_commands.py`
8. `tests/cli/test_arg_parsing.py`

**I2 = 15**:
1. `pyproject.toml`
2. `requirements.txt`
3. `.github/workflows/r11-upload-script-windows.yml` (untracked, new)
4–9. Six deleted placeholder files
10. `tests/cli/test_public_package_entrypoints.py`
11. `tests/cli/test_arg_parsing.py` (shared with I1)
12. `README.md`
13. `dayu/README.md`
14. `dayu/fins/README.md`
15. `tests/README.md`

8 + 15 − 1 (shared) = 22. ✓

### 4.2 R11-I2-VAL-PD-F01 closure trace

| Plan owner | Before correction | After correction | Verification |
|---|---|---|---|
| §4 slice allocation | `test_arg_parsing.py` only in I1; I2 = 14 paths | I2 = 15 paths; shared path = test_arg_parsing.py; only `test_root_readme_matches_current_cli_public_contract` open | ✓ |
| §4 protected I1 | I2 authorization treated full file hash as immutable | before-lock `7cdc4c1d...ece6` must match before I2; after mutation, 7 non-shared I1 paths keep hash, shared path only changes one node | ✓ |
| §7.1 allowlist | 14 paths, test_arg_parsing.py excluded | 15 paths including shared test_arg_parsing.py, strict single-function scope | ✓ |
| §7.1 test contract | not specified | exact positive/negative assertions: remove `--infer` ban, remove JSON argv/no-shell assertions; add batch-only `--infer`, `FMP_API_KEY`, executable `.sh`/`.cmd` positive; add direct-upload no-`--infer`, no JSON argv/no-shell negative | ✓ |
| §7.2 workflow count | 22 cumulative listed without I2 path count distinction | explicit: 22 cumulative unique paths, I2 = 15 paths, shared test counted in 5 cumulative test files, no double-count | ✓ |
| §7.3 checkpoint | packaging focused command included full test file, no node ownership | before-lock match, single-function change, 15-path allowlist record, node-level diff review | ✓ |
| §8 validation | test file in final scan, node exception not explicit | 15-path allocation verification, current contract assertions, protected-I1 node verification, owner review requirement | ✓ |
| §9.1 state machine | I2 only packaging/README/Windows, I1 hashes generically protected | 15 paths, single shared node; before-mutation 8 I1 lock match; after-mutation 7 non-shared hash invariant + single-node delta | ✓ |
| §10 checklist | no plan-drift closure item | 22/8/15 count, single-node allocation, new README test contract acceptance item | ✓ |

F01 is **CLOSED** in all nine plan owners. No residual ambiguity.

### 4.3 Current test function state

The stale `test_root_readme_matches_current_cli_public_contract` at line 358 currently asserts:

```python
# Line 368: forbids --infer globally
for removed_contract in (
    "`write`",
    "--infer",       # ← must be removed
    ...
):
    assert removed_contract not in readme

# Lines 378–380: stale JSON/no-shell assertions
assert '"schema_version": 1' in readme    # ← must be removed
assert '"commands"' in readme             # ← must be removed
assert "不生成 shell" in readme            # ← must be removed
```

The plan's corrected contract (§7.1 step 5, and AgentCodex fix artifact §5) requires:

- Remove `--infer` from the global forbidden set
- Remove the three JSON/no-shell positive assertions
- Add positive assertions: `upload_filings_from` + `--infer` + `FMP_API_KEY`, POSIX `.sh` / Windows `.cmd` + `/bin/sh` / `cmd.exe /d /c`
- Add negative assertions: direct upload does NOT have `--infer`, old JSON argv `schema_version=1` / `commands` / "不生成 shell" do NOT appear
- Preserve other existing assertions (like `write`, `ci`, `web-provider`, etc.)

This is specific, actionable, and covers all three stale contract dimensions. ✓

### 4.4 I1 owner protection verification

The plan protects I1 owners through a multi-layer mechanism:

1. **Before-mutation lock**: All 8 I1 path locks must match before I2 begins (§9.1). This includes the test_arg_parsing.py before-lock `7cdc4c1d...ece6`.

2. **After-mutation invariant**: 7 non-shared I1 paths must keep identical hashes after I2 (§9.1). The shared path (test_arg_parsing.py) is the ONLY path allowed to change, and only one function within it.

3. **Node-level diff review**: The I2 checkpoint requires explicit proof that only `test_root_readme_matches_current_cli_public_contract` changed in test_arg_parsing.py (§7.3).

4. **Cumulative re-validation**: After I2, all I1 tests are re-run as part of the full cumulative validation (§8.1), ensuring no regression.

No other test function in test_arg_parsing.py references placeholder packages, Web/WeChat/render, or JSON argv protocols. The 36 other test functions in this file test parser mechanics, help text, CLI main behavior, and log configuration — none of which are affected by I2 packaging/README changes. ✓

### 4.5 Deferred scope verification

```bash
git diff --name-only R10_baseline -- dayu/service dayu/host dayu/engine \
  dayu/runtime dayu/config dayu/tool dayu/ui constraints \
  docs/host/design.md docs/engine/design.md docs/tool/design.md \
  docs/fins/design.md docs/ui/design.md
# → zero output
```

Deferred scope is clean. ✓

### 4.6 Review/commit/Windows release-blocker sequence

The plan's §9 state machine:

```
R11-I1 implementation → Controller I1 checkpoint (PASS, row 253)
  → I2 implementation (started, stopped at plan drift, row 254)
  → [current] plan-drift fix + dual complete plan review
  → Controller plan acceptance + new I2 authorization
  → I2 implementation continuation:
      before-lock match → single-function change → checkpoint
  → final cumulative validation (full tests, coverage, pyright, Ruff, scans, wheel smoke)
  → Controller I2 checkpoint
  → one cumulative code-review gate (dual review + adjudication + fix + re-review)
  → Controller accepted implementation commit
  → completion validation + completion commit
  → Windows gate: PENDING_RELEASE_BLOCKER
  → PR/push to GitHub → real Windows workflow run
  → Windows gate CLOSED or fix cycle
```

The sequence is logically ordered, has clear state transitions, and correctly defers Windows closure to post-push GitHub run. The plan correctly forbids claiming Windows closed before the real `cmd.exe` run. ✓

The plan also correctly separates:
- **Local completion**: can happen without Windows (with PENDING_RELEASE_BLOCKER noted)
- **Umbrella aggregate acceptance / PR ready**: MUST wait for real GitHub Windows run (§9.4)
- **Release closeout**: requires Windows CLOSED, accepted findings = 0, residual = 0

## 5. Findings

### 5.1 Finding summary

经过完整 925-line plan 审查、所有 hash/路径/契约验证、五个 adversarial lens 逐一应用，**零 material finding**。

下面三个 LOW 观察不是 plan defect，不阻止 plan acceptance 或 I2 implementation authorization，但值得在 I2 implementation checkpoint 中留意。

### LOW-O1: Node-level diff review 依赖人工判断，缺少自动化命令

- **位置**: §7.3 I2 checkpoint、§9.1 state machine
- **问题类型**: 可实施性
- **当前写法**: "I2 checkpoint 必须记录 exact 15-path allowlist，并用 node-level diff review 证明该文件其它 parser/help tests 未变化"
- **观察**: The plan specifies the WHAT (prove only one function changed) but doesn't specify an automated diff command. The I2 implementation agent must manually verify the node-level diff. This is not a defect — the Controller validation itself serves as the authoritative verification — but an automated `git diff` command targeting only the function could reduce human error risk.
- **严重程度**: LOW（不阻止 plan acceptance；Controller validation 覆盖此风险）

### LOW-O2: Plan §6.5 Windows algorithm description 使用现在时但 I1 已实现

- **位置**: §6.5
- **问题类型**: 措辞
- **当前写法**: "WP-B 实现顺序必须是：先把上述 adversarial matrix 写成 renderer unit + real-recorder oracle；再在唯一 renderer 内实现一个候选算法..."
- **观察**: §6.5 描述的是 I1 WP-B 的 Windows 实现策略。由于 I1 已经完成并通过 checkpoint，这段文字现在是描述性的（已执行的策略）而非指令性的（待执行的策略）。但措辞使用了"必须是"和"WP-B 实现顺序"这样的指令性语言，可能让 implementation agent 误以为需要重新实现。这在当前 plan-drift correction 的 scope 内不是问题（correction 只修改 I2-related sections），但未来若 plan 被新 agent 完整读取，可能产生困惑。
- **严重程度**: LOW（不影响当前 I2 继续实施；agent 会执行 I2 而非 I1）

### LOW-O3: Stopped tree 包含 partial I2 变更，plan 未显式声明其 resume baseline

- **位置**: §7.3 I2 continuation
- **问题类型**: 可实施性
- **当前写法**: "I2 continuation 必须先匹配 §4 的 protected tests/cli/test_arg_parsing.py before-lock"
- **观察**: The stopped tree contains both completed I1 changes AND partial I2 changes (README modifications, placeholder deletions, pyproject.toml/requirements.txt changes). The plan correctly requires the before-lock match, but doesn't explicitly enumerate which I2 changes are already in the stopped tree vs. which still need to be applied. The I2 implementation agent must discover this by comparing the stopped tree against the plan's I2 requirements. The Controller's I2 authorization (yet to be issued) will presumably clarify this, but the plan itself relies on implicit stopped-tree knowledge.
- **严重程度**: LOW（Controller I2 authorization 应解决此问题；不影响 plan correction 的正确性）

## 6. Adverse scenario stress tests

| Scenario | Plan behavior | Verdict |
|---|---|---|
| I2 agent modifies wrong test function in test_arg_parsing.py | Node-level diff review catches it; Controller checkpoint fails | fail-closed ✓ |
| I2 agent fails to match before-lock | I2 cannot start; Controller must investigate | fail-closed ✓ |
| I2 packaging changes break an I1 test | Full cumulative re-validation (§8.1) catches it | fail-closed ✓ |
| Wheel build includes placeholder package | §7.3 wheel archive/RECORD/METADATA oracles catch it | fail-closed ✓ |
| Wheel METADATA still has `Provides-Extra: web` | §7.3 exact-one METADATA assertion catches it | fail-closed ✓ |
| Windows workflow never runs (no push) | Plan marks PENDING_RELEASE_BLOCKER; umbrella aggregate/PR blocked (§9.4) | fail-closed ✓ |
| Windows workflow runs but fails | Plan requires fix cycle (§9.4); cannot close as residual | fail-closed ✓ |
| test_arg_parsing.py before-lock doesn't match (tree tampered) | I2 cannot start; stopped diff hash also wouldn't match | fail-closed ✓ |
| Agent removes `--infer` from test but doesn't add `.sh`/`.cmd` assertions | §7.1 contract spec requires both positive and negative assertions; Controller validation catches partial fix | fail-closed ✓ |
| Agent adds `--infer` back to direct upload contract | §7.1 negative assertion "direct upload 未获得 --infer" catches it | fail-closed ✓ |

All ten adverse scenarios are fail-closed. ✓

## 7. Lens application summary

### Architecture boundary review
- Fins ↔ CLI owner boundary unchanged by plan correction
- Shared path opening respects the existing parser test ownership
- No layer violation introduced

### Best-practice review
- Plan correction is minimal (only I2 allocation + test contract)
- Before-lock / after-mutation hash invariant pattern is a strong protection mechanism
- Node-level diff review is the right granularity

### Optimal-solution review
- Assigning the single test function to I2 (rather than I1) is correct because the README it tests is an I2 artifact
- The alternative (modifying the test in I1, before the README exists) would violate dependency order
- No credible simpler alternative exists

### Overengineering review
- No new abstraction, layer, builder, wrapper, protocol, migration, or generalization added
- Plan correction is a pure allocation fix with exact path count + contract specification
- No overengineering

### Overcoupling review
- No new coupling introduced
- Shared path mechanism is well-scoped (single function, explicit before/after locks)
- I1 and I2 remain independently verifiable slices with clear dependency order

## 8. Open questions

无。所有 plan 声明均已基于直接代码/状态证据验证。

## 9. Residual risks

| Risk | Owner | Tracking |
|---|---|---|
| Windows real `cmd.exe` quoting 未在本地验证 | R11 Windows workflow (GitHub Actions) | Plan §9.4: PENDING_RELEASE_BLOCKER，umbrella aggregate/PR 前必须通过 |
| Node-level diff review 可能漏检共享文件中的非目标函数修改 | Controller I2 checkpoint validation | Plan §7.3 要求 node-level diff review；Controller 独立验证 |
| I2 implementation agent 在 stopped partial tree 上继续实施时可能误解当前状态 | Controller I2 authorization | 新 authorization 应精确列出 stopped tree 状态与待完成工作 |

## 10. Plan review conclusion

**PASS**

R11-I2-VAL-PD-F01 is fully closed across all nine plan owners (§4, §7.1, §7.2, §7.3, §8, §9.1, §10). The corrected plan:

- Maintains exact cumulative/I1/I2 path counts at 22/8/15
- Opens only `test_root_readme_matches_current_cli_public_contract` in the single shared path
- Specifies precise positive/negative test contract assertions
- Protects all other I1 owners through before-lock matching, hash invariants, and node-level diff review
- Preserves the stopped product diff `718846cd...8332`
- Maintains correct review/commit/Windows release-blocker sequencing

Zero material finding. Three LOW observations are non-blocking. Plan is code-generation-ready for I2 implementation continuation.

---

*Review timestamp: 20260718-041411*
*Artifact: `docs/reviews/wu-semantic-ownership-01-r11-i2-validation-plan-drift-review-ds.md`*
