# WU-LAYER-02 Slice 2 Implementation Report

## Changed Files

- `dayu/runtime/diagnostic_text.py`
- `tests/runtime/test_diagnostic_text.py`
- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase2.py`
- `docs/reviews/wu-layer-02-slice2-implementation-report-20260602.md`

未修改 `README` 文件，未 commit，未 push。

## Behavior Boundary

本次先关闭 runtime boundary blocker，再完成 Engine Agent exception diagnostic migration。

Runtime diagnostic text 边界调整：

- `Bearer` value 采用 Engine 已有 token 字符集边界，`Bearer }` 与 `Bearer ]` 不再被识别为敏感值。
- assigned-key value 采用 `[^,\s}\]]+` 边界，保留 `api_key=;`、`token=;`、`authorization=;`、`password=;`、`secret=;` 等分号 value start 的敏感判断。
- `api_key=}`、`api_key=]`、`token=}`、`token=]` 不识别为敏感值。
- 保持 `api key <plain-word>` broad match。
- 保持 `JWT token has expired`、`Content-Type header is invalid` 等普通诊断 false-positive guard。
- `redact_sensitive_diagnostic_values` 仍只做 Host-style value redaction；本次没有改变 runtime API，也没有引入 Host / Engine 依赖。

Engine migration：

- `dayu/engine/agent.py` 删除 Engine 私有 secret regex 和 `_contains_sensitive_exception_value`。
- Engine 改用 `dayu.runtime.diagnostic_text.contains_sensitive_diagnostic_value` 与 `truncate_diagnostic_text`。
- `_exception_diagnostic_message` 继续保持 Engine 策略：敏感值命中时整条变为 `exception message redacted`，普通长消息使用 Engine suffix `... [truncated]` 截断。
- `_safe_log_message` 继续保持 Engine 策略：空白消息整条 redacted，敏感值整条 redacted，普通长消息使用 Engine suffix 截断。
- 未使用 Host-style value redaction。
- 未改变 Agent 状态机、`RunnerEvent`、`RunFailedData` 字段、metadata 或 public contract。

## Tests / Pyright

已运行：

```bash
source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/engine/test_agent_phase2.py
```

结果摘要：

```text
112 passed in 0.21s
```

已运行：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果摘要：

```text
0 errors, 0 warnings, 0 informations
```

## README Sync Decision

- 根目录 `README.md`：不更新。用户安装、配置、跑通、CLI、trace/render 入口未变化。
- `dayu/README.md`：不更新。Slice 1 已记录 runtime diagnostic text capability；本次只收敛边界并迁移 Engine 调用点。
- `dayu/engine/README.md`：不更新。Engine public contract、状态机、事件流与扩展点未变化。
- `tests/README.md`：不更新。测试分层、运行方式与维护约定未变化；仅补充既有测试文件中的行为矩阵。

## Residual Risks

- 当前 runtime sensitive value 边界是文本启发式，不是 provider-specific secret parser；这符合本 WU 的层中立 helper 范围。
- 未迁移 Host compaction，本报告只覆盖 Slice 2 Engine migration。
- 工作树中存在本次未处理的既有变更：`docs/host/host-core-followup-implementation-control.md`。
