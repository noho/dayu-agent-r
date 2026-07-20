# WU-SEMANTIC-OWNERSHIP-01 / R11 final-plan source-lock re-review（DS route）

## 1. Gate、输入与 authority

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue。
- gate：Controller validated source-lock fix 后的 DS-route complete final-plan re-review。完整审查最终 886 行 plan，不是
  one-cell delta。
- reviewed target：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
  （886 lines / 74,571 bytes / SHA-256 `59156239ff4d73bfeaa1cb78a593c2b75504804102a07e851b1239803a4de51f`）。
- authority order（plan §2.1）：`AGENTS.md` → design docs → Controller Topic 7 → umbrella plan → umbrella control →
  production code → OLD files 仅作为分类规则证据。
- 本 review 不授权 implementation、stage、commit、push、PR 或 R12。

### 1.1 审查输入完整 identity

| Artifact | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| plan（最终） | 886 | 74,571 | `59156239ff4d73bfeaa1cb78a593c2b75504804102a07e851b1239803a4de51f` |
| Controller final-rereview adjudication | 95 | 5,636 | `71549dc841a57f663f2e0f07fe46ea0a3535fae7c226e48978d5ecf6819d5095` |
| AgentCodex source-lock fix evidence | 133 | 6,986 | `569d01b1ac231ba6a3cd48c76976e7e4e32db74671308372e6d3cfd0b3c54fca` |
| Controller fix validation | 72 | 4,025 | （直接读取 working tree 当前内容） |
| AGENTS.md | 128 | 10,036 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |

## 2. 独立 source-lock 复测与 finding closure 证明

### 2.1 R11-PR-BF-FR-DS-F01 — CLOSED 证明

#### Plan line 71 exact cell

```
| CURRENT `requirements.txt` | 12 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
```

- 旧值 `7e8c14d6`：零命中（`rg -c '7e8c14d6'` exit 1）。
- 正确 full SHA-256：精确一处命中，位于 plan line 71。
- 计划总行数不变：886。

#### 三路 requirements.txt hash 独立复测

| Source | SHA-256 |
|---|---|
| working tree `requirements.txt` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
| accepted-plan commit `f7b452f992b4797b32fea7c6f7212b5ec4345ec1` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
| R10 completion baseline `2b14b2fbc89654267e3d33daa2ae410ceff45e68` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |

复测命令与原始输出：

```text
$ shasum -a 256 requirements.txt
d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a  requirements.txt

$ git show f7b452f992b4797b32fea7c6f7212b5ec4345ec1:requirements.txt | shasum -a 256
d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a  -

$ git show 2b14b2fbc89654267e3d33daa2ae410ceff45e68:requirements.txt | shasum -a 256
d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a  -
```

**三路完全一致。旧错误值零残留。`R11-PR-BF-FR-DS-F01` 已 CLOSED。**

### 2.2 R11-IMP-BF01 — 仍 CLOSED 证明

最终 plan 精确只有两个 implementation slices：

1. `R11-I1 atomic Fins+CLI cutover`（§5 + §6）：合并 WP-A Fins owner contract 与 WP-B CLI consumer/renderer
   cutover。WP-A/WP-B 不构成独立 state-machine node，无 producer-only checkpoint、acceptance、stage、commit、
   handoff 或 review。
2. `R11-I2 packaging/README/Windows gate`（§7）：仅 I1 checkpoint pass 后执行。

代码证据：
- `R11-I1` merged exact allowlist 精确包含 8 个文件（production + tests），等于原 producer + consumer allowlists
  的并集。
- WP-A owner 路径 `dayu/fins/upload_batch.py` + `tests/fins/test_upload_batch.py` 不构成独立 slice。
- WP-B owner 路径 `dayu/cli/commands/fins.py` + `dayu/cli/arg_parsing.py` + `dayu/cli/upload_script.py` + 三个 test
  files 不构成独立 slice。
- 两者共同使用 `R11-I1` merged exact allowlist，无 work-package checkpoint。
- `R11-I2` 精确使用原 packaging slice allowlist，scope 未扩。

**`R11-IMP-BF01` 仍 CLOSED。**

### 2.3 R11-PR-BF-RR-F01 — 仍 CLOSED 证明

Plan 明确声明 §5.1/§8.1/§9.1：

> "同一 uninterrupted Agent task 内顺序编辑 WP-A/WP-B 文件。全部 coordinated edits 完成前的 transient
> inconsistency 不是合法 intermediate tree 或 pass/failure baseline"

> "首次 validation 只能在 WP-A/WP-B 全部 coordinated edits 完成后运行"

> "禁止把'先删除 old producer surface、consumer 尚未切换'的 transient tree 呈交为 gate input、checkpoint 或
> handoff"

同时禁止以 compatibility seam 缓解 transient inconsistency。Sequential editing 不要求跨文件事务原子写。
所有 material preflight 必须在 mutation 前完成。真实 blocker 仍安全 stop + failed working evidence。

**`R11-PR-BF-RR-F01` 仍 CLOSED。**

### 2.4 逐 finding closure ledger

| Finding | 本轮独立验证结论 |
|---|---|
| `R11-IMP-BF01` | **CLOSED** — 精确两个 slices；WP-A/WP-B 不构成 state-machine node |
| `R11-PR-BF-RR-F01` | **CLOSED** — sequential edit 无跨文件事务原子写要求；transient inconsistency 不是 gate truth |
| `R11-PR-BF-FR-DS-F01` | **CLOSED** — plan line 71 完整 hash 三路一致，旧值零残留 |

- accepted/open：`0`。
- blocker：`0`。
- actual accepted residual：`0`。

## 3. 关键生产代码 source lock 独立复测

### 3.1 Production files

| File | Lines | Plan lock SHA-256 | 实际 SHA-256 | 匹配 |
|---|---:|---:|---|:---:|
| `dayu/fins/upload_batch.py` | 376 | `6767d30c...6178` | `6767d30c...6178` | ✓ |
| `dayu/cli/commands/fins.py` | 1057 | `0db8ff2d...c95a6` | `0db8ff2d...c95a6` | ✓ |
| `dayu/cli/arg_parsing.py` | 932 | `a0e25ad6...c1c2c` | `a0e25ad6...c1c2c` | ✓ |
| `dayu/fins/resolver/fmp_company_info.py` | 394 | `c2abfbe0...46fa` | `c2abfbe0...46fa` | ✓ |
| `pyproject.toml` | 152 | `e076606d...6a25` | `e076606d...6a25` | ✓ |
| `requirements.txt` | 12 | `d1517613...5d3a` | `d1517613...5d3a` | ✓ |
| `AGENTS.md` | 128 | `cb26618a...c45e` | `cb26618a...c45e` | ✓ |

### 3.2 Ruff baseline

| File | SHA-256 | 匹配 |
|---|---|---|
| `workspace/tmp/r11-ruff-baseline.json` | `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` | ✓ |

### 3.3 环境观察：Ruff version

- 计划锁定：ruff 0.15.11（baseline `051bd6cc...1cea`）。
- 当前 `.venv`：ruff 0.15.9。
- 计划 §8.1 已有 version oracle 机制："版本漂移立即 stop，由 Controller 在同一 implementation 输入树上同时重新锁
  version oracle 与 full baseline"。这不是 plan 缺陷；实现 Agent 在 preflight 阶段会命中该机制，Controller 将重锁。
  产品 contract 不受影响。

## 4. Two-slice owner/state machine 精确验证

### 4.1 State machine graph

```text
R11-I1 coordinated implementation
  全部 material preflight（必须在 mutation 前完成）
  WP-A Fins owner contract + WP-B CLI consumer/renderer cutover
  （同一 uninterrupted Agent task 内顺序编辑；无跨文件事务原子写要求）
  （全部 coordinated edits 完成前：不运行 validation、不做 gate transition）
  （真实 blocker：stop + failed working evidence；不宣称 pass/checkpoint/rollback/扩 scope）
 -> 全部 coordinated edits 完成后的首次 producer+consumer validation
 -> 若真实 consumer 暴露 owner gap：同一 slice 内 Fins owner targeted correction + combined revalidation
 -> producer+consumer cumulative tests/smokes/coverage/full pyright/Ruff/scans
 -> Controller R11-I1 atomic checkpoint
 -> R11-I2 packaging/README/Windows implementation（仅 I1 checkpoint pass）
 -> final cumulative tests/smokes/coverage/full pyright/Ruff/scans + packaging/Windows gate evidence
 -> Controller R11-I2 checkpoint
 -> one cumulative code-review gate
```

**状态机节点**：
1. `R11-I1 coordinated implementation`（entry point）
2. `R11-I1 atomic checkpoint`（Controller 裁决）
3. `R11-I2 packaging/README/Windows implementation`（仅前一 checkpoint pass）
4. `R11-I2 checkpoint`（Controller 裁决）
5. `cumulative code-review gate`（并发双 review + Controller adjudicate + narrow fix + 并发双 re-review）
6. `accepted implementation commit`（Controller 授权；Agent 不自行 stage/commit）

**合法 transition**：严格顺序，无旁路、无回溯（除 Fins correction loop 回到同一 slice 内部重验证）、无 work-package
级 checkpoint。两个 slices 之间不做 slice acceptance、code-review gate 或 commit。

**禁止的 state-machine node**：
- producer-only checkpoint（WP-A 完成后独立 gate transition）
- consumer-only checkpoint（WP-B 完成后独立 gate transition）
- intermediate implementation commit
- "next work package authorization" 在全部 coordinated edits 完成前
- old/new dual surface 作为合法 intermediate tree

### 4.2 顺序编辑与 safety stop 验证

Plan §5.1/§5.3/§8.1/§9.1 四层一致：

1. **顺序编辑许可**：同一 uninterrupted Agent task 可顺序编辑 WP-A/WP-B 文件；不要求跨文件事务原子写。
2. **transient inconsistency 处置**：不是合法 intermediate tree，不是 pass/failure baseline；不运行/宣称
   validation，不做 gate transition；不用 compatibility seam 固化。
3. **安全 stop**：真实 allowlist/source/design/security blocker 出现时停止 mutation；保留当前 diff 为 failed
   working evidence；不继续冒险、不宣称 pass/checkpoint、不自行 rollback、不扩大 scope。该 safety stop 不把
   transient tree 升格为合法 state。
4. **首次 validation**：只在全部 coordinated edits 完成后运行。

**无弱化。**

### 4.3 Fins correction loop 验证

Plan §5.3/§9.1：

- WP-B 首次真实 consumer 暴露 typed fact 缺失、enum mismatch 或 optional ownership gap 时：
  - 状态保持在 `R11-I1 coordinated implementation`
  - 修正只在 Fins owner 路径：`dayu/fins/upload_batch.py` + `tests/fins/test_upload_batch.py`
  - CLI 继续机械消费同一 source of truth
  - **禁止**：在 builder/renderer/adapter/test fixture 补偿；创建新 sub-WU/slice/commit；扩大 `R11-I1` allowlist
  - **必须**：重跑 §5.3 + §6.6 + §8 全部 producer+consumer cumulative validation；不能只重跑 owner tests
  - 收敛后 + combined revalidation 全通过 → Controller 做一次 `R11-I1` atomic checkpoint

**无弱化。**

### 4.4 Combined revalidation 验证

Plan §5.3、§6.6、§8.1 明确：

- Fins correction 后必须 combined revalidation；不得复用此前结果。
- `R11-I2` 完成后必须对最终 cumulative tree 重跑完整 validation，加入 packaging/wheel/README/placeholder/Windows
  evidence；不得复用 I1 结果冒充 final pass。
- 仅 I1 尚未修改的 packaging placeholder negative oracle 保留到 I2 后判零，其余 I1-scope gate 均不得推迟。

**无弱化。**

### 4.5 Full pyright 0、Ruff、coverage、security、deferred、Windows gates 验证

| Gate | Plan 要求 | 是否弱化 |
|---|---|---|
| full pyright | 任何时点不得放宽 `0 errors` | 否 |
| Ruff | 0.15.11 version oracle + scoped 零错误 + full baseline set-difference current-only 为空 | 否 |
| 逐文件 coverage | 每个 changed production file `summary.percent_covered >= 80.00`；禁止 omit/pragma/fake-mock-only/总覆盖率代替 | 否 |
| security | §8.3 四项人工/自动 oracle：反向依赖、propagation、security（containment/symlink/atomic/argv/secret）、deferred | 否 |
| deferred | Issue 142/151/175/177/178、R12、真实 Web/WeChat/render、Topic 8/9、统一 auth 的 production diff 为零 | 否 |
| Windows | §7.2 最小 workflow；可标 `PENDING_RELEASE_BLOCKER` 但不标 closed；最迟 PR check 触发并通过 | 否 |

**所有 gate 均未弱化。**

## 5. 完整 886 行 plan 对抗审查

### 5.1 Architecture boundary review

#### 5.1.1 分层依赖验证

Plan §4 semantic owner map 定义了 16 项语义事实的唯一 owner。逐项用当前代码验证：

| Semantic fact | 指定 owner | 代码证据 | 正确 |
|---|---|---|---|
| upload suffix allowlist | `FINS_UPLOAD_FILE_SUFFIXES` in `upload_batch.py:19` | `frozenset` 定义于 line 19-23 | ✓ |
| 文件发现/containment/symlink | `upload_batch.py` | 当前 `generate_upload_batch_plan` 已有 source dir 校验 | ✓ |
| 财期/material 推断 | `upload_batch.py` 单一 helpers | 当前尚未实现；plan 要求新增 | N/A（新增） |
| canonical ticker + alias CSV | CLI input + ticker normalization | `dayu.fins.ticker_normalization.n()` 可用 | ✓ |
| FMP resolver | `FmpCompanyInfoResolver.resolve_company_info()` | 类定义于 `fmp_company_info.py:98`，method 于 line 135 | ✓ |
| explicit/inferred merge | CLI input boundary | 新增逻辑；plan §6.2.5 定义 merge precedence | N/A（新增） |
| direct upload flags/defaults | `arg_parsing.py` | 当前 `FILING_ACTION_CHOICES` / `BATCH_UPLOAD_ACTION_CHOICES` 定义于 line 63-64 | ✓ |
| plan entry → argv | `fins.py` 单一 builder | 当前 `_upload_batch_command_argv` 于 line 338；plan 要求改为 typed entry consumer | ✓ |
| POSIX/Windows quoting | `upload_script.py`（新增） | 新模块；owner boundary 不泄漏到 builder | N/A（新增） |
| output/publish | `upload_script.py` | 同上 | N/A（新增） |
| readable summary | CLI command | stdout，不产生机器 schema | ✓ |
| console scripts / wheel | `pyproject.toml` + build artifact | 当前 `[project.scripts]` 于 line 99-105 | ✓ |
| Windows workflow | `r11-upload-script-windows.yml`（新增） | `.github/workflows/` 当前不存在 | N/A（新增） |

**反向依赖验证**：当前 `upload_batch.py` 无 `dayu.cli` import（验证通过 `rg 'from dayu\.cli|import dayu\.cli'
dayu/fins/upload_batch.py` 零命中）。plan 要求此 invariant 保持。

**分层依赖检查**：plan §4 明确禁止 Fins 读 env/网络、CLI 做业务推断、renderer 做 filename regex — 均在
plan 的多处得到 enforce。无跨层穿透。

#### 5.1.2 潜在关注：FMP resolver path label

Plan §2.2 source lock 表使用 label "CURRENT FMP resolver"，而非精确文件路径。实际文件位于
`dayu/fins/resolver/fmp_company_info.py`（394 lines，hash 匹配）。实现 Agent 做 preflight 时如果仅按
label 搜索，可能找不到文件。该 label 对实现 Agent 的 discoverability 略低于其它 source lock（它们都用
精确文件路径）。hash 与行数已独立验证正确；这是 minor discoverability issue，不影响产品 contract。

**将此列为新 finding `R11-PR-BF-FR-DS-F02`（LOW / PLAN-ONLY / DISCOVERABILITY）。** 详见 §7。

### 5.2 Best-practice review

#### 5.2.1 Windows quoting 算法的 evidence-driven 方法

Plan §6.5 将 Windows quoting 算法推迟到真实 `cmd.exe` runner 反证后锁定，不在无 Windows evidence 的 plan
中臆定。这是正确的工程判断：batch file quoting 有大量已知边缘情况，任何 paper design 都可能被真实
`cmd.exe` 推翻。Plan 的约束足够严格：

- adversarial matrix 必须先写成 renderer unit + real-recorder oracle
- 候选算法必须在真实 `cmd.exe` 通过全部反例
- 禁止 compat/fallback/双算法/platform test shim
- `subprocess.list2cmdline` 不得作为 owner、安全证明或 fallback

**无 finding。**

#### 5.2.2 POSIX real upload smoke 的依赖链

§6.6 POSIX real upload smoke 依赖：
1. `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm` 存在且内容有效
2. Service/Fins runtime 可处理该 XBRL fixture
3. Temp storage 可用

如果 Service/Fins runtime 有 R11 无关的既有问题，该 smoke 会失败并 block R11。但 plan 明确要求
"不得 monkeypatch Service、runtime、validator 或 storage"，这是有意为之的端到端验证。Plan §5.3/§6.6
将这些 smoke 归入 `R11-I1` atomic checkpoint 的必须通过项。如果既有 Service issue 确实存在，block R11
是正确的——R11 修改了 producer contract，必须证明完整链路成立。

**无 finding。**

#### 5.2.3 wheel 验证 oracle 的健壮性

§7.3 的四个 Python negative oracle 对 wheel metadata/archive 做精确验证。每个 oracle 均：
- 内置 exact-one wheel/dist-info assertion（不依赖 shell wildcard）
- 对命中打印 exact hits（可审计）
- 期望 exit 0 + 精确 stdout 字符串

这些 oracle 是幂等的、可独立运行的。格式正确。

**无 finding。**

### 5.3 Optimal-solution review

Plan 的核心方案：删除 JSON 中间协议 → Fins 产生 typed plan → CLI 机械投影为真实可执行脚本 → 安全原子发布。
这条路与项目现有架构一致（typed dataclass → 机械投影），没有明显更优的替代方案。

- `auto` action：Plan 要求 `FILING_ACTION_CHOICES` 改为 `auto|create|update|delete`、`BATCH_UPLOAD_ACTION_CHOICES`
  改为 `auto|create|update`、三个 upload parser default 均为 `auto`。这直接对齐了 runtime 真源
  `action=auto`，消除了入口 grammar 与 owner contract 的错误投影。
- `--infer` flag：一次 resolver 调用补全 company name/aliases，语义干净。
- Placeholder 删除：直接删除文件 + entrypoint + optional dependency，wheel 验证零残留。无兼容 shim。

**无 finding。**

### 5.4 Overengineering review

Plan 的 deferred/no-touch 列表（§3.3）非常明确：
- 不实现或修改 Issue 142/151/175/177/178
- 不进入 R12
- 不实现真实 Web/WeChat/render package
- 不改 Service/Host/Engine/Runtime
- 不增加 JSON fallback、compat re-export/wrapper/alias、第二 renderer、generic authorization、extra payload

Plan 新增的唯一模块是 `dayu/cli/upload_script.py`（platform renderer + publisher），这是最小新增 surface。
没有不必要的 abstraction、builder、factory、protocol 或 migration。

**无 finding。**

### 5.5 Overcoupling review

#### 5.5.1 R11-I1 的 tight coupling 是 intentional

WP-A（Fins）与 WP-B（CLI）在 R11-I1 内紧耦合：WP-A 定义 typed contract，WP-B 立即消费它；不形成
producer-only checkpoint。这是 contract cutover 的正确 sequencing——plan §4 明确：

> "R11-I1 的合并只修复 contract cutover sequencing，不改变 semantic owner"

如果有担忧，是 implementation Agent 需要在一个 uninterrupted task 内协调 8 个文件的修改。但 plan 已提供：
- material preflight（mutation 前完成全部输入验证）
- sequential edit（可顺序编辑，不要求事务原子写）
- safety stop（真实 blocker → stop + failed working evidence）
- correction loop（consumer 暴露 gap → 回 Fins owner 修正 + combined revalidation）

这些机制合理减轻了协调风险。

**无 finding。**

#### 5.5.2 `upload_script.py` 的双职责

新增的 `upload_script.py` 同时承担 platform renderer（quoting、comment、passthrough）和 publisher
（containment、symlink、atomic replace、mode）。二者共享 output target 与 platform context，放在同一模块
是合理的。Plan §4 将这两组语义分别归于同一 owner（`upload_script.py`），消费者也相同（CLI command +
tests）。

**无 finding。**

### 5.6 Code fact cross-validation

#### 5.6.1 Plan 声称的当前问题验证

| Plan 声称 | 代码证据 | 证实 |
|---|---|---|
| "upload_batch.py 仅做 token 分类并返回单一 entries 与 path-only skip" | `generate_upload_batch_plan` 返回 generic `entries`，无 material routing/fiscal/dedup/caps | ✓ |
| "CLI 把 Fins entry 再投影成 {schema_version: 1, commands: [argv...]}" | `_render_upload_batch_plan` 于 `fins.py:316-327` 产生 `{schema_version, commands}` | ✓ |
| "pyproject.toml 仍发布 dayu-web/dayu-wechat/dayu-render" | `pyproject.toml:102-104` 含三个 placeholder entrypoints | ✓ |
| "FILING_ACTION_CHOICES 缺 auto，BATCH_UPLOAD_ACTION_CHOICES 也缺 auto" | `arg_parsing.py:63-64`：`("create","update","delete")` / `("create","update")` | ✓ |
| "upload_filings_from CLI 缺 --infer 与 --overwrite" | `arg_parsing.py:797-808` parser 无这两个 flag | ✓ |
| "placeholder packages 只有 unavailable placeholder" | 三个 `__init__.py` 均只有 stub | ✓ |
| "当前 HEAD 无 .github tree/workflow" | `.github/workflows/` 目录不存在 | ✓ |
| "negative boundary sentinel" | `test_web_tools_provider.py:760` 与 `test_diagnose_web_access.py:49` 各有一处 `"dayu.web"` | ✓ |

**所有动机声明均被直接代码证据证实。**

#### 5.6.2 Branch 与 tree 状态

- Branch：`phaseflow/host-issues-control` ✓
- Staged tree：空 ✓
- `git diff --check 2b14b2fb`：通过 ✓
- Deferred diff（Service/Host/Engine/Runtime/Config/Tool/UI/Constraints/Design）：空 ✓
- Product diff：`M docs/host/issues-implementation-control.md`（Controller-owned dirty，预期）+ 已添加的
  plan/review gate artifacts（均为 gate artifact，非 product change）✓

**无 product allowlist 外变更。**

## 6. 特殊审查维度

### 6.1 LLM-facing text 约束验证

Plan §6.2.4 要求 `--infer` help 为 "使用 FMP 公司信息补全公司名称与 ticker aliases（需要 `FMP_API_KEY`）"。
这是符合 CLAUDE.md LLM-facing 约束的自解释文本：说明动作、输入、输出与环境要求，不写内部模块名。

Plan 的 tool schema 变更仅涉及 `upload_filing`/`upload_material`/`upload_filings_from` 的 action choices
与新增 flag；这些是 argparse help text，面向 CLI 用户而非 LLM。但按 CLAUDE.md "tool schema 必须提供
业务可读语义" 约束，新增 flag 的 help text 应对 LLM 友好。Plan 对 `--infer` 和 `--overwrite` 给出了 exact
help contract。

**无 finding。**

### 6.2 安全约束验证

Plan §8.3 的 security closeout 明确限定了本轮报告范围：
> "本轮 security closeout 只报告保留/加强的 path containment、symlink、atomic write、argv injection 与
> secret non-persistence；不得把它描述为统一 authorization、workspace trust 或 shell sandbox"

Plan 的 containment model 是 lexical + resolved dual containment，与现有 Fins upload batch 的 containment
模型一致。External ancestor symlink（如 `/tmp → /private/tmp`）被显式允许，这是实用且正确的。

**无 finding。**

### 6.3 Windows gate 作为 PENDING_RELEASE_BLOCKER 的正确性

Plan §7.2/§9.4 明确：
- Windows gate 本地不可关闭
- 可标 `PENDING_RELEASE_BLOCKER`
- umbrella aggregate acceptance、draft PR ready/final closeout 必须等真实 GitHub run
- 失败时回到 R11 owner fix/review，不新建 WU，不转 residual
- 真正 release closeout 时 accepted findings、actual accepted residual、Windows release blocker 三者均为 0

这是 umbrella §7.3/§22 允许的唯一延迟规则。Windows workflow contract（triggers、permissions、test
commands、artifact）均有精确定义。

**无 finding。**

## 7. 新 current material finding

### `R11-PR-BF-FR-DS-F02` — LOW — FMP resolver source-lock label 不含精确文件路径

- **位置**：Plan §2.2 baseline source locks 表，row "CURRENT FMP resolver"
- **问题类型**：discoverability / plan-only metadata
- **当前写法**：`CURRENT FMP resolver | 394 | c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa`
- **反例/失败场景**：实现 Agent 按 plan source lock 做 preflight 时，搜索 `fmp_company_info_resolver.py` 或
  仅按 "FMP resolver" label 推断路径。实际文件为 `dayu/fins/resolver/fmp_company_info.py`（394 lines，hash
  已独立验证匹配）。若 Agent 按错误路径做 `shasum`，会得到 "No such file" 并可能误判为 source drift。
- **为什么有问题**：plan §2.2 所有其它 production source lock 都使用精确相对路径（如
  `dayu/fins/upload_batch.py`、`dayu/cli/commands/fins.py`）；仅有 FMP resolver 使用描述性 label。不一致的
  label 格式降低 implementation preflight 的确定性与可自动化程度。
- **直接证据**：plan §2.2 row 5 vs row 6-8 的路径精度差异；`find` 确认文件实际路径为
  `dayu/fins/resolver/fmp_company_info.py`。
- **影响**：implementation preflight 短暂混淆（分钟级），不改变产品 contract、hash truth 或实现正确性。
- **建议改法和验证点**：将 plan §2.2 该 row 的 label 改为精确路径
  `CURRENT dayu/fins/resolver/fmp_company_info.py`。验证：替换后 plan SHA-256 变更限于该 cell，行数不变；
  `rg 'fmp_company_info\.py'` 在该 plan 中唯一匹配该行。
- **修复风险**：LOW — plan-only 一个 label cell 替换；hash 与行数不变；不影响任何产品/owner/slice/validation
  contract。
- **严重程度**：LOW — 不阻止 implementation；实现 Agent 可通过 `rg -l 'FmpCompanyInfoResolver' dayu/`
  在 5 秒内自行定位。

**本 finding 不重开任何已裁决产品问题。** 它仅涉及 source-lock 表的 discoverability 一致性，不改变 FMP
resolver 的语义 owner、修改 allowlist、slice sequencing 或 validation gate。

## 8. Open questions

无。Plan 的 scope、non-goals、slice contract、validation gates 与 deferred items 均充分定义。

## 9. Residual risks

| 风险 | 处置 | 跟踪目标 |
|---|---|---|
| Windows quoting 算法未在设计期确定 | Plan §6.5 使用 evidence-driven approach：adversarial matrix → candidate → real `cmd.exe` 反证 → lock。禁止 fallback/compat。 | Implementation evidence |
| Ruff 0.15.11 vs 当前 0.15.9 version mismatch | Plan §8.1 version oracle 机制处理：version drift → Controller 重锁 version oracle + baseline。 | Implementation preflight |
| POSIX real upload smoke 依赖 Service/Fins runtime | Plan 明确不 monkeypatch；既有 Service issue 若存在则正确 block R11。 | R11-I1 atomic checkpoint |
| `R11-PR-BF-FR-DS-F02`（FMP resolver path label） | 建议 Controller 以 plan-only narrow fix 关闭或裁决为 deferred。 | Controller adjudication |

## 10. Final re-review conclusion

### 10.1 独立证明总结

| 证明项 | 结论 |
|---|---|
| R11-IMP-BF01 仍 CLOSED | ✓ — 精确两个 slices；WP-A/WP-B 不构成 state-machine node |
| R11-PR-BF-RR-F01 仍 CLOSED | ✓ — sequential edit 无事务原子写；safety stop 完整 |
| R11-PR-BF-FR-DS-F01 已 CLOSED | ✓ — plan line 71 hash 三路一致；旧值零残留 |
| Two-slice owner/state machine 完整 | ✓ — 节点、transition、禁止节点均精确定义 |
| 顺序编辑与 safety stop 正确 | ✓ — 四层一致；transient inconsistency 不升格 |
| Fins correction loop 正确 | ✓ — owner 范围、重验证范围、禁止补偿均明确 |
| Combined revalidation 正确 | ✓ — I1 correction 后 + I2 完成后均需 cumulative |
| Full pyright 0 | ✓ — 未弱化 |
| Ruff/Coverage/Security/Deferred/Windows gates | ✓ — 均未弱化 |

### 10.2 Finding ledger

| Finding | 本轮状态 |
|---|---|
| `R11-IMP-BF01` | CLOSED |
| `R11-PR-BF-RR-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F02` | OPEN / LOW / PLAN-ONLY / DISCOVERABILITY |

- accepted/open new：`1`（LOW）。
- blocker：`0`。
- actual accepted residual：`0`。
- 已裁决产品问题重开：`0`。
- Windows：`PENDING_RELEASE_BLOCKER`，未改变。

### 10.3 Conclusion

**PASS-WITH-OBSERVATION** — 最终 plan 的 source lock 已精确修复；两个 implementation slices 的 owner/state
machine、sequential editing safety stop、Fins correction loop、combined revalidation 与全部 validation/
security/deferred/Windows gates 均完整且未弱化。唯一的 new finding（FMP resolver source-lock label
discoverability）是 LOW / PLAN-ONLY，不阻止 implementation。

READY_FOR_CONTROLLER_R11_FINAL_PLAN_REREVIEW_ADJUDICATION
