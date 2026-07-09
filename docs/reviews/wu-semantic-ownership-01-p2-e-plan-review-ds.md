# WU-SEMANTIC-OWNERSHIP-01 / P2-E Plan Review — AgentDS

## 结论

**pass-with-findings**

7 个失败均属于测试/fixture 对齐问题，无需 production 修复。plan 的 owner boundary 分析正确，slice 分组合理，stop conditions 充分。以下 findings 不改变 pass 结论，但必须在 implementation 前解决或显式确认。

---

## Finding 1 — wait-resume integration assertion 变更可能掩盖 fixture 缺陷 (MEDIUM)

**直接证据：**

- 生产代码 `_resume_wait_messages_from_current_start`（`dayu/host/run_input.py:986-1036`）有两条路径：
  - 正常路径：`accepted_arguments is not None` → `UserMessage → AssistantMessage(tool_call) → ToolMessage`（协议闭环重建）
  - Fallback 路径：`accepted_arguments is None` → `_resume_wait_fallback_message()` → 中文自解释 `SystemMessage`
- Fallback 路径的触发条件是 `_resume_wait_accepted_arguments` 返回 `None`，即缺少 `TOOL_CALL_REQUESTED` request atom 或 accepted evidence envelope
- 当前测试（`test_phase7_waiting_integration.py:343-350`）断言旧英文 fallback 文本 `"A previous interrupted step has an accepted wait result."`、`tool_name=...`、`resolution_kind=completed`
- 该测试 fixture（`_seed_active_integration_run`）是否创建了 `TOOL_CALL_REQUESTED` request atom 和 accepted evidence envelope **尚未在本 plan 中验证**

**风险：**

如果 fixture 实际上没有创建 request atom（即它是为旧 fallback 路径设计的），那么：
1. `_resume_wait_accepted_arguments` 返回 `None`
2. 生产代码走 fallback 中文 guidance 路径
3. 当前测试断言旧英文 fallback → **旧断言碰巧通过，但不是因为生产行为正确，而是因为旧 fallback 与旧 assertion 同时 stale**
4. 如果按 plan 把 assertion 改为协议闭环（User/Assistant/Tool messages），测试会**失败**——不是因为生产代码有 bug，而是因为 fixture 没有为正常路径准备必要数据

这种情况下，正确的修复不是"改测试"，而是"先修 fixture 再改 assertion"。

**Owner boundary：**

- Request atom 事实产生：Host ToolRuntime `DefaultHostToolAwaitingAcceptPort`（`dayu/host/tool_runtime/awaiting_accept.py`）
- Resume projection 消费者：`dayu/host/run_input.py::_resume_wait_messages_from_current_start`
- 测试 fixture 所有者：`tests/host/test_phase7_waiting_integration.py::_seed_active_integration_run`

**最小修复要求：**

在 implementation 开始时，**必须先做 fixture 诊断**，确认 `_build_resume_request` 实际产出的 `resume_request.messages` 内容：

1. 如果 messages 包含 `UserMessage + AssistantMessage(tool_calls=[...]) + ToolMessage(tool_call_id=...)`：直接改 assertion 为协议闭环检查，confirm 无 fixture 缺陷
2. 如果 messages 只包含 `SystemMessage`（中文 fallback）：**必须先修 fixture**，注入正确的 `TOOL_CALL_REQUESTED` request atom 和 accepted evidence envelope，再改 assertion
3. 如果 messages 仍是旧英文 fallback：production regression，owner 转为 `dayu/host/run_input.py`，停止 alignment 并升级为 production fix

Plan 中 Slice E2 的 stop condition（"若 `resume_request.messages` 实际不是协议闭环，则停止"）已覆盖此风险，但**未显式要求 implementation 第一步做 fixture 诊断**。建议在 implementation closeout 中显式记录 fixture 诊断结果。

---

## Finding 2 — purge cancelling fixture 修复应优先创建完整 cancel lifecycle EventLog row（LOW）

**直接证据：**

- 生产 schema CHECK（`dayu/host/durable/schema.py:537-539`）：
  ```sql
  CHECK(status NOT IN ('cancelling', 'cancelled') OR cancel_request_event_id IS NOT NULL)
  ```
- 测试 fixture `_insert_run_row`（`test_purge_session.py:1535-1569`）不接受 `cancel_request_event_id` 参数
- 当 `run_status='cancelling'` 时，`_SeedClosedSessionMatrixOperation.__call__` 走 shortcut 路径（line 779-791），只插入 Run row 且不写 `cancel_request_event_id`

**Plan 的 proposed fix：** "为 `cancelling` Run 写入或引用一个语义明确的 cancel request EventLog row，并把 `cancel_request_event_id` 插入 Run row"

**评审：** fix 方向正确。但需注意两个细节：

1. `_SeedClosedSessionMatrixOperation` 在 `run_status != _RUN_STATUS_SUCCEEDED` 时走简化路径（不写 attempt/dispatch/wait/read-model 等 rows）。这个简化路径**本意是测试 purge 对不同状态的拒绝行为**，不是模拟完整 cancel lifecycle。因此 fix 只需提供 schema 所需的最小合法字段（一个 cancel request event id），不需要补齐完整的 cancel lifecycle rows。
2. Plan 的 mitigation（"添加显式 cancel request EventLog row"）优于"复用任意 terminal event"方案。但 fixture 应该**用专用 event id**（如 `"event-cancel-request"`），避免与 `_insert_target_events` 的已有 event ids 冲突。

**建议：** 扩展 `_insert_target_events` 或 `_SeedClosedSessionMatrixOperation`，为非 terminal status 添加一个 `cancel_request_event` tuple `(event_id, event_sequence)`，并传给 `_insert_run_row`。`cancel_request_event_id` 应该是一个新 event id，不要在 fixture 中引用已有 events。

---

## Finding 3 — Slice E2 的 heterogeneous 风险在 plan 中未充分讨论（LOW）

**事实：** Slice E2 包含三个语义独立的变更：
- Host/API export snapshots（failure 4+5）
- wait-resume integration assertion（failure 6）
- purge fixture（failure 7）

**Plan 的理由：** "Host export、wait-resume integration、purge fixture 都属于 Host 测试对已接受 public/durable/LLM-facing contract 的 alignment"

**评审：** 虽然三者都是 Host 测试对齐，但 failure 6 的 stop condition 可能触发 production fix 场景，而 failure 4/5/7 不可能触发。如果 failure 6 触发 stop condition：
- 整个 Slice E2 需要停止或拆分为 E2a（exports + purge fixture）和 E2b（wait-resume）
- Plan 当前的 "Stop condition" 只是说停止，未说如何回退已完成的 E2 其他修复

**建议：** 在 implementation 开始前，先做 fixture 诊断（见 Finding 1）。如果 fixture 诊断确认 failure 6 是纯测试对齐，三者在同一 slice 内安全。如果 fixture 诊断发现需要 production fix，则应先完成 exports + purge fixture alignment（E2a），再单独处理 wait-resume（E2b）。这不改变 plan 的 slice 结构，但应在 implementation closeout 中显式记录此决策。

---

## Finding 4 — propagation audit 缺少 export snapshot alignment 的显式记录（INFO）

**事实：** Plan 的 "Propagation Audit Expectations" 只覆盖了 wait-resume LLM-facing semantics。对于 Engine/Host public export snapshot alignment（failures 3/4/5），plan 只说 "更新 EXPECTED_EXPORTS"。

**评审：** 这些 snapshot alignment 的 propagation 检查虽然简单（生产代码没变，只改测试），但仍应在 implementation closeout 中显式列出：
- Engine `__all__` 新增两类型 → 确认 `dayu.engine` 包根 docstring / `dayu/engine/README.md` 已覆盖这两个类型的公共导出说明（design doc line 58 已覆盖，不需要额外变更）
- Host `__all__` 新增 `HostThinkingView` → 确认 `dayu/host/README.md` 已将其列为公共 typed event view（line 239 已覆盖，不需要额外变更）

**这不是 blocker**，但 plan 的 "README / Doc Trigger Analysis" 部分已隐含覆盖了此检查。Implementation closeout 只需显式确认即可。

---

## 逐条 review 焦点回应

### 1. 7 个失败是否都可按测试/fixture alignment 处理；是否有任何一个必须先修 production

**结论：** 全部 7 个失败均可按测试/fixture alignment 处理，**当前不需要 production fix**。

| Failure | 生产行为意图 | 测试滞后根因 | 直接证据 |
|---|---|---|---|
| 1. stream heartbeat | 心跳日志级别为 `STREAM_DEBUG_LOG_LEVEL`（低于 DEBUG） | 测试用 `logging.DEBUG` 捕获 | `runner.py:968-969`, `log_levels.py:16` |
| 2. iteration_started | `input_projection` 已是 accepted public contract | 测试快照缺少此字段 | `engine_events.py:112`, `engine/design.md:472` |
| 3. engine `__all__` | 两个 projection 类型已是包根公共导出 | EXPECTED_EXPORTS 未更新 | `engine/__init__.py:80-81,169-170`, `engine/design.md:58` |
| 4. host `__all__` | `HostThinkingView` 已是 public typed event view | EXPECTED_HOST_EXPORTS 未更新 | `host/__init__.py:200`, `host/README.md:239` |
| 5. host.api `__all__` | 同上 | EXPECTED_API_EXPORTS 未更新 | `host/api.py:3565` |
| 6. wait-resume guidance | 生产代码优先走协议闭环重建 | 测试断言旧英文 fallback | `run_input.py:986-1036` |
| 7. purge cancelling | 生产 schema 正确拒绝非法 durable Run | fixture 直接插入非法数据 | `schema.py:537-539`, `test_purge_session.py:1535` |

**例外注意：** Failure 6 的 fixture 可能在旧 assertion 下碰巧通过（旧英文 fallback 文本与旧 assertion 匹配），但实际生产路径可能因 fixture 缺少 request atom 而走了不当路径。详见 Finding 1。

### 2. Slice E1/E2 grouping 是否过宽

**结论：** 不过宽。两个 slice 的理由充分：

- E1（failures 1/2/3）：全部是 Engine 层测试对已接受 public/diagnostic contract 的滞后。每个修复只改一个测试文件，无 stop condition 需要跨文件协同。
- E2（failures 4/5/6/7）：全部是 Host 层测试/fixture 对齐。其中 4/5 完全独立（只改 export snapshots），7 完全独立（只改 fixture），只有 6 的 stop condition 需要单独关注。

按总控文档的 slice 切分原则（"小型同一语义 cleanup 优先合并"），2 slices 在 1-3 的预算范围内且每个都可独立验证。详见 Finding 3 关于 E2 内 heterogeneous 风险的讨论。

### 3. stream heartbeat 的 STREAM_DEBUG_LOG_LEVEL 判断是否有直接证据

**结论：** 有充分直接证据。

- `dayu/runtime/log_levels.py:16`：`STREAM_DEBUG_LOG_LEVEL = DEBUG_LOG_LEVEL - 1`（整数 9，低于 `logging.DEBUG`=10）
- `dayu/engine/runners/openai/runner.py:968-969`：`self._logger.log(STREAM_DEBUG_LOG_LEVEL, "runner.stream_idle.heartbeat " + ...)`
- `dayu/engine/runners/openai/sse_parser.py:348`：SSE 解析器同样使用 `STREAM_DEBUG_LOG_LEVEL` 进行流诊断

生产行为意图明确：stream-only diagnostic（包括 heartbeat）只能在 `--debug-stream` 级别捕获，不能在普通 `--debug`（`logging.DEBUG`）中可见。这是刻意设计，不是疏忽。

### 4. Engine input_projection / projection exports 是否有设计真源支撑

**结论：** 有充分设计真源支撑。

- `docs/engine/design.md:58`（公共入口段）：明确写道 "当前包根也导出 Runner 请求身份与输入观测相关公共契约，包括 `RunnerInputMessageProjection`、`RunnerInputToolCallProjection`..."
- `docs/engine/design.md:472`（EngineEvent 表段）：明确 `iteration_started` 携带 `input_projection` 及其字段结构、中性约束
- 生产代码：`engine_events.py:112` 的 `IterationStartedData` 包含 `input_projection` 字段；`engine/__init__.py:80-81,169-170` 导出两个 projection 类型

两个 projection 类型不是实现类、不是 runner 私有 adapter——design doc 明确称它们为"公共契约"。

### 5. HostThinkingView export 是否有设计/API 支撑

**结论：** 有充分设计/API 支撑。

- `dayu/host/README.md:239`（host 公共接口段）：`HostThinkingView` 被列为 "Host 对 UI / Service 暴露的 typed event view、安全 activity view 与运行态 thinking view"
- `dayu/host/README.md:539`（HostEvent 段）：明确 `HostEvent` 携带可选 `HostThinkingView`
- 生产代码：
  - `host/api.py:2649-2664`：`HostThinkingView` dataclass 定义
  - `host/api.py:3061`：`HostEvent.thinking: HostThinkingView | None`
  - `host/api.py:3565`：`"HostThinkingView"` in `api.__all__`
  - `host/__init__.py:55,200`：import 和 export
  - `host/read_api.py:36,1110-1124`：`_thinking_from_row` 消费并生成 `HostThinkingView`

`HostThinkingView` 是完整的 public API 元素：有 design doc 描述、有 typed dataclass、有 `HostEvent` 字段引用、有 read API 消费路径。不存在"泄露实现细节"的风险。

### 6. wait-resume integration 改断言协议闭环是否正确；是否可能掩盖 production regression

**结论：** 改断言为协议闭环方向正确，但必须先做 fixture 诊断确认当前生产路径实际产出的消息结构（详见 Finding 1）。

如果 fixture 诊断确认正常路径被正确触发，改断言为 `UserMessage → AssistantMessage(tool_call) → ToolMessage` 是**比旧断言更严格的回归保护**——它不光检查"某种 guidance 文本存在"，而是检查：
- Resume 请求包含原始 user prompt（而不是只传 system guidance）
- Assistant tool call 的 `id/name/arguments` 与 awaiting request 一致
- Tool message 的 `tool_call_id` 与 assistant tool call 一致，content 包含 `answer: 42`
- 不会意外覆盖旧英文 fallback 路径的缺失

如果 fixture 诊断发现正常路径未被触发（fallback 路径），说明生产代码的 `accepted_arguments` 返回 `None`——这通常是 fixture 缺少 `TOOL_CALL_REQUESTED` request atom 或 accepted evidence envelope 的结果。此时不应"放宽 assertion 为 fallback guidance"，而应**先修 fixture**，确保测试覆盖生产正常路径。

### 7. purge cancelling fixture 的 proposed fix 是否语义有效

**结论：** 语义有效，但 fixture 细节需注意（详见 Finding 2）。

核心判断：
- Plan 的 fix 方向（添加合法 `cancel_request_event_id`）是正确的 owner boundary 修复：owner 是 fixture（它错误地插入了 schema-invalid 数据），fix 落在 fixture 端
- Plan 不放宽生产 schema——这是正确的：production CHECK constraint 的语义是 "cancelling/cancelled 必须有 cancel request event"，放开它会让真实的 production cancel lifecycle 数据完整性退化
- Plan 不在 purge helper 捕获 CHECK 失败——这也是正确的：purge helper 的 precondition 检查应该依赖同 schema 的 durable invariant，而不是在 purge 路径做 defensive fallback

### 8. validation/README/propagation audit 是否完整

**结论：** 基本完整，有一个 INFO 级别的补充建议（Finding 4）。

Plan 包含：
- Targeted validation：7 个 targeted 命令，覆盖每个失败
- Regression validation：4 层 regression（相关模块 focused test → runtime → broad Engine/Host → full suite）
- README trigger analysis：正确识别 implementation 只改 tests，不会触发生产 README 更新
- Propagation audit：wait-resume LLM-facing semantics 的 6 步 propagation 路径完整

建议补充（implementation closeout 中完成，无需改 plan）：
- 显式记录 export snapshot alignment（failures 3/4/5）的 propagation 结论：生产代码未变，设计真源已覆盖
- 显式记录 purge fixture fix 后 Run row 的 durable invariant 确认（`cancel_request_event_id IS NOT NULL` for cancelling）

---

## Evidence verification log

| Plan claim | Direct evidence | Result |
|---|---|---|
| `iteration_started` 携带 `input_projection` | `engine_events.py:112`, `engine/design.md:472` | Confirmed |
| Engine 包根导出两个 projection 类型 | `engine/__init__.py:80-81,169-170`, `engine/design.md:58` | Confirmed |
| Stream heartbeat 使用 `STREAM_DEBUG_LOG_LEVEL` | `runner.py:968-969`, `log_levels.py:16` | Confirmed |
| `HostThinkingView` 是 HostEvent public typed view | `host/README.md:239,539`, `host/api.py:2649,3061,3565` | Confirmed |
| `HostThinkingView` 在 `dayu.host.__all__` | `host/__init__.py:200` | Confirmed |
| `HostThinkingView` 在 `dayu.host.api.__all__` | `host/api.py:3565` | Confirmed |
| 生产 resume 路径优先重建 User/Assistant/Tool 协议闭环 | `run_input.py:986-1036` | Confirmed |
| Durable schema 要求 cancelling/cancelled 有 `cancel_request_event_id` | `schema.py:537-539` | Confirmed |
| Purge fixture `_insert_run_row` 不写 `cancel_request_event_id` | `test_purge_session.py:1535-1569` | Confirmed |
| 4 failed 复现 | plan line 38 command: 4 failed, 5 passed | Confirmed by plan |

---

## Residual risks after implementation

1. **wait-resume fixture 诊断未做：** 如果 implementation 跳过 Fixture 诊断直接改 assertion，且 fixture 实际缺少 request atom，会导致 assertion 改为协议闭环检查后测试失败，但错误地诊断为"production regression"而非"fixture 缺陷"。
2. **broad suite 可能有其他 stale snapshot：** 7 个 targeted 失败之外，broad suite 可能有其他测试因同一轮 public contract expansion 而 stale。Regression validation 应覆盖此风险，但建议额外关注 `tests/host/test_*` 和 `tests/engine/test_*` 中任何使用 snapshot/contract locking pattern 的测试。
3. **purge fixture 修改范围可能被低估：** `_insert_run_row` 的调用方不止 `_SeedClosedSessionMatrixOperation`，如果修改 `_insert_run_row` 签名（添加 `cancel_request_event_id` 参数），需要检查所有调用方。如果只在 `_SeedClosedSessionMatrixOperation` 中单独创建 cancel request event 并直接 INSERT，则不影响其他调用方。

---

## Decision

**pass-with-findings**。Plan 的 owner boundary 分析正确，failure taxonomy 准确，slice 分组合理，stop conditions 充分。4 个 findings 均可在一轮 implementation 内解决：Finding 1 要求在 implementation 第一步做 fixture 诊断（不改变 plan 结构），Finding 2 是 fix 实现细节建议，Finding 3 是被 stop condition 自然覆盖的提醒，Finding 4 是 closeout 记录补充。

没有 blocking finding。Implementation 可以 proceed。
