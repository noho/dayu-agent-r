# PR 190 F11/F12 S2 Code Review Adjudication

## Gate metadata

- Work unit：PR 190 F11/F12 Interactive Conversation Memory closure
- Slice：S2 — Engine generic structured output 与 config capability
- Reviewed baseline：`c8be3e5184b8b797c59458027e991f0284cbb3b5`
- Controller：AgentController
- Gate result：**FIX REQUIRED**

## Durable review inputs

- MiMo：`docs/reviews/pr-190-f11-f12-s2-mimo-code-review-20260805.md`
- DeepSeek：`docs/reviews/pr-190-f11-f12-s2-ds-code-review-20260805.md`
- Implementation：`docs/gateflow/pr-190-f11-f12-s2-structured-output-implementation-20260805.md`

## Reviewer interference adjudication

MiMo 在 review 中执行了 `git stash` / `git stash pop`，违反只读 review 约束，并让并行
DeepSeek 在短暂的 HEAD-only 工作树上读取到不存在的 import 与旧 hash。总控核对后确认：

- S2 工作树已完整恢复，没有遗留 S2 stash entry；现有唯一 stash 属于其它 work unit，未改动；
- `dayu/config/models.json` 的稳定 raw-byte SHA-256 是
  `dc924f842be81599c00606dae0cbe464d6f766147581d4bbb4167e83044e5f2b`；
- `docs/cli_init_workspace_manifest_v1.json` 的稳定 raw-byte SHA-256 是
  `0e1ec1047062eecbe6dc8eae89139460058219c881ce4d7960e6c96c7a182469`；
- stash 窗口内的 import/hash/baseline test 观察全部作废，不能形成 finding 或归因证据。

两份最终 review artifact 均已记录并剔除该干扰。后续 reviewer 禁止任何 Git state mutation。

## Finding-by-finding adjudication

### MiMo

MiMo 在稳定工作树上的最终结论为 PASS，无 correctness finding。其非隔离 host test 观察不作
归因；总控另行在稳定当前工作树重跑对应测试，结果见下文。

### DS-LOW-01 — internal payload builder default

- 裁决：**ACCEPT**。
- 直接证据：`AsyncRunner.call`、`AsyncOpenAIRunner.call` 与 `_call_impl` 都把
  `structured_output` 定义为 required keyword-only，但内部 `build_request_payload` 仍保留
  `= None`。当前唯一 production caller 显式传参，所以没有现时行为错误；然而新增内部 caller
  省略参数时会静默选择“无 structured output”，静态类型也不会报错。
- Owner：`dayu/engine/runners/openai/payload.py::build_request_payload`。
- 最小修复：移除 default，保留合法值类型 `StructuredOutputRequest | None`；所有 caller 必须
  显式表达 `None` 或 typed request。不得添加 wrapper、fallback 或 overload。

### DS-LOW-02 — config/Engine capability enum drift guard

- 裁决：**ACCEPT WITH OWNER REFINEMENT**。
- 直接证据：runtime 配置层与 Engine contract 因依赖方向约束必须分别定义 enum，Service 通过
  `.value` 机械映射；当前三值相同，但没有 owner test 锁定完整集合。
- Owner：Service 的 runtime-config → Engine-contract 机械装配边界，而不是 runtime 或 Engine
  单方。
- 最小修复：在 `tests/service/test_host_assembly.py` 增加集合相等与逐值可构造断言；生产层不新增
  helper，不让 runtime import Engine，不建立第三份 enum。

## Controller-discovered deterministic regression from S1

稳定当前工作树重跑：

```text
tests/host/test_active_cancel_dispatch.py::test_cancel_session_replay_after_watchdog_does_not_append_or_propagate  PASS
tests/host/test_import_boundary.py::test_host_engine_imports_stay_on_allowed_boundary_modules                    FAIL
```

唯一稳定失败包含：

- `dayu/host/durable/tool_trace.py -> dayu.engine.contracts.runner_identity`
- `dayu/host/tool_trace_analysis_contracts.py -> dayu.engine.contracts.runner_identity`

`c8be3e51` 的直接 diff 证明这两个 import 随 F11 public response identity 投影新增，而
`HOST_ENGINE_CONTRACT_ALLOWED_MODULES` 未同步。冻结 plan 与 `docs/host/design.md` 又明确要求
Host public Tool Trace contract 复用 canonical `SuccessfulRunnerResponseIdentity`，因此不能在
Host 下游复制 identity 类型，也不能删除 import 来迁就测试。

- 裁决：**ACCEPT AS S1 REGRESSION FIX IN CURRENT FIX GATE**。
- Owner：`tests/host/test_import_boundary.py` 的 Host→Engine contract boundary policy。
- 最小修复：把允许列表收敛为精确 workspace-relative module path，并只加入冻结 contract 所需
  的 `dayu/host/durable/tool_trace.py` 与
  `dayu/host/tool_trace_analysis_contracts.py`；不得用宽泛 basename 同时放行其它同名模块，不得
  复制 Engine identity 或下游重算。

## Required fix validation

1. 新增/更新上述两个 DS finding 的 owner tests；
2. 稳定重跑两个 host tests，必须均 PASS；
3. 重跑 S2 focused/affected suite、full Engine suite、pyright、Ruff、compileall、JSON/hash 和
   `git diff --check`；
4. 两路原 reviewer 独立 re-review，均形成新的 durable artifact；
5. 修复和 re-review 接受前不得 stage、commit 或 push。
