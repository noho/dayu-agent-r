# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 accepted code-review fix — AgentCodex

## 1. Gate、范围与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 `R12 S2 accepted code-review fix`，不是新 WU。
- Authority：fixed plan `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`、implementation handoff `eaccec2f...64e`、两路 review `c983c234...b623` / `25c545f7...763a` 与 Controller adjudication `fa021252...b3666`。
- 只修复 accepted `R12-S2-CR-F01..F03`；没有实现 reviewer 的长度/命名/冗余意见，也没有进入 S3、prewarm、README/full CLI stale caller迁移、Windows workflow、aggregate、commit/push/PR。
- 实际修改精确为 `dayu/cli/init_environment.py`、`dayu/cli/commands/init.py`、`tests/cli/test_init_environment.py`、`tests/cli/test_init_command.py`，并新增本 artifact。
- 结论：accepted findings `3/3` 已在各自 semantic owner 关闭；当前停在 `Controller validation`，没有 stage/commit/push。

## 2. 第一性原理与设计取舍

问题动机成立。原 environment owner 只把 `OSError` 当作失败边界，导致 `KeyboardInterrupt` 绕过 temp cleanup、Windows批次名称真值与 CLI prepared-transaction abort。修复不能放到下游 fallback：POSIX/Windows durable store truth只能由 `init_environment` 产生，workspace abort只能由 `commands.init`在 persistence→publication边界消费。

最小设计如下：

1. `EnvironmentPersistenceInterrupted` 继承 `KeyboardInterrupt`，只携带既有 result shape 的 `target / written_names / unwritten_names`；新增 `status=interrupted`，不携带 values、stdout/stderr、return code或 registry/profile content。因此 CLI外层仍机械映射 exit `130`，无需 cancellation framework。
2. POSIX writer从 `mkstemp` descriptor记录 `st_dev/st_ino`。write/fsync/replace抛出普通错误或中断时，只有仍匹配该 no-follow identity的 private temp才允许 unlink；identity已漂移的同名对象不删除。replace抛错后用 source/destination identity对账：source仍持有 owner identity表示 public store未写；source消失且 profile持有 owner identity表示 replace after-effect已发生。中断报告全部 written names，普通 `OSError`继续写后验证，不把已发布 durable state猜成失败。write/fsync在 private temp产生的 bytes不属于 public store，结果仍为全部 unwritten并清理含 secret的 owner temp。
3. Windows每个 `setx`只有 return code `0`后才进入 `written_names`；first/middle/last call中断时保存已确认前缀和未确认当前项/后缀。全部 `setx`成功、随后进程内 `os.environ`注入中断时仍报告全部 durable written names。captured output从未进入 result/exception。
4. `run_init_command` 在 persistence boundary分别捕获 typed/plain interrupt：typed路径先报告不能自动回滚的 written names，两条路径都调用既有 `abort_prepared_workspace_transaction(prepared)`后重新抛出原中断。abort若返回既有 `InitWorkspaceError`，CLI输出原 stage/retained/public/durability truth，再继续传播原中断；不会伪装清理成功，也不会把中断降格为 exit `1`。
5. 没有新增 callback、factory、profile object、implicit default、test-only production seam、兼容分支或通用 cancellation abstraction。测试只在 owner module lookup boundary monkeypatch真实 `os.fdopen/os.fsync/os.replace/subprocess.run`。

## 3. Findings closure

### R12-S2-CR-F01 — 已修复

- POSIX private temp identity由 writer创建时 fd truth产生，不从文件名反推。
- write/fsync/replace调用前/后分别覆盖 `OSError` 与 `KeyboardInterrupt`。
- replace after-effect用 source/destination identity判定；ordinary error继续 owner verification，interrupt携带全部 written names。
- 所有仍由 owner持有的含 secret `.dayu-init-env-*` 都在失败/中断路径清理；identity漂移测试证明未知 replacement不被按名称删除，同时 replacement不含 secret。
- exception/result/repr/CLI output均不含 secret。

### R12-S2-CR-F02 — 已修复

- Windows first/middle/last `setx` interrupt分别断言 `written_names=success prefix`、`unwritten_names=current + suffix`。
- 全部 `setx`成功后的进程内环境注入 interrupt断言 `written_names=all`、`unwritten_names=()`。
- typed interrupt只含安全 target与names，不含 values/captured output；继承 `KeyboardInterrupt`，没有伪造 registry rollback。

### R12-S2-CR-F03 — 已修复

- plain/typed persistence interrupt都在真实 staging、真实 Service/Fins discovery之后 abort prepared transaction，并返回 CLI exit `130`。
- 成功 abort时 workspace没有 public config/`.dayu`，也没有 `.dayu-init-transaction-*`。
- typed路径报告已写 env names与“不能自动回滚”，不报告 values。
- abort failure测试保留真实 prepared transaction，输出 `pre_publication_abort_cleanup`、retained path与 public root truth，同时仍返回 exit `130`。

## 4. 文件终态 identity

| 路径 | 行 | 字节 | SHA-256 |
|---|---:|---:|---|
| `dayu/cli/init_environment.py` | 776 | 29,178 | `55756e0662d203811a84325cb79c3a42ea13592b790ec02966f361e670e71a40` |
| `dayu/cli/commands/init.py` | 689 | 25,789 | `3acbbec9049c91fd238a167a7a5a708a03be9b49a73f03907a710f32dffd56ce` |
| `tests/cli/test_init_environment.py` | 1,146 | 44,114 | `406ad395bfa8e6c644bca8f7a9349181bdabfd770a7e2ea1772828d54379eed6` |
| `tests/cli/test_init_command.py` | 832 | 29,097 | `5f229547219f34db0116d8fed5a764ab2d741ae47423e62166bb4b1bca6f72cb` |

本 artifact终态行/字节/SHA-256在文件关闭后由 Controller机械读取，避免 self-referential hash。

## 5. Exact validation commands 与结果

所有 Python命令均先执行 `source .venv/bin/activate`。

### 5.1 Owner tests

```bash
pytest tests/cli/test_init_environment.py -q
```

- exit `0`；`52 passed in 0.12s`，即原 `35` 加 `17` 个新增 owner tests。

```bash
pytest tests/cli/test_init_command.py -q
```

- exit `0`；`21 passed, 3 warnings in 1.70s`，即原 `18` 加三个新增 tests。warning均为既有 edgar deprecated import。

### 5.2 Focused cumulative baseline + 新增与 runtime anchors

```bash
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py -q
```

- exit `0`；`393 passed, 3 warnings in 9.84s`，精确等于既有 `373` baseline加本 fix `20` 个新增 tests。

```bash
pytest tests/runtime/test_filelock.py tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py -q
```

- exit `0`；`146 passed in 0.23s`。

### 5.3 四个 cumulative CLI production owner 逐文件 coverage

| Exact command | 结果 |
|---|---|
| `pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q` | exit `0`；`31 passed`；`276/27/90.22%` |
| `pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q` | exit `0`；`52 passed`；`280/17/93.93%` |
| `pytest tests/cli/test_init_workspace.py --cov=dayu.cli.init_workspace --cov-report=term-missing --cov-fail-under=80 -q` | exit `0`；`90 passed, 3 warnings`；`547/70/87.20%` |
| `pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init --cov-report=term-missing --cov-fail-under=80 -q` | exit `0`；`21 passed, 3 warnings`；`259/23/91.12%` |

### 5.4 Type、changed Ruff 与 full Ruff exact fingerprint

```bash
python -m pyright dayu/ tests/ utils/
```

- exit `0`；`0 errors, 0 warnings, 0 informations`。

```bash
python -m ruff check dayu/cli/init_environment.py dayu/cli/commands/init.py tests/cli/test_init_environment.py tests/cli/test_init_command.py
```

- exit `0`；`All checks passed!`。

```bash
set +e
python -m ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-current.json
ruff_current_status=$?
set -e
test "$ruff_current_status" -eq 1
test "$(python -c 'import json,sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))))' workspace/tmp/r12-ruff-current.json)" -eq 144
test "$(shasum -a 256 workspace/tmp/r12-ruff-current.json | awk '{print $1}')" = "051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea"
test "$(shasum -a 256 workspace/tmp/r12-ruff-baseline.json | awk '{print $1}')" = "051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea"
cmp workspace/tmp/r12-ruff-baseline.json workspace/tmp/r12-ruff-current.json
```

- full Ruff按既有 baseline预期 exit `1`；JSON count `144`；baseline/current SHA均为 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；`cmp` exit `0`。

### 5.5 Diff、stage、authority 与 immutable hashes

```bash
git diff --check
git diff --cached --name-only
```

- diffcheck exit `0`；staged path为空。

Authority artifacts保持：

| 路径 | SHA-256 |
|---|---|
| fixed plan | `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c` |
| implementation handoff | `eaccec2ff8af46e7eccfc220250e2f81a9b90135b551d266c4e8f4bcce38564e` |
| MiMo review | `c983c2341785406846e491abd0099b8ba1d2c80be30c4898dc1cd30e8d7eb623` |
| DS review | `25c545f79a01a6654ac4dfa13bea55112729d256d6639e51d68e8160eeeb763a` |
| Controller adjudication | `fa0212521fc643eb041a5d8f651a420aae0e214872fd347696c1ed3f3e8b3666` |

用户锁定的 10 个 fixed targets保持：

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

```bash
rg -n "cancell?ation|callback|factory|compat|fallback|shim|hasattr\(|getattr\(|implicit[_ -]?default|test[_ -]?seam" dayu/cli/init_environment.py dayu/cli/commands/init.py tests/cli/test_init_environment.py tests/cli/test_init_command.py
```

- exit `1`，零匹配。正向 owner scan只命中上述四个授权文件。

## 6. README decision

- 本 fix修改 tests，但用户与 adjudication精确禁止进入 S3 README/full CLI migration；`tests/README.md` 的完整 init工作流同步仍归 S3，不允许在本 gate局部提前更新。
- 本轮没有改变公开 flags、最终用户成功路径、Service owner或分层关系；根 README、`dayu/config/README.md`、`dayu/service/README.md`、`tests/README.md`均保持不动。

## 7. Residual risks / uncovered areas

1. `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 的旧无交互调用仍是 S3 mandatory migration；本轮没有用 production implicit default/fallback让它伪绿。分类：`covered by later approved slice S3`。
2. prewarm、真实 POSIX subprocess smoke、真实 Windows normal/junction/rollback workflow、R11两个真实 `.cmd`节点与 README/full CLI closure仍归 S3。分类：`covered by later approved slice S3`。
3. Windows parent-directory crash durability、RESET两根非 single-syscall atomic、`.dayu-init.lock`只串行 init、OS environment与workspace非同一事务均保持 fixed-plan retained residual。分类：`covered by existing fixed-plan residual owners`。
4. 当前 fix本地未留 accepted finding、unclassified residual、design contradiction或 blocking question。

## 8. Stop status

- `R12-S2-CR-F01`：已修复。
- `R12-S2-CR-F02`：已修复。
- `R12-S2-CR-F03`：已修复。
- accepted/open：`0`；deferred accepted：`0`；local blocker：`0`。
- 下一 checkpoint：`Controller validation`。只有 Controller validation通过后才可进入双路 complete cumulative re-review；本 artifact不授权 S3、aggregate、commit、push或 PR。
