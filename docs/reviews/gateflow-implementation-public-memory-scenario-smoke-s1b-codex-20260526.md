# Gateflow 实施产物：Public Memory Scenario Smoke S1b

## Gate

- Work unit：Host public conversation memory scenario smoke
- 当前 gate：implementation
- 分配切片：S1b Host public flow integration
- Worker：Codex implementation worker
- Approved plan：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- S1a accepted commit：`2c98662`
- 停止条件：S1b 完成后停止；未提交、未 push、未开 PR、未进入 review gate 或其它 gate。

## 范围

允许文件：

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s1b-codex-20260526.md`

已遵守 non-goals：

- 未修改现有 minimal smoke。
- 未新增 scene assets、tests 或 README。
- 未读取 private Host durable state、EventLog、sqlite、memory tables、compact payload 或 private Host implementation。
- 未运行 full end-to-end smoke，因为默认 scene manifest 和 prompt assets 延后到 S2。

## 变更文件

- `utils/smoke_host_public_conversation_memory_scenarios.py`
  - 将 S1a skeleton entry flow 替换为 Host public runtime flow。
  - 增加 Service-like runtime assembly：`ConfigLoader`、`resolve_runtime_locations`、`discover_service_tools`、`prepare_scene`、`compose_open_host_options`、`compose_submit_followup_request`。
  - 增加 `discover_smoke_tools` provider，通过 `ToolsDiscoveryProviderOutput` 返回 deterministic `MockFinanceMemoryTool`。
  - 将 `MockFinanceMemoryTool` 改为 public `ToolCallable` 签名和 Host tool outcome 返回形态。
  - 增加 async `run_smoke`：`open_host`、`ensure_session`、tracked tool session、`watch_session_events`、逐轮 `submit_followup`、terminal event 断言、工具调用次数断言、hard/soft answer 检查、每轮后 `get_session`、最终 `calls_by_key` 摘要。
  - terminal failure 摘要只在失败路径使用 public `get_run`。
  - 保留 `--pressure-mode off` 行为，并输出 compact pressure 摘要但不打印完整 pressure payload。
- `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s1b-codex-20260526.md`
  - 新增本文实施产物。

## 已实施计划项

- Runtime assembly 与 `utils/smoke_host_public_conversation_memory.py`、`utils/smoke_host_public_multiturn.py` 保持同类 public boundary style。
- 内置 smoke tool 通过 `ToolsDiscovery`-compatible provider 注入，再与 Service-discovered tools 合并，不修改生产 runtime 包。
- Round 执行由 `RoundSpec` 数据驱动；断言流没有新增 label-based 场景大分支。
- 工具调用计数只在 `track_session(session_id)` 后统计，避免旧 recovered run 污染本次断言。
- 每轮 `tool_names` 通过 `compose_submit_followup_request` 传递；禁用工具轮使用 `frozenset()`。
- public snapshot 只通过 `get_session` 观察。
- 失败诊断只在 terminal non-success 时通过 `get_run` 获取脱敏摘要。

## 验证

执行目录：`/Users/leo/workspace/dayu-agent-r`

```bash
source .venv/bin/activate && python -m py_compile utils/smoke_host_public_conversation_memory_scenarios.py
```

结果：通过，无输出。

```bash
source .venv/bin/activate && pyright utils/smoke_host_public_conversation_memory_scenarios.py
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

边界 grep：

```bash
rg -n "^(from|import) .*dayu\.host\.(durable|read_api|memory|dispatch|command|projection|tool_runtime)|^import sqlite3|sqlite3|\.execute\(|\bSELECT\b|\bFROM\b .*\bmemory\b" utils/smoke_host_public_conversation_memory_scenarios.py
rg -n "^(from|import) .*EventLog|EventLog[A-Za-z]*Reader|event_log\." utils/smoke_host_public_conversation_memory_scenarios.py
rg -n "def [^(]*\([^)]*\b(Any|object)\b|->\s*(Any|object)\b|: (Any|object)\b" utils/smoke_host_public_conversation_memory_scenarios.py
rg -n "\b(getattr|hasattr)\(" utils/smoke_host_public_conversation_memory_scenarios.py
```

结果：全部无匹配。

未运行 full smoke：S1b 阶段默认 scene manifest 和 prompt assets 尚不存在，按 handoff 要求留到 S2 后执行。

## 文档决策

未更新 README。本切片只允许修改 smoke 脚本和 implementation artifact，且明确要求不新增 scene assets/tests/README。用户可执行入口文档应在 S2 scene assets 或后续 executable slice 中同步。

## 残余风险

- End-to-end Host 执行尚未验证，需 S2 增加 scene manifest 和 prompt asset 后覆盖。Owner：后续 S2 slice。
- 默认 scene id 当前可能仍因资源缺失导致 assembly 运行失败。Owner：后续 S2 slice。
- LLM answer 格式遵循仍是 smoke-time 风险；当前硬断言基于 marker/value，软观察不阻断。Owner：S2+ 手工 smoke operator。

## Stop Status

S1b implementation 已完成。已按要求停止在 implementation gate；未提交、未 push、未开 PR、未进入 code review 或其它 gate。
