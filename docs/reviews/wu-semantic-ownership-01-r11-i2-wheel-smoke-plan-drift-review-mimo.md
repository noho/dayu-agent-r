# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 wheel smoke plan-drift complete review — AgentMiMo

## 1. Review target 与 scope

- **Reviewed artifact**：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- **Plan SHA-256**：`f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd`
- **Plan size**：942 lines / 81,592 bytes
- **Review scope**：完整 adversarial review，重点核验 R11-I2-VAL-PD-F02 closure、wheel build/archive 与 fresh runtime oracle 分离、macOS arm64/Python3.11 constraints owner、single normal install、pip check/help/importability 顺序、dependency failure stop、Windows workflow 不变、22/8/15/shared-node/stopped diff 保护。
- **Review date**：2026-07-18
- **Reviewer**：AgentMiMo

## 2. Authority 与完整读取证明

完整读取并遵守：

| Source | Lines | Status |
|---|---|---|
| `AGENTS.md` | 128 | PASS |
| accepted plan (942 lines / SHA `f1c95c3b...b2ffd`) | 942 | PASS |
| Controller adjudication `docs/reviews/wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-controller-adjudication.md` | 75 | PASS |
| AgentCodex fix artifact `docs/reviews/wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-fix-codex.md` | 159 | PASS |
| Controller validation `docs/reviews/wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-fix-controller-validation.md` | 37 | PASS |
| 总控 current state `docs/host/issues-implementation-control.md` §当前状态 | ~170 | PASS |

## 3. Key assumptions tested

| # | Assumption | Direct evidence | Verdict |
|---|---|---|---|
| 1 | R11-I2-VAL-PD-F02 已在 plan 中正确修复 | §2.4 line 103、§7.3 lines 647-668、§8.1 lines 702-707、§10 lines 932-935 | PASS |
| 2 | wheel build/archive 与 fresh runtime oracle 正确分离 | §2.4 "两类 oracle 分离"、§7.3 "fresh venv 只允许对 exact built wheel 做一次 normal constrained install"、§8.1 "两类证据分离" | PASS |
| 3 | macOS arm64/Python3.11 constraints owner 明确 | §7.3 line 647 使用 `constraints/lock-macos-arm64-py311.txt`、§8.1 line 703-704 明确 constraints 真源 | PASS |
| 4 | single normal install 语义正确 | §7.3 lines 659-661 "不得先做 `--no-deps` install、重复安装同一 wheel"、§10 lines 933-934 "只对 exact built wheel做一次 normal constrained install" | PASS |
| 5 | pip check/help/importability 顺序正确 | §7.3 lines 648-651 明确 `pip check` → `dayu.cli --help` → `upload_filings_from --help` → importability oracle、§8.1 line 704 "按顺序运行 `pip check`、两个真实 help 与 importability oracle" | PASS |
| 6 | dependency failure stop 语义正确 | §7.3 lines 670-674 "fresh constrained dependency resolution/install 失败、`pip check` 非零、任一真实 help/importability oracle 失败...这些 fresh-venv failure 是真实 packaging gate failure"、§8.1 lines 705-707 "依赖解析、下载或安装失败、lock 冲突、`pip check` 非零或任一 runtime oracle 失败都是真实 final packaging validation failure" | PASS |
| 7 | Windows workflow 不变 | fix-codex §5 "未改 §7.2 Windows workflow"、Controller validation §2 "Windows workflow、22/8/15 counts、shared function、review/commit sequence、deferred/security边界未变化" | PASS |
| 8 | 22/8/15/shared-node/stopped diff 保护 | §4 lines 197-210 明确 22/8/15 counts、§4 line 214 明确 shared path 只开放 `test_root_readme_matches_current_cli_public_contract`、Controller adjudication §4 line 49 stopped diff `6c8284c6...d0e6` 未变、fix-codex §6 所有 locks MATCH | PASS |

## 4. Plan internal consistency check

### 4.1 §2.4 baseline mapping ↔ §7.3 command 一致性

**检查结果**：PASS。

- §2.4 line 103 明确 "两类 oracle 分离"，§7.3 lines 647-668 实现了这一分离。
- §2.4 说 "fresh venv 只对 exact built wheel做一次 `constraints/lock-macos-arm64-py311.txt` normal constrained install"，§7.3 line 647 实现了 exact-one wheel 选择和 constrained install。

### 4.2 §7.3 command ↔ §8.1 validation 一致性

**检查结果**：PASS。

- §7.3 lines 647-651 的 command 顺序是：install → `pip check` → help → importability → archive negative oracles。
- §8.1 lines 702-707 的描述是："fresh venv 则只对 exact built wheel做一次 constrained normal install，再按顺序运行 `pip check`、两个真实 help 与 importability oracle"。
- 两者一致。

### 4.3 §7.3 stop conditions ↔ §8.1 failure semantics 一致性

**检查结果**：PASS。

- §7.3 lines 670-674 列出了 stop conditions：dependency resolution/install 失败、lock 冲突、`pip check` 非零、help/importability oracle 失败。
- §8.1 lines 705-707 列出了相同条件："依赖解析、下载或安装失败、lock 冲突、`pip check` 非零或任一 runtime oracle 失败"。
- 两者一致。

### 4.4 §10 checklist ↔ §7.3/§8.1 一致性

**检查结果**：PASS。

- §10 lines 932-935 明确：wheel build 保持 `--no-deps --no-build-isolation`、fresh venv 只做一次 constrained install、`pip check` → help → importability 顺序、dependency failure 按真实 packaging gate stop。
- 与 §7.3 和 §8.1 一致。

## 5. Attack surface analysis

### 5.1 Architecture boundary review

**检查结果**：PASS。

- wheel build/archive oracle 证明构建产物边界（§7.3 lines 644-655）。
- fresh runtime oracle 证明声明依赖可解析、安装且 wheel 可运行（§7.3 lines 647-651）。
- 两者正确分离，不混合。

### 5.2 Best-practice review

**检查结果**：PASS。

- 使用 `--constraint` 而非 `--no-deps` 安装 runtime wheel，符合 pip best practice。
- `pip check` 在 help/importability 之前运行，及早发现依赖问题。
- archive negative oracles 在 runtime oracles 之后运行，分离关注点。

### 5.3 Optimal-solution review

**检查结果**：PASS。

- Controller adjudication 接受了 `R11-I2-VAL-PD-F02` 的唯一正确修复：只改 validation plan，不改产品代码。
- lazy import、fallback、fixture/sys.path shim、重复 install、修改 lock、回改 Windows workflow 或扩大 I2 product/test 范围都被正确禁止。

### 5.4 Overengineering review

**检查结果**：PASS。

- plan 没有引入不必要的抽象或复杂性。
- 修复是最小化的：只改 validation plan wording，不改产品代码。

### 5.5 Overcoupling review

**检查结果**：PASS。

- wheel build/archive 和 fresh runtime oracle 正确分离。
- Windows workflow 不受 local correction 影响。
- 22/8/15 counts、shared-node contract、stopped diff 保护未受影响。

## 6. Specific verification points

### 6.1 R11-I2-VAL-PD-F02 closure

**检查结果**：PASS。

- Controller adjudication §1 明确 "Controller 接受 `R11-I2-VAL-PD-F02`"。
- Controller adjudication §3 表格显示 status 为 "ACCEPTED / OPEN"，plan owner fix 指向 §7.3 和 §8/§10。
- fix-codex §1 明确 "`R11-I2-VAL-PD-F02` 已在 accepted plan 的验证 owner boundary 修复"。
- fix-codex §8 表格显示 status 为 "`FIXED_IN_PLAN / PENDING_DUAL_COMPLETE_WHEEL_SMOKE_PLAN_REVIEW`"。
- Controller validation §1 明确 "`R11-I2-VAL-PD-F02` 已在 packaging validation owner中修复"。
- 总控 current state 明确 "`R11-I2-VAL-PD-F02` is fixed/controller-validated"。
- plan 中 §2.4、§7.3、§8.1、§10 和 Slice stop wording 已同步。

### 6.2 wheel build/archive 与 fresh runtime oracle 分离

**检查结果**：PASS。

- §2.4 line 103："两类 oracle 分离，不虚构未验证的 source archive owner"。
- §7.3 lines 644-645：wheel build 使用 `pip wheel --no-deps --no-build-isolation`。
- §7.3 lines 652-655：archive negative oracles 检查 METADATA、entry_points、extracted paths、RECORD。
- §7.3 lines 647-651：fresh runtime oracle 做一次 constrained install、`pip check`、help、importability。
- §8.1 lines 702-707："I2 local wheel runtime gate 必须保持两类证据分离"。

### 6.3 macOS arm64/Python3.11 constraints owner

**检查结果**：PASS。

- §7.3 line 647：`--constraint constraints/lock-macos-arm64-py311.txt`。
- §7.3 lines 659-660："constraints 真源固定为当前平台 `constraints/lock-macos-arm64-py311.txt`"。
- §8.1 line 703-704："constraints/lock-macos-arm64-py311.txt constrained normal install"。
- 当前执行平台是 Darwin arm64 / Python 3.11 `.venv`，与 constraints 文件匹配。

### 6.4 single normal install

**检查结果**：PASS。

- §7.3 lines 659-661："不得先做 `--no-deps` install、重复安装同一 wheel 或依赖 pip 的偶然重装行为"。
- §10 lines 933-934："只对 exact built wheel做一次 normal constrained install"。
- fix-codex §4.2 明确 "fresh venv 对该 wheel 只做一次 normal constrained install"。
- Controller validation §2 明确 "fresh venv只对 exact-one built wheel做一次 `constraints/lock-macos-arm64-py311.txt` normal constrained install"。

### 6.5 pip check/help/importability 顺序

**检查结果**：PASS。

- §7.3 lines 648-651：`pip check` → `dayu.cli --help` → `upload_filings_from --help` → importability oracle。
- §8.1 line 704："按顺序运行 `pip check`、两个真实 help 与 importability oracle"。
- §10 lines 934-935："随后 `pip check`、两个真实 help 与 importability 全部成功"。

### 6.6 dependency failure stop

**检查结果**：PASS。

- §7.3 lines 670-674："fresh constrained dependency resolution/install 失败、`pip check` 非零、任一真实 help/importability oracle 失败...这些 fresh-venv failure 是真实 packaging gate failure"。
- §7.3 lines 673-674："不得改回 runtime `--no-deps` install，不得以 lazy import、fallback、fixture/sys.path shim、修改 constraints/lock 或扩大 I2 product/test 范围补偿"。
- §8.1 lines 705-707："依赖解析、下载或安装失败、lock 冲突、`pip check` 非零或任一 runtime oracle 失败都是真实 final packaging validation failure...不得用 runtime `--no-deps`、重复 install、lazy import/fallback、fixture shim 或 lock/workflow 修改绕过"。

### 6.7 Windows workflow 不变

**检查结果**：PASS。

- fix-codex §5："未改 §7.2 Windows workflow、`22/8/15` counts、shared test node contract、review/commit sequence、deferred owner、security boundary 或 R12 boundary"。
- Controller validation §2："Windows workflow、22/8/15 counts、shared function、review/commit sequence、deferred/security边界未变化"。
- §8.1 line 707："本 local correction 不改变 §7.2 Windows workflow 的 install command或真实 Windows release gate"。

### 6.8 22/8/15/shared-node/stopped diff 6c8284c6...d0e6 保护

**检查结果**：PASS。

- §4 lines 197-210：cumulative unique paths 为 22，I1 为 8 paths，I2 从 14 修正为 15 paths。
- §4 line 214：唯一共享 path 只开放 `test_root_readme_matches_current_cli_public_contract`。
- Controller adjudication §4 line 49：stopped diff `6c8284c6...d0e6` 未变。
- fix-codex §6 表格：所有 locks MATCH，staged set empty。
- Controller validation §3："staged empty；`git diff --check HEAD` PASS"。

## 7. Findings

**零 finding。**

plan 在所有关键点上都是正确的：

1. R11-I2-VAL-PD-F02 已在 plan 中正确修复，所有相关章节已同步。
2. wheel build/archive 与 fresh runtime oracle 正确分离。
3. macOS arm64/Python3.11 constraints owner 明确。
4. single normal install 语义正确。
5. pip check/help/importability 顺序正确。
6. dependency failure stop 语义正确。
7. Windows workflow 不变。
8. 22/8/15/shared-node/stopped diff 6c8284c6...d0e6 保护正确。

## 8. Open questions

零 open question。

## 9. Residual risks

| # | Risk | Severity | Tracking |
|---|---|---|---|
| 1 | Windows real-run release blocker 仍未关闭 | HIGH | 已有 tracking，本 review 不改变 |
| 2 | stopped implementation/test/README/packaging 未重跑 | N/A | 本 review 是 plan-only，不涉及 implementation |

## 10. Verdict

**PASS。**

plan 在所有审查维度上都是正确的。R11-I2-VAL-PD-F02 已在 packaging validation owner boundary 修复，wheel build/archive 和 fresh runtime oracle 正确分离，所有关键约束（macOS arm64/Python3.11 constraints owner、single normal install、pip check/help/importability 顺序、dependency failure stop、Windows workflow 不变、22/8/15/shared-node/stopped diff 保护）均已明确且一致。

plan 是 code-generation-ready 的，可以交给 implementation agent。

---

**Review artifact path**：`docs/reviews/wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-review-mimo.md`
**Timestamp**：20260718-044414
**Reviewer**：AgentMiMo
