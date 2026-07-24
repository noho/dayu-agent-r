# WU-CTX-01 Slice 1 Implementation Resume

## 0. Gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- gate：`implementation / Slice 1 resume`
- lane：`AgentCodex implement`
- accepted first-call producer plan commit：`ed43bcf2`
- Controller final pass：
  `docs/reviews/wu-ctx-01-slice-1-first-call-producer-plan-rereview-controller-adjudication.md`
- 真源：主 plan 与 `docs/host/design.md` §25
- status：`implementation complete / ready for implementation review`
- commit / push / PR：均未执行

本轮只完成 Slice 1。未实现 `CONTEXT_BUDGET_EVALUATED`、public projection、usage
anchor、provider usage prediction或 correlation。既有 Controller-owned
`docs/host/issues-implementation-control.md` diff 原样保留，未纳入本轮编辑；未修改
其它 review artifact。

## 1. First-principles judgment

Slice 1 动机成立。原实现只有 ordinary / reactive 局部 candidate 或 manifest producer，
但 Attempt start 的语义 owner 分散在 admission、scheduler、wait resume、startup /
attachment recovery 与 Engine continuation。只修单一入口会允许以下真实错误：

- startup 从 current config 重建历史输入，而不是 exact replay；
- steer / wait resume 在 `RUN_STARTED` 后才补写 manifest；
- failed / lost wait 产生伪 resume artifacts；
- admission / terminal owner 直接把 queued Run 提升，绕过 ordinary governance；
- Engine continuation 误用 pre-start recorder；
- source Run policy 或 worker delegate identity 漂移后仍继续执行。

正确 owner 是：strict source fact reader 负责 exact input policy；RunInput owner 负责
完整 candidate；`ContextSizingStage × ContextPressureLevel` closed matrix 负责 action；
manifest owner 负责 exact runner input；各 lifecycle owner 只能在 manifest 已提交后
执行 start transition。实现沿这些 owner boundary 收口，没有引入 loader/current-config
fallback、start 后补写、fixture-only compatibility 或 loose parsing。

## 2. 初始 18 个 full Host failures 定位

恢复时先运行 full Host，得到 18 failures。直接堆栈与 durable rows 将其归为以下
同源迁移问题，而非新的 plan 外 production owner：

1. 多个测试从
   `tests.host.test_resolve_wait_command._create_execution_handle` 间接取得固定 baseline，
   与各自 scheduler / opener 的 execution、memory、tool、context truth 不同源；
2. recovery / wait / open-host fixtures 直接制造 `RUNNING` 或 recovery state，缺少新
   contract 要求的 candidate / manifest-before-start；
3. `create_host_admission_service(...)` 的新增语义依赖仍在部分 construction site
   隐式缺失；
4. open-host ordering 断言仍假设两个 terminal/start fact 相邻，没有容纳必须先提交的
   `RUNNER_CALL_INPUT_ASSEMBLED`；
5. legacy direct-promotion tests/imports 仍冻结已删除的 admission/durable 旁路。

修复落在 owner 或直接上游输入边界：

- 新增 `tests/host/execution_handle_support.py` 公共 helper；
- 每个测试或专属 support 显式传入与被测 scheduler/open options 同源的
  `OrdinaryRunExecutionBaseline`、memory/tool/context truth；
- recovery / wait fixtures 改为真实 governed start 流；
- construction site 显式装配所有语义依赖；
- ordering 断言改为验证 manifest-before-start；
- 删除 direct-promotion 专属 tests/imports，而不是给 production 加兼容分支。

最终审计确认没有测试导入
`tests.host.test_resolve_wait_command._create_execution_handle`，也没有通过该文件复用
固定 baseline。

## 3. Production implementation evidence

### 3.1 Candidate、sizing、action 与 manifest

- `dayu/host/context_budget.py`
  - `ContextSizingStage` 闭集为 `ORDINARY`、`POST_COMPACT`、
    `DISPATCH_FALLBACK`、`REACTIVE_POST_COMPACT`、`CONTINUATION`；
  - 五 stage × 三 pressure 共十五格以显式 closed match 穷举；
  - candidate sizing 使用完整 messages / selected tools / policy 与 conservative
    atoms；diagnostic metadata 不参与预算；
  - `CONTINUATION` 保持 limited manifest stage，并对三种 pressure 返回允许动作。
- `dayu/host/_runner_call_manifest.py`
  - candidate、projection descriptor graph、hot payload 与 manifest identity 共用唯一
    strict owner；
  - 所有新 Attempt producer 在 start transition 前提交 manifest；
  - CAS / state precondition 失败不留下孤立 start artifacts。
- `dayu/host/compact_payload.py`、`compaction_operation.py`、
  `context_fallback.py`、`memory.py`
  - strict compact source boundary 与 covered/current refs 同源；
  - 保留 reactive exact catch-up 与 manifest-before-recovery-start；
  - post-compact / fallback / reactive candidate 使用同一 sizing/action contract。

### 3.2 Exact input fact 与 continuity

- `dayu/host/run_input.py`
  - source Run exact input fact 由共享 strict helper 读取；
  - exact policy parser 同时服务 source loader 与 worker delegate；
  - delegate 后再次校验 caller/source run、attempt、execution identity；
  - startup replay 不读取 current baseline/tooling/config；
  - running / waiting steer 对同一 payload strict parse；
  - `SessionContinuityView.source_refs` 为必填，全部 production/test construction site
    显式提供；
  - ordinary continuity 使用 `()`；wait continuity 使用 request/result exact refs。

### 3.3 Admission、dispatch、wait 与 recovery

- `dayu/host/admission.py`
  - first call 与 queued admission 冻结 exact effective execution/tool facts；
  - idempotent replay 先判定既有结果，再读取新 admission baseline；
  - running / waiting steer 构造 exact candidate 并在 start 前提交 manifest；
  - admission 只发送 queue governance wakeup，不直接 promotion。
- `dayu/host/dispatch.py`
  - ordinary accepted / queued pickup 统一走 scheduler governance；
  - proactive、post-compact、fallback 与 startup replay 都保持
    candidate/action/manifest-before-start；
  - reactive recovery 保留 exact catch-up 与 pre-start manifest。
- `dayu/host/accepted_result_projection.py`、`waiting.py`
  - completed / cancelled wait 先通过 accepted-result projection 同一 strict core
    形成 planned typed continuity；
  - planned result event id 与 committed row exact 相等；
  - resume candidate 与 manifest 在 start 前完成；
  - failed / lost 直接终态，零 resume candidate、manifest、Attempt、dispatch。
- `dayu/host/recovery.py`
  - startup / attachment recovery 只从 durable source exact replay；
  - source 缺失或非法 fail closed 为既有 typed lost owner；
  - manifest-before-recovery-start，CAS 失败不遗留孤立 artifacts。
- `dayu/host/engine_ingest.py`
  - continuation 只使用 `CONTINUATION` stage；
  - 直接记录实际 continuation input 的 limited manifest；
  - 不调用 pre-start candidate recorder。
- `dayu/host/command.py`、`open_host.py`
  - `PayloadStore`、ordinary baseline、tooling、context policy、memory policy、
    truncation flag 与 owner host id 均逐项显式装配；
  - admin-only handle 明确传 `None`，运行路径不使用 fallback。

### 3.4 Direct promotion 删除

从 `admission.py`、`durable/state.py`、`durable/run_transition.py` 及 tests 删除：

- `promote_next_queued_run`
- `promote_queued_run_in_transaction`
- `PromoteQueuedRunInput`
- `PromotionSkipReason`
- `promote_queued_run_row`
- `_validate_promote_input`
- 对应 state mutation、private helpers、imports 与专属 fixture/tests

保留的 `promotion` 文本只属于 scheduler ordinary queue governance、post-commit wakeup
与其 lifecycle tests；admission、terminal closeout、cancel、recovery 都是 wake-only，
没有 durable direct promotion 调用。

## 4. Diff scope

实际修改 18 个 production Python 文件：

- candidate / manifest：
  `_runner_call_manifest.py`、`context_budget.py`、`compact_payload.py`、
  `compaction_operation.py`、`context_fallback.py`
- input / projection：
  `run_input.py`、`accepted_result_projection.py`、`memory.py`
- lifecycle producers：
  `admission.py`、`dispatch.py`、`waiting.py`、`recovery.py`、
  `engine_ingest.py`
- durable deletion / schema：
  `durable/state.py`、`durable/run_transition.py`、`durable/schema.py`
- composition：
  `command.py`、`open_host.py`

tests 覆盖 owner contract、十五格 matrix、ordinary/startup/steer/wait/recovery/
continuation producer、rollback、schema/import/static guards；新增
`tests/host/execution_handle_support.py` 作为显式语义输入的公共测试 support。

README 按触发规则更新：

- `dayu/host/README.md`：记录 exact production stage 术语、十五格 action、
  manifest-before-start、exact replay、wait continuity 与 queue wake-only 稳定边界；
- `tests/README.md`：增加当前 Slice 1 focused 验证入口；
- `dayu/engine/README.md`、`dayu/README.md`、根 `README.md`：production layering、
  Engine public contract与用户工作流均未改变，不更新；
- Service / CLI / Fins production 未修改。

## 5. Validation evidence

### 5.1 Tests

计划列出的 focused Slice 1 suite：

```text
986 passed in 12.74s
```

最后两处 strict owner 修改的定向回归：

```text
206 passed in 5.98s
35 passed in 0.49s
```

完整 Host gate：

```text
2173 passed, 2 skipped, 6 deselected in 51.71s
```

两个 skip 均为既有外部环境 gate：

- real compactor smoke 需要显式设置 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1`；
- Gemini real-runner smoke 因 provider quota / rate limit 明确 skip。

6 个 deselected 来自项目默认 marker 配置，不属于 Slice 1 failure。

最终 schema / import boundary / package export / weak typing / terminal static gate：

```text
164 passed in 3.50s
```

使用最终生产源码重建 coverage 的 full Host run：

```text
2173 passed, 2 skipped, 6 deselected in 72.74s
```

### 5.2 Per-file line coverage

| production file | line coverage |
| --- | ---: |
| `_runner_call_manifest.py` | 89% |
| `accepted_result_projection.py` | 95% |
| `admission.py` | 90% |
| `command.py` | 88% |
| `compact_payload.py` | 91% |
| `compaction_operation.py` | 94% |
| `context_budget.py` | 90% |
| `context_fallback.py` | 91% |
| `dispatch.py` | 88% |
| `durable/run_transition.py` | 92% |
| `durable/schema.py` | 97% |
| `durable/state.py` | 88% |
| `engine_ingest.py` | 89% |
| `memory.py` | 92% |
| `open_host.py` | 89% |
| `recovery.py` | 86% |
| `run_input.py` | 87% |
| `waiting.py` | 88% |

18 个 changed production 文件全部 `>=80%`；合计为 `90%`。

### 5.3 Type、diff 与 static audits

- `python -m pyright dayu/ tests/ utils/`：
  `0 errors, 0 warnings, 0 informations`
- `git diff --check`：通过
- direct-promotion 上述六个 legacy symbols：零引用
- `SessionContinuityView(` construction sites：全部显式 `source_refs`
- 私有测试 helper
  `tests.host.test_resolve_wait_command._create_execution_handle`：零 import
- `CONTEXT_BUDGET_EVALUATED`、`context_anchor`、
  `_estimate_usage_observation_input`：production/tests 零引用
- `USAGE_ANCHORED`：仅保留已冻结 enum contract，未接入算法、producer 或 consumer
- admission factory 全 construction sites：显式语义依赖并通过 strict pyright
- manifest/schema/import/package/weak-typing static tests：通过
- README stage 术语已与 production `ContextSizingStage` exact 对齐
- 当前 `HEAD` 仍为 accepted plan commit
  `ed43bcf271968a39b2692ed637cca8a8355feec0`；未创建新 commit

## 6. Residual risks

- optional real compactor smoke 未启用；这是既有显式 opt-in 外部 gate。
- Gemini real-runner smoke 本次受外部 quota 限制，未提供成功调用证据。
- 项目默认排除的 stress marker 未在本轮额外启用；Slice 1 owner、focused、full Host、
  type、coverage与静态门禁均已通过。

未发现 plan 外 production owner 需求或 full Host 新 blocker。当前实现可进入
implementation review；尚未由 Controller 接受。
