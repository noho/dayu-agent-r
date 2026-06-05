# WU-TOOLS-01 Slice S1 Fix - AgentCodex

Gate: fix  
Work unit: WU-TOOLS-01  
Slice: S1 shared document foundations  
Agent: AgentCodex  
Date: 2026-06-05  
Status: fixed

## Scope

本 fix gate 仅处理 Controller 接受的窄范围文案问题，不进入 re-review gate，不提交 commit，不推送，不开 PR。

## Files Changed

- `dayu/documents/processors/registry.py`
- `docs/reviews/wu-tools-01-slice1-fix-codex.md`

## Exact Accepted Finding Fixed

- 已修复 `M1 / D3` 中被 Controller 接受的部分：`dayu/documents/processors/registry.py` 模块 docstring 原先称注册表用于“核心层可用”，该表述对迁移后的 `dayu.documents` 包不准确。
- 当前 wording 改为 documents 包默认共享的处理器注册表，保持语义定位在 documents package/default shared document processor 上。

## Rejected Or Deferred Findings Left Untouched

- 未重命名 `build_engine_processor_registry(...)`；该命名按 Controller 裁决延后处理，S1 继续保留 OLD function signatures。
- 未修改 `_doc_processor_factory.py` 中的 `_get_engine_processor_registry` 或 `_ENGINE_PROCESSOR_REGISTRY`。
- 未处理 deferred coverage/parity findings；这些由后续 WU-TOOLS-01 slices 和 final residual reconciliation 承接。
- 未处理 `PageAwareProcessor` `__all__` finding；Controller 已基于直接代码证据驳回。
- 未修改 provider、adapter、Host、Engine、Fins、Web 代码。

## Validation

已运行：

- `source .venv/bin/activate && pytest tests/documents tests/runtime/test_import_boundary.py tests/engine/contracts/test_import_boundary.py`：通过，18 passed。
- `source .venv/bin/activate && pytest tests/engine/test_import_boundary.py`：通过，4 passed。
- `source .venv/bin/activate && pyright`：通过，0 errors, 0 warnings, 0 informations。

## Remaining Residual Risks

- `WU-TOOLS-01-S1-R1`: documents test coverage / parity gaps 仍按 Controller 裁决延后到后续 WU-TOOLS-01 slices 和 final residual reconciliation。
- `WU-TOOLS-01-S1-R2`: `build_engine_processor_registry(...)` 的 OLD naming 仍保留，按 Controller 裁决由 post-migration cleanup 或显式后续设计决策处理。
