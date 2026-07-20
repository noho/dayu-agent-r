# WU-SEMANTIC-OWNERSHIP-01 / R11 amended-plan boundary re-review（AgentDS 第二路）

## 1. Gate、scope 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- reviewed target：R11 amended plan `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，
  848 lines / 70,036 bytes，SHA-256
  `9d46ecfc74ced43b6f4868405fbee426523cee754456f0f2131aa3c4dd917be0`。
- review type：complete amended-plan re-review（第二路），不是 delta-only。
- review focus：证据证明或反证 R11-IMP-BF01 是否关闭；完成 Controller 指定的七项完整挑战。
- Agent verdict：**PASS / ONE FINDING / ZERO BLOCKER**。

R11-IMP-BF01 已由 amended plan 关闭。plan 内发现一项 MEDIUM 级别的 implementation workflow 表述精准度不足，但不阻塞
implementation authorization。所有原始产品裁决、cumulative gates、security/deferred 边界均未被弱化或重开。

## 2. Before / final locks

| Lock | 实测值 | Verdict |
|---|---:|---|
| amended plan SHA-256 | `9d46ecfc74ced43b6f4868405fbee426523cee754456f0f2131aa3c4dd917be0` | PASS，逐字节匹配 |
| amended plan lines / bytes | 848 / 70,036 | PASS |
| accepted-plan commit | `f7b452f992b4797b32fea7c6f7212b5ec4345ec1` | PASS |
| `AGENTS.md` | 128 lines / `cb26618a...ac45e` | PASS |
| Controller adjudication (S1 stop) | `b53f0c7546801a48d465b70c66a1fbf0f51fd3cd2cec595b449a3e56364db600` | PASS |
| AgentCodex fix evidence | `4d91a4be8b37cc78246cccf81df38ae15bc23317534ba91b48eb0c76bc323e21` | PASS |
| Controller boundary fix validation | `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-boundary-fix-controller-validation.md`（已完整读取） | PASS |
| AgentMiMo 第一路 re-review | 第一路已在 Controller handoff 中提及；本路独立执行，不依赖第一路结论 | — |
| CURRENT `dayu/fins/upload_batch.py` | 376 lines / `6767d30c...d6178` | PASS |
| CURRENT `dayu/cli/commands/fins.py` | 1,057 lines / `0db8ff2d...c95a6` | PASS |
| CURRENT `dayu/cli/arg_parsing.py` | 932 lines / `a0e25ad6...c1c2c` | PASS |
| CURRENT FMP resolver | `resolve_company_info(canonical_ticker) -> FmpCompanyInfo`，方法存在且返回
  `canonical_ticker`/`company_name`/`ticker_aliases` | PASS |
| CURRENT `normalize_ticker` | `dayu/fins/ticker_normalization.py:84`，签名 `(raw: str) -> NormalizedTicker` | PASS |
| staged tree | `git diff --cached --name-only` = empty | PASS |

本路未修改任何 product/test/README/design/CI/Controller control 或其它 Agent artifact；未 stage/commit/push/PR。

## 3. R11-IMP-BF01 封闭性证据

### 3.1 Root cause 确认

CURRENT `dayu/fins/upload_batch.py` 仍定义并导出通用 `UploadBatchPlanEntry`（含 `command_name`、`files: tuple[Path, ...]`）
与 `UploadBatchPlanResult`（含 `entries: tuple[UploadBatchPlanEntry, ...]`）。CURRENT `dayu/cli/commands/fins.py` 静态 import
`UploadBatchPlanEntry`、读取 `plan.entries`、`entry.command_name`、`entry.files`，并将这些字段投影为 JSON argv。

原 accepted plan 的 S1 exact allowlist 只有 `dayu/fins/upload_batch.py` 与 `tests/fins/test_upload_batch.py`，禁止修改 CLI
consumer。因此 producer-only 删除旧 generic 类型/字段会直接破坏 CLI 的 import/attribute/type contract（full pyright 从 0
errors 变为非零），而保留旧 surface、property、alias 或 dual reader 又违反 AGENTS 的 no-compat 与 accepted plan 的唯一 typed
owner 约束。这是 producer-consumer atomic contract cutover 的直接逻辑矛盾，不是测试或实现技巧问题。

### 3.2 修复正确性

Amended plan 的修复是：

1. 把原 S1（Fins producer）与原 S2（CLI consumer/renderer）合并为同一个 atomic slice `R11-I1`，内含两个 ordered work
   packages WP-A 与 WP-B，但二者之间无 checkpoint/acceptance/commit/full validation/handoff 或 next-slice transition。
2. 原 S3（packaging/placeholder/README/Windows）成为第二个 slice `R11-I2`。
3. 保留 Fins 为分类/财期/material/skip 唯一 owner，CLI 为 argv/renderer/publisher/summary 唯一 owner。
4. I1 的 exact allowlist 精确 union 原 S1+S2 八个 product/test 路径，不增不减。
5. Consumer gap 发现时只允许 Fins owner 两路径 targeted correction，CLI 继续机械消费；随后重跑全部 producer+consumer
   cumulative validation。
6. 两 slices 全部完成后才做一次 cumulative dual code review/fix/re-review。

这是同时保持唯一 semantic owner、strict typing、full-pyright-clean tree 与 no-compat 的最窄合法修复。没有更小的合法
checkpoint 方案。

### 3.3 旧三-slice 残留扫描

执行独立遗留扫描：

```bash
rg -n 'R11-S[123]|S1[[:space:]]*->[[:space:]]*S2|三[个份][[:space:]]*slice|S1 checkpoint|S2 checkpoint|S3 checkpoint|进入 S[123]|回到 S[123]|从 S[123]'
```

结果：exit 1，stdout empty。唯一的 bare `S1` 命中在 plan line 12，是引用 Controller-owned authorization/stop/adjudication
artifact 的历史专名，不是当前 state-machine node。

```bash
rg -n '\bS2\b|\bS3\b'
```

结果：exit 1，stdout empty。旧三-slice state transition 零残留。

正向两-slice propagation 命中：

- line 211: `## 5. Atomic slice R11-I1 / WP-A`
- line 348: `## 6. Atomic slice R11-I1 / WP-B`
- line 514: `## 7. Slice R11-I2`
- line 749: `严格顺序精确两个 implementation slices`
- line 762: `-> one cumulative code-review gate`

所有 `checkpoint` 命中经逐项人工审阅后只属于四类合法语义：明确禁止 WP-A/WP-B 中间 checkpoint、WP-A+WP-B 共同 cutover 后
的唯一 `R11-I1 atomic checkpoint`、I2 完成后的 `R11-I2 checkpoint`、acceptance checklist 复述。不存在 producer-only
checkpoint、CLI-only checkpoint、work-package acceptance、work-package commit 或第三 slice transition。

**R11-IMP-BF01: CLOSED。**

## 4. Controller 七项完整挑战逐项裁决

### 4.1 I1 merged context 是否是最小合法 atomic cutover 且实现后可 full-pyright-clean

**证据与结论：是。**

I1 allowlist（plan §4 lines 200-205）精确 union 原 S1 两路径（`dayu/fins/upload_batch.py`、owner test）与原 S2 六路径
（`dayu/cli/commands/fins.py`、`dayu/cli/arg_parsing.py`、新增 `dayu/cli/upload_script.py`、三个 CLI test files）。没有引入
Service、storage、runtime、design、constraints 或其它非 owning 路径。

Full-pyright-clean 成立的条件：
- WP-A 产出新 typed `UploadBatchFilingEntry`/`UploadBatchMaterialEntry`/`UploadBatchSkippedEntry`/`UploadBatchPlan` 替换旧
  `UploadBatchPlanEntry`/`UploadBatchPlanResult`；
- WP-B 同时删除旧 import、`plan.entries`、`entry.command_name`、`entry.files` 消费，改用新 typed contract；
- 新增 `dayu/cli/upload_script.py` 是全新模块，无旧依赖；
- 所有 consumers（CLI、tests）在同一 patch set 中切换到新 contract。

同时替换 producer 定义与所有 consumer 引用后，full pyright 应保持 0 errors。如果新 typed contract 的任一字段、枚举或
optional rule 有误，会在 WP-B 首个真实 consumer 消费时立即暴露——这正是 plan §5.3/§9.1 的 owner correction loop 设计目标。

更小的合法 checkpoint 不存在：不能只改 producer 而让旧 consumer import 失败，也不能在 producer 中保留旧 generic
surface（违反 no-compat）。唯一更小方案是保留原三-slice 但允许 transient broken pyright——已被 Controller 明确拒绝。

**I1 是最小合法 atomic cutover。** 唯一表述性风险见 §6 Finding R11-PR-BF-RR-F01。

### 4.2 "no observable broken tree" 与 material preflight/stop 是否冲突

**证据与结论：不冲突，但表述需更精确。**

Plan §5.1 要求 "不得留下'新 producer + 旧 consumer'的 transient broken working tree"，§9.1 要求 "WP-A/WP-B 之间无可观察
broken tree、stop/handoff/checkpoint/accept/commit/full validation"。这里的 "no observable broken tree" 的正确语义是：

- 不得在 WP-A 完成后运行任何 validation gate（pyright、tests、coverage、Ruff、diffcheck）；
- 不得以 "producer-only" 状态做 checkpoint、acceptance、commit 或 handoff；
- 不得让 Controller 或下游 Agent 观察到 producer-changed + consumer-unchanged 的中间 tree 作为 gate input。

但这不意味着实现 Agent 在顺序编辑文件时文件系统从不出现瞬时不一致。实现 Agent 逐个文件写入时必然存在 producer 已改但
consumer 尚未改的瞬时窗口。plan 对此的约束应更精确地区分：gate/validation boundary（禁止）vs. 编辑 session 内的瞬时
文件系统状态（允许但不验证）。

Material preflight（source locks 验证、Ruff version oracle 匹配）发生在 mutation 之前，不受此约束影响。Material stop
conditions 在 coordinated cutover 完成后统一检查，不会因为 "中间不检查" 而遗漏——plan §5.3/§6.6 的 stop 条件覆盖了所有
需要触发 stop 的场景。

**不冲突。** 但见 §6 Finding R11-PR-BF-RR-F01 的表述精准度建议。

### 4.3 I1/I2 test/package/README consumers 是否按依赖切开而不会产生第二个 broken checkpoint

**证据与结论：是，不会产生第二个 broken checkpoint。**

I1（Fins+CLI atomic cutover）产出稳定的 typed producer contract，I2（packaging/placeholder/README/Windows）只消费 I1
已锁定的 contract，不回改或扩张 I1 产品范围。

I2 的唯一变更：
- 删除六个 Web/WeChat/render placeholder package 文件；
- 从 `pyproject.toml` 删除 placeholder entrypoints/web extra/package-data；
- 从 `requirements.txt` 删除 `[web]` extra 消费；
- 新增 Windows workflow；
- 更新四个 README；
- 更新 `test_public_package_entrypoints.py`（删除 placeholder contract、保留 Docling tests）。

这些变更的 blast radius 分析：
- Placeholder package 文件没有 production consumer（它们的 `__init__.py`/`__main__.py` 只 print unavailable 并 exit 非零）；
- `pyproject.toml` entrypoint 删除不影响 `dayu-cli`（唯一保留的 entrypoint）或 I1 的 Fins/CLI 模块；
- `requirements.txt` 的 `[web]` extra 删除不影响 I1 的 test/dev 依赖；
- Windows workflow 是新增文件，与 I1 无冲突。

唯一需要验证的交叉点是：I2 的 wheel smoke 使用 `pip wheel` 构建后验证 importability 与 metadata。如果 I1 的代码变更
引入了新的 import 依赖而 `pyproject.toml` 未声明，wheel smoke 的隔离安装会暴露该问题。这正是 plan §8.1/§9.1 要求 I2
完成后重跑 cumulative validation 的原因。

Plan §7 line 626 明确："本 slice 不回改或扩张 R11-I1 产品范围"。I1 checkpoint 与 I2 checkpoint 之间的唯一依赖是 I1 的
typed contract 稳定存在——这是正常的 dependency order，不是 broken checkpoint。

**不会产生第二个 broken checkpoint。**

### 4.4 Consumer gap correction 是否只在 Fins owner 且重跑 combined validation

**证据与结论：是，约束完整。**

Plan §5.3 lines 335-346：
- "不得 checkpoint、不得在 CLI 补偿，也不得退出 atomic slice 回到一个虚构的 producer-only state"
- "按 §9.1 在同一 R11-I1 内对 dayu/fins/upload_batch.py 与 tests/fins/test_upload_batch.py 做 Fins owner targeted correction"
- "再重跑 producer+consumer 全部 cumulative contract/tests/scans/smoke/full validation"
- "不得扩大 allowlist、建立兼容 seam 或创建新 sub-WU/slice/commit"

Plan §6.6 lines 508-512：
- "WP-B 首次消费暴露的 Fins typed gap 不是下游 stop/fallback 许可"
- "必须按 §5.3/§9.1 在同一 atomic slice 回到 Fins owner targeted correction"
- "严禁在 builder/renderer/adapter/test fixture 补偿"

Plan §9.1 lines 770-775：
- "状态保持在 R11-I1 coordinated implementation：只在 Fins owner 路径做 targeted correction"
- "CLI 继续机械消费同一 source of truth"
- "修复后必须重跑 §5.3、§6.6、§8 对 producer+consumer 的全部 cumulative contract/tests/scans/smoke/coverage/full pyright/Ruff"

三处约束一致且无歧义：correction 只在 Fins owner path，combined validation 必然重跑，CLI/adapter/fixture 禁止补偿。

**Consumer gap correction 边界完整。**

### 4.5 原 cumulative allowlist、typed owner/current CLI projection/POSIX 和 Windows/wheel smoke、changed-file coverage>=80、full pyright、Ruff 0.15.11 baseline、Windows PENDING_RELEASE_BLOCKER、security/deferred/no-touch/no-push 是否未弱化

**证据与结论：全部保留，未弱化。**

逐项独立验证：

| Gate | 原始位置（旧 plan） | Amended plan 对应 | 弱化？ |
|---|---:|---|---|
| cumulative closed allowlist | 旧 §3 / §9 product allowlist | §4 lines 162-208，I1+I2 exact union | 否，仅重组 |
| Fins typed owner | 旧 §4 semantic owner map | §4 lines 146-160，同表 | 否 |
| CLI projection owner | 旧 §6 当前 grammar | §6.2 lines 381-411，同 contract | 否 |
| POSIX recorder smoke | 旧 §6 POSIX smoke | §6.6 lines 487-505，同 `/bin/sh` + recorder | 否 |
| POSIX real Service/Fins smoke | 旧 §6 real smoke | §6.6 lines 491-505，同 AAPL fixture + temp storage | 否 |
| Windows recorder smoke | 旧 §7 Windows | §7.2 lines 547-591，同 `cmd.exe` + JSONL | 否 |
| Windows real CLI smoke | 旧 §7 Windows | §7.2 lines 582-586，同 grammar + temp storage | 否 |
| wheel smoke (5 oracles) | 旧 §8 wheel | §7.3 lines 595-622，同 METADATA/entry_points/extracted/RECORD/importability | 否 |
| changed-file coverage >=80 | 旧 §8 coverage | §8.2 lines 672-684，同单文件 line coverage ≥80.00 | 否 |
| full pyright 0 errors | 旧 §8 pyright | §8.1 line 638，`python -m pyright dayu/ tests/ utils/` 零错误 | 否 |
| Ruff 0.15.11 baseline | 旧 §8 Ruff | §8.1 lines 662-669，同 version oracle + 144-finding baseline + current-only=empty | 否 |
| Ruff version drift stop | 旧 §8 Ruff | §8.1 lines 665-667，"版本漂移立即 stop" | 否 |
| Windows PENDING_RELEASE_BLOCKER | 旧 §7 / §9 | §7.2 lines 588-591、§9.2、§9.4 lines 817-824 | 否 |
| source/output containment | 旧 §5 / §6 security | §5.2 rule 1-3、§6.3 lines 419-428 | 否 |
| symlink rejection (root-self / root-internal) | 旧 §5 / §6 | §5.2 rule 1、§6.3 lines 420-423 | 否 |
| external ancestor symlink allowed | 旧 §5 / §6 | §5.2 rule 1 line 258、§6.3 line 422 | 否 |
| same-dir atomic replace | 旧 §6 publisher | §6.3 line 424，`os.replace` + temp cleanup | 否 |
| POSIX mode 0o755 | 旧 §6 | §6.3 line 424 | 否 |
| Windows delayed expansion off | 旧 §6 / §7 | §6.5 line 459、§8.3 scan line 700 | 否 |
| argv injection marker | 旧 §6 security | §6.5 line 454、§6.6 line 489 | 否 |
| secret non-persistence | 旧 §6 security | §6.3 line 428、§8.3 lines 701-702 | 否 |
| deferred Issues (142/151/175/177/178) | 旧 §3 / §8 | §3.3 lines 134-135、§8.3 line 739 | 否 |
| R12 no-touch | 旧 §1 / §3 | §1 line 8、§3.3 line 136 | 否 |
| no-push/PR | 旧 §1 / §9 | §1 line 16-17、§9.3 line 807 | 否 |
| Service/storage/runtime/FMP/ticker/design/constraints no-diff | 旧 §3 / §8 | §3.3 lines 139-140、§8.3 line 710 | 否 |
| Topic 8/9 no-touch | 旧 §3 | §3.3 lines 138-139 | 否 |

所有 gate 逐项保留。唯一重新组织的是 validation sequencing：旧 plan 在 S1/S2/S3 各自 checkpoint 运行 validation，amended
plan 在 I1 joint cutover 后运行一次 producer+consumer cumulative validation，I2 后再运行一次 final cumulative validation。
这不是弱化——I1 的 joint validation 覆盖了原 S1+S2 的合并范围，且 plan 明确禁止以 I1 validation 冒充 final pass（§8.1
line 636-638）。

**所有 gate 未弱化。**

### 4.6 旧三-slice/提前 review/commit/acceptance/compatibility seam 是否零残留

**证据与结论：零残留。**

- 旧三-slice `R11-S1 -> R11-S2 -> R11-S3` 全文中零命中（见 §3.3 独立扫描）。
- 提前 review：plan §9.1 line 777-779、§9.2 明确 code review 只在两 slices 全部完成后执行一次，无中间 slice/work-package
  review。
- 提前 commit：plan §9.1 line 778 "两个 slices 之间不做 slice acceptance、code-review gate 或 commit"，§9.2 line 797
  "Agent 不得自行 stage/commit"。
- 提前 acceptance：plan §9.1 line 777 "两个 slices 之间不做 slice acceptance"。
- Compatibility seam：plan §4 line 209 明令禁止 old/new dual surface、generic alias/property/wrapper、CLI loose
  parsing/fallback/重算、下游 adapter。plan §5.1/§6.1/§9.1 反复禁止 compatibility alias/property/wrapper/dead
  dataclass/union adapter/`hasattr/getattr`/dual reader。Plan §6.5 line 461 禁止 Windows compat/fallback/双算法/platform
  test shim。

AgentCodex fix evidence §5.1 的遗留扫描已证明旧三-slice reference 零命中；本路独立复验一致。

**零残留。**

### 4.7 原产品裁决是否被重开或扩 scope

**证据与结论：未被重开或扩 scope。**

对照 Topic 7 final adjudication（Controller discussion lines 521-619）：

| Topic 7 裁决 | Amended plan disposition | 重开？ |
|---|---|---|
| `upload_filings_from` 生成平台可执行脚本，不是 JSON | §6.2/§6.4/§6.5 产出 POSIX `.sh` / Windows `.cmd`；§8.3 删除 JSON schema/argv scan | 否 |
| 删除未实现 placeholder entrypoints | §7.1 删除六个 Web/WeChat/render package 文件与对应 pyproject/requirements/README surface | 否 |
| 保留 ISSUE trackers 为 product backlog | §3.3 不实现 Issue 142/151/175/177/178、#84、#147 | 否 |
| Fins 拥有 batch plan，CLI 拥有脚本渲染 | §4 semantic owner map、§5 Fins owner、§6 CLI owner | 否 |
| 不迁移 OLD 架构 | §2 authority order line 52-53 "OLD 不拥有当前架构、API、类型或兼容需求" | 否 |
| `dayu-cli init` 独立处理 | §3.3 "不进入 R12 init" | 否 |

对照 original accepted plan re-review Controller adjudication（R11-PR-F01—F06 closed），六个原始 finding 的 closed 裁决均
在 amended plan 中保留：
- F01: typed field checklist → §5.3 mapping table
- F02: containment/symlink → §5.2 rule 1-3 + §6.3
- F03: `--infer`/`--overwrite` → §6.2 rule 4/6
- F04: wheel oracles → §7.3
- F05: AAPL fixture → §6.6
- F06: call cap=0 + Ruff baseline → §5.2 rule 10 + §8.1

**原产品裁决未被重开或扩 scope。**

## 5. 其它 adversarial review lenses

### 5.1 Architecture boundary

- Fins production 零 `dayu.cli/service/host/engine/ui` import（plan §8.3 line 731）：当前 `upload_batch.py` 的 import 只有
  `__future__`、`re`、`collections.abc`、`dataclasses`、`pathlib`、`typing`。符合。
- Renderer 零 filename/fiscal/material/cap regex（plan §8.3 line 731）：plan §6.2 要求 renderer 只消费 tuple argv，由单一
  builder 做 field-to-flag 投影。符合。
- 分层 `UI -> Service -> Host -> Engine` 未被穿透：plan §3.3 禁止修改 Service/Host/Engine，§6.2 line 378 明确
  `upload_filings_from` 不创建 direct Service。符合。

### 5.2 Overcoupling

- I1 allowlist 把 producer 与 consumer 放入同一 slice，这不是过度耦合——这是 static type contract 原子切换的必要条件。
  plan 明确这是 contract cutover 的耦合，不是功能耦合：Fins 仍独立拥有分类规则，CLI 仍独立拥有渲染规则；二者的唯一共享
  是 typed contract interface。
- I2 与 I1 之间只有 dependency order（I2 需要 I1 的 contract 稳定），没有双向依赖或共享可变状态。符合。

### 5.3 Overengineering

- Plan 拒绝新增 JSON fallback、第二 renderer、shell-specific 业务分支、generic authorization、extra payload、compat
  re-export/wrapper/alias。符合 AGENTS 的"不做过度设计"。
- Plan 拒绝为 Windows quoting 预猜算法或固定 iteration count，而是要求真实 runner 反证后锁定。这是正确的 evidence-driven
  approach，不是 overengineering。
- Wheel smoke 的五个 Python negative oracle 是精确的 contract 验证，不是过度设计——它们是删除 placeholder package 后确保
  wheel 干净的唯一可审计手段。

### 5.4 Best-practice

- 每个 changed production file 有独立 line coverage 阈值（不是总覆盖率）：§8.2。
- Full pyright 保持 0 errors：§8.1。
- Ruff baseline delta 用 set difference（不是只看 exit code）：§8.1。
- 真实 `/bin/sh` 与 `cmd.exe` recorder 而非 mock：§6.6、§7.2。
- Wheel smoke 用隔离 venv 验证 importability：§7.3。
- Security scan 分离 comment/body 证明 executable body 无 secret：§8.3 line 737-738。

### 5.5 Optimal-solution

- 原 3-slice 改为 2-slice 是把不可能的 checkpoint 修正为可行的 atomic cutover。没有更小的合法方案。
- 保留两个 ordered work packages 而非要求单次全文件写入是完全合理的：WP-A 定义 contract，WP-B 消费 contract，但两者之间
  不设 gate。这为实现 Agent 提供了逻辑顺序而不创造非法 checkpoint。

## 6. Finding

### R11-PR-BF-RR-F01 — "no observable broken tree" 表述对实现 Agent 顺序编辑工作流不够精确

- **位置**: §5.1 lines 222-223、§9.1 lines 753-755
- **问题类型**: 不可直接实施（implementation workflow 约束表述精准度不足）
- **当前写法**: "不得留下'新 producer + 旧 consumer'的 transient broken working tree"（§5.1）；"WP-A/WP-B 之间无可观察
  broken tree"（§9.1）
- **反例/失败场景**: 实现 Agent 编辑 I1 的八个文件时必然顺序执行：先改 `upload_batch.py` 的定义，再改 `fins.py` 的 import，
  再改 `arg_parsing.py` 的 grammar，再改 `upload_script.py`（新文件），再更新测试文件。在编辑 session 中，文件系统在
  producer 已改但 consumer 未改的瞬时窗口中客观存在 import/type 不一致。若实现 Agent 严格按字面解释 "no observable broken
  tree" 为"文件系统任一时刻都不能出现不一致"，则需要同时写入所有八个文件——这在标准编辑工具中不可行。
- **为什么有问题**: Plan 的正确意图是 gate/validation/checkpoint/handoff boundary 约束（不得在中间状态运行 pyright、tests、
  coverage、Ruff，不得做 checkpoint、acceptance、commit、handoff），但当前措辞可被误读为禁止实现 Agent 顺序编辑时的瞬时
  文件系统不一致。这会迫使实现 Agent 要么误解约束、要么在首次 validation 失败时过度保守地 stop。
- **直接证据**:
  - Plan §5.1 line 222-223："不得留下'新 producer + 旧 consumer'的 transient broken working tree，也不得以 compatibility
    seam 维持旧 consumer"
  - Plan §9.1 line 755："WP-A/WP-B 之间无可观察 broken tree、stop/handoff/checkpoint/accept/commit/full validation"
  - 同时 plan §9.1 line 765-767 又说："禁止先删除 old producer surface 并把仍消费旧 contract 的 tree 留作工作状态、
    validation 输入或 handoff"——这里的"工作状态、validation 输入或 handoff"才是真正的禁止对象
  - 实现 Agent 必须编辑 3 个已有 production files、1 个新增 file、4 个 test files 才能完成 coordinated patch
- **影响**: 实现 Agent 可能误解约束导致过度保守 stop，或在编辑中间步骤意外触发 validation 工具（如 IDE 自动 pyright）
  后误判为 plan violation
- **建议改法和验证点**: 在 §5.1 或 §9.1 增加一句澄清："实现 Agent 顺序编辑文件时文件系统可能存在瞬时不一致；'no observable
  broken tree' 指不得在此瞬时状态运行任何 validation gate（pyright、tests、coverage、Ruff）、做 checkpoint、请求
  acceptance、stage、commit 或 handoff。只有 WP-A+WP-B 全部文件协调完成后才可运行首次 validation。" 验证：实现 Agent 正确
  理解可顺序编辑，且不会在中间步骤运行 validation
- **修复风险**: 低（纯表述澄清，不改变 plan contract、allowlist、gate 或 state machine）
- **严重程度**: 中（不影响 plan 正确性，但可能造成实现 Agent 误解或过度保守 stop；不阻塞 implementation authorization）

## 7. Open questions

无。所有 Controller 指定的挑战项均已用直接 plan/code/真源证据封闭。

## 8. Residual risks

- **Implementation execution risk**：I1 coordinated patch 的复杂度较高（8 个文件的跨模块类型替换），实现 Agent 可能需要在
  owner correction loop 中迭代。plan 的 correction loop 设计正确（只改 Fins owner + 重跑 combined validation），但迭代次数
  和 wall-clock 成本取决于实现 Agent 首次 cutover 的精准度。这不是 plan 缺陷，是正常 implementation risk。
- **Windows quoting convergence**：plan 正确地把 quoting algorithm 留给真实 `cmd.exe` runner 反证，不预猜算法。如果真实
  Windows run 暴露多轮反例，owner correction path 仍在同一 renderer 内收敛，不扩大 allowlist。这是已知的
  `PENDING_RELEASE_BLOCKER` 风险，不是 plan 缺口。
- **FMP resolver parameter name**：plan §6.2 rule 4 写 `resolve_company_info(canonical)`，而实际签名为
  `resolve_company_info(canonical_ticker: str)`。这是参数名的文字差异，不影响实现。实现 Agent 应使用实际签名。

## 9. Final plan review conclusion

**PASS / ONE FINDING / ZERO BLOCKER。**

R11-IMP-BF01 已被 amended plan 正确关闭。plan 的 atomic cutover boundary fix 是同时满足唯一 semantic owner、strict typing、
full-pyright-clean tree 与 no-compat 的最窄合法方案。

一项 MEDIUM finding（R11-PR-BF-RR-F01）指出 "no observable broken tree" 表述对实现 Agent 顺序编辑工作流不够精确，建议在
implementation authorization 中由 Controller 补充澄清。该 finding 不阻塞 implementation authorization——plan 的正确意图已
在 §9.1 的详细禁止列表中充分表达，只是总结性措辞可更精确。

所有原始产品裁决、cumulative gates、security/deferred 边界均保留且未被弱化；旧三-slice 残留、提前 review/commit/acceptance、
compatibility seam 均为零残留。

READY_FOR_CONTROLLER_ADJUDICATION
