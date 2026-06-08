# Code Review

## Scope

- Mode: current changes
- Branch: host-wu-tools-01-f01
- Base: main
- Output file: docs/reviews/wu-tools-01-f01-s4-code-review-mimo.md
- Included scope: S4 实现的全部生产代码、测试、README 和 control doc 变更
- Excluded scope: docs/host/issues-implementation-control.md 仅作为 controller bookkeeping 背景
- Parallel review coverage: 无

## Findings

### S4-01-未修复-低-可维护性-download 与 preprocess 工具模块间辅助函数重复

- **入口/函数**: `download_tools.py:_awaiting_outcome_from_job_start`、`_failed_outcome`、`_optional_text_tuple`、`_required_text`、`_optional_bool` 与 `preprocess_tools.py` 同名函数
- **文件(行号)**: `dayu/fins/tools/download_tools.py:206-230`、`233-270`、`338-362`、`273-290`、`365-385` 与 `dayu/fins/tools/preprocess_tools.py:197-221`、`224-261`、`310-334`、`264-281`、`337-357`
- **输入场景**: 所有 download 和 preprocess 工具调用路径
- **实际分支**: 两个模块各自独立实现相同的 outcome 构造和参数解析逻辑
- **预期行为**: 按 AGENTS.md "重复逻辑必须抽取" 约束，共用函数应抽取到共享模块
- **实际行为**: `_awaiting_outcome_from_job_start`（25 行）、`_failed_outcome`（37 行）、`_optional_text_tuple`（25 行）、`_required_text`（18 行）、`_optional_bool`（21 行）共约 126 行近乎相同的代码在两个文件中各写一份
- **直接证据**: `download_tools.py:206-230` 与 `preprocess_tools.py:197-221` 的 `_awaiting_outcome_from_job_start` 函数体完全相同；`download_tools.py:233-270` 与 `preprocess_tools.py:224-261` 的 `_failed_outcome` 函数体完全相同；`download_tools.py:338-362` 与 `preprocess_tools.py:310-334` 的 `_optional_text_tuple` 函数体完全相同
- **影响**: 两份代码后续修改时可能漂移不一致，增加维护成本；当前行为正确，无 correctness 风险
- **建议改法和验证点**: 将 `_awaiting_outcome_from_job_start`、`_failed_outcome`、`_required_text`、`_optional_text_tuple`、`_optional_bool` 抽取到 `dayu/fins/tools/_ingestion_helpers.py`（或 `dayu/fins/tools/_common.py`），`download_tools.py` 和 `preprocess_tools.py` 从该模块导入。验证点：pyright 通过、现有测试全部通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### S4-02-未修复-低-测试覆盖-job 持久化失败路径和未预期异常路径未覆盖

- **入口/函数**: `FinsDownloadToolCallable.__call__`、`FinsPreprocessToolCallable.__call__`
- **文件(行号)**: `dayu/fins/tools/download_tools.py:72-87`、`dayu/fins/tools/preprocess_tools.py:73-88`
- **输入场景**: 当 `runtime.start_download`/`start_preprocess` 抛出 `OSError`（job record 写入失败）或未预期 `Exception`
- **实际分支**: `except OSError` 和 `except Exception` 分支
- **预期行为**: 测试应覆盖 `OSError` 返回 `ToolFailedOutcome(error="fins_download_start_failed")` 和泛 `Exception` 返回同 error code 的路径
- **实际行为**: `test_fins_ingestion_tools.py` 只覆盖参数错误路径（`ToolFailedOutcome(error="invalid_argument")`）和 happy path（`ToolAwaitingOutcome`）。`OSError` 和泛 `Exception` 两个 catch 分支没有被测试覆盖
- **直接证据**: `test_fins_ingestion_tools.py` 中只有 5 个测试函数：`test_tools_discovery_discovers_read_download_and_preprocess_independently`、`test_download_tool_returns_external_job_awaiting_outcome`、`test_preprocess_tool_returns_external_job_awaiting_outcome`、`test_tool_argument_error_returns_failed_outcome_before_job_creation`、`test_ingestion_tool_schemas_hide_host_internal_fields`。无任何 mock runtime 或注入失败的测试
- **影响**: 如果 `OSError` catch 分支的 error code 或 hint 文本被错误修改，当前测试不会发现。风险较低，因为 `FinsIngestionRuntime.start_download`/`start_preprocess` 本身的异常传播已在 S2 测试中覆盖
- **建议改法和验证点**: 可选补充：mock `runtime.start_download` 抛出 `OSError`，断言返回 `ToolFailedOutcome` 且 error 为 `fins_download_start_failed`；mock 抛出 `RuntimeError`，断言返回同 error code。验证点：测试通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

1. Host wait adapter / Service composition-root 接线未在 S4 中实现（属于 S5 范围）。Download/preprocess tool callable 正确返回 `ToolAwaitingOutcome`，但 Host acceptance 仍需后续接线。
2. 真实 SEC/CN/HK 网络下载 adapter 不在范围内。运行时在没有 adapter 时仍返回 unsupported-source 终态失败。
3. 未添加 status/cancel polling 工具（设计上由 Host 拥有 wait/resume/cancel 治理）。
4. `except Exception` catch-all 分支在 download_tools.py:80-87 和 preprocess_tools.py:81-88 未被测试覆盖，但该分支只是防御性兜底，runtime 已在 S2 中覆盖异常路径。

## Validation Notes

- 已运行 `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_storage_provider.py -q`：16 passed, 3 warnings
- 已运行 `pyright dayu/fins/tools/download_tools.py dayu/fins/tools/preprocess_tools.py dayu/fins/tools/download_provider.py dayu/fins/tools/preprocess_provider.py dayu/fins/tools/provider.py dayu/fins/tools/__init__.py`：0 errors, 0 warnings, 0 informations
- 已阅读 git diff main（4 files changed: `__init__.py`、`provider.py`、`test_fins_storage_provider.py`）和全部 untracked 新文件（`download_provider.py`、`download_tools.py`、`preprocess_provider.py`、`preprocess_tools.py`、`test_fins_ingestion_tools.py`）
- 已阅读 `dayu/fins/README.md` 和 `tests/README.md` 的 diff，确认只同步稳定事实，不写未来计划

## Verdict

pass-with-findings
