# WU-TOOLS-01-F01-02 Slice 5 Fix

执行者：AgentCodex

日期：2026-06-08

## Scope

本次只处理 controller accepted finding `S5-F1`。MiMo 的 TypeGuard 风格 finding 已被 controller 判定为 rejected-with-reason，未处理。

Allowed files：

- `tests/fins/test_fins_ingestion_tools.py`
- `docs/reviews/wu-tools-01-f01-02-slice5-fix-codex.md`

## Motivation

`test_ingestion_tool_schemas_hide_host_internal_fields` 原本只通过 `schema_text` 做全文检查，能够间接阻止 Host 内部治理字段泄漏，但没有直接锁定 LLM-facing JSON Schema 的参数入口。真实风险点是 `definition.schema.function.parameters.properties` 和 `definition.schema.function.parameters.required` 被投影给模型，因此显式断言这两个位置不含 `execution_context` / `cancellation_token` 是成立且必要的窄修复。

## Changes

- 在 `tests/fins/test_fins_ingestion_tools.py::test_ingestion_tool_schemas_hide_host_internal_fields` 中，对每个 Fins awaiting tool definition 读取：
  - `definition.schema.function.parameters.properties`
  - `definition.schema.function.parameters.required`
- 显式断言 `execution_context` 和 `cancellation_token` 均不在 `properties` 与 `required` 中。
- 保留既有 `schema_text` 全文检查，继续覆盖 `tool_call_id`、`digest`、`cursor`、`raw job record`、`Host` 等 Host 内部字段。
- 未修改生产代码、其它测试或 control doc。

## README Decision

- 修改触发 `tests/` README 检查；已读取 `tests/README.md`。
- `tests/README.md` 已记录 `tests/fins/test_fins_ingestion_tools.py` 覆盖 download / preprocess 工具 schema 不暴露 Host 内部治理字段。本次仅在已有测试职责内补充显式 `properties` / `required` guard，不新增测试层级、测试目录、运行方式或维护约定，因此不更新。
- 未修改 `dayu/fins/`、分层关系、装配方式或 Host / Engine public contract，因此不触发 `dayu/fins/README.md` 或 `dayu/README.md` 更新。

## Validation

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q
```

结果：PASS，69 passed。仅有第三方 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
```

结果：PASS，44 passed。仅有第三方 `edgar` deprecation warnings。

```bash
source .venv/bin/activate && pyright
```

结果：PASS，0 errors / 0 warnings / 0 informations。pyright 提示存在新版本 `1.1.410`，当前环境版本为 `1.1.409`，不影响本次验证。

```bash
git diff --check
```

结果：PASS，无输出。

## Remaining Risks

- 本次只加深 Fins awaiting schema test guard，不改变工具 schema 生成逻辑或 Host injection contract。
- Awaiting accept 两阶段启动、同步 I/O 不可抢占、legacy adapter cancellation outcome 投影等残余风险仍按 closeout review controller adjudication 保持 deferred，不在本 fix gate 处理。
