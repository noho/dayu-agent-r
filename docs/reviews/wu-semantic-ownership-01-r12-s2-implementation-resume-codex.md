# WU-SEMANTIC-OWNERSHIP-01 / R12 cumulative S2 implementation resume handoff

## 1. Gate 身份与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 `R12 cumulative S2 implementation continuation`，不是新 WU。
- 执行依据：amended authorization `docs/reviews/wu-semantic-ownership-01-r12-s2-resume-controller-authorization.md` 与 fixed plan `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`。
- 实施结论：S2 授权范围内实现与 mandatory verification 完成；未实现 S3/prewarm/workflow、Issue 142/151/175/177/178、Topic 8/9、统一 tool authorization、Web/WeChat/render 能力。
- Stop-condition 结论：未命中 R12 S2 当前 gate 的 §10.2 stop condition。S1 locks、authority locks、staged tree、full pyright、changed-path Ruff 与 full Ruff fingerprint 均保持要求值。
- 下一 checkpoint：只交 Controller validation；本轮未 stage、commit、push、开 PR，也不自行进入 code review 或 S3。

## 2. Authority 与只读输入核验

| 输入 | 终态值 |
|---|---|
| HEAD | `8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8` |
| fixed plan SHA-256 | `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c` |
| amended authorization SHA-256 | `de8c8cfaa3c8fdbb0290b02d538e633391a4ce7519ba89dfd716f3143279354e` |
| final Controller adjudication SHA-256 | `d675ec3d1ac8d4eee29502bbb9d3ea89ac6cc15f1572b70977edd90857df5cbe` |
| 旧 stop handoff SHA-256 | `b123dff616a0c4ac22bb3d1f47b00fe5913a9747e9f3e413ff34462ddbd82fcd` |

S1 四路径保持只读且 hashes 未漂移：

| 路径 | SHA-256 |
|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` |
| `dayu/cli/init_environment.py` | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` |
| `tests/cli/test_init_catalog.py` | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` |
| `tests/cli/test_init_environment.py` | `820c2bf262dd77628201977e7d4f823265e141ac0ae6a28791bd7d12cf5ad01a` |

## 3. 实际 writable scope 与机械度量

| 路径 | entry | 终态 SHA-256 | 行 / 字节 |
|---|---|---|---:|
| `dayu/cli/init_workspace.py` | `ABSENT` | `b5aac7f486d86d0c01896a2fc3533d028d0e5064f43982bb2974fddc7efd3fd7` | 1618 / 60044 |
| `dayu/cli/commands/init.py` | `c33db7318476e54f81630c5e5ec8b33e94a6281dd12ecd2ddc7ee85da57b10ab` | `fd927badc32fe5b266d3cd7f6d11500fd60c3b02ba78e413bdee318a67b52a21` | 664 / 24686 |
| `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` | `add2353afbc64db84af1c4df899dfa8a692409131d91570d6c7fac7d1241319e` | 957 / 31846 |
| `tests/cli/test_init_workspace.py` | `ABSENT` | `c363bc1916ceb3204f517a038d70ce632d0c3d8fd17319651cfee2ecb8f3e95b` | 2504 / 86456 |
| `tests/cli/test_init_command.py` | `c7d226ed8f72ae846c3f3cca1cd500a2342e7050750415cb0022ea5e5bb15364` | `db965a53b3ff0f9d8449f784dc5ae8204ae0be0389780166457042377196807c` | 716 / 24131 |
| `tests/cli/test_arg_parsing.py` | `d3a4abcc22093ff6c4e06edebf249282f1fbac9d9eb3a575c618f28210742658` | `9a0b7aa6647c7ca18dc96eb50714ec1cadff29ff2df51ccdf7edc0926ef1b9e2` | 1260 / 40379 |
| `dayu/service/host_assembly.py` | `54559d2ea0446316b4ff82bf66594dfaa5d7b75067d495f5d3558d2ea94bbe52` | `658b57e5378ea6ea849203106e2bd57b38e1d6917a93743264cd22ec2f2c27b9` | 2368 / 95596 |
| `dayu/service/entrypoint_runtime.py` | `014c5ea0cf16d3538793883277672d70764d5a812054028369c98c229c0115c6` | `4e16540335ae9a614381d59899dcda23f590f42320494a093e01ce0329344632` | 1867 / 69507 |
| `tests/service/test_host_assembly.py` | `04675e6629e80d8348e9abc1f87f4c4b7762b59e9eef17d6dd67f1b3689a203e` | `28e099404bcf931dc4c78158288705c1f1ff555966eadf08a3f5d3df865e6ad8` | 3363 / 126750 |
| `dayu/service/README.md` | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` | `d1eed1d028fda7df7e913361fdd313109d262a952433ad8c99ef2a1c0c9f4d79` | 42 / 9418 |

本文件是 amended authorization 允许新增的唯一 resume artifact。其终态行数、字节数与 SHA-256 由 Controller/最终机械核验在文件关闭后读取。

## 4. Semantic owner 与实现事实

### 4.1 Workspace transaction owner

- `dayu.cli.init_workspace` 是 `.dayu`、`config` 两个 whole-tree managed roots 的唯一 transaction owner；manifest 不含 public `assets`、`portfolio` 或 lock。
- typed `WorkspaceSnapshot`、`InitMode`、request/prepared/result/warning 与 `InitWorkspaceError` 统一拥有 snapshot、四态、retained path、public-root truth、partial deletion 与 durability truth。
- 状态优先级精确为 `RESET > OVERWRITE > config-exists(PRESERVE) > FIRST`：
  - FIRST 从当前五个 package config 文件与 prompt assets 新建 config，不复制 package `README.md`/`.DS_Store`；
  - PRESERVE whole-tree 复制旧 config、仅补缺失 prompt 普通文件，user file/manifest byte truth 保持；
  - OVERWRITE 从 package defaults 重建 config，不合并旧 config，保持 `.dayu`；
  - RESET 从 package defaults 重建 config，并按同一 manifest 移出 `.dayu` 与旧 config；`--reset --overwrite` 仍是 RESET。
- fresh workspace root 只由 orchestrator bootstrap；lock 固定为 `.dayu-init.lock`，显式 `timeout_seconds=None` / `create_parent_dirs=False`，并在 acquire 前输出 public waiting notification。
- RESET 在 bootstrap、secret、staging 前展示 active-process 警告和实际存在 targets；No/空/EOF/SIGINT 均为零 bootstrap/零 managed mutation。

### 4.2 Staging、真实 discovery 与 catalog boundary

- transaction、staging、validation、backup、quarantine 都在 workspace 同父/同 filesystem，并记录 no-follow identity。
- staging 在任何模型 projection 前执行 ordinary-tree 复核；PRESERVE/package prompt `copytree(..., symlinks=True)` 不跟随扫描后新换入的 link，staging race test 证明外部 sentinel 不变。
- staging 使用真实 `ConfigLoader` 读取当前 schema；Service effective assembly 精确传 `workspace_root=<canonical public workspace>` 与 `fins_workspace_root_override=<canonical absolute private validation root>`。
- 一次真实 `discover_service_tools(...)`，一次 `SceneToolCatalog.from_tool_bundle(...)`，同一真实 catalog 校验 13 个 production manifests；每次只传两个锁定空 slot `current_time`、`fins_default_subject`。
- 三个 `smoke_host_public_*` 仍只由 S1 test-owned explicit manual-smoke catalog fixture 验证；S1 hashes 未改。
- 真实发现观察到四个 Fins providers 的 `.dayu` / `portfolio` side effect 只落 private validation root；tool count 为 15，production scene count 为 13。

### 4.3 Service Fins-root owner

- `assemble_effective_tool_provider_configs(...)` 在既有 Service classifier owner 增加 keyword-only `fins_workspace_root_override: pathlib.Path | None = None`。
- raw `config.workspace_root` 总是先通过当前 type/non-empty grammar；只有合法 raw 未配置/绝对/相对三态才进入 path selection。
- non-`None` override 必须是 absolute，canonical 后无条件支配合法 raw path；raw mapping、staging serialized bytes 与 public serialized bytes均未改写。
- `entrypoint_runtime` ordinary caller 显式传 `None`；R12 init validation 是唯一 production non-`None` consumer。
- Service owner tests覆盖 read 与 awaiting Fins classification；非 Fins provider不消费 override，Web storage-state 仍只用 ordinary public root。

### 4.4 Cleanup、publication、rollback 与 durability

- private cleanup 执行 direct-child containment、no-follow identity equality、same-parent unique quarantine、quarantine identity复核，再递归删除；不按 glob/name 猜测用户路径。
- POSIX 只有 `shutil.rmtree.avoids_symlink_attacks is True` 才删除，并使用 `O_NOFOLLOW`/`O_DIRECTORY` + `fstat` 的文件/目录 sync；capability 缺失 pre-publication fail closed。
- Windows 分支不依赖 POSIX capability flag；root/nested reparse classification、ordinary cleanup 与 scan-delete race 均有模拟证据，外部 sentinel 不变。
- publication 前完成 validation cleanup；POSIX validation-parent sync、staging file fsync/leaf-to-root directory sync与 public workspace sync 都属于 success boundary。
- backup/config replace 调用后抛错时按 source/destination identity 重新对账；backup/public config rename 后再次核验 identity，避免 syscall 已生效但记录缺失。
- rollback 先隔离本 transaction 发布的 config，再逆序 restore 每个 backup；restore root 与 rollback workspace sync 有精确 typed stage、current public truth、retained path 与 durability truth。
- success boundary 后 backup/staging cleanup fault 只返回 warning，不 rollback；若路径已删但 POSIX workspace sync 失败，warning 明确 `path_exists=False` 与 `deletion_durability_unconfirmed=True`。
- cleanup warning 沿显式 exception cause chain报告底层 `OSError`/`KeyboardInterrupt` 类型，不把 owner wrapper 冒充 syscall 类型。

### 4.5 Environment 与 secret

- required secret 与固定 optional integrations 只以隐藏输入收集；仅输出变量名、target 和脱敏状态，不写 workspace/log，不打印 value。
- persistence plan拒绝、POSIX writer failure、Windows partial result均在 publish 前 abort prepared transaction。
- Windows partial result或已成功持久化后 publication失败时，只报告 `written_names`，明确 OS store不能自动回滚；不伪造 workspace 已发布。

## 5. Fault matrix 证据

`tests/cli/test_init_workspace.py` 与 `tests/cli/test_init_command.py` 在 production owner lookup boundary 覆盖：

| 阶段 | 注入与断言 |
|---|---|
| staging/validation | package copy ENOSPC/KI、file open/fsync OSError/KI、POSIX staging directory sync OSError/KI、真实 malformed ConfigLoader、Service discovery OSError/KI、scene validation OSError/KI；全部零 public replace，安全时 private tree清空 |
| validation identity/quarantine | identity read OSError/KI、identity drift、containment、quarantine replace调用前/后 OSError/KI、quarantine identity drift、POSIX capability missing；全部 pre-publication fail closed并报告实际 retained path |
| recursive delete | delete未开始 OSError/KI与 partial deletion独立覆盖；partial path指向实际 quarantine，不承诺已删内容完整 |
| validation parent sync | child/quarantine已删除后的 POSIX sync OSError/KI；唯一 retained 是 transaction container，child absent，durability未确认 |
| persistence | required secret批次拒绝、POSIX owner error、Windows partial result；config不发布、secret不泄漏 |
| public backup/config replace | OVERWRITE backup/config 与 FIRST config 调用前/后 OSError/ENOSPC/KI；RESET `.dayu`/`config` 每根 backup 调用前/后 OSError/KI；成功 rollback回到 snapshot/absent真值 |
| publication sync | POSIX workspace sync OSError/KI仍在 boundary 前，执行 rollback |
| rollback | transaction-published config delete OSError/KI、RESET 每根 backup restore调用前/后 OSError/KI、rollback workspace sync OSError/KI；报告精确 stage、current truth、remaining backup/quarantine/staging与durability |
| post-publication cleanup | backup/staging identity/rename/delete OSError/KI、未开始与partial delete、最终POSIX sync OSError/KI；init成功、warning truthful、无 rollback |
| platform/security | root/nested/dangling symlink、special file、root identity/content drift、staging copy race、Windows root/nested reparse、ordinary cleanup与scan-delete race；外部 sentinel保持 |

## 6. Mandatory verification：exact commands 与结果

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### 6.1 Focused regression

```bash
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py -q
```

- exit `0`；`373 passed, 3 warnings in 9.64s`。
- 三个 warning 都来自 edgar 依赖 deprecated import，不是 R12 warning。

```bash
pytest tests/runtime/test_filelock.py tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py -q
```

- exit `0`；`146 passed in 0.24s`。

### 6.2 七个 production 文件逐文件 coverage

| exact command target | TOTAL | MISS | Cover | pytest |
|---|---:|---:|---:|---:|
| `pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q` | 276 | 27 | 90% | 31 passed |
| `pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q` | 233 | 13 | 94% | 35 passed |
| `pytest tests/cli/test_init_workspace.py --cov=dayu.cli.init_workspace --cov-report=term-missing --cov-fail-under=80 -q` | 547 | 70 | 87% | 90 passed |
| `pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init --cov-report=term-missing --cov-fail-under=80 -q` | 247 | 23 | 91% | 18 passed |
| `pytest tests/cli/test_arg_parsing.py --cov=dayu.cli.arg_parsing --cov-report=term-missing --cov-fail-under=80 -q` | 294 | 1 | 99% | 66 passed |
| `pytest tests/service/test_host_assembly.py --cov=dayu.service.host_assembly --cov-report=term-missing --cov-fail-under=80 -q` | 570 | 30 | 95% | 84 passed |
| `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing --cov-fail-under=80 -q` | 571 | 67 | 88% | 49 passed |

一次并发执行七条 coverage 命令时，`test_host_assembly` 的 pytest-cov 与其它进程争用同一 `.coverage` SQLite，84 个测试断言已通过但 combine 阶段报 `no such table: other_db.file`，进程 exit `3`。未修改代码或 coverage 数据来掩盖；随后单独按上表原 exact command 重跑，exit `0`、84 passed、95%，该隔离结果是 gate 结果。

### 6.3 Type 与 Ruff

```bash
python -m pyright dayu/ tests/ utils/
```

- exit `0`；`0 errors, 0 warnings, 0 informations`。

```bash
python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py dayu/cli/init_workspace.py dayu/cli/commands/init.py dayu/cli/arg_parsing.py dayu/service/host_assembly.py dayu/service/entrypoint_runtime.py tests/cli/test_init_catalog.py tests/cli/test_init_environment.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/service/test_host_assembly.py
```

- exit `0`；`All checks passed!`。
- `.venv` Ruff 版本：`ruff 0.15.11`。

```bash
set +e
python -m ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-current.json
ruff_current_status=$?
set -e
test "$ruff_current_status" -eq 1
test "$(python -c 'import json,sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))))' workspace/tmp/r12-ruff-current.json)" -eq 144
test "$(shasum -a 256 workspace/tmp/r12-ruff-current.json | awk '{print $1}')" = "051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea"
cmp workspace/tmp/r12-ruff-baseline.json workspace/tmp/r12-ruff-current.json
```

- full Ruff command按预期 exit `1`；JSON count `144`。
- baseline/current SHA-256 均为 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。
- `cmp` exit `0`，逐字节零差异；R12 未新增、删除、移动或改写历史诊断。

## 7. Diff、scope、source 与 security scans

### 7.1 Diff/scope

```bash
test "$(git diff --name-only -- dayu/service tests/service | sort)" = "$(printf '%s\n' dayu/service/README.md dayu/service/entrypoint_runtime.py dayu/service/host_assembly.py tests/service/test_host_assembly.py | sort)"
git diff --exit-code -- dayu/fins dayu/host dayu/engine dayu/tools dayu/runtime dayu/config/models.json dayu/config/prompts/manifests docs/fins/design.md docs/host/design.md docs/engine/design.md docs/tool/design.md docs/ui/design.md pyproject.toml utils
test -z "$(git status --porcelain=v1 -- dayu/fins dayu/host dayu/engine dayu/tools dayu/runtime dayu/config/models.json dayu/config/prompts/manifests docs/fins/design.md docs/host/design.md docs/engine/design.md docs/tool/design.md docs/ui/design.md pyproject.toml utils)"
git diff --check
test -z "$(git diff --cached --name-only)"
```

- 全部 exit `0`。
- Service diff 精确四路径；Fins/package/Host/Engine/Tool/runtime/design/pyproject/utils 零 diff/零 status；staged tree为空。
- `git diff --no-index --check /dev/null dayu/cli/init_workspace.py` 与对应 `tests/cli/test_init_workspace.py` 均无 whitespace diagnostic；新增 diff的命令级 exit `1` 是正常 no-index diff truth。

### 7.2 Source/security scans

执行 fixed-plan S2 适用的 `rg -n` scans，结果如下：

- `authorization|authorisation|tool[_ -]?auth|permission`：S2 CLI owner/测试零匹配，exit `1`。
- CLI Fins classifier/raw strip scan（`_is_fins_workspace_bound_provider_config|financial-*|dayu.fins.tools.*provider|pop/del workspace_root`）：production CLI零匹配，exit `1`。
- `metadata-only|synthetic|fake provider|test shim|manual-smoke|allow_empty`：production CLI零匹配，exit `1`。
- prewarm/runtime assembly symbols、forbidden import roots：`commands/init.py` 与 S2 command tests零匹配，exit `1`。
- `requests|httpx|urllib|socket|huggingface|download|web_search|open_host|run(`：S2 transaction/command production零匹配，exit `1`；无网络或外部模型探测。
- `assemble_effective_tool_provider_configs|discover_service_tools|SceneToolCatalog.from_tool_bundle`：`init_workspace.py` 只有 imports 与唯一真实 assembly/discovery/catalog call chain；`commands/init.py` 零重复 chain。
- `fins_workspace_root_override` production consumers精确为 ordinary `entrypoint_runtime.py: ...=None` 与 init `...=private_validation_root`；其它 production occurrences只在 Service owner declaration/forwarding。
- secret-name scan只命中测试中的 env names与脱敏断言；production不打印/持久化 value到workspace。
- containment/security scan确认 `follow_symlinks=False`、`O_NOFOLLOW`、`O_DIRECTORY`、Windows file attributes/reparse tag、identity/quarantine、fd-safe rmtree、retained/durability字段都位于唯一 transaction owner。
- deferred Issue/Topic/authorization字符串零匹配。`Web/WeChat` 仅出现在 fixed-plan要求的 RESET active-process警告、Service README non-consumer boundary与owner isolation测试，不包含路由、runtime或功能实现。
- broad `compat|fallback|shim` scan在 entry-existing Service/测试语义中有历史 `fallback` matches；S1/Service entry hashes与 full Ruff fingerprint证明这些不是 R12 S2新增兼容路径。新 `init_workspace.py`/`commands/init.py` 对该组为零匹配。

## 8. README 判断

- 已读取并遵守 `dayu/service/README.md` 的更新约束；Service effective-config public owner contract发生变化，因此只在现有 provider effective-spec 段补充 ordinary `None`、init private override、raw grammar先行、raw不改写、非 Fins/Web不消费的事实。
- `tests/README.md`、root `README.md`、`dayu/config/README.md` 均已检查 trigger，但 amended authorization与用户本 gate 明确只允许 Service README，且其它 README 归 S3；本轮未机械同步或越权修改。

## 9. Residual risks 与 owner

1. Windows 本轮只有 owner-level reparse/junction/ordinary cleanup/scan-delete race模拟；真实 Windows normal transaction、junction与rollback runner证据以及 release claim仍归 S3/Controller，当前不声明已在真实 Windows runner验证。
2. RESET 两个 managed roots是逐根 same-volume `os.replace` + rollback，不是跨根 single-syscall atomic transaction；这是 fixed-plan retained residual。
3. Windows缺少本项目已验证的 parent-directory fsync等价机制；保留同-volume visibility/rollback，不承诺 power-loss directory crash durability。
4. `.dayu-init.lock` 只串行 init，不是 Host/CLI/Web/WeChat process lock；RESET warning要求用户先停 active进程，R12不做 process discovery/kill。
5. 已持久化到 OS store 的环境变量无法与 workspace publication组成同一事务；失败输出只报告 written names，不能自动回滚 value。
6. S3 的 prewarm、POSIX/Windows real smoke、其它 README与full CLI仍未实现。静态检查还确认现有 `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 以无交互方式调用旧 init；S2 fixed focused不执行该测试，且该路径不在本轮 allowlist。Controller 在授权 S3 前应裁决其测试迁移路径，不能要求S2生产代码恢复隐式默认选择。

## 10. Controller validation handoff

Controller 可从以下只读命令开始：

```bash
git diff --check
git status --short
git diff --name-only
```

本轮停在 Controller validation，不自行更新 control doc，不进入 S3，不 stage/commit/push。
