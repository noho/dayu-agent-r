# WU-STRESS-01 Slice 1 Implementation Artifact

## Scope

- Role: AgentCodex, WU-STRESS-01 implementation specialist.
- Slice: Slice 1 Stress marker、默认排除、summary/helper 基础。
- Gate constraints: 未启动 gateflow；未 commit；未 push；未创建 PR；未修改生产代码。

## Changed Files

- `pyproject.toml`
- `tests/host/stress_support.py`
- `tests/host/test_host_production_stress.py`
- `tests/README.md`
- `docs/reviews/wu-stress-01-implementation-slice1-codex-20260601.md`

未发现需要保留并报告的非本 slice 既有变更；`git status --short` 只显示上述本 slice 文件。

## Implemented Plan Items

- 在 `pyproject.toml` 注册 `stress` marker，并设置默认 `addopts = "-m 'not stress'"`。
- 新增 `tests/host/stress_support.py`：
  - `HostStressSummary`。
  - 封闭 `StressFailureBoundary`。
  - `StressTerminalObservation` 与 `terminal_duplicate_count` / `terminal_dedupe_ok` 消费路径。
  - `summary_to_json` 与 `assert_summary_ok`。
  - `compute_watch_lag`，docstring 明确 fresh short read transaction / point-in-time diagnostic 语义边界。
  - `DeterministicStressWorkerFactory` / worker / handle，支持 final、failed、blocking final、stream exception、clean EOF 和基础 close/cancel/accepted 诊断。
  - `build_stress_open_host_options`，复用 `tests.host.public_smoke_support.open_host_options` 与 deterministic runner spec。
- 新增 `tests/host/test_host_production_stress.py`：
  - 模块级 `pytestmark = pytest.mark.stress`。
  - `test_stress_marker_summary_contract` 哨兵测试，验证 summary JSON 字段完整、terminal duplicate helper 可用，并使用 `pytest.mark.timeout(5)`。
- 更新 `tests/README.md`：
  - 记录默认 pytest 排除 stress。
  - 记录显式 stress 命令。
  - 记录 stress summary 字段约定与 failure boundary 封闭语义。

## Validation

- `source .venv/bin/activate && pytest --markers`
  - PASS。
  - 输出包含 `stress` marker。
  - 输出包含 `timeout(timeout, method=None, func_only=False, disable_debugger_detection=False)` marker。
- `source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_host_production_stress.py -q`
  - PASS: `10 passed, 1 deselected in 0.33s`。
  - 说明默认 `addopts` 排除了 stress 哨兵，非 stress package export 测试正常运行。
- `source .venv/bin/activate && pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q`
  - PASS: `1 passed in 0.22s`。
  - final docstring adjustment 后重跑仍 PASS: `1 passed in 0.22s`。
- `source .venv/bin/activate && pytest --collect-only tests/host/test_host_production_stress.py -q`
  - EXPECTED DEFAULT EXCLUSION: `no tests collected (1 deselected) in 0.19s`。
  - pytest 对单文件全量 deselect 返回 exit code 5；该输出证明默认 marker expression 生效，没有误收集 stress test。
- `source .venv/bin/activate && pytest -o addopts="" --collect-only tests/host/test_host_production_stress.py -q`
  - PASS: 收集到 `tests/host/test_host_production_stress.py::test_stress_marker_summary_contract`，`1 test collected in 0.19s`。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - PASS: `0 errors, 0 warnings, 0 informations`。
  - final docstring adjustment 后重跑仍 PASS: `0 errors, 0 warnings, 0 informations`。

## CI / Regular Pytest Configuration Inspection

- `.github/**`: 未发现目录或文件。
- `.gitlab-ci.yml`: 未发现。
- `tox.ini`: 未发现。
- `noxfile.py`: 未发现。
- `Makefile`: 未发现。
- `pyproject.toml`: 只发现 pytest 依赖声明与 `[tool.pytest.ini_options]`，未发现 CI pytest 命令。

结论：未发现对应 CI pytest 配置。当前仓库若直接运行 `pytest` 或 `pytest tests/...`，会继承默认 `addopts = "-m 'not stress'"` 并排除 stress；显式 stress 运行需要使用 `-o addopts="" -m stress`。

## Docs Decision

- 已更新 `tests/README.md`，因为本 slice 修改测试运行方式、marker 和 summary 字段约定。
- 未更新根目录 `README.md`，因为用户手册入口、CLI、trace/render 或项目级配置入口未变化。
- 未更新 `dayu/README.md` 或 `dayu/host/README.md`，因为分层关系、Host public contract、状态机和生产机制未变化。

## Plan Gaps

- 默认 `pytest --collect-only tests/host/test_host_production_stress.py -q` 在 stress 文件被全部 deselect 时返回 pytest exit code 5。计划要求记录 collected / deselected / selected 摘要；本实现记录该行为，不通过生产代码或自定义 plugin 改变 pytest 语义。

## Residual Risks

- Slice 1 只建立 marker、默认排除和 helper 基础；未实现 Slice 2-5 的 crash/recovery/watch/scheduler/liveness 实际 stress 场景。
- `DeterministicStressWorkerFactory.wait_accepted` 当前只等待至少一次 accepted；后续 slice 若需要等待指定数量或指定 run，需要在允许范围内扩展 helper。
- summary JSON helper 当前覆盖固定字段；后续 slice 若需要附加诊断，应优先另建 typed diagnostic 类型，避免把显式参数塞入 extra payload。

## Stop Status

- 未触发 stop condition。
- 默认排除策略已生效。
- `pytest-timeout` marker 已可见。
- pyright 无新增或扩散报错。
