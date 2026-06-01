# WU-STRESS-01 Slice 1 Code Review

## Gate

- **Gate**: code review
- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Review slice**: Slice 1 — Stress marker、默认排除、summary/helper 基础
- **Reviewer role**: AgentMiMo code review specialist
- **Review date**: 2026-06-01

## Reviewed Target

当前工作区未提交的 Slice 1 diff，涉及以下文件：

- `pyproject.toml`
- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`
- `tests/README.md`
- `docs/reviews/wu-stress-01-implementation-slice1-codex-20260601.md`（implementation artifact）

## Conclusion

**PASS**

Slice 1 实现完整、正确、类型安全，默认排除策略可靠，哨兵测试有效。无 blocking finding。

## Findings

无 finding。

## Detailed Review Notes

### 1. Default addopts 排除策略

`pyproject.toml:138` 设置 `addopts = "-m 'not stress'"`。验证结果：

- `pytest tests/host/test_package_exports.py tests/host/test_host_production_stress.py -q` → `10 passed, 1 deselected`，stress 哨兵被正确排除。
- `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q` → `1 passed`，显式命令可靠运行 stress。
- `pytest --collect-only tests/host/test_host_production_stress.py -q` → exit code 5，`no tests collected (1 deselected)`，默认排除生效。
- `pytest -o addopts="" --collect-only tests/host/test_host_production_stress.py -q` → `1 test collected`。

显式 stress 命令使用 `-o addopts=""` 先清空默认 addopts，再用 `-m stress` 精确选择，避免 `-m stress` 与默认 `-m 'not stress'` 组合歧义。方案正确。

### 2. stress_support.py 类型与边界

- **无弱类型**：无 `Any`、`object`、裸 `dict` / `list` 注解。所有签名有完整参数类型和返回值类型。
- **封闭失败边界**：`StressFailureBoundary` 使用 `TypeAlias = Literal[...]`，封闭集合，Python 3.11 兼容。
- **summary JSON 值类型**：`StressSummaryJsonValue` 使用封闭 `TypeAlias = str | int | bool | tuple[int, ...] | None`，不引入 `Any`。
- **中文 docstring**：所有模块级 class、dataclass、函数均有完整中文 docstring，包含参数、返回值、异常说明。
- **Host public boundary**：只从 `dayu.host` 导入 `AttemptDispatchSnapshot`、`HostEventKind`、`HostTerminalStatus`、`LocalEngineWorker`、`LocalEngineWorkerFactory`、`LocalWorkerHandle`、`OpenHostOptions`，均为 `dayu.host.__all__` 白名单内的公共符号。不导入 `dayu.engine`、`dayu.runtime`、`dayu.service`、`dayu.ui`、`dayu.fins`。
- **`from tests.host.public_smoke_support`** 导入 `deterministic_runner_spec` 和 `open_host_options`，是测试层内部复用，不违反分层约束。

### 3. DeterministicStressWorkerFactory / Worker / Handle 协议合规

- `DeterministicStressWorkerFactory.create_worker(snapshot) -> LocalEngineWorker`：签名匹配 `LocalEngineWorkerFactory` 协议。
- `DeterministicStressWorker.accept(snapshot, request) -> LocalWorkerHandle`：签名匹配 `LocalEngineWorker` 协议。
- `DeterministicStressWorkerHandle` 实现 `local_worker_id`（property）、`events()`（AsyncIterator）、`close()`（async）、`on_cancel(reason)`：签名匹配 `LocalWorkerHandle` 协议。
- `events()` 正确处理五种 `StressWorkerBehavior`：`FINAL` → yield final、`FAILED` → yield failed、`BLOCKING_FINAL` → await release + yield final、`STREAM_EXCEPTION` → raise RuntimeError、`CLEAN_EOF` → return（空流）。CLEAN_EOF 通过 fall-through `return` 实现，语义正确。

### 4. 哨兵测试有效性

`test_host_production_stress.py`:

- `pytestmark = pytest.mark.stress` 正确标记整个模块。
- `test_stress_marker_summary_contract` 使用 `@pytest.mark.timeout(5)`，超时预算合理。
- 测试验证：`terminal_duplicate_count` 对同 run_id 重复观测返回 1，`terminal_dedupe_ok` 返回 False；构造 `HostStressSummary` 并通过 `summary_to_json` 检查所有 `_SUMMARY_JSON_FIELDS` 存在；`assert_summary_ok` 通过。
- 使用 `record_property` 记录 summary JSON，符合 plan 中 `record_property("host_stress_summary", ...)` 约定。

### 5. tests/README.md 同步

- 记录了默认 pytest 排除 stress 的行为。
- 记录了显式 stress 命令 `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q`。
- 记录了 stress summary 字段约定与 failure boundary 封闭语义。
- 只描述当前已存在的事实，不写未来计划。符合 README 职责边界。

### 6. Slice 范围控制

- 只修改了 plan 中 Allowed Implementation Files 列出的四个文件（加 implementation artifact）。
- 未修改任何生产代码（`dayu/host/**`、`dayu/engine/**` 等）。
- 未实现 Slice 2-5 的 crash/recovery/watch/scheduler/liveness 场景。
- `stress_support.py` 中的 `build_stress_open_host_options` 为后续 slice 提供了 option builder 基础，但不触发任何生产行为。

### 7. pyright 验证

`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。无新增或扩散报错。

## Open Questions / Residual Risk

1. **`_NOW` 固定时间戳**：`stress_support.py:72` 使用 `datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)` 作为所有 EngineEvent 的 `occurred_at`。这是确定性测试的合理选择，但后续 slice 若需要区分不同事件的时间顺序，可能需要 per-event 可配时间戳。当前不构成问题。

2. **`wait_accepted` 只等待至少一次**：`DeterministicStressWorkerFactory.wait_accepted` 只等待 `_accepted_event`（至少一次 accepted）。后续 slice 若需等待指定 run_id 或指定数量的 accepted，需在不破坏现有契约的前提下扩展。Plan 已记录此 residual risk。

3. **Summary JSON 字段完整性**：当前 `_SUMMARY_JSON_FIELDS` 元组包含 12 个字段，与 `HostStressSummary` dataclass 的 12 个字段一一对应。后续 slice 若需附加诊断字段，应优先新增 typed diagnostic 类型，避免把显式参数塞入 extra payload。

## Controller Decision Status

**APPROVED** — 无需 controller 裁决。Slice 1 实现完整通过 review gate，可进入后续 slice。

## Artifact Path

`docs/reviews/wu-stress-01-code-review-slice1-mimo-20260601.md`
