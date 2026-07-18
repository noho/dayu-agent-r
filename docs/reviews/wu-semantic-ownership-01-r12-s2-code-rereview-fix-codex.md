# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 complete code re-review accepted-finding fix — AgentCodex

## 1. Gate、authority 与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S2 complete code re-review accepted-finding 窄修复，不是新 WU。
- 已完整读取根 `AGENTS.md`、fixed plan、上游 code-review fix / Controller validation、AgentMiMo / AgentDS 两路 complete re-review，以及 Controller adjudication。
- Controller adjudication 已机械核验为 57 行 / 4,200 bytes / SHA-256 `695c21d52bb48f74fd9c9313018f6b624a9b9059b86f2067e5584c80c0cca6ec`。
- 只修复 accepted `R12-S2-RR-F01` 与 `R12-S2-RR-F02`。实际生产/测试修改精确为 `dayu/cli/init_environment.py`、`dayu/cli/commands/init.py`、`tests/cli/test_init_environment.py`、`tests/cli/test_init_command.py`，并新增本 artifact。
- 未修改 fixed plan、control、Controller/reviewer artifacts；未进入 S3 prewarm/smoke/README/Windows workflow/stale caller migration；未 stage/commit/push。
- 结论：两个 accepted findings 已在各自 semantic owner 关闭，当前停在 `Controller validation`。

## 2. 第一性原理、root cause 与 semantic owner

动机成立，而且严重性由直接故障证据支持：

1. F01 的根因是 CLI 在 typed interrupt 分支先执行可能失败的 stderr diagnostic，后执行 prepared transaction abort；diagnostic `OSError` 会跳过 abort 并把 exit 130 改成 exit 1。abort failure diagnostic 自己也可能覆盖原始中断。
2. F02 的根因是 POSIX environment owner 把 temp identity-read、identity drift 与 unlink failure 全部压成无返回值的 best-effort cleanup；调用方因此无法区分“已清理”“未知 identity 对象仍在”“owner temp 含敏感值但 unlink 失败”。Controller 的直接探针证明后者会真实发生。

唯一 owner 与修复位置：

- `dayu.cli.init_environment` 继续唯一拥有 POSIX temp identity、清理和 environment persistence durable truth；它产生 written/unwritten names 与最小 `retained_paths`，不携带或格式化 secret value。
- `dayu.cli.commands.init` 继续只编排 workspace transaction：先调用 transaction owner abort，再 best-effort 投影 environment retained path、written names 与 abort failure truth。
- 未在 workspace owner、展示 adapter、fixture 或 stale caller增加 fallback；未建立通用 filesystem/cancellation framework或 production test seam。

## 3. Accepted findings closure

### R12-S2-RR-F01 — CLOSED

- persistence 的 typed/plain interrupt 都先调用 `_try_abort_prepared_transaction(...)`；该 helper 不做 diagnostic I/O，只返回可空 typed `InitWorkspaceError`。
- written names、environment retained paths 与 abort failure diagnostic 全部在 abort 尝试之后，通过 owner-local `_report_diagnostic_best_effort(...)` 输出；普通 diagnostic I/O 异常不会覆盖既有 transaction/interrupt 控制流。
- Windows partial result、typed persistence failure 和普通 persistence `OSError` 同样先 abort，再报告，避免同类 pre-publication transaction 遗留。
- broken stderr owner tests 以真实 prepared transaction覆盖 typed/plain 与 abort success/failure：abort 永远是首个事件；success 时无 `.dayu-init-transaction-*`，abort failure 时保留精确 transaction path；四种组合均 exit 130。

### R12-S2-RR-F02 — CLOSED

- `EnvironmentPersistenceResult` 与 `EnvironmentPersistenceError` 新增严格 `tuple[Path, ...]` retained-path truth；字段只携带路径，不携带 value、profile 内容、stdout/stderr 或 registry 内容。
- POSIX owner 使用封闭的 owner-local no-follow identity 分类：`owned / absent / drifted / unreadable`。cleanup 只对 `owned` 调用 `os.unlink`；`drifted` / `unreadable` 不删除并报告路径；unlink/identity-read 故障均报告路径，不再静默遗留。
- interrupt 路径用 `EnvironmentPersistenceInterrupted.result.retained_paths` 携带 truth；ordinary failure 用 `EnvironmentPersistenceError.retained_paths` 携带同一 truth。
- identity-drift test 证明同名 unknown replacement 不被误删，其路径仍被准确报告；unlink/identity-read × ordinary failure/interrupt 四个 fault cases 证明 owner temp 真实保留且含运行期 value，但 exception/result/repr/CLI diagnostic 均不含该 value。
- CLI 收到 retained-path truth 后先 abort prepared transaction，再 best-effort 输出精确路径；不会尝试删除 environment owner 的 temp，也不会输出 value。

## 4. 最终修改路径 identity

| 路径 | 行 | 字节 | SHA-256 |
|---|---:|---:|---|
| `dayu/cli/init_environment.py` | 835 | 31,429 | `16353a72bce2efeeac1aae64f1f0c94cdca2e30e956be9412f2f0f20002059c0` |
| `dayu/cli/commands/init.py` | 743 | 27,820 | `fe5d4a434ccd5b528ef61cf80295652bbcc4bfa961bd0be3c6dc2aecf95a3e19` |
| `tests/cli/test_init_environment.py` | 1,245 | 48,353 | `5bc46652d54ae5e6860424c3acb952ce2dd615cb0df09eb1ae5c3b6c1f184618` |
| `tests/cli/test_init_command.py` | 964 | 34,238 | `25de81a149fcaee079c1e693b278258390d1710d87617e350abbe5abd914a4b2` |

本 artifact 自身的终态 identity 由 Controller 在文件关闭后机械读取，避免 self-referential hash。

## 5. 测试、coverage 与静态验证

所有 Python 命令均先执行 `source .venv/bin/activate`。

### 5.1 Owner 与 focused cumulative tests

```bash
pytest tests/cli/test_init_environment.py tests/cli/test_init_command.py -q
```

- exit `0`；`81 passed, 3 warnings in 1.97s`。warning 是既有 `edgar` deprecated imports。

```bash
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py -q
```

- exit `0`；`401 passed, 3 warnings in 9.96s`。

```bash
pytest tests/runtime/test_filelock.py tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py -q
```

- exit `0`；`146 passed in 0.23s`。

### 5.2 两个修改 production 文件逐文件 coverage

| Exact command | 结果 |
|---|---|
| `pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q` | exit `0`；`56 passed`；304 statements / 16 miss / 94.74% |
| `pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init --cov-report=term-missing --cov-fail-under=80 -q` | exit `0`；`25 passed, 3 warnings`；284 statements / 27 miss / 90.49% |

### 5.3 Full pyright、changed Ruff 与 full Ruff immutable fingerprint

```bash
python -m pyright dayu/ tests/ utils/
```

- exit `0`；`0 errors, 0 warnings, 0 informations`。

```bash
python -m ruff check dayu/cli/init_environment.py dayu/cli/commands/init.py tests/cli/test_init_environment.py tests/cli/test_init_command.py
```

- exit `0`；`All checks passed!`。

```bash
python -m ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-current.json
```

- Ruff `0.15.11`；full command 按 immutable baseline 预期 exit `1`。
- baseline/current JSON 均为 144 diagnostics，SHA-256 均为 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。
- `cmp workspace/tmp/r12-ruff-baseline.json workspace/tmp/r12-ruff-current.json` exit `0`。

## 6. Scope、immutable 与扫描结果

- `git diff --check` exit `0`；两个 untracked Python target 另以 `git diff --no-index --check /dev/null <path>` 核验无 whitespace diagnostic。
- staged tree 为空。
- 禁止扫描对四个授权文件检查 `cancellation/callback/factory/compat/fallback/shim/hasattr/getattr/test seam/prewarm/importlib.import_module`，零命中。
- secret diagnostic 扫描没有发现 Controller sentinel、production value print 或 stderr value projection；唯一宽松命中是既有测试 `_WaitingPrint(*values)` 转发 public lock notification，不读取 environment entry value。
- S3 path/token 扫描没有发现 `test_init_smoke`、`r12-init-windows`、stale prompt migration 或 prewarm 实现。
- 正向扫描只在 environment owner 命中 `os.lstat/os.unlink/retained_paths`，只在 CLI owner 命中 abort-first 与 best-effort diagnostic chain。

10 个 immutable S2 路径保持 Controller fixed hashes：

| 路径 | SHA-256 |
|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` |
| `dayu/cli/init_workspace.py` | `b5aac7f486d86d0c01896a2fc3533d028d0e5064f43982bb2974fddc7efd3fd7` |
| `dayu/cli/arg_parsing.py` | `add2353afbc64db84af1c4df899dfa8a692409131d91570d6c7fac7d1241319e` |
| `dayu/service/host_assembly.py` | `658b57e5378ea6ea849203106e2bd57b38e1d6917a93743264cd22ec2f2c27b9` |
| `dayu/service/entrypoint_runtime.py` | `4e16540335ae9a614381d59899dcda23f590f42320494a093e01ce0329344632` |
| `dayu/service/README.md` | `d1eed1d028fda7df7e913361fdd313109d262a952433ad8c99ef2a1c0c9f4d79` |
| `tests/cli/test_init_catalog.py` | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` |
| `tests/cli/test_init_workspace.py` | `c363bc1916ceb3204f517a038d70ce632d0c3d8fd17319651cfee2ecb8f3e95b` |
| `tests/cli/test_arg_parsing.py` | `9a0b7aa6647c7ca18dc96eb50714ec1cadff29ff2df51ccdf7edc0926ef1b9e2` |
| `tests/service/test_host_assembly.py` | `28e099404bcf931dc4c78158288705c1f1ff555966eadf08a3f5d3df865e6ad8` |

排除本轮四个修改路径与新 artifact 后，开工/终态机械摘要一致：

- existing tracked dirty diff SHA-256：`9f1f302b8d5a731c426bf7bc648f7ea9448eba2ecce17cf192aa600f7c66679e`。
- existing status-path SHA-256：`726336f4ea615cf5f861ca6cf28e3e13c6ddc39abfd5b40b52b0c12b502fbe6a`。

因此其它 dirty tree path/scope 未漂移；本轮没有覆盖用户或 Controller 既有改动。

## 7. README decision

- 本轮修改 tests，通常触发 `tests/README.md` 检查；但当前 gate 与 Controller adjudication 明确禁止进入 S3/README，且本修复不改变最终用户工作流、公开 flag、Service owner或分层关系。
- 因此根 README、`dayu/config/README.md`、`dayu/service/README.md`、`tests/README.md` 均保持不动；README 同步仍归既定 S3 gate。

## 8. Residual 与停止状态

1. POSIX cleanup 失败时，含敏感值的 owner temp 仍可能真实保留；本轮正确 contract 是 `0600` owner temp 不被错误声称已删除，并通过最小 retained path 让操作者可定位。R12 不创建安全删除重试器、journal或通用 FS framework。
2. identity `drifted/unreadable` 时 fail closed，不按名称删除未知对象；该安全选择可能保留不属于本 transaction 的同名 path，但不会误删外部对象。
3. S3 prewarm、真实 POSIX/Windows smoke、Windows workflow、README 与 stale explicit-interaction caller migration仍未执行，且未被本轮测试或 production fallback 偷带。
4. Windows directory crash durability、RESET 两根非 single-syscall atomic、`.dayu-init.lock` 只串行 init、OS environment 与 workspace 非同一事务仍是 fixed plan §10.1 retained residual。
5. 当前 accepted finding open：`0`；unclassified local blocker：`0`；design contradiction：`NONE`。

下一 checkpoint：`Controller validation`。AgentCodex 在此停止，不进入 S3、complete re-review、stage、commit、push 或 PR。
