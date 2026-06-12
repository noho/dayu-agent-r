# WU-RET-00 Slice 2 Fix — Codex

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: fix
- slice: Slice 2 — read-only storage usage report
- agent: AgentCodex
- artifact path: `docs/reviews/wu-ret-00-slice2-fix-codex.md`
- status: complete
- blocked: no

## Accepted Finding

- MiMo F01: `report_storage_usage` 是 Service-facing public API，DB/WAL `Path.stat()` 的非缺失类 `OSError` 不应以裸异常泄漏给调用方。

## 第一性原理判断

该问题真实存在且 fix 动机成立。底层 durable reader 的 `_file_size_bytes` 明确把 `FileNotFoundError` 视为 WAL 正常缺失并返回 0，同时透传其它 `OSError`，这属于底层诊断读取语义；但 `report_storage_usage(host)` 位于 Host public facade 边界，调用方应看到结构化 `HostApiError`，而不是文件系统裸异常。因此修复点应在 facade/public boundary，而不是改变 durable reader。

## 改动摘要

- `dayu/host/storage_maintenance.py`
  - 在 `report_storage_usage(host)` 中捕获 `OSError`。
  - 包装为 `HostApiError(code=HostApiErrorCode.INTERNAL_ERROR, retryable=False)`。
  - 使用 `raise ... from exc` 保留原始 DB/WAL stat 异常链。
  - 更新 docstring，明确 durable 读取失败或 DB/WAL 文件 stat 失败对 public caller 表现为 `HostApiError`。
- `tests/host/test_storage_usage_report.py`
  - 新增 public facade 测试，分别模拟 DB 与 WAL 路径 `Path.stat()` 抛出非缺失类 `PermissionError`。
  - 断言 public facade 抛 `HostApiError`、错误码为 `INTERNAL_ERROR`、`retryable=False`、`__cause__` 是原始 `OSError`。
  - 使用 pytest `monkeypatch` 局部替换 `Path.stat`，不留下全局 patch 残留。

## 验证结果

- `source .venv/bin/activate && pytest tests/host/test_storage_usage_report.py -q`
  - passed: `7 passed in 0.31s`
- `source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - passed: `28 passed in 1.71s`
- `source .venv/bin/activate && pyright dayu/host/storage_maintenance.py tests/host/test_storage_usage_report.py`
  - passed: `0 errors, 0 warnings, 0 informations`

## README 检查

- 已检查 `dayu/host/README.md` 的 Agent 更新约束。本次不新增 Host 能力或稳定接口说明，只修正已有 public facade 的错误映射，不需要更新。
- 已检查 `tests/README.md`。本次只在已有 `tests/host/test_storage_usage_report.py` 内补充 case，不新增测试层级或测试文件清单，不需要更新。

## 未覆盖风险

- 本 fix 未修改 durable `_file_size_bytes` 的底层 `OSError` 透传语义；该语义由 MiMo F06 接受并保留。
- 本 fix 不处理 controller 已拒绝为 blocking 的其它 review 项。
- 本 fix 不进入 Slice 3/4 范围：不扫描 artifact root，不 checkpoint，不删除文件或 SQLite row。
