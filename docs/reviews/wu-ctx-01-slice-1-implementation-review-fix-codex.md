# WU-CTX-01 Slice 1 implementation review fix

## 1. Gate 与范围

- Work Unit：`WU-CTX-01`
- Gate：Slice 1 implementation review fix
- 基线 HEAD：`ed43bcf2`
- 控制性裁决：
  `docs/reviews/wu-ctx-01-slice-1-implementation-review-controller-adjudication.md`
- 结论：已逐项实现裁决接受的 `CTRL/REVIEW-IMPL-01..09`，未实施
  rejected / deferred findings。
- 提交状态：未 commit；production/tests 在 Controller 双路 re-review 通过前仍为
  **not accepted**。

本轮没有修改 Controller-owned
`docs/host/issues-implementation-control.md` 或 Controller adjudication。workspace
中这些文件的既有状态不属于本 fix 的写入范围。

## 2. 第一性原理与 semantic owner

裁决指出的问题均成立，不是单纯测试或展示差异：

1. admission 已持久化实际工具事实，但 dispatch 对 `all` 重读当前配置，导致 durable
   truth 与 actual request 分叉；
2. no-budget plan 丢失 stage，使 manifest 持久化错误事实；
3. continuation source failure 由 Engine 宽泛捕获，丢失 strict source owner 的错误
   分类；
4. manifest EventLog row 与 hot payload 是同一 canonical fact 的 row/projection，
   缺少交叉 identity 校验会允许错误 source；
5. matrix、sizing parser 与 docstring/dead code 缺口会削弱 owner contract。

修复因此落在 admission/dispatch shared contract、RunInput strict source loader、
manifest parser 与 context-budget owner，而没有在 Engine consumer、fixture 或错误消息上
增加 fallback / compatibility shim。

## 3. Accepted findings 修复映射

### CTRL-IMPL-01：exact effective tool facts

- 在 `dayu.host.admission` 建立共享 typed contract：
  `EffectiveBusinessToolSelector`、`EffectiveToolFacts`、
  `effective_tool_facts_json()`、`parse_effective_tool_facts()` 与
  `validate_effective_tool_facts_runtime()`。
- producer 与 consumer 共用 exact field set，严格校验 selector、requested names、
  effective names、完整 business bundle digest、selected schema digest、
  `tool_snapshot_ref`、display snapshot 与 typed source refs。
- `selector=all` 只保留 caller intent；dispatch 始终使用 admission 冻结的 exact
  effective names，不再以 `None` 表示“选择当前全部工具”。
- ordinary/queued dispatch 在 Attempt 创建前验证当前 runtime 的完整 business
  bundle、source refs、selected schemas、display snapshot 与冻结 digest。任一 drift
  fail closed，零 Attempt、零 manifest、零 start。
- `subset` 与普通 requested `none` 继续冻结 admission 时的完整 available bundle
  truth；`none` 仅表示 effective names 为空，不把 bundle truth抹成空。
- 永久 no-tool repair replay 单独使用同一 typed contract 产生
  `selector=none`、exact empty names、empty bundle/schema digest、empty source refs；
  replay 传 `tooling_options=None`，不新增当前 tooling 输入，也不读取或校验无关业务
  bundle。
- steer 保留 caller intent：non-replay 且 policy/runtime 禁用工具时，显式非空
  `subset` fail closed；`all` 仍可按既有语义被 policy 禁用；`none` 保持 no-tool。
- 删除旧 loose/local parser 与旧手写 payload 兼容路径；相关 fixture 全部迁移到 current
  exact producer。

Owner/反例测试覆盖：

- `all` exact match、queued 后新增工具、同名 schema drift；
- `subset`、普通 `none`、repair replay empty truth；
- bundle digest、selected schema digest/ref、source ref corruption；
- drift 后零 Attempt / `RUN_STARTED` / manifest；
- replay 不读取当前 tooling；
- `subset + allow_tool_calls=False` fail closed。

### CTRL-IMPL-02：NoBudgetDispatchStart stage

- `NoBudgetDispatchStart` 显式携带 `ContextSizingStage`。
- ordinary、post-compact、dispatch-fallback producer 分别传入实际 stage。
- commit owner 只消费 plan 中的 `stage`，不按 reason、Run status 或 caller 反推。
- contract test 覆盖三种 no-policy manifest stage。

### CTRL-IMPL-03：continuation typed closed reason

- `dayu.host.run_input` 新增
  `PreparedRunnerCallSourceFailureCategory` closed union：
  `TOOL_SCHEMA / POLICY / REQUEST_SEMANTICS`，以及携带 category 的
  `PreparedRunnerCallSourceError`。
- strict loader 以 owner contract 分类；Engine 只按 typed category 做封闭映射，不再
  捕获宽泛异常后统一归为 tool，也不按异常 message 猜测。
- projection 检查仍在最前；source loader 内固定顺序为：
  manifest/hot/candidate policy-independent payload/tool snapshot → exact policy →
  request semantics。
- candidate policy-independent pass 先验证 schema/Session/Run/cursor/messages、
  tool schemas/disable/mode/source refs 与 selected-tool descriptor，不读取 policy；
  complete parser 在 policy/request owner 校验后仍执行 exact field-set 与 digest
  校验，没有放宽 parser。
- 反例确认同一 source 同时 tool+policy 损坏时为 `TOOL_SCHEMA`，tool valid +
  policy invalid 时为 `POLICY`。
- continuation manifest contract test 覆盖唯一四类 closed reason：
  projection → tool → policy → request。

### CTRL-IMPL-04：EventLog row / hot identity

- source manifest finder 对 canonical EventLog row 的
  session/run/attempt/execution/type 与 source Run、caller、hot payload 做严格同源
  校验。
- 同 Attempt/execution 的 continuation limited manifests 仍执行 row/hot identity
  校验，但 iteration pair 非空时不参与 pre-start match/duplicate 判断。
- compactor proposal 也先验证 row/hot identity，再按独立 caller identity 跳过。
- 只有 iteration id/index 均为 `None` 的 dispatch pre-start kind 可成为 source；
  一个 pre-start 加多个 continuation 合法，两个 pre-start fail duplicate。
- 测试覆盖 row/hot 交叉错配、pre-start+continuation 唯一返回 pre-start、双
  pre-start duplicate。

### REVIEW-IMPL-05：5×3 owner matrix

- owner test 补齐 `CONTINUATION × normal/soft/hard` 三格，冻结完整 5 stage ×
  3 pressure = 15 cells。
- docstring 同步为 5×3。
- unknown stage / pressure 使用测试侧类型收窄制造反例，production 不增加兼容分支。

### REVIEW-IMPL-06：compactor sizing invariant

- manifest parser 明确拒绝 `compactor_proposal + COMPLETE`。
- 保留并补强 closed invariant：compactor proposal 只能
  `NOT_APPLICABLE`；dispatch-relevant runner call 不能 `NOT_APPLICABLE`。
- 正反 contract tests 覆盖上述组合。

### REVIEW-IMPL-07：dead source policy loader

- 删除 `engine_ingest._source_policy_snapshot_in_transaction`。
- 同步删除只为该零 caller helper 保留的 imports/constants。

### REVIEW-IMPL-08：dead admission direct-running wrapper

- 删除 admission 层零 caller `_create_running_admission_result`。
- 同步删除其 direct-running imports；未扩大范围清理底层测试基础设施。

### REVIEW-IMPL-09：estimator digest docstring

- `BudgetEstimate.estimator_digest` docstring 改为真实语义：estimator contract、
  完整 estimate input 与固定常量的 digest，不再声称包含 policy payload。

## 4. Controller 途中复核专项

1. repair replay 永久 no-tool，不与当前 tooling bundle/source drift 重新耦合；
2. continuation limited manifests 不参与 pre-start duplicate 判断，但仍校验
   EventLog/hot identity；
3. steer 明确保留 `SUBSET / ALL / NONE` caller intent 与 policy-disabled 差异；
4. strict source loader 固定 projection → tool → policy → request 优先级，并以 typed
   category 投影。

四项均有 owner-level contract 或反例测试。

## 5. Rejected / deferred scope

未实施 Controller §4 的 rejected / deferred 项，包括：

- `source_boundary_refs` 新 schema/重复位置校验；
- COMPLETE redundant `None` guard、hard closeout docstring 风格调整；
- 仅为消除 `cast` 添加 assert；
- recovery `CAS_LOST` 不可达分支；
- 改变 startup page rollback；
- optional `PayloadStore` 防御、无状态 primitive 强制注入；
- 改变 rollback signal public exception contract；
- sizing factory 额外自校验。

也未引入 Slice 2 `CONTEXT_BUDGET_EVALUATED` / public projection，未引入 Slice 3
usage-anchor producer、selection 或 durable usage anchor。

## 6. 验证

### Focused tests

```text
pytest -q \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_context_budget.py \
  tests/host/test_runner_call_hot_payload_contract.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_run_input_builder.py

397 passed in 3.97s
```

最新 source owner 优先级专项：

```text
pytest -q tests/host/test_engine_ingest_mapping.py \
  -k 'source_loader or continuation_source_failure_projects_typed_closed_reason'

9 passed, 107 deselected in 0.61s
```

### Full Host tests

```text
coverage erase
pytest -q tests/host --cov=dayu.host --cov-branch --cov-report=

2202 passed, 2 skipped, 6 deselected in 64.25s
```

默认 `pyproject.toml` 排除 6 个 `stress` tests；2 个测试按各自 skip 条件未执行。
optional real smoke / quota 不伪装为已执行证据。

### Full pyright

```text
python -m pyright dayu/ tests/ utils/

0 errors, 0 warnings, 0 informations
```

### Changed production branch coverage

| 文件 | Coverage |
| --- | ---: |
| `dayu/host/_runner_call_manifest.py` | 85% |
| `dayu/host/accepted_result_projection.py` | 93% |
| `dayu/host/admission.py` | 85% |
| `dayu/host/command.py` | 88% |
| `dayu/host/compact_payload.py` | 87% |
| `dayu/host/compaction_operation.py` | 91% |
| `dayu/host/context_budget.py` | 88% |
| `dayu/host/context_fallback.py` | 87% |
| `dayu/host/dispatch.py` | 84% |
| `dayu/host/durable/run_transition.py` | 88% |
| `dayu/host/durable/schema.py` | 95% |
| `dayu/host/durable/state.py` | 83% |
| `dayu/host/engine_ingest.py` | 85% |
| `dayu/host/memory.py` | 88% |
| `dayu/host/open_host.py` | 86% |
| `dayu/host/recovery.py` | 80% |
| `dayu/host/run_input.py` | 82% |
| `dayu/host/waiting.py` | 83% |

全部 changed production files 单文件 branch coverage `>=80%`；合计 85%。

### Static audits

- `git diff --check`：通过。
- direct-promotion stale symbol grep：零命中。
- dead source-policy loader / admission direct-running wrapper / 旧 effective-tool loose
  parser grep：零命中。
- Slice 2 `CONTEXT_BUDGET_EVALUATED` 新增符号 grep：零命中。
- Slice 3 usage-anchor producer/consumer 新增路径 grep：零命中。Slice 1 contract 中已有
  `ContextEstimateMethod.USAGE_ANCHORED` closed vocabulary，但没有 anchor 执行实现。
- effective tool payload fixtures audit：执行路径与 owner tests 使用 shared current
  producer；保留的 corruption fixtures只用于 strict failure 测试。

### README audit

- 已按 `dayu/host/README.md` 的 Agent 更新约束补充 admission effective tool facts、
  `all` exact consumption、pre-start drift fail-closed 与 repair replay no-tool 边界。
- 已复核 `tests/README.md`：Slice 1 implementation 已记录 focused 命令与现有测试层，
  本 fix 未新增测试层或新的稳定运行方式，无需再扩写。
- 未改变用户安装、CLI、Web/WeChat、根 README、分层装配或 Engine public contract，
  其余 README trigger 未命中。

## 7. Residual risk

- optional real compactor smoke 未启用；
- Gemini 等真实 provider quota / endpoint smoke 未执行；
- 默认 pytest 配置排除 6 个 stress tests。

这些是 Controller 明确保留的外部/可选验证风险，不以 mock 或本地 deterministic
tests 冒充。除此之外，当前未发现本 Slice accepted findings 的已知 residual
correctness gap；最终 acceptance 仍取决于 Controller 双路 implementation re-review。
