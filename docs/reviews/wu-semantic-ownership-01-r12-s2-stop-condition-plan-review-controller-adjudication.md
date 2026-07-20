# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 stop-condition corrected-plan review Controller 裁决

## 1. Gate 身份与结论

- 本 gate 是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 S2 stop-condition corrected plan 的双路完整 plan review 裁决，不是新 WU，也不重新打开独立历史 sub-WU。
- review target：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，634 行 / 81,713 字节 / SHA-256 `1f4df5f942a49a5c95bd60f75d0ef3e8a3cbfacede2c2d8f7ecf3c42a1436715`。
- AgentMiMo 最终 artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-review-mimo.md`，276 行 / 23,704 字节 / SHA-256 `b59e529f6371cee21279124cfe3b8d2e7f7d3c013eab8396652e641563e9bec4`。
- AgentDS 最终 artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-review-ds.md`，293 行 / 25,633 字节 / SHA-256 `b8e4773047caade4020a1d55847a87bfad47918c2ea33da5ae41b210b3425c32`。
- Controller verdict：`REWORK / IMPLEMENTATION NOT AUTHORIZED`。
- 裁决计数：`accepted plan-fix groups = 6`，`rejected/no-fix = 2`，`deferred = 0`，`blocking design contradiction = 0`。

两路 review 都正确确认了 package-default Fins 配置走 transaction-private root 时的真实 discovery 链，但 AgentDS 找到的显式 `config.workspace_root` 反例会直接破坏隔离核心契约。其严重度不能按 review 中的 LOW 或“残余风险”处理，snapshot drift 也不是允许 pre-publication 外部 mutation 的 owner contract。因此不得进入 implementation。

## 2. Controller 直接证据

1. `dayu/service/host_assembly.py::_effective_fins_workspace_root_config_value` 在 Fins provider 未配置 `workspace_root` 时使用调用方 runtime root；但显式绝对路径会原样 resolve 后返回，忽略调用方传入的 private validation root。
2. `tests/service/test_host_assembly.py::test_fins_tool_discovery_spec_preserves_explicit_workspace_root` 明确锁定了普通 runtime assembly 保留显式 Fins root 的现行 contract。
3. R12 PRESERVE 必须逐字节保留现有 config；因此合法用户配置可以把真实 discovery side effect 定向到 transaction-private tree 之外。`DefaultFinsRuntime.create` 随后会在该路径创建 `portfolio/`、`.dayu/repo_*`、`.dayu/fins_ingestion/jobs/` 等路径。
4. 仅由 CLI 删除/覆盖 raw provider 字段会改变 PRESERVE 用户配置语义；由 CLI 按 import path/provider id 猜 Fins provider 又会复制 Service 已拥有的 provider classification。两条路径都违反唯一 semantic owner。
5. 项目 `.venv` Python 3.11.15 实测 `shutil.rmtree.avoids_symlink_attacks is True`；当前实现使用 `lstat/open/fstat` 的 fd-safe traversal。因没有 `follow_symlinks` 参数而断言 Python 3.11 `rmtree` 必然会跟随 symlink 是错误的；AgentMiMo 已在同任务 artifact follow-up 中修正该事实。
6. review authority 表中的行数/字节错误也已在同任务 follow-up 中修正；两份最终 review artifact 均通过 `git diff --check`。

## 3. Accepted plan-fix groups

### R12-S2-PR-F01 — HIGH — 显式 Fins workspace root 必须受 validation-only override 支配

接受 AgentDS DS-F03 的反例，但将严重度提升为 HIGH，并拒绝“只记录 residual”或“在 PRESERVE staging 剥离字段”的建议。

Plan 必须把 validation override 放回唯一能识别 Fins workspace-bound provider 的 Service assembly owner：

- 为 `assemble_effective_tool_provider_configs` 设计一个朴素、显式、仅作用于 Fins effective config 的 validation override 输入；普通 runtime 调用继续保留用户显式 Fins root，R12 validation 调用则由该 override 无条件支配 Fins effective root。
- 不得让 CLI 复制 `_is_fins_workspace_bound_provider_config` 规则、按 provider id/import path 猜 owner、修改 staging raw config、引入 schema 字段、兼容分支、fallback、metadata-only discovery 或 test-only production seam。
- override 必须只改变 in-memory effective provider config，不改变 staging/public config bytes；Web storage-state 等非 Fins effective config 不受影响。
- S2 allowlist、owner tests、README 触发判断、coverage、pyright、Ruff 和 exact-diff/scans 必须随真实 owner boundary 更新。允许最小 Service assembly 与其直接 owner tests/说明发生当前 finding 所需的 diff；Fins production 与 package manifests 仍必须零 diff。
- tests 必须同时覆盖未配置、显式绝对、显式相对 Fins roots，证明 validation override 全部落入 private root；并证明 ordinary runtime assembly 仍保留现行显式配置语义、非 Fins provider 不受影响、public roots 在 discovery/cleanup 前后 byte/identity 不变。

这不是统一 tool authorization、sandbox 或新 provider framework；它是对既有 effective-config owner 增加一个直接输入，精确解决当前真实隔离缺口。

### R12-S2-PR-F02 — MEDIUM — OS fault injection 与“test shim”边界必须自洽

接受 AgentDS DS-F01，并与 AgentMiMo Finding 004 的 fault-point 精确性合并。

- Plan 必须明确允许 tests 通过 `pytest.monkeypatch` / `unittest.mock` 在 owner 模块边界注入 `os.open`、`os.fsync`、`os.replace`、删除原语和 interrupt/ENOSPC 等 syscall fault；这不属于禁止的 synthetic provider、metadata-only discovery 或 test shim。
- 不得为测试向 production contract 增加 callback/factory/default-callable seam。
- 列出 pre-publication validation cleanup、publication/rollback 与 post-publication cleanup 的精确 fault points及各自预期状态，避免“每个 fault point”由实现者自行猜测。

### R12-S2-PR-F03 — MEDIUM — cleanup 后 parent-fsync 失败的 retained truth 必须唯一

接受 AgentMiMo Finding 001。

- validation tree 已删除而 private parent fsync 失败时，保留的是仍存在的 transaction-private staging/container path，不得声称已删除 validation tree 仍存在。
- typed diagnostic 必须报告 retained staging path、`deletion durability unconfirmed` 和精确安全错误阶段；测试断言 staging 存在、validation child 不存在、public roots 未变。
- 删除中途失败时只承诺 retained path 与精确 failure stage/path；不承诺 private tree 内容仍完整。

### R12-S2-PR-F04 — MEDIUM — no-follow 删除必须形成可执行的跨平台 contract

接受经事实修正后的 AgentMiMo Finding 002，并扩展到 S3 的真实 Windows 要求。

- Plan 不得强制不安全的 `os.walk` 方案，也不得仅因 Python 3.11 `rmtree` 无 `follow_symlinks` 参数而禁用它。
- 必须规定 owner 使用当前平台上经直接验证的 symlink/reparse-point-safe、identity-locked 删除路径；fd-safe `shutil.rmtree` 仅在 `avoids_symlink_attacks=True` 且前后 identity/containment 检查成立时可用。
- 对 `avoids_symlink_attacks=False` 的平台，Plan 必须给出能在 Windows 用户工作流中执行的 fail-closed 安全路径，不能把所有正常 Windows init 永久拒绝。若需平台原语，应保持 owner-local、最小且有真实 Windows 证据，不抽象成通用 filesystem framework。
- tests 必须覆盖 nested symlink/dangling symlink、root identity drift、外部 sentinel 不变和 Windows reparse/symlink 可用场景；平台无法创建 symlink 时必须有明确 skip reason，并由真实 Windows workflow 补足可执行行为证据。

### R12-S2-PR-F05 — MEDIUM — directory durability 的平台语义必须真实

接受 AgentDS DS-F04 中关于语义边界与 Windows 差异的有效部分。

- Plan 必须精确区分 directory-entry durability、文件内容 durability与 secure deletion；不得把 parent fsync 描述成不可 forensic 恢复。
- POSIX 与 Windows 的 publication/cleanup durability 实现及失败语义必须分别写清。若 Python/平台不支持相同的 directory fsync，Plan 必须选择并验证最小可行的 platform-owned mechanism，或明确收窄 crash-durability承诺而不削弱 atomic replace/rollback、pre-publication isolation 和 truthful diagnostic。
- S3 real Windows job 必须覆盖正常 init transaction；不能只在 POSIX mock Windows 分支后宣称跨平台通过。

### R12-S2-PR-F06 — LOW — source/propagation scans 必须随 owner 修正

原 plan 的“Service/Fins production 必须零 diff”与 accepted HIGH owner fix 已直接矛盾。Plan 必须：

- 将 Service 允许路径限制为 F01 所需的 assembly owner、直接 caller/test/README 触发范围；禁止无关 Service 改动。
- 保留 Fins production、package models/manifests、Host/Engine/Tool 和 deferred ISSUE 路径零 diff。
- 增加 source scan，证明 validation-only override 只有 R12 init validation consumer，ordinary runtime caller 显式选择无 override，且没有 CLI-side Fins provider 分类、raw-config stripping 或第二条 discovery/parser chain。

## 4. Rejected / no-fix opinions

1. **AgentDS DS-F02 独立修复：REJECT / NO FIX。** Partial deletion 后 diagnostic tree 可能不完整是删除失败的固有事实；当前 owner 只需保留可定位 staging path和精确异常阶段，不承诺完整取证副本。有效的 truthful wording 已并入 R12-S2-PR-F03，无需复制 tree、预先快照或引入 cleanup journal。
2. **AgentMiMo Finding 003：REJECT / NO FIX。** 两个 managed roots 的 snapshot 不是单 syscall 原子是已知 residual。init lock 已串行化 init writers；非 init writer 竞争由 reset 前强警告、锁后 identity复核和现有 residual owner 承接。本轮不扩展 Host process lock/kill 或 filesystem watcher。

## 5. Fix gate 与授权边界

下一 gate 是 AgentCodex plan-only fix：

- 必须完整修正 `R12-S2-PR-F01..F06`，更新同一 R12 plan 与新的 plan-fix artifact；不得实现 product/test/README/workflow。
- Plan 应保持 R12 三个 cumulative slices，不新增第四 slice或新 sub-WU；Service owner correction属于 S2 当前闭环。
- Controller validation 后必须再次由 AgentMiMo / AgentDS 并发完整 re-review；所有 accepted findings 关闭前不得恢复 S2 implementation。
- 当前明确未授权 S2 product implementation、S3、aggregate、commit、push、PR、Issue 142/151/175/177/178、Web/WeChat/render tracker能力或统一 tool authorization framework。
- blocking questions：`NONE`；design-truth contradiction：`NONE`。
