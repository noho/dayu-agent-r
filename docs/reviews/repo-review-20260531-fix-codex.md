# repo-review-fix 修复说明

## 输入

- MiMo review：`docs/reviews/repo-review-20260531-165913.md`
- DS review：`docs/reviews/repo-review-20260531-165918.md`
- 执行 Agent：implementation/fix AgentCodex
- Gate：repo-review-fix

## 裁定原则

- 只修复有直接代码证据、严重度未被明显高估、且适合本轮 bugfix 小范围完成的问题。
- 生产代码修改均补充对应测试。
- 不处理纯维护性大重构，不为旧接口补兼容逻辑。
- 未触碰用户要求避开的未跟踪文件：`docs/host/conversation-memory-discussion.md`、`docs/host/followup-hardening-control.md`。

## 已修复项

### MiMo 001：幂等写入 INSERT 阶段缺少并发 IntegrityError 保护

- 裁定：成立。
- 证据：`record_idempotent_result()` 先读后插，原 INSERT 未捕获 `sqlite3.IntegrityError`；同模块已存在 digest 冲突语义，`event_log.append_event()` 也采用冲突后回读模式。
- 修复：`dayu/host/durable/idempotency.py` 捕获 INSERT `IntegrityError` 后回读既有记录；digest 相同返回既有 record，digest 不同抛 `HostIdempotencyConflictError`。
- 测试：`tests/host/test_idempotency_store.py` 增加受控 interleaving fake transaction，覆盖相同 digest 回读成功与不同 digest 冲突。

### DS 2：non_stream_parser 非 dict tool_calls 静默跳过

- 裁定：成立。
- 证据：`_build_tool_calls()` 对非 dict 元素直接 `continue`；当列表非空但全非法时，下游只能看到空 tool calls。
- 修复：`dayu/engine/runners/openai/non_stream_parser.py` 对非 dict 元素产出协议诊断；若没有任何 JSON object tool call，追加 fatal protocol error 并以 `Done(ERROR)` 收口。
- 测试：`tests/engine/runners/openai/test_non_stream_response.py` 增加全非法 tool_calls 用例。

### DS 4：dispatch drain durable retry exhausted fail-close 不取消活跃任务

- 裁定：成立。
- 证据：`_drain_loop()` retry exhausted 分支只设置 `_closed` 并标记 host instance stopped，未对 active registry 执行 cancel。
- 修复：`dayu/host/dispatch.py` 在该 fail-close 分支调用 `ActiveWorkerRegistry.cancel_all()`，与 scheduler close 的 active cancel 语义对齐。
- 测试：`tests/host/test_dispatch_scheduler.py` 覆盖 retry exhausted 后 active token 被取消。

### DS 5：open_host 启动异常路径不 flush projection catch-up

- 裁定：成立。
- 证据：`_OpenHostContextManager.__aenter__()` 在 scheduler 打开后、host handle 创建前失败时只 close scheduler 和 durable store；close projection port 尚未交给 `_PublicHostHandle`，因此不会 flush。
- 修复：`dayu/host/open_host.py` 增加启动失败清理路径 best-effort projection catch-up，失败只记录 warning，不吞原始异常。
- 测试：`tests/host/test_open_host_runtime.py` 模拟 startup recovery scan 失败，断言异常退出前执行 catch-up。

### DS 6：Content-Type 缺失时 stream=True 被分类为 SSE

- 裁定：成立。
- 证据：`_is_sse_response(content_type="", stream=True)` 原逻辑返回 True。
- 修复：`dayu/engine/runners/openai/runner.py` 对空 Content-Type 保守走非流式解析，并记录 warning 诊断。
- 测试：`tests/engine/runners/openai/test_streaming_capability_and_content_type.py` 覆盖 stream=True、缺 Content-Type、JSON body 的路径。

### DS 7：正常迭代空 content 与 force-answer 空 content 处理不一致

- 裁定：成立。
- 证据：普通 final path 会接受 `content=""`；force-answer path 已拒绝空内容。
- 修复：`dayu/engine/agent.py` 普通 final path 拒绝空 content，返回 `runner_empty_final_content`；force-answer 保留原有 `force_answer_empty` 错误码。
- 测试：`tests/engine/test_agent_phase3_tool_call.py` 增加普通 final 空 content fail-closed 用例，并保留 force-answer 原错误码测试。

### DS 8：transaction.py type ignore 绕过 sqlite_errorcode 类型检查

- 裁定：成立。
- 修复：`dayu/host/durable/transaction.py` 用私有 Protocol + `cast` 表达 Python 运行时 sqlite 扩展属性，移除 `# type: ignore[attr-defined]`。
- 验证：pyright 通过。

### DS 9：filelock release 失败时状态不一致

- 裁定：成立。
- 修复：`dayu/runtime/filelock.py` 在底层 release 失败时也将 token 标记为 `released=True`，避免调用方二次释放；同时 marker restore 失败改为 DEBUG 诊断，不再静默吞掉。
- 测试：`tests/runtime/test_filelock.py` 增加底层 release 失败后不重试的状态测试。

## 未修复项与理由

### DS 1：God function 13 处

- 裁定：问题属于维护性大重构，当前行为证据不足以证明本轮 bugfix blocker。
- 处理：不改生产代码。需要单独计划拆分核心循环和 Host dispatch 大函数，并配套更大范围回归。

### DS 3：purge replay 路径丢弃 artifact cleanup refs

- 裁定：风险成立，但当前 schema 不足以正确修复。
- 证据：tombstone 只持有 `deleted_refs_digest`，该字段是 digest，不可从中反解析 `artifact_relative_paths`。现有 `PurgeTombstoneRow` 没有保存可清理 artifact refs 的结构化列。
- 处理：不做表面修。需要 tombstone schema 设计或独立 GC 设计后再修。

### DS 10：purge precondition 检查与删除动作距离

- 裁定：当前严重度被高估。
- 证据：当前事务模型为 `BEGIN IMMEDIATE`，前置检查和删除在同一写事务内，未见可导致错误删除的竞态证据。
- 处理：不做本轮生产重排；可作为后续可读性重构。

### DS 11：scheduler close clean EOF 分类

- 裁定：低风险语义精度问题，不适合本轮改 terminal 语义。
- 证据：`close()` 已传播 active cancel；clean EOF closeout 的终态分类牵涉 EngineEvent ingest 终态语义，不是单点诊断改动。
- 处理：不改生产代码，避免扩大状态机变更面。

### DS 12：并发 cancel deferred check 不精确

- 裁定：低概率幂等语义问题，需更完整的 public API 时序设计。
- 处理：不纳入本轮。

### DS 13：batch timeout elapsed_seconds 硬编码 0.0

- 裁定：诊断精度问题成立，但当前函数只接收 batch deadline，未持有 batch start；直接修改需要扩展调用链参数。
- 处理：不做表面修。

### DS 14：filelock marker restore 静默吞异常

- 裁定：成立，已随 DS 9 一并修复为 DEBUG 诊断。

### DS 15：scene system prompt 非空校验

- 裁定：配置策略变更，不属于本轮 bugfix。
- 处理：不纳入本轮。

### DS 16-18：runner 错误体部分读取、idle heartbeat 日志、pending readany 日志级别

- 裁定：均为诊断质量低风险项。
- 处理：不纳入本轮，避免在 Runner 清理路径扩大改动面。

### DS 19：SSE tool_calls delta 非 dict 元素静默跳过

- 裁定：与 DS 2 同类，但 SSE 路径涉及流式 partial 聚合与 warning 是否影响 Agent failure candidate 的契约，需要单独设计。
- 处理：不纳入本轮。

### DS 20：长度续写路径空 content 可能导致连续 user 消息

- 裁定：边缘协议风险成立，但与 continuation 消息构造策略相关。
- 处理：不纳入本轮。

### DS 21：cancellation helper 吞已失败任务真实异常

- 裁定：race 小窗口诊断透明度问题。
- 处理：不纳入本轮。

### DS 22-23：contracts 校验增强

- 裁定：公共契约收紧，可能影响现有调用方。
- 处理：不纳入本轮 bugfix。

### DS 24-27：事务读重试参数、schema bootstrap DDL、purge tombstone 补录异常细分、log level 文档

- 裁定：低风险维护性或文档语义问题，不是本轮 blocker。
- 处理：不纳入本轮。

### DS 28：测试函数命名

- 裁定：提示级维护性问题。
- 处理：不纳入本轮。

## README 裁定

触发检查范围包括 `dayu/engine/README.md`、`dayu/host/README.md`、`dayu/README.md`、`tests/README.md`。本轮变更是内部错误处理、fail-close 清理和诊断补强；未改变稳定 public contract、命令、配置入口、架构边界或测试层级，因此 README 无需修改。

## 变更文件

- `dayu/host/durable/idempotency.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/agent.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `dayu/host/durable/transaction.py`
- `dayu/runtime/filelock.py`
- `tests/host/test_idempotency_store.py`
- `tests/engine/runners/openai/test_non_stream_response.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_open_host_runtime.py`
- `tests/runtime/test_filelock.py`

## 验证

```bash
source .venv/bin/activate && pytest tests/host/test_idempotency_store.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/test_agent_phase3_tool_call.py::test_force_answer_empty_and_tool_call_are_fail_closed tests/engine/test_agent_phase3_tool_call.py::test_normal_final_empty_content_is_fail_closed tests/host/test_dispatch_scheduler.py::test_drain_loop_fail_closes_on_durable_retry_exhausted tests/host/test_open_host_runtime.py::test_open_host_startup_failure_flushes_projection_before_close tests/runtime/test_filelock.py
```

结果：44 passed。

```bash
source .venv/bin/activate && pyright
```

结果：0 errors, 0 warnings, 0 informations。

## 残余风险

- purge replay artifact cleanup 需要 schema 或 GC 设计，当前不具备从 tombstone digest 恢复 refs 的数据来源。
- God function 拆分、SSE 非 dict tool_calls 诊断、continuation 空 content、contracts 校验增强等均需要独立计划和更大范围回归。
- 本轮未运行全仓 pytest；已运行受影响测试与全量 pyright。
