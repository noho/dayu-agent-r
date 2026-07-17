# WU-SEMANTIC-OWNERSHIP-01 / R11 final-plan source-lock re-review 2 — AgentDS

## 1. Gate、scope 与 reviewed target

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue。
- gate：dual complete final-plan re-review 2（DS route）。Controller 要求在 authority order 下完整读取最终 886 行 plan
  并做 adversarial review；不得只审 delta，不得授权 implementation。
- reviewed target：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
  - 886 lines / 74,647 bytes
  - SHA-256 `817c9d2fde2112c244e14659e713041748e59d048b77e07be2f0b8def5175a92`
- 输入 artifacts（完整读取）：
  - Controller adjudication（101 lines / 5,495 bytes / SHA `131b6a65...3dfc`）
  - AgentCodex fix2 evidence（105 lines / 5,929 bytes / SHA `bed1ddb8...db07`）
  - Controller fix2 validation（72 lines / 3,786 bytes / SHA `b6d97208...` — verified from identity in Controller validation doc §1）
- 本 artifact 唯一 write：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-source-lock-rereview2-ds.md`
- 不修改 product、test、README、design、CI、control、既有 review/auth/stop/adjudication artifact；不 stage/commit/push/PR。

## 2. §2.2 source locks 独立全量复测

### 2.1 验证方法

每条 source lock 都从 working tree 直接复测 lines 与 SHA-256；对与 `f7b452f9`（accepted plan commit）和
`2b14b2fb`（R10 completion baseline）相关的 lock，同时做三路比对。Ruff 版本与 baseline SHA 在 activated `.venv`
中采集。不使用 reviewer label 或 prior finding conclusion 替代独立复测。

### 2.2 逐行复测结果

| Plan §2.2 row | Lock lines | Lock SHA（abbrev） | Working tree | `f7b452f9` | `2b14b2fb` | Verdict |
|---|---|---|---|---|---|---|
| `AGENTS.md` | 128 | `cb26618a...45e` | 128 / `cb26618a...45e` | — | — | ✅ MATCH |
| Controller control（working tree，只读） | 2242 | `1906ce2f...808` | **2256** / `9ba19002...4859` | — | — | ⚠️ DRIFT（预期；Controller gate transition） |
| umbrella optimization control | 302 | `6d924e91...1db` | 302 / `6d924e91...1db` | — | — | ✅ MATCH |
| Controller discussion | 731 | `cd26760d...33a` | 731 / `cd26760d...33a` | — | — | ✅ MATCH |
| Host/Engine/Tool/Fins/UI design | 3696/553/134/123/111 | `276d35e1...` 等 | 全匹配 abbreviated hashes | — | — | ✅ MATCH |
| umbrella remediation plan | 1269 | `30c27562...a838` | 1269 / `30c27562...a838`（path: `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`） | — | — | ✅ MATCH（label ≠ path，见 Finding R11-PR-BF-RR2-DS-F02） |
| CURRENT `upload_batch.py` | 376 | `6767d30c...6178` | 376 / `6767d30c...6178` | — | — | ✅ MATCH |
| CURRENT `fins.py` | 1057 | `0db8ff2d...95a6` | 1057 / `0db8ff2d...95a6` | — | — | ✅ MATCH |
| CURRENT `arg_parsing.py` | 932 | `a0e25ad6...1c2c` | 932 / `a0e25ad6...1c2c` | — | — | ✅ MATCH |
| CURRENT `fmp_company_info.py` | 394 | `c2abfbe0...c46fa` | 394 / `c2abfbe0...c46fa` | — | — | ✅ MATCH（R11-PR-BF-FR-DS-F02 fix verified） |
| CURRENT `pyproject.toml` | 152 | `e076606f...6a25` | 152 / `e076606f...6a25` | — | — | ✅ MATCH |
| root / `dayu/` / Fins / tests README | 348/**265**/793/293 | `2f5cebfd...` / `16bbdc87...5367` / `a4805995...` / `15bb09f8...` | 348/265/793/293 / 全部匹配 | 265 / `16bbdc87...5367` | 265 / `16bbdc87...5367` | ✅ MATCH（R11-PR-BF-FR-CV-F01 fix verified） |
| CURRENT `requirements.txt` | 12 | `d1517613...5d3a` | 12 / `d1517613...5d3a` | 12 / `d1517613...5d3a` | 12 / `d1517613...5d3a` | ✅ MATCH 三路一致 |
| OLD `cli_support.py` | 2267 | `248cc859...da45` | **文件不存在于 working tree 或任何 git commit** | **不存在** | **不存在** | ❌ OLD FILE INACCESSIBLE（见 Finding R11-PR-BF-RR2-DS-F01） |
| OLD `upload_recognition.py` | 555 | `5a45618b...f816` | **文件不存在于 working tree 或任何 git commit** | **不存在** | **不存在** | ❌ OLD FILE INACCESSIBLE（见 Finding R11-PR-BF-RR2-DS-F01） |

### 2.3 Ruff version + baseline oracle

```text
$ source .venv/bin/activate && python -m ruff --version
ruff 0.15.11

$ source .venv/bin/activate && python -m ruff check dayu tests utils --output-format json | shasum -a 256
051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea  -
```

✅ 版本 oracle 与 baseline content hash 均与 plan §8.1 完全一致。未使用 global `ruff 0.15.9`。

### 2.4 Controller control drift

Controller control 已从 plan §2.2 锁定的 2242 行漂移至 2256 行（SHA 也变化）。Controller adjudication 已裁定为
"NO-FIX EXPECTED STATE"：control 是当前 gate truth owner，随每个 gate 合法变化。不构成 material finding。

## 3. Prior findings 独立闭证

### R11-IMP-BF01 → CLOSED

- **Claim**: 精确两个 implementation slices，无 producer-only gate truth
- **Independent verification**: Plan §9.1 精确定义两个 slices：`R11-I1 atomic Fins+CLI cutover` 与
  `R11-I2 packaging/README/Windows gate`。§4 明确 `R11-I1` 是 WP-A（Fins）+ WP-B（CLI）的 merged exact allowlist，
  不是独立 slice。§5.3 明文：WP-A 的 owner tests 只能在 WP-A+WP-B **全部 coordinated edits 完成后**运行，不能
  作为 WP-A checkpoint。§6.1 明文：WP-B 不是第二个 slice，不允许在开始 WP-B 前形成 producer-only checkpoint。
- **Updated plan text 直接引用**:
  - §4 lines 199-200: "`R11-I1 atomic cutover` 合并 §5 WP-A 与 §6 WP-B"
  - §5.1 line 219-220: "它与 §6 WP-B 共同使用 §4 的 `R11-I1` merged exact allowlist；本列表不是独立 slice allowlist"
  - §9.1 line 773: "R11-I1 的两个 ordered work packages 不构成 slices 或 state-machine nodes"
- **Verdict**: ✅ CLOSED。plan 无 producer-only checkpoint 或 gate truth。

### R11-PR-BF-RR-F01 → CLOSED

- **Claim**: sequential edit 与 transient gate truth/safety stop 边界完整
- **Independent verification**:
  - §5.1 line 225-231: 顺序编辑可短暂出现 transient inconsistency，但"它不是合法 intermediate tree，也不是 pass/failure baseline。在 WP-A/WP-B 全部 coordinated edits 完成前，不得运行或宣称 tests、pyright、coverage、Ruff、diff/diffcheck/scans validation"
  - §5.3 lines 355-360: safety stop 规则："Agent 必须停止 mutation，保留并报告当前 diff 作为 failed working evidence；不得继续冒险、不宣称 pass/checkpoint、不自行 rollback"
  - §9.1 lines 793-798: state machine 明确"顺序编辑中的 transient inconsistency 不是合法 intermediate tree 或 pass/failure baseline"
  - §9.1 lines 799-804: safety stop "不构成合法 intermediate state、failure baseline、acceptance、commit、review 或 next-slice transition"
- **Verdict**: ✅ CLOSED。transient inconsistency 的边界约束、validation 时序、safety stop 行为均已完整定义。

### R11-PR-BF-FR-DS-F01 → CLOSED

- **Claim**: `requirements.txt` full SHA 三路一致，旧值零残留
- **Independent verification**:
  ```text
  working tree: 12 lines / d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a
  f7b452f9:     12 lines / d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a
  2b14b2fb:     12 lines / d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a
  ```
  三路 lines/SHA 完全一致。
- **Verdict**: ✅ CLOSED。无 drift，无残留。

### R11-PR-BF-FR-DS-F02 → CLOSED

- **Claim**: FMP resolver label 已改为 exact path
- **Independent verification**:
  - Plan §2.2 row 现为 `CURRENT dayu/fins/resolver/fmp_company_info.py` | 394 | `c2abfbe0...c46fa`
  - Working tree: `dayu/fins/resolver/fmp_company_info.py` = 394 lines / `c2abfbe0...c46fa`
  - 旧 descriptive label `CURRENT FMP resolver` 零残留
- **Verdict**: ✅ CLOSED / CONTROLLER-VALIDATED。label 现在是 exact path。

### R11-PR-BF-FR-CV-F01 → CLOSED

- **Claim**: `dayu/README.md` lines/hash 已修正为 265 / full SHA
- **Independent verification**:
  ```text
  plan §2.2 README row: 348 / 265 / 793 / 293 | 2f5cebfd... / 16bbdc87...5367 / a4805995... / 15bb09f8...
  working tree: 265 / 16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367
  f7b452f9:     265 / 16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367
  2b14b2fb:     265 / 16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367
  ```
  三路完全一致。root/Fins/tests README 的 lines/abbreviated hash cells 逐字符不变。
- **Verdict**: ✅ CLOSED / CONTROLLER-VALIDATED。

## 4. 结构完整性验证

### 4.1 Two-slice state machine

Plan §9.1 精确描述两个 dependency-ordered implementation slices。状态机有六个明确节点：

1. `R11-I1 coordinated implementation`（WP-A + WP-B 顺序编辑）
2. 首次 producer+consumer cumulative validation
3. 可选 correction loop（Fins owner targeted correction → combined revalidation）
4. `Controller R11-I1 atomic checkpoint`
5. `R11-I2 packaging/README/Windows implementation`
6. `Controller R11-I2 checkpoint` → cumulative code-review gate

中间不存在 work-package checkpoint、slice acceptance 或中间 commit。状态转换条件在 §5.3、§6.6、§9.1 中完整定义。
✅ 状态机结构完整且无歧义。

### 4.2 顺序编辑 / safety stop

Plan §5.1、§5.3、§8.1、§9.1 多处重复加固同一组约束：
- 全部 coordinated edits 完成前，transient inconsistency 不是合法 tree
- 不运行 validation，不做 gate transition
- 真实 blocker 出现时 stop + 报告 failed working evidence
- 不宣称 pass/checkpoint，不自行 rollback，不扩大 scope

约束在四个不同章节中一致出现（§5.1 lines 225-231、§5.3 lines 355-360、§8.1 lines 653-655、§9.1 lines 793-804），
没有矛盾。✅ 边界完整。

### 4.3 Correction loop / combined revalidation

Plan §5.3 lines 344-348 与 §9.1 lines 806-810 定义同一 correction loop：
- WP-B consumer 暴露 owner gap → 只在 Fins owner 路径（`upload_batch.py` + test）做 targeted correction
- CLI 继续机械消费同一 source of truth
- 修复后必须重跑 §5.3 + §6.6 + §8 全部 cumulative validation
- 严禁在 builder/renderer/adapter/test fixture 补偿
- 严禁创建新 sub-WU/slice/commit 或扩大 allowlist

✅ Correction loop 边界清晰，combined revalidation 不缩水。

### 4.4 pyright / coverage / security / deferred / Windows gates

逐个验证：

| Gate | Plan 要求 | 当前 plan text | Weakened? |
|---|---|---|---|
| pyright | full `0 errors`，不放宽 | §8.1 line 662: "任何时点都不得放宽当前 full pyright `0 errors` 要求" | ❌ 未弱化 |
| coverage | 每文件 line coverage ≥ 80%，不用 `--branch` | §8.2 lines 705-708: "逐文件读取普通 line `summary.percent_covered`，每个 `>=80.00`" | ❌ 未弱化 |
| Ruff | scoped 零错误，full vs baseline set difference current-only 必须为空 | §8.1 lines 689-693: 版本 oracle + set difference + noqa 禁用 | ❌ 未弱化 |
| security | containment/symlink/atomic/secret scans | §8.3: 零匹配项以 `rg` exit 1 为成功证据，不吞错 | ❌ 未弱化 |
| deferred | Issue 142/151/175/177/178、R12、Topic 8/9 diff 为零 | §8.3 item 4: production diff 必须为空 | ❌ 未弱化 |
| Windows | `PENDING_RELEASE_BLOCKER`，不标 closed | §7.2 lines 603-606, §9.4: 明确定义 release blocker 语义 | ❌ 未弱化 |

✅ 所有 gate 完整保留，无弱化。

## 5. 关键 contract 验证

### 5.1 FMP resolver contract

- `dayu/fins/resolver/fmp_company_info.py`：394 lines，确认
- Public method：`FmpCompanyInfoResolver.resolve_company_info(self, canonical_ticker: str) -> FmpCompanyInfo`（line 135）
- Plan §6.2 item 4: "创建当前 `FmpCompanyInfoResolver` 并只调用一次其现有 public method `resolve_company_info(canonical)`"
- ✅ Contract 对齐：resolver 不读 env，不读 `FMP_API_KEY` 环境变量，由调用方显式传入 `api_key`

### 5.2 POSIX smoke fixture

- `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`：存在（1,503,780 bytes）
- Plan §6.6: fixture 是唯一内容源，测试只读取不修改
- ✅ Fixture 可访问

### 5.3 Sentinel test files

- `tests/tools/web/test_web_tools_provider.py` line 760：`"dayu.web"`
- `tests/tools/web/test_diagnose_web_access.py` line 49：`"dayu.web"`
- Plan §8.3: "两个合法 `"dayu.web"` 负向 import-boundary sentinel 必须精确各命中一次"
- ✅ 两个 sentinel 各命中一次

### 5.4 Placeholder packages

- Plan §7.1 item 3 要求删除六个 placeholder files
- Working tree 当前包含全部六个 tracked files：
  - `dayu/web/__init__.py`、`dayu/web/__main__.py`
  - `dayu/wechat/__init__.py`、`dayu/wechat/main.py`
  - `dayu/render/__init__.py`、`dayu/render/render.py`
- `git ls-files` 确认全部 tracked
- ✅ 删除 target 存在且正确。`.github/workflows/` 不存在，确认需新建。

### 5.5 Authority cross-references

- Authority item 4: "umbrella remediation plan §7、§18、§20—22"
  - `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`（1269 lines）包含对应章节：
    - §7 (line 147): "所有 slice 共用的实施与验证协议"
    - §18 (line 906): "R11 — OLD-aligned upload shell/cmd workflow 与 placeholder surface 删除"
    - §20 (line 1080): "README 触发决策矩阵"
    - §21 (line 1096): "安全相关 retained / modified 行为清单"
    - §22 (line 1121): "Aggregate 验证、deepreview、PR gates 与 final closeout"
  - ✅ 所有交叉引用可解析，内容对应
- Authority item 2: "`docs/fins/design.md` §10 与 `docs/ui/design.md` §1—2"
  - Fins design §10 (line 116): "Upload Batch Plan"
  - UI design §1 (line 12): "Public Entrypoint Lifecycle"、§2 (line 31): "`upload_filings_from`"
  - ✅ 交叉引用可解析

## 6. Current code vs plan gap analysis

### 6.1 `upload_batch.py` 当前状态 vs plan 要求

| Aspect | Current (376 lines) | Plan §5 requirement |
|---|---|---|
| Action type | `Literal["create", "update"]` | `Literal["auto", "create", "update"]`，默认 `auto` |
| Entry model | 单一 generic `UploadBatchPlanEntry` | 三个 typed models：`UploadBatchFilingEntry`、`UploadBatchMaterialEntry`、`UploadBatchSkippedEntry` |
| Plan result | `entries` + `skipped_files` | `recognized_entries` + `material_entries` + `skipped_entries` |
| Classification | SEC form token matching (10-K/10-Q/8-K etc.) | OLD fiscal/material classification with 12 rules |
| Fiscal inference | 无 | Filename + parent directory inference |
| Material routing | 无 | Three categories: FINANCIAL_STATEMENTS/EARNINGS_CALL/EARNINGS_PRESENTATION |
| Priority/dedup/caps | 无 | Full priority chain + dedup + annual=5/periodic=6/presentation=6/call=count |
| Symlink containment | 无（`path.is_file()` 不拒绝 symlink） | Full lexical+resolved containment with per-component symlink rejection |
| Skip reasons | Path-only skip (no reason code) | Typed reason code + readable reason |
| Request model | No `aliases`, no `overwrite`, no `--infer`-related | Canonical ticker + aliases, overwrite, explicit fiscal overrides |

**评估**: 当前 `upload_batch.py` 几乎没有 plan 需要的 OLD 分类语义。plan 要求的是 fundamentally different
classification engine，不是渐进式改进。这个 gap 本身不是 plan defect——plan 清楚地描述了目标状态——但意味着
R11-I1 WP-A 本质上是一次重写而非修改。

### 6.2 `arg_parsing.py` 当前状态 vs plan 要求

| Aspect | Current | Plan §6.2 requirement |
|---|---|---|
| `FILING_ACTION_CHOICES` | `("create", "update", "delete")` | `("auto", "create", "update", "delete")` |
| `BATCH_UPLOAD_ACTION_CHOICES` | `("create", "update")` | `("auto", "create", "update")` |
| Default action | `"create"` (line 904) | `"auto"` |
| `--infer` | 不存在 | `action="store_true"`, `default=False` |
| `--overwrite` on batch | 不存在 | `action="store_true"`, `default=False` |
| ticker CSV parsing | 单一 `--ticker` | CSV with canonical+aliases |

### 6.3 `fins.py` (CLI) 当前状态 vs plan 要求

| Aspect | Current | Plan requirement |
|---|---|---|
| `upload_filings_from` output | JSON (`schema_version: 1, commands: [argv...]`) | `.sh`/`.cmd` executable scripts |
| `_render_upload_batch_plan` | 存在，输出 JSON | 删除，替换为 `upload_script.py` renderer |
| JSON constants | `_UPLOAD_BATCH_SCHEMA_VERSION` 等 | 全部删除，零残留 |
| `BatchUploadAction` import | 从 `upload_batch` 导入 | 更新为含 `auto` 的新类型 |
| `--overwrite` on batch | 不存在 | 传播到 Fins request |

## 7. New current material findings

### R11-PR-BF-RR2-DS-F01 — OLD source files inaccessible（中）

- **位置**: Plan §2.2 source lock table 最后两行；§2.1 item 7；§5.2 全部 OLD-aligned 分类规则
- **问题类型**: 契约缺失 / open question 未收敛
- **当前写法**: Plan §2.2 列出两个 OLD 文件 `dayu/fins/cli_support.py`（2267 lines, SHA `248cc859...da45`）与
  `dayu/fins/upload_recognition.py`（555 lines, SHA `5a45618b...f816`）作为 source lock。§2.1 item 7 声明它们
  "只作为用户工作流与分类规则证据"。§5.2 转录 12 条 OLD-aligned 分类规则。
- **反例/失败场景**: Implementation agent 执行 preflight，按 §2.2 source lock 表找到 OLD 文件的 lines/hash，
  试图读取验证 §5.2 转录的 OLD 规则是否完整、正确、无遗漏时，发现文件不存在于 working tree 或任意 git commit。
  如果 OLD 规则中存在 §5.2 未覆盖的边缘情况（例如某些 fiscal period pattern、material routing 边界或 priority
  edge case），Agent 无法发现。
- **为什么有问题**: 违反了 "root cause 必须逻辑/数据同源" 与 "先判断动机是否成立" 纪律——Agent 必须在无法访问
  第一手证据的情况下信任 plan 的规则转录。此外，§2.1 item 7 说它们"只作为……证据"，但如果文件不可达，"证据"
  功能不成立，lock 中的 lines/hash 值也无法被 Agent 验证其来源。
- **直接证据**:
  - `git log --all -- 'dayu/fins/cli_support.py'`：无历史
  - `git log --all -- 'dayu/fins/upload_recognition.py'`：无历史
  - `git show f7b452f9:dayu/fins/cli_support.py`：返回 1 line（空）
  - `find . -name 'cli_support.py' -o -name 'upload_recognition.py'`：无匹配
- **影响**: Implementation Agent 无法独立验证 §5.2 规则是否完整覆盖 OLD 行为。如果 OLD 规则与 §5.2 转录存在
  未发现的差异，实现将有语义错误，且只能在 Controller（有文件访问权限的人）review 时捕获。
- **建议改法和验证点**:
  1. 将两个 OLD 文件加入 tracked read-only fixture（如 `tests/fins/fixtures/old/`），供 Agent preflight 验证。
  2. 或在 plan 中显式声明：文件不可达，§5.2 规则已由 Controller（有访问权限）逐条验证对应 OLD 行为完整无误，
     并记录验证日期与比较方法。
  3. Implementation preflight checklist 增加一项：逐条对照 §5.2 规则与 OLD 文件（若可访问），记录 delta。
- **修复风险**: 低（只需增加 fixture 或 Controller 验证声明）
- **严重程度**: 中

### R11-PR-BF-RR2-DS-F02 — "umbrella remediation plan" source lock label 不精确（低）

- **位置**: Plan §2.2 source lock table row 4（"umbrella remediation plan"）；§2.1 authority item 4
- **问题类型**: 不可直接实施（label 不匹配实际文件路径）
- **当前写法**: Plan §2.2 写 `umbrella remediation plan | 1269 | 30c27562...a838`。§2.1 item 4 写
  "umbrella remediation plan §7、§18、§20—22"。其余 source lock rows 使用 exact path（如
  `dayu/fins/upload_batch.py`）或明确 group label（如 `root / dayu/ / Fins / tests README`）。
- **反例/失败场景**: Implementation Agent 做 preflight source lock 验证，在 repo 中搜索名为
  "umbrella remediation plan" 的文件，找不到。需要额外推理或询问才能定位到
  `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`。
- **为什么有问题**: Source lock table 承担 implementation preflight 的精确文件路由功能。先用描述性 label
  再用 exact path 是同一文件两类表示，容易导致 preflight 路由错误。这与已被修复的 `R11-PR-BF-FR-DS-F02`
  （FMP resolver 从 "CURRENT FMP resolver" 改为 exact path）是同一类问题。
- **直接证据**:
  - `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`: 1269 lines, SHA `30c27562...a838`（匹配 lock）
  - `docs/host/wu-semantic-ownership-01-umbrella-plan.md`: 826 lines, SHA `70863a24...b19e3`（不匹配，不同的文件）
  - Plan §2.2 其余 production source rows 均为 exact path
- **影响**: Preflight 路由歧义，低概率但可避免
- **建议改法和验证点**: 将 label 改为 exact path
  `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`，保持 lines/hash 不变。同时将 §2.1
  authority item 4 中的引用也改为该 exact path。
- **修复风险**: 低
- **严重程度**: 低

### R11-PR-BF-RR2-DS-F03 — §5.2 rule 4 Q4 歧义：匹配范围未明确（低）

- **位置**: Plan §5.2 rule 4
- **问题类型**: 切片过粗 / open question 未收敛
- **当前写法**: "Q4 含'季报'保留 Q4，否则为 FY"
- **反例/失败场景**: implementation agent 对"含"的解释可能不同：
  - 仅文件名 stem 包含"季报"？（如 `2024Q4_季报.pdf`）
  - 完整文件名包含"季报"？（如 `2024Q4_季度报告.pdf` 不匹配，因为"季度报告"≠"季报"）
  - 路径任意位置包含"季报"？（如 parent dir 名为 `季报目录`）

  此外，如果文件名包含 Q4 但实际内容是年报（如 `2024Q4_年报.pdf`），rule 说"含'季报'保留 Q4"但这里文件名
  "年报"≠"季报"，应该归 FY。这种行为是否正确取决于"含"的匹配范围与优先级。
- **为什么有问题**: 财经报告的文件命名实践中，"季报"与"季度报告"并存，"年报"与"年度报告"并存。rule 4 只提到
  "季报"一个字面量，未说明是否需要处理"季度报告"等变体，也未说明 Q4+年报 组合的优先级。
- **直接证据**: Plan §5.2 rule 4 原文
- **影响**: Implementation agent 可能对 Q4 edge case 做不同实现选择，导致 Controller review 时需要返工
- **建议改法和验证点**: 明确：
  1. 匹配范围（仅文件名 stem？完整 filename？路径？）
  2. 匹配方式（exact substring "季报"？还是 pattern `季.*报`？）
  3. 如果同时匹配 Q4 marker 和 FY marker（如 "年度报告"），优先级规则
  4. 补充测试用例覆盖这些 edge case
- **修复风险**: 低（plan-only clarification）
- **严重程度**: 低

## 8. Open questions

1. **OLD 文件可达性**: Controller 是否有可访问的 OLD 文件副本？如果有，是否应该 check in 为 read-only fixture？
   见 R11-PR-BF-RR2-DS-F01。

2. **§5.2 rule 8 priority level 5**: "演示/新闻/简报/摘要" 被归为最低 priority 5。如果这些是
   EARNINGS_PRESENTATION 的弱匹配变体，它们应该先被 material routing（rule 6）捕获。如果没被捕获
   而进入 filing priority，优先级为最低似乎合理。但需确认"演示"（presentation 中文）与 material routing
   中的 "Presentation" 英文是否在 OLD 中以不同 language 同时出现。

3. **§5.2 rule 9 caps**: "FY 按年度降序最多 5"——这里的"年度降序"是按 fiscal_year 数值降序（2024 > 2023），
   没有歧义。但"periodic 只保留已识别到的最新 fiscal year"——如果 latest year 的 Q1 文件缺失但 Q2-H1 存在，
   是否仍然保留该 year 的全部识别到的 periodic 文件？这似乎是 yes（"已识别到的最新"），但 edge case 值得
   在 implementation 前澄清。

## 9. Residual risks

| Risk | 跟踪目标 | 缓解 |
|---|---|---|
| OLD 规则转录不完整 | Controller 需在 implementation 前确认 §5.2 完全覆盖 OLD 行为 | §2.1 item 7 指定 OLD 只作证据；建议增加 fixture 或 Controller verification statement |
| `upload_batch.py` 实质重写导致 scope 意外扩大 | R11-I1 implementation | Plan §5.2 规则详细明确；WP-A allowlist 限制在 `upload_batch.py` + test |
| Windows quote/escape 算法未经真实 runner 验证 | R11-I2 release gate | Plan 明确 Windows 可为 `PENDING_RELEASE_BLOCKER`；不允许提前标 closed |
| `dayu/cli/upload_script.py` 作为新增模块可能产生对 Service/runtime 的意外 import | R11-I1 implementation | Plan §8.3 item 1 的反向依赖 oracle 只覆盖 Fins production，应扩展到 renderer |

## 10. Final plan review conclusion

**Verdict: PASS-WITH-RISKS**

**Pass rationale**:
- 所有 5 个 prior findings 均独立验证为 CLOSED
- §2.2 source locks（除 OLD 文件不可达和 Controller control 预期 drift 外）全部精确匹配
- Two-slice state machine、sequential edit/safety stop、correction loop/combined revalidation 结构完整且无歧义
- pyright/coverage/security/deferred/Windows gates 均未弱化
- Producer-consumer contract mapping（§5.3 checklist）逐字段完整
- 3 个 new findings 均为 LOW-MEDIUM，非 blocker

**Risk acceptance required**:
- R11-PR-BF-RR2-DS-F01（中）：OLD 文件不可达，建议 Controller 确认 §5.2 转录完整性或提供 fixture
- R11-PR-BF-RR2-DS-F02（低）：umbrella remediation plan label 不精确
- R11-PR-BF-RR2-DS-F03（低）：§5.2 rule 4 Q4 歧义

**Blocker count: 0**。不建议阻止 plan 进入 implementation authorization。

## 11. Ledger

| Finding | Status |
|---|---|
| `R11-IMP-BF01` | CLOSED（独立验证） |
| `R11-PR-BF-RR-F01` | CLOSED（独立验证） |
| `R11-PR-BF-FR-DS-F01` | CLOSED（独立验证） |
| `R11-PR-BF-FR-DS-F02` | CLOSED / CONTROLLER-VALIDATED（独立验证） |
| `R11-PR-BF-FR-CV-F01` | CLOSED / CONTROLLER-VALIDATED（独立验证） |
| `R11-PR-BF-RR2-DS-F01` | NEW / MEDIUM / OLD files inaccessible |
| `R11-PR-BF-RR2-DS-F02` | NEW / LOW / umbrella remediation plan label imprecise |
| `R11-PR-BF-RR2-DS-F03` | NEW / LOW / §5.2 rule 4 Q4 ambiguity |

- accepted/open before re-review: 0
- new current material findings: 3
- blocker: 0
- actual accepted residual: 0
- Windows: `PENDING_RELEASE_BLOCKER`（未改变）

READY_FOR_CONTROLLER_R11_FINAL_PLAN_REREVIEW2_ADJUDICATION
