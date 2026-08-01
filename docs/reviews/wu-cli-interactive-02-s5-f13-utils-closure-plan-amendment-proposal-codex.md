# WU-CLI-INTERACTIVE-02 S5/F13 Utils Closure Plan Amendment Proposal

## 0. Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Slice / finding：`S5 / F13`
- Gate 事件：第三次 accepted-plan premise invalidation 的 accepted arithmetic finding fix；只修订 code-generation-ready plan/proposal
- Accepted base HEAD：`e7f578dc7bdfafb51a859be2db584300e08f81fb`
- 分支：`codex/interactive-oracle`
- 生成时间：`2026-08-01T23:51:56+08:00`
- Reviewed target：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md` 的 §9.1、§10.5、§13、§15
- Proposal artifact：`docs/reviews/wu-cli-interactive-02-s5-f13-utils-closure-plan-amendment-proposal-codex.md`
- 允许修改：目标 plan 与本 proposal
- 明确禁止：生产代码、测试代码、其它 utils、其它 docs、revert 既有未提交实现、implementation、commit、push、PR
- Completion status：`accepted arithmetic finding fixed / awaiting simultaneous independent re-review`
- Next gate：MiMo 与 AgentDS simultaneous independent re-review；不得继续 S5 implementation

本文件是 amendment proposal，不是 planreview/re-review artifact，也不自判 review pass。

## 1. Preflight 与 dirty ownership

Preflight 直接结果：

- `git branch --show-current`：`codex/interactive-oracle`；不是 protected trunk。
- `git rev-parse HEAD`：`e7f578dc7bdfafb51a859be2db584300e08f81fb`，与 Controller 指定 accepted HEAD 完全一致。
- 本 amendment 开始前，目标 plan 为 clean，本 proposal 尚不存在。
- 工作树已有以下 20 个 modified paths，全部是用户明确指定必须原样保留的 S5 implementation ownership；本轮不得 stage、revert、格式化或修改：

```text
dayu/engine/__init__.py
dayu/engine/agent.py
dayu/engine/contracts/__init__.py
dayu/engine/contracts/agent_run.py
dayu/engine/contracts/engine_events.py
dayu/engine/contracts/runner_identity.py
dayu/host/compact_pipeline.py
dayu/host/compaction.py
dayu/host/compaction_operation.py
dayu/host/context_events.py
dayu/host/dispatch.py
dayu/host/engine_ingest.py
dayu/host/llm_compaction.py
tests/engine/contracts/test_agent_run.py
tests/engine/contracts/test_runner_identity.py
tests/engine/test_engine_event_contract.py
tests/engine/test_package_exports.py
tests/host/fake_compaction.py
tests/host/test_compaction_operation.py
tests/host/test_llm_compaction.py
```

- 排除本轮两个 allowed docs 后，既有 dirty binary diff 的 amendment 前 SHA-256 为
  `d19605477fe3c284e5791f8c8bdfb8272bfaac8bbd1876d7d4518c7eff8beeb9`。该整体 hash 与最终
  status/diff scan 共同作为“既有实现内容未变”的保护证据。
- accepted HEAD 上两个目标 utils 与工作树文件各自 SHA-256 完全一致：
  `smoke_host_public_awaiting_entrypoint.py = e212f06f2bfd4b66221791d15f9348deabeafad9be98a2f7ad572dce2b0a25ef`；
  `smoke_host_public_conversation_memory_scenarios.py = 84b176655ff4f4ada9ef3e0e3e9b92702852b1221f68087f2ae8a4b067a3fd56`。
  因而本 proposal 的行证据不是从 dirty S5 实现间接推断。

Dirty ownership 已由用户明确，branch/base/scope 均无 blocking open question。

## 2. 第一性原理判断、root cause 与 semantic owner

第三次 premise invalidation **成立，且严重性评估准确**。

F13 accepted contract 已把 `FinalAnswerData.response_identity` 与
`EngineRunOutcomeFinalAnswer.response_identity` 冻结为 required typed identity，并禁止
default、optional、compatibility 或下游 fallback。项目最终类型闭包又明确要求运行：

```bash
python -m pyright dayu/ tests/ utils/
```

第一 amendment 的 inventory 只搜索 `tests/`。两个既有 utils smoke 直接构造上述 required
contracts，却不在 25-file tests closure 或 S5 allowed boundary 中。因此只要 owner contract
按 accepted plan 收紧，全量 pyright 就必然在 utils 报漏传 required identity。若不先 amend，
实现者只能越界修改、留下全量 pyright failure，或错误引入 default/optional/compatibility 来
掩盖遗漏。根因是 accepted plan 的 consumer inventory 与自身全量 type-check scope 不同源，
不是 utils smoke 的业务行为缺陷。

Semantic owner 保持不变：

- Engine success terminal/outcome contract 是成功 response identity 的唯一业务 owner，负责定义
  required typed shape 与不变量。
- Engine 实际调用链负责产生真实 Runner response identity；Host 只机械验证、携带与持久化。
- 两个 utils 只是 synthetic smoke fixture consumer。它们只拥有各自明确模拟的一次成功调用
  输入，可据同一次 `AgentRunRequest` 构造 self-consistent typed fixture identity；不得发明真实
  provider evidence、从 config 推断 actual identity 或成为第二套 identity owner。

正确修复边界是把这两个 direct consumers 纳入 required-contract mechanical closure，而不是
放宽 owner contract。该方案不增加生产抽象、不新增测试 framework，也不建立共享万能 helper，
因此没有过度设计。

## 3. Accepted HEAD 精确调用证据与完整 inventory

### 3.1 两个 utils 的 direct calls

| 文件 / owner-local call path | accepted HEAD 行证据 | 已有同源输入 |
|---|---:|---|
| `utils/smoke_host_public_awaiting_entrypoint.py::_AnswerHandle.events()` | `FinalAnswerData(...)` 第 2010 行 | `_AnswerHandle` 第 1976/1978 行持有本次 `AgentRunRequest`；event 第 2007-2008 行已使用同一 request 的 session/run |
| `utils/smoke_host_public_conversation_memory_scenarios.py::_AcceptingSmokeCompactorRunner.__call__()` | `EngineRunOutcomeFinalAnswer(...)` 第 1748 行 | `__call__` 第 1733 行直接接收本次 compactor `AgentRunRequest`，outcome 第 1749-1750 行已使用其 session/run |
| `utils/smoke_host_public_conversation_memory_scenarios.py::_RejectingSmokeCompactorRunner.__call__()` | `EngineRunOutcomeFinalAnswer(...)` 第 1794 行 | `__call__` 第 1779 行直接接收本次 compactor `AgentRunRequest`，outcome 第 1795-1796 行已使用其 session/run |
| `utils/smoke_host_public_conversation_memory_scenarios.py::_final_answer_event()` | `FinalAnswerData(...)` 第 1843 行 | `_DeterministicCompactWorker.accept()` 第 1643-1645 行同时持有 snapshot 与同一次 `AgentRunRequest`；第 1663 行调用该 helper |

accepted HEAD 对 `utils/` 搜索
`ContextCompactor|FakeContextCompactor|prepare_compactor_proposal_run_input|run_prepared_compactor_proposal`
为零命中。因此本 amendment 不扩展 CR closure。

### 3.2 完整 tests+utils closure

Controller inventory 与本次只读 accepted-HEAD 复核一致：

- `FinalAnswerData(...)`：37 calls / 21 files；
- `EngineRunOutcomeFinalAnswer(...)`：6 calls / 4 files；
- `ContextCompactor` typed-return：7 files；
- 三类去重 union：27 files；
- 两个 utils 与既有 25-file tests identity/typed-return closure 无重叠；
- utils 无 CR hit。

第二次 amendment 的 strict durable builder closure 为 8 files。它与 27-file
identity/typed-return closure 的 overlap 精确为 2 files：
`tests/host/test_compaction_operation.py`、`tests/host/test_dispatch_scheduler.py`。因此 builder
closure 相对 27-file closure 的 set difference 精确为以下 6 files：

- `tests/host/test_compact_material.py`
- `tests/host/test_compaction_terminal.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/test_run_input_builder.py`

其中 `tests/host/test_context_compact_events.py` 在第二次 amendment 前已经属于 S5 allowed owner
tests，但没有 FA/OA/CR hit；其余 5 files 才是第二次 amendment 新增 allowed-file delta。因此
allowed-file delta 仍为 5，不得改称 6；完整 S5 枚举 mechanical union 必须按
`27 identity/typed-return + 8 builder - 2 overlap = 33 files` 去重，不能用 allowed-file delta
代替完整集合运算。历史 25-file tests table、8-file/15-call builder inventory 与既有 review
trace 都保留，不重写已有 review artifact。

Controller 对 initial dual review 的裁决与本 fix 状态：

- MiMo `finding 001` 接受并修复（`accepted-fixed`）：接受 total union 算术 finding，同时按
  Controller 纠正术语，保留 5-file allowed-file delta，并明确 6-file builder-only set difference。
- AgentDS `A5 / final pass` 的 arithmetic conclusion 按 `rejected-set-arithmetic` 拒绝；其关于
  exact 2-file/4-call、semantic owner、identity source、cardinality、`UNAVAILABLE + None`、scope
  与 validation 的其它直接证据继续接受。
- Controller adjudication、MiMo review、AgentDS review 及更早历史 artifacts 均保留原文；本
  proposal 不回写或生成 review/re-review artifact。

对应直接证据 artifacts：

- `docs/reviews/gateflow-wu-cli-interactive-02-s5-utils-closure-amendment-review-adjudication-20260802.md`
- `docs/reviews/plan-review-20260802-000526.md`
- `docs/reviews/plan-review-20260802-000107.md`

## 4. 唯一 allowed implementation delta

### 4.1 两个文件共同不变量

未来获准实现时，只允许修改：

- `utils/smoke_host_public_awaiting_entrypoint.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`

每个文件只可增加：

1. 构造 required identity 所需的精确 typed imports；
2. module-level private deterministic iteration-id 常量和一个 file-local 窄 typed construction
   helper；helper 所有语义输入必须显式、无 default；
3. 本 proposal 枚举的 4 个 constructors 的 required `response_identity` 构造/透传。

两个文件各自定义
`_unavailable_smoke_response_identity(*, request: AgentRunRequest, iteration_id: str, iteration_index: int, runner_call_index: int) -> SuccessfulRunnerResponseIdentity`。
所有参数 required 且无 default；helper 只封装 `SuccessfulRunnerResponseIdentity` 与
`build_runner_request_identity(...)` 的 typed construction，不共享到第三个文件，不读取 config，
不选择 provider/model，不接受 payload bag，也不隐藏调用点的 iteration/call inputs。

常量名和值冻结为：

- awaiting 文件：`_ANSWER_RESPONSE_ITERATION_ID = "awaiting-smoke-answer-iteration"`、
  `_SMOKE_RESPONSE_ITERATION_INDEX = 0`、`_SMOKE_RESPONSE_RUNNER_CALL_INDEX = 1`；
- conversation-memory 文件：
  `_SMOKE_FINAL_RESPONSE_ITERATION_ID = "smoke-final-answer-iteration"`、
  `_SMOKE_ACCEPTING_COMPACTOR_RESPONSE_ITERATION_ID = "smoke-accepting-compactor-iteration"`、
  `_SMOKE_REJECTING_COMPACTOR_RESPONSE_ITERATION_ID = "smoke-rejecting-compactor-iteration"`、
  `_SMOKE_RESPONSE_ITERATION_INDEX = 0`、`_SMOKE_RESPONSE_RUNNER_CALL_INDEX = 1`。

不得复用既有 `_SMOKE_REACTIVE_ITERATION_ID` 充当 final/compactor identity；它只拥有 reactive
compaction-request event 语义。

每次 synthetic invocation 的字段映射固定为：

| identity 字段 | 唯一来源 |
|---|---|
| `run_id` | 当前 `AgentRunRequest.run_id` |
| `attempt_id` / `execution_id` | 当前 `AgentRunRequest.attempt_id/execution_id`；保持成对语义，compactor request 继续为 `None/None` |
| `effective_provider` / `effective_model` | 当前 `AgentRunRequest.runner_spec.provider/model` |
| `iteration_id` | 对应 smoke call site 显式传入的 module-level private deterministic id；不得从 config/manifest/输出推断 |
| `iteration_index` | `0`；该 synthetic request 只模拟一个 iteration |
| `runner_call_index` | `1`；该 synthetic request 只模拟一个成功 Runner call |
| provider request id | `ProviderRequestIdAvailability.UNAVAILABLE` + `None`；这些 stubs 没有接收真实 provider request id |
| `client_correlation_id` | 只由 public `build_runner_request_identity(...)` 从上述完整 request tuple canonical 派生 |

`iteration_index=0` 与 `runner_call_index=1` 是当前 smoke 单调用 cardinality 的显式表示，不是从
config 推断 actual identity。不同 Host run/compactor attempt 使用各自 request.run_id，不能复用
相邻 invocation 的 identity。

### 4.2 `smoke_host_public_awaiting_entrypoint.py`

- `_AnswerHandle.events()` 从 `self._request` 构造 required identity并传给第 2010 行的
  `FinalAnswerData(...)`。
- run/attempt/execution 与 provider/model 只能读 `self._request`；provider request id 固定按
  `UNAVAILABLE + None` 表达“smoke stub 没有该证据”。
- 不修改 `_AwaitingHandle`、tool-awaiting handshake、11-phase state flow、worker id、event 顺序、
  timeout/backoff、stdout marker 或 public Host/Service oracle。

### 4.3 `smoke_host_public_conversation_memory_scenarios.py`

- `_DeterministicCompactWorker.accept()` 用其已收到的 `request` 构造 required identity，并通过
  无 default 的 required typed 参数传给 `_final_answer_event(...)`；该 helper只把参数写入
  `FinalAnswerData.response_identity`，不从 snapshot 反推 provider/model。
- `_AcceptingSmokeCompactorRunner.__call__()` 与
  `_RejectingSmokeCompactorRunner.__call__()` 分别从当前 compactor request 构造 identity并传给
  对应 `EngineRunOutcomeFinalAnswer(...)`。不得在两个 runner 之间缓存/复用 identity。
- 不修改 proposal JSON、semantic rejection、pressure policy、reactive/fallback state path、
  tool payload、suite dispatch、provider assembly、artifact/EventLog audit、stdout marker 或 CLI
  oracle；不得新增 identity 输出。

### 4.4 禁止项

- 不增加 default、optional field、compatibility overload/wrapper、`type: ignore`、掩盖类型错误的
  cast、loose dict 或下游补值。
- 不从 runtime/workspace config、model id CLI 参数、manifest、provider family、相邻 event、
  snapshot string、日志、输出文本或偶然调用顺序反推 actual identity。
- 不新增跨文件共享万能 helper、共享 singleton identity或生产 helper。
- 不改变 smoke invocation 数量、场景、输出、CLI oracle、provider 配置或失败语义。
- 若实现需要超出上述 exact delta，必须停止并退回 Controller 再次修订 plan。

## 5. 目标 plan amendment

本轮只按职责修订目标 plan：

1. §9.1：保留既有 25-file tests closure 与 builder history；加入两个 utils 的精确调用行、
   2-file allowed delta、完整 `FA 37/21`、`OA 6/4`、`CR 7`、27-file union、8-file builder
   closure、2-file overlap、6-file builder-only set difference，以及按 `27 + 8 - 2` 得出的
   33-file mechanical union；冻结 §4 的同源 request identity 数据流和 non-goals。
2. §10.5：将 required-constructor / typed-return pre/post inventory 从 `tests` 扩为
   `tests utils`，冻结 expected counts/paths、完整五类 pattern 去重 33 的可执行检查、full pyright
   closure 与 fail-closed 条件；登记 public awaiting、memory-reactive-compact、
   memory-compact-fallback 三条既有 smoke validation。
3. §13：增加 2-file/4-call exact checklist、request/provider-model source、zero-behavior-delta、
   full pyright/post-inventory/smoke/code-review completion signal；把 total union 修正为 33，并明确
   overlap 2、builder-only set difference 6 与 allowed-file delta 5 是不同集合事实。
4. §15：保留所有历史 accepted trace与 review artifacts，追加第三次 Controller premise
   invalidation、MiMo finding accepted-fixed、AgentDS arithmetic rejected、修订落点和 next gate；
   不得把本 proposal 伪装为 re-review pass。

Docs decision：本轮没有 production/test/utils implementation 或用户可见行为变化，不触发任何
README/design 更新；只允许更新目标 plan 与本 proposal。

## 6. Validation

### 6.1 本 amendment 的文档级验证

本 gate 只允许并执行了只读证据收集与文档检查：

- branch 与 accepted HEAD 精确匹配；preflight dirty ownership 已冻结；
- accepted HEAD 两个 utils 与工作树内容 hash 一致；4 个 direct calls 与 utils CR zero-hit 已复核；
- exact `rg` inventory 重现 FA 37/21、OA 6/4、CR 7 files 与 27-file union；
- 完整五类 pattern 去重重现 8-file builder closure、2-file exact overlap、6-file builder-only
  set difference 与 `27 + 8 - 2 = 33`；第二次 amendment 新增 allowed-file delta 仍为 5；
- 旧 arithmetic 值与错误 delta 公式的 active 残留扫描为零；目标 plan 中同数字的剩余命中仅是
  既有 `prompt.P32-existing-dayu-no-config` scenario id；
- `git diff --check` exit 0；proposal 的 `git diff --no-index --check /dev/null <proposal>`
  因存在预期内容差异 exit 1，但输出为空，表示无 whitespace error；
- 排除 plan/proposal 后，既有 dirty binary diff 的 amendment 后 SHA-256 仍为
  `d19605477fe3c284e5791f8c8bdfb8272bfaac8bbd1876d7d4518c7eff8beeb9`，与 preflight 完全一致；
- Controller adjudication、MiMo review 与 AgentDS review 的文件 hash 与本 fix 前完全一致；两路
  review 的其它直接证据和全部历史 artifacts 均未修改；
- 最终 status scope scan 证明本 fix 只改动目标 plan 与本 proposal；既有 20-file dirty set、两个
  utils、Controller/review artifacts 与其它代码/docs 均未修改、revert、stage 或格式化；
- plan diff hunk 只落在用户指定的 §9.1、§10.5、§13、§15；proposal scope/status wording 不宣称
  review pass、implementation、commit、push 或 PR 完成。

本 gate 禁止 implementation，因此不运行 pytest、pyright、coverage 或 smoke；未运行不能写成
通过。

### 6.2 后续获准 implementation 的闭包

实现前后运行完全相同的 inventory：

```bash
rg -n --glob '*.py' '\bFinalAnswerData\s*\(' tests utils
rg -n --glob '*.py' '\bEngineRunOutcomeFinalAnswer\s*\(' tests utils
rg -n --glob '*.py' \
  '\b(ContextCompactor|FakeContextCompactor|prepare_compactor_proposal_run_input|run_prepared_compactor_proposal)\b' \
  tests utils
rg -n --glob '*.py' '\bbuild_context_compacted_payload\s*\(' tests/host
rg -n --glob '*.py' \
  '\bbuild_context_compaction_attempt_rejected_payload\s*\(' tests/host
```

pre 与 post 都必须保持 FA 37/21、OA 6/4、CR 7 files、union 27；utils 精确只有本 proposal 的
4 个 FA/OA calls、无 CR hit。CB/RB 必须保持 accepted 8 calls / 6 files、rejected 7 calls / 4 files、
builder union 8；必须执行目标 plan §10.5 的完整五类 pattern 去重 block，直接断言 27-file 与
8-file closure 的 overlap 为上述 2 files、builder-only set difference 为上述 6 files、完整
mechanical union 为 33。第二 amendment 新增 allowed-file delta 仍为 5，仅用于 allowed scope
检查，不得用来替代 builder closure 或把 allowed delta 改称 6。任何新 file/call/type-return hit
都 fail closed 回到 Controller。

完整类型检查：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

相关既有 smoke：

```bash
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-cli-interactive-02-s5-awaiting-identity

DEEPSEEK_API_KEY=test-provider-key \
python utils/smoke_host_public_conversation_memory_scenarios.py \
  --suite memory-reactive-compact \
  --log-level CRITICAL

DEEPSEEK_API_KEY=test-provider-key \
python utils/smoke_host_public_conversation_memory_scenarios.py \
  --suite memory-compact-fallback \
  --pressure-mode auto \
  --log-level CRITICAL
```

awaiting smoke 保持 11-phase public path 与既有 pass marker；reactive suite 覆盖 accepting
compactor outcome 与 ordinary final；fallback suite 覆盖 rejecting compactor outcome 与 ordinary
final。后续 code review 必须逐一核对 4 个 identity 的 request/run/provider-model 同源性与
zero-behavior/output/config/oracle delta。

按项目规则，两个 `utils/` 文件不新增测试且没有 coverage 要求；该规则不免除 full pyright、
post-inventory、上述既有 smoke 或后续 code review。production modified files 的既有 >=80%
coverage 要求不变。

## 7. Non-goals

- 不修改任何 production/test/utils 代码或其它 docs；不 revert 既有 dirty S5 implementation。
- 不执行 S5 implementation，不运行实现级 pytest/pyright/coverage/smoke。
- 不改变 `SuccessfulRunnerResponseIdentity`、`FinalAnswerData`、
  `EngineRunOutcomeFinalAnswer`、`ContextCompactor` 或 durable payload schema。
- 不改变 smoke scene/suite、public flow、provider config/assembly、输出、CLI oracle、artifact、
  EventLog audit或异常语义。
- 不新增共享万能 helper、测试 fixture framework、adapter或兼容层。
- 不把 synthetic `UNAVAILABLE` identity 宣称为真实 provider continuity evidence；行为项 29/G06
  的外部证据边界不变。
- 不修改、重写或生成 planreview/re-review artifact。
- 不 commit、push、创建 PR、修改外部 issue/comment 或其它外部状态。

## 8. Residual risks

| 风险 | 分类 | 处理 |
|---|---|---|
| utils identity 错取 config/manifest provider-model，或复用相邻 request | `fixed in current amendment` | §4 冻结每个 call 直接使用当前 `AgentRunRequest` 的 run/attempt/execution 与 `runner_spec.provider/model`；post-inventory、smoke 与 code review 复核 |
| synthetic stub 没有 provider request id却伪装 present | `fixed in current amendment` | 四处全部冻结为 `UNAVAILABLE + None`，不冒充真实 provider evidence |
| helper 演化为共享万能 seam或隐藏 default | `fixed in current amendment` | 只允许两个 file-local narrow helper，全部语义输入显式、无 default；跨文件 helper与 compatibility 明确禁止 |
| 把 5-file allowed-file delta 误当 builder closure 相对 identity closure 的完整差集 | `fixed in current amendment` | §3.2/§5/§6 冻结 27-file identity closure、8-file builder closure、2-file overlap、6-file builder-only set difference 与 33-file union；完整五类 pattern 直接去重，不再用 delta 代替集合 |
| accepted HEAD 后出现新的 tests/utils constructor 或 typed-return consumer | `requiring explicit controller decision` | implementation pre-inventory fail closed，先再次 amendment，不越界修补 |
| 两个 utils 未新增测试/coverage | `covered by later approved slice` | 项目规则明确豁免；full pyright、post-inventory、三条既有 smoke 与 code review 是 required closure |
| 本轮未运行 implementation validation | `covered by later approved slice` | 当前授权禁止 implementation；由两路 independent re-review 与 Controller 最终接受 amendment 后的 S5 implementation 执行 §6.2 |
| synthetic smoke identity 被误当真实 provider continuity | `covered by later approved slice` | 保持行为项 29/G06 外部 evidence owner，不用 smoke fixture关闭该 gap |

没有 unclassified residual risk。本 proposal 不宣称第三次 amendment 已被接受。

## 9. Completion 与 handoff

- [x] Preflight branch、HEAD、dirty ownership 与 protected hash 已记录。
- [x] Root cause 与 semantic owner 已基于 accepted HEAD direct calls 判定。
- [x] 精确 2 files / 4 calls 与 utils CR zero-hit 已记录。
- [x] 完整 FA 37/21、OA 6/4、CR 7、identity union 27、builder union 8、overlap 2、builder-only set difference 6 与 mechanical union 33 已冻结；第二次 amendment 新增 allowed-file delta 仍为 5。
- [x] 唯一 allowed delta、non-goals、后续 validation 与 residual risks 已 code-generation-ready。
- [x] MiMo arithmetic finding 已按 Controller 裁决修复（`accepted-fixed`）；AgentDS 的 arithmetic conclusion 已按 `rejected-set-arithmetic` 记录，其它直接证据继续接受。
- [x] 历史 accepted trace、Controller adjudication 与两路 review artifacts 未重写。
- [x] `git diff --check`、proposal whitespace check 与 protected dirty hash 前后对比通过。
- [x] Production/test/utils implementation、revert、commit、push、PR 均未执行。
- [ ] MiMo 与 AgentDS simultaneous independent re-review 尚未执行。
- Completion status：`accepted arithmetic finding fixed / awaiting simultaneous independent re-review`。
- Next gate：MiMo 与 AgentDS simultaneous independent re-review；两路独立 durable re-review
  artifacts 与 Controller 最终裁决完成前不得进入 implementation。
- Artifact path：
  `docs/reviews/wu-cli-interactive-02-s5-f13-utils-closure-plan-amendment-proposal-codex.md`
