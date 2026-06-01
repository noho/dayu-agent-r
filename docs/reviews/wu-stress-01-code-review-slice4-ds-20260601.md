# WU-STRESS-01 Slice 4 Code Review — AgentDS

## Scope

- **Mode**: current changes (unstaged)
- **Branch**: `test/host-stress-suite`
- **Base**: `main` (default)
- **Output file**: `docs/reviews/wu-stress-01-code-review-slice4-ds-20260601.md`
- **Included scope**: `tests/host/stress_support.py`, `tests/host/test_host_production_stress.py` — Slice 4 uncommitted diff only
- **Excluded scope**: Slice 1/2/3/5 committed changes; production code; design docs; Codex review artifact as source only
- **Parallel review coverage**: 无（单 reviewer 逐行走读）

### Sources consulted

- `docs/host/design.md` — Host 设计真源
- `docs/host/wu-stress-01-host-production-stress-suite-plan.md` Slice 4 section — 计划契约
- `docs/reviews/wu-stress-01-implementation-slice4-codex-20260601.md` — 上一轮 Codex implementation review（参考，不作为权威裁决）
- `dayu/host/api.py:271-306` — `RunStatus` 枚举定义
- `dayu/host/durable/liveness.py:33-39` — `HostInstanceStatus` 枚举
- `dayu/host/durable/codec.py:57-67` — `parse_utc_timestamp`
- `dayu/runtime/lane.py:123-483` — `LaneConfig`, `LaneController`, `LaneAcquired`
- `tests/host/public_smoke_support.py:856` — lane_db_path 设置

### Validation performed

```bash
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k scheduler_liveness -q
# → 1 passed, 3 deselected in 1.21s

pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
# → 4 passed in 4.69s

pytest tests/host/test_dispatch_scheduler.py tests/host/test_host_instance_liveness.py tests/host/test_public_cancel_session_runs.py -q
# → 1 pre-existing failure (test_memory_lag_pre_dispatch_failure_does_not_enter_recovering), 74 passed

python -m pyright dayu/ tests/ utils/
# → 0 errors, 0 warnings, 0 informations
```

## Findings

### DS-01-未修复-中-terminal_events_for_runs 不覆盖 RUN_LOST 终端事件

- **入口/函数**: `terminal_events_for_runs()` 在 `tests/host/stress_support.py:1229`
- **文件(行号)**: `tests/host/stress_support.py:104-108`（`_TERMINAL_EVENT_TYPES` 定义），`tests/host/stress_support.py:1254-1265`（查询），`tests/host/test_host_production_stress.py:669-671`（`Slice4SchedulerLivenessDiagnostics.terminal_dedupe_ok`）
- **输入场景**: Slice 4 混合流包含一个 `STREAM_EXCEPTION` worker 产生 `RUN_LOST` 终端事件
- **实际分支**: `terminal_events_for_runs()` 的 SQL 查询只过滤 `RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED`（`_TERMINAL_EVENT_TYPES`），SQL 层排除了 `RUN_LOST`
- **预期行为**: `RUN_LOST` 的去重应被显式且一致地覆盖
- **实际行为**: `RUN_LOST` 的去重仅通过 `Slice4SchedulerLivenessDiagnostics.terminal_dedupe_ok` 中的计数比较 `self.all_terminal_event_count == len(self.public_snapshots)` 间接检测——如果 `RUN_LOST` 数量正确则计数匹配。但 `terminal_duplicate_count(self.durable_observations)` 和 `terminal_dedupe_ok(self.durable_observations)` 都不包含 `RUN_LOST` 事件的去重判断
- **直接证据**:
  - `stress_support.py:104-108`: `_TERMINAL_EVENT_TYPES` 仅含 S/F/C
  - `stress_support.py:1294-1325`: `_terminal_kind_for_event_type` / `_terminal_status_for_event_type` 对非 S/F/C 类型抛出 `ValueError`，因此 `RUN_LOST` 无法映射为 `HostEventKind` / `HostTerminalStatus`
  - `test_host_production_stress.py:669-671`: `terminal_dedupe_ok` property 依赖 `all_terminal_event_count == len(self.public_snapshots)` 作为 RUN_LOST 唯一的去重防护
- **影响**: 目前不影响正确性——两个检查的组合（observation-level S/F/C dedupe + count-level 包含 RUN_LOST 的总数比较）能够捕获所有 duplicate 场景。但设计意图不够透明，未来维护者可能误以为 `RUN_LOST` 的去重已被 `terminal_events_for_runs` 覆盖
- **建议改法和验证点**:
  - 在 `Slice4SchedulerLivenessDiagnostics.terminal_dedupe_ok` 的 docstring 中明确说明 RUN_LOST 去重依赖 `all_terminal_event_count` 计数比较，而非 `terminal_dedupe_ok()` helper
  - 或在 `stress_support.py` 的 `_TERMINAL_EVENT_TYPES` 注释中说明为何故意排除 RUN_LOST（因为没有 `HostEventKind.LOST`）
  - 验证点：重新运行 `scheduler_liveness` 测试确认行为不变
- **修复风险（低）**: 仅补充文档/注释，不改变行为
- **严重程度（中）**: 正确性不受影响，但设计可读性存在 gap，增加维护风险

### DS-02-未修复-低-_is_terminal_status 终态扩展影响所有 Slice 调用方

- **入口/函数**: `_is_terminal_status()` 在 `tests/host/test_host_production_stress.py:1873`
- **文件(行号)**: `tests/host/test_host_production_stress.py:1881-1886`
- **输入场景**: 任何调用 `_is_terminal_status()` 的代码路径
- **实际分支**: 函数从 S/F/C 终态集合扩展为 S/F/C/LOST
- **预期行为**: Slice 4 新增 LOST 作为终态，但 Slice 2/3 不产生 LOST 运行，修改应该对已有测试无影响
- **实际行为**: 修改影响 Slice 2/3 的以下调用点：
  - `_wait_run_terminal` (line 1596): 现在会在 LOST 状态上终止等待（Slince 3 不产生 LOST，无实际影响）
  - `Slice3WatchDiagnostics.public_snapshots_terminal` (line 483): LOST 现在被视为终态
  - `Slice3WatchDiagnostics.disconnect_gap_terminal_truth_ok` (line 560): LOST 现在被视为终态
  - `Slice2StressDiagnostics.scheduler_drained` — 间接通过 terminal observation 但不直接使用此函数
- **直接证据**: `test_host_production_stress.py:1882` 新增 `RunStatus.LOST` 到终态集合
- **影响**: 当前无实际影响（Slince 2/3 不产生 LOST），但这是一个跨 Slice 的语义变更。如果 Slice 3 的 `_wait_run_terminal` 意外等待到一个 LOST 运行，它将静默接受而非超时报错，可能掩盖 bug
- **建议改法和验证点**:
  - 考虑新增一个 slice-scoped 函数（如 `_is_slice4_terminal_status`）或在 docstring 中说明修改原因和影响范围
  - 验证点：确认 Slice 2/3 测试在修改前后行为一致
- **修复风险（低）**: 可接受当前状态，因 LOST 确实是 Host public 终态
- **严重程度（低）**: 语义正确但跨 Slice 影响未显式论证

### DS-03-未修复-低-模块间常量重复定义

- **入口/函数**: 模块级常量定义
- **文件(行号)**:
  - `tests/host/stress_support.py:100-103`: `_HOST_DB_FILENAME`, `_EVENT_TYPE_RUN_SUCCEEDED`, `_EVENT_TYPE_RUN_FAILED`, `_EVENT_TYPE_RUN_CANCELLED`
  - `tests/host/test_host_production_stress.py:108-112`: 同名常量重复定义
- **输入场景**: 当 event type 常量或 DB filename 需要修改时
- **实际分支**: 两处独立定义相同的魔术字符串
- **预期行为**: 常量应从单一模块导出，避免重复定义
- **实际行为**: `_HOST_DB_FILENAME`, `_EVENT_TYPE_RUN_SUCCEEDED`, `_EVENT_TYPE_RUN_FAILED`, `_EVENT_TYPE_RUN_CANCELLED` 在两个模块中以不同的 module-private 名字重复定义
- **直接证据**:
  - `stress_support.py:100`: `_HOST_DB_FILENAME = "host.sqlite3"`
  - `test_host_production_stress.py:112`: `_HOST_DB_FILENAME = "host.sqlite3"`
  - `stress_support.py:101`: `_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"`
  - `test_host_production_stress.py:108`: `_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"`
- **影响**: 低——当前值一致，且这些常量按设计是模块私有的（`_` 前缀）。但未来修改时需要同步两处，容易遗漏
- **建议改法和验证点**:
  - 测试文件从 `stress_support` 导入这些常量（如果同意放宽模块私有性），或将重复定义的常量各自加注释说明为何不共享
  - 验证点：确认两个模块中的值一致
- **修复风险（低）**: 将模块私有常量提升为可导入常量需要评估 API 暴露面
- **严重程度（低）**: 维护性风险，不影响正确性

### DS-04-未修复-低-verify_lane_released 的 db_path 硬编码依赖约定

- **入口/函数**: `verify_lane_released()` 在 `tests/host/stress_support.py:1029`
- **文件(行号)**: `tests/host/stress_support.py:1088`
- **输入场景**: Host 使用的 lane DB 路径与 `verify_lane_released` 中硬编码的路径不一致时
- **实际分支**: `SQLiteLaneCoordinatorConfig(db_path=root_path / "lane.sqlite3")` — 硬编码路径
- **预期行为**: `verify_lane_released` 使用的 lane DB 路径应与 Host 使用的路径一致
- **实际行为**: 路径硬编码为 `root_path / "lane.sqlite3"`，与 `public_smoke_support.py:856` (`lane_db_path=tmp_path / "lane.sqlite3"`) 约定一致。但该约定不是通过 `OpenHostOptions` 透明传递的——如果 smoke support 或 Host opener 变更 lane DB 路径，此函数将静默失效（连接到空 DB，永远 acquire 成功并返回 `True`）
- **直接证据**:
  - `stress_support.py:1088`: 硬编码 `db_path=root_path / "lane.sqlite3"`
  - `public_smoke_support.py:856`: 匹配约定 `lane_db_path=tmp_path / "lane.sqlite3"`
  - `verify_lane_released` 不从 `OpenHostOptions.lane_db_path` 读取路径
- **影响**: 当前无影响——路径约定一致。但未来如果 Host opener 的 lane DB 路径变更，此 diagnostic 将产生假阳性（返回 True 而实际 lane 未释放）
- **建议改法和验证点**:
  - 让 `verify_lane_released` 接受完整的 `OpenHostOptions` 或显式的 `lane_db_path` 参数，而非仅接受 `lane_name`
  - 或在 docstring 中明确说明路径约定依赖
  - 验证点：检查 `verify_lane_released` 连接的 DB 确实是 Host 使用的同一文件
- **修复风险（低）**: 接口变更需要同步调用方
- **严重程度（低）**: 维护性/健壮性风险，当前约定一致时不触发

### DS-05-未修复-低-read_host_instances stale 阈值为测试专用值，与生产不一致

- **入口/函数**: `read_host_instances()` 在 `tests/host/stress_support.py:977`
- **文件(行号)**: `tests/host/stress_support.py:110,992`
- **输入场景**: Host instance heartbeat 在真实时间中的位置
- **实际分支**: `stale_after = timedelta(seconds=_HOST_INSTANCE_STALE_AFTER_SECONDS)` → `1.0` 秒
- **预期行为**: stale 判断应使用与生产 liveness policy 一致或可解释的阈值
- **实际行为**: 使用 `1.0` 秒硬编码阈值判断 stale，该值与生产 Host liveness 的 heartbeat 间隔 / TTL 无关。Docstring 已声明这是测试诊断而非生产 truth，但如果生产 liveness 的行为变化（如 heartbeat 间隔调整），这个测试阈值可能产生误导性的 stale 判断
- **直接证据**: `stress_support.py:110`: `_HOST_INSTANCE_STALE_AFTER_SECONDS = 1.0`
- **影响**: 低——当前测试依赖 `start_and_crash_owner_for_stress` 显式调用 `force_owner_pid_missing_and_heartbeat_stale` 制造 stale 证据，所以阈值的具体值不影响 crash/recovery 子流的诊断。但如果未来测试增加了不依赖显式 stale 注入的场景，`1.0` 秒阈值可能在慢 CI 环境中产生不稳定的 stale 判断
- **建议改法和验证点**:
  - 在 `_HOST_INSTANCE_STALE_AFTER_SECONDS` 的注释中说明该阈值与生产 liveness policy 的关系以及选择依据
  - 验证点：确认 force_owner_pid_missing_and_heartbeat_stale 已使 heartbeat 足够旧，不依赖阈值大小
- **修复风险（低）**: 仅补充注释
- **严重程度（低）**: 当前不触发实际错误

## Open Questions

- 无

## Residual Risk

1. **RUN_LOST / HostEventKind.LOST mapping gap**: `HostEventKind` 和 `HostTerminalStatus` 当前没有 `LOST` 成员。`terminal_events_for_runs()` 因此不能为 `RUN_LOST` 构造 `StressTerminalObservation`。如果未来 Host public API 新增 `HostEventKind.LOST`，`terminal_events_for_runs` 应同步更新以覆盖 `RUN_LOST` 去重。当前实现通过计数比较间接覆盖，风险可控。

2. **verify_lane_released 错误路径未测试**: 如果 lane DB 为空（新 DB）、或 lane capacity 被占用，`verify_lane_released` 返回 `False`。但测试未曾验证 `False` 返回路径（例如在 Host 未 close 时调用 verify）。这不是 Slice 4 的范围，但意味着 `verify_lane_released` 的 `False` 分支在生产 stress 中未被覆盖。

3. **Clean close proof 的隐含假设**: Slice 4 测试在 close 时不保留 active run（所有 run 已 terminal），因此 clean close 后 reopen 无 recovery。这验证了"已 drain 的 Host close 不产生 spurious recovery"，但未覆盖"仍有 active run 时 close Host"的场景——该场景下 recovery 是预期行为。测试意图已明确（见 Codex review 注释），但代码中没有显式断言或注释说明为什么 close 前所有 run 必须 terminal。

4. **Stress 测试为非随机确定性测试，不覆盖 soak/fuzz**: 这是 Slice 4 计划中明确声明的范围限制。

## Review Conclusion

**PASS** — Slice 4 实现满足计划契约。所有 6 个 finding 严重程度均为"中"或"低"，无 correctness-breaking defects。

核心证明链（scheduler drain → liveness stale → handle cleanup → lane release → stream lost closeout → terminal dedupe）沿真实 Host public API 路径走读，每个 predicate 均有直接 durable 证据支撑。

Pyright 0 errors，stress suite 4/4 通过，相关回归测试无新增失败。
