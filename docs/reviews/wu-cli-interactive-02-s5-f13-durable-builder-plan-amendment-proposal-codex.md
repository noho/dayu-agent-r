# WU-CLI-INTERACTIVE-02 S5/F13 Durable Builder Plan Amendment Proposal

## 0. Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Slice / finding：`S5 / F13`
- Gate 事件：第二次 accepted-plan premise invalidation；只做 durable-builder plan amendment proposal
- Base HEAD：`ec9342ed9e5584123618f6b5c5eba8e93e2aed94`
- 分支：`codex/interactive-oracle`
- 生成时间：`2026-08-01T22:13:32+08:00`
- Preflight：工作树在本次 amendment 前干净；HEAD 与 Controller 指定 base 完全一致；分支不是 protected trunk
- Reviewed target：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md` 的 S5 allowed test closure、focused/full validation、pre/post inventory 与 checklist
- Amendment artifact：`docs/reviews/wu-cli-interactive-02-s5-f13-durable-builder-plan-amendment-proposal-codex.md`
- First review：`docs/reviews/plan-review-20260801-221922.md`
- Second review：`docs/reviews/planreview-20260801-222140.md`
- First dual re-review：AgentDS `docs/reviews/plan-review-20260801-223512.md`；MiMo
  `docs/reviews/plan-review-20260801-224130.md`
- Final dual re-review：AgentDS `docs/reviews/plan-review-20260801-225540.md`；MiMo
  `docs/reviews/plan-review-20260801-225601.md`
- Review adjudication：`docs/reviews/gateflow-wu-cli-interactive-02-s5-durable-builder-amendment-review-adjudication-20260801.md` §7
- Accepted-finding fix preflight：工作树已有目标 plan、adjudication、两份 initial review、两份
  first dual re-review、两份 final dual re-review 与本 proposal 的预期 amendment dirty set；范围
  所有权明确，当前 fix 只修改目标 plan 与本 proposal
- 允许修改：目标 plan 与本 proposal artifact
- 明确禁止：生产代码、测试、其它 docs、implementation、commit、push、PR
- Completion status：`second amendment accepted-low fix applied / awaiting final dual independent re-review`
- Next entry point：MiMo 与 AgentDS simultaneous independent final dual re-review；不得进入 S5 implementation

## 1. 结论与第一性原理判断

第二次 accepted-plan premise invalidation **成立，严重性评估准确**。

第一 amendment 已正确关闭 required Engine final identity 与 `ContextCompactor` typed-return
的 25-file test/test-support closure，但它的 inventory 没有枚举 Host strict durable payload
builder 的全部直接测试调用。Accepted S5 §9.4 同时冻结了另一个 required contract：

1. `CONTEXT_COMPACTED.successful_response_identity` 是 required mapping；
2. `CONTEXT_COMPACTION_ATTEMPT_REJECTED.successful_response_identity` 是 required field，
   其值按对应 attempt 是否获得 successful Engine final 为 mapping 或 `null`；
3. strict builder/parser 拒绝 missing、extra、renamed 与 loose payload，也不得从 manifest、
   config 或相邻 operation/attempt 反推该 identity。

因此，S5 implementation 必须先由 `dayu/host/context_events.py` owner 给两个 strict builder
增加无 default 的 required typed `successful_response_identity` 参数，再让全部 8 files / 15
direct calls 机械迁移。当前 8-file builder union 中只有 3 个文件已在 S5 allowed tests，另
5 个文件不在 allowed boundary；这 5 个文件只是新增 allowed-file delta，不是完整迁移范围。
若不先 amend，只能越界修改、遗漏既有 3-file consumers、让 pytest/pyright 失败，或错误地
增加 optional/default/compatibility seam。正确修复是闭合 owner signature 与所有直接
consumer，不是放宽 durable contract。

## 2. Semantic owner 与直接证据

### 2.1 Owner 判定

- `dayu/host/context_events.py` 是 `CONTEXT_COMPACTED` 与
  `CONTEXT_COMPACTION_ATTEMPT_REJECTED` strict payload 的 builder、validator/parser 与
  exact-field contract owner。
- F13 计划中的 `SuccessfulRunnerResponseIdentity` 由 Engine success terminal contract
  产生，Host writer/builder 只验证并机械持久化；manifest、config、provider family、日志、
  字符串和测试断言都不是 response identity owner。
- 全部 8 个测试 consumer files 只拥有各自场景的 fixture 输入。它们可以补齐 owner 新增的
  required typed `successful_response_identity` 或 exact payload fixture，但不得产生新的
  业务规则、改变场景状态或在 consumer 层重算 identity；其中 5 个文件仅是本 amendment
  新增的 allowed-file delta。

该 owner 划分保持第一 amendment 的 Engine identity owner 与 Host durable projection owner
不变，不新增 adapter、helper、schema owner 或兼容层。

### 2.2 Base HEAD builder 证据

Base HEAD 的 `dayu/host/context_events.py` 中：

- `build_context_compacted_payload(...)` 位于约第 1092 行；
- `build_context_compaction_attempt_rejected_payload(...)` 位于约第 1352 行；
- 两者均在 owner 内构造 mapping 后调用各自 strict validator；
- 当前签名尚未包含 S5 计划中的 `successful_response_identity`，因为 S5 implementation
  尚未开始；全部 15 个 test calls 也因此尚未携带该 builder argument；
- owner 必须先增加 required typed signature，随后所有 15 个 direct calls 才能机械迁移。

这说明问题不是当前 production 已经实现错误，而是 accepted implementation boundary
没有把 owner contract 收紧与全部 8-file / 15-call consumer migration 写成同一个有序闭包，
并遗漏了其中 5 个测试消费者的 allowed-file boundary。

### 2.3 Strict durable builder inventory

Controller 给出的 inventory 已由本次只读 `rg` 独立复核。`CB(n)` 表示
`build_context_compacted_payload(...)` 的 test call 数，`RB(n)` 表示
`build_context_compaction_attempt_rejected_payload(...)` 的 test call 数：

| 文件 | 直接证据 | 既有 S5 状态 |
|---|---|---|
| `tests/host/test_context_compact_events.py` | `CB(3) + RB(4)` | 已允许 |
| `tests/host/test_compaction_operation.py` | `RB(1)` | 已允许 |
| `tests/host/test_dispatch_scheduler.py` | `CB(1) + RB(1)` | 已允许 |
| `tests/host/test_memory_projection.py` | `CB(1)`，约第 449 行 | 缺口 |
| `tests/host/test_compaction_terminal.py` | `CB(1)`，约第 650 行 | 缺口 |
| `tests/host/test_run_input_builder.py` | `CB(1)`，约第 7134 行 | 缺口 |
| `tests/host/test_compact_material.py` | `CB(1)`，约第 3605 行 | 缺口 |
| `tests/host/test_proactive_compaction_operation.py` | `RB(1)`，约第 268 行 | 缺口 |

复核结果精确为：

- accepted builder：`8 calls / 6 files`；
- rejected builder：`7 calls / 4 files`；
- 两类去重：`8 files`；
- 其中此前已允许 3 files；
- 新增 allowed-file delta：精确 5 files。

第一 amendment 的 25-file identity/typed-return closure 没有被删除、替换或重解释。本次
只加入 5 个此前未允许的 durable-builder consumer，因此 S5 枚举的机械 closure 总 union
从 25 增至 30 个去重 test/test-support files。

## 3. 精确 amendment

### 3.1 目标 plan 修改

仅修订 `docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`：

1. §9.1 保留第一 amendment 的 25-file identity/typed-return table 与同源 identity 规则；
   新增 8-file durable-builder inventory，并明确 3 个既有 allowed tests、5-file delta 与
   30-file total mechanical union。
2. §9.1 冻结实现顺序：先由 `dayu/host/context_events.py` owner 给 accepted/rejected 两个
   builder 增加 required typed 参数，再机械迁移全部 8 files / 15 calls；5-file delta 只
   表示新增 allowed-file boundary。
3. §9.1 冻结未执行真实 Engine 的 fixture 规则，以及 accepted/rejected mapping/null 分类；
   删除“测试已经拥有 runtime response identity”的错误暗示。
4. §10.5 的 S5 focused Host command 纳入全部 5 个文件；full affected Host command 与
   `pytest tests/engine tests/host -q` 都必须收集它们，不能用间接 full pass 替代 focused
   failure 定位。
5. §10.5 的 pre/post inventory 增加两个 strict builder 查询，并冻结 base 计数与 exact
   file union；新文件 hit 或无法按 exact contract 迁移时 fail closed 回到 Controller。
6. §13 S5 checklist 保留 25-file closure，增加 owner-first signature、完整 15-call migration、
   5-file allowed delta、30-file union、file-local typed fixture、mapping/null 与禁止项。

### 3.2 完整迁移与五文件 allowed delta

S5 先在 `dayu/host/context_events.py` 修改两个 owner signatures：

- `build_context_compacted_payload(...)` 增加 required
  `successful_response_identity: SuccessfulRunnerResponseIdentity`；
- `build_context_compaction_attempt_rejected_payload(...)` 增加 required
  `successful_response_identity: SuccessfulRunnerResponseIdentity | None`。

两者都不得提供 default、optional call seam 或兼容 overload。随后机械迁移 §2.3 全部 8
files / 15 calls；此前已允许的 3 个文件也在迁移范围内。下表只定义新放行 5 个文件的
allowed-file delta，不把它们误写为完整迁移范围：

| 文件 | 唯一允许的 S5 迁移 |
|---|---|
| `tests/host/test_memory_projection.py` | 给既有 accepted compact fixture 补 required identity / exact field |
| `tests/host/test_compaction_terminal.py` | 给既有 compacted terminal fixture 补 required identity / exact field |
| `tests/host/test_run_input_builder.py` | 给既有 accepted compact fixture 补 required identity / exact field |
| `tests/host/test_compact_material.py` | 给既有 accepted compact fixture 补 required identity / exact field |
| `tests/host/test_proactive_compaction_operation.py` | 给既有 `quality_check_rejected` fixture 补 required typed mapping / exact field |

Base HEAD 的 15 个 calls 都没有该参数，不得暗示这些测试已经拥有 runtime response
identity。contract、projection、material、run-input 等测试未执行真实 Engine、helper 没有
run context 时，每个 affected file 可在自己的 fixture owner 内定义 private typed identity
factory。test/case caller 必须使用当前 helper/call site 实际已有的显式、非敏感且足以区分
event 的上下文（例如 case label、`operation_id`、attempt/run id 或显式 ordinal），由该 factory
构造 deterministic 且对该 event 唯一的 `SuccessfulRunnerResponseIdentity`；具体输入维度与
参数名以现有 helper/call site 为准，不要求为统一形状虚构不存在的维度。caller 再把返回的
identity 作为 required 参数显式传给 payload helper。已有 proposal manifest / compactor Engine
run context 时，caller 必须显式传入对应 `compactor_engine_run_id` 给 factory，factory 或 payload
helper 不得从 manifest 或其它
sibling field 反推。identity 必须与同一 event 的 sibling run/operation/attempt/manifest 语义
一致；它只用于
满足 strict event contract 并验证 fixture 自洽，不是实际 provider continuity evidence。

mapping / `null` 必须按 event 业务语义冻结，不按测试是否运行 Engine 决定：

- `CONTEXT_COMPACTED` 始终为 mapping；
- rejected 的 parse/schema/semantic/quality/budget post-success category 为 mapping；
- transport/timeout/cancel/Engine failed 且没有 successful final 时才为 `null`；
- `tests/host/test_proactive_compaction_operation.py::_rejected_payload()` 的 orphan、incomplete、
  exhausted 三个调用都通过该 helper 生成
  `failure_category="quality_check_rejected"` event；因此三者的
  `successful_response_identity` 都必须为 mapping。MiMo-002 建议的三场景 `null` 结论被
  Controller 明确拒绝。

不得：

- 改变场景、状态转移、trigger、failure category、repair policy 或行为断言语义；
- 增加 optional/default/factory fallback、兼容 builder signature、wrapper 或 overload；
- 在 identity factory 或 payload helper 内提供 default，或硬编码跨 event 共享 singleton；
- 从 manifest/config/provider family、相邻 operation/attempt、client correlation 字符串或
  偶然 fixture 顺序反推 identity；
- 接受 missing/extra/renamed field、局部 dict patch 或 loose payload parsing；
- 新增跨文件万能 helper 或共享万能 identity fixture，把不同 operation/attempt 的事实折叠为
  一个值。

### 3.3 Review finding / fix trace

| Review item | Controller decision | Fix status | Proposal / plan fix |
|---|---|---|---|
| MiMo-001 | `accepted-medium-clarification` | 已修复 | §1、§2.2、§3.1-§3.2 与 plan §9.1/§10.5/§13 明确 owner-first required typed signature、完整 8 files / 15 calls migration；5-file 仅为 allowed delta |
| MiMo-002 | `accepted-concern / rejected-null-conclusion` | 已修复 | §3.2 与 plan §9.1/§9.4/§10.5/§13 冻结 mapping/null；proactive `quality_check_rejected` 明确 mapping，不接受 reviewer 的 `null` 建议 |
| DS finding 2 | `accepted-medium-with-owner-correction` | 已修复 | §3.2 与 plan §9.1/§10.5/§13 允许 file-local deterministic、非敏感、typed identity，并禁止把它当 provider continuity evidence |
| DS finding 1 | `rejected-historical-trace` | 不适用 | plan §16 是 accepted original plan gate 的 historical `planned-new` validation trace；本 fix 明确保留原文，不按当前工作树改写 |
| MiMo re-review finding 001 | `accepted-low` | 已修复 | §6 将当前 amendment 已冻结的 file-local identity/fixture 风险改为 `fixed in current amendment` |
| MiMo re-review finding 002 | `accepted-low` | 已修复 | §3.2 与 plan §9.1/§10.5/§13 明确 orphan/incomplete/exhausted 三个调用都生成 `quality_check_rejected` event，三者 identity 均为 mapping |
| AgentDS re-review finding 001 | `accepted-low-with-strategy` | 已修复 | §3.2 与 plan §9.1/§10.5/§13 冻结 caller 的实际显式上下文 → file-local private typed factory → required identity 参数的数据流；已有 run context 显式传对应 run id，禁止 helper default、共享 singleton、跨文件万能 helper与反推 |
| MiMo final finding 001 | `rejected-duplicate-inventory` | 不适用 | §2.3 与 plan §9.1 已分别完整冻结 25-file closure、8-file builder inventory 和 5-file delta，plan §10.5 要求重跑去重 inventory；不复制第三份 30-file 全清单 |
| MiMo final finding 002 | `rejected-already-covered` | 不适用 | §3.2、§4.2 与 plan §9.1/§10.5/§13 已冻结 event uniqueness、sibling consistency、required argument 及 default/共享 singleton/反推禁止项；无需新增抽象 |
| AgentDS final finding 001 | `accepted-low-clarification` | 已修复 | §3.2、§4.2、§6、§7 与 plan §9.1/§10.5/§13 将写死的 `case_label` / `operation_label` / `attempt_label` 改为 caller 使用当前 helper/call site 实际已有的显式、非敏感、足以区分 event 的上下文；不要求虚构不存在的维度，仍保持 deterministic、event-unique、sibling-consistent，并继续禁止 default、共享 singleton、跨文件万能 helper及 manifest/sibling 反推 |

Controller adjudication §3、§6 与 §7 的 accepted findings 均已落实到 proposal 与目标 plan；没有
blocking open question 或 unclassified residual risk。最终状态仍需 MiMo/AgentDS
simultaneous independent final dual re-review 裁决，本 proposal 不自判 review pass。

## 4. Validation

### 4.1 本 amendment 的文档级验证

本 gate 只执行只读证据收集与文档检查：

- `git branch --show-current`：`codex/interactive-oracle`；
- original amendment 前 `git status --short`：空；本轮 accepted-low fix preflight 为目标 plan、
  adjudication、两份 initial review、两份 first dual re-review、两份 final dual re-review 与本
  proposal 的预期 dirty set；
- `git rev-parse HEAD`：`ec9342ed9e5584123618f6b5c5eba8e93e2aed94`；
- 两个 builder 的 repo-wide test inventory：`8/6`、`7/4`、8-file union；
- 目标 plan 的 path scan：3 个 builder tests 已在 S5 boundary，5 个为精确新增缺口；
- `git diff --check`：目标 plan 无 whitespace error；
- 新 artifact 的 `git diff --no-index --check`：因 `/dev/null` 与新文件存在预期内容差异而
  exit 1，输出为空，表示没有 whitespace error；
- 最终 `git status --short`：仍只列上述 9 个 amendment/review artifacts；本次内容修改只
  发生在目标 plan 与本 proposal；
- status wording scan：本 proposal 将当前 entry point 精确冻结为
  `final dual independent re-review`，不宣称 review pass、implementation、accepted-plan
  commit、push 或 PR 已完成；plan §16 historical trace 保持原文。

本 gate 明确禁止 implementation，因此不运行 pytest、coverage 或 pyright；它们只在两路
re-review 通过、Controller 最终复核并创建第二 accepted plan-amendment commit 后，才由
获准恢复的 S5 按 amended §10.5 执行。

### 4.2 后续 implementation validation closure

- S5 先改 owner required typed signatures，再迁移全部 8 files / 15 calls；
- S5 focused Host tests必须显式包含 5-file allowed delta，完整验证 8-file closure；
- full affected Host command与 `pytest tests/engine tests/host -q` 必须实际收集这些文件；
- `python -m pyright dayu/ tests/ utils/` 关闭 required builder argument 与 exact typed
  identity 的全部遗漏；
- implementation 前后都重跑第一 amendment 的 25-file identity/typed-return inventory
  和本次 `8/6`、`7/4` builder inventory；
- 无 run context helper 的 caller 必须使用当前 helper/call site 实际已有的显式、非敏感且足以
  区分 event 的上下文（例如 case label、`operation_id`、attempt/run id 或显式 ordinal），由
  file-local private typed factory 生成 deterministic、event-unique identity，再作为 required
  参数显式传给 payload helper；具体输入维度与参数名以现有 helper/call site 为准，不要求虚构
  不存在的维度；已有 manifest / compactor Engine run 时 caller 显式传对应 run id 给 factory；
- contract/projection/material/run-input fixture 的 file-local typed identity 必须断言 sibling
  run/operation/attempt/manifest 语义一致；proactive orphan/incomplete/exhausted 三个
  `quality_check_rejected` event 的 identity 必须全部为 mapping；
- post-inventory 出现未允许的新文件 hit、optional/default/compatibility、manifest/config
  反推或 loose payload，均直接失败并退回 Controller。

## 5. Non-goals

- 不修改任何生产代码、测试代码、README、design、oracle 或 scenario 文档。
- 不执行 S5/F13 implementation，不运行实现 pytest/pyright/coverage/provider smoke。
- 不改变 F13 required identity contract、Host accepted/rejected schema、Engine/Host owner 或
  第一 amendment 的 25-file identity/typed-return closure。
- 不通过本次 durable-builder migration 改变 8 个 consumer files 的既有场景与断言语义；
  不借 5-file allowed delta 增加新场景或重构 fixture。
- 不扩展 8-file / 15-call consumer closure 或 5-file allowed delta，不增加 production/test scope。
- 不增加 optional/default/compatibility、manifest/config 反推、loose payload 或下游补偿。
- 不裁决真实 provider continuity、行为项 29 或 G06；test identity 不能替代外部证据。
- 不 commit、push、创建 PR、发 review comment 或修改外部状态。

## 6. Residual risks

| 风险 | 分类 | 处理 |
|---|---|---|
| file-local deterministic typed identity 与 sibling run/operation/attempt/manifest 语义不一致 | `fixed in current amendment` | §3.2 与 plan §9.1/§10.5/§13 已冻结 caller 使用当前 helper/call site 实际已有的显式、非敏感、足以区分 event 的上下文，不虚构维度，并保持 event uniqueness、显式 run id 与 sibling consistency |
| amendment 后 HEAD 新增 strict builder call file | `requiring explicit controller decision` | S5 pre-inventory fail closed；先再次 amend allowed boundary |
| 实现者只更新 builder call，遗漏 exact payload fixture | `fixed in current amendment` | §3.2 与 plan §9.1/§10.5/§13 已冻结 caller 必须把 event-unique typed identity 作为 required 参数显式传给 payload helper；focused/strict/full/pyright 验证该规则 |
| test-only identity 被误当成真实 provider continuity evidence | `covered by later approved slice` | 保留行为项 29/G06 外部验证边界，不以 fake 宣称关闭 |
| pytest、pyright、coverage 尚未运行 | `covered by later approved slice` | 本 gate 禁止 implementation；由获批后的 S5/S6 validation 执行 |
| optional/default/compatibility 或 manifest/config 反推掩盖缺口 | `fixed in current amendment` | §9.1、§10.5 与 §13 已明确禁止，后续 review/pyright/inventory fail closed |

没有 unclassified residual risk。本 proposal 不宣称第二次 amendment 已被接受。

## 7. Completion checklist 与 dual re-review handoff

- [x] 直接证据与 Controller inventory 一致：accepted `8/6`、rejected `7/4`、union 8
  files / 15 calls。
- [x] Semantic owner 保持 `dayu.host.context_events` strict durable payload owner；owner-first
  required typed signature 与完整 consumer migration 顺序已冻结。
- [x] 5-file delta 仅作为 allowed-file boundary 加入；第一 amendment 25-file closure 完整
  保留，总枚举 mechanical union 仍为 30 个去重 test/test-support files。
- [x] “fixture 已有 runtime response identity”错误暗示已删除；无 run context helper 已冻结为
  caller 使用当前 helper/call site 实际已有的显式、非敏感、足以区分 event 的上下文（例如
  case label、`operation_id`、attempt/run id 或显式 ordinal）→ file-local private typed factory →
  required payload helper 参数；具体输入维度与参数名以现有 helper/call site 为准，不要求虚构
  不存在的维度；已有 manifest / compactor Engine run 时 caller 显式传对应 run id 给 factory。
- [x] identity helper 内无 default、无硬编码共享 singleton、无跨文件万能 helper，也不从
  manifest / sibling fields 反推。
- [x] mapping/null 已按 event semantic 冻结；proactive orphan/incomplete/exhausted 三个调用均
  生成 `quality_check_rejected` event，三者 `successful_response_identity` 均为 mapping。
- [x] §6 已将当前 amendment 冻结的 file-local identity/fixture 风险分类改为
  `fixed in current amendment`。
- [x] plan §16 historical `planned-new` trace 未修改。
- [x] Focused/full validation、pre/post inventory 与 S5 checklist wording 已修订。
- [x] Production/test implementation、pytest/pyright/coverage 未执行。
- [x] Commit/push/PR 未执行。
- [ ] MiMo 与 AgentDS simultaneous independent final dual re-review 尚未执行。
- Completion status：`accepted-low fix complete / awaiting final dual independent re-review`。
- Next entry point：MiMo 与 AgentDS simultaneous independent final dual re-review；两路通过前不得
  进入 accepted plan amendment commit 或 S5 implementation。
- Artifact path：
  `docs/reviews/wu-cli-interactive-02-s5-f13-durable-builder-plan-amendment-proposal-codex.md`
