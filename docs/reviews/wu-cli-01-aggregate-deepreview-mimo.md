# Code Review

## Scope

- Mode: aggregate deepreview (current changes)
- Branch: `phase/host-ui-implementation`
- Base: `de99831f` (accepted plan commit)
- Output file: `docs/reviews/wu-cli-01-aggregate-deepreview-mimo.md`
- Included scope: WU-CLI-01 全部 accepted slices (S1–S7) 的整体集成，覆盖 `dayu/cli/`、`dayu/service/entrypoint_runtime.py`、`dayu/service/host_assembly.py`、`dayu/service/fins_direct.py`、`dayu/runtime/location.py`、`dayu/fins/upload_batch.py`、相关 tests 和 README 更新。
- Excluded scope: Host internals、Engine internals、Fins storage、旧 write workflow、旧 host management、旧 provider interactive、旧 migrations、旧 label registry。
- Parallel review coverage: 无（单 reviewer 直接走读全部关键链路）。

## Findings

未发现实质性问题。

以下为 maintainability observations，均不构成 correctness / boundary / stability finding：

### 编号-未修复-低-SIGINT monitor 实现跨三个 CLI 命令模块重复

- **入口/函数**: `_PromptSigintMonitor`（`dayu/cli/commands/prompt.py`）、`_InteractiveSigintMonitor`（`dayu/cli/commands/interactive.py`）、`_FinsSigintMonitor`（`dayu/cli/commands/fins.py`）
- **文件(行号)**: `prompt.py:82–158`、`interactive.py:82–163`、`fins.py:96–169`
- **输入场景**: 任何 CLI 命令进入运行态 SIGINT 观察。
- **实际分支**: 三个模块各自定义结构和行为几乎完全相同的 SIGINT monitor 类。
- **预期行为**: 共享 SIGINT 观察逻辑应收敛到一个可复用位置。
- **实际行为**: 每个 CLI 命令模块各自维护一份 `_event`、`_loop`、`_installed`、`install()`、`close()`、`notify()`、`wait_next()` 实现。
- **直接证据**: 三个类的字段、方法签名和实现逻辑行对行一致。
- **影响**: 修改 SIGINT 观察语义时需要同步三处；新增 CLI 命令时需要第四份副本。
- **建议改法和验证点**: 抽取到 `dayu/cli/_sigint_monitor.py` 或类似共享位置；三个命令模块 import 复用；测试不变。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### 编号-未修复-低-workspace root 解析与可选文本校验 helper 跨模块重复

- **入口/函数**: `_resolve_workspace_root`（`prompt.py`、`interactive.py`、`fins.py`、`init.py`）、`_optional_stripped_text`（`host_context.py`、`prompt.py`、`interactive.py`、`fins.py`、`upload_batch.py`）
- **文件(行号)**: 各文件中的对应函数。
- **输入场景**: 任何 CLI 命令解析 workspace root 或可选文本参数。
- **实际分支**: 四个 `_resolve_workspace_root` 和五个 `_optional_stripped_text` 各自独立定义。
- **预期行为**: 公共 CLI 文本校验逻辑应收敛到共享位置。
- **实际行为**: 每个命令模块各自维护功能等价的 helper，仅异常类型略有差异。
- **直接证据**: 函数体逻辑行对行一致。
- **影响**: 修改校验规则时需要同步多处。
- **建议改法和验证点**: 抽取到 `dayu/cli/_helpers.py` 或类似共享位置；各命令模块 import 复用。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### 编号-未修复-低-CLI 命令 ValueError 子类各自独立定义

- **入口/函数**: `CliCommandUsageError`（`prompt.py`）、`CliInteractiveUsageError`（`interactive.py`）、`CliFinsUsageError`（`fins.py`）、`CliInitUsageError`（`init.py`）
- **文件(行号)**: 各文件中的对应类定义。
- **输入场景**: 任何 CLI 命令遇到用法错误。
- **实际分支**: 四个模块各自定义语义等价的 `ValueError` 子类。
- **预期行为**: 统一的 CLI 用法错误类型便于上层 `main.py` 和测试统一捕获。
- **实际行为**: 每个命令模块各自维护一个 `ValueError` 子类，语义完全相同。
- **直接证据**: 四个类的 docstring 和继承关系一致。
- **影响**: 上层需要 import 多个异常类型；新增命令时需要第五个副本。
- **建议改法和验证点**: 统一为 `CliUsageError`；各命令模块 import 复用。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

无。

## Residual Risk

以下 residual risks 已在 `docs/host/ui-implementation-control.md` 中登记，均有明确 owner / destination：

| ID | 类型 | Owner | 摘要 |
|---|---|---|---|
| WU-CLI-01-RR-01 | behavior parity | Fins owner | `--infer` alias inference 当前无 approved Fins boundary，download / upload 与旧 CLI 行为不完全一致。 |
| WU-CLI-01-RR-02 | behavior parity | Fins / tooling owner | `--ci` process snapshot 当前无公共 contract。 |
| WU-CLI-01-RR-03 | Host observability | Host / Service owner | 旧 debug / trace / duplicate governance flags 无当前 Host public per-run contract。 |
| WU-CLI-01-RR-04 | Fins batch parity | Fins owner | `upload_filings_from` 文件识别规则与旧 CLI 不完全一致；当前采用保守 typed rule。 |
| WU-CLI-01-RR-05 | model profile UX | Config / Service owner | `--thinking` / `--no-thinking` 在当前模型 schema 中不是独立布尔开关。 |
| WU-CLI-01-RR-06 | Fins cancel responsiveness | Fins runtime / CLI signal adapter owner | 部分长事务可能不及时检查 cancel request；无 `add_signal_handler` 平台无法提供同等 durable cancel UX。 |
| WU-CLI-01-RR-07 | Fins upload action parity | Fins owner | `upload_filing --action delete` 当前是否被 Fins upload runtime 支持需实现时验证。 |
| WU-CLI-01-RR-08 | CLI output UX | CLI / Fins product owner | `SUCCEEDED` direct command 输出未展示 Fins `result_summary`。 |

以上所有 residual risk 均为 `deferred-with-owner` 状态，无无 owner 风险。

## 覆盖范围

- CLI parser factory、scoped command help、全局参数、exit code mapping。
- `init` 命令：current-schema filesystem bootstrap、`--reset` 白名单、symlink/containment 预检、`--overwrite`、旧 schema 不生成。
- `prompt` 命令：ConfigLoader → ScenePrepare → ToolsDiscovery → Service assembly → Host public API 完整链路；`--ticker`/`--label`/`--model-name` 映射；unsupported legacy flags fail fast；SIGINT → Host cancel → terminal wait。
- `interactive` 命令：同 prompt 链路；多轮 REPL；`--label`/`--new-session` session binding；每轮独立 watcher attach/close；SIGINT 第一次 cancel、第二次本地退出。
- Fins direct commands（`download`、`upload_filing`、`upload_material`、`process`、`process_filing`、`process_material`）：CLI 参数 → `FinsDirectCommandService` 显式方法参数 → Fins ingestion runtime；SIGINT → durable cancel → 第二次本地退出。
- `upload_filings_from`：本地目录扫描 → `generate_upload_batch_plan` → 结构化 plan → CLI 脚本渲染；不启动 job。
- `dayu.service.entrypoint_runtime`：runtime 准备、Session ensure/create、watcher attach-before-submit、terminal observation、outbox fallback、cancel request 构造、watcher failure 诊断。
- `dayu.service.fins_direct`：download/preprocess/upload typed request 构造、job start、poll terminal、durable cancel、exit mapping。
- `dayu.service.host_assembly`：`ServiceRunOverrides` → `RunnerCallOptions`/`AgentPolicy` typed override 合并。
- `dayu.fins.upload_batch`：结构化批量上传计划生成、filing/material 识别、`FINS_UPLOAD_FILE_SUFFIXES` 公共常量。
- `dayu.runtime.location`：显式 config overlay 目录解析。
- README 更新：`dayu/README.md`、`dayu/service/README.md`、`dayu/fins/README.md`、`dayu/config/README.md`、`tests/README.md`。
- 测试：190 passed，pyright 0 errors。

## 未覆盖范围

- Host internals、Engine internals、Fins storage：不在 WU-CLI-01 scope 内。
- 旧 write workflow、旧 host management、旧 provider interactive、旧 migrations、旧 label registry：不在本轮 scope 内。
- Web / GUI / WeChat entrypoint：属于 WU-WEB-01 / WU-GUI-01 scope。
- 端到端 smoke 测试（真实 Host / Fins runtime）：当前使用 mocked dependencies；端到端验证属于后续 integration test scope。
- Windows ProactorEventLoop 等无 `add_signal_handler` 平台的 SIGINT cancel：属于 WU-CLI-01-RR-06。
