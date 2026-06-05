# WU-DUR-P01-S2-R2 runner-call event link plan re-review

## Review metadata

| field | value |
|---|---|
| reviewed target | `docs/host/wu-dur-p01-s2-r2-runner-call-event-link-plan.md` (revised) |
| review scope | 仅复核上一轮 ds + mimo 阻断项和非阻断建议的关闭情况；不扩大到无关 scope |
| review date | 2026-06-05 |
| reviewer | planreview (adversarial re-review) |
| prior artifacts | `docs/reviews/wu-dur-p01-s2-r2-plan-review-ds.md` (findings F1-F8 + OQ1-OQ3); `docs/reviews/wu-dur-p01-s2-r2-plan-review-mimo.md` (findings 01-06 + OQ1-OQ3) |
| output path | `docs/reviews/wu-dur-p01-s2-r2-plan-rereview-ds.md` |

## 阻断项关闭复核

### ds-F1（高）: `_has_prior_iteration_observation` durable query 契约 → **已关闭**

revised plan §5 "Link resolution contract" lines 152-158 追加了完整的 durable query scope：

- scope: 当前 `run_id` + `attempt_id` + `execution_id`
- signal: committed `RUNNER_CALL_INPUT_ITERATION_LINKED` canonical event **或** committed accepted `ITERATION_STARTED` preview event
- 排除: `RUNNER_CALL_INPUT_ASSEMBLED` 计数、`ENGINE_EVENT_REJECTED`、compactor proposal execution、跨 Attempt、跨 execution
- transaction 语义: 若 link event 与 preview 同事务未提交，只能看到本 transaction 已 append rows

Slice 1 line 243 也明确：`_has_prior_iteration_observation(...)` 必须只看当前 `run_id` + `attempt_id` + `execution_id` 下 accepted link 或 accepted preview。stop condition line 359 覆盖了错误信号风险。

**证据**: plan lines 152-158, line 243, stop condition line 359。代码事实：`dayu/host/engine_ingest.py:2348-2363` 当前无 prior-observation guard，plan 新增的 scope 足够精确。

### ds-F2（中）: "ordinary dispatch kind" 未给闭集 → **已关闭**

revised plan §5 line 143 显式列出闭集：

```text
runner_call_kind 属于闭集 initial_user_dispatch / followup_user_dispatch / post_compaction_dispatch
```

同时增加了 `compactor_identity is None` 作为防御性过滤条件，排除 `tool_result_continuation` 与 `compactor_proposal`。

Slice 2 line 281-282 测试覆盖：followup ordinary manifest 与 post-compaction ordinary manifest 均能被 link；compactor proposal manifest 不会被选中。

**证据**: plan line 143。代码事实：`dayu/host/run_input.py:221-223` 三个常量值与 plan 闭集一致；`dayu/host/run_input.py:3781` 所有 ordinary manifest `iteration_id=None`。闭集正确覆盖了 `_runner_call_kind_and_trigger` 返回的所有 ordinary dispatch kind。

### ds-F3（中）: timing/ordering 约束缺失 → **已关闭**

revised plan 新增 §4 "Durable ordering guarantee" (lines 126-132)：

- ordinary prepared manifest 必须在 Engine worker 可产生 `ITERATION_STARTED` **之前** durable committed
- Slice 0 必须检查并记录该 guarantee
- 若核对发现无 durable ordering guarantee，不得用 sleep/retry/grace window/limited-signal 掩盖，必须回 design gate

stop condition line 356：`发现 ordinary prepared manifest write 与 Attempt dispatch / worker start / ITERATION_STARTED ingest 之间没有 durable commit-before-start ordering guarantee` 必须停止。

**证据**: plan §4, stop condition line 356。该约束将 ordering guarantee 从隐含假设升级为显式设计检查项。

### mimo-F01（高）: `ENGINE_EVENT_REJECTED` 未进入设计真源 → **已关闭**

revised plan 新增 §3 "ENGINE_EVENT_REJECTED 与 reason 契约" (lines 106-124)：

- 承认这是 pre-existing gap：代码已使用 (`dayu/host/engine_ingest.py:213` `_EVENT_TYPE_ENGINE_EVENT_REJECTED`) 但设计真源 `docs/host/design.md` event type list 未登记
- 定义完整 contract：scope (`session_id`, `host_run_id`, `attempt_id`, `execution_id`, `worker_event_index`, `engine_event_type`)、payload (`reason`, `stop_worker_stream`, 可选 `diagnostic_refs`)、无 Run/Attempt 状态副作用、audit/Tool Trace 消费边界
- Slice 0 line 207 明确要求在 event type 表和 event contract matrix 中补录
- Slice 0 验收 line 224 要求 `ENGINE_EVENT_REJECTED` 可 grep 到

**证据**: plan §3, Slice 0 line 207, 验收 line 224。代码事实：`dayu/host/engine_ingest.py:213` 已定义常量，plan 只要求设计文档补齐。

### mimo-F02（高）: 新增 diagnostic reason 未写入设计真源闭集 → **已关闭**

revised plan §3 lines 117-124 完整定义了新增 reason 的语义和归属：

- **Engine ingest rejected reason 闭集**（用于 `ENGINE_EVENT_REJECTED.reason`）:
  - `missing_runner_call_manifest`：首次 ITERATION_STARTED 找不到 unlinked prepared manifest
  - `ambiguous_runner_call_manifest`：多条 unlinked prepared manifest 无法唯一确定
  - `runner_call_iteration_link_conflict`：同 iteration 已有 link 但 identity 冲突
  - `runner_call_manifest_mismatch`：唯一 manifest 存在但 message_count/role_digest mismatch 的 fail-closed 控制原因

- **Runner-call reconstruction diagnostic reason 闭集**（用于 `RUNNER_CALL_INPUT_ITERATION_LINKED.diagnostic.reason`）:
  - `message_count_mismatch`
  - `role_sequence_digest_mismatch`

- 明确禁止混用：line 124 "`ambiguous_runner_call_manifest` 与 `runner_call_iteration_link_conflict` 不得写入 `RUNNER_CALL_INPUT_ITERATION_LINKED.diagnostic.reason`"
- Slice 0 lines 208-209 要求分别补录两个闭集

**证据**: plan §3, Slice 0 lines 208-209, stop condition line 364。

## 非阻断建议关闭复核

### ds-F4（中）: anti-join 查询策略 → **已关闭**

revised plan §5 line 145 给出明确查询策略：

- 同 Host transaction 内用 `NOT EXISTS` 子查询
- `manifest_event_id` 从 hot payload JSON 读取，优先 SQLite JSON1 `json_extract(payload_json, '$.manifest_event_id')`
- 查询同时按 `run_id`、`attempt_id`、`execution_id` 和 event type 收窄
- 禁止只用全 Run `RUNNER_CALL_INPUT_ASSEMBLED` 计数、禁止 Python 端差集
- stop condition line 358：若无法支持该策略，停止

**证据**: plan line 145, stop condition line 358。查询策略已足够具体，implementation agent 可据此写 SQL。

### ds-F5（低）: diagnostic reason 枚举归属 → **已关闭**

由 §3 覆盖（见 mimo-F02 复核）。两类 reason 的枚举归属已明确分离。

### ds-F6（低）: 测试夹具 seeding 路径 → **已关闭**

revised plan Slice 2 lines 277-278 给出 seeding 策略：

- 通过生产 helper / ingest 路径创建 ordinary manifest 与 accepted link（推荐）
- 或使用 dedicated test helper 追加 typed `RUNNER_CALL_INPUT_ITERATION_LINKED`（备选）
- 不得用 raw SQL 绕过 payload shape
- line 279 明确更新现有 continuation 测试：seed prior iteration observation before `iteration_index=1`

**证据**: plan lines 277-279。

### ds-F7（低）: preview resolution result 传递 → **已关闭**

revised plan §6 "Preview payload correlation" lines 173-178 给出完整机制：

- 增加 typed result dataclass `_RunnerCallIterationResolution`
- `_append_iteration_started_events` 先完成 resolution，再传递给 preview payload builder
- `_preview_payload` 可新增可选参数或拆出 `_iteration_started_preview_payload(transaction, context, data, resolution)`
- 禁止 preview builder 内再次调用 `_find_runner_call_manifest_event` 或 `_runner_call_manifest_matches_iteration`
- Slice 1 line 241 增加了 `_iteration_started_preview_payload` helper

**证据**: plan §6, Slice 1 line 241。传递机制足够具体。

### ds-F8（低）: link+preview/rejected 同事务约束 → **已关闭**

revised plan §5 line 160 明确：

> `RUNNER_CALL_INPUT_ITERATION_LINKED` 与对应 accepted `ITERATION_STARTED` preview 必须在同一个 Host write transaction 中 append。`RUNNER_CALL_INPUT_ITERATION_LINKED mismatch` 与对应 `ENGINE_EVENT_REJECTED` 也必须在同一个 Host write transaction 中 append。若实现无法保持同事务原子性，必须停止并回到 design gate。

stop condition line 360 覆盖同事务要求。Slice 1 验收 lines 258-259 验证同事务提交或回滚。

**证据**: plan line 160, stop condition line 360, Slice 1 验收 lines 258-259。

### mimo-F03（中）: `_has_prior_iteration_observation` 范围 → **已关闭**

由 ds-F1 覆盖。

### mimo-F04（中）: 现有 continuation 测试 fixture 更新 → **已关闭**

revised plan Slice 2 line 279 明确要求更新现有测试：
> 更新现有 `test_iteration_started_writes_limited_runner_call_manifest_for_continuation`：在发送 `iteration_index=1` continuation 前 seed 当前 attempt/execution 下的 prior accepted iteration observation，否则新逻辑会正确 reject 为 missing initial manifest。

**证据**: plan line 279。

### mimo-F05（低）: dead code 清理 → **已关闭**

revised plan Slice 1 line 233：
> 删除 `_runner_call_manifest_matches_iteration`，并删除或重写其唯一调用方 `_find_runner_call_manifest_event`。新逻辑不得留下仍按 `iteration_index == 0` 匹配 prepared manifest 的 dead code。

验收 line 260 要求 grep 确认旧 fallback 不再命中。测试命令 lines 317-318 要求静态检查验证。

**证据**: plan lines 233, 260, 317-318。

### mimo-F06（低）: `validation_status` mismatch 语义过载 → **已关闭**

revised plan §2 lines 96-97：
> `mismatch`：找到唯一 prepared manifest，但 `message_count` 或 `role_sequence_digest` 与 Engine observation 不一致。**该 status 不表达 link identity conflict。**

link identity conflict 已从 `mismatch` 语义中移除，改为通过 `ENGINE_EVENT_REJECTED` + reason `runner_call_iteration_link_conflict` 表达（§3 line 121）。

**证据**: plan lines 96-97, line 121。

## 用户指定重点检查项复核

| 检查项 | plan 位置 | 状态 |
|---|---|---|
| ENGINE_EVENT_REJECTED design sync/event matrix | §3 lines 106-115; Slice 0 line 207; 验收 line 224 | **已覆盖** |
| rejected reason 与 runner-call diagnostic reason 枚举归属和语义 | §3 lines 117-124; Slice 0 lines 208-209; stop condition line 364 | **已覆盖** |
| `_has_prior_iteration_observation` durable query scope | §5 lines 152-158; Slice 1 line 243; stop condition line 359 | **已覆盖** |
| ordinary dispatch kind 闭集 | §5 line 143 (explicit enum); Slice 2 lines 281-282 (test coverage) | **已覆盖** |
| manifest commit-before-start ordering stop condition | §4 lines 126-132; stop condition line 356 | **已覆盖** |
| anti-join 查询策略 | §5 line 145; stop condition line 358 | **已覆盖** |
| preview resolution result 传递 | §6 lines 173-178; Slice 1 line 241 | **已覆盖** |
| link+preview/rejected 同事务 | §5 line 160; stop condition line 360; Slice 1 验收 lines 258-259 | **已覆盖** |
| 旧 fallback/dead code 清理验收 | Slice 1 line 233; 验收 line 260; 验证命令 lines 317-318 | **已覆盖** |
| Tool Trace 最小实现语义 | §7 lines 184-190; 非目标 line 22; Slice 3 line 297 | **已覆盖** |

## 次要观察（非阻断）

### O1-低-`compactor_identity is None` 过滤条件可能需读 manifest body

revised plan §5 line 143 在 unlinked manifest 搜索条件中包含 `compactor_identity is None`。但 `compactor_identity` 在 manifest body 中（`dayu/host/run_input.py:3800`），不在 EventLog hot payload 中（hot payload 只有 `runner_call_kind` 等字段）。anti-join 查询（line 145）在 SQLite 层只能访问 hot payload JSON，无法直接过滤 `compactor_identity`。implementation agent 需要在 Python 层读取 manifest body 做二次过滤，或依赖 `runner_call_kind` 闭集（已排除 `compactor_proposal`）跳过此检查。

**建议**: implementation agent 可将 `compactor_identity is None` 作为 Python 层 defense-in-depth assertion，不阻塞 anti-join SQL。不影响 plan 整体正确性。

### O2-低-`_has_prior_iteration_observation` 为模块级 helper，直接单测困难

plan Slice 2 line 283 要求测试 "prior observation helper 不把 `RUNNER_CALL_INPUT_ASSEMBLED` 计数或 `ENGINE_EVENT_REJECTED` 当作 prior iteration"。由于 `_has_prior_iteration_observation` 是模块级私有函数（非 public API），直接单测需要暴露或通过 ingest path 间接测试。plan 的测试策略（通过 ingest 路径间接验证）是合理的，但 implementation agent 需要确保 seed 的 `RUNNER_CALL_INPUT_ASSEMBLED` 事件（无 link + 无 preview）不会触发 prior observation 误判。

## Open questions（上一轮遗留）

| OQ | 原始内容 | 修订 plan 处理 | 状态 |
|---|---|---|---|
| OQ1 (ds) | preview validation summary 与 link refs 关系 | §6 line 178: 两者来自同一 resolution result；preview 顶层增加 `runner_call_iteration_link_event_id` 等新字段 | **已关闭** |
| OQ2 (ds) | Engine 双重 `iteration_index=0` | 风险 §8 line 348: 明确归为 Engine contract anomaly，按 continuation limited-signal 记录 | **已关闭** |
| OQ3 (ds) | ENGINE_EVENT_REJECTED 后状态迁移 | Slice 0 line 214: rejected 后状态机与现有 unsupported Engine event rejected 路径一致，不改变 Run/Attempt 状态 | **已关闭** |
| OQ1 (mimo) | link event 是否需要进入 Tool Trace | 非目标 line 22 + §7 line 189: 最低实现不强制投影；README 明确两种 complete 区别 | **已关闭** |
| OQ2 (mimo) | `stop_worker_stream` 是否需在 event payload 显式记录 | §3 line 113: event payload 必须记录同名布尔值 | **已关闭** |
| OQ3 (mimo) | `manifest_schema_version` 语义 | 未显式处理，但 link event payload 中 `manifest_schema_version` 是 manifest body 的 schema version，从 matched manifest 复制的诊断字段 | **非阻断** |

## Residual risks（更新）

| risk | tracking | status |
|---|---|---|
| `compactor_identity is None` 过滤需读 manifest body | implementation 时由 agent 决定 Python 层二次过滤或依赖 kind 闭集 | 低，不影响 plan |
| anti-join 在大 Run EventLog 下的性能 | stop condition line 358 + scope 固定到 attempt/execution | 已缓解 |
| Engine 双重 `iteration_index=0` | plan line 348 明确处理策略 | 已缓解 |
| Tool Trace consumer 未升级 | plan 最小实现不强制 | deferred |

## Final conclusion: **accept**

上一轮 ds review 的 3 个阻断项（F1/F2/F3）和 mimo review 的 2 个高严重度 finding（01/02）均已在修订 plan 中关闭。全部 8 个非阻断建议和 6 个 open question 也已处理或明确裁决。用户指定的 10 个重点检查项均有覆盖。修订后的 plan 在 contract 完整性、durable query 规格、ordering guarantee、枚举归属分离、dead code 清理验收、事务原子性约束和测试夹具 seeding 方面均达到 code-generation-ready 水平。

两个次要观察（O1/O2）为 implementation-level 细节，不阻塞进入 implementation gate。
