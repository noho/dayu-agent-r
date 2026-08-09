# WU-CLI-CONFORMANCE-F01-F07 Plan Fix 记录（Codex）

## 0. Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Gate：`plan re-review -> second plan fix -> second plan re-review`
- Goal Confirmation：用户已确认。
- 修复对象：`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
- 首轮裁决真源：`docs/reviews/wu-cli-conformance-f01-f07-plan-review-controller-adjudication.md`
- 第二次 fix 当前唯一裁决真源：`docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md`
- 首轮 Reviewer 输入：
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-review-ds.md`
- Plan Re-review 输入：
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-ds.md`
- 本 Gate 允许写入：修订后的 plan artifact 与本 fix artifact。
- 本 Gate 禁止：生产代码、测试、README、design、两个 frozen registry、stage、commit、push、PR 操作。
- 状态：`SECOND PLAN FIX COMPLETE — 待第二轮独立 Plan Re-review`。
- 下一合法入口：仅为第二轮独立 `Plan Re-review Gate`。

## 1. 动机、证据与 owner 判断

修订动机成立，且严重性没有被高估。首轮真实 CLI evidence 直接证明 F01–F07 是 owner boundary 上的可复现偏差；Host design 与 invalid-response audit 又直接证明原计划删除 reactive multi-pass 的路径不成立。修订没有接受 reviewer 票数作为事实，而是以 controller 对 frozen oracle、design、evidence 与 direct code 的逐项裁决为唯一 finding disposition。

本次确认并写入计划的语义 owner 如下：

| 语义 | owner | plan-fix 结论 |
|---|---|---|
| 显式 editor 启动、draft/cursor、错误展示 | CLI composer | 显式命令由 CLI-owned launcher 处理；unset 才使用 prompt_toolkit public fallback。 |
| raw key sequence 分类 | `dayu.cli.run_keys` reader thread / prompt_toolkit composer binding | `Vt100Parser` 只在 reader thread 创建、feed、deadline flush；async loop只接收typed action。 |
| accepted/cancel/closeout 协调 | Host public lifecycle + CLI 最小观察 barrier | prompt 与 interactive 共用最小 coordinator，不携带 interactive-only 状态。 |
| compaction candidate validity与operation terminal | Host Context Governance / terminal commit guard | 保留 operation-level bounded reactive multi-pass；全部pass接受并完成root重验后才形成唯一accepted truth。 |
| Memory size policy与估算 | `dayu/host/memory.py` | 直接复用 `MemoryProjectionPolicy` 与 `estimate_memory_size_units()`，不复制配置或估算。 |
| Memory compact fact | committed canonical `CONTEXT_COMPACTED` event 的 strict v2 semantic projection | Memory不直连内存中的未提交accepted object；失败fallback不是accepted compact truth。 |

## 2. Accepted / accepted-in-part finding 逐项闭环

### 2.1 MiMo findings

| Finding | 裁决 | Plan fix 证据 |
|---|---|---|
| M-F1 | accepted | S1 将错误路径修为 `tests/cli/test_session_command.py`，并以typed construction-site表和`rg` inventory纳入 controller 列举的 Service、prompt、interactive、host-admin与transient-delivery测试。 |
| M-F2 | accepted | S4 owner test 固定为真实存在的 `tests/host/test_session_attachment_registry.py`，并明确禁止另建重复测试文件。 |
| M-F3 | accepted | S7 增加旧 active schema symbol/literal 到 fresh v2 symbol/literal 的机械映射、producer/persistence/reader/projection/tests/design传播闭包及旧值零残留扫描；无alias。S6也对F06 trigger给出同等机械映射。 |
| M-F4 | accepted | S7 保持单一outer slice/accepted commit，同时列出 schema、strict parser/accept、repair、projection+multi-pass 四个focused tests/pyright内部checkpoint。 |
| M-F7 | accepted/consolidated | S2 固定public seam，不再保留implementation-time选择：unset调用public `Buffer.open_in_editor`；显式命令使用CLI-owned tempfile、public `run_in_terminal`、exact argv及public `Buffer.document`。 |
| M-O1 | accepted | S8 明确provider blocked时状态保持`BLOCKED-ON-REAL-EVIDENCE`，current/next gate均为S8 real-evidence acquisition；恢复后必须使用新run id。 |
| M-O2 | accepted-as-plan-clarification | S7及风险章节明确policy/estimator owner均已在 `dayu/host/memory.py`，删除implementation-time猜测。 |

### 2.2 DeepSeek findings

| Finding | 裁决 | Plan fix 证据 |
|---|---|---|
| DS-B1 | accepted | S3 固定`Vt100Parser` reader-thread方案：parser只在reader thread创建/调用，同线程chunk `feed()`与named ESC ambiguity deadline/`flush()`；callback只用`loop.call_soon_threadsafe`投递typed action；完整序列不取消。 |
| DS-B2 | accepted | §13.2 固定accepted plan commit的十条显式路径，包含两个registry baseline和plan/review/fix/re-review/controller artifacts；stage前后校验working-tree及index SHA-256，随后S1–S8 registry必须clean。 |
| DS-B3 | accepted | S2 区分missing/non-executable/`OSError` actionable、nonzero silent cancel、zero-only refill、unset public fallback；显式路径不调用private API且不fallback。 |
| DS-B4 | accepted | S3 逐点映射 `_PromptAcceptedRunState`、`_InteractiveAcceptedRunState`、prompt cancel helper、interactive acceptance/cancel sites到最小shared coordinator。 |
| DS-B5 | accepted-in-part | 接受四个内部checkpoint；明确禁止stash、新branch、wall-clock预算、中间stage/compatibility commit，保持单一outer staged set/accepted commit。 |
| DS-B7 | accepted-in-part | editor seam与Memory owner均已收口；仅provider可用性保留为S8 operational stop，不再作为实现设计开放问题。 |

### 2.3 Controller 新增 findings

| Finding | 裁决 | Plan fix 证据 |
|---|---|---|
| C1 | accepted-严重 | S7 保留 `CompactPipelinePassQueuePlan` 与 `build_reactive_pass_queue_plan(...)`。每pass使用immutable source boundary和whole-candidate repair；全部required passes accepted后，operation owner重验root coverage、duplicate、caps及budget，形成唯一 `CompactAcceptedTruthV2`。中间pass不写canonical terminal、Memory、ordinary RunInput；失败只提交一个 `CONTEXT_COMPACTION_FAILED`。 |
| C2 | accepted-严重 | S2 写明F02四分语义；nonzero不再与配置/启动错误合并，且所有失败/取消路径都保持原draft/cursor、零Run及REPL continuation。 |
| C3 | accepted-高 | S1 typed construction-site allowlist、映射表、`rg` inventory及focused command覆盖controller列举的全部直接调用点，不以default/兼容字段保留旧调用。 |
| C4 | accepted-高 | S7 将final accepted truth先交给terminal owner一次性写artifact与canonical event；Memory只消费已提交event的strict v2 semantic projection，不消费未提交对象；失败fallback不称accepted truth。 |
| C5 | accepted-中 | §0与§16移除旧阶段叙事和与当前gate冲突的完成声明；当前状态为Plan Fix完成，下一入口只能是Plan Re-review。 |

## 3. 关键 contract 修订

### 3.1 F02 四分语义

计划现在固定以下唯一决策，不把不同事实压成一个“editor失败”：

1. 显式环境值missing、non-executable或spawn `OSError`：actionable且自解释；无traceback；原draft/cursor；零Run；REPL继续。
2. 显式editor process nonzero：静默cancel；原draft/cursor；零Run；REPL继续。
3. 显式editor process zero：读取UTF-8内容并通过public `Buffer.document`回填；仅后续显式submit创建Run。
4. `VISUAL`与`EDITOR`真正unset：调用public `Buffer.open_in_editor(validate_and_handle=False)`，允许prompt_toolkit系统fallback。

显式命令解析固定`VISUAL`优先、否则`EDITOR`；使用CLI-owned安全tempfile与public `run_in_terminal`执行exact argv。不得触碰private API，显式失败不得fallback。

### 3.2 F03 parser 与最小共享 coordinator

计划不再留下thread/async桥接选择。reader thread拥有parser、decoder、chunk feed、ESC ambiguity deadline和flush；parser callback不执行业务状态变更，只向event loop投递typed local action。standalone Escape必须等ambiguity deadline确认；CSI/Home/Delete/Alt/bracketed paste等完整序列不得被错误取消。

prompt/interactive既有accepted-state与cancel consumers映射到两个最小共享概念：accepted-run barrier与active-turn closeout。attachment、composer、pending mutation等interactive-only状态留在interactive owner，避免shared coordinator变成god bag。

### 3.3 F06 机械重命名闭包

计划明确旧active trigger机械替换：

| 旧 active | fresh replacement |
|---|---|
| `_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED` | `_RUNNER_CALL_TRIGGER_CONTEXT_GOVERNANCE_RESOLVED` |
| `context_compaction_completed` | `context_governance_resolved` |

producer、manifest persistence/strict reader、generic ingest、tool trace projection、tests及`docs/host/design.md`在同一slice更新；旧symbol/literal执行零残留扫描。没有alias、migration、loose parsing或fallback。

### 3.4 F07 reactive multi-pass 与 committed-event Memory

计划保留现有reactive queue owner。每pass对自己的immutable source boundary执行whole-candidate validation/repair，并共享operation全局attempt budget；pass truth只是operation内transient truth。全部required passes接受后，Host按确定性规则合并，并重新验证operation-root coverage等式、duplicate source disposition、policy caps与budget。root问题只可在可归因且仍有budget时让最后贡献该事实的pass按同一immutable boundary重提whole candidate，否则fail closed。

只有root validation通过才产生唯一final accepted truth。terminal owner一次性写aggregate artifact与`CONTEXT_COMPACTED`；event提交后，`context_events.py` strict v2 semantic projection才供Memory/RunInput/trace消费。中间pass、rejected candidate、失败fallback均不拥有accepted compact truth；失败路径只写一个`CONTEXT_COMPACTION_FAILED`。

### 3.5 Registry 与 S7 transaction 边界

当前fix/re-review不stage任何文件。未来plan re-review通过后，accepted plan commit按§13.2精确十路径纳入两个固定registry baseline和完整review loop；working-tree与index blob均校验固定digest。该commit以后S1–S8不再携带dirty registry。

S7内部checkpoint只提供验证反馈，不形成stash、branch、stage或commit边界。schema、strict parser/accept、repair、projection+multi-pass在一个outer slice、一个staged set和一个accepted commit中闭合，不产生v1/v2兼容窗口。

## 4. Rejected finding 保持拒绝

| Finding | 保持的处置 |
|---|---|
| M-F5 | 不新增旧v1 durable data reader、migration、fallback或兼容测试；按fresh schema/全新起库，旧schema active input由strict parser拒绝。 |
| M-F6 | 不拆散共享acceptance/cancel语义；保留最小shared coordinator，但禁止其携带interactive-only字段。 |
| DS-B6 | 已检查 `dayu/service/README.md` 不列相关request/字段，因此不修改；只在计划记录检查结论。 |
| DS-B5未接受部分 | 不使用stash、新branch、wall-clock预算或中间compatibility commit。 |

## 5. 文件与边界审计

本 Gate 只产生以下内容变化：

- 修订：`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
- 新增：`docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`

以下内容保持只读且未由本 Gate 修改：生产代码、测试、README、design、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、两份review及controller adjudication。两个registry的既有dirty状态属于进入本Gate前的formal baseline，不在本Gate清理或stage。

完整 review loop 中以下三条 durable artifact 已实际存在，第二次 fix 已将 plan 与本 artifact 统一为这些真实路径：

- `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-mimo.md`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-ds.md`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md`

## 6. 校验结果

完成本artifact后得到以下只读校验结果：

| 校验 | 结果 |
|---|---|
| `git diff --check` | PASS，exit 0、无诊断。 |
| plan/fix artifact no-index whitespace check | PASS；`git diff --no-index --check` 因文件相对`/dev/null`存在差异按约定返回1，但两份artifact均无whitespace诊断。 |
| `.venv/bin/python -m json.tool docs/cli_ci_oracles.json` | PASS，exit 0。 |
| `.venv/bin/python -m json.tool docs/cli_ci_scenarios.json` | PASS，exit 0。 |
| registry SHA-256 | PASS，与下列固定值逐字节一致。 |
| 计划所列现有路径逐项`test -e` | PASS，无`MISSING`；仅三条re-review artifact与future run-id root明确标注为未来新增。 |
| 旧阶段元数据、错误测试路径、删除reactive queue的反向表述扫描 | PASS，active plan中零残留。 |
| `git diff --cached --name-only` | PASS，输出为空；没有stage。 |
| `git status --short` | PASS；只有进入Gate前的两个dirty registry、既有plan/review/controller artifacts，以及本次新增fix artifact；无生产代码、测试、README或design变化。 |

预期并必须保持的registry digest：

```text
f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4  docs/cli_ci_oracles.json
7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef  docs/cli_ci_scenarios.json
```

## 7. Residual risk 与交接

- S7 large atomic closure：由单一outer transaction与四个focused checkpoint覆盖，仍需implementation/review/deepreview验证。
- PTY/editor/key timing：由S2/S3 owner tests与S8真实PTY evidence覆盖。
- provider availability：纯operational；S8在真实evidence成功前保持open，恢复后使用新run id。
- natural-language semantic fidelity：接受的模型风险；只承诺deterministic minimum validity和真实follow-up evidence，不以schema伪装事实真伪证明。
- registry accidental mutation/staging：由固定hash、accepted plan commit精确路径及S1–S8 clean guard控制。

当前不存在未分类的plan blocker。本Gate到此停止，不进入implementation、不stage、不commit、不push、不操作PR；下一入口只能是独立Plan Re-review。

---

## 8. 第二次 Plan Fix（R1 / R2）

### 8.1 Gate 元数据与裁决边界

- 当前 Gate：`Second Plan Fix`。
- 当前唯一裁决真源：`docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md`。
- 修复范围：只修订 plan artifact，并在本 artifact 追加本节；§1–§7 的首轮 fix 记录继续保留。
- Gate 状态：`SECOND PLAN FIX COMPLETE — 待第二轮独立 Plan Re-review`。
- 下一合法入口：仅为第二轮独立 `Plan Re-review Gate`；不得提前进入 implementation 或标记为 code-generation-ready。

第二次修订动机成立。R1 的直接证据是当前开发/验证环境安装 `prompt_toolkit==3.0.52`，而 `pyproject.toml` 声明 `prompt_toolkit>=3.0.0`；两者分别是环境事实和项目依赖边界，不能把前者提升为产品契约。R2 的直接证据是三份 durable re-review artifact 已使用 `plan-rereview-*` 命名，旧 staged-set 拼写引用不到文件。对应 owner 分别是 CLI composer 定义的 frozen editor success behavior，以及 review gate 已实际生成的 durable artifact path；修复不应落到依赖声明、private API、兼容层或新建/rename artifact。

### 8.2 R1 修复闭环

Plan §4.2、§4.5 与 §14.1 已统一为以下 contract：

1. 明确区分当前开发/验证环境的 `3.0.52` 与项目声明的 `>=3.0.0`，不把环境安装值写成 pin，也不声称全部未来满足声明范围的版本行为相同。
2. 实现只依赖 public import/API：unset 路径使用 public `Buffer.open_in_editor(...)`，显式路径使用 public `run_in_terminal(...)` 与 public `Buffer.document`。当前环境 private behavior 只作为排除错误实现路径的负面证据，不拥有产品语义。
3. “成功读取后最多移除一个末尾换行”已改为 CLI composer 拥有的 frozen editor success behavior，不再从依赖版本反推。
4. Stop signal 已改为：若当前 resolved dependency 的所需 public seam 与直接核验证据不符，立即回到 plan；禁止 private fallback、monkey patch、兼容层或擅自 pin。
5. 本轮未修改 `pyproject.toml`，未新增 dependency compatibility layer。

### 8.3 R2 修复闭环

Plan §13.2 的 exact staged set、完整 `git add --` 示例与本 artifact 的路径记录已统一为以下十条真实 durable paths，计数固定为 `10`：

1. `docs/cli_ci_oracles.json`
2. `docs/cli_ci_scenarios.json`
3. `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
4. `docs/reviews/wu-cli-conformance-f01-f07-plan-review-mimo.md`
5. `docs/reviews/wu-cli-conformance-f01-f07-plan-review-ds.md`
6. `docs/reviews/wu-cli-conformance-f01-f07-plan-review-controller-adjudication.md`
7. `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`
8. `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-mimo.md`
9. `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-ds.md`
10. `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md`

本轮没有另建或 rename 文件。当前 fix/re-review 阶段仍禁止 stage；以上集合只描述第二轮独立 plan re-review 通过后未来 accepted plan commit 的精确边界。

### 8.4 第二次 Plan Fix 校验结果

| 校验 | 结果 |
|---|---|
| plan/fix artifact 错误 re-review 文件名扫描 | PASS，0 命中。 |
| plan/fix artifact 三类错误版本措辞扫描 | PASS，0 命中。 |
| 十条 exact staged paths 逐项 `test -e` | PASS，存在 `10/10`，计数为 `10`。 |
| `git diff --check` | PASS，exit 0、无诊断。 |
| 两份 untracked artifact 的 no-index whitespace check | PASS，无 whitespace 诊断。 |
| 两个 registry 的 `json.tool` | PASS，均为 exit 0。 |
| 两个 registry SHA-256 | PASS，与冻结值逐字节一致。 |
| `git diff --cached --name-only` | PASS，输出为空，index 未被修改。 |
| second plan-fix scope | PASS；只改 plan 与本 fix artifact，未修改生产代码、测试、README、design、registry 或 review/controller artifacts。 |

Registry digest 保持：

```text
f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4  docs/cli_ci_oracles.json
7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef  docs/cli_ci_scenarios.json
```

R1、R2 均已修复，原18项 accepted/accepted-in-part finding 状态不变，当前没有未分类 blocker。Second Plan Fix Gate 到此停止；下一入口只能是第二轮独立 Plan Re-review，不实施、不stage、不commit、不push、不操作PR。
