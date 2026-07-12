# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S7 Controller Validation

## 结论

`pass-for-code-review`。

Controller 独立复验接受 AgentCodex 的 S7 implementation handoff。当前变更停留在 S7 allowed files 内；`dayu/engine/` diff 为空，未修改 Service、CLI、Fins 或 R3-B/R3-E scope。

## 验证

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_cancellation_scope.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q
```

结果：`307 passed in 2.71s`。

```bash
source .venv/bin/activate
python -m pyright dayu/host/compaction_operation.py dayu/host/llm_compaction.py dayu/host/dispatch.py dayu/host/engine_ingest.py tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --name-only -- dayu/engine/
git diff --check
```

结果：Engine diff 空；`git diff --check` 通过。

## Source Scan 分类

```bash
rg -n '_signal_timeout_cancellation|request_cancel\(' dayu/host/llm_compaction.py dayu/host/compaction_operation.py
```

分类：timeout cancellation 只命中 `dayu/host/llm_compaction.py` 的 attempt-local child token helper；`request_cancel()` 命中为 cancellation protocol method 或 child-token timeout call，不污染 parent token。`dayu/host/compaction_operation.py` 的命中为 read-only protocol surface。

## Review Focus

- 每个 provider attempt 必须使用 fresh child token；timeout 只能取消 child，不能污染 parent Run token。
- parent cancellation reason/requested_at 必须优先于 attempt timeout。
- manifest commit 后、provider call 前必须有真实 durable pre-call recheck。
- Engine cancellation protocol 仍是 read-only；不得引入 writable Engine contract。
