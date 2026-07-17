# WU-SEMANTIC-OWNERSHIP-01 / R11 final plan boundary re-review（MiMo route）

## 1. Gate、scope 与 verdict

- 时间：`2026-07-18`。
- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- gate：R11 amended-plan second complete re-review；不是新 WU、issue 或 feature，不授权 implementation。
- reviewed target：886 lines / 74,523 bytes / SHA-256
  `c3c0616f7ec90cb8e62f68bf219e43b053a07db320c3b169f70159855ce1430c`。
- verdict：**PASS / finding 0 / blocker 0**。
- `R11-IMP-BF01`：**CLOSED**。
- `R11-PR-BF-RR-F01`：**CLOSED**（wording fix 已通过 Controller validation，本轮确认最终 closure）。
- actual accepted residual：`0`。
- Windows gate：仍为 `PENDING_RELEASE_BLOCKER`，不因本轮 re-review 改变。
- next gate：Controller adjudication of this re-review。
- 本 artifact 不授权 implementation、stage、commit、push、PR 或 R12。

## 2. 输入与完整读取证明

本 re-review 完整读取了最终 886 行 plan，未只审 delta：

| Artifact | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| 最终 plan | 886 | 74,523 | `c3c0616f7ec90cb8e62f68bf219e43b053a07db320c3b169f70159855ce1430c` |
| Controller adjudication（prior round） | 75 | 4,885 | `9fceb2f83239fdf7afe804e39730cecd9d95224527ed96fe129b4011ea8d8426` |
| Codex fix evidence | 158 | 10,833 | `e3d1d0f8e01525f95cc1ccab2f149fa8aae9b41cbd0ec00faf070d1f49a369e7` |
| Controller validation | 83 | 5,877 | `36a7b3a04c847bb3f7e2cafd8a8f7bf71c8d3a43c5e38b71e40b72bf30a2a4b3` |

按 plan authority order 核对：

| Authority source | 验证结果 |
|---|---|
| AGENTS.md（128 lines / SHA-256 `cb26618a...`） | ✅ 行数与 hash 精确匹配 |
| docs/fins/design.md §10 | ✅ 存在，Fins typed batch plan owner 边界与 plan 一致 |
| docs/ui/design.md §1—2 | ✅ 存在，placeholder lifecycle 与 `upload_filings_from` Fins/CLI split 与 plan 一致 |
| Controller discussion Topic 7 final adjudication（731 lines） | ✅ 7.1/7.2/7.3 与 plan scope 一致 |
| umbrella remediation plan / optimization control | ✅ 存在，plan §2.4 mapping 正确 |
| CURRENT `dayu/fins/upload_batch.py`（376 lines / SHA-256 `6767d30c...`） | ✅ 行数与 hash 精确匹配 |
| CURRENT `dayu/cli/commands/fins.py`（1057 lines / SHA-256 `0db8ff2d...`） | ✅ 行数与 hash 精确匹配 |
| CURRENT `pyproject.toml`（152 lines / SHA-256 `e076606f...`） | ✅ 行数与 hash 精确匹配 |
| R10 completion baseline commit `2b14b2fb` | ✅ git log 确认 |
| accepted-plan commit `f7b452f9` | ✅ git log 确认 |
| staged tree | ✅ `git diff --cached --name-only` 为空 |

## 3. R11-IMP-BF01 closure proof

`R11-IMP-BF01` 仍 **CLOSED**。独立证明：

1. plan §9.1 状态机（lines 773-814）精确只有两个 implementation slices：
   `R11-I1 atomic Fins+CLI cutover -> R11-I2 packaging/README/Windows gate`。
2. §4（lines 196-209）将 cumulative allowlist 分配给两个 slices，不以 work package 为由缩窄或扩张。
3. §5.1（lines 211-231）明确 WP-A 与 WP-B 共用 §4 的 R11-I1 merged allowlist，WP-A 不是独立 slice。
4. §6.1（lines 365-378）明确 WP-B 与 WP-A 共用同一 allowlist，"本列表不是第二个 slice"。
5. §9.1 state machine diagram 仅有两个 checkpoint node：`Controller R11-I1 atomic checkpoint` 和 `Controller R11-I2 checkpoint`。
6. 无 producer-only checkpoint、producer-only commit、producer-only review、producer-only handoff、producer-only acceptance 或 producer-only stage。
7. §10 checklist（lines 867-872）确认 "精确两个 dependency-ordered slices"。

旧三-slice 扫描（`R11-S1|S2|S3|S1 checkpoint|S2 checkpoint|S3 checkpoint|三[个份] slice`）零命中。

**结论**：原 Fins producer 与 CLI consumer/renderer 已合并为 R11-I1 atomic cutover，原 packaging 为 R11-I2；两个 slices 之间无 producer-only gate truth。闭合成立。

## 4. R11-PR-BF-RR-F01 closure proof

`R11-PR-BF-RR-F01` 已 **CLOSED**。独立证明：

### 4.1 五项 Controller requirement 逐项验证

| Controller §4 requirement | Plan closure evidence |
|---|---|
| 同一 uninterrupted Agent task 可顺序编辑 I1 多文件；不要求跨文件事务原子写 | §5.1 line 223-224: "实现 Agent 可在同一 uninterrupted task 内顺序编辑 `R11-I1` 多个文件；这里的 atomic cutover 只定义 gate truth，不要求编辑工具提供跨文件事务原子写" |
| WP-A/WP-B 全部 coordinated edits 完成前不得 validation 或 gate transition | §5.1 lines 227-229, §5.3 lines 303-304, §8.1 lines 647-651, §9.1 lines 780-782, 793-797 均逐项禁止运行/宣称 tests/pyright/coverage/Ruff/diff/diffcheck/scans validation，禁止 checkpoint/acceptance/stage/commit/handoff/review/next-slice transition |
| transient inconsistency 不是合法 intermediate tree 或 pass/failure baseline；不得 compatibility seam；首次 validation 仅在全部 edits 后 | §5.1 line 226, §5.3 line 303, §8.1 line 649, §9.1 line 781 均明确区分 edit state 与 gate truth；§5.1 line 229, §8.1 line 651, §9.1 line 797 锁定首次 validation 时点 |
| material preflight 在 mutation 前；真实 blocker 仍安全 stop | §5.1 lines 222, 230-231, §5.3 lines 355-358, §8.1 lines 653-655, §9.1 lines 801-804 均要求 mutation 前完成 material preflight；edit-time blocker 必须 stop，当前 diff 只作 failed working evidence |
| Fins correction loop、combined revalidation、full pyright 0 与其它 gates 保留 | §5.3 lines 344-348, 359-361, §8.1 lines 656-658, 662, 687-693 保留 correction loop + combined revalidation + full pyright `0 errors` + Ruff 0.15.11 baseline |

### 4.2 一致性扫描

| Scan | Result |
|---|---|
| `不可停\|不得停\|不能停\|no-stop\|无 broken tree\|之间没有.*stop\|之间无.*stop` | **零命中** |
| `transactional editor\|rollback framework\|compat layer\|third slice\|中间 commit` | **零命中**（line 422 的 "第三种 body command" 是 "a third kind of command"，非 third slice） |
| `R11-S[123]\|S1.*->.*S2\|三.*slice\|S[123] checkpoint` | **零命中** |
| sequential edit + transient inconsistency + failed working evidence + 首次 validation + combined revalidation + full pyright 约束 | **正向命中**，§5.1/§5.3/§8.1/§9.1/§10 均存在 |

**结论**：wording fix 已在权威 plan 内形成 closure，不依赖下游 artifact 补偿。闭合成立。

## 5. 验证 gates 未弱化证明

| Gate | Evidence |
|---|---|
| Fins correction loop | §5.3 lines 344-348: consumer gap 只在 Fins owner 两路径做 targeted correction；§9.1 lines 806-810 同一 |
| combined revalidation | §5.3 lines 359-361: correction 后 combined revalidation；§8.1 lines 656-658: "correction 后必须 combined revalidation，不能只复用此前结果" |
| full pyright `0 errors` | §8.1 line 662: "任何时点都不得放宽当前 full pyright `0 errors` 要求" |
| Ruff 0.15.11 baseline | §8.1 lines 687-693: version oracle + full baseline SHA-256 锁定，不允许放宽 |
| per-file coverage ≥80% | §8.2 lines 696-708: 逐文件读取 `summary.percent_covered >= 80.00` |
| security gates | §8.3 lines 710-767: path containment/symlink/atomic write/argv injection/secret non-persistence 全保留 |
| deferred/no-touch | §3.3 lines 133-143, §8.3 lines 763-764: Issue 142/151/175/177/178、R12、真实 Web/WeChat/render、Topic 8/9、统一 auth 均不进入 |
| Windows release gate | §7.2 lines 562-607, §9.4 lines 846-861: `PENDING_RELEASE_BLOCKER` 规则完整 |
| POSIX/Windows real smokes | §6.6 lines 481-527, §7.2 lines 586-601: `/bin/sh` recorder + real Service/Fins smoke, `cmd.exe` recorder + real CLI smoke |

**结论**：所有 validation gates 保持原强度，无弱化。

## 6. Plan code-generation-ready 证明

| 禁止方案 | Plan 状态 |
|---|---|
| transactional editor / 跨文件事务原子写 | 未引入；plan 明确 "不要求编辑工具提供跨文件事务原子写"（§5.1/§8.1/§9.1） |
| rollback framework | 未引入；safety stop 保留当前 diff 为 failed working evidence，不自动 rollback（§5.1/§5.3/§9.1） |
| compatibility layer / old-new dual surface / fallback / loose parsing | 未引入；§5.1 line 209, §5.3 line 347 明确禁止 |
| 第三 slice / 中间 commit / R12 | 未引入；精确两个 slices（§9.1 line 773）；不进入 R12（§3.3 line 136） |
| 统一 authorization | 未引入；§3.3 line 138: "Topic 9 不实现统一 authorization" |
| deferred Issue | 未引入；§3.3 明确不实现 Issue 142/151/175/177/178 |

**结论**：plan 保持 code-generation-ready，未引入任何禁止方案。

## 7. 新 material finding ledger

### 7.1 Adversarial 全文审查

对 886 行最终 plan 执行完整 adversarial 审查，逐节核对：

| Section | 审查结果 |
|---|---|
| §1 Gate / first-principles | ✅ gate 定义准确，动机四条直接 owner-side 证据与当前代码一致 |
| §2 Authority / source locks | ✅ 所有 source locks 行数与 SHA-256 通过独立验证 |
| §2.4 Umbrella mapping | ✅ 12 条 mandatory baseline mapping 与 umbrella plan 一致 |
| §3 Goal / success / forbidden | ✅ 9 条 success signals 覆盖完整，deferred/no-touch 边界正确 |
| §4 Semantic owner map / allowlist | ✅ 12 条 owner mapping 无重叠；cumulative allowlist 精确；two-slice 分配正确 |
| §5 WP-A Fins owner | ✅ typed models 完整；12 条 classification rules 逻辑自洽；validation/smoke/checkpoint 定义清晰 |
| §6 WP-B CLI/renderer | ✅ 8 条 grammar locks 覆盖完整；output path/safe publish/POSIX renderer/Windows outcome 定义清晰 |
| §6.5 Windows outcome | ✅ evidence-driven algorithm gate 保留；`list2cmdline`/fallback/shim 零残留 |
| §7 R11-I2 packaging | ✅ allowlist 精确；Windows workflow 最小 contract 完整；wheel smoke 覆盖 METADATA/entry_points/extracted/RECORD |
| §8 Validation / coverage / scans | ✅ sequencing 与 §5.1/§9.1 一致；per-file coverage；source/propagation/security/deferred scans 完整 |
| §9 State machine / gates | ✅ two-slice 状态机完整；aggregate gate/accepted commit/completion gate 定义清晰 |
| §10 Acceptance checklist | ✅ 12 条 checklist 覆盖全部关键 boundary |

### 7.2 Current code evidence 交叉验证

| Plan motivation claim | Current code evidence | Status |
|---|---|---|
| `upload_batch.py` 仅做 token 分类，返回 generic `entries` 与 path-only skip | 确认：376 行，无 OLD fiscal/material routing/skip reason | ✅ |
| `fins.py` 投影成 `{schema_version: 1, commands: [argv...]}`，`--output` 写 stdout | 确认：1057 行，存在 JSON schema 投影 | ✅ |
| `pyproject.toml` 发布 placeholder entrypoints | 确认：152 行，含 `dayu-web`/`dayu-wechat`/`dayu-render` scripts | ✅ |
| CLI 只允许 `create\|update\|delete`，缺 `auto` | 确认：`FILING_ACTION_CHOICES` 无 `auto` | ✅ |
| `requirements.txt` 消费 `[web]` extra | 确认：含 `-e .[test,dev,browser,web]` | ✅ |
| `dayu/README.md` 把 placeholder 写成稳定边界 | 确认：line 72 存在 placeholder "Stable Boundaries" 承诺 | ✅ |
| `.github/workflows/` 不存在 | 确认：目录不存在 | ✅ |
| 六个 placeholder package 文件存在且 tracked | 确认：`git ls-files` 列出全部六个 | ✅ |

### 7.3 Placeholder deletion completeness

plan §4 列出六个待删文件，与 `git ls-files` 精确匹配：

- `dayu/web/__init__.py`、`dayu/web/__main__.py`
- `dayu/wechat/__init__.py`、`dayu/wechat/main.py`
- `dayu/render/__init__.py`、`dayu/render/render.py`

`pyproject.toml` 删除项覆盖：`[project.scripts]` 中三个 entrypoints、`web` optional dependency、`dayu.render` package-data mapping。

`requirements.txt` 删除 `[web]` extra 消费。

§7.1 明确 "删除三个仅 placeholder package 的全部 tracked 文件"。无遗漏。

### 7.4 Negative boundary sentinel preservation

`tests/tools/web/test_web_tools_provider.py` 与 `tests/tools/web/test_diagnose_web_access.py` 中的 `"dayu.web"` 是负向 import-boundary sentinel，plan §2.4 和 §8.3 明确保留。它们不在 R11-I2 allowlist 内，不会被修改或删除。✅

### 7.5 Finding ledger

| Finding ID | Status | Description |
|---|---|---|
| `R11-IMP-BF01` | CLOSED | producer+consumer 合并为 R11-I1 atomic cutover；无 producer-only checkpoint |
| `R11-PR-BF-RR-F01` | CLOSED | sequential edit state vs gate truth wording 已在 plan 内修复并通过 Controller validation |
| **New findings** | **0** | 无新 material finding |

## 8. Residual / blocker

| Item | Status |
|---|---|
| actual accepted residual | `0` |
| blocker | `0` |
| Windows release gate | `PENDING_RELEASE_BLOCKER`（不因本轮 re-review 改变） |
| R12 | 未授权 |
| implementation | 未授权 |

## 9. Verdict

**PASS**。最终 886 行 plan 通过 complete adversarial re-review：

- `R11-IMP-BF01` 仍 CLOSED：精确两个 implementation slices，无 producer-only gate truth。
- `R11-PR-BF-RR-F01` 仍 CLOSED：sequential edit state vs gate truth wording fix 已在权威 plan 内一致完成。
- Fins correction loop、combined revalidation、full pyright `0 errors`、Ruff baseline、coverage、security、deferred、Windows gates 均未弱化。
- plan 保持 code-generation-ready：无 transactional editor、rollback framework、compat layer、第三 slice、中间 commit、R12/deferred Issue 或统一 authorization。
- adversarial 全文审查无新 material finding。
- 已裁决产品问题未重开。

READY_FOR_CONTROLLER_R11_PLAN_BOUNDARY_FINAL_REREVIEW_ADJUDICATION
