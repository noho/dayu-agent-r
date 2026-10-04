# Upload material assets S1：I-R29 修复记录

日期：2026-09-30。工作分支：`codex/upload-material-oracle`。

## 动机与语义 owner

总控在 `docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md` 接受 I-R29。`dayu/fins/service_runtime.py` 中 `run_upload` 的唯一 material 调用传入 `ticker=normalized.canonical`，但私有方法 `_run_material_upload` 的方法体不读取该形参，仅用 `normalized.market` 选择 pipeline，并把同一 validated handoff 交给 pipeline。这个形参暗示 runner 的 canonical ticker 会生效，实际没有生效链；问题属于 runner 装配边界的死参数。下游 pipeline 对 ticker 的归一化仍由下游自行负责。

## 改动

只在 `dayu/fins/service_runtime.py` 删除 `_run_material_upload` 调用中的死实参、私有方法形参和对应中文 Args 说明。保留 `normalized.market` 路由、validated handoff 和 pipeline 行为。未改动其它生产文件、测试、README、裁决总表或 queue；未暂存、提交、推送或创建 PR。

`dayu/fins/README.md` 的更新边界是稳定架构和公共契约；本次私有死参数删除不改变其内容。

## 验证

- `source .venv/bin/activate && python -m pytest tests/fins/test_fins_service_runtime.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py -q`：exit 0，81 passed，3 个第三方 edgar 弃用警告。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：exit 0，0 errors、0 warnings、0 informations；另有新版 pyright 提示。
- `git diff --check`：exit 0。
- 预检 canary 文件原文：`gpt-6-sol-023f3ca8`。

## 风险与边界

本次只删除无消费的私有参数，预期不改变运行时行为。验证限于指定的三个测试文件和全范围 pyright；未重跑全仓测试。工作树原有其它暂存、未暂存和未跟踪内容均保持原状，本记录不对其验收或归因。

预检中查询记忆索引的 `rg` 因无匹配返回 exit 1；该查询未用于判断根因，根因由本工作树源码及总控裁决直接确认。
