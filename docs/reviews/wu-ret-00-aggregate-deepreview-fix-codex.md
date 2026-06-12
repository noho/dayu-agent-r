# WU-RET-00 Aggregate Deepreview Fix - AgentCodex

## Scope

- 当前 gate: fix
- 修复对象: DS aggregate deepreview Finding 001 与 Open Question Q1 中已接受的低风险 docstring 问题
- 范围约束: 仅修改 public Protocol 与 async handle 的 `run_storage_maintenance` docstring，不改变行为代码、类型签名、公共 API 或测试断言

## Changed Files

- `dayu/host/api.py`
  - 将 `Host.run_storage_maintenance` docstring 从整体 dry-run 描述改为完整 maintenance 描述。
  - 明确默认 dry-run 不删除文件；当 `request.reclaim_orphan_artifacts=True` 时，会执行破坏性 orphan artifact 回收。
  - 将 raises 描述改为 maintenance 读取、扫描、checkpoint 或 orphan artifact 回收失败，移除“不支持 destructive reclaim 请求”的误导措辞。
- `dayu/host/open_host.py`
  - 同步 `_PublicHostHandle.run_storage_maintenance` docstring 的行为空间与 raises 描述。

## README / Design Sync

- 未同步 README 或 design。
- 理由: 本次只修正 public/handle docstring 与设计真源不一致的问题；`docs/host/design.md` 已准确描述默认 dry-run 与显式 reclaim 的破坏性回收语义，README/design 无需扩大修改。

## Validation

- 已运行: `source .venv/bin/activate && pyright dayu/host/api.py dayu/host/open_host.py`
  - 结果: 0 errors, 0 warnings, 0 informations
  - 备注: pyright 提示存在新版 `v1.1.410`，当前校验使用仓库环境中的 `v1.1.409`。
- 未运行测试原因: 本次为 docstring-only 修复，不改变运行时代码、类型签名、公共 API 或测试断言；若 pyright 通过，最小验证已覆盖本次风险面。

## Residual Risk / Uncovered

- 未覆盖运行时测试: docstring-only 变更无行为面，未运行 pytest。
- 未进入 re-review gate，未 stage、commit、push、PR 或 merge。
