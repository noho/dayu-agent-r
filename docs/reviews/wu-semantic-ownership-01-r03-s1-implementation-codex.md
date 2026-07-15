# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Implementation Artifact

## 1. Gate 与结论

- Work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`。
- Slice：`R03-S1 — ordinary/awaiting shared request atom + durable replay identity`。
- Agent：AgentCodex。
- original accepted plan commit：`8c6ae966`。
- original implementation transition commit：`244bfdae`。
- accepted plan correction commit：`f5a28f9e`。
- corrected implementation continuation control transition：`6e11d916`。
- gate：implementation。
- 结论：**IMPLEMENTATION FIX COMPLETE / READY FOR CONTROLLER RE-VALIDATION**。
- commit：未创建；本 artifact 不授权进入 code review、accepted slice commit、S2 或 S3。
- 总控：未修改 `docs/host/issues-implementation-control.md`。

## 2. 第一性原理判断、root cause 与 owner

问题真实且严重性成立。durable replay identity 必须由一次 Host accept 产生的 exact canonical request fact 唯一承诺；旧实现却同时存在以下直接证据：

1. ordinary 与 awaiting 分别构造 `TOOL_CALL_REQUESTED`，storage、query 与 identity 映射可漂移；
2. awaiting writer 先对参数做 redaction，再把 redacted body digest 与原始 normalized digest 分开保存；
3. `TOOL_AWAITING` 又复制 arguments 与 digest，形成第二份 durable truth；
4. resolve 从 `wait_id` 推导 request event id，未使用显式 durable link；
5. accepted-result / resume 在 request material 缺失时返回 limited/fallback，掩盖 linkage corruption。
6. 初版 wait-resolution `TOOL_RESULT_ACCEPTED` writer 使用 request 侧 resume/空 identity，而该事实语义属于产生等待的 suspended source Attempt；同时 transition 未校验 WaitRecord execution 与 source Attempt execution 同源。

这些不是展示层问题。root cause 与数据同源：request atom 的产生、持久化链接和严格读取没有单一 owner。S1 的 owner 裁决落实为：

- `dayu/host/tool_call_request.py`：唯一 canonical request atom 构造 owner；只构造 append request，不 append、不预测 sequence；
- ordinary / awaiting accept caller：EventLog append owner；必须使用 `append_event(...).row` 返回的真实 row / sequence；
- `TOOL_AWAITING`：waiting governance owner；只保存治理字段和显式 request row link；
- `dayu/host/payload_resolution.py`：request atom storage/shape/digest strict reader owner；
- `dayu/host/accepted_result_projection.py`：accepted result 到 canonical request 的 shared strict projection owner；
- `dayu/host/run_input.py`：resume runner message owner；只消费 shared projection 提供的 exact arguments，不建立 fallback identity。
- `dayu/host/durable/run_transition.py`：wait resolution 状态机与 `TOOL_RESULT_ACCEPTED` identity writer owner；写前校验 WaitRecord/source Attempt execution 等值，并始终使用 suspended source Attempt 的 attempt/execution identity。

该方案是满足 S1 的最小 owner closure：没有引入兼容 shim、统一 authorization framework、LLM-safe normalization 或新 schema migration。

## 3. Controller test-only allowlist 裁决

Controller 在
`docs/reviews/wu-semantic-ownership-01-r03-s1-allowlist-controller-adjudication.md`
作出 `TEST-ONLY-ALLOWLIST-EXPANSION-ACCEPTED`：全 Host 初次回归的 21 个失败只位于四个 strict consumer propagation 测试文件，因此允许额外修改：

- `tests/host/test_compact_material.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`

裁决未扩张 production owner 或产品语义。本实现只把这些 fixture 迁移到 identity/digest 同源的 canonical request + accepted envelope，并把旧 skip/limited 断言改为 `HostDurableError` 与 no-publish 断言。Controller artifact 仅作为输入读取，AgentCodex 未修改该文件。

随后 correction 链完整经过 plan-correction Codex、Controller adjudication/validation、MiMo/DS reviews 与 final Controller adjudication；最终裁决接受 `f5a28f9e`，并由 control transition `6e11d916` 重新开放同一个 R03-S1 implementation continuation gate。纠正后的 §6 只新增 `dayu/host/durable/run_transition.py` 作为 production owner，并明确：

- write precondition 必须包含 `WaitRecord.execution_id == source Attempt.execution_id`；
- resume 与 terminal 共用的 result writer 必须使用 source Attempt attempt/execution，不能使用 resume identity、`None` 或新 authority；
- public completed/failed/lost tests 证明正常 producer identity；direct typed resume/terminal tests 证明 mismatch 返回 `INVALID_STATE` 且五表无 mutation；
- 已落地的 governance-only `TOOL_AWAITING`、descriptor 冷热互斥、strict result execution equality/no-publication contract 必须保留，不能因 correction 回退。

本轮只修改 corrected exact allowlist、两份触发 README 与既有 implementation artifact；所有 correction authority/review/control 文件保持只读且工作区 clean。

## 4. Old / new durable payload snapshot

### 4.1 旧形态

- ordinary 与 awaiting 各自拥有 request builder；awaiting 只支持本地 inline 参数，并生成 synthetic query。
- awaiting request body 保存 redacted replay arguments，而 `normalized_arguments_digest` 来自原始 accepted arguments。
- `TOOL_AWAITING` 重复保存：
  - `normalized_arguments_digest`
  - `accepted_arguments`
  - `accepted_arguments_source_digest`
- resolve 通过 `wait-<digest>` 前缀推导 `event-tool-call-requested-<digest>`。
- resume request material 不可用时生成 compatibility system guidance。

### 4.2 新 canonical `TOOL_CALL_REQUESTED`

ordinary 与 awaiting 共用一个 22-key request atom contract：

```text
session_id, run_id, attempt_id, execution_id, iteration_id,
tool_call_id, tool_name, tool_schema_digest, tool_identity_digest,
normalized_arguments_digest,
arguments_json_size_bytes, arguments_storage_kind,
arguments_inline_json, arguments_payload_ref, arguments_payload_digest,
tool_fact_kind, accept_idempotency_key, semantic_input_digest,
semantic_query_storage_kind, semantic_query_text,
semantic_query_payload_ref, semantic_query_digest
```

关键不变量：

- `accepted_arguments` 先形成 `{"arguments": <exact accepted mapping>}`；
- `arguments_payload_digest == normalized_arguments_digest`，writer 与 reader 都校验；
- small args inline，large args 统一写 `TOOL_CALL_ARGUMENTS_JSON` descriptor；
- ordinary 只保存 producer 显式 query；awaiting `semantic_query_text=None`，storage kind 为 `absent`，不发明 query；
- `tool_identity_digest` 原样来自 caller atom，不由 writer 重算；
- writer 不 append；ordinary/awaiting caller append 后使用数据库返回 row。

### 4.3 新 `TOOL_AWAITING`

exact key set：

```text
session_id, run_id, attempt_id, execution_id, iteration_id,
wait_id, tool_call_id, tool_name,
tool_call_requested_event_ref,
await_spec, adapter_key, resume_policy,
snapshot_ref, external_job_ref,
accept_idempotency_key, semantic_input_digest
```

`tool_call_requested_event_ref` 只能是同一 accept transaction 中已 append row 的
`{"event_id": ..., "event_sequence": ...}`。payload 不再含任何 accepted arguments、normalized digest 或 `arguments_*` 副本。

## 5. Sequencing、rollback 与 idempotency

awaiting accept 的固定顺序为：

1. shared writer 构造 canonical request append request；
2. append `TOOL_CALL_REQUESTED`，取得真实 row；
3. 用该 row 构造 exact request ref；
4. append `TOOL_AWAITING`；
5. append `RUN_WAITING` / `ATTEMPT_SUSPENDED`，写 wait record、状态与 idempotency；
6. 任一步失败由同一 write transaction 整体 rollback。

owner-level tests 覆盖 request append 后、`TOOL_AWAITING` 后、`RUN_WAITING`/后续 mutation 失败，均断言 EventLog、wait row、Run/Attempt state 和 idempotency 无部分提交。same-digest replay 返回 existing ack；same-body existing request row 使用既有真实 sequence；different digest/body conflict 不产生孤立 facts。

## 6. Strict read 与 corruption matrix

| Corruption | Owner behavior | No-partial-output assertion |
|---|---|---|
| request `arguments_payload_digest != normalized_arguments_digest` | `tool_call_request_atoms` 抛 `HostDurableError` | 不返回 canonical args |
| accepted envelope 缺失 | shared accepted-result projection 抛 `HostDurableError` | compact/trace 不发布结果 material |
| request link 缺失或 row 不存在 | shared projection / wait resolver 抛 `HostDurableError` | 无 resolution/resume facts；memory/trace 无输出 |
| request ref shape 或 sequence 错误 | waiting strict link reader 抛 `HostDurableError` | Run/Attempt/wait 不推进 |
| request event type / session / run / attempt / execution 错配 | strict identity check 抛 `HostDurableError` | memory snapshot、compact view、result trace 不发布 |
| tool call id / tool name / arguments digest / semantic input digest 与 envelope 漂移 | shared projection 抛 `HostDurableError` | 四 consumer 不降级为 limited/fallback |
| resume canonical arguments 缺失或 shape 非 object | RunInput 抛 `HostDurableError` | 不生成 compatibility system message |

Memory projection runner 会把 consumer 抛出的异常记录为 `last_error_code=HostDurableError`，snapshot、memory items 与 checkpoint 不越过损坏 result。Tool Trace 同样记录 projection failure，损坏 result 没有 hot row 或 cold JSONL line。Compact material 在 view build 前直接失败，不返回部分 evidence block。

## 7. 精确 diff

### 7.1 Production

- `dayu/host/tool_call_request.py`（新增）：typed atom input、origin、唯一 descriptor-capable writer 与私有 payload/ref/digest helpers。
- `dayu/host/tool_runtime.py`：ordinary accept 显式映射 shared atom，append 后使用真实 row；删除本地 writer/descriptor helper 闭集。
- `dayu/host/waiting.py`：awaiting 显式映射 shared atom；真实 row link；resolve 严格沿 `wait created event -> TOOL_AWAITING ref -> request row` 读取；删除 wait-id 推导与重复 digest proof。
- `dayu/host/_event_payload.py`：`TOOL_AWAITING` 删除 arguments/digest 副本，新增 exact request ref；删除 replay redaction helper。
- `dayu/host/payload_resolution.py`：strict normalized/payload digest equality、required semantic input digest、inner `arguments` object shape。
- `dayu/host/accepted_result_projection.py`：missing/broken/unreadable/mismatch request material 一律 `HostDurableError`；删除 request-unavailable limited branch；校验 semantic identity。
- `dayu/host/run_input.py`：resume 只取 shared projection exact args；删除 fallback message、optional old-ref helper与对应 system section。
- `dayu/host/durable/run_transition.py`：resume/terminal 写前校验 WaitRecord/source Attempt execution 等值；共用 result writer 接收已读且已校验的 `source_attempt: AttemptRow`，并把 `TOOL_RESULT_ACCEPTED` 归属 source attempt/execution。

### 7.2 Original S1 tests

- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_wait_awaiting_accept.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_accepted_result_projection.py`

覆盖 shared ordinary/awaiting payload、inline/descriptor/query、真实 sequence、rollback、idempotent existing-row stability、strict digest/identity/link 与 exact replay。`test_resolve_wait_command.py` 还覆盖 public completed/failed/lost 正常 source identity，以及 direct typed resume/terminal execution mismatch 的 `INVALID_STATE`/五表 no-mutation 矩阵。Controller finding `R03-S1-CV-F01` 的最小补测继续位于该文件：direct resume 缺失目标 Run、direct terminal 缺失 WaitRecord 时，共享 durable precondition 返回 `NOT_FOUND`，所有待写 event/result 字段为空且五张 owner 表完全不变。

### 7.3 Controller-expanded tests

- `tests/host/test_compact_material.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`

成功 fixture 全部创建 canonical request + accepted envelope；missing/wrong-link/identity/digest corruption 断言 `HostDurableError`，并验证不继续发布 snapshot、compact 或 result trace。

### 7.4 Docs

- `dayu/host/README.md`：命中 Host stable contract 职责，更新 shared writer、governance-only awaiting、strict consumer 与 exact resume。
- `tests/README.md`：命中已存在测试事实职责，更新 strict corruption/no-publish 与测试层覆盖说明。
- `docs/reviews/wu-semantic-ownership-01-r03-s1-implementation-codex.md`：本 implementation artifact。

未修改任何其它 production/test/doc 文件；未修改 Issue #177/#178、Engine、prompt/schema、总控或授权文件。

## 8. 验证命令与结果

### 8.1 Test matrices

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_wait_awaiting_accept.py \
  tests/host/test_resolve_wait_command.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_accepted_result_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_memory_projection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py
```

结果：`389 passed in 2.66s`。

```bash
pytest tests/host -k \
  'tool_call_requested or awaiting_accept or replay_arguments or request_atom' -q
```

结果：`50 passed, 1909 deselected in 0.94s`。

```bash
pytest -q tests/host
```

结果：`1952 passed, 2 skipped, 5 deselected in 71.62s`。

### 8.2 R03-S1-CV-F01 exact owner coverage

Controller accepted finding 指定的精确命令：

```bash
pytest \
  tests/host/test_resolve_wait_command.py \
  tests/host/test_run_attempt_transitions.py \
  --cov=dayu.host.durable.run_transition \
  --cov-report=term-missing -q
```

修复前基线为 `75 passed`、`1375 statements / 283 missing / 79%`。仅新增两个真实 durable precondition case 后，结果为 `77 passed in 1.20s`、`1375 statements / 281 missing / 80%`；新覆盖的是 `_invalid_waiting_resolution_precondition` 的 Run 缺失与 WaitRecord 缺失 `NOT_FOUND` 分支。测试使用现有真实 SQLite store、production `EventLogStore`、typed transition input 和五表快照，没有 mock seam、coverage-only assertion、production branch、pragma、阈值调整或 test-driven shim。

### 8.3 Per-production-file coverage

最终绿色命令：

```bash
pytest -q tests/host \
  -k 'not process_backed and not tool_runtime_outer_task_cancel_closes_process_capsule and not wires_process_capsule_interrupt_policy' \
  --cov=dayu.host.tool_call_request \
  --cov=dayu.host.tool_runtime \
  --cov=dayu.host.waiting \
  --cov=dayu.host._event_payload \
  --cov=dayu.host.payload_resolution \
  --cov=dayu.host.accepted_result_projection \
  --cov=dayu.host.run_input \
  --cov=dayu.host.durable.run_transition \
  --cov-report=term-missing
```

最终结果：`1936 passed, 2 skipped, 21 deselected in 64.38s`。

首轮同命令得到八个文件全部达标的相同 coverage 百分比，但一个无本轮 diff 的 dispatch scheduler close 时序用例在 coverage 插桩下失败（`1935 passed, 1 failed`）；该用例已在无插桩 full Host 中通过，原样重跑整条 coverage 命令后全绿，期间未修改 production 或该测试。该一次性观察未复现，不构成 R03-S1 产品语义 finding，但保留在 artifact 中供 Controller 独立复验。

| Production file | Coverage | Target | Result |
|---|---:|---:|---|
| `dayu/host/tool_call_request.py` | 95% | >=95% | pass |
| `dayu/host/tool_runtime.py` | 86% | >=80% | pass |
| `dayu/host/waiting.py` | 89% | >=80% | pass |
| `dayu/host/_event_payload.py` | 98% | >=80% | pass |
| `dayu/host/payload_resolution.py` | 96% | >=90% | pass |
| `dayu/host/accepted_result_projection.py` | 95% | >=90% | pass |
| `dayu/host/run_input.py` | 91% | >=80% | pass |
| `dayu/host/durable/run_transition.py` | 93% | >=80% | pass |

coverage 命令只在插桩运行中排除 21 个 macOS multiprocessing spawn/process-backed 相关用例；无 coverage 注入的完整 Host 回归包含这些用例并为全绿，因此该限制属于 coverage/spawn instrumentation 冲突，不是产品行为回归。

### 8.4 Type / lint / diff

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
python -m ruff check <corrected §6 allowlist 的 17 个修改/新增 Python 文件>
```

结果：`All checks passed!`。

```bash
git diff --check
```

结果：pass，无输出。

## 9. Source / propagation scans

### 9.1 S1 删除闭集

对 `waiting.py`/`tool_runtime.py` 的旧本地 writer/helper 定义，以及 `_event_payload.py`/`accepted_result_projection.py`/`run_input.py` 的旧 redaction/fallback helpers 执行 exact `rg`。结果全部零命中；没有 compatibility alias、旧 fallback 或 wait-id 推导残留。

shared writer usage scan 只显示 ordinary、awaiting 两个 caller；二者都执行 `append_event(...).row`。`TOOL_AWAITING` payload owner 只命中 `tool_call_requested_event_ref`；其它 `normalized_arguments_digest` 命中位于 result payload 或 idempotency canonicalization，不是 awaiting payload 副本。

### 9.2 Accepted-plan propagation scans

执行 accepted plan §13.5 三组 `rg`：

- opaque/source scan：
  - `accepted_result_projection.py: 9`
  - `run_input.py: 25`
  - `memory.py: 52`
  - `compact_material.py: 57`
  - `tool_trace.py: 7`
- internal ref/digest scan：
  - `accepted_result_projection.py: 40`
  - `evidence.py: 69`
  - `compact_material.py: 189`
  - `tool_trace.py: 217`
- legacy material 文案 scan：3 个现存命中：`dayu/host/evidence.py` 2 个，`tests/host/test_accepted_result_projection.py` 1 个。

人工裁决：这些命中属于 accepted plan 已明确分配给 R03-S2/S3 的 source/opaque/fallback inventory；S1 不得删除或重写。进一步执行 diff-only scan：

```bash
git diff -U0 -- \
  dayu/host/accepted_result_projection.py \
  dayu/host/run_input.py \
  dayu/host/memory.py \
  dayu/host/compact_material.py \
  dayu/host/tool_trace.py \
| rg -n '^[+-].*(OpaqueEvidenceRef|source_refs|locator_refs|ref_kind|ref_id|unsafe|blacklist|citation)'
```

结果：零命中，证明 S1 未实施 S2 blacklist/source audit 或 S3 opaque-ref propagation。

### 9.3 Correction follow-up closure 与 allowlist

| Controller follow-up | Closure evidence | Status |
|---|---|---|
| wait result writer 曾使用 resume/空 identity | `_waiting_tool_result_event_request(*, request, run, source_attempt)` 只写 `source_attempt.attempt_id/execution_id`，resume/terminal 两 caller 共用 | closed |
| WaitRecord/source Attempt execution 不同源未被 transition 拦截 | `_invalid_waiting_resolution_precondition` 写前比较二者；direct resume/terminal mismatch 均为 `INVALID_STATE` 且五表 snapshot 不变 | closed |
| public producer identity 未锁定 | completed、failed、lost 分别断言唯一 `TOOL_RESULT_ACCEPTED` 使用 seeded suspended source attempt/execution；resume execution 另有独立 identity | closed |
| governance-only `TOOL_AWAITING` fixture 可能回退 | exact key-set、真实 request row/ref、`accepted_arguments`/source digest/normalized digest/全部 `arguments_*` absence assertions 保留 | closed |
| descriptor 冷热正文可能双份共存 | arguments/query descriptor + inline copy 均由 owner guard 拒绝，对应 tests 保留并通过 | closed |
| strict result execution equality/no-publication 可能放宽 | `_request_row_matches_result` 保持 session/run/attempt/execution 全等；四 consumer corruption tests 保持 `HostDurableError`/no-publication | closed |
| `payload_resolution.py` corrected coverage 门槛不足 | malformed inline/descriptor atom owner matrix 补齐，最终该文件 96%（target >=90%） | closed |
| `R03-S1-CV-F01` 精确 transition owner suite 仅 79% | 新增缺失 Run / WaitRecord direct-transition `NOT_FOUND` + 五表 no-mutation contract；精确命令 `77 passed`，`run_transition.py` 80% | closed，待 Controller re-validation |

allowlist scan 将 `git status --porcelain` 排除本轮开始前已存在且保持只读的 control 与 Controller validation artifact 后，与 corrected §6 的 8 个 production、9 个 tests、2 个 README 路径及本 implementation artifact 做集合差，结果为空。`R03-S1-CV-F01` fix 本身只修改 `tests/host/test_resolve_wait_command.py` 与本 artifact；未修改 production、README、accepted plan、Controller validation/control、MiMo/DS artifacts，也没有进入 S2/S3、code review 或 aggregate。`git diff --check`、untracked writer whitespace check 与 S2/S3 diff-only scan 均无诊断；旧 local writer/fallback 定义精确 scan 零命中，shared writer usage 仍只有 ordinary/awaiting 两个 caller。

## 10. README 决定

- `dayu/host/README.md`：必须更新。shared writer、`TOOL_AWAITING` link-only schema、strict four-consumer contract、exact replay，以及 wait result 的 suspended source Attempt identity/write precondition 都是当前 Host package 已实现的稳定开发边界。
- `tests/README.md`：必须更新。九个 test files 的 canonical fixture、strict corruption/no-publish matrix，以及 public/direct wait-resolution identity tests 是当前测试层已存在事实。
- 根 README 与 `dayu/README.md`：不更新。本 slice 没有用户安装/CLI/workflow变化，也没有改变 `UI -> Service -> Host -> Engine` 分层关系。
- `R03-S1-CV-F01` fix：不新增或修改任何 README；新测试只锁定上述既有 durable owner contract，现有 R03-S1 README diff 保持只读。

## 11. Residual risks / uncovered areas

| Risk / uncovered area | Classification / owner |
|---|---|
| S2 source blacklist / LLM source owner audit 尚未实施 | covered by later approved slice `R03-S2`；本 slice 禁止越界 |
| S3 opaque ref internal-only propagation 与 legacy fallback material 删除尚未实施 | covered by later approved slice `R03-S3`；传播 scan 已记录 baseline |
| coverage 与 macOS spawn 插桩不兼容 | validation tooling limitation；完整无插桩 Host 回归已覆盖并通过 process-backed tests |
| fresh-schema 之外的旧 waiting facts / DB compatibility | explicit non-goal；accepted plan 禁止 migration、compatibility reader 或 shim |
| 外部 provider / aggregate real-run smoke | covered by later aggregate gate；S1 无 prompt/tool schema/provider contract diff |

没有未分类 residual risk，没有证据要求再次扩张 production/test allowlist。

## 12. R03-S1-CV-F01 closure

- Finding：`R03-S1-CV-F01`。
- 修复状态：**已修复，待 Controller re-validation**。
- 修改范围：仅 `tests/host/test_resolve_wait_command.py` 与本 implementation artifact。
- owner contract：共享 waiting-resolution durable precondition 对缺失 Run / WaitRecord 返回 `NOT_FOUND`，在任何 resolution/resume/terminal fact 或 state mutation 前停止；五张 durable 表无部分写入。
- 精确成功信号：指定两文件 coverage 命令从 `75 passed / 79%` 提升到 `77 passed / 80%`。
- 最终验证：corrected 9-file `389 passed`；关键字 `50 passed, 1909 deselected`；full Host `1952 passed, 2 skipped, 5 deselected`；full 8-file coverage `1936 passed, 2 skipped, 21 deselected` 且每文件达标；full pyright 零错误；ruff、diff、allowlist 与 source scans 通过。
- 保留契约：resume/terminal execution mismatch `INVALID_STATE` + 五表 no-mutation、public completed/failed/lost source identity、governance-only `TOOL_AWAITING`、descriptor 冷热互斥、strict result identity/no-publication 均由原矩阵继续通过。

## 13. Handoff

R03-S1 implementation continuation 已按 `f5a28f9e` / `6e11d916` 的 corrected boundary 完成，`R03-S1-CV-F01` 已按 accepted finding 闭合。当前工作区保持未提交状态；下一入口仅为 Controller re-validation。本 Agent 停止于 implementation fix handoff，不创建 commit、不修改总控、不进入 code review、S2/S3 或 aggregate。
