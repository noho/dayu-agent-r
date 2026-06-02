# WU-LAYER-02 Slice 1 Implementation Report

## Changed Files

- `dayu/runtime/diagnostic_text.py`
  - 新增层中立 diagnostic 文本 primitive，提供敏感值检测、局部 value 脱敏和有界截断。
  - 仅依赖标准库 `re` 与 `typing.Final`，不 import Host / Engine / Service / UI / Fins。
  - Bearer 使用 word-boundary；`authorization` / `password` / `secret` / `token` 仅在后接 `:` 或 `=` 时命中；API key 类字段覆盖空格、下划线、短横线、冒号与等号形式。
  - `redaction_marker` 通过 callable replacement 字面替换，避免 `re.sub` replacement group reference 解释。
- `dayu/runtime/__init__.py`
  - 仅更新 runtime 能力清单 docstring，加入 `diagnostic_text`；包根不 re-export。
- `tests/runtime/test_diagnostic_text.py`
  - 新增 runtime helper 直接测试，覆盖 detection、false-positive guard、局部脱敏、marker 字面替换、truncate no-op / exact-boundary / 超限 / 空字符串、redact+truncate 组合、幂等性和非法参数。
- `tests/runtime/test_weak_typing_guard.py`
  - 将 `diagnostic_text.py` 加入显式 helper 覆盖集合；未放宽弱类型扫描。
- `dayu/README.md`
  - 在 `dayu.runtime` 稳定能力清单中补充 diagnostic 文本脱敏与有界截断说明。
- `tests/README.md`
  - 在 `tests/runtime/` 分层说明中补充 diagnostic text helper 测试事实。

## README / Doc Sync Decision

- `dayu/README.md`: 已更新。新增 runtime capability 属于开发手册总览职责范围。
- `tests/README.md`: 已更新。新增 runtime 测试文件属于测试分层说明职责范围。
- 根目录 `README.md`: 未更新。用户使用入口、CLI 命令、配置入口和常用工作流未改变。
- `dayu/engine/README.md`: 未更新。本 Slice 尚未迁移 Engine 调用，Engine public contract 未改变。
- `dayu/host/README.md`: 未更新。本 Slice 尚未迁移 Host 调用，Host public contract、状态机和事件语义未改变。

## Validation Output Summary

- `source .venv/bin/activate && pytest -q tests/runtime/test_diagnostic_text.py tests/runtime/test_weak_typing_guard.py tests/host/test_import_boundary.py`
  - `47 passed in 1.25s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `0 errors, 0 warnings, 0 informations`
  - pyright 额外提示存在新版本 `v1.1.410`，不影响本次类型检查结果。

## Residual Risks / Uncovered Areas

- 本 Slice 只建立 runtime primitive，尚未迁移 `dayu.engine.agent` 或 `dayu.host.compaction_operation` 的调用点；业务层行为闭环属于后续 Slice 2 / Slice 3。
- Runtime regex 只覆盖当前计划列出的 value-bearing diagnostic text pattern，不处理 provider JSON diagnostic payload、Host durable digest、tool trace digest 或业务字段语义。
- API key 空格写法按计划允许 `api key <value>` 命中；这会比强制 assignment operator 更积极，但该行为已由计划明确要求并由测试锁定。

## Completion Status

WU-LAYER-02 Slice 1 completed locally. 未 commit，未 push。
