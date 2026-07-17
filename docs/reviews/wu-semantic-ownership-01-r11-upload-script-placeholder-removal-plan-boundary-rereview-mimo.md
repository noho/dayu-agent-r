# WU-SEMANTIC-OWNERSHIP-01 / R11 amended plan complete re-review — AgentMiMo（第一路）

## 1. Reviewed target、scope 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU：R11 — upload script 与 placeholder surface remediation。
- reviewed target：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，
  848 lines / 70,036 bytes / SHA-256 `9d46ecfc74ced43b6f4868405fbee426523cee754456f0f2131aa3c4dd917be0`。
- scope：完整 848 行 amended plan，不是 delta-only。覆盖 §1—§10 全部章节、两个 implementation
  slices 的 allowlist/contract/tests/smokes/coverage/pyright/Ruff/scans/security/deferred gates。
- review lens：architecture boundary、best-practice、optimal-solution、overengineering、overcoupling。
- focus：R11-IMP-BF01 closure 证明、I1 atomic cutover 合法性、no-observable-broken-tree 与
  material-preflight/stop 兼容性、I1/I2 consumer 依赖切分、consumer-gap correction 边界、cumulative gates
  保留完整性、旧三-slice/提前 review/commit/compatibility seam 零残留。
- verdict：`PASS`。零 material finding，零 blocker。

## 2. Authority 与 source locks 验证

| Source | Expected | Actual | Verdict |
|---|---|---|---|
| plan lines | 848 | 848 | PASS |
| plan SHA-256 | `9d46ecfc...17be0` | `9d46ecfc...17be0` | PASS |
| `AGENTS.md` | 128 lines / `cb26618a...ac45e` | 128 / match | PASS（只读） |
| `docs/fins/design.md` §10 | Upload Batch Plan owner | 逐字匹配 | PASS（只读） |
| Controller discussion Topic 7.1 | OLD-aligned upload_filings_from | plan §1 正确引用 | PASS（只读） |
| Controller discussion Topic 7.2 | 删除 placeholder | plan §7 正确引用 | PASS（只读） |
| CURRENT `upload_batch.py` | 376 lines / `6767d30c...6178` | 376 / match | PASS（只读） |
| CURRENT `fins.py` CLI consumer | 1057 lines / `0db8ff2d...95a6` | 1057 / match | PASS（只读） |
| CURRENT `arg_parsing.py` | 932 lines / `a0e25ad6...1c2c` | 932 / match | PASS（只读） |
| CURRENT `pyproject.toml` | 152 lines / `e076606f...6a25` | 152 / match | PASS（只读） |
| CURRENT `requirements.txt` | 12 lines / `7e8c14d6...79c93` | 12 / match | PASS（只读） |

Controller-owned dirty/untracked files（`issues-implementation-control.md`、S1 authorization/stop/adjudication
artifacts）未被触碰。Phaseflow umbrella optimization control 作为附加总控约束已读取。

## 3. R11-IMP-BF01 closure 证明

### 3.1 问题回顾

原 R11 plan 有三个 slices：S1（Fins producer）、S2（CLI consumer/renderer）、S3（packaging）。AgentCodex
执行 S1 时发现：S1 contract 要求删除 `UploadBatchPlanEntry`/`UploadBatchPlanResult`、`entries`、
`command_name`、`files` 等旧类型/字段，但 S2 CLI consumer 静态 import 并读取这些旧 surface。因此：

1. 正确替换 producer → 破坏 CLI import/attribute/type → pyright 从 0 errors 新增 error。
2. 保留旧 surface → 违反 no-compat 与唯一 typed owner。
3. 放宽 pyright → 迴反 AGENTS 与 plan validation gate。

Controller adjudication 接受 `R11-IMP-BF01` 为 BLOCKER，要求合并为 atomic cutover。

### 3.2 Amended plan 如何关闭

Amended plan 将原三 slices 合并为两个：

- `R11-I1 atomic cutover`：合并原 S1 producer + S2 consumer/renderer，内部以 WP-A/WP-B
  两个 ordered work packages 实现，但两者之间**无 checkpoint、acceptance、commit、full validation、
  handoff 或 next-slice transition**（§9.1 lines 753—769）。
- `R11-I2 packaging`：原 S3 内容原样后移。

关键修复证据：

1. §4（lines 196—209）合并原 producer+consumer 为八个 write paths 的单一 `R11-I1` allowlist。
2. §5（lines 211—346）WP-A 定义 Fins typed producer contract，§6（lines 348—512）WP-B 定义 CLI
   consumer/renderer cutover。
3. §5.1（lines 220—223）明令："implementation 必须在开始 mutation 前准备完整协调 patch，并把两者作为一个
   不可停、不可 handoff 的 cutover 应用；不得留下'新 producer + 旧 consumer'的 transient broken working
   tree"。
4. §9.1（lines 749—779）固定精确 two-slice state machine，WP-A/WP-B 之间无任何中间 state transition。

### 3.3 Closure verdict

**R11-IMP-BF01 已在 plan 文本中关闭。** 根因（producer-consumer atomic contract cutover boundary 错误）
已被精确修复为 atomic slice 合并；原 rejected alternatives（compatibility seam、loose parsing、
放宽 pyright、transient broken tree 作为 checkpoint）全部被 plan 明令禁止。Controller §5 的七项
amendment requirements 全部 plan-text closed（参见 boundary-fix-codex §4 mapping table）。

## 4. 完整挑战：I1 merged context 是否是最小合法 atomic cutover

### 4.1 最小性论证

原三 slices 中，S1（producer）和 S2（consumer）无法在 no-compat + full pyright=0 下独立通过 checkpoint。
正确合并为单一 atomic slice 是能够同时保持唯一 semantic owner、strict typing、可验证 tree 与 no-compat
的最窄修复。没有更小的合法 checkpoint 方案——任何把 producer 和 consumer 分在不同 checkpoint 的方案都会
回到 R11-IMP-BF01 的根因。

### 4.2 Atomic cutover 可行性

§5.1 要求"在开始 mutation 前准备完整协调 patch"。这意味着 implementation agent 必须先设计好 WP-A
（Fins typed models）和 WP-B（CLI consumer/renderer cutover）的完整变更，然后一次性应用。这在技术上
可行：Python 允许同时修改多个文件，pyright 在全部修改完成后检查。

### 4.3 Full-pyright-clean 保证

Plan 要求 §8.1 `python -m pyright dayu/ tests/ utils/` 保持 `0 errors`。Atomic cutover 意味着
旧类型/字段被新类型/字段一次性替换，CLI 同时消费新 surface。只要 implementation 正确完成，tree
必然是 pyright-clean。若 implementation 中途失败（非 validation 失败），tree 可能处于 broken state，
但这不是 plan 的 checkpoint 问题，而是 implementation crash recovery 问题——与 R11-IMP-BF01 的
根因（planned checkpoint 不能形成合法中间 tree）不同。

**Verdict：PASS。I1 merged context 是最小合法 atomic cutover，实现后可 full-pyright-clean。**

## 5. 完整挑战："no observable broken tree" 与 "material preflight/stop" 是否冲突

### 5.1 Plan 文本

§9.1（lines 753—756）："WP-A+WP-B 一起 cutover 并完成 combined validation 后才运行…两者之间无
可观察 broken tree、stop/handoff/checkpoint/accept/commit/full validation"。

§5.3（lines 340—346）列出 stop conditions："任何 OLD rule 不能映射为当前 typed upload fact、current
suffix owner 与实际 runtime 冲突、需要 Service/storage/CLI classifier 才能完成、source containment
无法在 Fins boundary 保证"。

### 5.2 兼容性分析

关键区分：§9.1 的 "no stop between WP-A/WP-B" 禁止的是**两个 work packages 之间的 checkpoint/transition
stop**，不是禁止在整个 I1 内的 stop。§5.3 的 stop conditions 是整个 I1 的 stop conditions，不是
WP-A→WP-B 的中间 stop。

此外，§5.3 的 stop conditions（如 "OLD rule 不能映射为当前 typed upload fact"）需要 WP-B 消费 typed
contract 后才能暴露。WP-A 单独完成时，typed contract 尚未被 consumer 验证，因此这些 stop conditions
不会在 WP-A/WP-B 之间触发。它们只能在 WP-A+WP-B 共同完成后、cumulative validation 期间触发。

§5.3（lines 335—339）明确处理了 consumer 暴露 gap 的场景："若 WP-B 首个真实 consumer 暴露 typed
fact 缺失、enum 与 current grammar 不一致，或 optional ownership 仍需消费者猜测，不得 checkpoint、
不得在 CLI 补偿…按 §9.1 在同一 R11-I1 内对 dayu/fins/upload_batch.py 与 tests/fins/test_upload_batch.py
做 Fins owner targeted correction，再重跑 producer+consumer 全部 cumulative contract/tests/scans/
smoke/coverage/full pyright/Ruff"。

**Verdict：不冲突。"No observable broken tree" 禁止的是 WP-A/WP-B 之间的中间 checkpoint stop；
§5.3 的 stop conditions 是整个 I1 的 stop conditions，在 combined validation 期间触发。两者语义兼容。**

## 6. 完整挑战：I1/I2 test/package/README consumers 是否按依赖切开

### 6.1 I1 scope

I1 修改：`upload_batch.py`、`fins.py`、`arg_parsing.py`、新增 `upload_script.py`，以及对应四个测试文件。
I1 不修改 packaging/README/placeholder。

### 6.2 I2 scope

I2 修改：`pyproject.toml`、`requirements.txt`、新增 Windows workflow、删除六个 placeholder package
文件、`test_public_package_entrypoints.py`（只删 placeholder 部分）、四个 README。
I2 不修改 `upload_batch.py`、`fins.py`、`arg_parsing.py`、`upload_script.py`。

### 6.3 依赖分析

- I2 的 placeholder 删除（`dayu/web`、`dayu/wechat`、`dayu/render`）不影响 I1 的 product code。
  I1 的 product code 不 import 这些 placeholder modules。
- I2 的 `test_public_package_entrypoints.py` 修改只删除 placeholder 测试，保留 Docling tests。
  Docling tests 不依赖 I1 修改的 code。
- I2 的 README 修改不影响 I1 的 product/test code。
- I2 的 `pyproject.toml`/`requirements.txt` 修改只删除 placeholder entrypoints/dependencies，
  不影响 I1 的 product code imports。

### 6.4 Checkpoint 分析

- I1 checkpoint：只在 WP-A+WP-B 共同 cutover + cumulative validation 全通过后发生。
- I2 checkpoint：只在 I2 implementation + final cumulative validation（包括 packaging/Windows evidence）
  全通过后发生。
- I2 的 final cumulative validation（§8.1）重跑全部 tests/scans，包括 I1 的 tests。若 I2 packaging
  变更破坏了 I1 owner contract，此处会捕获。

**Verdict：PASS。I1/I2 按依赖切开；I2 不会产生第二个 broken checkpoint。**

## 7. 完整挑战：consumer gap correction 是否只在 Fins owner 且重跑 combined validation

Plan §5.3（lines 335—346）与 §9.1（lines 770—775）明确：

1. Consumer 暴露 gap 时，状态保持在 `R11-I1 coordinated implementation`。
2. 只允许在 Fins owner 路径 `dayu/fins/upload_batch.py` 与 `tests/fins/test_upload_batch.py` 做
   targeted correction。
3. CLI 继续机械消费同一 source of truth。
4. 修复后必须重跑 producer+consumer 全部 cumulative contract/tests/scans/smoke/coverage/full
   pyright/Ruff。
5. 禁止在 builder/renderer/adapter/test fixture 补偿，禁止创建新 sub-WU/slice/commit 或扩大
   allowlist。

**Verdict：PASS。Consumer gap correction 精确限定在 Fins owner 且重跑 combined validation。**

## 8. 完整挑战：cumulative gates 是否未弱化

### 8.1 Cumulative allowlist

§4（lines 162—209）列出 R11 cumulative implementation closed allowlist，精确包含原 producer+consumer
八个 paths + 原 packaging/CI/deletion/test/README paths。两个 slices 对上述 cumulative allowlist 的
唯一分配明确列出（lines 197—205）。未新增或删除路径。

### 8.2 Typed owner / current CLI projection

§5.1（lines 238—247）定义 frozen typed models：`UploadBatchPlanRequest`、`UploadBatchFilingEntry`、
`UploadBatchMaterialEntry`、`UploadBatchSkippedEntry`、`UploadBatchPlan`。§5.3（lines 318—333）
producer-consumer field/enum/optional mapping checklist 逐字段锁定。§6.2（lines 380—411）current
grammar locks 逐项定义。CLI 对文件名和 raw fields 零业务推断（§3.2 success signal 1）。

### 8.3 POSIX/Windows wheel smoke

§6.6（lines 466—512）定义 POSIX recorder smoke 与 POSIX real upload smoke。
§7.2（lines 548—591）定义真实 `windows-latest` / `cmd.exe` workflow 与 Windows recorder/CLI grammar
smoke。§7.3（lines 594—621）定义 packaging real smoke（wheel metadata/extracted names/RECORD）。

### 8.4 Changed-file coverage >=80%

§8.2（lines 673—685）逐文件读取 coverage JSON `summary.percent_covered >= 80.00`，明确四个
changed production Python files。

### 8.5 Full pyright

§8.1（line 651）`python -m pyright dayu/ tests/ utils/`，§8.1（line 638）"不得放宽当前 full pyright
0 errors 要求"。

### 8.6 Ruff 0.15.11 baseline

§8.1（lines 661—669）锁定 `ruff 0.15.11` version oracle、144 findings baseline SHA-256、
current-only 必须为空。不得因 atomic slice 合并而更新、删减或放宽。

### 8.7 Windows PENDING_RELEASE_BLOCKER

§7.2（lines 588—591）、§9.2（line 790）、§9.4（lines 814—816）均保留 `PENDING_RELEASE_BLOCKER`。
不得标 Windows closed；最迟在 aggregate/draft PR check 触发并通过。

### 8.8 Security/deferred/no-touch/no-push

§3.3（lines 132—143）deferred/no-touch 边界完整。§8.3（lines 688—740）exact source/propagation/
security/deferred scans 完整。§1（lines 13—17）no-push/no-commit/no-PR 边界明确。

**Verdict：PASS。所有 cumulative gates 保留完整，未被弱化。**

## 9. 完整挑战：旧三-slice / 提前 review/commit/acceptance / compatibility seam 是否零残留

### 9.1 Legacy three-slice scan

Boundary-fix-codex §5.1 执行 `rg -n 'R11-S[123]|...'` 精确零命中。唯一 bare `S1` 是 line 12
的 Controller artifact 专名，不是 current state-machine node。`S2`/`S3` 零命中。

### 9.2 Positive two-slice propagation

Boundary-fix-codex §5.2 正向扫描确认：
- `## 5. Atomic slice R11-I1 / WP-A`
- `## 6. Atomic slice R11-I1 / WP-B`
- `## 7. Slice R11-I2`
- `严格顺序精确两个 implementation slices`

所有 `checkpoint` 命中经逐项审阅后只属于四类合法用途。

### 9.3 Compatibility seam scan

Plan 全文禁止：
- `UploadBatchPlanEntry/Result`、`entries/command_name/files` compatibility surface（§5.1、§9.1）
- CLI loose parsing、`hasattr/getattr`、fallback、重算、downstream repair（§3.3、§5.1、§6.1、§9.1）
- old/new dual surface、compatibility alias/property/wrapper（§4、§5.1、§9.1）
- transient broken tree 作为 checkpoint/validation/handoff truth（§5.1、§9.1）

### 9.4 提前 review/commit/acceptance scan

§9.1（lines 766—768）："WP-A/WP-B 之间不运行 focused/full gate、不记录 checkpoint、不请求
acceptance、不 stage/commit，也不产生'next work package authorization'。"
§9.1（lines 777—779）："两个 slices 之间不做 slice acceptance、code-review gate 或 commit。"
§9.2（lines 792—797）："随后对完整 cumulative diff 并发执行两份 complete code review…只有
0 accepted open finding 且 Controller 接受 aggregate 后，Controller 才可授权一次 exact-scope
local accepted implementation commit。"

**Verdict：PASS。旧三-slice、提前 review/commit/acceptance、compatibility seam 零残留。**

## 10. 原产品裁决核对

### 10.1 Topic 7.1 裁决

Controller discussion Topic 7.1 裁决：upload_filings_from 必须完成，OLD-aligned，删除 JSON argv
public schema，实现平台可执行脚本。Plan §1、§3.1、§5、§6 完整传播此裁决。未重开或扩 scope。

### 10.2 Topic 7.2 裁决

Controller discussion Topic 7.2 裁决：删除 placeholder package scripts/grammar/README/tests，保留
ISSUE trackers。Plan §7 完整传播此裁决。未重开或扩 scope。

### 10.3 Semantic owner 不变

Fins 仍唯一拥有 discovery/fiscal/material/priority/dedup/caps/skips（§4 semantic owner map）。
CLI 仍只拥有 input、一次 public FMP resolve、typed projection、renderer/publisher/summary。
未因 atomic cutover 改变 semantic owner。

**Verdict：PASS。原产品裁决未被重开或扩 scope。**

## 11. Findings

### 11.1 Material findings

零。

### 11.2 Non-findings

以下项目经审查后确认为 non-finding：

1. **WP-A/WP-B crash recovery**：若 implementation agent 在 WP-A 完成后、WP-B 开始前 crash，
   tree 处于 broken state。但这不是 plan 的 checkpoint 问题（plan 明确禁止 WP-A/WP-B 之间有
   checkpoint），而是 implementation crash recovery 问题。Implementation agent 应在开始 mutation
   前准备完整协调 patch（§5.1），crash 后可从 git 恢复到 accepted-plan commit。这不构成 plan
   设计缺陷。

2. **`--action auto` default change**：§6.2.2 要求三个 upload parser default 都改为 `auto`。
   这是 `upload_filings_from` 新命令的 deliberate design，且 plan §1（line 34）声称 runtime
   已支持 `action=auto`。对现有 direct upload commands，`auto` 是 runtime 的 natural default，
   不改变实际行为。

3. **Windows quoting algorithm 延迟**：§6.5 明确"具体 quote/escape 算法不在无 Windows evidence
   的 plan 中臆定"，要求真实 `cmd.exe` evidence 后才锁定。这被正确标记为
   `PENDING_RELEASE_BLOCKER`，不是 plan 缺陷。

4. **I2 对 I1 的潜在影响**：I2 删除 placeholder packages 不影响 I1 product code（I1 不 import
   placeholder modules）。I2 final cumulative validation 重跑全部 I1 tests，可捕获任何意外回归。

### 11.3 既有 release blockers

- Windows quoting `PENDING_RELEASE_BLOCKER`（§7.2、§9.2、§9.4）：需真实 GitHub-hosted
  `windows-latest` / `cmd.exe` run 通过后才可关闭。

## 12. Open questions

零。

## 13. Residual risks

| Risk | Severity | Destination |
|---|---|---|
| Windows quoting algorithm 需真实 runner 反证 | 中 | R11 release gate（PENDING_RELEASE_BLOCKER） |
| Implementation agent 需在 mutation 前准备完整协调 patch | 低 | Implementation agent 技术约束 |

## 14. Plan review conclusion

**PASS。**

R11-IMP-BF01 已在 amended plan 中关闭：根因（producer-consumer atomic contract cutover boundary
错误）被精确修复为 atomic slice 合并。I1 merged context 是最小合法 atomic cutover，实现后可
full-pyright-clean。"No observable broken tree" 与 material preflight/stop 不冲突。I1/I2 consumers
按依赖切开。Consumer gap correction 限定在 Fins owner 且重跑 combined validation。所有 cumulative
gates（allowlist、typed owner、POSIX/Windows smoke、coverage>=80、full pyright、Ruff 0.15.11
baseline、Windows PENDING_RELEASE_BLOCKER、security/deferred/no-touch/no-push）保留完整。旧三-slice、
提前 review/commit/acceptance、compatibility seam 零残留。原产品裁决未被重开或扩 scope。

零 material finding。零 blocker（既有 Windows PENDING_RELEASE_BLOCKER 不计入本 review blocker）。

READY_FOR_CONTROLLER_ADJUDICATION
