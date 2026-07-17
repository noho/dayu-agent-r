# WU-SEMANTIC-OWNERSHIP-01 / R11 second complete amended-plan re-review — AgentDS（第二路 final）

## 1. Gate、scope 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal remediation：`R11 — OLD-aligned upload shell/cmd workflow 与 placeholder surface 删除`。
- reviewed target：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，
  886 lines / 74,523 bytes，SHA-256
  `c3c0616f7ec90cb8e62f68bf219e43b053a07db320c3b169f70159855ce1430c`。
- review type：second complete amended-plan re-review（DS route），不是 delta-only。
- 前置 artifacts 已完整读取：
  - Controller adjudication（first re-review）：75 lines / SHA-256
    `9fceb2f83239fdf7afe804e39730cecd9d95224527ed96fe129b4011ea8d8426`
  - AgentCodex wording fix evidence：158 lines / SHA-256
    `e3d1d0f8e01525f95cc1ccab2f149fa8aae9b41cbd0ec00faf070d1f49a369e7`
  - Controller wording fix validation：84 lines（已完整读取）
  - AgentMiMo first re-review（848-line plan）：341 lines / SHA-256
    `ff534233f131358b88dcdf14bb97640c35445154282889e93aaead28a1ab7708`
  - AgentDS first re-review（848-line plan）：387 lines / SHA-256
    `bec8c777a1e1c8fdb3a2aa33ebb850257c6dc466dd2deaf18e49a023aed9eecf`
- 按 plan authority order 核对：AGENTS.md → design docs → Controller discussion Topic 7 →
  umbrella remediation plan → umbrella optimization control → Controller control truth →
  current production code/tests/READMEs → OLD reference files。
- Agent verdict：**PASS / ONE LOW FINDING / ZERO BLOCKER**。

五项目标独立证明全部通过。R11-IMP-BF01 仍 closed；R11-PR-BF-RR-F01 已正确关闭；全部
cumulative gates 未弱化；plan 仍 code-generation-ready，未引入 transactional editor、rollback
framework、兼容层、第三 slice、中间 commit、R12/deferred Issue 或统一 authorization。
发现一项 LOW severity 文档级 source lock 不匹配（不影响产品 contract）。

本 gate 不授权 implementation、stage、commit、push、PR 或 R12。唯一 write 为本 artifact。

## 2. 完整 source locks 与 authority 验证

### 2.1 Plan authority order 逐层核对

| Authority | 核对结果 |
|---|---|
| AGENTS.md（128 lines / `cb26618a...ac45e`） | 语义所有权、分层、类型、测试、README 约束全部在 plan §3.3/§4/§5.1/§8.1 中传播；no-compat、no-`hasattr/getattr`、no-`Any`、full pyright 0 全部保留 |
| `docs/fins/design.md` §10（Upload Batch Plan owner） | plan §5 完整实现 typed batch plan owner contract；Fins 不依赖 CLI parser |
| `docs/ui/design.md` §1—2（entrypoint lifecycle、`upload_filings_from`） | plan §6/§7 完整传播：CLI 拥有参数/脚本格式/argv quoting，Fins 拥有分类规则；placeholder 只删除不实现 |
| Controller discussion Topic 7 final adjudication | plan §1/§3.1/§5/§6/§7 完整传播：upload_filings_from 生成平台可执行脚本、删除 placeholder、保留 ISSUE trackers、Fins 拥有 batch plan、CLI 拥有脚本渲染、不迁移 OLD 架构 |
| umbrella remediation plan §7/§18/§20—22 | plan §9 aggregate gate + §2.4 exact mapping table + §8 Windows release blocker 一致 |
| umbrella optimization control | 两 slices 属 High Risk（生产代码 + public contract + CLI），执行完整 gate 流程；R11-PR-BF-RR-F01 属 Low Risk plan wording fix，该 gate 已完成 |
| Controller control truth（2242 lines，只读） | 未触碰；Controller-owned dirty/untracked 文件均为有意状态 |

### 2.2 Production source locks 核实

逐项以 `shasum -a 256` 重新测量，对比 plan §2.2 声明值：

| Source | Plan 声明 lines/SHA-256 | 实测 lines/SHA-256 | 匹配？ |
|---|---:|---|
| `dayu/fins/upload_batch.py` | 376 / `6767d30c...d6178` | 376 / `6767d30c...d6178` | ✅ |
| `dayu/cli/commands/fins.py` | 1057 / `0db8ff2d...c95a6` | 1057 / `0db8ff2d...c95a6` | ✅ |
| `dayu/cli/arg_parsing.py` | 932 / `a0e25ad6...c1c2c` | 932 / `a0e25ad6...c1c2c` | ✅ |
| FMP resolver (`fmp_company_info.py`) | 394 / `c2abfbe0...c46fa` | 394 / `c2abfbe0...c46fa` | ✅ |
| `pyproject.toml` | 152 / `e076606f...6a25` | 152 / `e076606f...6a25` | ✅ |
| `requirements.txt` | 12 / `7e8c14d6...79c93` | 12 / `d1517613...15d3a` | ❌ 见 §8 Finding |

`requirements.txt` 在 accepted-plan commit `f7b452f9` 与当前 working tree 的 SHA-256 均为
`d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a`，与初始 commit `ddf0ca6e`
一致——文件内容从未变更。plan 记录的 `7e8c14d6...79c93` 是测量误差，不是 material drift。

其余 production source locks 全部精确匹配。Controller-owned control 文件可因 gate transition
合法变化；本路确认无 production contract、owner、allowlist 或依赖发生 material drift。

### 2.3 Completion truth locks 核对

| Lock | Plan 声明 commit | 验证 |
|---|---|---|
| R06 accepted implementation | `4f417e91` | confirmed via git log |
| R09 accepted implementation | `8e0f2c55` | confirmed via git log |
| R09 completion | `1c258527` | confirmed — 是当前 HEAD 的前第四个 commit |
| R10 completion baseline | `2b14b2fb` | confirmed — accepted-plan parent，`git diff` 以此为基础 |
| accepted-plan commit | `f7b452f9` | HEAD |

### 2.4 Plan authority order 未变更

原 authority order（AGENTS.md → design docs → Controller discussion → umbrella plan →
control → current code → OLD reference）全部保留；plan 未引入新的 authority source 或重排优先级。
已裁决产品问题（Topic 7、R11-PR-F01—F06 closed、R11-IMP-BF01 closed）均未被重开。

## 3. Proof 1：R11-IMP-BF01 仍 closed

### 3.1 Root cause 回顾

CURRENT `upload_batch.py`（line 17）定义 `BatchUploadAction = Literal["create", "update"]`（无
`auto`）；`UploadBatchPlanEntry`（lines 89-119）含 `command_name`、`files: tuple[Path, ...]` 等
generic 字段；`UploadBatchPlanResult`（lines 122-136）含 `entries: tuple[UploadBatchPlanEntry, ...]`
与 path-only `skipped_files`。

CURRENT `dayu/cli/commands/fins.py`（lines 54-62）静态 import `UploadBatchPlanEntry` 等旧类型，
`_run_upload_filings_from`（lines 275-313）消费 `plan.entries`，
`_render_upload_batch_plan`（lines 316-329）渲染为
`{schema_version: 1, commands: [argv...]}` JSON。

原 accepted plan 的 S1 exact allowlist 只有 producer 两路径，禁止修改 CLI consumer。因此
producer-only 删除旧 generic 类型/字段会直接破坏 CLI 的 static import/attribute/type contract
（full pyright 从 0 errors 变为非零），而保留旧 surface 又违反 no-compat 约束。

### 3.2 Final plan 的修复

Plan §4（lines 197-209）将原 S1（Fins producer）与原 S2（CLI consumer/renderer）合并为同一个
atomic slice `R11-I1`，内含 WP-A（Fins typed contract）与 WP-B（CLI cutover）两个 ordered work
packages，共享同一 merged exact allowlist（8 个 product/test 路径）。原 S3（packaging）成为
`R11-I2`。

Plan §5.1（lines 215-231）明确：
- WP-A 和 WP-B 是同一 slice 的 work packages，不是独立 slices。
- 实现 Agent 可在同一 uninterrupted task 内顺序编辑多个文件；不要求跨文件事务原子写。
- atomic cutover 只定义 gate truth。
- 全部 coordinated edits 完成前的 transient inconsistency 不是合法 intermediate tree 或
  pass/failure baseline，不运行 validation，不做 gate transition。

Plan §9.1（lines 771-816）固定精确 two-slice state machine：
```
R11-I1 coordinated implementation → Controller R11-I1 atomic checkpoint →
R11-I2 packaging/README/Windows → Controller R11-I2 checkpoint →
one cumulative code-review gate
```

WP-A/WP-B 之间无 checkpoint、acceptance、commit、full validation、handoff、review 或
next-slice transition。

### 3.3 Closure evidence

以下独立 scan 在 886 行 final plan 上执行，全部为 exit 1 / stdout empty：

```text
rg -n 'R11-S[123]|S1[[:space:]]*->[[:space:]]*S2|三[个份][[:space:]]*slice|S1 checkpoint|S2 checkpoint|S3 checkpoint|进入 S[123]|回到 S[123]|从 S[123]|\bS2\b|\bS3\b' <plan>
```

旧三-slice state transition 零残留。唯一的 bare `S1` 命中在 plan line 12，是引用 Controller-owned
S1 authorization/stop/adjudication artifact 的历史专名，不是 current state-machine node。

正向二-slice propagation：
- line 211: `## 5. Atomic slice R11-I1 / WP-A`
- line 363: `## 6. Atomic slice R11-I1 / WP-B`
- line 529: `## 7. Slice R11-I2`
- line 772: `严格顺序精确两个 implementation slices`

所有 `checkpoint` 命中经逐项人工审阅后只属于合法语义：明确禁止 WP-A/WP-B 中间
checkpoint、WP-A+WP-B 共同 cutover 后的唯一 `R11-I1 atomic checkpoint`（仅 Controller 可执行）、
I2 完成后的 `R11-I2 checkpoint`、acceptance checklist 复述。不存在 producer-only checkpoint、
CLI-only checkpoint、work-package acceptance、work-package commit 或第三 slice transition。

**Verdict：R11-IMP-BF01 仍 CLOSED。** 只有两个 implementation slices；无 producer-only
checkpoint/commit/review/handoff。

## 4. Proof 2：R11-PR-BF-RR-F01 已正确关闭

### 4.1 Controller §4 五项 wording requirement 逐项验证

**Requirement 1：同一 uninterrupted Agent task 可顺序编辑 I1 多文件；不要求跨文件事务原子写**

- Plan §5.1（lines 223-224）："实现 Agent 可在同一 uninterrupted task 内顺序编辑 R11-I1
  多个文件；这里的 atomic cutover 只定义 gate truth，不要求编辑工具提供跨文件事务原子写"
- Plan §8.1（lines 647-649）："Validation sequencing 是 atomic boundary 的一部分，但不要求
  跨文件事务原子写：实现 Agent 可在同一 uninterrupted task 内顺序编辑 WP-A/WP-B 文件"
- Plan §9.1（lines 793-795）："R11-I1 mutation 必须在同一 uninterrupted Agent task 内协调
  应用 producer 与全部 consumer 变更，但可以顺序编辑文件，不要求跨文件事务原子写"

三处文字一致，语义无歧义。✅

**Requirement 2：WP-A/WP-B 全部 coordinated edits 完成前不得 validation 或 gate transition**

- Plan §5.1（lines 226-229）："在 WP-A/WP-B 全部 coordinated edits 完成前，不得运行或宣称
  tests、pyright、coverage、Ruff、diff/diffcheck/scans validation，不得 checkpoint、acceptance、
  stage、commit、handoff、review 或 next-slice transition"
- Plan §5.3（lines 301-304）：首次 validation 只能在全部 edits 完成后运行
- Plan §8.1（lines 649-651）：全部 coordinated edits 完成前不得运行/宣称 validation
- Plan §9.1（lines 795-798）：首次 validation 只能在全部 coordinated edits 完成后运行

四处一致，禁止项列表完整（tests/pyright/coverage/Ruff/diff/diffcheck/scans +
checkpoint/acceptance/stage/commit/handoff/review/next-slice）。✅

**Requirement 3：transient inconsistency 不是合法 intermediate tree 或 pass/failure baseline；
不得 compatibility seam；首次 validation 仅在全部 edits 后**

- Plan §5.1（lines 226-231）："顺序编辑期间可以短暂出现'新 producer + 旧 consumer'等
  transient inconsistency，但它不是合法 intermediate tree，也不是 pass/failure baseline。...
  首次 validation 只能在全部 R11-I1 coordinated edits 完成后运行"
- Plan §5.1（lines 229-230）："也不得以 compatibility seam 缓解 transient inconsistency"
- Plan §8.1（lines 649-651）："全部 coordinated edits 完成前的 transient inconsistency 不是
  合法 intermediate tree，也不是 pass/failure baseline"
- Plan §9.1（lines 795-798）：同语义

transient inconsistency 的定义与禁止用途均已精确。✅

**Requirement 4：material preflight 在 mutation 前；真实 blocker 仍安全 stop**

- Plan §5.1（lines 224-226）："implementation 必须在 mutation 前完成并记录全部 material
  preflight"
- Plan §5.1（lines 231-233）："若编辑期间出现真实 allowlist/source/design/security blocker，
  必须立即 stop 并按 §5.3/§9.1 报告 failed working evidence；不得继续冒险，也不得把这一
  safety stop 解释为 checkpoint/pass 许可"
- Plan §5.3（lines 350-358）：详细 stop conditions 与 safety stop 程序
- Plan §8.1（lines 653-657）："所有 material preflight 必须在 mutation 前完成；若编辑期间
  出现真实 allowlist/source/design/security blocker，仍必须 stop，保留并报告当前 diff 作为
  failed working evidence"
- Plan §9.1（lines 801-804）："该 safety stop 不构成合法 intermediate state、failure
  baseline、acceptance、commit、review 或 next-slice transition"

safety stop 与 failed working evidence 的语义在四处一致。✅

**Requirement 5：保留 Fins correction loop、combined revalidation、full pyright 0 与其它 gates**

- Plan §5.3（lines 360-361）："correction 后必须 combined revalidation...full pyright
  `0 errors` 与其它既有产品/security/deferred/Windows/Ruff gates 全部通过"
- Plan §8.1（line 662）："任何时点都不得放宽当前 full pyright `0 errors` 要求"
- Plan §8.1（line 662）："其余产品、security、deferred、Windows 与 Ruff gates 同样保持不变"
- Plan §9.1（lines 806-811）：consumer gap 发现时 correction loop 与 combined revalidation

full pyright 0 与所有 gates 保留的断言在四处可验证。✅

### 4.2 禁止方案零残留

以下独立 scan 全部为 exit 1 / stdout empty：

```text
rg -n -i 'transactional editor|rollback framework|compat layer|third slice|第三[个份]?[[:space:]]*slice|中间 commit' <plan>
rg -n -i '不可停|不得停|不能停|no[ -]?stop|无可观察[^\n]*broken tree|之间没有[^\n]*stop|无 broken tree' <plan>
```

旧 readiness marker（`READY_FOR_CONTROLLER_PLAN_WORDING_FIX_VALIDATION` 之前版本）与旧
evidence path 均已替换为当前 gate 对应值。

**Verdict：R11-PR-BF-RR-F01 已正确关闭。** Controller §4 五项 wording requirement 在 final plan
的 §5.1、§5.3、§8.1、§9.1 中一致、完整、自足。未引入 transactional editor、rollback
framework、兼容层、第三 slice 或中间 commit。

## 5. Proof 3：全部 gates 未弱化

### 5.1 Fins correction loop 与 combined revalidation

| 约束 | Plan 位置 | 内容 | 弱化？ |
|---|---|---|---|
| correction 只在 Fins owner | §5.3 lines 344-348、§9.1 lines 806-808 | 只修改 `dayu/fins/upload_batch.py` 与 `tests/fins/test_upload_batch.py` | 否 |
| CLI 继续机械消费 | §5.3 line 348、§9.1 line 808 | "CLI 继续机械消费同一 source of truth" | 否 |
| correction 后 combined revalidation | §5.3 lines 360-361、§8.1 lines 656-657、§9.1 lines 810-811 | "重跑 §5.3、§6.6、§8 对 producer+consumer 的全部 cumulative" | 否 |
| 禁止在 builder/renderer/adapter/fixture 补偿 | §5.3 line 347、§6.6 lines 522-525、§9.1 lines 808-809 | 三处一致禁止 | 否 |

### 5.2 Full pyright 0 errors

Plan §8.1（line 662）："任何时点都不得放宽当前 full pyright `0 errors` 要求"。Plan §8.1
（line 675）：`python -m pyright dayu/ tests/ utils/` 涵盖全仓。该约束在 §5.3、§8.1、§9.1
三处重复锁定。**未弱化。**

### 5.3 Ruff 0.15.11 baseline

Plan §8.1（lines 686-693）：version oracle 逐字锁定 `ruff 0.15.11`、144 findings baseline
SHA-256 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`、
current-only 必须为空、版本漂移立即 stop。Scoped command 必须零错误。**未弱化。**

### 5.4 Per-file line coverage ≥80%

Plan §8.2（lines 705-708）：逐文件从 coverage JSON 读取 `summary.percent_covered >= 80.00`，
四个 changed production files 逐文件判定。禁止扩大 omit、pragma 或总覆盖率代替。**未弱化。**

### 5.5 Security scans

Plan §8.3（lines 714-765）：source/output containment、symlink rejection、atomic replace、
POSIX mode、Windows delayed expansion off、argv injection marker、secret non-persistence、
executable body 无 `--infer`/API-key/网络调用。四项人工 oracle（反向依赖、propagation、
security、deferred）覆盖完整。**未弱化。**

### 5.6 Deferred/no-touch

Plan §3.3（lines 134-143）：不实现 Issue 142/151/175/177/178、不进入 R12、不实现真实
Web/WeChat/render、Topic 8/9 不变、不改 Service/Host/Engine/runtime/storage/FMP resolver/
ticker normalizer/design docs/constraints。Plan §8.3 deferred diff scan（line 733-735）要求
`dayu/service dayu/host dayu/engine dayu/runtime dayu/config dayu/tool dayu/ui constraints`
与 design docs 的 diff 为零。实测 CURRENT deferred diff 确实为零。**未弱化。**

### 5.7 Windows PENDING_RELEASE_BLOCKER

Plan §7.2（lines 602-606）：本地 branch 未发布前无法得到 GitHub-hosted run，accepted
implementation 可标 `PENDING_RELEASE_BLOCKER` 但不得标 Windows closed。Plan §9.4
（lines 852-860）：最迟在 aggregate/draft PR check 触发并通过；失败时回到 R11 owner
fix/review，不新建 WU，不转 residual。**未弱化。**

**Verdict：全部 gates（correction loop、combined revalidation、full pyright 0、Ruff baseline、
coverage、security、deferred、Windows blocker）均未弱化。**

## 6. Proof 4：plan 仍 code-generation-ready

### 6.1 禁止元素零引入

| 禁止项 | Plan/Codex fix 处置 | 状态 |
|---|---|---|
| transactional editor / 跨文件事务原子写 | §5.1/§8.1/§9.1 明确"不要求"；Codex fix §6 明确拒绝 | ✅ 未引入 |
| rollback framework | Codex fix §6 拒绝："自动 rollback 会销毁诊断证据并越过裁决" | ✅ 未引入 |
| compatibility layer / old-new dual surface | §4/§5.1/§9.1 明确禁止；Codex fix §6 拒绝 | ✅ 未引入 |
| 第三 slice | §9.1 只有 R11-I1 与 R11-I2；legacy scan 零命中 | ✅ 未引入 |
| 中间 commit / checkpoint / review | §9.1 明确禁止；§9.2 只在两 slices 完成后一次 cumulative review | ✅ 未引入 |
| R12 / deferred Issue 实现 | §3.3 明确禁止 | ✅ 未引入 |
| 统一 authorization | §3.3 line 138 "Topic 9 不实现统一 authorization" | ✅ 未引入 |

### 6.2 实现可行性

Plan 提供完整实现输入：

- **Exact allowlist**：§4（lines 162-209）列出全部 production/packaging/CI/test/README 路径，
  并精确分配给 R11-I1 与 R11-I2。
- **Exact typed models**：§5.1（lines 248-255）定义 `UploadBatchPlanRequest`、
  `UploadBatchFilingEntry`、`UploadBatchMaterialEntry`、`UploadBatchSkippedEntry`、
  `UploadBatchPlan`，全部字段含义、类型、optionality 明确。
- **Exact classification rules**：§5.2（lines 260-297）12 条规则覆盖扫描、containment、财期
  推断、material routing、优先级、去重、数量限制、skip reason。
- **Exact producer-consumer mapping checklist**：§5.3（lines 329-342）逐字段锁定 Fins typed
  fact 到 CLI flag 的映射，含 enum 与 optional 规则。
- **Exact grammar locks**：§6.2（lines 396-428）逐项锁定 action grammar、ticker CSV、`--infer`、
  `--overwrite`、argv builder、regeneration comment。
- **Exact renderer/publisher contract**：§6.3—§6.5 锁定 POSIX/Windows output path、containment、
  atomic publish、quoting invariants。
- **Exact validation commands**：§5.3/§6.6/§8.1—§8.3 列出全部 pytest/pyright/Ruff/coverage/
  scans 命令与预期输出。
- **Exact state machine**：§9.1 固定 gate 顺序与 transition 条件。

所有命令中的路径、参数、预期输出均为可复制执行的完整命令，不含 `$PWD`、`<placeholder>` 或
"参见前文"引用。**Plan 可直接交给实现 Agent 执行。**

### 6.3 Windows quoting 算法

Plan §6.5（lines 455-479）正确地将具体 quote/escape 算法留给真实 `cmd.exe` runner 反证，
并固定了必须成立的 invariants（空字符串、空格、Unicode、引号、反斜杠、`%`、`!`、`&|^()<>`
等 adversarial matrix）。算法不可用时明确标注 release gate pending，不声称 closed。这是正确的
evidence-driven approach，不是 plan 缺口。

**Verdict：plan 仍 code-generation-ready，未引入任何禁止元素。**

## 7. Proof 5：完整 adversarial review

### 7.1 Architecture boundary

- Fins production 零 `dayu.cli/service/host/engine/ui` import（plan §8.3 line 754）：CURRENT
  `upload_batch.py` 的 import 只有 `__future__`、`re`、`collections.abc`、`dataclasses`、
  `pathlib`、`typing`。**符合。**
- Renderer 零 filename/fiscal/material/cap regex（plan §8.3 line 754）：plan §6.2 要求单一
  argv builder 做 field-to-flag 投影，renderer 只消费 `tuple[str, ...]`。**符合。**
- 分层 `UI -> Service -> Host -> Engine` 未被穿透（plan §3.3）：不改 Service/Host/Engine。
  **符合。**
- `dayu.runtime` 不被 Fins/CLI 新增 import：plan allowlist 不含 runtime paths。**符合。**

### 7.2 Semantic owner boundary

Plan §4 semantic owner map（lines 146-160）的每个事实都有唯一 owner 且消费者明确：

| Semantic fact | Owner | Consumer | Boundary 是否干净 |
|---|---|---|---|
| upload suffix allowlist | CURRENT Fins contract | batch scanner 直接复用 | ✅ 不复制 OLD suffix set |
| 文件发现、containment/symlink verdict | `upload_batch` | CLI 只收到 typed facts | ✅ 无 CLI 侧重判 |
| 财期/material/priority/dedup/caps/skip | `upload_batch` 单一 helpers | CLI 机械投影 | ✅ 无 renderer 重算 |
| canonical ticker + alias CSV | CLI input boundary + normalization | typed batch request | ✅ Fins 不读 env/网络 |
| FMP resolve | 既有 `FmpCompanyInfoResolver` | CLI 只调用一次 | ✅ Fins 不读 env/网络 |
| explicit/inferred merge | CLI input boundary | batch plan 接收定型 metadata | ✅ |
| plan entry → argv | CLI single builder | renderer 只消费 tuple | ✅ renderer 不判型 |
| POSIX/Windows quoting | `upload_script.py` renderer | builder/tests 不 replace/escape | ✅ 单一 quote owner |
| output/publish | `upload_script.py` publisher | CLI command 只传 intent | ✅ |
| human summary | CLI command | stdout | ✅ 不产生机器 schema |

不存在同一语义多 owner 或 downstream fallback 重算。

### 7.3 OLD 分类规则覆盖率

对照 OLD `cli_support.py`（2267 lines）与 `upload_recognition.py`（555 lines），plan §5.2 的
12 条规则覆盖：

| OLD 规则 | Plan §5.2 | 覆盖？ |
|---|---|---|
| 文件后缀过滤 | rule 2（复用 CURRENT suffix set） | ✅ |
| structured directory auto-recursive | rule 2（`20YY`/`20YYQn`/`20YYH1`） | ✅ |
| 财期从文件名/父目录推断 | rule 4（中文/英文 Q/H/FY patterns） | ✅ |
| Q4 分流 | rule 4（含"季报"→Q4，否则 FY） | ✅ |
| explicit fiscal 覆盖推断 | rule 5 | ✅ |
| material routing（三 form types） | rule 6 | ✅ |
| material name 派生 | rule 7（year-period prefix + strip HKEX） | ✅ |
| filing 优先级/tie-breaking | rule 8（6 级 priority + stable path） | ✅ |
| FY annual max 5 | rule 9 | ✅ |
| periodic latest year max 6 | rule 9（Q1,H1,Q2,Q3,Q4 order） | ✅ |
| presentation max 6 | rule 10（按文件名年份降序） | ✅ |
| call cap = filtered recognized filing count | rule 10 | ✅ |
| call cap=0 时全部 call→skipped | rule 10 | ✅ |
| financial statements no cap | rule 10 | ✅ |
| empty plan → typed error + skipped evidence | rule 12 | ✅ |

规则 11（metadata 传播）与规则 3（symlink/escape rejection）是 R11 新增的安全边界，OLD
无对应项。**OLD 分类规则覆盖率完整。**

### 7.4 Edge case analysis

逐项验证 plan 对关键 edge case 的处理：

| Edge case | Plan 处置 | 是否正确 |
|---|---|---|
| 文件同时匹配 filing 与 material pattern | §5.2 rule 6：material routing 先命中先得，已命中 material 不进入 filing | ✅ |
| `--material-forms` 传入但无文件匹配 material | §5.2 rule 6：只覆盖已 material-routed entry 的 form type，不强制 material | ✅ |
| fiscal year 缺且 parent 无法补齐 | §5.2 rule 5：filing 缺 year 或 period → skipped；material 可保留可选 fiscal | ✅ |
| 纯年份 parent（如 `2024/`） | §5.2 rule 4："纯年份 parent 不能猜 period" | ✅ |
| `--infer` 但 `FMP_API_KEY` 未设 | §6.2 rule 4："缺失立即失败" | ✅ |
| `--infer` resolver 返回不同 canonical | §6.2 rule 5："typed generation failure，不静默改 ticker" | ✅ |
| recognized/material 均为空 | §5.2 rule 12：typed empty error + skipped evidence，不生成空脚本 | ✅ |
| 显式 `--output` 指向既有目录 | §6.3：目录内使用默认文件名 | ✅ |
| 显式 `--output` 指向文件 | §6.3：原样采用 exact path | ✅ |
| output target 是既有 directory/非普通 | §6.3：write failure | ✅ |
| `KeyboardInterrupt` 在 write 期间 | §6.3：清理 temp，旧 target byte-for-byte 不变 | ✅ |
| workspace root 自身是 symlink | §6.3：拒绝 | ✅ |
| `/tmp -> /private/tmp` external ancestor symlink | §5.2 rule 1 / §6.3：必须允许 | ✅ |
| `call cap = 0` 因 filtered recognized = 0 | §5.2 rule 10：全部 EARNINGS_CALL→skipped，不保留 minimum-one | ✅ |
| Windows file name 含禁止字符 | §7.2：只在 recorder 的普通 argv 覆盖，不伪造为 filesystem path | ✅ |

全部 edge case 有明确 typed 处置，无静默丢失、fallback 或 undefined behavior。

### 7.5 Overcoupling check

I1 允许 list 把 producer 与 consumer 放入同一 slice——这是 static type contract 原子切换的
必要条件，不是功能耦合。Fins 仍独立拥有分类规则（§5.2），CLI 仍独立拥有渲染规则（§6.2—§6.5），
二者仅在 typed contract interface 有共享。I2 与 I1 之间只有 dependency order，无双向依赖或
共享可变状态。**无过度耦合。**

### 7.6 Overengineering check

Plan 拒绝：JSON fallback、第二 renderer、shell-specific 业务分支、generic authorization、
extra payload、compat re-export/wrapper/alias。Windows quoting 不预猜算法。Wheel smoke 的
五个 Python negative oracle 是删除 placeholder 后确保 wheel 干净的唯一可审计手段。
**无过度设计。**

### 7.7 Best-practice check

- Per-file line coverage（非总覆盖率）✅
- Full pyright 0 errors ✅
- Ruff baseline set difference（非只看 exit code）✅
- 真实 `/bin/sh` 与 `cmd.exe` recorder（非 mock）✅
- Wheel smoke 用隔离 venv ✅
- Security scan 分离 comment/body ✅

**最佳实践一致。**

## 8. Finding

### R11-PR-BF-FR-DS-F01 — `requirements.txt` source lock 不匹配

- **位置**：plan §2.2 baseline source locks 表（line 71）
- **问题类型**：文档级 source lock 测量误差
- **当前声明**：`requirements.txt` SHA-256 `7e8c14d6...79c93`
- **实测值**：`d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a`
- **直接证据**：
  - `shasum -a 256 requirements.txt` → `d1517613...15d3a`
  - `git show f7b452f9:requirements.txt | shasum -a 256` → `d1517613...15d3a`
  - `git log --oneline -- requirements.txt` → 仅 `ddf0ca6e`（初始 commit）
  - 文件内容从未变更；plan 记录的 SHA-256 在任何 commit 上都不存在
- **影响分析**：
  - 文件内容正确且未变更（12 lines，与 plan 声明一致）
  - plan 对该文件的修改指令（删除 `[web]` extra 消费）仍然正确有效
  - 不影响 implementation 的正确性或可验证性
  - Controller 在进入 implementation 前会按 plan §2.2 要求重新锁定所有输入，届时会自然
    发现并纠正
- **严重程度**：LOW — 纯文档级测量误差；不改变产品 contract、owner、allowlist 或任何 gate；
  不阻塞 implementation authorization
- **建议处置**：Controller 在 implementation preflight 时用实测值更新 source lock；不需要
  plan amendment 或 wording fix
- **不可与已裁决产品问题混淆**：这不是 requirements.txt contract 错误、不是 scope creep、
  不是 gate 弱化，不重开任何已 closed finding

## 9. Non-findings（经审查确认不构成 finding）

1. **FMP resolver parameter name**：plan §6.2 rule 4 写 `resolve_company_info(canonical)`，
   实际方法签名为 `resolve_company_info(canonical_ticker: str)`。这是参数名的文字差异，不
   影响 public method contract。实现 Agent 应使用实际签名。已在 first-round DS review 中认定
   为 non-finding，维持不变。

2. **Plan readiness marker**：plan line 886 仍写
   `READY_FOR_CONTROLLER_PLAN_WORDING_FIX_VALIDATION`。该 marker 是 Codex wording fix 的
   gate marker；Controller 已通过该 validation。按 plan review 规则，本路不修改 plan，marker
   更新是 Controller 在最终 adjudication 后的职责。

3. **Windows quoting algorithm 延迟**：plan §6.5 正确标记为 `PENDING_RELEASE_BLOCKER`，不
   声称 closed。这是正确设计，不是缺口。

4. **I2 对 I1 的潜在回归**：plan §8.1 要求 I2 完成后重跑全部 cumulative validation（包括
   I1 tests），可捕获任何意外回归。不是 plan 缺陷。

5. **Implementation crash recovery**：若实现 Agent 在 WP-A 完成后 crash，tree 处于 broken
   state。plan 明确禁止 WP-A/WP-B 之间有 checkpoint，因此不存在"crash 后从 broken
   checkpoint 恢复"的问题。实现 Agent 可从 git 恢复到 accepted-plan commit。

## 10. Residual risks

| Risk | Severity | Destination |
|---|---|---|
| Windows quoting algorithm 需真实 `windows-latest` / `cmd.exe` 反证 | 中 | R11 release gate（`PENDING_RELEASE_BLOCKER`） |
| I1 coordinated patch 复杂度（8 文件跨模块类型替换） | 低 | 实现 Agent 技术约束；correction loop 设计正确 |
| `requirements.txt` source lock 测量误差 | 低（文档） | Controller implementation preflight 纠正 |
| FMP resolver parameter name 文字差异 | 可忽略 | 实现 Agent 使用实际签名 |

## 11. Findings ledger

| Finding | Status | Evidence |
|---|---|---|
| `R11-IMP-BF01` | CLOSED | 只有两个 slices；无 producer-only checkpoint；无旧三-slice 残留 |
| `R11-PR-BF-RR-F01` | CLOSED | Controller §4 五项 wording requirement 在 §5.1/§5.3/§8.1/§9.1 一致完整；禁止方案零引入 |
| `R11-PR-BF-RR-DS-F01`（新） | OPEN / LOW | `requirements.txt` SHA-256 声明与实测不匹配；纯文档级测量误差 |

## 12. Final plan review conclusion

**PASS / ONE LOW FINDING / ZERO BLOCKER。**

五项目标独立证明全部通过：

1. **R11-IMP-BF01 仍 closed**：只有 R11-I1 atomic Fins+CLI cutover → R11-I2 packaging 两个
   slices；无 producer-only checkpoint/commit/review/handoff。
2. **R11-PR-BF-RR-F01 已正确关闭**：Controller §4 五项 wording requirement 在 §5.1、§5.3、
   §8.1、§9.1 一致、完整、自足；未引入任何禁止方案。
3. **全部 gates 未弱化**：Fins correction loop、combined revalidation、full pyright 0、
   Ruff 0.15.11 baseline、per-file coverage ≥80%、security/deferred scans、Windows
   PENDING_RELEASE_BLOCKER 均完整保留。
4. **Plan 仍 code-generation-ready**：未引入 transactional editor、rollback framework、兼容层、
   第三 slice、中间 commit、R12/deferred Issue 或统一 authorization。所有 exact allowlist、
   typed models、classification rules、grammar locks、validation commands 可直接交给实现
   Agent 执行。
5. **Adversarial review 完成**：architecture boundary、semantic owner、OLD rule coverage、
   edge case analysis、overcoupling/overengineering/best-practice 全部通过。发现一项 LOW
   severity 文档级 source lock 不匹配（`requirements.txt` SHA），不影响产品 contract 或
   implementation correctness。

已裁决产品问题未被重开。所有 Controller-owned artifacts 未被触碰。

READY_FOR_CONTROLLER_R11_PLAN_BOUNDARY_FINAL_REREVIEW_ADJUDICATION
