# WU-SEMANTIC-OWNERSHIP-01 / R11 最终 plan re-review 3 — AgentDS 独立 adversarial review

## 1. Gate 身份与审查边界

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- gate：R11 dual complete final-plan re-review 3（DS route）。
- immutable review target：
  `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
  892 lines / 75,434 bytes / SHA-256 `35a15ae9acd3276d8fea95473d295cb01c9b39c591f1bac077ccc1b93029f571`。
- 上一 gate Controller 裁决：
  `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-exact-source-q4-fix-controller-validation.md`
  105 lines / SHA-256 待锁定；verdict `PASS / READY_FOR_DUAL_COMPLETE_FINAL_PLAN_REREVIEW3`。
- 本审查不授权 implementation、stage、commit、R12、push 或 PR。reviewer verdict 不授权实现。
- 唯一 write：
  `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-exact-source-q4-rereview3-ds.md`。
- 不得改 plan/control/product/tests/README/design/CI/既有 artifacts。

**动机成立**：R11 plan 经过 boundary-rereview fix、source-lock rereview adjudication、exact-source/Q4 plan-only fix 与 Controller validation 后，需要独立的 adversarial final re-review 验证全部闭证未退化、无新增 scope/sequencing/architecture/overcoupling/test-gap/source-lock/residual defect。

## 2. 方法

1. 完整读取全部 892 行 plan，不做 delta-only 审查。
2. 按 plan authority order（§2.1）完整读取 AGENTS.md、Controller control（只读，非 dirty 内容）、
   umbrella optimization control、overdesign remediation plan、既有设计文档、全部 CURRENT source locks。
3. 完整读取 Controller rereview2 adjudication、AgentCodex exact-source/Q4 fix evidence、Controller fix validation、
   以及 DS rereview2 与 MiMo rereview2 原始 review artifacts。
4. 从 exact external absolute paths 只读加载两份 OLD 文件，独立执行全五个 Q4 oracle。
5. 对 immutable plan 做 adversarial 审查：全部八个 findings 闭证、source locks、
   two-slice state machine、sequential edit/safety stop、correction loop/combined revalidation、
   owner boundary、closed allowlist、pyright zero、per-file coverage >=80、activated .venv Ruff 0.15.11
   locked baseline、security/containment/atomic/secret、deferred/no-code、README、POSIX smoke、
   Windows PENDING_RELEASE_BLOCKER gates 均未弱化。
6. 查找任何新的 scope、sequencing、architecture、overcoupling/overdesign、test gap、source-lock
   或 residual defect。

## 3. 独立 source-lock 验证

### 3.1 External OLD 文件

| Exact external source | Lines | Bytes | Full SHA-256 | Verdict |
|---|---:|---:|---|---|
| `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py` | 2267 | 73,820 | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` | **MATCH** |
| `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py` | 555 | 20,921 | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` | **MATCH** |

验证方法：`wc -l -c` + `shasum -a 256`，与 plan §2.2 locked rows 逐项比对。两份文件均从
absolute external path 只读加载，未复制到当前 repo、tracked fixture 或兼容 surface。

### 3.2 Umbrella overdesign remediation plan

| Exact source | Lines | SHA-256 | Verdict |
|---|---:|---|---|
| `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` | 1269 | `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` | **MATCH** |

### 3.3 Plan immutability

| Property | Expected | Actual | Verdict |
|---|---|---|---|
| Lines | 892 | 892 | **MATCH** |
| Bytes | 75,434 | 75,434 | **MATCH** |
| SHA-256 | `35a15ae9acd3276d8fea95473d295cb01c9b39c591f1bac077ccc1b93029f571` | `35a15ae9acd3276d8fea95473d295cb01c9b39c591f1bac077ccc1b93029f571` | **MATCH** |

### 3.4 Plan authority references

Plan §2.1 七个 authority items 逐一验证：

1. `AGENTS.md` — 128 lines，`cb26618a...` SHA ✓
2. `docs/fins/design.md` §10 与 `docs/ui/design.md` §1-2 — 存在 ✓
3. Controller discussion Topic 7 final adjudication — 731 lines，locked SHA ✓
4. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §7、§18、§20-22 — exact path ✓；
   交叉验证：§7 覆盖验证协议、§18 覆盖 R11 umbrella 定义、§20 覆盖 README 矩阵（R11 行：根/Fins/tests）、
   §21 覆盖安全清单（含 CLI upload script quoting）、§22 覆盖 aggregate/PR gates ✓
5. `docs/phaseflow-umbrella-optimization-control.md` — 302 lines，locked SHA ✓
6. CURRENT production code/tests/READMEs — 逐项锁定 ✓
7. 两个 OLD external absolute paths — 见 §3.1 ✓

### 3.5 Ruff baseline

| Property | Expected | Actual | Verdict |
|---|---|---|---|
| Ruff version | `0.15.11` | `0.15.11` | **MATCH** |
| Baseline findings count | 144 | 144 | **MATCH** |
| Baseline SHA-256 | `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` | `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` | **MATCH** |

验证方法：`python -m ruff check dayu tests utils --output-format json > /tmp/r11-ruff-test.json`，
对原始 JSON 文件做 `shasum -a 256`。注意：SHA 是 raw JSON file hash（Ruff 原生输出字节级稳定），
不是 Python sort+re-serialize 的 hash。两路都确认 144 findings，无 Ruff 版本/规则漂移。

## 4. 独立 Q4 owner oracle

使用当前 `.venv/bin/python -B` 直接只读加载 external OLD
`/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py`，执行五个 oracle：

```text
Oracle 1: 2024Q4季报.pdf -> Q4                              PASS
Oracle 2: 2024Q4季度报告.pdf -> FY                            PASS
Oracle 3: 2024Q4年报.pdf -> FY                               PASS
Oracle 4: 2021Q4/季报.pdf -> (2021, 'Q4')                    PASS
Oracle 5: 2021Q4/季度报告.pdf -> (2021, 'FY')                 PASS
```

OLD 代码直接证据：

- `_Q4_QUARTERLY_MARKER_PATTERN = re.compile(r"季报", re.IGNORECASE)`（line 53）：
  只认 exact contiguous literal `季报`，`季度报告` 不命中，无宽松 alias。
- `_infer_fiscal_period_from_filename(filename)`（lines 221-252）：先判 H1/FY，再判 Q1-Q4；
  Q4 分支只在同一 filename 命中 `季报` 时返回 `Q4`，否则返回 `FY`。
- `_infer_fiscal_from_path(file_path)`（lines 255-307）：仅在 filename 自身不足时读取
  direct structured parent；`20YYQ4` parent 分支仍只对 `file_path.name` 搜索 exact `季报` marker。

Plan §5.2 rule 4 现明确四点：marker 只检查 child 完整 filename、quarterly marker 只认 exact `季报`、
FY/annual 在 Q1-Q4 前判定、direct 20YYQ4 parent fallback 仍只用 child filename exact `季报`。
Plan §5.3 owner-test matrix 明确锁定上述五个 exact cases。无需重开产品裁决。

注意：OLD line 105 的 `季报|季度.{0,5}报告|Quarterly.{0,5}Report` 是 priority 分类（层 1：季度正式报告），
不是 Q4 period inference marker。Plan 正确区分了这两条规则。

## 5. 全部八个 findings 闭证验证

### 5.1 五个 prior closed findings（维持 CLOSED）

| Finding | 原始 issue | Plan 处置 | 独立验证 |
|---|---|---|---|
| `R11-IMP-BF01` | producer-consumer 未合为 atomic slice | §4/§5/§6/§9：R11-I1 合并 WP-A/WP-B，无独立 work-package checkpoint | **CLOSED** — 状态机只有两个 implementation slices；transient inconsistency 不是 gate truth |
| `R11-PR-BF-RR-F01` | 顺序编辑 transient tree 可能被误解为合法 state | §5.1/§8.1/§9.1：多次明确 "不是合法 intermediate tree"、"safety stop 不是 checkpoint" | **CLOSED** — 三处交叉引用一致 |
| `R11-PR-BF-FR-DS-F01` | Ruff version oracle 不锁定 | §8.1：`ruff 0.15.11` verbatim + 版本漂移立即 stop | **CLOSED** — 独立验证 Ruff 0.15.11 |
| `R11-PR-BF-FR-DS-F02` | Ruff baseline SHA 不锁定 | §8.1：144 findings / SHA `051bd6cc...` + set difference 比较 | **CLOSED** — 独立验证 match |
| `R11-PR-BF-FR-CV-F01` | Controller fix validation gate | Controller 已验证并 CLOSED | **CLOSED** — 不重开已裁决 |

### 5.2 三个 accepted/fixed findings（已 FIXED / CONTROLLER-VALIDATED）

| Finding | Plan fix location | 独立验证 |
|---|---|---|
| `R11-PR-BF-RR2-DS-F01` | §2.1 item 7 + §2.2：两个 OLD rows 改为 exact external absolute paths | **VERIFIED** — plan 内 exact paths 各出现 2 次，lines/hash 不变 |
| `R11-PR-BF-RR2-DS-F02` | §2.1 item 4 + §2.2：umbrella plan label 改为 exact path | **VERIFIED** — 旧 `umbrella remediation plan` descriptive row 已消除 |
| `R11-PR-BF-RR2-DS-F03` | §5.2 rule 4 + §5.3 owner-test matrix：Q4 semantics + 五个 exact cases | **VERIFIED** — 12 个 required clause/case 全部存在，独立 oracle 全通过 |

三个 findings 对应 plan delta 精确为 5 hunks / 8 deletions / 14 additions，与 AgentCodex fix evidence
内嵌 diff 一致。Controller validation 已确认 reverse patch 回到 before-plan SHA。

## 6. Two-slice state machine 审查

### 6.1 结构正确性

```text
R11-I1 coordinated implementation（同一 uninterrupted task，顺序编辑）
  → 全部 coordinated edits 完成后首次 producer+consumer validation
  → 若 consumer 暴露 gap：Fins owner targeted correction + combined revalidation
  → Controller R11-I1 atomic checkpoint
  → R11-I2 packaging/README/Windows implementation
  → final cumulative validation + packaging/Windows evidence
  → Controller R11-I2 checkpoint
  → one cumulative code-review gate
```

独立验证：

- WP-A/WP-B 不构成独立 slices 或 state-machine nodes ✓（§9.1 明确）
- transient inconsistency 不是 gate truth ✓（三处交叉引用：§5.1 lines 224-232、§8.1 lines 655-667、
  §9.1 lines 805-810）
- safety stop 不构成 checkpoint ✓（同三处）
- 全部 coordinated edits 完成后才首次 validation ✓（§5.1、§8.1）
- correction loop 只允许 Fins owner 路径 ✓（§9.1 lines 813-816）
- correction 后必须 combined revalidation ✓（§9.1 lines 814-816）
- R11-I2 不回改 R11-I1 产品范围 ✓（§7.3 line 648）

### 6.2 潜在实现歧义

§9.1 line 814 写 "只在 Fins owner 路径 `dayu/fins/upload_batch.py` 与
`tests/fins/test_upload_batch.py` 做 targeted correction，CLI 继续机械消费同一 source of truth"。
若 correction 新增 typed field，consumer（CLI builder/renderer）需要对应机械投影（新 field → 新 flag）。
"CLI 继续机械消费同一 source of truth" 的原则正确，且 plan 明确要求 correction 后
"重跑 producer+consumer 全部 cumulative contract/tests/scans/smoke/coverage/full pyright/Ruff"；
consumer 侧测试会暴露机械投影是否完成。此非 plan defect，但 implementation Agent 需注意：
"只对 Fins owner 路径做 targeted correction" 约束的是 root cause fix location，不禁止 consumer
因 contract 变更做对应机械调整（该调整仍在同一 R11-I1 内，不创建新 sub-WU，不扩大 allowlist）。

**结论：state machine 无结构性缺陷；上述歧义由 combined revalidation gate 与实践约束覆盖。**

## 7. Gate 完整性验证

### 7.1 Closed allowlist

plan §4 列出的 production/packaging/CI、tests、README 完整 allowlist 逐项核对：

- Product: `dayu/fins/upload_batch.py`、`dayu/cli/commands/fins.py`、`dayu/cli/arg_parsing.py`、
  `dayu/cli/upload_script.py`（新增）、`pyproject.toml`、`requirements.txt`、
  `.github/workflows/r11-upload-script-windows.yml`（新增）+ 删除六个 placeholder package 文件 ✓
- Tests: 五个 test 文件 ✓
- README: 四个 README 文件 ✓
- R11-I1 与 R11-I2 的 slice allowlist 分配与 cumulative allowlist 一致 ✓

新增 `.github/workflows/r11-upload-script-windows.yml` 的 precondition 已验证：
当前 HEAD 无 `.github` tree/workflow；git `ls-files .github/` 返回空 ✓。

### 7.2 Owner boundary

- Fins 唯一产生分类/财期/material/skip facts ✓（§5）
- CLI 只消费 typed plan、拥有 argv/renderer/publisher/summary ✓（§6）
- §4 owner map 中 12 个 semantic fact 各有唯一 owner 与允许消费者 ✓
- §5.3 producer-consumer field/enum/optional-to-current-flag checklist（16 rows）逐字段冻结 ✓
- 反向依赖 scan 预期：Fins 零 `dayu.cli/service/host/engine/ui` import ✓
- renderer 零 filename/fiscal/material/cap regex ✓

### 7.3 Pyright zero

plan §8.1 line 668 明确 "任何时点都不得放宽当前 full pyright `0 errors` 要求"。未弱化 ✓。

### 7.4 Per-file line coverage >=80%

plan §8.2 从 coverage JSON `summary.percent_covered` 逐文件读取：
`dayu/fins/upload_batch.py`、`dayu/cli/commands/fins.py`、`dayu/cli/arg_parsing.py`、
`dayu/cli/upload_script.py`（新增）各 `>=80.00` ✓。
不扩大 omit/pragma、不虚报未变更文件、不以总覆盖率替代单文件结果 ✓。

### 7.5 Ruff

`ruff 0.15.11`、144 findings baseline、scoped 零错误、full set difference current-only 必须为空 ✓。
已独立验证（见 §3.5）。

### 7.6 Security gates

plan §8.3 安全 oracle：

- source containment: lexical + resolved，symlink 拒绝 ✓
- output containment: workspace root lexical + resolved，external ancestor symlink allowed ✓
- atomic replace: temp + flush/fsync + os.replace ✓
- secret non-persistence: API key/provider URL/exception cause 不进入脚本/summary ✓
- POSIX: 0o755 mode ✓
- Windows: setlocal DisableDelayedExpansion，no list2cmdline ✓
- argv injection marker test ✓
- script comment/body separation: body 无 `--infer`/API-key env/provider URL/网络调用 ✓

### 7.7 Deferred / no-code

Issue 142/151/175/177/178、R12、真实 Web/WeChat/render、Topic 8/9、统一 auth 的
production diff 必须为零 ✓。plan §3.3 明确 deferred 边界，§8.3 deferred diff scan 预期为空 ✓。

### 7.8 Windows PENDING_RELEASE_BLOCKER

plan 明确 Windows gate 在最迟 aggregate/draft PR check 前是 release blocker ✓。
本地 completion 可标 PENDING_RELEASE_BLOCKER 但不能标 closed ✓。
非 Windows 开发机可先完成本地验证 ✓。未弱化为 residual ✓。

### 7.9 README triggers

对照 AGENTS.md line 108-116：
- `dayu/fins/` 修改 → `dayu/fins/README.md` ✓
- `dayu/cli/` + packaging + 用户可见 CLI 变化 → 根 `README.md` ✓
- `dayu/README.md` 仅在分层/装配边界变化时更新 → plan 在既有边界内收敛语义 ✓
- `tests/` 修改 → `tests/README.md` ✓

### 7.10 POSIX smoke

§6.6 定义两类 POSIX smoke：recorder（adversarial argv round-trip with real `/bin/sh`）和
real upload（generated script runs real `python -m dayu.cli` into temp storage）✓。
Fixture 锁定为 tracked read-only `tests/fins/fixtures/aapl_xbrl/...` ✓。

### 7.11 Diffcheck 与 staged tree

```text
git diff --check: exit 0, stdout empty
git diff --cached --name-only: exit 0, stdout empty
```

Staged tree 为空 ✓。

## 8. 新 finding

### DS-RR3-F01：Plan gate marker 未随 exact-source/Q4 fix 更新（plan-only / LOW）

**证据**：

- Plan line 7-11：
  > 当前 gate：既有 R11 amended plan boundary re-review 的 accepted finding
  > `R11-PR-BF-RR-F01` plan-only wording fix continuation

  该描述指向原始 boundary-rereview gate，但当前已是 re-review 3。

- Plan line 20-22：
  > 本 gate 完成后停在 `READY_FOR_CONTROLLER_PLAN_WORDING_FIX_VALIDATION`，等待 Controller
  > 完整读取 amended plan、执行 validation 与双路 complete re-review

  该描述与 Controller 的
  "PASS / READY_FOR_DUAL_COMPLETE_FINAL_PLAN_REREVIEW3" verdict 不一致。

- Plan line 892：ending marker 仍为 `READY_FOR_CONTROLLER_PLAN_WORDING_FIX_VALIDATION`。

**分析**：plan 在 boundary-rereview fix 后经历了 source-lock rereview adjudication →
exact-source/Q4 Codex fix → Controller validation 三轮 gate transition，但 §1 的 gate 描述
与结尾 marker 未随 exact-source/Q4 fix 更新。implementation Agent 清屏后可能误认为
当前 gate 仍是原始 wording fix continuation，而不是 final re-review 3。

**严重性**：LOW。Controller 的明确 verdict 与当前 re-review 3 assignment 已覆盖 gate identity。
plan 实质性内容（source locks、Q4 rules、owner-test matrix）已正确更新。

**建议**：Controller 可将 §1 gate 描述更新为 re-review 3 continuation 并修改结尾 marker 为
`READY_FOR_CONTROLLER_R11_FINAL_PLAN_REREVIEW3_ADJUDICATION`，或在本 adjudication 中
直接记录 gate marker staleness 已裁决，避免 plan-only 再修。

## 9. 未发现的问题

以下维度经 adversarial 审查后未发现新 material finding：

- **scope creep**：未发现 R12、真实 Web/WeChat/render、Issue 142/151/175/177/178 或
  Topic 8/9 进入 allowlist。
- **sequencing**：R11-I1 → R11-I2 依赖顺序正确；R11 只消费 R06 upload transaction 与
  R09 direct-stream terminal contract（不修改其 owner）。
- **overcoupling**：Fins/CLI/renderer/publisher owner 边界清晰；反向依赖 scan 规范完整。
- **overdesign**：plan 在既有架构边界内收敛语义，未增加新 abstraction layer、generic
  framework 或 future-proofing。
- **test gap**：Q4 owner-test matrix 五个 exact cases 已锁定；§5.3 与 §6.6 的 coverage
  列表覆盖所有关键 contract（action auto/default、ticker CSV、infer、overwrite、
  metadata flags、output/summary、containment/symlink、adversarial argv、real smoke）。
- **source lock**：全部 CURRENT 与 external OLD locks 独立验证通过。
- **residual defect**：未发现此前 gate 未覆盖的安全、containment 或 contract 缺口。

## 10. Overall verdict

**VERDICT：READY_FOR_CONTROLLER_R11_FINAL_PLAN_REREVIEW3_ADJUDICATION**

| 维度 | 状态 |
|---|---|
| 五个 prior CLOSED findings | 维持 CLOSED，未退化 |
| 三个 accepted/fixed findings | FIXED / CONTROLLER-VALIDATED，独立验证通过 |
| External OLD source locks（2 files） | MATCH |
| Umbrella plan source lock | MATCH |
| Plan immutability（lines/bytes/SHA） | MATCH |
| Ruff version + baseline SHA | MATCH |
| 五个 Q4 owner oracles | 全部独立 PASS |
| Two-slice state machine | 无结构性缺陷 |
| Correction loop + combined revalidation | contract 正确，implementation Agent 注意机械投影 |
| Closed allowlist（production/tests/README/CI） | 无遗漏或扩张 |
| Owner boundary | Fins/CLI/renderer/publisher 无重叠 |
| Pyright zero / per-file coverage >=80% | 未弱化 |
| Security/containment/atomic/secret | 未弱化 |
| Deferred/no-code | 边界完整 |
| Windows PENDING_RELEASE_BLOCKER | 未误报 closed |
| README triggers | 与 AGENTS.md 一致 |
| POSIX smoke / real upload smoke | 两类 smoke 均定义 |
| Diffcheck + staged tree | PASS / empty |
| New finding DS-RR3-F01 | 1（LOW，plan-only gate marker staleness） |
| Blocker | 0 |
| Actual accepted residual | 0 |

**唯一建议**：Controller 在 adjudication 中处置 DS-RR3-F01（gate marker staleness），
可选择 plan-only fix 或直接在本 adjudication 记录已裁决。两选项均不改变 plan 的产品语义。

该 verdict 不授权 implementation、stage、commit、push 或 PR；等待 Controller 最终裁决。

READY_FOR_CONTROLLER_R11_FINAL_PLAN_REREVIEW3_ADJUDICATION
