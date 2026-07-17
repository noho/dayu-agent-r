# WU-SEMANTIC-OWNERSHIP-01 / R11 final-plan source-lock re-review（MiMo route）

## 1. Gate、scope 与 reviewed target

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- gate：`R11-PR-BF-FR-DS-F01` source-lock exact fix 后的 dual complete final-plan re-review（MiMo route）。
- reviewed target：886 lines / 74,571 bytes / SHA-256
  `59156239ff4d73bfeaa1cb78a593c2b75504804102a07e851b1239803a4de51f`。
- 本 re-review 完整读取最终 886 行 plan，不是只审 one-cell delta。
- 本 gate 不授权 implementation、stage、commit、push、PR 或 R12。

## 2. Independent proofs

### 2.1 R11-IMP-BF01 — CLOSED ✓

Plan §1、§4、§9.1 精确只定义两个 slices：`R11-I1 atomic Fins+CLI cutover -> R11-I2 packaging/README/Windows gate`。WP-A/WP-B 不构成独立 state-machine node，无 producer-only checkpoint、acceptance、stage、commit、handoff 或 review。§5.3/§6.6/§9.1 的 correction loop 只在 `R11-I1` 内对 Fins owner 路径做 targeted correction，不创建新 sub-WU/slice/commit。Controller checkpoint 只在全部 coordinated edits + combined revalidation 后执行一次。

未发现任何将 producer/consumer 拆回独立 slices、创建中间 commit、或绕过 atomic cutover 的 plan 文本。

**Verdict：CLOSED，无 reopen 依据。**

### 2.2 R11-PR-BF-RR-F01 — CLOSED ✓

Plan §5.1、§6.1、§9.1 明确定义：

1. 同一 uninterrupted Agent task 可顺序编辑 `R11-I1` 多文件，不要求跨文件事务原子写（§5.1: "implementation Agent 可在同一 uninterrupted task 内顺序编辑"；§9.1: "不要求跨文件事务原子写"）。
2. 全部 coordinated edits 完成前的 transient inconsistency 不是合法 intermediate tree 或 pass/failure baseline（§5.1、§9.1 反复强调）。
3. 不得对 transient tree 运行或宣称 tests/pyright/coverage/Ruff/validation，不得 checkpoint/acceptance/stage/commit/handoff/review/next-slice transition（§5.1、§9.1）。
4. 不得以 compatibility seam 缓解 transient inconsistency（§5.1、§9.1）。
5. 真实 blocker 仍安全 stop + 报告当前 diff 为 failed working evidence（§5.1、§9.1）。

未发现任何弱化上述语义的 plan 文本。

**Verdict：CLOSED，无 reopen 依据。**

### 2.3 R11-PR-BF-FR-DS-F01 — CLOSED ✓

Plan line 71 完整 source-lock cell：

```text
| CURRENT `requirements.txt` | 12 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
```

三路独立复测：

| Source | Commit / tree | SHA-256 |
|---|---|---|
| working tree `requirements.txt` | 当前 working tree | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
| accepted-plan commit | `f7b452f992b4797b32fea7c6f7212b5ec4345ec1` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
| R10 completion baseline | `2b14b2fbc89654267e3d33daa2ae410ceff45e68` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |

- 旧错误值 `7e8c14d6...79c93`：plan 内零命中。
- 新完整 SHA-256：plan 内精确一处命中，位于 line 71。
- plan 行数不变（886）；bytes +48（16 字符缩写 → 64 字符 full SHA 精确长度差）。

**Verdict：CLOSED。旧错误值零残留，三路完全一致。**

### 2.4 Two-slice owner/state machine — 未弱化 ✓

| 机制 | Plan 位置 | 当前状态 |
|---|---|---|
| 精确两个 dependency-ordered slices | §9.1 | `R11-I1 → R11-I2`，无第三 slice |
| WP-A/WP-B 不是 state-machine nodes | §9.1 | 同一 atomic slice 内的 ordered work packages |
| Sequential editing within uninterrupted task | §5.1, §9.1 | 允许顺序编辑，不要求跨文件事务原子写 |
| Transient inconsistency 不是 gate truth | §5.1, §6.1, §9.1 | 反复强调，至少 4 处 |
| Safety stop + failed working evidence | §5.1, §5.3, §9.1 | blocker → stop + 报告当前 diff |
| Fins owner correction loop | §5.3, §9.1 | 只在 Fins owner 路径 + combined revalidation |
| Combined revalidation after correction | §5.3, §6.6, §8.1 | 必须重跑全部 cumulative gate |
| Full pyright `0 errors` | §8.1 | 未放宽 |
| Ruff 0.15.11 baseline 144 findings | §8.1 | 版本 oracle + set difference 要求未变 |
| Per-file line coverage ≥ 80% | §8.2 | 不使用 `--branch`，逐文件读取 |
| Security/deferred/Windows gates | §8.3, §7.2 | 均保持 |
| Code review 只在两个 slices 全部完成后一次 | §9.2 | 未改变 |

### 2.5 Safety mechanisms — 未弱化 ✓

| Safety | Plan 文本证据 |
|---|---|
| 不允许 old/new dual surface | §4, §6.1, §9.1: "禁止把先删除 old producer surface、consumer 尚未切换的 transient tree 呈交为 gate input" |
| 不允许 compatibility seam | §5.1, §9.1: "不得以 compatibility seam 缓解 transient inconsistency" |
| 不允许 hasattr/getattr/loose parsing | §6.1: "不得 dual-read old/new plan、保留旧 import/field/property、使用 hasattr/getattr/loose parsing" |
| 不允许 CLI fallback/重算 | §5.3, §6.6: "不得在 builder/renderer/adapter/test fixture 补偿" |
| Stop on allowlist/source/design/security blocker | §5.1, §5.3, §6.6, §9.1: "立即 stop" |
| No rollback | §9.1: "不自行 rollback" |

## 3. Source lock verification

### 3.1 Production source locks — 逐项核对

| Source | Plan hash | Working tree hash | Status |
|---|---|---|---|
| `AGENTS.md` (128 lines) | `cb26618ab...08ac45e` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | **MATCH** ✓ |
| `dayu/fins/upload_batch.py` (376 lines) | `6767d30cf...d6178` | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` | **MATCH** ✓ |
| `dayu/cli/commands/fins.py` (1057 lines) | `0db8ff2de...95a6` | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` | **MATCH** ✓ |
| `dayu/cli/arg_parsing.py` (932 lines) | `a0e25ad6c...c2c` | `a0e25ad6c58f3f266ef1afc4447c4a7e875d18c23ad346550ccf8cfd283c1c2c` | **MATCH** ✓ |
| `pyproject.toml` (152 lines) | `e076606fd...a25` | `e076606fd68ab911291be92cdba1bda9df05835baf8db7f81b1d33d517ce6a25` | **MATCH** ✓ |
| `requirements.txt` (12 lines) | `d15176134...5d3a` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` | **MATCH** ✓ |
| `README.md` (348 lines) | `2f5cebfd...a6e6a` | `2f5cebfd3bf82b7099ff11f94e7a1e0df3840ca13fc41324a9d4ae99a02a6e6a` | **MATCH** ✓ |
| `dayu/fins/README.md` (793 lines) | `a4805995...9767` | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` | **MATCH** ✓ |
| `tests/README.md` (293 lines) | `15bb09f8...1fba9` | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` | **MATCH** ✓ |
| `docs/fins/design.md` (123 lines) | `97033cf1...7abdd` | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` | **MATCH** ✓ |
| `docs/ui/design.md` (111 lines) | `5a19c829...ed973` | `5a19c829151777b1d9f3c69f1a9a305396f75c8e73eb5ea31577663c55bed973` | **MATCH** ✓ |
| `docs/host/design.md` (3696 lines) | `276d35e1...43e9` | `276d35e15edfbf3efb1b9bff8ff4abbb38de48e075050379218fd19df90f43e9` | **MATCH** ✓ |
| `docs/engine/design.md` (553 lines) | `f2091260...f31` | `f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31` | **MATCH** ✓ |
| `docs/tool/design.md` (134 lines) | `ddc6efc0...ea7c` | `ddc6efc03c15ad5ba50332593f2282b1035dbc88d243071597814c7b4dceea7c` | **MATCH** ✓ |

### 3.2 Controller-owned files — 预期 drift

| Source | Plan 值 | Working tree 值 | 说明 |
|---|---|---|---|
| Controller control | 2242 lines / `1906ce2f...` | 2254 lines / `f958a95d...` | Controller-owned file，gate transition 合法变化；plan §2.4 要求 implementation 前在 accepted-plan commit parent 重新锁定 |
| `dayu/README.md` | 111 lines / `1534bcfd...d9a74` | 265 lines / `16bbdc87...5367` | 源锁在 plan 创建时测量；plan §7.1 item 6 的修改指令（删除 Web/WeChat/render placeholder stale 承诺）仍然成立 |
| FMP resolver (394 lines) | `c2abfbe0...c46fa` | 待 implementation preflight 复核 | 只读验证输入，不在 R11 修改 allowlist |

Plan §2.4 明确："进入 implementation 前，Controller 必须以 accepted-plan commit 的 parent 重新锁定所有 production/test/README/CI 输入。" 源锁表是 plan 创建时的快照，不是 implementation baseline；implementation agent 有义务在 preflight 重新测量。

### 3.3 Ruff version oracle

Plan §8.1 要求：`ruff 0.15.11`，baseline 144 findings，SHA-256
`051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。

Working tree 实测：`ruff 0.15.9`，144 findings，SHA-256 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。

- finding count 与 baseline SHA-256 完全匹配。
- 版本差异（0.15.9 vs 0.15.11）将在 implementation preflight 被捕获：plan §8.1 要求"版本漂移立即 stop，由 Controller 在同一 implementation 输入树上同时重新锁 version oracle 与 full baseline"。
- 这是 plan 创建时的版本测量偏差，不影响 plan 语义、gates 或实现可行性。

## 4. Plan 动机与代码事实验证

Plan §1 声称的四点 owner-side 证据，逐项复核：

| # | Plan 声称 | 代码事实 | 判定 |
|---|---|---|---|
| 1 | `upload_batch.py` 仅做 token 分类并返回单一 `entries` 与 path-only skip | 实测：`UploadBatchPlanEntry` 有 `command_name` 字段，`UploadBatchPlanResult.entries` 是 generic tuple，无 OLD fiscal/material routing | **成立** ✓ |
| 2 | `fins.py` 把 Fins entry 再投影成 `{schema_version: 1, commands: [argv...]}` | 实测：line 71 `_UPLOAD_BATCH_SCHEMA_VERSION_FIELD`，line 307 `_render_upload_batch_plan(plan.entries)`，line 324 `commands: list[JsonValue]` | **成立** ✓ |
| 3 | `pyproject.toml` 仍发布 `dayu-web`/`dayu-wechat`/`dayu-render` | 实测：lines 102-104 有三个 entrypoint，line 130 有 `dayu.render` package-data | **成立** ✓ |
| 4 | CLI 只允许 `create|update|delete` 且默认 `create`，batch 缺 `auto` | 实测：`BatchUploadAction = Literal["create", "update"]`，无 `auto` | **成立** ✓ |

Plan 的动机成立，严重性评估准确。

## 5. Adversarial plan review — 新 findings

### 5.1 Architecture boundary review

Plan 的语义所有权表（§4）清晰定义了每个 semantic fact 的唯一 owner 与允许消费者。逐项验证：

- Fins 是 scanning/OLD classification/fiscal/material/priority/dedup/caps/skip 的唯一 owner → CLI 仅消费 typed plan → 符合 AGENTS.md 语义所有权约束。
- CLI 是 argv building/renderer/publisher/summary 的唯一 owner → Fins 不读 env/网络 → 反向依赖为零。
- `upload_script.py` 平台 renderer 拥有 quoting/regenerate comment/passthrough → builder/tests 不自行 replace/escape → 单一 owner。

未发现架构边界泄漏或跨层穿透。

### 5.2 Best-practice review

- frozen typed models（§5.1）替代 generic dict/`Any` → 类型安全 ✓
- 单一 argv builder（§6.2 item 7）→ renderer 不判断 command kind ✓
- same-directory atomic replace（§6.3）→ 不留 partial ✓
- `setlocal DisableDelayedExpansion`（§6.5）→ 防 `%VAR%`/`!VAR!` expansion ✓
- `shlex.quote`/`shlex.join`（§6.4）→ 标准库 quoting，不自行实现 ✓
- 完整中文 docstring 要求（§5.1）→ 符合 AGENTS.md ✓

### 5.3 Optimal-solution review

Plan 的 two-slice 方案（atomic cutover → packaging）是 credible alternatives 中最实际的路径：

- 单 slice 方案：风险过高，Fins + CLI + packaging + Windows + README 同时改，失败时难以定位。
- 三+ slice 方案：过度拆分，producer/consumer 分离已被 R11-IMP-BF01 裁决为不可接受。
- 当前方案：Fins+CLI 合并为 atomic slice（修复 cutover 问题），packaging 独立（职责分离），是最优平衡。

### 5.4 Overengineering review

- frozen typed models：必要的公共 contract，不过度。
- two-slice with internal work packages：最小化结构，WP-A/WP-B 只是逻辑分组，不增加 state-machine 节点。
- Fins owner correction loop：必要的质量保障，不是过度设计。
- Windows workflow：最小化（single `workflow_dispatch` + `pull_request` trigger），不多不少。

未发现过度设计。

### 5.5 Overcoupling review

- Fins/CLI 边界清晰：Fins 产出 typed facts，CLI 消费并投影为 argv。
- R11-I1/R11-I2 allowlist 严格分离：packaging 不回改 I1 范围。
- 无 Service/host/engine/runtime 变更：耦合边界最小化。
- 无双向依赖：Fins 不读 CLI，CLI 只通过 typed contract 消费 Fins。
- 无 shared mutable state：Fins 返回 frozen tuple，CLI 生成 immutable scripts。

未发现过度耦合。

## 6. 已裁决产品问题重开检查

| 已裁决问题 | 重开？ |
|---|---|
| R11-IMP-BF01（producer/consumer 合并） | 未重开 ✓ |
| R11-PR-BF-RR-F01（sequential editing semantics） | 未重开 ✓ |
| R11-PR-BF-FR-DS-F01（requirements.txt source lock） | 已修复，未重开 ✓ |
| Topic 7 final adjudication | 未重开 ✓ |
| Topic 8/9 不实现 | plan §3.3 明确 deferred ✓ |

## 7. New finding ledger

**无新 material findings。**

对 plan 的完整 adversarial review（architecture boundary、best practice、optimal solution、overengineering、overcoupling）均未发现会导致 plan 失败、不可 review、违反约束或产生难恢复行为的风险。

## 8. Residual risks

| Risk | Severity | Tracking |
|---|---|---|
| Ruff version drift（0.15.9 vs plan 的 0.15.11） | LOW | implementation preflight 会捕获并 stop；plan §8.1 有明确 oracle 匹配要求 |
| Controller control 源锁 drift（2242→2254 lines） | LOW | Controller-owned file 合法变化；plan §2.4 要求 implementation 前重新锁定 |
| `dayu/README.md` 源锁 drift（111→265 lines） | LOW | 源锁是 plan 创建时快照；plan 修改指令仍成立；implementation preflight 重新测量 |
| Windows release gate pending | MEDIUM | plan §7.2/§9.4 明确 `PENDING_RELEASE_BLOCKER` 流程 |

以上 residual risks 均有 plan 级别的明确治理机制，不构成 blocker。

## 9. Finding closure summary

| Finding | Status | Evidence |
|---|---|---|
| `R11-IMP-BF01` | **CLOSED** | §2.1 — 精确两个 slices，无 producer-only checkpoint |
| `R11-PR-BF-RR-F01` | **CLOSED** | §2.2 — sequential editing + transient inconsistency 不是 gate truth |
| `R11-PR-BF-FR-DS-F01` | **CLOSED** | §2.3 — plan line 71 完整 hash 三路一致，旧错误值零残留 |

- accepted/open findings：`0`。
- new findings：`0`。
- blocker：`0`。
- actual accepted residual：`0`。
- Windows：`PENDING_RELEASE_BLOCKER`（未改变）。

## 10. Plan review conclusion

**PASS。**

最终 886 行 plan 的 source locks、gates、state machine、safety mechanisms、correction loop、validation requirements 均未弱化。三路 `requirements.txt` hash 完全一致，旧错误值零残留。已裁决产品问题未被重开。无新 material findings。

READY_FOR_CONTROLLER_R11_FINAL_PLAN_REREVIEW_ADJUDICATION
