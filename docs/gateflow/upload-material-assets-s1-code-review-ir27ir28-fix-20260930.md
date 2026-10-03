# Upload material assets S1：I-R27／I-R28 修复记录

日期：2026-09-30。工作分支：`codex/upload-material-oracle`。

## 源码事实与语义 owner

- 总控在 `upload-material-assets-s1-code-review-adjudication-20260929.md` 接受 I-R27、I-R28，限定为冗余返回和测试说明漂移。
- `ValidatedFinsUploadFilingRequest.request` 与 `ValidatedFinsUploadMaterialRequest.request` 分别持有已验证 handoff 的原始请求；`ingestion_runtime.py::_raw_upload_request` 是从这两个 handoff 提取原始请求的投影 owner。修改前 `if` 两臂都执行 `return request.request`，因此分支收敛不改变返回对象、校验或异常。
- `test_fins_service_runtime.py::test_production_runner_parser_callsites_use_explicit_source_kind` 的断言已要求 filing 两处、material 一处、总计三处；只有 docstring 写成“四个”。测试自身拥有此说明。

## 改动

1. `dayu/fins/ingestion_runtime.py`：`_raw_upload_request` 收敛为单次 `return request.request`，Args 改为 filing 或 material 的 validated handoff。
2. `tests/fins/test_fins_service_runtime.py`：parser callsite 的 docstring 将“四个”改为“三个”；断言不变。

未修改其它生产行为、裁决总表或 queue；未暂存、提交或推送。`dayu/fins/README.md` 的职责是稳定架构及公共契约，`tests/README.md` 记录测试分层和运行方式；本次没有触发其内容更新。

## 验证

- `source .venv/bin/activate && python -m pytest tests/fins/test_fins_service_runtime.py tests/fins/test_fins_ingestion_runtime.py -q`：exit 0，**446 passed，3 warnings**（第三方 edgar 弃用提示）。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：exit 0，**0 errors、0 warnings、0 informations**；另有 pyright 新版本提示。
- `git diff --check`：exit 0，无空白错误。
- 预检 canary 文件原文：`gpt-6-sol-ebac7635`。

## 检查过程中的非零命令

- `rg -n 'I-R27|I-R28|upload-material-assets|ingestion_runtime' /Users/leo/.codex/memories/MEMORY.md`：exit 1，记忆索引无匹配；随后直接读取本工作树裁决文件并定位 I-R27／I-R28，未依赖记忆结论。
- `ls -l AGENTS.md dayu/AGENTS.md dayu/fins/AGENTS.md tests/AGENTS.md tests/fins/AGENTS.md docs/AGENTS.md docs/gateflow/AGENTS.md`：exit 1，列出的子目录 AGENTS.md 不存在；根目录 `AGENTS.md` 存在且已读取，用户给出的项目约束亦已遵守。

## 风险与边界

这两项只改变实现冗余和测试说明，不应产生运行时行为变化。验证限于指定的 service／ingestion runtime 测试和全范围静态类型检查；未重跑全仓测试或覆盖率。工作树原有其它暂存与未暂存改动保持原状，本记录不对其验收或归因。
