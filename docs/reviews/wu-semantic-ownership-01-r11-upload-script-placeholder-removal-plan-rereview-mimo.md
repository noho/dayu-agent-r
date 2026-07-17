# WU-SEMANTIC-OWNERSHIP-01 / R11 complete fixed-plan re-review — AgentMiMo（第一路）

## 1. Review metadata

- **reviewer**: AgentMiMo（第一路 complete fixed-plan re-review）
- **target**: `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- **target lock**: 773 lines / 61,810 bytes / SHA-256 `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`
- **baseline**: branch `phaseflow/host-issues-control`，HEAD `2b14b2fbc89654267e3d33daa2ae410ceff45e68`，staged tree empty
- **timestamp**: 20260717-222400（本机 `date +%Y%m%d-%H%M%S`）
- **scope**: 对 fixed plan 做完整 re-review，验证 R11-PR-F01—F06 全部关闭、rejected candidates 未被实施，并独立挑战 owner、三 slice 依赖、OLD typed classification、current CLI grammar/FMP-once、POSIX/Windows argv/publisher containment、placeholder/package/wheel/RECORD、真实 smoke、coverage/pyright/同版本 Ruff、Windows release blocker、security/deferred/no-touch 边界
- **authority order**: AGENTS.md → 设计真源 → Controller discussion Topic 7 → umbrella remediation plan → phaseflow umbrella optimization control → Controller control → CURRENT code/tests/README → OLD files

## 2. Source locks 验证

| Source | Plan claimed | Current HEAD | Match |
|---|---|---|---|
| `AGENTS.md` | 128 lines / `cb26618a...` | 128 lines | ✓ |
| `dayu/fins/upload_batch.py` | 376 lines / `6767d30c...` | 376 lines | ✓ |
| `dayu/cli/commands/fins.py` | 1057 lines / `0db8ff2d...` | 1057 lines | ✓ |
| `dayu/cli/arg_parsing.py` | 932 lines / `a0e25ad6...` | 932 lines | ✓ |
| `pyproject.toml` | 152 lines / `e076606f...` | 152 lines | ✓ |
| `requirements.txt` | 12 lines / `7e8c14d6...` | 12 lines | ✓ |
| Fixture `aapl-20240928.htm` | 1,503,780 bytes / `24a830a0...` | 1,503,780 bytes | ✓ |
| `.github/workflows/` | 不存在 | 不存在 | ✓ |
| Placeholder `dayu/web/` | 存在（2 `.py`） | 存在（2 `.py`） | ✓ |
| Placeholder `dayu/wechat/` | 存在（2 `.py`） | 存在（2 `.py`） | ✓ |
| Placeholder `dayu/render/` | 存在（2 `.py`） | 存在（2 `.py`） | ✓ |

Controller-owned `docs/host/issues-implementation-control.md` 未被 plan 覆盖。Staged tree 为空。

## 3. Assumptions tested

1. Fins batch owner 未拥有完整 OLD-aligned domain facts — **已验证**：当前 `upload_batch.py` 只有 generic `entries`/path-only skips。
2. CLI 输出 JSON argv protocol 而非 executable script — **已验证**：`fins.py:70` 定义 `_UPLOAD_BATCH_SCHEMA_VERSION = 1`。
3. CLI action 默认为 `create` 而非 `auto` — **已验证**：`arg_parsing.py:904` `default="create"`。
4. placeholder packages 仍存在 — **已验证**：三个目录各有 tracked `.py` 文件。
5. `.github/workflows/` 不存在 — **已验证**：目录不存在。
6. `FmpCompanyInfoResolver` 存在且可消费 — **已验证**：`dayu/fins/resolver/fmp_company_info.py` 存在。
7. `requirements.txt` 仍消费 `[web]` extra — **已验证**：`requirements.txt:12` `-e .[test,dev,browser,web]`。
8. 两个 `"dayu.web"` negative boundary sentinel 存在 — **已验证**：`tests/tools/web/test_web_tools_provider.py:760` 与 `test_diagnose_web_access.py:49`。
9. `pyproject.toml` 仍含 `dayu.render` package-data mapping — **已验证**：当前代码包含该映射。
10. Fixture 可读且 SHA-256 匹配 — **已验证**：1,503,780 bytes。

## 4. R11-PR-F01—F06 逐项关闭证明

### R11-PR-F01 — S2 发现 S1 owner contract gap 的回返路径

**状态：已关闭。**

- **Plan §5.3**（lines 291—309）新增逐字段 S1→S2 consumer mapping checklist，覆盖 entry type→command、ticker/aliases→CSV、action enum→省略/flag、file→`--files`、fiscal/amended/dates/company/overwrite/material-only fields 的 optional-to-flag 规则、skipped 只进 human summary。
- **Plan §9.1**（lines 705—711）新增唯一回返路径：S2 发现 §5.3 checklist gap 时立即 stop，Controller 只授权 S1 owner targeted fix，重跑 S1 checkpoint 与 S1+S2 cumulative validation。禁止 adapter/fixture fallback、新 sub-WU、新 slice 或中间 commit。
- **直接证据**：Controller adjudication lines 18—27 明确要求此修复。Fix evidence lines 41—58 记录 before/after。
- **独立验证**：checklist 每个字段与 §6.2 的 current grammar flag 一一对应，不留消费者推断空间。

### R11-PR-F02 — symlink 拒绝范围停在 workspace/source boundary

**状态：已关闭。**

- **Plan §5.2.1**（lines 229—238）：source root lexical path 自身是 symlink 时拒绝；lexical root 与 resolved root 分别形成扫描 boundary；root 到 candidate 的每个内部组件含 symlink 就拒绝；root 外部祖先不检查。
- **Plan §6.3**（lines 383—389）：output target 同时满足 lexical/resolved workspace containment；root self、root 内 output component/target symlink 拒绝；`/tmp -> /private/tmp` 等 external ancestor 允许。
- **测试矩阵**：§5.3 覆盖 external-ancestor allowed、root-self rejected、internal component/candidate rejected、escape rejected。§6.6 同理。
- **直接证据**：Controller adjudication lines 29—38 给出 `/tmp` 反例。Fix evidence lines 60—78 记录修复。
- **独立验证**：当前 plan 的 containment 规则在安全性和可用性之间取得正确平衡——拒绝所有 root 内 symlink 是安全的，允许 root 外 OS ancestor 是必要的。

### R11-PR-F03 — `--overwrite` / `--infer` grammar 与 publisher 消歧

**状态：已关闭。**

- **`--infer`**（§6.2.4，lines 355—359）：`action="store_true"`、`default=False`；help 自解释 FMP 补全与 `FMP_API_KEY`；未传零 resolver/env 访问；传入只调一次 existing `FmpCompanyInfoResolver.resolve_company_info(canonical)` public method。
- **`--overwrite`**（§6.2.6，lines 365—369）：`action="store_true"`、`default=False`；help 明确 storage overwrite 且不控制脚本替换；只传播到每条 direct upload 的 storage overwrite fact。
- **Publisher**（§6.3，lines 387—389）：对 valid contained non-symlink existing regular target 始终原子替换，与 `--overwrite` true/false 无关；不新增 `--force-output`。
- **直接证据**：Controller adjudication lines 40—48。Fix evidence lines 80—97。
- **独立验证**：两个 flag 的 argparse grammar、help text、default、propagation 和 publisher independence 均已在 plan 中锁定。§6.6 tests 覆盖两者 parser default false / explicit true。

### R11-PR-F04 — wheel extracted names 与 RECORD exact-zero oracle

**状态：已关闭。**

- **Plan §7.3**（lines 552—580）：Python exact-one assertion 选择 wheel/dist-info；extracted tree 对 `dayu/web`、`dayu/wechat`、`dayu/render` exact prefix 命中必须为零；CSV 解析 RECORD 第一列做相同 assertion；四个 Python negative oracle exit 0 打印 `...: 0`；命中或 wheel/dist-info 数量不是一 assertion 非零。
- **METADATA**：无 `Provides-Extra: web`、无 Streamlit requirement。
- **entry_points.txt**：只含真实 scripts。
- **Archive**：零 placeholder path。
- **RECORD**：零 placeholder path。
- **直接证据**：Controller adjudication lines 50—58。Fix evidence lines 99—117。
- **独立验证**：四个 oracle（METADATA、entry_points、extracted paths、RECORD）覆盖 wheel 内容的所有维度。Python exact-one selection 避免 shell wildcard 歧义。

### R11-PR-F05 — POSIX real smoke fixture source lock

**状态：已关闭。**

- **Fixture**：`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`，1,503,780 bytes。
- **Plan §6.6**（lines 452—460）：只读复制到 `workspace/tmp/r11-posix-real/source/` 下两个 OLD-recognizable 名称；不修改 tracked fixture；不从网络下载。
- **直接证据**：Controller adjudication lines 60—67。Fix evidence lines 119—136。
- **独立验证**：本 re-review 直接验证 fixture 存在且大小匹配。两个目标名称（`2024FY_AAPL_Annual_Report.htm`、`2024FY_AAPL_Earnings_Call_Transcript.htm`）按 §5 OLD 规则直接识别为 filing/material。

### R11-PR-F06 — zero-filing call cap 与 Ruff version oracle

**状态：已关闭。**

- **Zero-filing cap**（§5.2.10，lines 256—258）：filtered recognized filing count 为 `0` 时 call cap 也为 `0`，所有 `EARNINGS_CALL` candidates 进入带 cap reason 的 typed skipped，不得 minimum-one。
- **Owner test**（§5.3，lines 275—280）：覆盖 zero recognized filings 时全部 call candidates typed skipped。
- **Ruff version oracle**（§8.1，lines 591—617）：Controller 锁 baseline 时记录 `python -m ruff --version` verbatim；implementation/aggregate 在 delta 前逐字比较；version drift stop/relock。
- **直接证据**：Controller adjudication lines 69—76。Fix evidence lines 138—154。
- **独立验证**：Ruff 版本一致性检查是防御 baseline delta 假阳性的正确机制。Zero-filing cap 是 batch plan 的合理 empty-state 行为。

## 5. Rejected candidates 独立验证

### 旧 create default 兼容

**未实施。** Plan §6.2.2（lines 349—351）锁三个 upload parser default 为 `auto`。`BATCH_UPLOAD_ACTION_CHOICES` 为 `auto|create|update`，不含 `delete`。Controller discussion Topic 7.1 裁决 auto 为产品 default。无兼容分支。

### `list2cmdline` / fallback

**未实施。** Plan §6.5（lines 414—427）明确"禁止 compat/fallback/双算法/platform test shim"。Controller discussion 与 adjudication 拒绝 `list2cmdline` 作为 batch owner、安全证明或 fallback。Windows algorithm 保留给真实 `cmd.exe` evidence-driven 反证。

### 删除 OLD auto-recursion

**未实施。** Plan §5.2.2（lines 234—236）保留 structured auto-recursion 作为已接受 OLD-aligned workflow 规则。Controller adjudication 拒绝删除请求。

### 预猜 Windows algorithm

**未实施。** Plan §6.5（lines 414—427）明确"具体 quote/escape 算法不在无 Windows evidence 的 plan 中臆定"。Controller adjudication 拒绝预设候选算法家族或 iteration magic。

### cross-platform `--platform` flag

**未实施。** Plan §6.3（lines 379—382）由实际生成 OS 决定格式。Controller adjudication 拒绝新增 `--platform`。

### internal HTTP hop contract

**未实施。** Plan §6.2.4（lines 355—359）约束一次 existing public method call，明确不治理内部 HTTP hop。Fix evidence lines 159—163 确认。

### raw enum UI

**未实施。** Plan §5.1（lines 213—223）使用 frozen typed models with business-readable reason。§6.2.7（lines 371—373）以 typed entry 投影为 current command flags。Controller discussion Topic 7 裁决删除 JSON argv protocol。

## 6. 独立攻击面挑战

### 6.1 Owner 唯一性

| Semantic fact | Plan owner | 验证 |
|---|---|---|
| Upload suffix allowlist | 既有 `FINS_UPLOAD_FILE_SUFFIXES` | ✓ 复用，不复制 |
| 文件发现/递归/containment | `dayu.fins.upload_batch` | ✓ CLI 只收到 typed facts |
| 财期/material routing/priority/dedup/caps | `dayu.fins.upload_batch` | ✓ CLI 机械投影 |
| Canonical ticker + aliases | CLI input boundary + 既有 normalization | ✓ |
| FMP response parse | 既有 `FmpCompanyInfoResolver` | ✓ CLI 只调一次 |
| Plan entry → argv 投影 | `fins.py` 单一 builder | ✓ renderer 不判 command kind |
| POSIX/Windows quoting | `upload_script.py` 平台 renderer | ✓ builder/test 不 replace |
| Output containment/atomic publish | `upload_script.py` publisher | ✓ CLI 只传 intent |
| Placeholder surface | `pyproject.toml` + build artifact | ✓ |

无 owner 重叠或泄漏。

### 6.2 三 slice 依赖

- **S1→S2**：typed plan → current-grammar builder。§5.3 checklist 冻结 producer contract，§9.1 唯一回返路径。
- **S2→S3**：renderer/publisher → packaging/README。§7.1 的 README 更新依赖 S2 的 user-facing grammar。
- **无反向依赖**：S3 不修改 S1/S2 production code；S2 不修改 S1 owner。
- **每个 checkpoint 重跑 cumulative**（§9.1 lines 709—711）。

依赖顺序正确，无过度耦合。

### 6.3 OLD typed classification

- §5.2.4：fiscal year 用首个 `20YY`，period 支持 OLD patterns（Q1..Q4、1Q..4Q、中文、H1、FY 等）。先看文件名，不足时只从直接 structured parent 补齐。
- §5.2.6：material routing 按 OLD 表首个命中。
- §5.2.7：material name 按 OLD 规则从 stem 派生。
- §5.2.8—10：priority/dedup/caps 均来自 OLD。
- §5.2.5：explicit `--fiscal-year`/`--fiscal-period` 逐字段覆盖推断值。

OLD 规则映射完整，无未覆盖的分类场景。

### 6.4 Current CLI grammar / FMP-once

- `upload_filing` fields（§6.2.1）：ticker/action/files/fiscal-year/fiscal-period/amended/filing-date/report-date/company-name/aliases/overwrite。与当前 `arg_parsing.py` 的 `_register_upload_filing_command` 一致。
- `upload_material` 额外字段：`--forms`、`--material-name`、可选 `--document-id`/`--internal-document-id`。Batch entry 不臆造 ID。
- FMP-once（§6.2.4）：一次 `FmpCompanyInfoResolver.resolve_company_info(canonical)` public method call。不承诺 HTTP hop。
- Ticker CSV（§6.2.3）：首项 strict `normalize_ticker` → canonical，后续 alias trim/dedup。

Grammar 锁定完整，FMP 边界清晰。

### 6.5 POSIX/Windows argv / publisher containment

**POSIX**：
- Header：`#!/usr/bin/env sh`、`set -eu`（§6.4）。
- `shlex.quote`/`shlex.join` 编码（§6.4）。
- `$@` 安全追加（§6.4）。
- 真实 `/bin/sh` recorder + real upload smoke（§6.6）。

**Windows**：
- `@echo off`、`chcp 65001 >nul`、`setlocal DisableDelayedExpansion`（§6.5）。
- Outcome-driven：typed argv → batch file → cmd.exe → Python argv == original（§6.5）。
- 不使用 `list2cmdline`、无 fallback（§6.5）。
- 真实 `cmd.exe` recorder + CLI grammar smoke（§7.2）。
- Algorithm 保留给真实 runner evidence（§6.5）——这是 Controller 裁决后的有意设计。

**Publisher**：
- Lexical + resolved containment（§6.3）。
- Root self / root 内 component symlink rejected（§6.3）。
- External ancestor symlink allowed（§6.3）。
- Same-directory atomic replace（§6.3）。
- POSIX `0o755` mode；Windows 不宣称 POSIX mode（§6.3）。

### 6.6 Placeholder / package / wheel / RECORD

- §4 closed allowlist 明确列出删除/新增/修改的所有文件。
- §7.1 要求从 `[project.scripts]` 删除 `dayu-web`/`dayu-wechat`/`dayu-render`；删除 web extra 与 `dayu.render` package-data。
- §7.3 wheel smoke 覆盖 METADATA、entry_points、extracted paths、RECORD 四个维度。
- `requirements.txt` 删除 `[web]` 消费（§7.1.2）。
- 保留 inert constraints/lock pins（§2.4）。

### 6.7 真实 smoke

| Smoke | 位置 | 内容 |
|---|---|---|
| S1 filesystem | §5.3 | 真实层级 + 公开 batch-plan API → typed 三分结果 |
| POSIX recorder | §6.6 | Python recorder + `/bin/sh` → exact JSONL argv |
| POSIX real upload | §6.6 | 复制 fixture → `python -m dayu.cli` → temp storage exit 0 |
| Windows recorder | §7.2 | `cmd.exe` recorder + `.cmd` → exact JSONL argv |
| Windows CLI grammar | §7.2 | production builder → `.cmd` → `cmd.exe /d /c` → terminal success |
| Wheel | §7.3 | build → extract → install → help → importability → four oracles |

每个 smoke 使用真实 runtime，不 mock 核心路径。

### 6.8 Coverage / pyright / 同版本 Ruff

- **Coverage**（§8.2）：per-file line coverage `>=80%`，不使用 `--branch`。四个 changed production files。
- **pyright**（§8.1）：`python -m pyright dayu/ tests/ utils/` 全量。
- **Ruff**（§8.1）：scoped 零错误；full baseline delta 逐字比较；version oracle 在 delta 前匹配；drift → stop/relock。
- **diffcheck**（§8.1）：`git diff --check` from baseline。
- **Tests**（§8.1）：focused、full related、full 三级。

### 6.9 Windows release blocker

- Plan §7.2（lines 547—550）：本地 branch 未发布前无法得到 GitHub-hosted run。accepted implementation 可标 `PENDING_RELEASE_BLOCKER`，不得标 closed。
- Plan §9.4（lines 742—756）：umbrella aggregate acceptance / draft PR / final closeout 必须等真实 GitHub run。
- GitHub repository `noho/dayu-agent-r` Actions workflow list 为空，无现存 Windows runner。
- 最小 workflow（§7.2）：`windows-latest`、Python 3.11、`workflow_dispatch` + `pull_request.paths`、真实 test commands、artifact upload。

Windows gate 处理正确：implementation 不被阻塞，但 release 必须等 evidence。

### 6.10 Security / deferred / no-touch 边界

**Security 保留项**（§8.3）：
- Source/output lexical+resolved containment。
- External-ancestor symlink allowed；root self + root 内 component rejected。
- Same-dir atomic replace。
- POSIX executable mode；Windows delayed expansion off。
- argv injection marker 不存在。
- Secret non-persistence（脚本/summary/artifact 无 API key/provider URL/exception cause）。

**Deferred / no-touch**（§3.3）：
- Issue 142/151/175/177/178。
- R12 `init`。
- 真实 Web/WeChat/render。
- Topic 8 Engine 240-char / Topic 9 unified auth。
- `dayu/service/**`、`dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、storage schema、FMP resolver、ticker normalizer、design docs、constraints/locks、Controller control。

**Scan matrix**（§8.3）覆盖：schema residual、placeholder surface、production danger（`list2cmdline`/`shell=True`/`EnableDelayedExpansion`）、artifact secret/network、deferred diff、allowlist exact match、README trigger。

## 7. Plan code-generation-ready 评估

- §5 的 typed models、classification rules、tests/smoke 逐条精确，implementation agent 可直接编码。
- §6 的 current grammar locks、argv builder、renderer contracts、publisher、tests/smoke 逐条精确。
- §7 的 packaging deletion、wheel smoke、README edits、Windows workflow 均有 exact commands。
- §8 的 validation commands 可直接复制执行。
- §9 的 state machine、aggregate gate、commit gate 逐步骤明确。
- 唯一有意留白是 Windows quoting algorithm（§6.5），这是 Controller 裁决后的 evidence-driven 设计，不是 plan gap。

## 8. Findings

**无 material finding。**

完整 re-review 后，六项 accepted findings 均已在 plan 文本层正确闭合。Rejected candidates 均未被实施。Owner 边界清晰，三 slice 依赖正确，OLD 规则映射完整，CLI grammar 锁定，安全边界完整，validation gates 可执行。Windows quoting algorithm 的 evidence-driven 策略是 Controller 裁决后的有意设计，不构成 plan gap。

## 9. Open questions

无。

## 10. Residual risks

| Risk | Severity | Owner | Destination |
|---|---|---|---|
| Windows quoting algorithm 需真实 `cmd.exe` evidence 收敛 | 高 | R11-S2 implementation | Windows release gate |
| `.venv` 中 setuptools/wheel 版本满足 build 要求 | 低 | implementation pre-check | §7.3 wheel smoke |

两个 residual risk 均已在 plan 中有明确处理路径：Windows 通过 evidence-driven 反证 + release blocker gate；build deps 通过 pre-check + wheel smoke 验证。

## 11. Final plan review conclusion

**Verdict: PASS**

Fixed plan 在完整 re-review 后无 material finding。R11-PR-F01—F06 全部正确关闭；Controller rejected candidates 均未被实施；owner、三 slice 依赖、OLD classification、current CLI grammar/FMP-once、POSIX/Windows argv/publisher containment、placeholder/package/wheel/RECORD、真实 smoke、coverage/pyright/同版本 Ruff、Windows release blocker、security/deferred/no-touch 边界均经独立验证。

---

**Reviewer**: AgentMiMo
**Review timestamp**: 20260717-222400
**Reviewed artifact**: `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
**Reviewed artifact SHA-256**: `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`
**Review artifact line count**: 306
**Review artifact SHA-256**: 由 Controller 在 artifact 冻结后独立锁定
**Workspace status**: `git diff --cached --name-only` empty；`docs/host/issues-implementation-control.md` 是 Controller-owned dirty file，未被覆盖
**Staged status**: empty

READY_FOR_CONTROLLER_ADJUDICATION
