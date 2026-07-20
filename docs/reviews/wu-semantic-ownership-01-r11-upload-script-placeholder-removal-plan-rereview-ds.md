# WU-SEMANTIC-OWNERSHIP-01 / R11 complete fixed-plan re-review — AgentDS

## 1. Review metadata 与 target lock

- **reviewer**: AgentDS（第二路 complete fixed-plan re-review）
- **immutable target**: `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- **target lock**: 773 lines / 61,810 bytes / SHA-256 `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`
- **review posture**: constructively adversarial；本 review 是完整 fixed-plan 复审，不是 delta-only review
- **baseline**: branch `phaseflow/host-issues-control`，HEAD `2b14b2fbc89654267e3d33daa2ae410ceff45e68`，staged tree empty
- **authority order**: AGENTS.md → 设计真源 → Controller discussion Topic 7 → umbrella remediation plan → phaseflow umbrella optimization control → Controller control truth → CURRENT code/tests/README → OLD files
- **timestamp**: 2026-07-17T22:27:07+08:00
- **gate**: R11 dual complete fixed-plan re-review second path；不是新 WU/feature/issue
- **workspace 约束**: 只写本 review artifact；不得修改 plan、control、代码、测试、产品文档或其他 Agent artifact；不得 stage/commit/push/PR

## 2. Documents consulted

| Document | Lines | SHA-256 | Role |
|---|---|---|---|
| Fixed plan (immutable target) | 773 | `48bcfbaa...d025` | Review target |
| AGENTS.md | 128 | `cb26618a...c45e` | Authority #1 |
| Controller control doc (R11 rows) | — | `1906ce2f...f808` (working tree, read-only) | Current gate state |
| Umbrella optimization control | 302 | `6d924e91...1db` | Slice/review constraints |
| Controller discussion (Topic 7) | 731 | `cd26760d...33a` | Product decisions |
| Fins design §10 | 123 | `97033cf1...abdd` | Upload batch plan owner |
| Initial MiMo plan review | 289 | `b7eb5e1e...bf37` | Original reviewer findings |
| Initial DS plan review | 308 | `2e1c1847...9abd` | Original reviewer findings |
| Controller adjudication | 129 | `275c26e8...6229` | Accepted findings truth |
| AgentCodex fix evidence | 219 | `efb3eec7...cf40` | Fix implementation evidence |
| Controller fix validation | 92 | `773e4b83...c980` | Fix validation verdict |
| CURRENT `dayu/fins/upload_batch.py` | 376 | `6767d30c...6178` | Direct code evidence |
| CURRENT `dayu/cli/commands/fins.py` | 1057 | `0db8ff2d...95a6` | Direct code evidence |
| CURRENT `dayu/cli/arg_parsing.py` | 932 | `a0e25ad6...1c2c` | Direct code evidence |
| CURRENT `pyproject.toml` | 152 | `e076606f...6a25` | Placeholder surface |
| CURRENT `requirements.txt` | 12 | — | Placeholder dependency |
| CURRENT `dayu/fins/resolver/fmp_company_info.py` | ~394 | `c2abfbe0...46fa` | FMP resolver contract |
| CURRENT placeholder package files (6) | — | — | Deletion target |
| CURRENT `tests/cli/test_public_package_entrypoints.py` | 217 | — | Placeholder test surface |
| CURRENT `tests/tools/web/test_web_tools_provider.py` | — | — | Negative sentinel |
| CURRENT `tests/tools/web/test_diagnose_web_access.py` | — | — | Negative sentinel |
| Smoke fixture | 1,503,780 bytes | `24a830a0...ff6d6` | POSIX real smoke input |

## 3. Assumptions tested

1. Fixed plan 中 R11-PR-F01—F06 的修复文本切实闭合了 Controller adjudication 的每一项必修要求。
2. Plan 的 S1→S2 typed contract mapping checklist（§5.3）覆盖了所有 producer-consumer interface gap。
3. S2→S1 唯一 owner 回返路径（§9.1）不会导致 S2 adapter/renderer/fixture fallback 或 scope creep。
4. Symlink 拒绝边界（§5.2.1、§6.3）精确区分 root-self、root-internal component 与 external ancestor。
5. `--infer`/`--overwrite` 的 argparse 定义与 publisher 独立性在 plan 文本层无歧义。
6. Wheel archive/RECORD negative oracle 与 Python exact-one selection 对 placeholder 残留提供完整覆盖。
7. POSIX real smoke fixture 的锁定路径与实际 tracked file 一致。
8. Zero-filing call cap 与 Ruff version oracle 的 empty-state 与 drift-stop 规则可执行。
9. Controller rejected candidates（旧 create default、list2cmdline/fallback、删除 OLD auto-recursion、预猜 Windows algorithm、cross-platform platform flag、internal HTTP hop contract、raw enum UI）均未在 fixed plan 中被偷偷实施。
10. 三 slice 的 owner 边界、dependency order、allowlist 与 stop conditions 未被 fix 改变或弱化。

## 4. R11-PR-F01—F06 逐项闭合验证

### 4.1 R11-PR-F01 — S2 consumer mapping checklist 与 owner 回返路径

- **Controller adjudication 要求**: S1 checkpoint 增加 S2 consumer field/enum/optional-to-current-flag checklist；S2 发现 gap 时立即 stop，Controller 只授权 S1 owner targeted fix，随后重跑 S1+S2 cumulative validation；禁止 S2 adapter/renderer/fixture fallback。
- **Fixed plan 证据**:
  - §5.3（lines 294–309）：逐字段 checklist，覆盖 entry type→command、ticker/aliases→`--ticker` CSV、action enum、file→`--files`、fiscal/amended/dates/company/overwrite/material fields 的 optional-to-flag 规则，以及 skipped path/reason→human summary。
  - §9.1（lines 705–711）：唯一 owner 回返路径——S2 发现 typed fact/enum/optional ownership gap 时立即 stop 并提交 direct contract evidence；只有 Controller 可授权 S1 targeted fix；修复后从 S1 checkpoint 重新开始并重跑 S1+S2 cumulative validation；严禁 S2 fallback/重算/兼容 seam/新 sub-WU/slice/commit。
- **闭合判定**: **CLOSED**。Checklist 覆盖所有 typed field；回返路径精确限定 Controller-only、S1-only、cumulative revalidation 且禁止下游补偿。

### 4.2 R11-PR-F02 — symlink 拒绝范围停在 workspace/source boundary

- **Controller adjudication 要求**: 精确写出 lexical/resolved containment、root-self 与 root-inside component 检查；external-ancestor-symlink allowed；Fins source boundary 同样约束。
- **Fixed plan 证据**:
  - §5.2.1（lines 229–238）：source root 自身不是 symlink；lexical + resolved dual containment；internal component/candidate symlink 拒绝；不得向上扫描或拒绝 root 外部祖先。
  - §5.3（lines 275–280）：owner tests 覆盖 external-ancestor allowed、root-self rejected、internal component/candidate rejected、escape rejected。
  - §6.3（lines 383–389）：output target lexical+resolved containment；workspace root self symlink 拒绝；root 内 output component/target symlink 拒绝；`/tmp -> /private/tmp` 类 external ancestor 必须允许。
  - §6.6（lines 441–446）：test matrix 覆盖全部 symlink 场景。
  - §8.3（lines 682–685）：security verification 覆盖 source/output lexical+resolved containment、external-ancestor symlink allowed、root-self 与 root 内 symlink rejected。
- **闭合判定**: **CLOSED**。Symlink 策略精确限于 workspace/source boundary；`/tmp` 反例被明确允许。

### 4.3 R11-PR-F03 — `--overwrite` / `--infer` grammar 与 publisher 语义消歧

- **Controller adjudication 要求**: 两个 flag 都是 `store_true`/`default=False`；help text 自解释；overwrite 只传播为 storage fact 不控制 publisher replacement；infer 未传时零 env/resolver 访问。
- **Fixed plan 证据**:
  - §6.2.4（lines 355–359）：`--infer` 精确为 `action="store_true"`、`default=False`；help 自解释为 "使用 FMP 公司信息补全公司名称与 ticker aliases（需要 `FMP_API_KEY`）"；未传时零 resolver/env 访问；传入时只调用一次 existing resolver public method。
  - §6.2.6（lines 365–369）：`--overwrite` 精确为 `action="store_true"`、`default=False`；help 自解释为 "允许每条生成的上传命令覆盖已有存储文档；不控制脚本文件替换"。
  - §6.3（lines 383–389）：publisher existing-target atomic replacement 与 direct upload `--overwrite` 的 true/false 无关；publisher 始终按自身 contract 独立 replace。
  - §6.6（lines 441–446）：test matrix 覆盖 help/parser/propagation/replacement 全部 contract。
- **闭合判定**: **CLOSED**。两个 flag 的 argparse 定义、help contract、ownership boundary 与 publisher 独立性全部锁定。

### 4.4 R11-PR-F04 — wheel extracted names 与 RECORD exact-zero oracle

- **Controller adjudication 要求**: extracted wheel/zip name 与 RECORD 执行同一 placeholder-path zero assertion；明确 expected exit/output；不依赖 shell wildcard；不治理 untracked `__pycache__` 或合法 `top_level.txt=dayu`。
- **Fixed plan 证据**:
  - §7.3（lines 552–580）：Python exact-one wheel selection（`tuple(Path(...).glob('dayu_agent-*.whl'))` + `assert len(wheels) == 1`）；extracted archive relative path prefix zero assertion for `dayu/web`、`dayu/wechat`、`dayu/render`；CSV 解析 RECORD 第一列并执行相同 exact prefix assertion；四个 Python negative oracle 成功必须 exit 0，stdout 依次精确包含 `wheel METADATA placeholder contracts: 0`、`wheel placeholder entry points: 0`、`wheel extracted placeholder paths: 0`、`wheel RECORD placeholder paths: 0`；命中或 wheel/dist-info 数量不是一时 assertion 非零并打印 exact hits。
- **闭合判定**: **CLOSED**。RECORD 以 CSV 精确解析；extracted archive 以 relative path prefix 覆盖；四个 oracle 均锁定 exact output；不依赖 shell wildcard；不治理 `__pycache__`/`top_level.txt`。

### 4.5 R11-PR-F05 — POSIX real smoke fixture source lock

- **Controller adjudication 要求**: plan 写出 exact read-only fixture path、复制到 `workspace/tmp` 后的 OLD-recognizable names，以及不得修改 fixture/不从网络下载 fixture。
- **Fixed plan 证据**:
  - §6.6（lines 452–460）：源固定为 `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`；只复制为 `workspace/tmp/r11-posix-real/source/2024FY_AAPL_Annual_Report.htm`（filing）与 `workspace/tmp/r11-posix-real/source/2024FY_AAPL_Earnings_Call_Transcript.htm`（material）；不得修改 tracked fixture、不得从网络下载或更新 fixture。
  - 本 review 独立验证：fixture 存在，1,503,780 bytes，SHA-256 `24a830a0f1256e371d36a1f7f72e5e85a38037d1de2f6f966eb8457db42ff6d6`，与 Controller fix validation lock 一致。
- **闭合判定**: **CLOSED**。Fixture path、target names、mutation/network 禁令全部锁定并与实际文件系统一致。

### 4.6 R11-PR-F06 — zero-filing call cap 与 Ruff version oracle

- **Controller adjudication 要求**: filtered recognized filing count=0 时 call cap=0、全部 call candidates typed skipped、不得 minimum-one；Controller 锁 Ruff baseline 时同时记录 `python -m ruff --version`，implementation/aggregate 版本一致，否则 stop 并重新锁 baseline。
- **Fixed plan 证据**:
  - §5.2.10（lines 256–259）：filtered recognized filing count=0 时 call cap 也必须是 0，所有 `EARNINGS_CALL` candidates 进入带 cap reason 的 typed skipped，不得擅自保留 minimum-one。
  - §5.3（lines 275–280）：owner tests 明确覆盖零 filing 场景。
  - §8.1（lines 591–617）：Controller 在 accepted-plan parent 上同时锁 `python -m ruff --version` verbatim oracle 与 full JSON baseline；implementation/aggregate 在 Ruff delta 比较前逐字匹配版本；版本漂移立即 stop，由 Controller 在同一 implementation 输入树同时重新锁 version oracle 与 full baseline；禁止把版本/规则漂移算作 current finding 或用 baseline 更新掩盖。
- **闭合判定**: **CLOSED**。Zero-filing empty-state 与 minimum-one 禁止明确；Ruff version oracle 的 lock/compare/drift-stop/relock 流程完整。

## 5. Controller rejected candidates 保留验证

按 Controller adjudication §3（lines 79–109）逐项核对 fixed plan 是否保留了拒绝裁决：

| Rejected candidate | Controller 裁决 | Fixed plan 证据 | 状态 |
|---|---|---|---|
| Windows algorithm / `list2cmdline` 作为 baseline/fallback | 拒绝；禁止 `list2cmdline` 作为 batch owner、fallback 或 shim | §6.5（lines 414–427）仍只锁 outcome/invariants/real `cmd.exe` evidence；未新增候选算法家族、N 次 iteration magic、`subprocess.list2cmdline`、fallback 或 shim | **保留** |
| 保留旧 `create` default 或 compatibility notice | 拒绝；三个 upload default 为 `auto` 且禁止 compatibility branch | §6.2.2（lines 349–351）三个 upload parser default 均为 `auto`；batch 不生成 delete；无 compatibility re-export/wrapper/alias | **保留** |
| 删除 OLD structured auto-recursion | 拒绝；是已接受 OLD-aligned workflow 规则 | §5.2.2（lines 234–236）仍保留 structured directory `20YY/20YYQ1..Q4/20YYH1` auto-recursive | **保留** |
| 预先给出候选算法家族/iteration count | 拒绝；不能在无 runner evidence 时猜 | §6.5 仍保留 evidence-driven algorithm gate，无预猜算法 | **保留** |
| Cross-platform `--platform` flag | 拒绝（via DS-Q01 no-action） | §6.3（lines 379–382）仍由实际生成 OS 决定格式；无 `--platform` | **保留** |
| Internal HTTP hop contract | 拒绝（via DS-F03 no-action） | §6.2.4 只约束一次 existing public method call，明确不治理内部 HTTP hop；未修改 resolver owner | **保留** |
| Raw enum UI / 暴露内部类型给用户 | 拒绝（Controller discussion 已裁决） | Plan 全文中 typed plan 的 typed reason code 只进入 human summary，不暴露为机器 schema 或 raw enum string | **保留** |

**判定**: 所有 Controller rejected candidates 均未被实施。Fixed plan 在 Windows algorithm、compatibility、auto-recursion、platform flag、HTTP hop 与 UI 边界上与 Controller 裁决一致。

## 6. 独立 adversarial challenge

### 6.1 Owner 边界

逐项验证 §4 semantic owner map 与三 slice allowlist：

- **Fins typed classification**（§5.1）：`UploadBatchPlanRequest`、`UploadBatchFilingEntry`、`UploadBatchMaterialEntry`、`UploadBatchSkippedEntry`、`UploadBatchPlan` 均不含 executable/argv/output/shell 字段。零 CLI import。✓
- **CLI input/grammar**（§6.2）：ticker CSV normalize、FMP once、argv builder 以 `("python", "-m", "dayu.cli", ...)` 开头；renderer 只消费 `tuple[str, ...]`。零 filename/fiscal/material/cap regex。✓
- **Renderer/publisher**（§6.3–6.5）：`dayu/cli/upload_script.py`（新增）是唯一 quote/escape/publish owner；builder 不自行 replace/escape。✓
- **Packaging**（§7.1）：`pyproject.toml` 删除 placeholder console_scripts + web extra + `dayu.render` package-data；wheel 零残留 oracle。✓

**判定**: Owner 边界无重叠。Fins 不产生 executable/flag/shell；CLI renderer 不重算业务事实；publisher 独立拥有 output path/containment/atomicity。

### 6.2 三 slice 依赖顺序

- **S1→S2**: S1 typed plan（Fins）→ S2 current-grammar argv builder（CLI）+ renderer/publisher。dependency 方向正确；S2 是 S1 的 typed consumer。✓
- **S2→S3**: S2 完成 renderer/publisher 后 S3 删除 placeholder packages 并更新 README。S3 的 README 内容依赖 S2 的 final grammar。dependency 方向正确。✓
- **唯一回返路径**（§9.1）：只允许 S2→S1 的 Controller-authorized targeted fix，且必须重跑 cumulative validation。不允许 S3→S2 或 S3→S1 回返。slice count=3 未超过 umbrella optimization control 上限。✓

**判定**: 依赖顺序正确；回返路径 bounded 且不创建新 slice/commit。

### 6.3 OLD typed classification 完整性

逐项检查 §5.2 的 12 条分类规则是否覆盖 OLD workflow：

1. Source root containment + symlink → typed failure ✓
2. Suffix allowlist（复用 current `FINS_UPLOAD_FILE_SUFFIXES`）+ stable ordering ✓
3. Symlink/escape/non-regular → skipped with security reason ✓
4. Fiscal year `20YY`；period `Q1..Q4/1Q..4Q/中文/H1/FY`；parent dir fallback only `20YYQn/20YYH1` ✓
5. Explicit `--fiscal-year/--fiscal-period` 逐字段覆盖推断值 ✓
6. Material routing 按 OLD 表首个命中；material-first exclusive routing ✓
7. Material name 从 stem 派生；保留 structured prefix ✓
8. Filing same-period priority（6 级）+ stable path tie-break ✓
9. Caps: FY annual≤5、periodic latest-year-max6（Q1,H1,Q2,Q3,Q4）、presentation≤6、call=filtered filing count、financial statements no cap ✓
10. Zero-filing → call cap=0 → all call typed skipped（R11-PR-F06） ✓
11. Explicit amended/dates/company/aliases/overwrite 原样传播；无默认字符串 ✓
12. Empty plan → typed empty error + skipped evidence；不生成空脚本/JSON fallback ✓

**判定**: 12 条规则完整覆盖 OLD workflow。每条规则有明确 owner test coverage 声明。

### 6.4 Current CLI grammar / FMP-once

- **Action grammar**: `FILING_ACTION_CHOICES = auto|create|update|delete`；`BATCH_UPLOAD_ACTION_CHOICES = auto|create|update`；三个 upload parser default=`auto`；batch 不生成 delete。✓
- **Ticker CSV**: 首项 normalize→canonical；alias trim/去重/exclude canonical；无效 alias→usage error。✓
- **FMP-once**: `--infer` store_true/default=False；未传零 env access；传入时从 `FMP_API_KEY` 显式读取；创建一个 `FmpCompanyInfoResolver` 并只调用一次 `resolve_company_info(canonical)`；不治理 resolver 内部 HTTP hop。✓
- **Merge precedence**: canonical 始终来自用户首项；显式 aliases 在前、resolver aliases 在后；显式 `--company-name` 优先于 resolver name；resolver canonical 与请求 canonical 不一致是 typed failure。✓
- **Metadata projection**: 所有 current upload fields 精确进入 S1 request；filing 不带 material fields；material 不带未产生的 IDs。✓

**判定**: CLI grammar 与 FMP-once contract 精确锁定；无歧义或缺失。

### 6.5 POSIX/Windows argv/publisher containment

**POSIX**（§6.4）:
- Header: `#!/usr/bin/env sh`、`set -eu` ✓
- Quoting: `shlex.quote`/`shlex.join`；body 末尾 `"$@"` 追加 caller args ✓
- Regeneration comment: `# ` 前缀；不含 secret ✓
- Real `/bin/sh` recorder + adversarial argv exact JSONL oracle ✓

**Windows**（§6.5）:
- Outcome invariant: typed argv → batch literal/percent expansion → cmd.exe metacharacter+quote parsing → target Python argv parsing == original argv（element-for-element, character-for-character） ✓
- 必须同时成立: 空字符串/空格/Unicode/quotes/backslashes 不丢字符；literal `%` 不触发 expansion；`!` 保持 literal；metacharacters 不启动第二命令 ✓
- Script header: `@echo off`、`chcp 65001 >nul`、`setlocal DisableDelayedExpansion`；CRLF ✓
- 算法 gate: 先把 adversarial matrix 写成 renderer unit + real-recorder oracle；再实现候选算法；任何反例修改同一算法重跑直到 real `cmd.exe` 通过 ✓
- 禁止: `subprocess.list2cmdline`、compat/fallback/双算法/platform test shim ✓

**Publisher**（§6.3）:
- Lexical+resolved containment；root-self symlink rejected；internal component symlink rejected；external ancestor allowed ✓
- Owner-private temp → write/flush/fsync → POSIX chmod `0o755` → `os.replace` ✓
- Existing regular target 独立 atomic replace；与 `--overwrite` 无关 ✓
- Failure/KeyboardInterrupt → temp cleanup；旧 target byte-for-byte preserved ✓
- Secret non-persistence: API key/provider URL/exception cause 不进入脚本/summary/artifact ✓

**判定**: POSIX quoting 使用标准库；Windows 以 evidence-driven gate 锁定；publisher containment/atomicity/secret 边界完整。

### 6.6 Placeholder/package/wheel/RECORD

**Deletion scope**（§7.1）:
- `[project.scripts]`: 删除 `dayu-web`、`dayu-wechat`、`dayu-render`；保留 `dayu-cli` ✓
- `web` optional dependency/comment + `dayu.render` package-data: 删除 ✓
- `requirements.txt`: 删除 `[web]` extra 消费 + Streamlit/dayu-web stale comment ✓
- 6 个 placeholder package files: 删除；不留空 package/re-export/wrapper/README "暂不可用" surface ✓
- `constraints/lock`: 保留 inert Streamlit/watchdog pins（no-touch） ✓

**Wheel oracle**（§7.3）:
- METADATA: 零 `Provides-Extra: web` + 零 Streamlit `Requires-Dist` ✓
- `entry_points.txt`: 零 `dayu-web`/`dayu-wechat`/`dayu-render` ✓
- Extracted archive: 零 `dayu/web`、`dayu/wechat`、`dayu/render` prefix paths ✓
- RECORD: CSV parse 第一列，零 placeholder prefix paths ✓
- Importability: `importlib.util.find_spec` 对三个 removed packages 全部返回 `None` ✓
- 隔离安装后 `--help` 命令成功 + 零 placeholder/JSON claims ✓

**判定**: Placeholder deletion 覆盖 console_scripts、optional dependency、package-data、README 声明；wheel oracle 覆盖 METADATA/entry_points/archive paths/RECORD/importability 五层防御。

### 6.7 Real smoke

**POSIX**（§6.6）:
- Recorder smoke: `/bin/sh script.sh <adversarial appended args>` → recorder JSONL exact compare；injection marker 不存在 ✓
- Real upload smoke: locked fixture → `workspace/tmp/r11-posix-real` → `python -m dayu.cli ... upload_filings_from --action create` → `/bin/sh` 执行 → exit 0 → temp storage source document/terminal success ✓
- No monkeypatch Service/runtime/validator/storage ✓

**Windows**（§7.2）:
- Recorder smoke: `cmd.exe /d /c <generated.cmd> ...` → recorder JSONL exact compare；injection marker 不存在 ✓
- CLI grammar smoke: production builder/renderer 生成 `.cmd` → 复制 fixture 到含空格/Unicode/`% ! & ^ ( )` 的合法路径 → `python -m dayu.cli upload_filing|upload_material` → argparse 至少完成；若依赖允许则 temp storage exit 0 闭环 ✓
- Oracle 固定为 exit 0 + terminal success + temp storage source artifact；环境不允许闭环即 gate fail ✓

**判定**: 两类 smoke 均以 real executable（`/bin/sh`/`cmd.exe`）执行，exact argv compare；real upload smoke 经完整 parser→Service→Fins→storage 链路。

### 6.8 Coverage/pyright/同版本 Ruff

- **Line coverage**（§8.2）: 逐文件读取 coverage JSON `summary.percent_covered >= 80.00`；覆盖四个 changed production files；不虚报未变更文件；不使用 `--branch` ✓
- **Pyright**（§8.1）: `python -m pyright dayu/ tests/ utils/`；零 error ✓
- **Ruff**（§8.1）: scoped command 零错误；full command JSON baseline delta（relative filename/code/row/column/message set difference）current-only 必须为空；同版本 `python -m ruff --version` verbatim oracle；版本漂移 stop+relock ✓
- **Diff check**（§8.1）: `git diff --check` pass ✓

**判定**: Coverage 用普通 line coverage 非 branch；pyright 全量；Ruff 有 version oracle + baseline delta 机制。

### 6.9 Windows release blocker

- **Workflow file**（§7.2）: `.github/workflows/r11-upload-script-windows.yml`；name `R11 upload script Windows gate`；permissions `contents: read`；runner `windows-latest`；Python `3.11`；`timeout-minutes: 30` ✓
- **Triggers**: `workflow_dispatch`；`pull_request.paths` 精确列出 §4 closed product allowlist ✓
- **Test command**: 两个 real `cmd.exe` recorder/CLI grammar smoke nodes + 一个 action grammar node ✓
- **Artifact**: `actions/upload-artifact@v4`、`if: always()`、retention 14 days、`if-no-files-found: error` ✓
- **Gate status**: 本地 branch 未发布前 `PENDING_RELEASE_BLOCKER`；最迟 umbrella aggregate/draft PR check 触发并通过；任何未执行/skipped/cancelled/失败/artifact 缺失/oracle 不相等阻止 umbrella aggregate acceptance ✓
- **禁止降级**: 不得转 residual risk；通过后 Controller 才能改 `CLOSED` ✓

**判定**: Windows gate 定位为硬 release blocker；workflow 最小且 self-contained；证据读取路径固定。

### 6.10 Security/deferred/no-touch 边界

- **Security**（§8.3 oracles）:
  - Source/output containment + symlink ✓
  - Same-dir atomic replace + temp cleanup ✓
  - POSIX executable mode、Windows delayed expansion off ✓
  - Argv injection marker ✓
  - Secret scan（FMP_API_KEY/sentinel/provider URL in generated artifacts） ✓
  - Script body 无 `--infer`/API-key env/provider URL/网络调用；regeneration comment 可保留无 secret 的 `--infer` ✓
  - 本轮 security closeout 只报告 containment/symlink/atomic/argv injection/secret non-persistence；不描述为统一 authorization/workspace trust/shell sandbox ✓
- **Deferred**（§3.3 + §8.3 deferred diff）:
  - Issue 142/151/175/177/178 — zero production diff ✓
  - R12 `init` — zero diff ✓
  - 真实 Web（#84）/WeChat（#147）/render tracker — zero production diff ✓
  - Topic 8（Engine 240-char）/Topic 9（统一 auth） — zero production diff ✓
  - `dayu/service/**`、`dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**` — zero diff ✓
- **Negative sentinels**（§8.3）:
  - `tests/tools/web/test_web_tools_provider.py` 与 `test_diagnose_web_access.py` 中的 `"dayu.web"` 各精确命中一次；对应 test files 零 diff；是负向 import-boundary sentinel，不纳入 placeholder 零命中 ✓

**判定**: Security/deferred/no-touch 边界完整。局部安全机制不被升级为统一权限框架。

## 7. New findings

本 re-review 未发现新的 material finding。具体检查结果：

- **S1→S2 mapping checklist 中的 `fiscal_period` normalization 表**: Plan §5.2.4 列出 OLD patterns（Q1..Q4、1Q..4Q、中文一至四季度、H1/first-half/…、FY/annual/…），S2 checklist 锁定归一化为 `FY|H1|Q1|Q2|Q3|Q4`。Normalization 映射 implicit but clear（如 "四季度"→Q4、"年报"→FY、"中期报告"→H1）。implementation agent 可无歧义实现。**Non-finding**。

- **`--material-forms` 在无 material-routed entry 时的行为**: Plan §5.2.6 明确 "只覆盖已经 material-routed entry 的 form type"。无 material entry 时 flag 为 no-op，不会把所有文件强制变 material。行为正确。**Non-finding**。

- **`python -m pip wheel --no-build-isolation` 的 build dependency**: Plan §7.3 使用此命令构建 wheel。需要 `.venv` 中已有 `setuptools>=68` 和 `wheel`。标准开发环境满足此条件；若 `.venv` 是最小安装需先确认。这是 implementation 前的一次性 dependency check，不是 plan 缺陷。**Non-finding**。

- **Windows workflow `pull_request.paths` 的维护负担**: 若 §4 closed allowlist 中的文件路径变更，workflow trigger 需同步更新。Controller 已裁决（MiMo-03 rejected）闭集 allowlist 是有意约束。**Non-finding**。

- **`EARNINGS_CALL` cap 的 "过滤后" 含义**: Plan §5.2.10 说 "call cap 等于过滤后的 recognized filing 数量"。按 §5.1 flow（recognition → material-first routing → filing same-period priority/dedup → filing/material caps），"过滤后" 是 post-dedup、post-filing-cap 的最终 recognized filing 数量。流程清晰。**Non-finding**。

- **`--output` help text 更新**: Plan §6.3 重新定义 output 为脚本路径（不再是 JSON 路径），当前 help text（"结构化 JSON argv 计划输出路径"）需更新。这是 implementation 的自然结果，plan 的 output contract 已覆盖新语义。**Non-finding**。

## 8. Open questions

本 re-review 无 open question。初始 DS review 的三个 open questions（DS-Q01 跨平台生成、DS-Q02 zero-filing call cap、DS-Q03 Ruff baseline 跨版本一致性）均已在 Controller adjudication 或 fixed plan 中解决：

- DS-Q01：Controller 拒绝 cross-platform `--platform` flag；plan §6.3 由实际生成 OS 决定格式 → **已关闭**。
- DS-Q02：R11-PR-F06 fixed plan §5.2.10/§5.3 锁定 zero-filing→cap=0 → **已关闭**。
- DS-Q03：R11-PR-F06 fixed plan §8.1 锁定 Ruff version oracle → **已关闭**。

## 9. Residual risks

| Risk | Severity | Owner | Destination |
|---|---|---|---|
| Windows cmd.exe quoting algorithm 可能需多轮反例迭代才收敛 | 高 | R11-S2 implementation agent | S2 Windows renderer unit + real `cmd.exe` recorder gate；若 agent 无法收敛则 escalate 到 Controller |
| S2 首个真实 consumer 可能暴露 S1 typed contract 缺口（即使 checklist 已逐字段覆盖） | 中 | R11-S1/S2 Controller checkpoint | §9.1 唯一 owner 回返路径；Controller 在 S2 开始前按 §5.3 checklist 预验证 |
| Wheel build 在最小 `.venv` 中可能缺少 build frontend | 低 | R11-S3 implementation agent | Implementation 前做一次 `pip wheel --no-build-isolation --dry-run` 预检 |
| Windows workflow trigger paths 与 §4 allowlist 不一致 | 低 | R11 implementation agent | Implementation 时逐项核对 workflow `pull_request.paths` 与 closed allowlist |
| Ruff version drift 在 plan-acceptance 到 implementation 之间 | 低 | Controller | §8.1 version oracle + drift-stop + relock 流程；不影响 plan 文本层质量 |

## 10. Final verdict

**Verdict: PASS / ZERO FINDING / ZERO BLOCKER**

Fixed plan 中 R11-PR-F01—F06 全部闭合，修复位于对应语义 owner 或验证 owner 的边界，未引入 downstream fallback、compatibility seam、scope creep 或新的 material issue。Controller rejected candidates（旧 create default、list2cmdline/fallback、删除 OLD auto-recursion、预猜 Windows algorithm、cross-platform platform flag、internal HTTP hop contract、raw enum UI）均未被实施。

三 slice 的 owner 边界、dependency order、allowlist、stop conditions 与 review state machine 未被 fix 改变或弱化。Plan 已达到 code-generation-ready 状态：所有 typed field→flag mapping 被 S2 consumer checklist 锁定，所有 symlink/containment/atomic/secret 边界被精确规则锁定，所有 validation/scans/coverage gates 被可执行命令锁定。

Plan 可以安全交给 R11 implementation agent，按 §9 的切片状态机执行。

---

## 11. Artifact metadata

- **Reviewer**: AgentDS
- **Review timestamp**: 2026-07-17T22:27:07+08:00
- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- **Reviewed artifact SHA-256**: `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`
- **Reviewed artifact lines**: 773
- **Finding count**: 0
- **Blocker count**: 0
- **Workspace status**: Controller control doc dirty（expected）；R11 plan + all review artifacts untracked；zero staged files；zero production code diff
- **Staged status**: `git diff --cached --name-only` empty

READY_FOR_CONTROLLER_ADJUDICATION
