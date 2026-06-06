# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/wu-tools-01
- Base: main (uncommitted workspace diff)
- Output file: docs/reviews/wu-tools-01-slice2-code-review-mimo.md
- Included scope: WU-TOOLS-01 Slice S2 — `dayu/tools/_legacy_adapter/` (7 new files), `dayu/runtime/config_loader.py` (config pass-through), `dayu/service/host_assembly.py` (config mapping), `dayu/config/tool_discovery.json` (provider config examples), `tests/tools/test_legacy_tool_adapter.py`, `tests/runtime/test_config_loader.py`, `tests/service/test_host_assembly.py`, `dayu/README.md`, `dayu/config/README.md`, `tests/README.md`
- Excluded scope: `dayu.tools` business tool implementations (S3/S4/S5), Host/Engine runtime changes, Doc/Fins/Web provider parsing
- Parallel review coverage: 无

## Findings

### 1-未修复-低-adapt_collected_tool 与 adapt_collected_tools 对 fetch_more 的处理语义不一致

- **入口/函数**: `adapt_collected_tool()` 和 `adapt_collected_tools()` in `dayu/tools/_legacy_adapter/definition_adapter.py`
- **文件(行号)**: `definition_adapter.py:311` (adapt_collected_tool) vs `definition_adapter.py:339` (adapt_collected_tools)
- **输入场景**: 调用方意外传入 name="fetch_more" 的 `CollectedLegacyTool`
- **实际分支**: `adapt_collected_tool` 在 `declaration.name == "fetch_more"` 时 raise `ValueError`；`adapt_collected_tools` 在同一条件下 `continue` 静默跳过
- **预期行为**: 两种入口对同一约束违反应有一致的失败语义——要么都 fail fast（推荐），要么都静默过滤并记录。当前一个 raise 一个 skip 会让调用方困惑：单工具适配失败会中断流程，批量适配则悄悄吞掉
- **实际行为**: `adapt_collected_tools` 的 `continue` 不产生任何日志或错误信号
- **直接证据**: `definition_adapter.py:311` `raise ValueError("legacy adapter must not expose fetch_more as a business tool")` vs `definition_adapter.py:339` `if declaration.name == _RESERVED_FETCH_MORE_TOOL_NAME: continue`
- **影响**: 若 provider 意外声明了 fetch_more，批量路径会静默丢弃而单工具路径会报错。生产环境中静默丢弃可能导致调试困难
- **建议改法和验证点**: 统一为 `adapt_collected_tools` 中对 fetch_more 也 raise `ValueError`（与单工具路径一致），或在两处都使用 `logging.warning` + skip 并在测试中验证。验证点：确认 `test_fetch_more_is_not_emitted_as_business_tool` 在修改后仍通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-SERIAL_PER_PROVIDER 并发策略与通用异常投影路径缺少测试覆盖

- **入口/函数**: `adapt_collected_tools()` 中 `LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER` 分支；`project_legacy_exception()` 中 `RuntimeError` / 通用 `Exception` fallback 分支
- **文件(行号)**: `definition_adapter.py:346-347` (SERIAL_PER_PROVIDER lock 分支), `definition_adapter.py:287-294` (通用异常 fallback)
- **输入场景**: (a) 多工具共享 provider_lock 的并发调用 (b) 迁移函数抛出非业务 RuntimeError
- **实际分支**: (a) `SERIAL_PER_PROVIDER` 分支使用 `provider_lock` 共享锁 (b) 通用 `Exception` 分支返回 `execution_error` 错误码
- **预期行为**: 测试应证明 (a) 共享锁确实阻止跨工具并发 (b) 非业务异常被正确投影为 `execution_error`
- **实际行为**: 当前测试只覆盖 `SERIAL_PER_TOOL` 和 `CONCURRENT_AFTER_EVIDENCE`（隐式，通过不传 lock），未覆盖 `SERIAL_PER_PROVIDER` 共享锁行为；异常投影只覆盖 `ToolBusinessError`、`ToolArgumentError`、`FileAccessError`、`FileNotFoundError`
- **直接证据**: `test_legacy_tool_adapter.py` 中无 `SERIAL_PER_PROVIDER` 相关测试用例；`test_legacy_exceptions_project_to_current_failures` 只测试 `ToolBusinessError`
- **影响**: 两个已实现的代码路径没有测试证明其行为正确。`SERIAL_PER_PROVIDER` 共享锁若存在 bug（如 lock 未正确共享），在集成测试前不会被发现
- **建议改法和验证点**: 补充 (a) `SERIAL_PER_PROVIDER` 测试：两个不同 name 的工具共享 provider_lock，并发调用时验证无并发进入 (b) 通用异常测试：传入 `RuntimeError("boom")` 验证返回 `execution_error` 错误码
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- `dayu.tools._legacy_adapter` 当前没有实际的 Doc/Fins/Web provider 注册函数调用 collector；集成级验证需等 S3/S4/S5 实现具体 provider 后完成。
- `ToolPathValidationPolicy` 的 `file_path_params` 可以覆盖 `CollectedLegacyTool.file_path_params`，当前设计允许策略侧声明比工具自身更宽的路径参数集合。若未来 provider 策略配置出错，可能对非路径参数做路径校验。当前风险低，因为调用链上策略由 provider 显式构造。
- `tool_contracts.py` 中 `DupCallSpec` 是 S2 收集但不投影的 metadata；其实际消费（重复调用治理）留待后续 slice。

## Verdict

**pass-with-findings**

两项 low severity findings 均不阻塞 S2 slice commit：

1. `fetch_more` 处理语义不一致是设计选择差异，非 correctness defect。批量路径的静默跳过在当前使用场景下安全（fetch_more 名称碰撞概率极低），但建议后续 slice 统一语义。
2. 测试覆盖缺口是 maintainability 风险，不影响当前已测路径的正确性。建议在 S3/S4/S5 provider 集成测试时一并覆盖，或作为独立小补丁。

S2 实现符合所有关键约束：无 OLD registry/truncation/projection 导入或实例化，adapter 使用 current contracts only，ConfigLoader 保持层中立 JSON pass-through，无 Doc/Fins/Web 业务工具，reserved fetch_more 不作为业务工具输出，per-tool serialization 正确。

## Validation Commands Run

```bash
source .venv/bin/activate && pytest tests/tools/test_legacy_tool_adapter.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py -q
# Result: 89 passed

source .venv/bin/activate && pyright
# Result: 0 errors, 0 warnings, 0 informations

git diff --check
# Result: clean
```

全部验证通过，无新增或扩散报错。
