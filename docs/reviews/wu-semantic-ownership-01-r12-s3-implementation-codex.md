# WU-SEMANTIC-OWNERSHIP-01 / R12 S3 implementation — AgentCodex

## Gate 与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S3 cumulative implementation；不是新 WU。
- 结论：`LOCAL_IMPLEMENTATION_PASS / READY_FOR_CONTROLLER_VALIDATION`。
- Umbrella 状态：R12 尚未 close；本 artifact 只交 Controller checkpoint。
- 固定计划：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，SHA-256
  `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`。
- S2 final Controller 裁决：
  `docs/reviews/wu-semantic-ownership-01-r12-s2-code-final-rereview-controller-adjudication.md`，
  26 行 / 2,916 字节 / SHA-256
  `e52abe47468953e3e9dcc1df9b26186a9f185ba40dbd5afb7ccd808d23507eac`。
- 未 stage、commit、push、创建或修改 PR；`git diff --cached --name-only` 为空。

## Controller follow-up 授权

首次运行 affected matrix 时，
`tests/cli/test_arg_parsing.py::test_root_readme_matches_current_cli_public_contract`
仍冻结旧句“`init` 是非交互式文件初始化命令”，与 S2 已落地的显式交互选择及 S3 根 README
传播要求直接矛盾。Agent 未把旧句以否定/历史话术塞回用户手册，也未增加 production fallback，先按
stop condition 报告。

Controller 随后明确纠正先前过严的 immutable 指令：固定计划允许 S3 累积消费 S1/S2 路径，并只授权修改
上述 owner-level README contract assertion，使其验证当前 FIRST/PRESERVE/OVERWRITE/RESET、secret
persistence、lock 与 prewarm 语义。实现严格只迁移该 test function；其它原 immutable S2 paths 未改。
该路径终态 SHA-256 是
`2bb87bbeabb7b81df3e7e069904588a357049ffa970e22d1f5b598cf7b36c87c`。

## 第一性原理与 semantic ownership

S3 动机成立：config publication 已由 S2 transaction owner 完成，但 FIRST/RESET 后真实 CLI 入口 import
成本、跨平台真实用户工作流和用户文档尚缺 owner-level evidence。实现边界保持：

- `dayu/cli/commands/init.py` 继续唯一拥有 init 生命周期、publish 后 prewarm 决策与 warning 投影；
- 被导入模块自己拥有 transitive import graph；init 不复制 `session_execution` /
  `entrypoint_runtime` 或更深模块列表；
- `ConfigLoader`、Service effective provider assembly、tool discovery 与 ScenePrepare 继续拥有配置和 scene
有效性；smoke 只消费这些 production owners；
- `dayu.runtime.filelock` 继续拥有 lock primitive；竞争 smoke 只观察已有公开 waiting notification；
- README 是 production contract 的用户/开发者投影，测试只验证该投影，不反向定义业务语义；
- Windows workflow 只执行真实 runner evidence，不为 production 增加 platform seam。

没有新增 lifecycle/cache/preload framework、assembly callback、network probe、finite production timeout、
workspace/env prewarm input、兼容分支、test shim 或下游 fallback。

## 实现内容

### Exact-two-root import-only prewarm

`dayu/cli/commands/init.py` 新增模块级私有 immutable tuple，顺序精确为：

1. `dayu.cli.commands.interactive`
2. `dayu.cli.commands.prompt`

无参同步 helper 只循环调用 `importlib.import_module(...)`。FIRST/RESET 在
`publish_workspace_transaction(...)` 成功返回后各调用一次；PRESERVE/OVERWRITE 零次。普通 import
异常只输出 `error_type` 与固定安全摘要，且经既有 best-effort diagnostic boundary 处理；不输出 exception
message，不回滚已发布配置，不改变成功退出。`KeyboardInterrupt` / `SystemExit` 未被吞掉。

### Owner tests 与真实 POSIX smoke

- `tests/cli/test_init_command.py` 断言 exact roots、顺序、FIRST/RESET 一次、PRESERVE/OVERWRITE 零次，
  以及 import failure 的安全 warning 和 publication 保持。
- `tests/cli/test_init_smoke.py` 的隔离 subprocess 设置 `PYTHONDONTWRITEBYTECODE=1`，用 socket
  fail-fast observation seam、临时 workspace identity/content digest 和 environment snapshot 证明两次 helper
  调用连续稳定、零网络、零外部 workspace/env mutation；同时断言 exact roots、真实
  `dayu.cli.session_execution` / `dayu.service.entrypoint_runtime` transitive imports 和三个 deleted roots absent。
- 真实 POSIX subprocess 完成 FIRST→PRESERVE→OVERWRITE→RESET No→RESET Yes；PRESERVE 保留 user
  file/manifest并补缺失 package prompt，OVERWRITE 恢复 package defaults，RESET No 整树 digest 不变，
  RESET Yes 重建；真实 `ConfigLoader`、Service discovery 和 13 scenes 再校验已发布配置。
- 独立 reset boundary 证明 public `portfolio/` / `assets/` sentinel bytes 与 identity 保持，普通 FIRST
  不创建它们；真实 POSIX profile 证明 mode `0600`、唯一 marker block、原子替换和 captured output 脱敏。
- 真实 `file_lock(..., timeout_seconds=None)` 竞争用公开“正在等待此 workspace lock”通知协调；单 waiter
  在 release 前零 publish，两个基于既有 PRESERVE config 的 queued publishers 在同一 parent-held lock 后
  串行成功。test harness 只使用 bounded read/process timeout，无 `sleep`、重试或 production timeout。

### Stale explicit-interaction caller 与 README contract

- `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 现在向真实
  init 提供明确 Ollama 选择、dynamic defaults 和 optional-empty 输入；未给 production 加 implicit default。
- Controller follow-up 授权的 README contract test 删除旧“非交互式”断言，直接验证四态、RESET
  precedence、POSIX/Windows secret persistence、names/value boundary、init-only lock、active-process warning 和
  FIRST/RESET prewarm。

### Windows workflow

新增 `.github/workflows/r12-init-windows.yml`：

- `windows-latest` + Python 3.11；使用
  `constraints/lock-windows-x64-py311.txt` 安装 locked `.[test,dev]`；
- 真实运行 FIRST→PRESERVE→OVERWRITE→RESET No→RESET Yes、ConfigLoader/scene reload；
- 真实创建 nested directory junction，读取 `st_file_attributes` / reparse tag，要求 publication 前
  `tree_identity` fail closed、`retained=none`、public config identity/bytes 与 external sentinel identity/bytes
  不变；普通 symlink 只允许精确 `winerror=1314` skip；
- 运行真实 workspace root identity drift、replace-failure rollback 与 scan-delete race/fault 节点；
- 用唯一运行期 sentinel 完成真实 `setx`、user registry read 与 cleanup；CLI/JUnit 不打印 value；
- 同时运行 R11 两个真实 cmd/upload blocker nodes；
- artifact 只上传 JUnit、OS/Python/capability、source hashes 和 env names，不上传 environment/registry values
  或 raw registry output。

本机为 Darwin，没有执行或伪造 Windows 结果。真实 Windows runner 是 workflow 后续 release evidence；
Controller/reviewer 在该 workflow 成功前不得把 Windows gate 写成已通过。

### README

- `README.md`：按最终用户边界记录交互选择、四态、secret 目标/确认/脱敏、symlink/reparse、RESET 前停止
  active Dayu、init-only lock、waiting notification 与 prewarm warning 排障。
- `dayu/config/README.md`：记录 ConfigLoader/current JSON owner、四态 config contract、16 known manifests
  projection 与 secret ref/value boundary。
- `tests/README.md`：记录 owner/fault/真实 POSIX smoke 与 Windows workflow；不写未落地测试。
- `dayu/README.md`：零 diff；本 S3 没有新的分层/装配边界变化。

## Final target hashes

### S3 新增/修改路径

| 路径 | SHA-256 |
|---|---|
| `dayu/cli/commands/init.py` | `c30eb407d2bd462ab0d91a06b88a85aaef4b3cfa08010e474027c386f7026cb1` |
| `tests/cli/test_init_command.py` | `71c90d3acbbdb2baf74522905820b7aba0e7529bc0a75da10f2422b05fb4f199` |
| `tests/cli/test_init_smoke.py` | `7d8c363d1ba0b51aad2932564928ae4ebfa139e1ab5a174690af9a22571f3732` |
| `tests/cli/test_prompt_command.py` | `a9ca7be14aa952ca602b59a2bbf228c51da53aa02b596d8887c0d9d0be2ce5f9` |
| `tests/cli/test_arg_parsing.py` | `2bb87bbeabb7b81df3e7e069904588a357049ffa970e22d1f5b598cf7b36c87c` |
| `.github/workflows/r12-init-windows.yml` | `a465abb382ae0fcecc402ffc45bf8b98cdb7ebe37d5215adcbc3e0988f30f541` |
| `README.md` | `bd2f7bc12ee76f26b5d3a580f1f1e81c36bb57d964fb191fb09f92da051010fa` |
| `dayu/config/README.md` | `e7d6e88fffc0c6d7e83c0f1a54c8fa197ec204abcbdb53e345506078ac92caf7` |
| `tests/README.md` | `62f6d7d90daabf63ed2a8a3f6e01bacbe24efcbc9084ca770c34461b91ba228a` |

### 保持不动的 S2 cumulative paths

以下路径与 S2 final re-review 固定 hash 精确一致：

| 路径 | SHA-256 |
|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` |
| `dayu/cli/init_environment.py` | `16353a72bce2efeeac1aae64f1f0c94cdca2e30e956be9412f2f0f20002059c0` |
| `dayu/cli/init_workspace.py` | `b5aac7f486d86d0c01896a2fc3533d028d0e5064f43982bb2974fddc7efd3fd7` |
| `dayu/cli/arg_parsing.py` | `add2353afbc64db84af1c4df899dfa8a692409131d91570d6c7fac7d1241319e` |
| `dayu/service/host_assembly.py` | `658b57e5378ea6ea849203106e2bd57b38e1d6917a93743264cd22ec2f2c27b9` |
| `dayu/service/entrypoint_runtime.py` | `4e16540335ae9a614381d59899dcda23f590f42320494a093e01ce0329344632` |
| `dayu/service/README.md` | `d1eed1d028fda7df7e913361fdd313109d262a952433ad8c99ef2a1c0c9f4d79` |
| `tests/cli/test_init_catalog.py` | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` |
| `tests/cli/test_init_environment.py` | `5bc46652d54ae5e6860424c3acb952ce2dd615cb0df09eb1ae5c3b6c1f184618` |
| `tests/cli/test_init_workspace.py` | `c363bc1916ceb3204f517a038d70ce632d0c3d8fd17319651cfee2ecb8f3e95b` |
| `tests/service/test_host_assembly.py` | `28e099404bcf931dc4c78158288705c1f1ff555966eadf08a3f5d3df865e6ad8` |

16 个 package known manifest hashes、`dayu/config/models.json`、ConfigLoader/file_lock/scene anchors 和 R11
workflow anchor 也都与 fixed-plan entry 一致。

## 验证

### Tests

| Profile | 结果 |
|---|---|
| S3 cumulative affected CLI/Service | `408 passed, 5 skipped, 3 warnings` |
| runtime/config/scene/tool anchors | `184 passed` |
| full `tests/cli` | `505 passed, 7 skipped, 3 warnings` |
| final Service target | `133 passed, 3 warnings` |
| focused S3 + stale prompt caller | `33 passed, 5 skipped, 3 warnings` |

5 个 S3 smoke skip 都是本机 Windows-only nodes；full CLI 另外包含既有 Windows-only nodes。三条 warning
均为既有 `edgar` deprecation warning，不是 R12 失败。

### 七个 production 单文件 coverage

| Production file | TOTAL | MISS | Coverage |
|---|---:|---:|---:|
| `dayu/cli/init_catalog.py` | 276 | 27 | 90% |
| `dayu/cli/init_environment.py` | 304 | 16 | 95% |
| `dayu/cli/init_workspace.py` | 547 | 70 | 87% |
| `dayu/cli/commands/init.py` | 295 | 27 | 91% |
| `dayu/cli/arg_parsing.py` | 294 | 1 | 99% |
| `dayu/service/host_assembly.py` | 570 | 30 | 95% |
| `dayu/service/entrypoint_runtime.py` | 571 | 67 | 88% |

每项独立运行且 `--cov-fail-under=80` 通过；没有用聚合 coverage 替代。

### Type / lint / diff

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 15 个 cumulative changed/new Python paths scoped Ruff：`All checks passed!`；包含 Controller follow-up 的
  `test_arg_parsing.py` 与 stale caller `test_prompt_command.py`。
- full Ruff：`ruff 0.15.11`，baseline/current 都是 144 diagnostics，JSON SHA-256 都为
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`，`cmp` exit 0。
- `git diff --check`：pass。
- staged tree：空。
- Service exact diff：仅 `dayu/service/README.md`、`dayu/service/entrypoint_runtime.py`、
  `dayu/service/host_assembly.py`、`tests/service/test_host_assembly.py`。
- Fins/Host/Engine/Tool/runtime/package models+manifests/design/pyproject/utils restricted diff/status：零。
- `dayu/README.md`：零 diff。

### Source / propagation scans 分类

- prewarm production import scan：只命中 exact prompt/interactive roots 与 `importlib.import_module`；
  `session_execution` / `entrypoint_runtime` / deleted roots 只在测试 transitive/absent assertions 中出现。
- forbidden runtime assembly-call scan on `commands/init.py`：零命中。
- CLI-side Fins classification/raw stripping、metadata-only/synthetic/fake provider/test shim production scans：零命中。
- network scan：只命中 `urllib.parse.urlsplit`（本地 URL 语法校验）和 environment owner 的
  argument-safe `subprocess.run`；无 HTTP client、download、Host/runtime assembly。
- `compat` 字面扫描只命中业务展示/说明 `OpenAI-compatible` 与 schema `openai_compatible`，不是兼容代码；
  R12 production 无 fallback/shim/`hasattr`/`getattr`。
- auth scan 的既有 CLI host-context/test fixtures 不属于 R12 diff；R12 init production/test additions无授权分支。
- env scan只有固定 env names、schema refs、测试断言和 README 示例；未把运行期 sentinel value、profile 内容、
  subprocess captured output 或 registry value写入 tracked artifact。
- assets/portfolio 命中只表达不创建/不删除、reset sentinel 保持和 private validation isolation。
- Issue/Topic/Web/WeChat/render 命中均为既有代码/README上下文或 RESET active-process告警；无新实现分支。

## Residual risks / uncovered areas

1. **Windows real runner evidence — covered by approved workflow, 尚未在本机执行。**
   `.github/workflows/r12-init-windows.yml` 必须在 Windows release gate 真实运行并产出 name-safe artifact；
   workflow 未成功前不得关闭 S3 review 的 Windows evidence 条件。
2. **固定计划既有 RESET 两根 managed roots 非单 syscall 原子 residual — unchanged。**
   S3 未扩大 Host/process lock、journal 或 filesystem framework；S2 rollback truth 与 RESET 前 active-process
   提示保持唯一当前 contract。

没有未分类 residual、deferred finding 或需要新 issue 的 S3 implementation finding。下一 entry point 仅为
Controller validation；不得自行 close umbrella、commit、push 或开 PR。

本 artifact 自身的最终行数、字节数与 SHA-256 由文件关闭后的机械核验/Controller 读取。
