# Code Review — P8-S2 Host Event Stream Cursor Truth / Fanout Boundary

## 判决

**PASS** — 无阻塞发现。

生产代码 `dayu/host/read_api.py` 在 S2 中未被修改；其现有实现已满足全部 P8-S2 计划要求。测试变更质量合格，覆盖了所有计划要求的边界场景。导入守卫测试设计合理。

## Scope

- **Mode**: Current Changes（未提交 workspace changes）
- **Branch**: `feat/host-phase8-projection-core-event-stream`
- **Base**: S1 accepted commit `80c12a2`
- **Output file**: `docs/reviews/host-phase8-code-review-s2-ds-20260516.md`
- **Included scope**: `tests/host/test_public_event_stream.py`（已修改）、`tests/host/test_import_boundary.py`（已修改）、`dayu/host/read_api.py`（未修改，但作为被测试的生产代码审查）、`tests/host/test_weak_typing_guard.py`（验证仍绿）
- **Excluded scope**: S1 已提交代码、S3 范围文件、README（实现文档判定无需同步）
- **Parallel review coverage**: 无

## Findings

### 1-未修复-低-导入守卫令牌检查对注释/文档字符串存在误报可能

- **入口/函数**: `test_read_api_stream_does_not_reference_projection_or_fanout_truth`
- **文件(行号)**: `tests/host/test_import_boundary.py:212-214`
- **输入场景**: `read_api.py` 的 docstring 或注释中包含 "fanout"、"wakeup" 等英文单词（例如 `# No fanout implementation in this file`）
- **实际分支**: `token in source` 的简单子串匹配会将注释或字符串字面量中的匹配当作违规
- **预期行为**: 守卫应仅检测代码引用，不应因注释或文档字符串触发
- **实际行为**: 子串匹配无法区分代码标识符与注释/字符串中的自然语言文本
- **直接证据**: 第 212-214 行 `token for token in READ_API_EVENT_STREAM_FORBIDDEN_TOKENS if token in source` 使用朴素字符串包含
- **影响**: 开发者在 `read_api.py` 中添加说明性注释（如 "fanout is not used here"）会导致测试误报，增加维护摩擦
- **建议改法和验证点**: 考虑对源代码做 AST 遍历，仅检查标识符节点和字符串字面量节点的 `Name` / `Constant`，跳过注释和 docstring。或保持现状，因为导入检查（AST 级）已经覆盖了主要风险面，令牌检查是补充防御
- **修复风险**: 低
- **严重程度**: 低

## Open Questions

- 无。

## Residual Risk

1. **S3 投影表侧效未覆盖**: 当前测试仅检查 `host_projection_checkpoints` 和 `host_projection_failures` 不被 `stream_run_events` 写入。P8-S3 新增 `host_run_results`、`host_session_timeline_items` 后，需要补充对应边界测试，确保 stream 不写入新投影表。当前测试结构易于扩展——只需在 `test_stream_run_events_does_not_write_projection_tables` 中增加对新表的快照比对。

2. **fanout/wakeup 未来引入风险**: 当前无 fanout 代码，导入/令牌守卫覆盖了 `read_api.py` 级别。但如果未来 fanout 通过其他机制（如 after-commit hook 在 `command.py` 中注册回调）间接影响 stream 行为，当前守卫无法检测。P8 计划将此风险 defer 给后续 fanout owner。

3. **测试使用直接 SQLite 写入模拟投影状态**: `_write_projection_checkpoint` 和 `_write_projection_failure` 绕过 Host API 直接写表，不经过 `HostTransactionRunner`。这与生产环境投影 runner 通过 Host 事务写入的行为略有差异（如 WAL 隔离级别、外键约束生效方式），但对 S2 目标（证明 stream 独立于投影状态）无实质影响。

## Plan Compliance Checklist

| 计划要求 | 状态 | 证据 |
|---|---|---|
| 保持 `stream_run_events` Phase 4 语义 | PASS | 生产代码未修改，`_StreamRunEventsOperation.__call__` 仅读 EventLog |
| `stream_run_events` 不读取 projection checkpoint | PASS | `read_api.py` 未导入 `dayu.host.durable.projection`；导入守卫测试验证 |
| `stream_run_events` 不读取 fanout/notification 状态 | PASS | 导入守卫覆盖 `dayu.host.fanout`、`dayu.host.notification` |
| `stream_run_events` 不写 projection 表 | PASS | `test_stream_run_events_does_not_write_projection_tables` 验证 |
| `stream_run_events` 不触发 repair | PASS | `repair_minimal_read_models` 令牌守卫覆盖；生产代码无调用 |
| 投影检查点落后不影响 stream 结果 | PASS | `test_stream_run_events_ignores_projection_checkpoint_lag` |
| 投影失败行存在不影响 stream 结果 | PASS | `test_stream_run_events_ignores_projection_failure_row` |
| 无 fanout/wakeup 实现 | PASS | 无新增模块，无 fanout shell |
| 现有 Phase 4 测试保持绿 | PASS | 实现文档报告 18 passed（含全部已有测试） |
| pyright 零报错 | PASS | 实现文档报告 0 errors, 0 warnings |
| `git diff --check` clean | PASS | 实现文档报告通过 |
| 未修改 S2 范围外生产文件 | PASS | diff 仅含两个测试文件 + 实现文档 |

## Production Code Trace

沿 `read_api.py` 关键执行路径走读：

1. **`stream_run_events` 入口** (line 59-85): 构造 `_StreamRunEventsOperation` 并委托 `host._run_read()` → 正确。

2. **`_StreamRunEventsOperation.__call__`** (line 148-181):
   - Run 存在性校验 (line 156): 调用 `read_run_by_id` → 正确，仅依赖 durable state。
   - limit 解析 (line 162): 调用 `_resolve_stream_limit` → 正确，拒绝零/负/超限值。
   - EventLog 扫描 (line 163-167): 调用 `read_events_after(transaction, cursor.event_sequence, limit=...)` → 唯一真源。
   - cursor 推进 (line 168-173): 无扫描行时保持输入 cursor，否则取 last scanned `event_sequence` → 与 Phase 4 contract 一致。
   - 事件过滤/映射 (line 174-181): 按 `run_id` 过滤，`_event_view_from_row` 映射 → 正确，不涉及投影状态。

3. **`_resolve_stream_limit`** (line 184-199): 默认值/边界检查 → 正确，使用 public 常量。

4. **`_event_view_from_row`** (line 202-217): 从 `EventLogRow` 提取稳定字段 → 正确，不暴露内联 payload。

全路径确认：`stream_run_events` 从头到尾仅依赖 EventLog 和 durable Run state，不触及投影 checkpoint、failure、fanout、repair 或 session timeline。

## Guard Test Trace

**`test_read_api_stream_does_not_reference_projection_or_fanout_truth`**:
- 读取 `dayu/host/read_api.py` 完整源码 (line 206-207)
- AST 提取 import 模块名 (line 208-211)
- 前缀匹配检查：`dayu.host.projection`、`dayu.host.durable.projection`、`dayu.host.read_model`、`dayu.host.fanout`、`dayu.host.notification` → 当前生产代码均未命中
- 令牌子串检查：`host_projection_checkpoints`、`host_projection_failures`、`host_session_timeline_items`、`repair_minimal_read_models`、`fanout`、`wakeup` → 当前生产代码均未命中
- 双重守卫（AST import + 文本令牌）提供了分层防御

**现有导入守卫未被削弱**: `test_projection_modules_do_not_import_forbidden_layers_or_mutators` 保护 S1 投影模块边界，S2 新增的守卫是正交的 `read_api` 边界保护。

## Weak Typing Guard

`test_weak_typing_guard.py` 仅扫描 `dayu/host/` 生产代码，S2 未修改任何生产代码，故该测试不受影响。实现文档报告通过。

## Test Adequacy Assessment

| 测试 | 覆盖场景 | 断言强度 |
|---|---|---|
| `test_stream_run_events_ignores_projection_checkpoint_lag` | checkpoint 落后 → stream 仍返回完整 EventLog 结果 | 强：独立 SQL 计算期望值，精确比对 event_sequence/event_id/event_type 三元组和 next_cursor |
| `test_stream_run_events_ignores_projection_failure_row` | failure row 存在 → stream 不受影响 | 强：limit=3 的精确窗口扫描，cursor 用 `_max_scanned_event_sequence` 独立验证 |
| `test_stream_run_events_does_not_write_projection_tables` | stream 为纯读操作 | 强：前/后完整行快照对比，且断言 stream.events != () 确保确实发生了读取 |

所有三个新测试使用独立的 SQLite 连接从 EventLog 计算期望值（不依赖 Host 内部读路径），与实践声称的"EventLog 是 stream 的唯一真源"一致。测试 helper 函数 `_event_views_for_run_after` 正确复制了生产代码的 scan-window contract（`WHERE event_sequence > cursor ORDER BY event_sequence ASC LIMIT limit`，然后按 `run_id` 过滤）。
