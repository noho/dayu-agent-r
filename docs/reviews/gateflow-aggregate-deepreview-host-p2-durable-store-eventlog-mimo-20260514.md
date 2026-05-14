# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-phase2-durable-store-eventlog`
- Base: `main`
- Output file: `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-mimo-20260514.md`
- Included scope: `dayu/host/durable/`（14 个生产模块）、`tests/host/`（8 个测试文件）、`dayu/host/README.md`、`tests/README.md`、`docs/host/`（design.md、implementation-control.md、phase2 plan）、`docs/reviews/`（slice review artifacts）
- Excluded scope: `dayu/engine/`、`dayu/fins/`、`dayu/service/`、`dayu/ui/`、`dayu/runtime/`（非 Phase 2 变更范围）
- Parallel review coverage: 无
- Commits reviewed: 83c6ad6, be5dbdc, 50ba2d7, 7bbce64（4 commits）
- Total diff: ~59 files changed, ~11770 insertions

## Verification Results

| 检查项 | 结果 |
|--------|------|
| `pytest tests/host -q` | 94 passed in 0.43s |
| `pytest tests/runtime/...` | 29 passed in 0.58s |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| Engine/Fins/Service/UI/runtime import 污染 | 未发现（仅允许 `dayu.contracts.json_value.JsonValue`） |
| Host durable truth 位置 | 全部在 `dayu.host.durable` 内 |
| Schema / transaction / EventLog / idempotency / payload / artifact / liveness 语义 | 与 plan 一致 |
| README sync | `dayu/host/README.md` 和 `tests/README.md` 已按触发规则更新，内容为当前事实 |

## Findings

未发现实质性问题。

以下为两个低严重度的观察项，不影响 correctness 或 stability：

### 1-未修复-低-heartbeat / register 可将 stopping 状态回退为 running

- **入口/函数**: `heartbeat_current_instance()` 和 `register_current_instance()`（`dayu/host/durable/liveness.py:235`、`liveness.py:198`）
- **文件(行号)**: `dayu/host/durable/liveness.py:235-247`、`liveness.py:196-209`
- **输入场景**: Host 已调用 `mark_current_instance_stopping`，随后意外触发 `heartbeat_current_instance` 或 `register_current_instance`
- **实际分支**: UPDATE 语句无条件设置 `status = 'running'`
- **预期行为**: 当前设计有意如此——heartbeat 和 register 在 `WHERE process_start_token = ?` 保护下只操作当前进程自身 row，且 register 有 `_require_same_identity` 校验。此行为在测试 `test_repeated_register_same_identity_refreshes_heartbeat_and_status`（line 96）中被显式验证
- **实际行为**: `stopping` → `running` 状态回退
- **直接证据**: `liveness.py:235-247`（heartbeat UPDATE SET status = 'running'）；`liveness.py:198-209`（register UPDATE SET status = 'running'）
- **影响**: 若 Host 在 graceful shutdown 期间意外触发 heartbeat/register，会将自身状态从 stopping 回退为 running。当前 Phase 2 没有 recovery 消费此状态，影响为零；后续 phase 引入 recovery classifier 时需注意此行为
- **建议改法和验证点**: 当前无需修改。后续 phase 若需要严格 lifecycle 状态机，可考虑 heartbeat/register 在 `status IN ('running')` 时才更新，或在 UPDATE WHERE 子句中加 `AND status = 'running'`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-SQLitePayloadWriteRequest.payload_json 默认 None 在 canonical_json 格式下编码为 "null"

- **入口/函数**: `write_sqlite_payload()`（`dayu/host/durable/payload.py:190`）
- **文件(行号)**: `dayu/host/durable/payload.py:81`（字段定义）、`payload.py:429-440`（编码路径）
- **输入场景**: 调用方构造 `SQLitePayloadWriteRequest(payload_format=SQLitePayloadFormat.CANONICAL_JSON)` 且不显式提供 `payload_json`
- **实际分支**: `_encode_sqlite_payload` 对 `CANONICAL_JSON` 格式调用 `canonical_json_dumps(None)` → 输出字符串 `"null"` → `len("null".encode("utf-8"))` = 4 bytes → digest = `sha256:74234e98afe71541...`
- **预期行为**: `JsonValue` 类型别名包含 `None`（即 JSON `null`），所以 `canonical_json_dumps(None)` 返回 `"null"` 是类型正确的。但调用方可能期望 `payload_json` 必须显式提供
- **实际行为**: 默认值 `None` 被编码为 JSON `null` literal 存入 SQLite
- **直接证据**: `payload.py:81`（`payload_json: JsonValue = None`）；`payload.py:431`（`canonical_json_dumps(request.payload_json)`）
- **影响**: 功能正确但语义微妙。当前无调用方依赖此默认值（所有测试都显式提供 payload_json），后续调用方若遗漏此字段会静默存入 JSON `null`
- **建议改法和验证点**: 若后续调用方不应依赖默认值，可考虑移除默认值或在 `_validate_sqlite_payload_request` 中对 `CANONICAL_JSON` 格式要求 `payload_json is not None`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

1. **Artifact orphan cleanup**: plan 已明确 SQLite rollback 后已发布的 artifact 文件属于 cleanup / diagnostics orphan，不是 accepted fact。当前 Phase 2 不实现 orphan cleanup scheduler。后续 phase 需实现清理机制。
2. **Multiprocess concurrency**: `test_event_log_multiprocess.py` 验证了多进程并发 append 的 `event_sequence` 唯一递增，但未覆盖多进程并发写入 idempotency / payload / liveness 的场景。当前 Phase 2 的设计（application-level read-then-write + PRIMARY KEY 约束）在并发写入时依赖 SQLite busy timeout 重试，对于单机多进程场景是充分的。
3. **后续 phase 状态机**: liveness row 的 `stopping` → `running` 回退行为在当前无害，但后续 recovery classifier / lease / fencing phase 需评估此行为是否需要收紧。

## Architecture Boundary Verification

| 边界规则 | 验证结果 |
|----------|---------|
| `dayu.host.durable` 不从 `dayu.host` 包根导出 | 通过：`__init__.py` 仅提供 docstring，无 `__all__` |
| `dayu.host.durable` 不进入 `dayu.host.api` | 通过：无 import 关系 |
| 不 import `dayu.engine` / `dayu.fins` / `dayu.service` / `dayu.ui` | 通过：grep 确认无违规 |
| 不 import `dayu.runtime`（除允许的 contracts） | 通过：仅 import `dayu.contracts.json_value.JsonValue` |
| Host durable truth 全部在 `dayu.host.durable` 内 | 通过：schema、connection、transaction、event_log、idempotency、payload、artifact、liveness 全部在子包内 |
| 不创建 Session / Run / Attempt / wait / projection / outbox / memory / purge 表 | 通过：schema.py 只创建 5 张 foundation table |
| 不实现 command path / Engine dispatch / ToolRuntime / recovery | 通过：docstring 和代码确认 |
| 不做旧库兼容 migration | 通过：schema.py 只处理 fresh DB 和当前版本 |

## Plan Compliance Verification

| Plan 要求 | 实现状态 |
|-----------|---------|
| SQLite fresh bootstrap + PRAGMA user_version 校验 | `schema.py:157-181` |
| WAL / foreign_keys / busy timeout PRAGMA | `transaction.py:251-267` |
| BEGIN IMMEDIATE write transaction + busy retry | `transaction.py:192-248` |
| After-commit callback 顺序执行 | `transaction.py:283-298` |
| EventLog append + event_id 幂等 + identity conflict | `event_log.py:209-288` |
| EventLog global event_sequence cursor 补读 | `event_log.py:336-382` |
| Idempotency (scope_kind, scope_id, key) + digest conflict | `idempotency.py:127-186` |
| Payload descriptor (sqlite_payload + artifact_ref) | `payload.py:190-289` |
| SQLite payload row + descriptor 同 transaction 写入 | `payload.py:211-248` |
| Local artifact write + fsync + digest verify + atomic rename + containment | `artifact.py:75-116` |
| Host instance liveness register / heartbeat / stopping / stopped / read | `liveness.py:157-354` |
| canonical JSON + UTC timestamp + sha256 digest codec | `codec.py` 全文 |
| 结构化错误类型 | `errors.py` 全文（12 个错误类） |
| typed config options | `options.py` 全文 |
| 私有标量校验 helper | `_validation.py` 全文 |
| README sync | `dayu/host/README.md`、`tests/README.md` 已更新 |

## Test Coverage Summary

| 测试文件 | 测试数 | 行数 | 覆盖要点 |
|----------|--------|------|----------|
| test_durable_schema.py | 6 | 246 | fresh bootstrap、idempotent bootstrap、schema mismatch、table constraints |
| test_durable_transaction.py | 9 | 470 | commit、rollback、after-commit、busy retry、constraint error classification |
| test_event_log_store.py | 11 | 569 | append、read by id、cursor read、duplicate same body、duplicate different body、payload ref validation |
| test_idempotency_store.py | 8 | 391 | record、read、same key same digest、same key different digest conflict、conflict not retried |
| test_payload_store.py | 9 | 465 | sqlite payload write、artifact descriptor write、read、digest mismatch、event-log payload ref validation |
| test_artifact_store.py | 10 | 393 | write bytes、expected digest、path containment、temp cleanup、empty content |
| test_host_instance_liveness.py | 8 | 308 | register、heartbeat、stopping、stopped、identity conflict、best-effort mark absent |
| test_event_log_multiprocess.py | 1 | 157 | 多进程并发 append event_sequence 唯一递增 smoke |
| **总计** | **62** | **2999** | |

## Conclusion

**PASS**

Host Phase 2 Durable Store / EventLog / Payload Foundation 实现完整、架构边界干净、类型检查全绿、测试覆盖充分、README 同步正确。未发现 blocking 或 accepted finding。两个低严重度观察项不影响当前功能正确性，已记录供后续 phase 参考。
