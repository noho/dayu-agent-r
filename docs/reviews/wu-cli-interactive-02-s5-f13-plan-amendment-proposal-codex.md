# WU-CLI-INTERACTIVE-02 S5/F13 Plan Amendment Proposal

## 0. Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Slice / finding：`S5 / F13`
- Gate 事件：accepted-plan premise invalidation；只做 plan amendment proposal
- Base HEAD：`331d38dcaeebe3a929b7fa52d4e161a1c6504c55`
- 分支：`codex/interactive-oracle`
- 生成时间：`2026-08-01T21:34:19+08:00`
- Preflight：工作树在本次 amendment 前干净；HEAD 与用户指定 base 完全一致；分支不是 protected trunk
- Reviewed target：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md` 的 S5 allowed-file / validation closure
- Amendment artifact：`docs/reviews/wu-cli-interactive-02-s5-f13-plan-amendment-proposal-codex.md`
- 允许修改：目标 plan 与本 proposal artifact
- 明确禁止：生产代码、测试、其它产品/设计文档、implementation、commit、push、PR
- Completion status：`accepted finding fix applied / awaiting independent amendment re-review`
- Next entry point：`plan amendment re-review`；不得直接进入 S5 implementation

## 1. 结论与第一性原理判断

accepted-plan premise invalidation **成立，且严重性评估准确**。

F13 已冻结的 public contract 要求：

1. `FinalAnswerData.response_identity` required；
2. `EngineRunOutcomeFinalAnswer.response_identity` required；
3. `ContextCompactor.compact()` 与 prepared-compactor success path 返回
   `candidate + SuccessfulRunnerResponseIdentity` 的 typed proposal。

Python required dataclass field 与 protocol return type 不会只影响 owner contract tests；所有
现存直接构造点、test double override/delegation 以及直接 candidate consumer 都会在类型检查
或执行期发生必然机械错误。原 §9.1 只允许其中 5 个文件，遗漏 20 个，因此 implementation
若仍遵守旧 allowed files，只能选择以下错误路径之一：漏改导致 pyright/pytest 失败，或给
required contract 增加 default/optional/compatibility seam。后者直接破坏 F13 的 fail-closed
语义，所以必须在 implementation 前修订 plan boundary。

正确修复不是放宽生产契约，而是扩大测试机械闭包：生产 semantic owner 与生产直接构造点
保持原 §9.1 不变；测试只在真实 fake/event/outcome owner 处显式提供同源 identity。

## 2. Semantic owner 与直接代码证据

### 2.1 生产 owner 未发生漂移

- `dayu/engine/contracts/runner_identity.py` 是 `RunnerRequestIdentity` 与 F13 新 success
  response identity 的 contract owner。
- `dayu/engine/contracts/engine_events.py:432` 定义 `FinalAnswerData`；
  `dayu/engine/contracts/agent_run.py:138` 定义 `EngineRunOutcomeFinalAnswer`。
- `dayu/engine/agent.py:2449` 是生产 `FinalAnswerData(...)` 直接构造点，
  `dayu/engine/agent.py:3011` 是生产 `EngineRunOutcomeFinalAnswer(...)` 直接构造点；两者
  已在原 §9.1 的 `dayu/engine/agent.py` allowed boundary 内。
- `dayu/host/compaction.py:1930` 定义 `ContextCompactor` protocol；生产
  `LLMContextCompactor`、operation flow 与 durable writers 也都已在原 §9.1。

因此本次没有生产 allowed-file 缺口，不新增 production owner、adapter 或 compatibility
layer。

### 2.2 HEAD 测试 inventory

使用 repo-wide `rg` 对 HEAD 做直接构造与 typed-port 枚举，结果为：

- 35 个 `FinalAnswerData(...)` 直接构造，分布在 19 个文件；
- 4 个 `EngineRunOutcomeFinalAnswer(...)` 直接构造，分布在 3 个文件；
- 7 个文件直接实现、override、delegate 或消费 `ContextCompactor` / prepared-compactor
  typed return；
- 三类去重后共 25 个必然机械变更文件；原 §9.1 已覆盖 5 个，遗漏 20 个；
- 未发现 `FinalAnswerData` / `EngineRunOutcomeFinalAnswer` alias 构造，也未发现
  `ContextCompactor` 的 `AsyncMock` / autospec 隐式 return 配置。

完整文件清单如下。`FA(n)`、`OA(n)` 与 `CR` 的含义和 plan §9.1 相同。

| 文件 | 直接证据 | 原 §9.1 |
|---|---|---|
| `tests/engine/test_engine_event_contract.py` | `FA(2)` | 已允许 |
| `tests/engine/test_smoke_async_agent_providers.py` | `FA(1)` | 遗漏 |
| `tests/service/test_entrypoint_runtime_interactive_path.py` | `FA(1)` | 遗漏 |
| `tests/host/fake_compaction.py` | `CR` | 遗漏 |
| `tests/host/public_smoke_support.py` | `FA(1)` | 遗漏 |
| `tests/host/recovery_support.py` | `FA(2)` | 遗漏 |
| `tests/host/stress_support.py` | `FA(1)` | 遗漏 |
| `tests/host/transient_stream_support.py` | `FA(1)` | 遗漏 |
| `tests/host/test_active_cancel_dispatch.py` | `FA(2)` | 遗漏 |
| `tests/host/test_compact_artifact_store.py` | `CR` | 遗漏 |
| `tests/host/test_compaction_cancellation_scope.py` | `OA(1)` | 遗漏 |
| `tests/host/test_compaction_contract.py` | `CR` | 遗漏 |
| `tests/host/test_compaction_operation.py` | `CR` | 已允许 |
| `tests/host/test_dispatch_scheduler.py` | `FA(3) + CR` | 已允许 |
| `tests/host/test_effective_execution_config.py` | `FA(1)` | 遗漏 |
| `tests/host/test_engine_ingest_mapping.py` | `FA(10) + CR` | 已允许 |
| `tests/host/test_llm_compaction.py` | `OA(1) + CR` | 已允许 |
| `tests/host/test_open_host_runtime.py` | `FA(3)` | 遗漏 |
| `tests/host/test_per_run_tool_selection.py` | `FA(1)` | 遗漏 |
| `tests/host/test_phase5_local_execution_integration.py` | `FA(1)` | 遗漏 |
| `tests/host/test_public_compact_smoke.py` | `FA(1) + OA(2)` | 遗漏 |
| `tests/host/test_public_retry_replay.py` | `FA(1)` | 遗漏 |
| `tests/host/test_recovery_dispatch.py` | `FA(1)` | 遗漏 |
| `tests/host/test_submit_followup_public_contract.py` | `FA(1)` | 遗漏 |
| `tests/host/test_watch_session_events.py` | `FA(1)` | 遗漏 |

`CR` 的 7 个文件精确为：

- `tests/host/fake_compaction.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_llm_compaction.py`

## 3. Amendment 变更清单

### 3.1 目标 plan 修改

仅修订 `docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`：

1. §9.1 保留既有生产 allowed files 与 owner-level tests；增加上述 25 文件的完整
   mechanical closure，并明确实际新增缺口为 20 个文件。
2. §9.1 冻结机械改动边界：只补 required typed identity、迁移 return annotation、
   解包 candidate 或保留 paired identity；不得改变原测试场景和行为断言。
3. §9.3 明确 `tests/host/fake_compaction.py` 的外层 `FakeContextCompactor` 必须由 fake
   owner 显式构造安全完整 identity 并返回 typed proposal：
   - non-sensitive test-only provider/model；
   - 使用 canonical `build_runner_request_identity()`；
   - run/iteration/call 来自同一次 synthetic compactor invocation；
   - `attempt_id/execution_id` 显式为 `None`；
   - 无真实 provider request id 时使用 `UNAVAILABLE + None`；
   - 不允许 optional default、旧 return signature、compatibility overload。
4. §9.3 保持 `FakeConversationCompactorVNext` 的 candidate-only owner 不变；只变换
   candidate 的 custom fake 必须保留同一个 paired identity，模拟另一成功 call 时才显式
   构造该 call 自己的 identity。
5. §9.6 与 §13 S5 checklist 增加 25 文件机械闭包、同源 identity 与禁止消音规则。
6. §10.5 focused validation 纳入全部 direct test modules、contract tests 与 service
   direct constructor；完整回归扩大为 `pytest tests/engine tests/host -q`，并由全量
   pyright 关闭 test-support module 类型检查。
7. §10.5 增加 implementation 前后 inventory 重扫；出现新 hit 必须先回到 controller
   修订 allowed files。

### 3.2 同源 test identity 规则

- 接收 `AgentRunRequest` 的 fake runner，从该 exact request 与该次 fake response 构造
  identity；不得从相邻 request 或固定全局 identity 复制。
- 产出 `EngineEvent` 的 fake handle，从同一个 snapshot/event 的 run、attempt、
  execution 与 iteration 输入构造 identity；contract-only fixture 使用完整 file-local
  typed fixture，但仍保持 event/outcome sibling fields 一致。
- 无 provider request id 的 fake 明确表达 `UNAVAILABLE + None`，不伪造 vendor id，
  不把 client correlation id 当 provider id。
- candidate-transforming compactor 不重建 identity；identity 与 candidate 是同一个
  `CompactorProposal` 的 paired value。

这些规则把测试数据修复放在 test owner boundary，避免下游 consumer、adapter 或
assertion helper 反推/补偿业务语义。

## 4. Non-goals

- 不修改任何生产代码、测试代码或 README/design/oracle/scenario。
- 不改变 F01-F13 数量、accepted oracle、S1-S4 已接受实现或 S5 public contract。
- 不给 required identity 增加 default、optional、factory fallback、compatibility
  constructor、wrapper 或 overload；不得用仅为掩盖不匹配的 cast / `type: ignore` 消音。
- 不把 test-only synthetic identity 当成真实 provider continuity evidence；G06/行为项 29
  的真实 provider 证据仍由既有 S6/external validation 边界负责。
- 不新增测试公共 helper、生产 tracing framework、schema 字段、F 项或文档职责范围。
- 不执行 S5 implementation，不运行实现测试/pyright，不 commit、push 或创建 PR。

## 5. Validation

### 5.1 本 proposal 已执行的只读/文档验证

- `git branch --show-current`：`codex/interactive-oracle`
- `git status --short`（修改前）：空
- `git rev-parse HEAD`：`331d38dcaeebe3a929b7fa52d4e161a1c6504c55`
- repo-wide `rg`：得到 §2.2 的 35 / 19、4 / 3、7 与 25-file union
- alias/mock scan：未发现遗漏的 alias constructor 或 mock-configured compactor return

完成 amendment 后已运行文档级检查：

```bash
git diff --check
git diff --no-index --check /dev/null \
  docs/reviews/wu-cli-interactive-02-s5-f13-plan-amendment-proposal-codex.md
git status --short
rg -n --glob '*.py' '\bFinalAnswerData\s*\(' tests
rg -n --glob '*.py' '\bEngineRunOutcomeFinalAnswer\s*\(' tests
rg -n --glob '*.py' \
  '\b(ContextCompactor|FakeContextCompactor|prepare_compactor_proposal_run_input|run_prepared_compactor_proposal)\b' \
  tests
```

结果：tracked diff 与 untracked artifact 均无 whitespace error；`git status --short`
只列目标 plan 与本 artifact；程序化 union audit 得到
`35 calls / 19 files`、`4 calls / 3 files`、`7 CR files`、`25 union files`，plan 与
artifact 的 missing path 都为 0；HEAD 仍为指定 base。`git diff --no-index --check`
因 artifact 是新增文件按 no-index 语义返回 1，但输出为空，表示只有预期内容差异、没有
whitespace error。

因为本 gate 明确禁止 implementation，本次不运行实现 pytest、coverage 或 pyright；
这些命令已经完整写入 amended §10.5，由后续获批 S5 implementation 执行。

### 5.2 后续 S5 validation closure

- focused Engine contract/behavior tests覆盖 success identity 构造与透传；
- focused Host tests覆盖 compactor proposal、accepted/rejected binding 与所有 direct
  constructor test modules；
- `pytest tests/engine tests/host -q` 覆盖四个 support module 的真实消费者；
- `pytest tests/service/test_entrypoint_runtime_interactive_path.py -q` 覆盖 Service direct
  constructor；
- `python -m pyright dayu/ tests/ utils/` 必须对 required field 与 protocol return 零遗漏；
- inventory 重扫与 allowed-file diff check 阻止 HEAD 漂移和范围外机械补丁。

## 6. Residual risks 与分类

| 风险 | 分类 | 处理 |
|---|---|---|
| amendment 后 HEAD 新增 direct constructor / compactor fake | `requiring explicit controller decision` | S5 implementation 前重扫；出现新 hit 即停止并再次 amend，不在范围外修改 |
| test-only safe identity 无法证明真实 provider continuity | `covered by later approved slice` | 保持行为项 29/G06 外部证据边界；不得用 fake 宣称关闭 |
| broad Host/Engine tests、pyright、coverage 尚未运行 | `covered by later approved slice` | 本 gate 禁止 implementation；由 amended §10.5 在获批 S5/S6 执行 |
| synthetic fake identity 与 production prepared-input identity 语义混用 | `fixed in current amendment` | §9.3 明确 fake owner、candidate-only owner、同源构造与 paired identity 保留规则 |
| optional/default compatibility 掩盖遗漏调用点 | `fixed in current amendment` | §9.1/§9.3/§9.6/§10.5/§13 明确禁止并由全量 pyright 关闭 |

没有 unclassified residual risk。proposal 需经独立 amendment review 后才能恢复 Gateflow；
本 artifact 不宣称 accepted plan 已重新通过。

## 7. Completion

- 直接证据：完整记录。
- Allowed-file amendment：已写入目标 plan。
- Validation closure：已写入目标 plan。
- 生产/测试实现：未执行。
- Commit/push/PR：未执行。
- Next entry point：`plan amendment re-review`。
- Artifact path：
  `docs/reviews/wu-cli-interactive-02-s5-f13-plan-amendment-proposal-codex.md`

## 8. Accepted-finding fix trace

| Review item | Controller decision | Fix status | Proposal / plan 落点 |
|---|---|---|---|
| DS OBS-001 | `accepted-low` | 已修复 | Plan §10.5 已明确 `tests/host/fake_compaction.py` 由已列消费者测试与全量 pyright 覆盖，并关联 §9.3 的 `FakeContextCompactor` identity owner 与 paired identity 保留规则。 |

DS OBS-002 维持 `rejected-invalid-premise`，DS OBS-003 维持
`rejected-already-covered`；本 fix 未据二者改变 plan、allowed files、production/test scope
或既有 identity / inventory validation 规则。

本 fix 未修改 production/test/allowed-file scope，未执行 implementation；下一步必须由
MiMo 与 DS 独立 re-review，本 artifact 不宣称 amended plan 已通过。

文档级 fix validation：目标 plan 的 `git diff --check` 返回 0；本未跟踪 proposal 的
`git diff --no-index --check` 输出为空（仅因存在预期内容差异返回 1）；fix 后
`git status --short` 与 preflight 路径集合一致，没有新增修改路径。
