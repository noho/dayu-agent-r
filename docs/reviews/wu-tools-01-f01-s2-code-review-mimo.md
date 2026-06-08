# Code Review

## Scope

- Mode: current changes
- Branch: host-wu-tools-01-f01
- Base: main
- Output file: docs/reviews/wu-tools-01-f01-s2-code-review-mimo.md
- Included scope: dayu/fins/ingestion_runtime.py, dayu/fins/service_runtime.py, tests/fins/test_fins_ingestion_runtime.py, dayu/fins/README.md, tests/README.md
- Excluded scope: docs/host/issues-implementation-control.md (controller bookkeeping background only)
- Parallel review coverage: 无

## Findings

### 001-未修复-低-_save_failed_from_exception 吞噬二次异常可能导致孤儿 job 状态

- **入口/函数**: `FinsIngestionRuntime._save_failed_from_exception`
- **文件(行号)**: dayu/fins/ingestion_runtime.py:1226-1246
- **输入场景**: 后台 preprocess pipeline 执行期间发生异常，且 `_save_failed` 本身也失败（如磁盘满、job record 文件被外部删除）
- **实际分支**: 外层 `except Exception: return` 静默吞噬二次异常
- **预期行为**: 至少记录诊断信息，使运维可观测到 job 状态不一致
- **实际行为**: 方法直接返回，job 留在 `RUNNING` 或 `QUEUED` 非终态，成为无法被后续操作推进的孤儿状态
- **直接证据**:
  - 第 1240-1246 行：`try: ... except Exception: return`
  - 如果 `job_store.read_job(job_id)` 抛出 `OSError`（文件被删除），job 留在非终态
  - 如果 `_save_failed(...)` 抛出 `OSError`（磁盘满），job 留在非终态
- **影响**: 极端情况下 job 状态不一致，可能成为孤儿；但 job store 使用文件系统锁和 atomic replace，正常运行下不会触发
- **建议改法和验证点**: 在 `except Exception` 中添加 `logging.exception(...)` 记录诊断信息，不改变异常收口行为；验证日志输出包含 job_id 和异常类型
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无

## Residual Risk

- `start_download` 仍只创建 queued record，不执行真实 download pipeline（covered by later approved slice S3）
- processed `financials` 当前写入为 `None`，因为现有 processor protocol 没有统一结构化 financials 生产方法（assigned to later work unit）
- 测试中 `_wait_terminal` 使用 5 秒超时和 20ms 轮询间隔，在 CI 环境极端负载下可能不足，但当前 29 passed 验证通过

## Scope / Validation Notes

- 已运行：`source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q` -> 29 passed
- 已运行：`source .venv/bin/activate && python -m pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py` -> 0 errors, 0 warnings, 0 informations
- 已读取：accepted plan (docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md) S2 expected assertions 全部覆盖
- 已读取：implementation report (docs/reviews/wu-tools-01-f01-s2-implementation-codex.md)
- 已读取：dayu/fins/README.md, tests/README.md 同步内容准确

## Verdict

pass-with-findings
