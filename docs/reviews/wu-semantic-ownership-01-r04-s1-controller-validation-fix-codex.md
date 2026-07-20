# WU-SEMANTIC-OWNERSHIP-01 / R04-S1 Controller-validation fix — Codex

## 1. Gate 身份与结论

- umbrella WU：既有 `WU-SEMANTIC-OWNERSHIP-01`，不是新 WU 或新 slice。
- remediation：R04 `awaiting provider resolution composition` 唯一原子 S1。
- fix finding：`R04-S1-CV-F01`。
- implementation base / 当前 HEAD：`a4ffd7641c8f114e987972d77572c2c2b4a8202f`；HEAD 未移动。
- artifact：`docs/reviews/wu-semantic-ownership-01-r04-s1-controller-validation-fix-codex.md`。
- 结论：F01 已修复。`ServiceDiscoveredTools` 的 Fins awaiting runtime 与 typed metadata state 已成为 required construction invariant；四个 hidden consumers 均通过直接 typed replacement 保留 discovery owner 产出的完整状态；新增 owner-level regression 证明替换 tool bundle 后 Host wait binding、activation registry、poll registry 与 policy composition 不变。
- 状态：`READY_FOR_CONTROLLER_REVALIDATION`。

本 fix 没有进入 code review、accepted implementation commit、R05 或其它后续 gate。

## 2. Finding closure 与 root cause

Controller finding 成立。修复前 `ServiceDiscoveredTools._fins_awaiting_providers` 的空 tuple 默认把两个不同事实混为一谈：

1. discovery owner 已校验且确认没有 active awaiting provider；
2. 派生对象的调用方忘记传播 owner 产出的 typed state。

四个既有 consumers 手工重建 discovery result 时保留了公开字段与 `fins_awaiting_runtime`，却静默丢失 typed provider metadata。`_compose_options(...)` 正确地只消费 typed state，因此派生结果会错误省略 Host wait composition。根因位于 Service discovery result 的构造契约，而不是下游 Host、raw provider config 或 smoke fixture。

修复内容：

1. `ServiceDiscoveredTools.fins_awaiting_runtime` 与 `_fins_awaiting_providers` 均移除默认值。无 provider 仍由 owner 显式传入 `None` 与空 tuple；漏传则由 pyright 在开发期拒绝。
2. 四个派生点均改用 `dataclasses.replace(...)`，只替换各自真正拥有的 `tool_bundle` / `source_refs` / `provider_reports`，由 typed dataclass operation 原样保留 runtime、typed metadata 与其它 discovery facts。
3. 派生点没有访问私有 metadata type/field，没有从 `effective_provider_configs` 或 raw config 重算、reparse、fallback。
4. `tests/service/test_host_assembly.py` 新增 owner-level regression：在真实 packaged config discovery 上加入一个替换工具，再分别组合原始与派生 discovery，通过 Host public registry resolution 与 policy value object 比较三种 Fins binding、activation adapter、poll adapter 和完整 poller policy；测试不读取私有 metadata。

收紧 required signature 后、修正 consumers 前，full pyright 精确报告以下四个 `reportCallIssue`，没有其它错误：

- `tests/tools/test_combined_tools_acceptance.py:695`
- `utils/smoke_host_public_conversation_memory.py:612`
- `utils/smoke_host_public_conversation_memory_scenarios.py:3312`
- `utils/smoke_host_public_multiturn.py:534`

这证明遗漏 constructor state 已由类型检查变成开发期失败。修正后 full pyright 为零错误。

## 3. Exact changed files

本 fix 只修改以下 Controller 授权文件，并新增本 artifact：

1. `dayu/service/host_assembly.py`
2. `tests/service/test_host_assembly.py`
3. `tests/tools/test_combined_tools_acceptance.py`
4. `utils/smoke_host_public_conversation_memory.py`
5. `utils/smoke_host_public_conversation_memory_scenarios.py`
6. `utils/smoke_host_public_multiturn.py`
7. `tests/README.md`
8. `docs/reviews/wu-semantic-ownership-01-r04-s1-controller-validation-fix-codex.md`

`utils/smoke_host_public_conversation_memory_scenarios.py` 同时删除了 changed-file Ruff 发现的唯一未使用 `LocalEngineWorkerFactory` import；这是同一授权 consumer 内通过强制 F401 gate 所需的无行为机械修正。

未修改 accepted plan、Controller validation、control doc、原 implementation artifact、其它 production/test/README。工作树中其余既有 R04 实现、README 与 Controller/control 内容保持原样，没有删除、回滚或覆盖。

## 4. Tests 与 coverage

### 4.1 Finding focused validation

运行新 owner regression、Controller 指定 combined acceptance 与两个 assembly suites：

```text
36 passed, 3 warnings in 3.97s
```

包含：

- `tests/service/test_host_assembly.py::test_replacing_discovered_bundle_preserves_host_wait_composition`
- `tests/tools/test_combined_tools_acceptance.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`

### 4.2 Accepted-plan affected matrix

按 accepted plan §7 的完整十七组 target，在一个 `--cov=dayu` session 中运行。原 508 tests 加入本 fix 的一个 owner regression 后结果为：

```text
509 passed, 3 warnings in 21.17s
```

coverage JSON：`workspace/tmp/r04-controller-validation-fix-coverage.json`。三条 warning 均为既有 edgar dependency deprecation warning。

逐文件 coverage：

| production Python file | percent covered | gate |
|---|---:|---|
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 85.5421686746988% | pass |
| `dayu/fins/tools/download_provider.py` | 100.0% | pass |
| `dayu/fins/tools/preprocess_provider.py` | 100.0% | pass |
| `dayu/fins/tools/upload_provider.py` | 100.0% | pass |
| `dayu/host/wait_adapter.py` | 90.4054054054054% | pass |
| `dayu/runtime/config_loader.py` | 96.3126843657817% | pass |
| `dayu/service/entrypoint_runtime.py` | 88.2661996497373% | pass |
| `dayu/service/fins_wait_adapter.py` | 94.56521739130434% | pass |
| `dayu/service/host_assembly.py` | 95.02664298401422% | pass |

全部修改 production Python 文件逐文件 `>=80%`；没有 coverage pragma、omit 或总覆盖率替代。

## 5. Type、lint、diff 与 scans

- final `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 对全部 tracked changed Python/test/smoke 文件运行 `ruff check --select F401,F841`：`All checks passed!`。
- `git diff --check`：pass。
- 全仓 Python source constructor scan：`ServiceDiscoveredTools(...)` 只剩 `dayu/service/host_assembly.py` 的 discovery owner 唯一直接构造；四个 authorized derived consumers 均命中 `return replace(...)`。
- 对四个派生文件的 added-line scan：私有 metadata field、`effective_provider_configs`、raw `awaiting_resolution_mode` 与直接 `ServiceDiscoveredTools(...)` 构造均零命中。
- 旧 entrypoint policy helper、scene helper、无参 `WaitPollerRuntimePolicy()`：零命中。
- Host/Service/runtime 十个旧 deployment-default 常量：零命中。
- prompt assets / execution profile 的 wait policy 或 awaiting mode 污染：零命中。
- anchored `dayu.runtime` reverse-import：零命中。
- deferred-scope added-line scan（authorization、permission、process isolation、observation timeout、lost outcome）：零命中。
- mode propagation 仍只位于 packaged config、Fins 唯一 parser/direct providers、Service owner routing 与 owner tests；四个派生 consumer 没有新增解析。
- 当前 HEAD 复核仍为 `a4ffd7641c8f114e987972d77572c2c2b4a8202f`。

## 6. Packaged awaiting public smoke

运行：

```text
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r04-controller-validation-fix-smoke
```

结果：pass。packaged `ConfigLoader -> provider discovery -> Service composition -> public Host` 保持三种 typed mode 与完整十二字段 policy；poll path 实际观察 `not_ready=1 -> ready=1` 并以 `SUCCEEDED` 终止；manual/no-provider/provider-disabled/runtime-disabled 均不启动 poller；callback 在 Host open 前失败；prompt/interactive composition 一致。全过程只使用本地 deterministic execution/observation boundary，没有访问外部 LLM、网络或 secret。

## 7. README decision

`tests/README.md` 需要更新：该文件负责声明测试目录的稳定验证边界，本 fix 新增“derived discovery 替换 bundle 后保持 Host wait composition”的 owner-level contract，属于其读者与职责范围。

其它 README 不更新：本 fix 不改变 production contract 的既有最终描述、用户入口、命令、分层关系或排障面。

## 8. Residual risks 与 scope boundary

| residual / uncovered area | classification / owner |
|---|---|
| `R04-S1-CV-F01` typed state 丢失路径 | fixed in current fix；required constructor + 四个 direct replacement + owner regression + full pyright 已闭合 |
| callback 正向 transport | 既有 WU-WAIT-01 / #89 owner；本 fix 保持 pre-open fail-closed |
| 外部 LLM / 网络 smoke | 本任务明确禁止；packaged local public smoke 已覆盖本 finding 所需路径 |
| Host 重启恢复、R05 timeout/LOST、Issue 175、authorization/permission/deferred owners | 维持既有 owner；本 fix 未触碰、未实现 |
| 完整 R04-S1 code review | 等待 Controller re-validation 通过后由 Controller 按既定 gate 派发 |

没有未分类的当前 finding residual，也没有需要扩大 allowlist的 open question。

## 9. Commit / checkpoint 与 handoff

本 fix 没有创建 commit、checkpoint、stash、push 或 PR；HEAD 始终为 `a4ffd7641c8f114e987972d77572c2c2b4a8202f`。

`R04-S1-CV-F01` 已达到 fix-pass，下一且唯一入口为 Controller re-validation。状态：`READY_FOR_CONTROLLER_REVALIDATION`。
