# WU-CLI-CONFORMANCE-F01-F07 Gateflow 实施计划（Codex）

## 0. Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- 目标分支：当前分支 `codex/interactive-oracle`
- 既有 PR：`190`
- 当前 Gate：`Second Plan Fix`（承接 Plan Re-review 总控裁决）
- Gate 状态：`SECOND PLAN FIX COMPLETE — 待第二轮独立 Plan Re-review`
- Goal Confirmation：用户已显式批准；本计划不重复打开目标语义讨论。
- 允许动作：只更新本计划、在 `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md` 追加第二次 plan fix 记录并执行只读校验。
- 禁止动作：implementation、第二轮 plan re-review、code review、deepreview、stage、commit、push、PR 读取/写入/状态操作。
- 下一合法入口：仅为第二轮独立 **Plan Re-review Gate**；本次 fix 完成后必须停止。
- 编制日期：2026-08-02（Asia/Shanghai）

### 0.1 冻结真源与基线保护

本计划以以下内容作为实现时不可自行重定义的真源：

- `docs/cli_ci_oracles.json`
- `docs/cli_ci_scenarios.json` 中 `readiness_proof.init`、`readiness_proof.prompt`、`readiness_proof.interactive`、`readiness_proof.post_fix_conformance_refresh`
- `docs/cli_ci.md`
- `docs/host/design.md`
- `docs/engine/design.md`
- `/Users/leo/workspace/.dayu-cli-ci/pr190-closure-20260802TQgGLA1/evidence/interactive/observed-behavior-pr190-closeout.md`
- `/Users/leo/workspace/.dayu-cli-ci/pr190-closure-20260802TQgGLA1/evidence/interactive/compaction-invalid-response-audit-pr190.md`

其中两个 registry 文件是用户已有 dirty baseline。当前第二次 fix 与后续第二轮 plan re-review 都不得编辑、reset、overwrite、rebuild 或 stage 它们；它们只在 accepted plan commit 按 §13.2 的显式路径与固定字节纳入 PR 190。Plan Review 开始时的内容摘要必须保持：

| 路径 | Plan Gate 基线 SHA-256 | 保护级别 |
|---|---|---|
| `docs/cli_ci_oracles.json` | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` | dirty formal baseline，字节不可变 |
| `docs/cli_ci_scenarios.json` | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` | dirty formal baseline，字节不可变 |
| `observed-behavior-pr190-closeout.md` | `6aa8c8c7430e979b95f3bd8551f44ae34432e5e55172231c296d634932aa712f` | immutable first-round evidence |
| `compaction-invalid-response-audit-pr190.md` | `fed1a2ae29baf2b59b3d16d90460661c563ae18233f93530b241645ada38fb61` | immutable first-round evidence |

`docs/host/design.md` 作为语义设计真源允许且必须在后续 S6/S7 只同步已批准的新标识/新契约；这不是重定义产品语义。`docs/cli_ci.md` 在本 work unit 中只读。两个 registry 的内容在本 work unit 中也始终只读，但其既有 dirty baseline 会在 accepted plan commit 原字节提交；该提交完成后 S1–S8 面对的是 clean tracked registry，不再携带 dirty registry。

### 0.2 Controller 裁决与 blocker 规则

- F06 不是 blocker：`context_compaction_completed` 是 stale typed trigger identifier，语义已经是 governance resolved；计划按授权将代码、严格 manifest contract 和正确设计真源统一重命名为 `context_governance_resolved`，不保留 alias。
- F07 不是 blocker：现有 compact schema 缺少 typed source boundary、Host 派生 represented coverage 和 explicitly dropped coverage，是本次要修复的实现缺口；按 fresh schema/public contract 处理，不兼容旧 schema。
- 只有在实现直接证据证明“冻结 oracle 的最终可观察行为”与“Host 生命周期/取消/治理唯一所有权、accepted compact 单一真源、分层依赖”无法同时成立时才停止并报告 blocker。依赖 API 不便、旧测试失败、需要更新设计标识或旧 schema 不完整都不是产品 blocker。
- 截至本次 plan fix，没有发现不可调和的产品冲突；计划状态为 non-blocked。

## 1. 目标、动机与完成信号

### 1.1 第一性原理动机

首轮真实 CLI evidence 已证明 F01–F07 不是测试夹具偏差，而是 owner boundary 上的可复现偏差：CLI 暴露了不应存在的配置入口；editor 与键盘控制未跨越 acceptance barrier；READ_ONLY 被 UI 当作会话终止；interactive tool manifest 暴露了禁用工具；typed trigger 使用旧标识；Host compaction 接受边界无法证明完整覆盖、严格结构和 accepted truth 的单源派生。严重性成立，因为这些偏差分别会改变用户可调用语法、丢失草稿或取消意图、破坏并发附件隔离，或让 Memory/RunInput/artifact/trace 对同一 compact 事实产生不同结论。

修复必须落在语义 owner 或其直接输入边界：CLI 只拥有语法与本地交互状态；Service 只拥有入口装配；Host 唯一拥有 Run 生命周期、取消、attachment access、Context Governance acceptance 和 canonical terminal；Engine 只消费 Host typed input，不补偿 Host 语义。

### 1.2 最终成功信号

完整 work unit 只有同时满足以下条件才可在未来 implementation closeout 中判定完成：

1. F01–F07 的冻结 oracle 全部满足，且没有兼容路径、alias、loose parsing 或下游补偿。
2. S1–S6 各自保持 owner contract；S7 以一个原子 closure 同时切换 fresh compact schema、accept barrier、repair feedback、persistence/projection，不暴露中间不一致状态。
3. Host 先以唯一 final accepted compact truth 提交 canonical terminal；Memory、下一轮 RunInput、compact artifact 和 tool trace 只从该 committed canonical event 的 strict v2 semantic projection派生，rejected candidate或未提交的accepted object不产生任何partial materialization。
4. owner-level tests 覆盖反例及竞态；所有改动生产文件单文件覆盖率达到 `>=80%`；完整 pyright、测试、JSON tool、`git diff --check` 通过。
5. 新的真实 CLI evidence 使用独立 run root、clean target commit 和独立环境，先 Mimo、必要时再 DeepSeek fallback；bundle 不覆写首轮 evidence，并有可复验 digest。
6. 两个 dirty registry 的字节和 SHA-256 与 Plan Gate 基线完全相同；fix/re-review期间从未被stage，只在§13.2 accepted plan commit按精确路径和固定blob纳入，此后S1–S8保持clean。

## 2. Scope、非目标与设计对齐

### 2.1 In scope

- F01：彻底删除全局 `--config` 的 grammar、action、help、parsing、forwarding 与用户文档入口。
- F02：显式无效 `VISUAL`/`EDITOR` 的 actionable、无 traceback、保留草稿/REPL/零 Run 失败；两者 unset 时允许系统 fallback。
- F03：pre-accept Escape/Ctrl+C 穿越 acceptance barrier；精确区分 standalone Escape 与 CSI/Home/Delete/Alt/bracketed paste；double Ctrl+C 等待 Host `CANCELLED` 与 cleanup 后返回 130。
- F04：READ_ONLY 拒绝不离开 REPL、不清草稿；下一次 mutation 关闭旧 attachment 并 fresh attach，不提升旧 mode；同一待提交语义保持稳定 `client_request_id` 且最终恰好一个 Run。
- F05：只从 interactive effective tool set 移除 `start_fins_preprocess`，保留独立 preprocess 与 download/list/read。
- F06：typed trigger 全量无 alias 重命名，同时保留 canonical terminal outcome 的唯一所有权。
- F07：Host Context Governance accept barrier 成为 candidate validity 唯一 owner，并完成严格 fresh schema、coverage、repair、terminal、fallback 与 accepted truth 派生闭环。
- S8：post-fix integration、真实 evidence、README/design 同步和 closeout 报告。

### 2.2 明确非目标

- 不修改冻结 oracle、scenario 定义或 `docs/cli_ci.md` 来迁就实现。
- 不迁移旧 compact schema/旧 durable DB，不提供旧字段、旧 trigger 或 `--config` 兼容读取/alias/re-export。
- 不把 Host 取消、attachment mode 或 compact validity 下放到 CLI/Service/Engine。
- 不改变 ordinary Agent/Engine terminal outcome 枚举，不新增第二套 compact terminal。
- 不重写 prompt_toolkit 的通用编辑器、终端 parser、History 或 tempfile 生命周期。
- 不改变 Fins preprocess 的独立命令、工具实现或存储协议。
- 不用 LLM 做自然语言事实真伪/矛盾证明；F07 只实现 schema 可确定、source-bound、policy 可计算的 validity。
- 不顺手清理归档、无关 README、无关 pyright debt 或用户已有 dirty worktree。

### 2.3 语义 owner 决策

| 语义 | 唯一 owner | 消费者必须遵守的边界 |
|---|---|---|
| CLI 可接受的 option/action/help | `dayu.cli.arg_parsing` | command/service 不得二次拒绝已删除语法，也不得隐藏转发 |
| workspace/package config location | `dayu.runtime` location contract，经 Service 入口装配 | CLI 不提供覆盖；Service 传 typed workspace，不能从已删 option 恢复 |
| composer draft、cursor、editor error 展示 | CLI composer | Host/Service 不参与本地编辑器选择 |
| key sequence 分类 | prompt one-shot 为 `dayu.cli.run_keys`，interactive 为 prompt_toolkit composer binding | submit/cancel coordinator 只消费 typed local control intent，不解析 raw bytes |
| Run acceptance、cancel terminal | Host public API；CLI acceptance barrier 只协调观察 | CLI 不推断 CANCELLED，不以 task cancellation 代替 Host graceful cancel |
| attachment access mode | Host attachment contract | CLI fresh attach；禁止 mode promotion/改写旧 attachment |
| pending mutation identity | CLI interactive coordinator | Host 收到同一语义重试时沿用同一个 `client_request_id` |
| scene effective tool set | config scene manifest + Service scene assembly | interactive 只改变 manifest tag，Fins 实现保持独立 |
| compaction trigger identifier | Host typed RunInput/manifest contract | Engine/trace 只消费严格新值 |
| compact candidate validity | Host Context Governance accept barrier | parser、operation、artifact、Memory、RunInput 不得各自松散重算 |
| compact terminal | Host existing terminal commit guard | late/stale attempt 只能形成诊断，不能形成第二 terminal |

### 2.4 Slice 顺序与依赖

批准的 outer slices 固定为：

1. S1 / F01
2. S2 / F02
3. S3 / F03
4. S4 / F04
5. S5 / F05
6. S6 / F06
7. S7 / F07 atomic closure
8. S8 / post-fix integration、evidence、docs

S1 与 S2 在语义上独立，但都触及 CLI，因此按顺序实施以保持 review/staging 边界。S3 先建立统一 acceptance/cancel barrier；S4 复用 S3 的 accepted/pending mutation 协调，不得在 S4 再建第二套 submit state machine。S5/S6 独立。S7 依赖 S6 的新 trigger identifier，并必须原子落地。S8 依赖 S1–S7 全部 owner tests 完成；README 只按实际代码触发更新，真实 evidence 只针对最终 clean target commit。

---

## 3. S1 — F01：删除全局 `--config`

### 3.1 前置条件与允许文件

前置条件：确认两个 registry SHA-256 仍等于 §0.1，且 staged set 为空。仅允许修改：

- `dayu/cli/arg_parsing.py`
- `dayu/cli/agent_entrypoint.py`
- `dayu/cli/commands/session.py`
- `dayu/cli/session_execution.py`
- `dayu/service/entrypoint_runtime.py`
- `dayu/service/host_admin.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_transient_delivery_interruption_path.py`
- `tests/cli/test_session_command.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_host_admin.py`

根 `README.md` 的用户文档删除延迟到 S8，以便按最终实际 CLI 一次同步。S1 不允许修改 `dayu.runtime` location API、任何 Host/Engine 文件或 frozen docs/registry。

### 3.2 精确 contract 与代码变更

1. `dayu.cli.arg_parsing.ParsedCliArgs`
   - 删除 `config_dir` 字段。
   - `_build_runtime_arguments_parent(...)` 不再注册 `--config` action；root、command、action 三种 parser 均不能从 parent 继承该 option。
   - 删除 `_reject_disallowed_explicit_config(...)` 及所有调用：删除语法后不存在“部分入口接收、部分入口二次拒绝”的状态。
   - 删除 namespace 对该字段的 default/normalization；`parse_cli_args(...)` 遇到任何位置的 `--config` 都由 argparse canonical unknown-option 路径失败并返回现有 parse exit code。
2. `dayu.cli.agent_entrypoint`
   - 删除 `CONFIG_DIR_OPTION_NAME`、`resolve_explicit_config_dir(...)` 及 `__all__` export。
   - 不保留旧名字 wrapper、常量 re-export 或 hidden environment compatibility。
3. session call path
   - `dayu.cli.commands.session._prepare_session_admin(...)` 删除 config helper 调用与 `ServiceHostAdminRequest.config_overlay_dir` forwarding。
   - `dayu.cli.session_execution._prepare_session_runtime(...)` 构造 `EntrypointRuntimeRequest` 时不再传 `explicit_config_dir=None`，因为字段本身删除。
4. Service public/internal request
   - `EntrypointRuntimeRequest` 删除 `explicit_config_dir`；runtime preparation 始终根据 typed `workspace_root` 走现有 runtime location owner，得到 workspace `config` 或 package default。
   - `ServiceHostAdminRequest` 删除 `config_overlay_dir`；admin preparation 使用相同 workspace/package location contract。
   - 保留 `dayu.runtime` 中可独立复用的底层 location resolver，不把 CLI 兼容语义带入该公共基础设施。

construction-site allowlist 已按当前代码的 typed 构造事实冻结，删除字段时必须机械更新全部命中，不得靠 dataclass default、`**kwargs`、兼容字段或下游忽略保留旧调用：

| typed construction / assertion | 当前命中文件 | S1 动作 |
|---|---|---|
| `EntrypointRuntimeRequest(...)` 的 CLI 生产构造 | `dayu/cli/session_execution.py` | 删除旧 keyword |
| `EntrypointRuntimeRequest(...)` 的 CLI tests | `tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py`、`tests/cli/test_transient_delivery_interruption_path.py` | 更新 fresh request 构造与 capture 断言 |
| `EntrypointRuntimeRequest(...)` 的 Service tests | `tests/service/test_entrypoint_runtime.py`、`tests/service/test_entrypoint_runtime_prompt_path.py`、`tests/service/test_entrypoint_runtime_interactive_path.py` | 更新全部 typed construction sites |
| `ServiceHostAdminRequest(...)` 的生产构造 | `dayu/cli/commands/session.py` | 删除旧 keyword |
| `ServiceHostAdminRequest(...)` 的 tests | `tests/cli/test_session_command.py`、`tests/service/test_host_admin.py` | 更新 fresh request 构造与 workspace config 断言 |

实施前和完成后都运行以下 inventory；实施前命中必须与上表一致，完成后 constructor 仍存在但旧字段名在 CLI/Service request/call path 中零命中：

```bash
rg -n 'EntrypointRuntimeRequest\(|ServiceHostAdminRequest\(|explicit_config_dir|config_overlay_dir' dayu/cli dayu/service tests/cli tests/service
```

最终 call path 固定为：

```text
argv -> argparse（无 --config action）
     -> ParsedCliArgs（无 config_dir）
     -> CLI command/session runtime request（只传 workspace 等 typed input）
     -> Service runtime/admin preparation
     -> runtime location owner 解析 <workspace>/config 或 package default
```

### 3.3 状态、错误处理与不变量

- `dayu-cli --config X ...`、`dayu-cli prompt --config X`、`dayu-cli interactive --config X`、action 前后任意位置的该 option 都走同一个 unknown option 结果；help 中零出现。
- parser 失败发生在任何 Service/Host 打开、workspace mutation 或 Run 创建之前。
- 现有 workspace config 行为不变；删除的是全局覆盖入口，不是删除 workspace config。
- 代码、公开 export、typed request、测试和最终用户文档都不得残留 compatibility path。
- Registry 明确要求“removed option 不新增 scenario”，因此只刷新代码 owner tests；不修改 registry。

### 3.4 Owner-level tests 与预期断言

- `test_arg_parsing.py`
  - 枚举 root/command/action parser 的 `_actions`，断言 option strings 中无 `--config`。
  - 对 root、prompt、interactive、session admin 的前置/后置位置参数化输入 `--config /tmp/x`，断言 canonical `SystemExit`/exit code 与 unknown-option stderr；namespace 不含 `config_dir`。
  - `--help` 与各子命令 help 不含 `--config`。
- CLI command tests
  - patch Service opener 为“调用即失败”，执行 removed option，断言 opener 未调用、无 workspace/Run side effect。
  - 正常 prompt/interactive/session 路径仍把 workspace 传到 Service，并使用 workspace config。
- Service tests
  - 构造 fresh `EntrypointRuntimeRequest`/`ServiceHostAdminRequest`（无旧字段）并断言 resolved overlay 为 workspace config；无 workspace overlay 时保持 package default。
  - 类型/签名层断言旧 keyword 不能构造 request，不写运行时兼容分支。

聚焦验证命令（未来 implementation gate 执行）：

```bash
source .venv/bin/activate
pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_transient_delivery_interruption_path.py tests/cli/test_session_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_host_admin.py -q
python -m pyright dayu/cli/arg_parsing.py dayu/cli/agent_entrypoint.py dayu/cli/commands/session.py dayu/cli/session_execution.py dayu/service/entrypoint_runtime.py dayu/service/host_admin.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_transient_delivery_interruption_path.py tests/cli/test_session_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_host_admin.py
rg -n -- '--config|config_dir|resolve_explicit_config_dir|explicit_config_dir|config_overlay_dir' dayu/cli dayu/service tests/cli tests/service
git diff --check
```

`rg` 的完成条件是：上述范围对被删除 CLI contract 零命中；若底层独立 runtime location API 仍有同名内部概念，必须不在 CLI/Service request/call path 中且由 reviewer 单独核验，不能为了零命中误删独立能力。

### 3.5 Stop signal、产物与 residual risk

- 完成信号：所有 parser inventory/help/unknown-option 测试及正常 workspace config 回归通过；旧 typed request 字段零消费者；registry hash 未变。
- 立即停止信号：发现某个非 CLI 公共入口被批准设计明确要求保留显式 overlay 时，只停止删除该独立 lower-level API，不恢复 CLI option；若无法区分 owner，停止 S1 并记录 owner blocker。
- Slice artifact：聚焦测试输出、parser inventory、删除符号扫描、pyright、registry digest snapshot。
- Residual risk：`LOW`。主要风险是漏掉 help/export 或误删独立 runtime location 能力；由 inventory 与 Service 回归覆盖。
- 非目标：不重命名 workspace config 目录、不改变 init 生成内容、不修改 frozen CLI docs/registry。

---

## 4. S2 — F02：显式 editor 失败与 unset fallback

### 4.1 前置条件与允许文件

前置条件：S1 通过且没有未归属的 CLI state change。仅允许修改：

- `dayu/cli/composer.py`
- `tests/cli/test_interactive_composer.py`
- `tests/cli/test_interactive_command.py`

不新增 adapter 模块。Host/Service/Engine、prompt manifest 与 registry 均不可修改。

### 4.2 Typed 决策与精确变更

当前开发/验证环境安装的是 `prompt_toolkit==3.0.52`，项目在 `pyproject.toml` 声明的依赖范围是 `prompt_toolkit>=3.0.0`；前者是本轮直接核验环境事实，不是版本 pin 或产品契约，也不据此推断全部未来 `>=3.0.0` 版本行为相同。S2 只依赖 prompt_toolkit 的 public import/API：public `Buffer.open_in_editor(validate_and_handle=False)` 用于 **unset** 路径，public `run_in_terminal(...)` 与 public `Buffer.document` 用于 CLI-owned 最小 round trip。当前环境源码还证明 private `_open_file_in_editor()` 会在显式命令抛 `OSError` 后继续尝试系统候选，因此显式路径禁止调用或 monkey-patch该 private method；该 private/偶然行为只用于排除错误实现路径，不是产品语义 owner。S2 不再保留 implementation-time seam 选择。

在 CLI composer owner 内增加以下私有 typed contract（名称固定，均留在 `composer.py`）：

- `_EditorEnvironmentVariable(StrEnum)`：`VISUAL`、`EDITOR`。
- `@dataclass(frozen=True, slots=True) _ExplicitEditorCommand`：`source`、`argv: tuple[str, ...]`、`resolved_executable: Path`；不保存/输出完整原始环境。
- `_EditorConfigurationError(ValueError)`：携带 closed `reason`（`EMPTY_COMMAND`、`INVALID_SYNTAX`、`EXECUTABLE_NOT_FOUND`、`NOT_EXECUTABLE`）和安全 display name。
- `_EditorProcessOutcome(StrEnum)`：`UPDATED`、`CANCELLED`；只有 return code 0 可形成 `UPDATED`，任何非零精确形成静默 `CANCELLED`。
- `_resolve_explicit_editor_command(environ: Mapping[str, str]) -> _ExplicitEditorCommand | None`：只在两个 key 都不存在时返回 `None`。`VISUAL` key 存在则优先且不尝试 `EDITOR`；否则使用存在的 `EDITOR`。显式空白、`shlex.split` 失败或空 argv 都是 actionable 配置错误；含路径分隔符时规范化 `Path`，否则 `shutil.which`；要求普通可执行文件且 `os.access(..., X_OK)`。
- `_open_explicit_editor(buffer: Buffer, command: _ExplicitEditorCommand) -> asyncio.Task[_EditorProcessOutcome]`：
  - 先冻结 original public `Buffer.document`（text + cursor），再用 CLI-owned secure tempfile 写入原 draft；tempfile path不进入错误文案。
  - 通过 public `run_in_terminal(..., in_executor=True)` 精确执行 `(str(command.resolved_executable), *command.argv[1:], str(tempfile_path))`；不用 shell、不枚举候选、不调用 prompt_toolkit private API、不 fallback。
  - spawn `OSError` 投影为一条 actionable错误；原 document不变。
  - return code 非零投影为 `CANCELLED`，stderr保持静默，原 document不变。
  - return code 0 才以 UTF-8 读取 tempfile；CLI composer 作为 editor success behavior owner，按冻结规则最多移除一个末尾换行，再通过 public `buffer.document = Document(text=..., cursor_position=len(text))` 一次性回填；读取/解码失败保留原 document并形成一条稳定错误。
  - `finally` 清理 tempfile；返回 task由 composer 持有并消费异常。

unset 路径不进入上述 CLI-owned launcher，直接调用 public `Buffer.open_in_editor(validate_and_handle=False)`，保留 prompt_toolkit 的标准 system fallback。显式与 unset 两条路径不能互相降级。

Ctrl-X Ctrl-E handler 改为以下确定流程：

```text
读取环境快照
  -> resolve explicit command
     -> missing/non-executable/invalid：actionable stderr；draft/cursor 不变；留在 REPL；不启动进程
     -> unset：public Buffer.open_in_editor(False)，允许 dependency system fallback
     -> explicit valid：CLI-owned tempfile + public run_in_terminal + exact argv
  -> 保存 returned task 的强引用
  -> completion callback/await 消费结果和异常
     -> OSError/readback failure：actionable stderr；原 draft/cursor；零 Run；REPL继续
     -> process nonzero：静默 editor cancel；原 draft/cursor；零 Run；REPL继续
     -> process zero：public Buffer.document 回填；仍须用户后续显式 submit 才创建 Run
```

错误文案必须稳定、actionable、自解释但不泄漏完整命令/环境，例如：`VISUAL 指定的编辑器不可执行；请修正 VISUAL，或取消 VISUAL/EDITOR 以启用系统默认编辑器。` spawn `OSError` 说明“指定编辑器无法启动，草稿已保留”。nonzero 不输出错误。任何路径都不得打印 traceback、完整 argv、secret-like env 或 tempfile path。

### 4.3 状态转换、异常与不变量

composer editor 子状态：

```text
IDLE
  --Ctrl-X Ctrl-E + invalid explicit--> IDLE（error once，draft/cursor unchanged）
  --Ctrl-X Ctrl-E + valid/unset------> EDITOR_PENDING
EDITOR_PENDING
  --explicit return zero-------------> IDLE（public Buffer.document 采用编辑文本）
  --explicit return nonzero----------> IDLE（silent cancel，original draft/cursor）
  --explicit OSError/read failure----> IDLE（error once，original draft/cursor）
  --unset dependency completion------> IDLE（沿用 public dependency contract）
```

- editor 动作绝不提交 prompt，因此所有失败分支 Run count 为 0。
- `VISUAL` key 存在时不尝试 `EDITOR`；`EDITOR` key 存在时不尝试系统候选。只有两者都不存在才允许系统 fallback；显式空白也不等价于 unset。
- returned async task 必须被持有和观察，避免 exception 变成 event-loop traceback；composer teardown 必须等待或取消并消费 task，不能遗留 pending task warning。
- 打开 editor 前冻结 draft/cursor；只有显式进程 return code 0 且读取成功，或 unset public dependency成功回填时，才接受新 buffer。失败/cancel不得清 History、退出 REPL 或关闭 session attachment。

### 4.4 Owner-level tests 与预期断言

- 参数化 `VISUAL` 优先、`EDITOR`、两者真正 unset；断言 typed selection与分支精确，显式空白不进入 fallback。
- 显式 nonexistent、目录、非 executable、非法 shell quoting：`run_in_terminal` 零调用；stderr 含变量名和修复动作、无 `Traceback`；draft/cursor/history 不变；composer 仍能继续输入和提交。
- 显式 executable 的 spawn `OSError`：系统候选与 private API 零调用；actionable错误恰好一次；task exception被消费；tempfile清理；draft/cursor不变。
- 显式 `/usr/bin/false`（以及测试 launcher 返回任意非零）：exact argv只启动一次；stderr为空；draft/cursor/history不变；零 Run；REPL继续。
- 显式 return code 0：exact argv只启动一次；只有成功读取后 public `Buffer.document` 更新；随后未 submit 前零 Run，显式 submit 后恰好一个 Run。
- unset：精确断言调用 public `Buffer.open_in_editor(validate_and_handle=False)`，允许 dependency system fallback；CLI-owned launcher零调用。
- integration：missing/non-executable/`OSError`/nonzero后都能在同一 REPL继续；原 draft只在用户显式提交后形成一个 Run。
- teardown：EDITOR_PENDING 时关闭 composer，不产生 unhandled task/traceback。

聚焦验证命令：

```bash
source .venv/bin/activate
pytest tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py -q
python -m pyright dayu/cli/composer.py tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py
git diff --check
```

### 4.5 Stop signal、产物与 residual risk

- 完成信号：missing/non-executable/`OSError` actionable、nonzero silent cancel、zero-only回填、unset public fallback 四分 owner contract 全通过；显式路径零系统 fallback/private API；失败路径无 traceback、零 Run、draft/REPL 保留。
- 立即停止信号：当前 resolved dependency 的 public `run_in_terminal`、public `Buffer.document` 或其它本节所需 public seam 与已核验证据不符。不得改用 private fallback、monkey patch、兼容层或擅自 pin 依赖；记录直接依赖证据并回到 plan gate。
- Slice artifact：环境选择矩阵、adapter contract test、async exception 消费结果、CLI screen/captured stderr、focused pyright/test 输出。
- Residual risk：`MEDIUM`，原因是第三方 terminal suspend/resume 与真实 editor 子进程行为；通过 public seam contract test、tempfile cleanup测试和真实 PTY evidence 收敛。
- 非目标：不设计 editor 配置文件、不增加 CLI option、不实现自己的通用文本编辑器。

---

## 5. S3 — F03：跨 acceptance barrier 的 Escape/Ctrl+C 与精确序列分类

### 5.1 前置条件与允许文件

前置条件：S2 composer task lifecycle 已稳定；S3 不改变 editor selection。仅允许修改：

- `dayu/cli/run_keys.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/composer.py`（只允许 key binding 将 typed intent 送入 coordinator、以及 teardown 对接）
- `tests/cli/test_run_keys.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_composer.py`
- `tests/cli/test_interactive_command.py`

不得修改 Host cancellation/terminal、Service observation、Engine、registry 或 terminal emulator 全局设置。

### 5.2 Typed state 与 owner-level call path

`run_keys.py` 保留现有“后台 reader thread + asyncio queue”架构，并固定使用 prompt_toolkit public `Vt100Parser`；不迁移 fd 到 event loop、不写第二套 byte parser。实现细节已收口为：

1. `TtyRunningKeyMonitor._read_loop()` 在 **reader thread 内**创建唯一 `Vt100Parser(callback)` 与 UTF-8 incremental decoder；parser 不在线程外创建，也不被其它线程调用。
2. reader thread 用 chunk read；decoded chunk 只在该线程调用 `parser.feed(...)`。原始 chunk出现 ESC 后设置/刷新命名常量 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 对应的 monotonic deadline；ambiguity pending 时每个后续 chunk都刷新 deadline。
3. `select` 没有新字节且 deadline 到期时，由同一个 reader thread调用一次 `parser.flush()` 并清空 deadline。该 deadline只解决 ESC ambiguity，不是 Run timeout、poll budget或 cancel deadline。
4. parser callback也在 reader thread执行；它只把 `KeyPress` 分类成 typed `RunningKeyAction`，并仅通过 `loop.call_soon_threadsafe(queue.put_nowait, action)` 投递。只有 `key is Keys.Escape` 且 `data == "\x1b"` 才投递 `CANCEL_RUN`；Ctrl+T仍投递 `TOGGLE_ACTIVITY`；其它完整序列不投递 action。
5. CSI/Home/Delete/SS3、Alt组合与 bracketed paste 即使跨 chunk，也先由 parser收齐；完整 sequence callback不会满足 standalone ESC 条件。完整序列之后的空 flush是 no-op，不能取消。
6. `close()` 仍由 monitor owner设置 stop、join thread并恢复 termios；parser/decoder不泄漏到 cleanup线程。

`session_execution.py` 新增/重构以下最小共享 typed state；prompt 与 interactive 共享 acceptance/cancel/graceful-closeout 语义，但 attachment、composer、generation、queue 与 history 仍由 interactive outer state拥有：

- `_LocalCancelIntent(StrEnum)`：`NONE`、`CANCEL_REQUESTED`、`EXIT_AFTER_CANCEL`。
- `@dataclass(slots=True) _AcceptedRunBarrier`：`accepted_run_id: str | None`、`accepted: asyncio.Event`；唯一允许 `publish_accepted(run_id)`，相同 id重复回调幂等、冲突 id fail fast；`wait_run_id()`只等待 Host public acceptance callback。
- `@dataclass(slots=True) _ActiveTurnCloseout`：只冻结 turn identity、`_AcceptedRunBarrier`、`_LocalCancelIntent`、exactly-once Host cancel task与 canonical terminal observation；提供 `publish_accepted(run_id)`、`request_cancel(exit_after: bool)`、`wait_accepted_then_cancel()`、`observe_terminal(result)`、`wait_closeout()`。submit task仍由各 outer driver拥有；本类型不携带 composer、attachment、generation、queued draft或History。
- `_PromptControlKey(StrEnum)`：`CANCEL`、`TOGGLE_THINKING`；`run_keys` 只输出 typed key，不直接取消 task。

prompt/interactive 的统一 call path：

```text
创建 _ActiveTurnCloseout + shielded submit task
  -> local Escape / first Ctrl+C: request_cancel(False)
       accepted id 未到：只记录 intent，submit 继续跨 barrier
       accepted id 已到：exactly-once Host graceful cancel
  -> second Ctrl+C: request_cancel(True)
       只设置 EXIT_AFTER_CANCEL；不取消 Host wait，不立即返回 130
  -> submit publishes accepted id
       若已有 cancel intent，立即 exactly-once Host cancel
  -> 等待 Host canonical terminal
       必须为/观察到 CANCELLED（若 terminal 已先成立则尊重 canonical truth）
  -> 关闭 observer、renderer、composer/key reader、signal bridge、attachment
  -> EXIT_AFTER_CANCEL ? return 130 : 返回既有 cancelled result
```

现有 accepted-state/cancel consumers 到最小 shared coordinator 的机械映射固定如下，不留给 implementation重新发现：

| 当前 site | 当前职责 | 替换后 |
|---|---|---|
| `_PromptAcceptedRunState.record` 与 `submit_entrypoint_turn_and_wait(... on_run_accepted=...)` | 发布 prompt accepted id | callback 直接调用 `_ActiveTurnCloseout.publish_accepted` |
| `_cancel_prompt_turn_after_local_request(...)` | pre-accept 时取消 submit 并返回 | 删除本地 `submit_task.cancel()`；改为 `request_cancel(False)`，submit跨 barrier继续，accepted后exactly-once Host cancel并等 canonical terminal |
| `_InteractiveAcceptedRunState.record/wait_run_id` | interactive acceptance event | 由 `_AcceptedRunBarrier.publish_accepted/wait_run_id` 唯一承担 |
| `_start_interactive_turn`、`_start_interactive_queued_followup`、`_promote_interactive_queued_followup` | 创建/携带 accepted state | 创建或原样携带同一个 `_ActiveTurnCloseout`；queued promotion不得换 identity |
| `_InteractiveActiveTurn.cancel_reason/acceptance_task/cancel_task` | cancel intent、等待 accepted、Host cancel | 收敛到 `_ActiveTurnCloseout`；outer turn只保留 generation、turn index、submit task和interactive state |
| `_request_interactive_cancel`、`_start_interactive_cancel_task` | 合并取消并启动 Host cancel | 委托 `request_cancel` / `wait_accepted_then_cancel`；重复输入不能创建第二 cancel task |
| `_wait_interactive_batch_terminal_handling_sigint` | non-TTY first/second Ctrl+C与terminal收口 | first=`request_cancel(False)`，second=`request_cancel(True)`；await同一 coordinator closeout后决定130 |
| `_drive_interactive_tty_repl` 的 composer cancel、SIGINT、submit completion与 finally cleanup | TTY竞态收口 | 先消费同 batch typed intents，再 `observe_terminal`；退出只在 canonical terminal和outer resource cleanup完成后发生 |

旧 `_PromptAcceptedRunState`、`_InteractiveAcceptedRunState` 与只做透传的兼容 wrapper全部删除。shared coordinator只消费 Host public accepted callback、cancel API和terminal result，不从 task顺序、日志、字符串或时间戳反推 Host事实。

### 5.3 精确状态机、竞态与不变量

```text
SUBMITTING + Escape/first SIGINT -> CANCEL_PENDING_ACCEPT
CANCEL_PENDING_ACCEPT + accepted -> CANCEL_IN_FLIGHT
SUBMITTING + accepted            -> RUNNING
RUNNING + Escape/first SIGINT    -> CANCEL_IN_FLIGHT
CANCEL_* + second SIGINT         -> EXIT_PENDING_CANCEL（仍等待 Host）
RUNNING/SUBMITTING + canonical terminal before cancel commit
                                 -> TERMINAL（不得伪造 CANCELLED）
CANCEL_IN_FLIGHT/EXIT_PENDING_CANCEL + Host CANCELLED
                                 -> CLEANUP -> normal-cancel/130
```

- first Escape 与 first Ctrl+C 的 cancel 语义相同；只有第二次 Ctrl+C 请求最终 130，Escape 不累计 exit intent。
- 第三次及更多 Ctrl+C 在 closeout 完成前是幂等 no-op/已有 intent，不产生第二 cancel call。
- pre-accept intent 绑定到当前 turn identity，不能泄漏到下一 prompt。
- event-loop 同一 batch 中 terminal 与 key 同时 ready 时，先登记本 batch 的 control intents，再由 `_ActiveTurnCloseout` 依据 Host canonical terminal 收敛；不得因 task list 顺序丢失 key。
- CLI task cancellation 只用于自身 cleanup，不能代替 Host `cancel_run(...)`；accepted 后恰好一次 Host cancel。
- double Ctrl+C 的 130 只能在 Host terminal observation 与全部 cleanup 完成后返回；若 Host 报告非 CANCELLED canonical terminal，保存该 terminal truth并按现有 terminal policy处理，不能覆盖成 CANCELLED。

### 5.4 Owner-level tests 与预期断言

- `test_run_keys.py` 以分块字节覆盖：standalone ESC（named deadline/flush 后一次 cancel）、CSI arrows、Home、Delete、SS3、Alt+字符、ESC 与后续字节跨 chunk、完整 bracketed paste；除 standalone ESC 外 cancel count 均为 0。记录 parser create/feed/flush 的 thread id必须都等于 reader thread id，queue写入必须只经 `call_soon_threadsafe`。
- prompt pre-accept Escape/Ctrl+C：submit future 暂不返回，先注入 key，再返回 accepted id；断言 submit 未被本地取消、Host cancel 恰好一次、目标 id 正确、最终等待 CANCELLED。
- interactive 同样覆盖 pre-accept first/second Ctrl+C；第二次后 exit task 仍未完成，直到 Host CANCELLED 与 attachment/composer/renderer cleanup 全部记录完成才为 130。
- provider/tool/closeout 三个阶段参数化 double Ctrl+C；断言一个 Run、一个 Host cancel、一个 canonical terminal、无 pending task。
- accepted terminal 与 key 同 batch 两种调度顺序；断言无 stale intent、无第二 terminal、下一 turn 不被取消。
- Escape 取消后回到/退出行为按 frozen oracle；Escape 再 Escape 不能等价 double Ctrl+C。
- terminal 先于 cancel：不调用迟到 cancel 或由 Host public precheck跳过；保留真实 terminal outcome。

聚焦验证命令：

```bash
source .venv/bin/activate
pytest tests/cli/test_run_keys.py tests/cli/test_prompt_command.py tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py -q
python -m pyright dayu/cli/run_keys.py dayu/cli/session_execution.py dayu/cli/composer.py
git diff --check
```

### 5.5 Stop signal、产物与 residual risk

- 完成信号：parser thread ownership、named ambiguity deadline/flush、所有完整序列反例、pre-accept、double Ctrl+C 三阶段、同 batch 竞态通过；Host cancel/terminal/cleanup 次数满足不变量。
- 立即停止信号：需要改 Host terminal 语义或用本地 synthetic CANCELLED 才能让测试通过；这表明 owner 越界，不能继续。
- Slice artifact：raw byte→typed key 表、state transition trace、Host public cancel/terminal trace、PTY screen、cleanup task census、focused tests/pyright。
- Residual risk：`MEDIUM`，来自真实终端分块和信号竞态；由 parser chunk matrix、确定性 scheduler tests 与 S8 PTY evidence 收敛。
- 非目标：不支持任意 terminal protocol 扩展，不改变 SIGTERM/EOF 语义，不修改 Host cancel implementation。

---

## 6. S4 — F04：READ_ONLY 保留 REPL，并以 fresh attachment 重试 mutation

### 6.1 前置条件与允许文件

前置条件：S3 `_ActiveTurnCloseout` 已成为 submit/accept 的唯一协调器。仅允许修改：

- `dayu/cli/session_execution.py`
- `tests/cli/test_interactive_command.py`
- `tests/host/test_session_attachment_registry.py`（只增加 Host 已有 typed READ_ONLY owner contract 断言，不改 Host 生产代码）

该owner测试路径已由当前仓库直接确认；不得另建重复测试文件，也不得因此修改 Host 生产实现。README 延迟到 S8。

### 6.2 Typed contract 与精确 call path

在 CLI interactive coordinator 中新增：

- `@dataclass(slots=True) _InteractiveSessionAttachmentController`
  - `current: HostSessionAttachment`
  - `refresh_required: bool`
  - typed `open_fresh()`/`close_current()` callbacks
  - `attachment_for_mutation()`：若 refresh false 返回 current；若 true，先 shield 并等待关闭旧 attachment，再 fresh attach 并替换 current；旧 mode 永不更改。
  - `close()` 幂等，只关闭当前存活 attachment 一次。
- `@dataclass(slots=True) _InteractivePendingMutation`
  - 冻结 normalized prompt、原始 draft、cursor、draft revision、turn index、`client_request_id`。
  - `same_semantic_submission(...)` 只比较 frozen draft revision/content；相同待提交重试复用 identity。
  - 只有 Host 返回 accepted run id 后才能 retire 为 accepted。

composer submit 行为改为两阶段确认：开始 mutation 时不调用 `accept_submit(record_history=True)`、不清 buffer；先创建 pending mutation 并通过 controller 取得 attachment，再提交 Host。结果分支：

```text
Host accepted
  -> _ActiveTurnCloseout.publish accepted id
  -> composer accept_submit/history exactly once
  -> draft 清除，进入 accepted Run 生命周期

HostApiError(detail.kind=session_mutation_access, reason=READ_ONLY)
  -> 展示稳定 READ_ONLY 提示
  -> 不 ack composer，不清 draft/history，不退出 REPL
  -> pending mutation 保留
  -> attachment_controller.refresh_required = True
  -> Run count 不变

下一次 mutation
  -> 若 draft/revision 与 pending 相同：关闭旧 READ_ONLY attachment
     -> fresh attach -> 使用同 client_request_id 重试
  -> 若用户已编辑：retire 未接受 pending（无 durable side effect）
     -> 新 turn identity/client_request_id -> 关闭旧 attachment -> fresh attach
  -> 若仍 READ_ONLY：重复同一拒绝流程；不 promotion
  -> 若 READ_WRITE 且 accepted：exactly one Run，ack once
```

只通过 typed `HostApiError`/`HostSessionMutationErrorDetail` 的 `kind`、`reason=READ_ONLY`、`actual_mode=READ_ONLY` 分派；禁止字符串匹配。其它 Host 错误继续走既有 fatal/typed policy，不一概吞掉。

### 6.3 状态机与不变量

```text
ATTACHED_RW/ATTACHED_RO + draft submit -> MUTATION_PENDING
MUTATION_PENDING + READ_ONLY          -> REPL_RETAINED_REFRESH_REQUIRED
REPL_RETAINED_REFRESH_REQUIRED + next mutation
                                      -> CLOSE_OLD -> FRESH_ATTACH
FRESH_ATTACH + READ_ONLY              -> REPL_RETAINED_REFRESH_REQUIRED
FRESH_ATTACH + READ_WRITE + accepted  -> RUN_ACCEPTED
RUN_ACCEPTED                          -> composer ack once -> S3 closeout/run loop
```

- attachment mode 是 Host 创建时的 immutable truth。CLI 绝不把旧 `READ_ONLY` 改成 `READ_WRITE`，也不从另一个客户端退出推断 mode 已升级。
- fresh attach 必须发生在下一次 mutation 前，而不是后台抢占；先完整关闭旧 attachment，再创建新 attachment，任一时刻该 controller 只有一个 current attachment。
- 同一个未改变的 pending mutation 在 READ_ONLY 拒绝和 fresh attach 重试间保持 `client_request_id`、turn index、prompt 完全一致。
- 用户修改草稿代表新的语义提交，才允许生成新 identity；旧 pending 未被 Host 接受，因此不记 history、不创建 Run。
- Run acceptance 是清草稿/写 history 的唯一 barrier。READ_ONLY rejection 路径 Run count 严格为 0；最终 accepted 路径总 Run count 恰好 1。
- shutdown/cancel/EOF 对 current attachment 幂等关闭；旧 attachment 不重复关闭。

### 6.4 Owner-level tests 与预期断言

- Host owner test：以两个真实 Host attachments 打开同一 session，断言第二个的 access mode 为 READ_ONLY；mutation 返回 typed `session_mutation_access/READ_ONLY/actual_mode=READ_ONLY`，EventLog Run count 不增加，旧 attachment mode 不变。
- CLI concurrent test：A 持有 RW，B 持有 RO；B submit 后仍在 REPL、原 draft/cursor/history 不变、错误一次、submit durable count 0。
- A 退出后，B 对同一 draft 再次 submit：断言 B1 close 完成后才 open B2；B2 是 fresh identity/RW；两次尝试 `client_request_id` 相同；Host 最终只有一个 Run；composer ack/history 恰好一次。
- B fresh attach 仍 RO：重复拒绝，继续保留同一 pending identity/draft，不 mode promotion、不 Run。
- 用户在拒绝后编辑：下一 mutation 使用新 request id；旧 pending 不进入 history；fresh attach 规则仍成立。
- closeout：READ_ONLY 后 EOF、异常和最终 accepted terminal 三条路径均无 attachment leak/double-close。
- queue/accepted path：只有 Host accepted 才进入 queued/active slot，READ_ONLY 不伪装 queued。

聚焦验证命令：

```bash
source .venv/bin/activate
pytest tests/cli/test_interactive_command.py tests/host/test_session_attachment_registry.py -q
python -m pyright dayu/cli/session_execution.py tests/cli/test_interactive_command.py tests/host/test_session_attachment_registry.py
git diff --check
```

### 6.5 Stop signal、产物与 residual risk

- 完成信号：真实双 attachment owner test 与 CLI 状态测试证明“拒绝时零 Run/草稿保留，fresh attach 后一个 Run，同语义 request id 稳定，旧 mode 不变”。
- 立即停止信号：只有修改 Host attachment mode、复用旧 attachment 并提升权限、或从 EventLog/字符串推断 access 才能通过；这些都违反 owner boundary。
- Slice artifact：attachment identity/mode/close-open 时间线、pending mutation identity trace、Run/EventLog count、composer draft/history snapshot、focused tests/pyright。
- Residual risk：`MEDIUM`，来自并发 client 退出与 fresh attach 时序；由 Host public contract、barrier 顺序断言和 S8 真实并发 CLI evidence 收敛。
- 非目标：不做 attachment upgrade API、不自动循环 reattach、不在 READ_ONLY 时后台轮询、不改变 Host 的单写者政策。

---

## 7. S5 — F05：只从 interactive effective tool set 移除 preprocess

### 7.1 前置条件与允许文件

前置条件：S1–S4 owner tests 已通过，且工具发现 baseline 没有被 CLI 状态改动污染。仅允许修改：

- `dayu/config/prompts/manifests/interactive.json`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/runtime/test_scene_prepare.py`
- `tests/tools/test_combined_tools_acceptance.py`

S5 不允许修改 `dayu/fins/tools/preprocess_tools.py`、独立 Fins CLI、tool discovery provider、storage、Host/Engine 或 registry。`dayu/config/README.md`、根 `README.md` 的实际行为说明统一在 S8 更新。

### 7.2 精确变更、call path 与不变量

唯一生产变更是从 `interactive.json` 的 scene tags 删除 `fins-preprocess`；保留其余 tag、顺序和配置字段。不得按 tool name 在 Service/CLI 下游过滤，也不得删除 preprocess provider/实现。

```text
interactive scene manifest（无 fins-preprocess tag）
  -> scene prepare
  -> assemble_effective_tool_provider_configs(...)
  -> discover_service_tools(...)
  -> Host opener 的 interactive effective tool schemas
  -> 不含 start_fins_preprocess

独立 dayu-cli process/preprocess 或其它明确包含 fins-preprocess 的 scene
  -> 现有 Fins preprocess runtime
  -> 行为不变
```

- scene manifest 是该入口 effective tool set 的唯一配置 owner；禁止 CLI 根据工具名做隐藏过滤。
- 只移除 `start_fins_preprocess`；download/list/read 的 manifest tag、discovery、schema 和真实调用保留。
- WeChat 或其它 scene 是否保留 preprocess 只服从自身 manifest；不能由 interactive 的测试期望反推。
- manifest JSON 必须严格可解析，且不通过重排/重写产生无关 diff。

### 7.3 Owner-level tests、完成与 stop signal

- `test_scene_assets_migration.py` 将 interactive 与其它 scene 的期望分开：interactive effective names 精确不含 `start_fins_preprocess`；需要 preprocess 的独立 scene 仍含它。
- `test_entrypoint_runtime_interactive_path.py` 走真实 scene prepare + Service assembly，断言最终传给 Host 的 schema name set 不含 preprocess、仍含 download/list/read。
- `test_scene_prepare.py` 断言 tag 解析顺序/其余配置不变；`test_combined_tools_acceptance.py` 证明 preprocess provider 本身仍可独立发现和调用。
- 不允许通过 mock 固定最终 name set；owner test 至少有一条读取真实 manifest 并走真实 discovery assembly。

聚焦验证：

```bash
source .venv/bin/activate
python -m json.tool dayu/config/prompts/manifests/interactive.json >/dev/null
pytest tests/runtime/test_scene_assets_migration.py tests/service/test_entrypoint_runtime_interactive_path.py tests/runtime/test_scene_prepare.py tests/tools/test_combined_tools_acceptance.py -q
python -m pyright dayu/config tests/runtime/test_scene_assets_migration.py tests/service/test_entrypoint_runtime_interactive_path.py tests/runtime/test_scene_prepare.py tests/tools/test_combined_tools_acceptance.py
git diff --check
```

- 完成信号：真实 assembly 的 interactive set 只少 preprocess；独立 preprocess 及 download/list/read tests 通过。
- 立即停止信号：需要删除/禁用 Fins preprocess 实现，或只能在 Service/CLI 下游按名称过滤；这会改变非目标 owner。
- Slice artifact：manifest before/after semantic name set、Service assembled schemas、独立 preprocess acceptance、JSON/pyright/test 输出。
- Residual risk：`LOW`；主要风险是共享测试把 interactive 与其它 scene 混为一谈，已由分 scene contract test 收敛。
- 非目标：不改变 preprocess 参数、任务状态、storage 或 tool schema。

---

## 8. S6 — F06：typed trigger 无 alias 重命名

### 8.1 前置条件与允许文件

前置条件：S5 完成；确认 `docs/host/design.md` 仅需标识更新、既有 governance-resolved 语义不变。仅允许修改：

- `dayu/host/run_input.py`
- `dayu/host/_runner_call_manifest.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_tool_trace_projection.py`
- `docs/host/design.md`

Host README 的读者向说明统一在 S8 更新。归档、首轮 evidence、frozen registry、Engine 生产代码不修改。

### 8.2 精确 contract、机械映射与传播闭包

F06 是 fresh contract rename，不是兼容迁移。旧 active symbol/literal 到 fresh v2-era symbol/literal 的机械映射只有以下两行：

| 旧 active contract | fresh contract | 处理 |
|---|---|---|
| `_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED` | `_RUNNER_CALL_TRIGGER_CONTEXT_GOVERNANCE_RESOLVED` | 删除旧 symbol，直接改所有引用；不 alias/re-export |
| `"context_compaction_completed"` | `"context_governance_resolved"` | 新 manifest只序列化/接受新 literal；旧 literal严格 unknown/fail closed |

传播闭包按 owner 固定为：

| 环节 | 文件 / owner | 精确动作 |
|---|---|---|
| producer | `dayu/host/run_input.py` | `_prepared_candidate_kind_and_trigger(...)` 中 accepted compact 与 existing fallback resolution 两个生产点都返回新 symbol；trigger只表达 governance resolved |
| persistence + strict reader | `dayu/host/_runner_call_manifest.py` | closed allowlist删除旧 literal、加入新 literal；serialize/parse/hot payload round-trip不得 normalize |
| ingest reader | `dayu/host/engine_ingest.py` | 当前 generic manifest reader不含旧 literal分支，因此生产代码不改；由 `tests/host/test_engine_ingest_mapping.py` 增加新值读取、old/unknown拒绝与 hot link断言 |
| projection | `dayu/host/tool_trace.py` / `dayu/host/durable/tool_trace.py` | 当前只透传 strict manifest typed field、无旧 literal分支，因此生产代码不改；由 `tests/host/test_tool_trace_projection.py` 断言 public trace只保留新值且不反推 outcome |
| owner tests | `tests/host/test_run_input_builder.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_tool_trace_projection.py` | 覆盖 success/fallback producer、strict durable round-trip、reader/projection与旧值拒绝 |
| design | `docs/host/design.md` | active trigger表和流程文字机械改为新 literal；canonical terminal / fallback refs ownership不变 |

不存在需要迁移的旧 manifest reader、旧 durable DB或 active fallback。若新代码读到旧 literal，只能按 strict unknown contract fail closed；这不构成旧库兼容承诺。

```text
Host governance success 或已批准 fallback resolution
  -> RunInput prepared candidate
  -> trigger=context_governance_resolved
  -> strict RunnerCallManifest
  -> Engine typed ingest

Host canonical outcome/event/artifact refs
  -> 保持既有 terminal owner
  -> 不从 trigger 反推 terminal
```

### 8.3 测试、不变量、完成与 stop signal

- success 与 fallback 两条 RunInput 映射都精确得到新 trigger；同一次 resolution 只有一个 trigger。
- manifest serialize/parse/hot payload round-trip 新值；手工输入旧值精确失败；未知值同样失败。
- engine ingest mapping 与 tool trace projection tests 断言只透传新值，不生成/重算 outcome，不从 trigger构造 success/failure。
- terminal event/outcome/artifact refs 的既有断言保持，证明 rename 未转移 terminal ownership。
- active code/design 扫描旧标识零命中；归档和 frozen baseline/evidence 的历史文本不在修改范围。

聚焦验证：

```bash
source .venv/bin/activate
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py -q
python -m pyright dayu/host/run_input.py dayu/host/_runner_call_manifest.py tests/host/test_engine_ingest_mapping.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py
rg -n 'context_compaction_completed|CONTEXT_COMPACTION_COMPLETED|_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED' dayu/host tests/host docs/host/design.md
rg -n 'context_governance_resolved|_RUNNER_CALL_TRIGGER_CONTEXT_GOVERNANCE_RESOLVED' dayu/host tests/host docs/host/design.md
git diff --check
```

- 第一个 `rg` 的完成条件是零命中；第二个 `rg` 必须覆盖 producer、strict manifest、owner tests和design。archive、两份 frozen registry与immutable evidence不进入零残留修改范围。
- 完成信号：active producer/persistence/reader/projection/test/design只含 `context_governance_resolved`；旧 symbol/literal严格拒绝；terminal contract无变化。
- 立即停止信号：直接证据表明某个冻结外部 public consumer 被当前 work unit 明确要求继续发送旧值；不得添加 alias，须报告 contract blocker。当前证据不存在该冲突。
- Slice artifact：新旧值 parser matrix、success/fallback RunInput manifest、terminal identity 对照、active scan、focused tests/pyright。
- Residual risk：`LOW`；fresh contract 无兼容要求，风险主要是漏改 active allowlist，由严格 parse 与扫描覆盖。
- 非目标：不重命名 terminal outcome/event，不修改 Engine 调度语义。

---

## 9. S7 — F07：Host Context Governance 原子 closure

### 9.1 原子边界、前置条件与允许文件

前置条件：S6 新 trigger 已生效；S7 开始前冻结现有 Host compact owner tests 和 Memory policy snapshot。`MemoryProjectionPolicy` 与 `estimate_memory_size_units()` 的 owner 已由直接代码确认同在 `dayu/host/memory.py`，该文件已在 allowlist；implementation不得再猜 owner或复制 estimator。S7 保持一个 outer slice、一次 code review loop和一个 accepted slice commit；内部只按 §9.8 的四个 checkpoint增量验证，不得 stash、创建新 branch、stage/commit中间状态或引入兼容 commit。只有全部 owner tests和投影一致性通过后，S7才整体完成。

允许修改的生产/设计文件严格为：

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/context_governance.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/compact_payload.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/compact_artifact.py`
- `dayu/host/context_events.py`
- `dayu/host/memory.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/run_input.py`
- `dayu/host/tool_trace.py`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `dayu/config/prompts/scenes/conversation_compaction.md`
- `docs/host/design.md`

允许修改的测试文件严格为：

- `tests/host/fake_compaction.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_compaction_terminal.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/runtime/test_scene_prepare.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`

不允许修改 Engine 生产文件、frozen CLI docs/registry、Fins、CLI 或 Service production。README 在 S8 更新。

### 9.2 Fresh input/source-boundary contract（无兼容路径）

#### 9.2.1 旧 active contract 到 fresh v2 contract 的机械映射

以下映射必须一次完成；旧 symbol删除，不允许 alias、兼容 re-export、migration、fallback reader或 dual-schema branch：

| 旧 active symbol / literal | fresh v2 symbol / literal |
|---|---|
| `CONVERSATION_COMPACT_INPUT_SCHEMA_VERSION_VNEXT` / `"conversation_compact_input_v1"` | `COMPACT_INPUT_SCHEMA_V2` / `"dayu.context_compaction.input.v2"` |
| `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`、`CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` / `"conversation_compact_output_v1"` | `COMPACT_OUTPUT_SCHEMA_V2` / `"dayu.context_compaction.output.v2"` |
| `ConversationCompactInputVNext` | `CompactInputV2` |
| `ConversationCompactOutputVNext` | `CompactCandidateV2` |
| `ConversationCompactLabelSectionVNext` | 删除；input引用空间由 `CompactSourceKindV2`，output业务区由 `CompactSemanticSectionV2` 分别拥有 |
| `CompactReadableViewVNext` | 删除；previous summary/fact/anchor/intent/reference逐项进入 `CompactSourceBoundaryEntryV2` |
| `CompactCandidateDiagnosticVNext` | `CompactCandidateDiagnosticV2` |
| `CompactQualityIssueVNext` | `CompactValidationIssueCodeV2` |
| `CompactQualityCheckResultVNext` | reject arm=`CompactValidationReportV2`；success arm=`CompactAcceptedTruthV2`，不再用 `accepted: bool` bag |

字段层也只做 fresh replacement：input 的 `schema_version/current_input_anchor/previous_compacted_view/*_material` 收敛为 `schema/current_input/source_boundary`；output 的 `schema_version/evidence_backed_facts/reference_continuity_items` 收敛为 `schema/evidence_facts/reference_continuity`，其余字段严格使用本节下方 v2 shape。旧字段不得作为兼容 key保留。

传播闭包固定如下，implementation artifact必须逐行打勾：

| 环节 | 文件 | v2 更新 |
|---|---|---|
| contract definition / canonical JSON | `dayu/host/compaction.py` | 删除旧 symbols/literals/fields并定义全部v2 types与serializer |
| input producer / rolling source boundary | `dayu/host/compact_material.py` | 从 committed material与latest accepted compact event逐项生成v2 boundary |
| LLM-facing producer / strict parser | `dayu/host/llm_compaction.py`、两个 conversation compaction prompts | 自足v2 schema、strict parse、whole-candidate repair feedback |
| accept / operation / reactive queue | `dayu/host/context_governance.py`、`dayu/host/compaction_operation.py`、`dayu/host/compact_pipeline.py` | v2 validation、per-pass truth、operation-root aggregate truth；保留 reactive queue |
| persistence / canonical reader | `dayu/host/compact_payload.py`、`dayu/host/compact_artifact.py`、`dayu/host/context_events.py` | 只写/读strict v2 semantic payload；event是committed truth owner |
| terminal writer / reactive owner | `dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` | permit下提交唯一terminal；中间pass不可见 |
| projection / next input / trace | `dayu/host/memory.py`、`dayu/host/run_input.py`、`dayu/host/tool_trace.py` | 只消费committed strict v2 event projection；不重读raw response、不直连未提交truth |
| tests / fake / public smoke | §9.1列出的全部test文件 | fresh v2 construction、old symbol/literal/key拒绝、single/multi-pass与跨投影同源 |
| design | `docs/host/design.md` | active I/O shape、accept/repair/multi-pass/event→Memory数据流机械更新，无迁移叙事 |

旧 durable DB 不迁移且不提供兼容读取/测试；本 work unit按全新 schema起库。active parser中旧 v1 payload的严格拒绝仅证明 fresh schema输入边界，不承诺旧数据库可继续打开。

#### 9.2.2 Fresh v2 input contract

`dayu.host.compaction` 定义并唯一导出以下 v2 typed contract；v1 parser/alias/compat branch 全部删除：

- `COMPACT_INPUT_SCHEMA_V2 = "dayu.context_compaction.input.v2"`
- `COMPACT_OUTPUT_SCHEMA_V2 = "dayu.context_compaction.output.v2"`
- `CompactSourceKindV2(StrEnum)` 精确值：
  - `previous_session_summary`
  - `previous_evidence_fact`
  - `previous_answer_anchor`
  - `previous_forward_intent`
  - `previous_reference_continuity`
  - `trace_material`
  - `evidence_material`
  - `answer_material`
- `CompactSemanticSectionV2(StrEnum)` 精确值：`session_summary`、`evidence_facts`、`answer_anchors`、`forward_intents`、`reference_continuity`。
- `CompactCurrentInputV2`：`source_ref: str`、`readable_text: str`。它是本轮必须保留的 input anchor，不分配 source label，不进入 represented/dropped coverage，也不能被 candidate 引用。
- `CompactSourceBoundaryEntryV2`：
  - `source_label: str`：Host 在本次请求内生成的唯一稳定引用标签；只作引用，不是业务事实。
  - `source_kind: CompactSourceKindV2`
  - `source_refs: tuple[str, ...]`：唯一、非空 canonical refs；不得投影给 LLM。
  - `readable_text: str`：经 Host 做 LLM-facing 自解释转换的业务可读内容。
- `CompactInputV2`：`schema: Literal[COMPACT_INPUT_SCHEMA_V2]`、`current_input: CompactCurrentInputV2`、`source_boundary: tuple[CompactSourceBoundaryEntryV2, ...]`。source boundary 精确等于此次允许 compact/删除/替代的全部 citable semantic inputs；顺序由 Host 固定，label 唯一，空 boundary 走既有 no-op/selection 路径而不调用 compactor。

`compact_material.py` 是 input material/source-boundary builder；它从当前 Memory 的每个已有 summary/fact/anchor/intent/reference 项和本轮选中 raw trace/evidence/answer material生成逐项 typed entry，不再用一个粗粒度 previous summary section 隐藏来源。`current_input` 单独传入并始终进入下一轮 RunInput，不得被 compaction coverage 删除。

### 9.3 Fresh candidate、represented coverage 与 explicitly dropped coverage

LLM 输出只允许 `CompactCandidateV2`，字段精确为：

- `schema: Literal[COMPACT_OUTPUT_SCHEMA_V2]`
- `session_summary: CompactSessionSummaryV2 | None`
  - `text: str`
  - `source_labels: tuple[str, ...]`
- `evidence_facts: tuple[CompactEvidenceFactV2, ...]`
  - `claim: str`
  - `support_labels: tuple[str, ...]`（非空，只允许 `evidence_material`/`previous_evidence_fact`）
  - `context_labels: tuple[str, ...]`（可空，只允许 `trace_material`/`answer_material`）
- `answer_anchors: tuple[CompactAnswerAnchorV2, ...]`
  - `title: str`
  - `detail: str`
  - `source_labels: tuple[str, ...]`（只允许 `answer_material`/`previous_answer_anchor`）
- `forward_intents: tuple[CompactForwardIntentV2, ...]`
  - `intent_type: str`
  - `text: str`
  - `status: CompactForwardIntentStatusV2`（沿用现行闭集语义但以 v2 type 表达）
  - `source_labels: tuple[str, ...]`（只允许 `trace_material`/`answer_material`/`previous_forward_intent`）
- `reference_continuity: tuple[CompactReferenceContinuityV2, ...]`
  - `text: str`
  - `reason: str`
  - `source_labels: tuple[str, ...]`（只允许 `trace_material`/`evidence_material`/`answer_material`/`previous_reference_continuity`）
- `diagnostics: tuple[CompactCandidateDiagnosticV2, ...]`
  - `code: str`
  - `message: str`
  - `source_labels: tuple[str, ...]`
  - diagnostics 只解释问题，永不算 represented semantic coverage。
- `explicitly_dropped_sources: tuple[CompactExplicitDropV2, ...]`
  - `source_label: str`
  - `reason: CompactDropReasonV2`

`CompactDropReasonV2` 精确闭集：`superseded`、`redundant`、`out_of_scope`、`policy_limit`。不得接受自由文本、alias 或 unknown reason。

Host 在 `context_governance.py` 从 candidate 的五个 business semantic sections 派生而非接收以下类型：

- `CompactRepresentedSourceV2`：`source_label: str`、`sections: tuple[CompactSemanticSectionV2, ...]`；sections 去重并按 enum 固定顺序。
- `CompactRepresentedCoverageV2`：`sources: tuple[CompactRepresentedSourceV2, ...]`；其 label set 由 `sources` 计算，不再持久化第二份手填 list。
- `CompactExplicitlyDroppedCoverageV2`：`drops: tuple[CompactExplicitDropV2, ...]`；由严格输出字段构造并验证。
- `CompactAcceptedTruthV2`：`candidate`、`source_boundary`、`represented_coverage`、`explicitly_dropped_coverage`、`current_input_ref`。该类型构造器私有，只能由 acceptance function 成功返回；`covered_source_refs` 是按 boundary 中 represented∪dropped labels 计算的 property，不是另存字段。

覆盖不变量：

```text
boundary_labels == represented_labels ∪ explicitly_dropped_labels
represented_labels ∩ explicitly_dropped_labels == ∅
```

所有 label 必须已知且各 list 内唯一。非空 boundary 必须至少有一个 represented business source；全 drop、五个 semantic section 全空、只有 diagnostics、只有 summary 空白、或 represented 仅来自空白 item 都以 `LOW_INFORMATION_OUTPUT`/对应精确 issue 拒绝。summary 可引用任意 boundary kind；其它 section 必须遵守上述 source-kind matrix。Host 不让 LLM 回报单独 `represented_source_labels`，从而消除 candidate 与 coverage 的重复真源。

### 9.4 严格 JSON 边界、deterministic validity 与共享 policy cap

`llm_compaction.py` 的 raw JSON boundary 使用 `json.loads(..., object_pairs_hook=...)` 保留每层 pairs，在转成 dict/dataclass 前递归检测 duplicate keys。top-level 与每种 nested object 都有 exact required/optional key set：unknown key、missing required key、duplicate key、错误类型、空白 required text、非闭集 enum 均拒绝；Python 默认“后值覆盖前值”不得发生。v1 schema、缺 schema 和其它 schema 都拒绝。

`context_governance.py` 是 candidate validity 唯一 owner，并按固定次序产生 issues：strict shape → label/source-kind → coverage completeness/disjointness → duplicate/contradiction → information floor → policy caps。确定性规则：

- semantic duplicate identity 忽略 provenance 顺序：fact=`claim`；anchor=`title+detail`；intent=`intent_type+text`；reference=`text`；diagnostic=`code+message`。文本用现有统一 whitespace canonicalizer，不做模糊相似度。
- contradiction 只判 schema 可证明冲突：同一 `intent_type+text` 出现不同 status；同一 reference text 出现不同 reason；同一 drop label 出现不同 reason；represented/drop overlap。不得凭自然语言判断事实真假。
- source label tuple 去重并按 source-boundary 顺序 canonicalize；同一个 item 重复 label 拒绝，不静默去重。
- policy caps 直接接收 `dayu/host/memory.py` 已有 `MemoryProjectionPolicy` typed instance，并调用该模块同一个 `estimate_memory_size_units`/同一 item count、summary chars、各 section count/size limit。禁止在 Context Governance 复制 cap常量、另写估算器或implementation-time重新寻找owner。
- acceptance 前检查 candidate投影后各项和总量。Memory不直接接收内存中的 `CompactAcceptedTruthV2`；它只消费 terminal owner 已提交的 canonical `CONTEXT_COMPACTED` event，经 `context_events.py` strict v2 semantic parser恢复的 projection。Memory移除 downstream truncate/merge/default补偿；若 committed v2 semantic projection在 Memory再违反同一 policy，视为 projection invariant error并停止该projection/catch-up，不把 rejected或未提交对象改写成Memory truth。

### 9.5 Validation issues 与 bounded redacted repair feedback

定义 `CompactValidationIssueCodeV2(StrEnum)` 闭集：

- `invalid_json`
- `duplicate_json_key`
- `unknown_json_key`
- `missing_required_key`
- `invalid_field_type`
- `invalid_enum_value`
- `blank_required_text`
- `unknown_source_label`
- `duplicate_source_label`
- `source_kind_mismatch`
- `duplicate_drop_label`
- `represented_and_dropped`
- `uncovered_source`
- `duplicate_semantic_item`
- `contradictory_semantic_item`
- `empty_semantic_output`
- `diagnostics_only_output`
- `low_information_output`
- `policy_item_cap_exceeded`
- `policy_size_cap_exceeded`

类型固定为：

- `CompactValidationIssueV2`：`code`、`json_path: str`、`message: str`、`source_labels: tuple[str, ...]`。
- `CompactValidationReportV2`：`issues: tuple[CompactValidationIssueV2, ...]`，按 `code/json_path/source_labels` 稳定排序并精确去重。
- `CompactRepairFeedbackV2`：`previous_attempt_number: int`、`issues`、`additional_issue_count: int`、`required_action: str`。

边界常量固定为 `MAX_COMPACT_REPAIR_ISSUES = 32`、`MAX_COMPACT_REPAIR_ISSUE_MESSAGE_CHARS = 240`、`MAX_COMPACT_REPAIR_FEEDBACK_CHARS = 8192`。超过 32 个只取稳定排序前 32 个并记录 remainder；单条和总长按字符边界截断。feedback 不含 raw candidate 片段、input readable text、canonical refs、event/tool-call id、digest、cursor、路径、环境或 secret；只允许 issue enum、JSON path、允许字段/enum提示和 opaque source label。message 必须自解释，例如指出哪个 path 需要哪个字段/允许哪些 source kinds。`required_action` 固定要求“返回一个完整 replacement candidate，不是 patch，也不得沿用先前 JSON”。

`prepare_compactor`/`compact` protocol 以直接 typed 参数接收 `repair_feedback: CompactRepairFeedbackV2 | None`，不得塞入 extra payload。第一次为 `None`；candidate validation reject 后下一 attempt 接收前一次 report；Runner execution/transport failure 的重试不伪造 validation feedback。每次 prepared prompt/manifest digest 必须包含本次 feedback，业务 source boundary 保持 immutable。

### 9.6 Attempt、accept、terminal 与投影数据流

保留 `CompactPipelinePassQueuePlan`、`build_reactive_pass_queue_plan(...)` 与 operation-level bounded reactive multi-pass；修复的是当前“最后一个 pass candidate 冒充整个 operation accepted truth”的错误，不删除 queue。single-pass 与 multi-pass 共用同一 accept/terminal owner。

`CompactPipelinePassQueuePlan` 同时保存 immutable root `CompactInputV2` 与按 material block/evidence chunk 确定性切分的 pass inputs。各 pass 的 citable source boundary 是 root boundary 的稳定、互斥子集；current input仍只是每个pass的不可引用保护锚点。queue order、pass id、boundary digest在operation开始时冻结，repair不得改变。

每个 pass 的流程固定为：

```text
immutable pass CompactInputV2
  -> attempt N prepare（N>1 可带该pass前次redacted feedback）
  -> Runner raw response
  -> strict JSON parse
  -> Context Governance validate + derive coverage + shared policy caps
     -> rejected：记录 attempt diagnostic；不写 artifact/event/Memory/RunInput
                  若operation全局预算允许，对同一pass做whole-candidate replacement
     -> accepted：形成 operation-private CompactPassAcceptedTruthV2
```

`CompactPassAcceptedTruthV2` 只存在于 operation内存，或进入受控、bounded transient diagnostic artifact；它不是 durable accepted compact truth。所有 required passes accepted 后，operation owner按 frozen queue order机械合并：tuple semantic sections/diagnostics/drops按pass顺序拼接；多个非空 `session_summary` 仅按pass顺序用单个换行连接文本并按root boundary顺序合并source labels，不做自然语言改写。随后必须针对 **root** `CompactInputV2` 重新执行：

1. exact coverage partition / represented-vs-drop disjointness；
2. cross-pass semantic duplicate与schema-provable contradiction；
3. `MemoryProjectionPolicy` item/char/size caps；
4. operation-root post-compact hard budget。

root report拒绝时，不得发布已accepted pass。若剩余全局attempt budget允许，按稳定规则把issue路由到最后一个贡献该section/source label的pass，废弃该pass truth，并向同一immutable pass input提供bounded redacted feedback，要求整个candidate重产；无可归属的root coverage/invariant issue直接fail closed。每次重产仍消耗 `max_compaction_attempts_per_operation`。只有root四类重验全部通过，私有构造器才生成整个operation唯一 `CompactAcceptedTruthV2`；全局预算不能收口时operation失败。

operation terminal流程固定：

```text
single-pass accepted truth / multi-pass aggregate accepted truth
  -> existing hard budget + CompactionTerminalCommitPermit
  -> 原子选择一次 canonical outcome
     -> success：terminal owner写compact artifact descriptor与strict v2
                CONTEXT_COMPACTED semantic payload
     -> 任一pass exhaust / aggregate无法在剩余预算收口：只写一个
                CONTEXT_COMPACTION_FAILED，再走既有fallback/fail-closed
  -> canonical event commit后，Memory projector追平event
  -> ordinary RunInput/tool trace只读取committed compact fact或typed fallback refs
```

`CompactionOperationResult` 的 success arm精确携带 `accepted_truth: CompactAcceptedTruthV2`；failure arm不得携带partial candidate或pass truth。`compact_payload.py`从 final accepted truth构造v2 semantic payload；`compact_artifact.py`保存相同aggregate candidate、root typed boundary、derived represented coverage和dropped coverage；`context_events.py`只从已提交 canonical event strict parse semantic payload，并重新验证schema、root coverage等式与digest identity。

Memory数据流只能是：

```text
Context Governance final CompactAcceptedTruthV2
  -> terminal owner + commit permit
  -> compact artifact + canonical CONTEXT_COMPACTED strict v2 semantic payload
  -> commit成功
  -> context_events strict semantic projection
  -> Memory projector按event sequence更新snapshot
```

禁止 `context_governance.py`、operation result或terminal helper把未提交 `CompactAcceptedTruthV2` 直接传给 `memory.py`。`memory.py`只从 committed event projection恢复candidate/root boundary/coverage，并用accepted candidate **替换** summary/facts/anchors/intents/references，不保留旧summary、不merge旧items；旧semantic item已作为 previous-* boundary entry，必须被final candidate represented或explicitly dropped。选中raw recent material只在final derived `covered_source_refs`覆盖后删除。失败terminal、tier 4/5 fallback input和rejected candidate都不是 accepted compact truth，Memory不得消费；fallback连续性只由 `CONTEXT_COMPACTION_FAILED`、typed fallback input refs和fallback manifest拥有。

中间 pass不得写canonical terminal、Memory、ordinary RunInput、public tool trace或accepted artifact descriptor。`run_input.py`从 committed Memory snapshot和compact artifact/canonical event引用构造下一输入，不重新解析raw LLM JSON。`tool_trace.py`、artifact descriptor、EventLog和RunInput的outcome/artifact identity/coverage digest必须来自同一次terminal commit。`dispatch.py`/`engine_ingest.py`复用existing `CompactionTerminalCommitPermit`：permit关闭后到达的success/failure只能成为late diagnostic，不得写第二artifact、第二Memory或第二terminal。

### 9.7 Rolling compact、fallback 与 stale/late 不变量

- 第二次 compact 时，第一次 accepted summary/fact/anchor/intent/reference 各自成为 typed previous-* source boundary；新 candidate 必须逐项 represented 或 drop。接受后 Memory 只含第二次 accepted truth，不同时残留第一次旧版本。
- 两次后续 ordinary followup 的 RunInput 必须读取相同 committed compact truth；不能一轮从 artifact、另一轮从旧 Memory/raw tail 重算。
- single-pass repair与每个reactive pass repair永远面对各自完整、immutable input boundary，只改变bounded validation feedback；不得把上一rejected candidate的部分section materialize成下一输入。
- reactive queue全部pass accepted后仍必须root重验；current pass或aggregate未通过时，任何中间accepted pass都不能成为durable truth。
- attempt exhaust恰好走现有fallback/fail-closed决策，且只提交一个canonical `CONTEXT_COMPACTION_FAILED`。tier 1-3若最终产生合法accepted compact，仍必须走相同final truth/event投影；tier 4-5只拥有fallback input refs/manifest，不能称为accepted compact truth。
- stale/late candidate 无论更好或有效都不能覆盖已提交 outcome；只允许 bounded diagnostic，且不改变 artifact identity、Memory revision、RunInput 或 trace terminal。
- current input anchor 不在 coverage 中，始终保留；accepted compact 不能删除本轮用户输入。

### 9.8 Owner-level tests、completion 与 stop signal

必须覆盖：

1. strict JSON：每个对象层级 duplicate key、unknown key、missing/type/enum；旧 v1 精确拒绝。
2. source coverage：unknown/duplicate label、kind mismatch、uncovered、represented/drop overlap、duplicate drop/reason；合法 exact partition。
3. semantic quality：full-empty、diagnostics-only、all-drop、低信息、精确 duplicate/contradiction；自然语言不同但相似文本不误判。
4. caps：对每个 Memory policy count/char/size cap 的边界值 `==` 接受、`+1` 拒绝；验证 Context Governance 和 Memory 使用同一 policy instance/estimator，无下游截断。
5. repair：首次无 feedback；invalid 后 feedback code/path/message 自解释、无 raw文本/ref/digest；32/240/8192 caps；第二次完整 candidate success；rolling invalid reports；execution failure不带 validation feedback。
6. materialization：rejected attempt和中间accepted pass的canonical artifact/event/Memory/ordinary RunInput写入计数全为0；final accepted truth的artifact/event各一次，event commit后Memory才追平，并共享identity/coverage。
7. reactive multi-pass：`CompactPipelinePassQueuePlan`按root boundary形成immutable/disjoint pass boundaries；每pass whole-candidate repair；全部pass accepted后root coverage/duplicate/caps/budget重验；跨pass duplicate、aggregate cap、root budget失败可在剩余attempt预算内完整重产，无法收口时只有一个failure terminal。
8. exhaust/terminal：single-pass与multi-pass的all-invalid、mixed execution+invalid、late success、late failure、cancel race都恰好一个canonical terminal；fallback/fail-closed保持现有policy。
9. rolling：single-pass和reactive multi-pass第一次compact后再compact，previous-*边界完整；第二次accepted replacement后Memory无旧残留；两个followup RunInput、artifact、EventLog、trace一致。
10. public smoke：真实prompt/schema经Service assembly和Host public API，合法candidate可accepted，非法candidate不能通过fake bypass；fake必须实现同一typed contract。

S7 内部 checkpoint 只用于缩小故障面，不改变单一 outer slice/accepted commit边界；每个checkpoint都在同一working tree继续，禁止 stash、新branch、中间stage/commit或old/new compatibility状态：

| checkpoint | implementation closure | focused tests / pyright |
|---|---|---|
| A — schema + source boundary | `compaction.py`、`compact_material.py`、两个prompt、fake构造 | `test_compaction_contract.py`、`test_compact_material.py`、`test_scene_prepare.py`；对应模块与tests pyright |
| B — strict parser + accept | `llm_compaction.py`、`context_governance.py` | `test_llm_compaction.py`、`test_compaction_contract.py`；duplicate/unknown/coverage/caps矩阵与对应pyright |
| C — repair + operation | `compaction_operation.py`、repair feedback/manifest路径 | `test_compaction_operation.py`、`test_llm_compaction.py`；whole-candidate feedback/exhaust与对应pyright |
| D — projection + multi-pass | `compact_pipeline.py`、payload/artifact/events、Memory、dispatch/ingest、RunInput、trace | `test_compact_pipeline.py`、`test_context_compact_events.py`、`test_compact_artifact_store.py`、`test_memory_projection.py`、`test_dispatch_scheduler.py`、`test_engine_ingest_mapping.py`、`test_run_input_builder.py`、`test_compaction_terminal.py`；single/multi-pass与对应pyright |

每个内部checkpoint完成即运行表中focused tests和仅当前闭包的pyright；D完成后再运行以下S7整体验证，只有整体结果用于review/accepted slice commit：

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_terminal.py tests/host/test_public_compact_smoke.py tests/runtime/test_scene_prepare.py tests/service/test_entrypoint_runtime_interactive_path.py -q
python -m pyright dayu/host dayu/config tests/host tests/runtime/test_scene_prepare.py tests/service/test_entrypoint_runtime_interactive_path.py
rg -n 'conversation_compact_(input|output)_v1|CONVERSATION_COMPACT_(INPUT|OUTPUT)_SCHEMA_VERSION_VNEXT|CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT|ConversationCompact(Input|Output)VNext|ConversationCompactLabelSectionVNext|CompactReadableViewVNext|CompactCandidateDiagnosticVNext|CompactQuality(Issue|CheckResult)VNext' dayu/host dayu/config tests/host tests/runtime/test_scene_prepare.py tests/service/test_entrypoint_runtime_interactive_path.py docs/host/design.md
rg -n 'CompactPipelinePassQueuePlan|build_reactive_pass_queue_plan' dayu/host/compact_pipeline.py dayu/host/engine_ingest.py tests/host/test_compact_pipeline.py tests/host/test_compaction_operation.py tests/host/test_engine_ingest_mapping.py docs/host/design.md
git diff --check
```

- 第一个 `rg` 必须零命中；第二个 `rg` 必须证明reactive queue builder、operation consumer与owner tests仍存在。不得把保留的 `pass_queue` 当残留删除。
- 完成信号：上述十类contract全通过；fresh schema旧值/旧symbol零active consumer；single-pass或全部reactive passes root重验后都只形成一个final accepted truth；canonical event commit后派生Memory/RunInput/trace；S7 staged diff是原子闭包。
- 立即停止信号：冻结 accepted oracle 与 Host single-owner invariant出现不可同时满足的直接反例；或必须让 rejected partial 写入、复制 Memory cap、在 Engine/CLI 补偿才能通过。不得以兼容 schema/loose parser继续。
- Slice artifact：v2 schema samples、source-kind/section matrix、validation matrix、repair transcripts（redacted）、attempt/terminal timeline、artifact/EventLog/Memory/RunInput/trace identity comparison、rolling两轮 snapshots、focused tests/pyright/coverage。
- Residual risk：`HIGH`，因为这是 schema、governance、durable projection和竞态的原子变更；以 strict owner tests、真实两轮 CLI evidence、single-commit boundary 和不兼容启动政策降低。残余自然语言事实质量属于模型评估风险，不由 deterministic validator伪装解决。
- 非目标：不做通用 JSON Schema 框架、不引入多阶段 DAG/新数据库、不做语义 embedding 去重、不改变 Engine outcome owner。

---

## 10. S8 — Post-fix integration、真实 evidence 与文档

### 10.1 前置条件与允许文件

前置条件：S1–S7 owner tests/pyright完成；S7 没有 partial schema；目标 commit 可在 detached worktree 中 clean checkout。S8 repo 内只允许修改：

- `README.md`
- `dayu/host/README.md`
- `dayu/config/README.md`
- `tests/README.md`

S8 不再修改生产代码、测试语义、`docs/host/design.md` 或任何 frozen source。真实 evidence 写在 repo 外新的 `/Users/leo/workspace/.dayu-cli-ci/<run-id>/`，不 stage 进 repo。

已阅读相应 README 的 Agent 更新约束后，更新决策固定为：

- 根 `README.md`：**更新**。F01 改变用户可见 CLI grammar/help；删除所有全局 `--config` 示例/排障，说明使用 workspace config。F05 若根文档承诺 interactive preprocess，则精确改为 download/list/read 与独立 preprocess入口，不扩写开发内部。
- `dayu/host/README.md`：**更新**。面向当前开发者说明新 trigger、v2 accept barrier、accepted truth 单源和 terminal ownership；不保留历史迁移叙事。
- `dayu/config/README.md`：**更新**。该文件没有更窄的本地 Agent 约束，按根约束只同步 interactive manifest tag 与 compaction prompt v2 自足 contract；明确 `start_fins_preprocess` 仍为独立能力。
- `tests/README.md`：**更新**。登记 F01–F07 owner test 所属层和 real-oracle smoke，不罗列每个测试函数。
- `dayu/README.md`：**不更新**，UI→Service→Host→Engine 分层和装配关系未变。
- `dayu/engine/README.md`、`docs/engine/design.md`：**不更新**，Engine 无生产变更且不拥有新语义。
- `dayu/fins/README.md`：**不更新**，Fins preprocess/storage contract 未变。
- `dayu/service/README.md`：**不更新**。本次 plan fix 已用 `rg` 直接确认该 README 不记录 `EntrypointRuntimeRequest`、`ServiceHostAdminRequest`、`explicit_config_dir` 或 `config_overlay_dir`；S1字段删除不改变其读者向职责或既有内容。
- `docs/cli_ci.md`、两个 registry：**不更新**，它们是 frozen oracle/baseline。

### 10.2 Integration 与真实断言

按 S1–S7 顺序做一次无 mock integrated CLI/Host 验证：

- F01：所有 parser/help入口无 `--config`，传入时在 Service/Host打开前失败。
- F02：显式 nonexistent/nonexec/launch `OSError`均 actionable、无 traceback、草稿保留、REPL继续、零Run；显式nonzero静默cancel并保留草稿；zero才回填；真正unset才允许public system fallback。
- F03：standalone Escape取消；CSI/Home/Delete/Alt/bracketed paste不取消；pre-accept Escape/Ctrl+C跨 barrier；double Ctrl+C等待 Host CANCELLED和全部 cleanup后130。
- F04：双客户端 concurrent session；B READ_ONLY拒绝后留在REPL/保留draft/零Run；A退出，B关闭旧 attachment、fresh attach；同一 request id、最终恰好一Run、不提升旧 mode。
- F05：interactive effective set无 preprocess；跨真实 turns调用download/list/read；独立 preprocess仍成功。
- F06：success/fallback manifest只含 `context_governance_resolved`；terminal outcome/refs仍来自Host canonical terminal。
- F07：single-pass与reactive multi-pass各至少一条valid accepted coverage + artifact identity + 两次followup；每pass whole-candidate repair、全部pass后root重验；invalid duplicate/unknown/coverage/cap触发repair；exhaust走既有fallback/fail-closed且单terminal；Memory只从committed event追平并与RunInput/artifact/trace一致。

每条 evidence 都必须从 Host public reads、EventLog、Tool Trace、Memory、RunInput 和 artifact descriptor 取证；SQLite 只可做诊断旁证，不能替代 public contract。screen recording 与命令输出不得包含 credential、header、完整 env 或未脱敏模型响应中的 secret。

### 10.3 完成/stop signal、产物与 residual risk

- 完成信号：全量矩阵通过；fresh real evidence 满足所有 frozen scenario；文档与最终代码一致；registry/evidence基线摘要不变。
- 立即停止信号：目标 commit不clean、provider身份/模型不可证、evidence需覆盖旧bundle、需要改oracle才能判通过，或任一F01–F07真实断言与owner test不一致。
- provider credentials、配额、网络或模型不可用时，S8状态固定为 `BLOCKED-ON-REAL-EVIDENCE`，不得closeout pass；保留该次失败bundle，current/next gate都仍为 **S8 real-evidence acquisition**。provider恢复后必须使用新run id重新执行，不复用、解锁或覆盖旧bundle，也不退回S1–S7。
- Slice artifact：全量测试/pyright/coverage/json/diff输出、README trigger checklist、fresh evidence bundle + `SHA256SUMS`、scenario→evidence索引、最终 residual-risk register。
- Residual risk：`MEDIUM`，来自真实 provider、PTY和并发时序；通过独立环境、双provider规则、不可变bundle和cross-layer identity证据收敛。
- 非目标：S8不顺手修代码；若 integration暴露缺陷，退回对应S1–S7 implementation/review gate修复并重跑，而不是在S8补偿。

---

## 11. 全量验证矩阵与命令

### 11.1 每 slice 共通检查

每次未来代码修改后，先运行该 slice focused tests/pyright，再执行：

```bash
source .venv/bin/activate
git diff --check
python -m json.tool docs/cli_ci_oracles.json >/dev/null
python -m json.tool docs/cli_ci_scenarios.json >/dev/null
shasum -a 256 docs/cli_ci_oracles.json docs/cli_ci_scenarios.json
git status --short
git diff --cached --name-only
```

预期 registry digest始终为§0.1两值，且不出现在S1–S8 staged list；accepted plan commit后 `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` 必须为空。任一slice再次让registry变dirty或staged都立即停止。每个修改生产文件以其owner tests运行coverage，单文件阈值 `>=80%`；不可用总平均掩盖低覆盖文件。示例：

```bash
source .venv/bin/activate
coverage erase
coverage run -m pytest <slice-owner-tests>
coverage report --include='dayu/<exact-modules>.py' --show-missing --fail-under=80
```

### 11.2 最终完整验证

```bash
source .venv/bin/activate
pytest tests/contracts tests/cli tests/documents tests/fins tests/tools tests/host tests/runtime tests/service tests/engine -q
python -m pyright dayu/ tests/ utils/
python -m json.tool docs/cli_ci_oracles.json >/dev/null
python -m json.tool docs/cli_ci_scenarios.json >/dev/null
git diff --check
shasum -a 256 docs/cli_ci_oracles.json docs/cli_ci_scenarios.json
git status --short
git diff --cached --name-only
```

再执行 contract scans：

- active CLI/Service 无已删除 `--config` grammar/export/request forwarding；独立 runtime location 能力不计误报。
- active Host/test/design 无旧 `context_compaction_completed`。
- active compact schema/prompt/test无v1 alias或旧loose field；`CompactPipelinePassQueuePlan`、`build_reactive_pass_queue_plan`与operation-level bounded multi-pass必须仍存在，并有aggregate-root revalidation tests。
- interactive effective schema names 精确无 `start_fins_preprocess`，独立 preprocess 与 download/list/read仍在正确入口。
- `git diff --stat` 和 staged allowlist 只含当前 slice 文件；任何无关变化先停止，不清理用户文件。

### 11.3 失败处理

- owner test失败：退回对应 slice修 root cause；禁止更新oracle/fixture掩盖。
- full suite暴露跨slice问题：按语义owner归回S1–S7；S8不实现补偿。
- pyright涉及 touched范围既有错误时一并修至不扩散；禁止 ignore/cast-to-Any。
- JSON/digest失败：立即停止；不得重建 registry。
- real evidence失败：保留该次immutable失败bundle，使用新run id重试；不得覆盖或删改。

---

## 12. Mimo-first、DeepSeek fallback 的全真实 evidence 程序

### 12.1 隔离与命名

对每个最终待验证 clean commit 建立唯一 run id：

```text
pr190-wu-cli-conformance-f01-f07-<UTC-YYYYmmddTHHMMSSZ>-<12-char-commit>
```

root 固定为 `/Users/leo/workspace/.dayu-cli-ci/<run-id>/`。创建必须使用“目标已存在即失败”的方式；不得复用 `pr190-closure-20260802TQgGLA1`，不得改其两个首轮报告。新 root 内建立 detached `worktree/`、独立 `.venv/`、独立 workspaces、`evidence/interactive/` 和 `logs/`；manifest 记录 target commit、branch、Python/dependency版本、UTC时间、provider/model、scenario id和registry digests。证据收集前确认 detached worktree clean且 target SHA精确。

### 12.2 Provider 顺序

1. 所有需要真实 LLM 的 scenario 首先使用配置中的 Mimo provider/model；manifest和screen明确其真实身份。
2. Mimo invalid/exhaust 是 F07 failure evidence 时必须原样保留，不因失败改名为成功。
3. 若成功路径因 Mimo持续不能产出合法v2 candidate而无法完成，建立**新的 scenario attempt/bundle目录**使用 DeepSeek fallback；不在同一声称为Mimo的结果内静默换provider。
4. DeepSeek只作为记录清晰的fallback，不改变oracle；两个provider的command/input/screen/artifact各自保存。
5. provider不可用、认证失败或网络失败属于环境blocked，不是产品pass；保存诊断但不泄露secret。

### 12.3 每条 scenario 的最小 bundle

```text
evidence/interactive/<scenario-id>/<attempt-id>/
  manifest.json
  command.txt
  before.json
  input.txt
  screen.txt
  host-public.json
  event-log.jsonl
  tool-trace.jsonl
  memory.json
  run-input.json
  artifacts.json
  after.json
  verdict.json
```

`verdict.json` 只有一个最终 verdict，列出oracle assertion、对应文件/字段和pass/fail；不以日志片段代替 owner evidence。F02/F03/F04 额外保存PTY timing/control timeline；F07 保存每attempt validation code、redacted feedback、terminal permit、accepted coverage及两次followup identity。raw provider响应若含敏感内容先按既有evidence规则脱敏，并在manifest记录redaction，不篡改业务字段。

### 12.4 不可变与 digest

收集完成后先写 `bundle-index.json`，列出所有相对路径、size、scenario/provider/commit。然后在 run root 内按 `LC_ALL=C` 排序，对除 `SHA256SUMS` 自身和临时文件外的所有普通文件生成 SHA-256；用 `shasum -a 256 -c SHA256SUMS`复验。复验成功后递归移除写权限。任何补录都必须新建run id，不能chmod回去修改旧bundle。最终closeout同时报告：新bundle根、`SHA256SUMS`自身digest、首轮两报告digest和两个registry digest。

---

## 13. Frozen oracle、staging 与 future commit 边界

### 13.1 本 Gate

当前第二次 plan-fix gate 只更新本 plan并在 `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md` 追加本轮记录；不stage、不commit、不push、不做PR操作。下一入口只能是第二轮独立plan re-review。两个dirty registry在fix/re-review期间既不stash/reset也不stage。

### 13.2 Accepted plan commit：registry disposition 与精确 staged set

仅在第二轮独立plan re-review通过、总控裁决所有accepted findings均为已修复后，执行Gateflow accepted plan commit。该commit必须把两个既有dirty registry baseline按原字节纳入PR 190，并同时包含完整plan review loop；不得把registry留给S1–S8，也不得混入生产代码、测试或README。

精确路径集合固定为：

- `docs/cli_ci_oracles.json`
- `docs/cli_ci_scenarios.json`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-review-mimo.md`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-review-ds.md`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-review-controller-adjudication.md`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-mimo.md`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-ds.md`
- `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md`

stage前先确认工作树中上述artifact齐全、index为空，并计算working-tree registry哈希；只能使用 `git add -- <上述十条显式路径>`。stage后再次计算working-tree哈希，并直接校验index中的两个blob：

```bash
shasum -a 256 docs/cli_ci_oracles.json docs/cli_ci_scenarios.json
git diff --cached --name-only
git add -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md docs/reviews/wu-cli-conformance-f01-f07-plan-review-mimo.md docs/reviews/wu-cli-conformance-f01-f07-plan-review-ds.md docs/reviews/wu-cli-conformance-f01-f07-plan-review-controller-adjudication.md docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-mimo.md docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-ds.md docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md
shasum -a 256 docs/cli_ci_oracles.json docs/cli_ci_scenarios.json
git show :docs/cli_ci_oracles.json | shasum -a 256
git show :docs/cli_ci_scenarios.json | shasum -a 256
git diff --cached --name-only
git diff --cached --check
```

四次registry digest都必须分别精确为§0.1固定值，`git diff --cached --name-only` 必须与上述十路径集合完全相等。随后才允许创建 `gateflow: accept plan for WU-CLI-CONFORMANCE-F01-F07` local commit。commit后再次校验hash，并要求 `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` 为空；从此S1–S8不再携带dirty registry。

### 13.3 未来 implementation slice

- 每个 S1–S6 使用一个独立 implementation diff和一个经相应review gate接受后的commit边界；只用 `git add -- <该slice显式allowlist>`，禁止 `git add -A`/`git add .`。
- S7 无论内部四个checkpoint如何推进，只允许一个outer staged set/accepted commit；schema、validator、repair、terminal、reactive multi-pass aggregate、artifact、canonical-event-to-Memory、RunInput、trace和owner tests必须同在。不得stash、建新branch、提交“producer v2、consumer兼容v1”或任何partial checkpoint。
- S8 的README/docs与evidence index使用独立closeout commit边界；repo外 evidence不stage。若设计真源已在S6/S7原子提交更新，S8不得重写语义。
- 每次S1–S8 stage前后运行 `git diff --cached --name-only` 与 `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json`；两个registry既不能出现在slice staged set，也不能重新变dirty。违反任一条件立即停止，只撤销错误index选择，不改registry working-tree内容。
- 每个slice commit前保存 focused validation artifact；commit后用clean detached target运行需要的integration。新的代码缺陷回到owner slice修复并形成显式fix commit，不amend已用作immutable evidence的commit。

建议边界：

| Slice | staged owner |
|---|---|
| S1 | CLI grammar/call sites、Service request、owner tests |
| S2 | composer public editor fallback与CLI-owned explicit launcher、owner tests |
| S3 | key parser/acceptance closeout、owner tests |
| S4 | interactive attachment/pending mutation、owner tests |
| S5 | interactive manifest、scene/discovery tests |
| S6 | trigger code、strict manifest tests、Host design identifier |
| S7 | 全部v2 atomic closure、prompt、Host design、owner tests |
| S8 | 允许的四个README、closeout索引/报告（若仓库约定需要） |

---

## 14. 风险、开放问题与 no-overdesign

### 14.1 风险登记

| 风险 | 等级 | 收敛方式 |
|---|---|---|
| prompt_toolkit terminal suspend/resume与显式editor子进程行为 | MEDIUM | 当前 resolved dependency 的 public seam contract tests、CLI-owned frozen readback规则、exact argv、无fallback真实PTY测试；seam不符即回plan |
| ESC ambiguity与SIGINT/terminal同batch竞态 | MEDIUM | Vt100Parser chunk matrix、turn-bound state、确定性scheduler与PTY evidence |
| READ_ONLY后writer退出时fresh attach竞争 | MEDIUM | Host public typed mode、close-before-open、stable pending identity、真实双CLI |
| F07 fresh schema与reactive aggregate影响面大 | HIGH | S7单一outer边界、四个内部checkpoint、strict parser、root revalidation、committed-event projection、full suite |
| LLM自然语言仍可能低质量但形式合法 | MEDIUM/ACCEPTED | deterministic最低信息+coverage；真实provider evidence；不伪装语义证明 |
| Mimo/DeepSeek/网络环境不可用 | MEDIUM/OPERATIONAL | Mimo-first、明确fallback、新bundle；环境失败不算产品pass |
| dirty registry误stage/覆盖 | HIGH/CONTROLLED | accepted plan commit精确十路径、stage前后working-tree/index hash、之后S1–S8 clean guard |

### 14.2 开放问题与 operational stop

当前没有阻塞实现设计的开放问题：editor public seam已固定；`MemoryProjectionPolicy`与`estimate_memory_size_units()` owner已确认在 `dayu/host/memory.py`。唯一保留的是外部运行条件：真实provider credentials/配额/网络若不可用，S8按§10.3保持 `BLOCKED-ON-REAL-EVIDENCE`，保留失败bundle，provider恢复后用新run id继续S8；不得降级为mock证据或宣称closeout pass。

### 14.3 No-overdesign rationale

- F01删除seam而非新建配置抽象；F05改manifest owner而非增加过滤层；F06直接重命名而非alias registry。
- F02只增加CLI-local typed explicit launcher并复用public prompt_toolkit seam，不实现通用editor；F03共用一个最小turn closeout且不携带interactive-only状态；F04只管理current attachment和pending mutation，不增加权限升级协议。
- F07保留设计已要求的operation-level bounded reactive multi-pass，不引入新DAG；每pass whole-candidate repair，全部pass后只做一次root aggregate revalidation并形成一个accepted truth。represented coverage由Host派生、caps/estimator复用 `dayu/host/memory.py` 真源，Memory只消费committed canonical event，没有第二份配置、LLM自报真源或下游补偿。
- 不引入新业务层、数据库、迁移、callback/profile/generic schema framework；仅增加完成冻结contract所需的typed value types和owner validator。

---

## 15. 最终 closeout 报告格式

未来只有所有implementation/review/deepreview/evidence gates完成后，最终报告使用以下固定结构；当前Second Plan Fix Gate不得提前填写PASS：

```text
Work unit: WU-CLI-CONFORMANCE-F01-F07
Branch / PR / target commit:
Goal Confirmation: approved

Slice results:
- S1/F01: PASS|FAIL — owner changes — focused validation artifact
...
- S8/integration: PASS|FAIL — full validation artifact

Contract changes:
- removed CLI/public fields:
- fresh schema/typed trigger:
- compatibility paths: none

Validation:
- focused tests and per-file coverage:
- full pytest:
- pyright:
- JSON tools / diff-check:
- README/design trigger decisions:

Real evidence:
- run id / target SHA:
- Mimo attempts:
- DeepSeek fallback attempts (if any):
- scenario verdict index:
- immutable bundle path / SHA256SUMS digest:

Integrity:
- cli_ci_oracles.json SHA-256:
- cli_ci_scenarios.json SHA-256:
- first-round report SHA-256 values:
- staged/committed file boundaries:

Residual risks / uncovered items:
- classified risk, owner, disposition

Final verdict: PASS only when every frozen oracle assertion and gate is satisfied.
```

## 16. Second Plan Fix Gate 完成判定

本次第二次fix已逐项落实Plan Re-review总控裁决的R1与R2，并保持原18项accepted/accepted-in-part finding的已修复状态及rejected finding的既有处置。Plan仅把当前环境与项目依赖声明作为不同事实，editor成功readback由CLI owner定义；future staging使用十条真实存在的durable artifact路径。Second Plan Fix Gate标记为 `COMPLETE`、non-blocked、**待第二轮独立plan re-review**；不得提前标记为code-generation-ready。

当前动作到此停止。下一合法动作仅是第二轮独立的 **Plan Re-review Gate**；本次不得进入该gate，也不得实施、stage、commit、push或操作PR。
