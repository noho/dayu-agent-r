# WU-SEMANTIC-OWNERSHIP-01 / R12 S3 Complete Cumulative Code Review — AgentMiMo

## Scope

- Mode: cumulative code review (fixed 20-path manifest)
- Branch: `phaseflow/host-issues-control`
- Agent artifact: `docs/reviews/wu-semantic-ownership-01-r12-s3-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-r12-s3-controller-validation.md`
- Fixed plan: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`, SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`
- Source of truth: `AGENTS.md`, `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-mimo.md`
- Included scope: 20/20 paths (see manifest below)
- Excluded scope: none
- Parallel review coverage: 无

## Manifest Verification

```bash
shasum -a 256 .github/workflows/r12-init-windows.yml README.md dayu/cli/arg_parsing.py dayu/cli/commands/init.py dayu/cli/init_catalog.py dayu/cli/init_environment.py dayu/cli/init_workspace.py dayu/config/README.md dayu/service/README.md dayu/service/entrypoint_runtime.py dayu/service/host_assembly.py tests/README.md tests/cli/test_arg_parsing.py tests/cli/test_init_catalog.py tests/cli/test_init_command.py tests/cli/test_init_environment.py tests/cli/test_init_smoke.py tests/cli/test_init_workspace.py tests/cli/test_prompt_command.py tests/service/test_host_assembly.py | LC_ALL=C sort | shasum -a 256
```

Manifest digest: **`2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d`** ✓ PASS。

## Findings

未发现实质性 correctness、stability 或 maintainability 问题。以下逐项报告各必查维度的 review 结论。

---

## Mandatory Review Challenge Results

### 1. Exact-two-root prewarm 控制流

**结论: PASS。**

`dayu/cli/commands/init.py:206-207` 精确在 `publish_workspace_transaction(prepared)` 成功返回后、且仅当 `result.mode is InitMode.FIRST or result.mode is InitMode.RESET` 时调用 `_run_init_prewarm()`。PRESERVE/OVERWRITE 零次调用。

`_run_init_prewarm()`（第 663-678 行）只循环 `_PREWARM_IMPORT_ROOTS`（固定为 `("dayu.cli.commands.interactive", "dayu.cli.commands.prompt")`），每个 root 只调用 `importlib.import_module(module_name)`。普通 `Exception` 只投影 `error_type` 与 `_PREWARM_FAILURE_SUMMARY`（固定文本），不含 exception message、secret、HTTP body 或 environment value。`KeyboardInterrupt`/`SystemExit` 未被 `except Exception` 捕获，正确透传。

测试覆盖:
- `test_init_command.py:382-404`: 断言 exact roots、顺序、调用参数
- `test_init_command.py:407-439`: 断言 prewarm failure 只给脱敏 warning，不回滚已发布 config，secret 不进入 stdout/stderr
- `test_init_command.py:305-317`: FIRST 调用 prewarm 一次
- `test_init_command.py:338-356`: PRESERVE/OVERWRITE 零次，RESET 一次
- `test_init_smoke.py:328-421`: 隔离 subprocess 证明 exact transitive imports（`session_execution`/`entrypoint_runtime` 加载）、deleted roots absent、连续两次稳定、零网络（socket mock）、零 workspace/env mutation

**Failure/interrupt/diagnostic I/O 控制流真实**: prewarm failure 在 `publish_workspace_transaction` 成功之后，不参与 rollback 决策。环境持久化失败/KeyboardInterrupt 在 prewarm 之前触发 abort path（第 176-194 行）。Publication 失败直接 re-raise（第 203-205 行），不调用 prewarm。

### 2. Import observation: 零 import-time network/external mutation

**结论: PASS。**

- `dayu/cli/commands/init.py`: 无 `requests`/`httpx`/`urllib`/`socket`/`huggingface`/`download`/`web_search`/`open_host`/`asyncio.run` import
- `dayu/cli/init_catalog.py`: 只 import `urllib.parse.urlsplit`（本地 URL 语法校验），无网络调用
- `dayu/cli/init_environment.py`: 只 import `subprocess` 用于 argument-safe `setx`，无网络
- `dayu/cli/init_workspace.py`: 只 import `dayu.service.host_assembly`（`assemble_effective_tool_provider_configs`/`discover_service_tools`）和 `dayu.runtime.*`；这些是真实 Service discovery，但只在 transaction-private staging 内执行

测试 `test_init_smoke.py:328-421` 在隔离 subprocess 中 mock `socket.socket.connect`/`socket.create_connection`/`socket.getaddrinfo` 为 `AssertionError`，验证 prewarm 期间零网络调用。

transitive graph（`session_execution`→`entrypoint_runtime`）的加载是 Python 正常 import mechanism 行为，不是产品契约。测试断言 `session_execution`/`entrypoint_runtime` 在 prewarm 后存在于 `sys.modules`，但 production 不依赖该事实、不复制 transitive module list、不调用其中函数。

### 3. S1/S2 四态、secret store、transaction、rollback、interrupt、cleanup

**结论: PASS，未发现回归。**

四态（`init_workspace.py:101-107`）: `FIRST`/`PRESERVE`/`OVERWRITE`/`RESET` 由 `determine_init_mode()` 严格按 `RESET > OVERWRITE > config existence` 优先级决定。

Secret store（`init_environment.py`）:
- POSIX: 唯一 marker block、`shlex.quote`、同父目录 `tempfile.mkstemp` + `fsync` + `os.replace` 原子写入、写后校验 marker/name/mode
- Windows: argument-safe `subprocess.run(("setx", name, value), shell=False, ...)`，成功后才注入 `os.environ`
- 批次成功前不注入、不 publish workspace

Transaction（`init_workspace.py`）:
- `prepare_workspace_transaction()`: 创建 transaction-private staging、真实 ConfigLoader/Service discovery/13-scene validation、POSIX fsync、identity-locked cleanup
- `publish_workspace_transaction()`: backup→replace→rollback 逆序、POSIX workspace-root sync
- `abort_prepared_workspace_transaction()`: identity-locked discard

Rollback: `publish_workspace_transaction()` 第 670-701 行在 InitWorkspaceError/KeyboardInterrupt/OSError 时调用 `_rollback_or_raise()`，逆序恢复 backup→original replace，POSIX sync workspace root。

Interrupt: 环境持久化 KeyboardInterrupt 在 publication 前触发 abort（第 176-185 行），publication 中 KeyboardInterrupt 触发 rollback（第 682-689 行）。

Cleanup: post-publication backup/staging cleanup 失败转为 `WorkspaceCleanupWarning`（第 703-743 行），不 rollback 已发布 config。

### 4. POSIX real smoke 与 Windows workflow

**结论: POSIX PASS。Windows PENDING_RELEASE_BLOCKER。**

POSIX real smoke（`test_init_smoke.py:425-600`）覆盖:
- FIRST→PRESERVE→OVERWRITE→RESET No→RESET Yes 完整四态
- 真实 ConfigLoader + Service discovery + 13-scene validation 重载已发布配置
- `portfolio/`/`assets/` sentinel 全程不变
- RESET No 整树 hash 不变
- 真实 POSIX profile `0600` mode、唯一 marker block、原子替换、脱敏
- 真实 `file_lock(..., timeout_seconds=None)` 单 waiter 与双 queued publisher 串行成功
- 公开 "正在等待此 workspace lock" 通知作为可观察协调点

Windows tests（`test_init_smoke.py:602-805`）在本机 Darwin 上 skip。`.github/workflows/r12-init-windows.yml` 覆盖:
- 四态 + ConfigLoader/scene reload
- 预置 nested junction fail-closed（`tree_identity` stage、`retained=none`、public/external sentinel identity/bytes 不变）
- 普通 symlink 精确 `winerror=1314` skip
- workspace root identity drift rejection
- replace-failure rollback
- scan-delete race
- 真实 `setx` round-trip + cleanup
- R11 两个真实 cmd/upload nodes

**Windows runner evidence 必须保持 PENDING_RELEASE_BLOCKER。** 本机 Darwin 不能替代 Windows runner 真实证据。

### 5. Workflow/JUnit/log/artifact 失败路径

**结论: PASS。**

`.github/workflows/r12-init-windows.yml`:
- `if: always()` 只保证 R11 节点和 artifact 上传继续执行/上传，不掩盖前一步失败
- artifact 只上传 JUnit、OS/Python/capability、source hashes 和 env **names**；不上传 environment/registry values 或 raw registry output
- JUnit 断言使用 name-only/固定错误文本，不 dump captured output
- 环境变量名列表（`environment-names.txt`）只记录变量名，不记录值

### 6. README 语义同源

**结论: PASS。**

`README.md` 准确记录:
- 四态（FIRST/PRESERVE/OVERWRITE/RESET）行为与代码一致
- Secret persistence: POSIX `~/.zshrc`/`~/.bashrc` + Windows `setx`、变量名-only 展示、默认 No
- RESET 前必须停止 active Dayu 进程
- `.dayu-init.lock` 只串行 init
- FIRST/RESET prewarm: import-only、不联网、不回滚
- symlink/reparse 拒绝
- 排障指南与代码语义一致

`dayu/config/README.md` 准确记录:
- ConfigLoader/current JSON schema owner
- 四态 config contract
- 16 known manifest projection
- secret ref/value boundary

`dayu/service/README.md` 准确记录:
- Fins root override 的 ordinary `None` 与 R12 init validation non-`None` contract
- Service effective-config owner 边界

`tests/README.md` 准确记录:
- Owner/fault/真实 POSIX smoke 与 Windows workflow 覆盖
- 16 known manifest、profile、lock contention、setx 等测试事实

未发现 README 扩大 durability、network、Host lock 或 assets/portfolio 承诺。

### 7. Semantic ownership drift、下游 fallback/repair、compat/shim

**结论: PASS。**

- `compat` 字面扫描只命中 `display_name="Custom OpenAI-compatible"` 和 `runner_kind="openai_compatible"`（model kind 名称），不是兼容代码
- 无 `fallback`/`shim`/`hasattr`/`getattr` 在 R12 production 代码中
- `_init_model_role`/`default_name`/`loose parsing` 不存在
- CLI 不猜 Fins provider id、不 strip raw config、不重建 parser
- Service effective-config owner 是唯一 Fins root classification/precedence 真源
- init 只消费 ConfigLoader/Service owner，不形成第二套 schema owner

### 8. Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9 scope leakage

**结论: PASS。**

Production files 无 Issue 142/151/175/177/178 引用。Web/WeChat/render 只出现在 RESET active-process 警告文本中（`commands/init.py:353`），不是实现分支。`wechat` 作为 known manifest basename 被正确处理（`init_catalog.py:249`），不涉及 Web/WeChat/render 入口实现。Topic 8（240-char truncation）/Topic 9（tool authorization）在 R12 代码中无实现。

### 9. Coverage、pyright、Ruff 证据

**结论: PASS（基于 implementation/controller artifact 声明，本机未独立重跑）。**

Controller validation artifact 声明:
- 七个 production 文件单文件 coverage 87%-99%，均 `>=80%`
- `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`
- 15 个 cumulative changed/new Python paths scoped Ruff: `All checks passed!`
- full Ruff: 144 条，SHA-256 `051bd6cc...`，`cmp` exit 0
- `git diff --check`: pass
- staged tree: 空
- Service exact diff: 仅 4 个文件
- Fins/Host/Engine/Tool/runtime/package/design/pyproject/utils: 零 diff

本机未独立重跑这些验证命令。Controller validation 已由独立 Controller 执行并记录。

### 10. Windows workflow code-correctness

**结论: PASS（code review）。**

Workflow 文件本身逻辑正确:
- `windows-latest` + Python 3.11 + locked dependencies
- 真实 pytest 运行四态/junction/symlink/identity/rollback/scan-delete/setx 节点
- R11 节点在 `if: always()` 下执行
- artifact 上传使用 `if-no-files-found: error` 确保报告产出
- 不泄露 environment/registry values

Windows runner 成功执行是 release evidence，不是 code review 替代。

---

## Open Questions

无。

## Residual Risk

1. **Windows real runner evidence**: `.github/workflows/r12-init-windows.yml` 必须在 Windows runner 成功执行。当前 PENDING_RELEASE_BLOCKER。
2. **RESET 两个 managed roots 非单 syscall 原子**: 既有 residual，per-root `os.replace` + 逆序 rollback + RESET 前 active-process 警告是当前 contract。未引入 Host/process lock。
3. **Controller validation 声明的 coverage/pyright/Ruff 未独立重跑**: 本机 review 基于 Controller artifact 声明。若需独立验证，应运行完整验证命令。

## 覆盖的 20/20 路径

| # | 路径 | 状态 |
|---|---|---|
| 1 | `.github/workflows/r12-init-windows.yml` | 已 review |
| 2 | `README.md` | 已 review |
| 3 | `dayu/cli/arg_parsing.py` | 已 review |
| 4 | `dayu/cli/commands/init.py` | 已 review |
| 5 | `dayu/cli/init_catalog.py` | 已 review |
| 6 | `dayu/cli/init_environment.py` | 已 review |
| 7 | `dayu/cli/init_workspace.py` | 已 review |
| 8 | `dayu/config/README.md` | 已 review |
| 9 | `dayu/service/README.md` | 已 review |
| 10 | `dayu/service/entrypoint_runtime.py` | 已 review |
| 11 | `dayu/service/host_assembly.py` | 已 review |
| 12 | `tests/README.md` | 已 review |
| 13 | `tests/cli/test_arg_parsing.py` | 已 review |
| 14 | `tests/cli/test_init_catalog.py` | 已 review |
| 15 | `tests/cli/test_init_command.py` | 已 review |
| 16 | `tests/cli/test_init_environment.py` | 已 review |
| 17 | `tests/cli/test_init_smoke.py` | 已 review |
| 18 | `tests/cli/test_init_workspace.py` | 已 review |
| 19 | `tests/cli/test_prompt_command.py` | 已 review |
| 20 | `tests/service/test_host_assembly.py` | 已 review |

## 独立运行的验证

- manifest digest (`LC_ALL=C sort`): ✓ `2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d`
- source scans（`compat`/`fallback`/`shim`/`hasattr`/`getattr`/network/auth/Issue/Topic）: ✓ production 零禁止命中
- `fins_workspace_root_override` scan: production non-`None` consumer 仅 `init_workspace.py:930`（R12 validation）；`entrypoint_runtime.py:517` 显式 `None`
- forbidden runtime assembly-call scan on `commands/init.py`: 零命中

## 所有既有 accepted findings closure

- S1 findings: 未发现回归（catalog/environment owner contract 稳定）
- S2 findings: 未发现回归（workspace transaction/Service override/rollback 稳定）
- Controller discussion topics 1-9: 未发现 scope leakage

## Windows pending evidence

**`PENDING_RELEASE_BLOCKER`**: `.github/workflows/r12-init-windows.yml` 必须在 Windows runner 成功执行并产出 name-safe evidence。在此之前，Windows gate、S3、R12 和 umbrella 不得写成最终通过。
