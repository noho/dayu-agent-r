# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 implementation stop-condition handoff

## 1. Gate 身份与结论

- Gate：既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 R12 cumulative slice S2 implementation，不是新 WU。
- Agent：AgentCodex。
- 结论：`STOPPED / ACCEPTED PLAN §10.2 REAL STAGING VALIDATION CONTRADICTION`。
- 本轮未进入 S2 code review、S3、aggregate、commit、push 或 PR。
- Controller 在执行期间原地纠正了 authorization §4.4；更新后 authority SHA-256 为
  `259abecca9fb36112013dcc3be72320d9fe824604ca39eeddb44936f779c2f86`。本轮接受纠正后的唯一语义：
  `RESET > OVERWRITE`，`--reset --overwrite` 归入 RESET，不产生第五态或兼容报错。
- 上述 factual correction 与本 artifact 记录的 staging validation contradiction 正交，没有解除 §10.2 stop condition。

## 2. 第一性原理判断与直接证据

S2 要求在 workspace publication 前同时成立：

1. 使用 staging `RuntimeConfig`、真实 Service effective-provider assembly/discovery、
   `SceneToolCatalog.from_tool_bundle(...)` 校验 13 个 production manifests；
2. effective-provider assembly 按 accepted plan §6.4 接收当前用户 workspace root；
3. publication 前不得改变 managed roots；
4. `portfolio/` 不是 managed root，且 package/user `assets`、`portfolio` 不由 init 创建或删除。

真实调用链证明这四项当前不能同时成立：

- `dayu.service.host_assembly.assemble_effective_tool_provider_configs(...)` 会把传入的当前 workspace root
  注入四个 Fins provider 的 effective `workspace_root`；直接 owner 是
  `dayu/service/host_assembly.py::_effective_fins_workspace_root_config_value`。
- `dayu.service.host_assembly.discover_service_tools(...)` 会真实执行 enabled provider binding；这不是
  metadata-only parser。
- Fins provider 随后调用 `DefaultFinsRuntime.create(workspace_root=...)`；
  `dayu/fins/service_runtime.py` 直接构造 filesystem repository set 与
  `FsFinsIngestionJobStore.from_workspace_root(...)`。
- Fins filesystem owners 在构造时创建 repository roots、`portfolio/`、`.dayu/` 及 ingestion job store；
  例如 `FsFinsIngestionJobStore.__post_init__` 明确执行 `root_dir.mkdir(parents=True, exist_ok=True)`。

因此根因是 accepted plan 指定的真实 Service/Fins public seam 本身具有 workspace filesystem side effect，
不是 init transaction、测试替身、日志或间接迹象造成。

## 3. 可复现探针与磁盘真值

在 production/test 修改前锁定 Ruff baseline 后，本轮用 fresh
`workspace/tmp/r12-s2-probe-a`、Ollama 非 secret 输入执行了一次真实 CLI staging 探针。
探针调用的真实链为：

```text
ConfigLoader(staging)
-> assemble_effective_tool_provider_configs(..., workspace_root=<fresh public workspace>)
-> discover_service_tools(...)
-> SceneToolCatalog.from_tool_bundle(...)
```

结果：

- shell command exit：`0`（探针脚本本身正常结束）；
- 内部 `dayu-cli init` result：`1`；
- init 安全停止原因：`managed-root snapshot changed; rerun dayu-cli init`；
- `config/` 未 publish；
- 真实 discovery 在 publication 前已经创建以下 public paths：

```text
workspace/tmp/r12-s2-probe-a/portfolio
workspace/tmp/r12-s2-probe-a/.dayu/repo_batches
workspace/tmp/r12-s2-probe-a/.dayu/repo_backups
workspace/tmp/r12-s2-probe-a/.dayu/batch_recovery.lock
workspace/tmp/r12-s2-probe-a/.dayu/fins_ingestion/jobs
workspace/tmp/r12-s2-probe-a/.dayu/batch_locks
```

该结果同时证明：

- snapshot 漂移不是误报；真实 discovery 新建了 manifest 内 `.dayu/`；
- 即使忽略 snapshot，public `portfolio/` 的创建仍违反 S2 strict boundary；
- 在 discovery 后删除这些路径不是合法修复：会让 init 下游清理 Service/Fins owner 的副作用，并可能删除并发用户数据；
- 把 `portfolio` 纳入 `ManagedRootManifest` 同样被 plan/authorization 明确禁止。

探针仅位于 `workspace/tmp/`，未进入 tracked diff，未使用或记录任何 secret value。

## 4. Stop-condition 裁决

命中的 accepted plan §10.2 / authorization §7 条件：

- 真实 Service public seam 与 §6.4 的 pre-publication/no-public-mutation contract 冲突；
- 在不改 plan 的情况下，继续需要以下至少一种越界动作：
  - 修改 allowlist 外 Service/Fins production，使 discovery 变为 metadata-only / side-effect-free；
  - 把 `portfolio` 纳入 managed roots；
  - discovery 后由 init 删除 public `.dayu` / `portfolio`；
  - 使用 synthetic catalog、mock provider 或 production test shim 跳过真实 discovery。

四条路径均被当前 authority 禁止。故 AgentCodex 必须停止并交 Controller，不能通过 fallback、清理补偿、
扩大 manifest 或测试替身继续实现。

## 5. 建议 Controller 裁决的最小修订

首选最小方案是修订 accepted plan §6.4 / S2 authorization：

- 仍使用 staging `RuntimeConfig`、真实 Service effective-provider assembly/discovery、真实
  `SceneToolCatalog.from_tool_bundle(...)` 和 13 个 production scene；
- 但把 effective-provider assembly 的 `workspace_root` 改为本 transaction 私有目录内的独立 validation
  workspace root，而不是用户 public workspace root；
- validation discovery 产生的 `.dayu/` / `portfolio/` 全部属于 transaction-owned private tree，在 publish 前
  安全清理；用户 public `.dayu`、`config`、`portfolio`、`assets` 保持不变；
- 该修订只改变 validation 隔离位置，不引入 synthetic provider、duplicate parser、Host lifecycle、兼容层或
  allowlist 外 production 修改。

不建议为了 init validation 修改 Service/Fins provider 的既有 runtime 构造语义；那会扩大 owner boundary，且不是
完成当前 S2 的最小方案。Controller 必须先明确 validation workspace 的语义 owner 与 amended authority，Agent 才能
重新进入 S2 implementation。

## 6. Before / after hashes 与 retained scope

发现 stop condition 后，AgentCodex 已将未完成的 production edits 恢复到 S2 entry lock；没有留下半实现。

| 路径 | Before | Retained after |
|---|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | 同 before |
| `dayu/cli/init_environment.py` | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` | 同 before |
| `tests/cli/test_init_catalog.py` | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` | 同 before |
| `tests/cli/test_init_environment.py` | `820c2bf262dd77628201977e7d4f823265e141ac0ae6a28791bd7d12cf5ad01a` | 同 before |
| `dayu/cli/commands/init.py` | `c33db7318476e54f81630c5e5ec8b33e94a6281dd12ecd2ddc7ee85da57b10ab` | 同 before |
| `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` | 同 before |
| `tests/cli/test_init_command.py` | `c7d226ed8f72ae846c3f3cca1cd500a2342e7050750415cb0022ea5e5bb15364` | 同 before |
| `tests/cli/test_arg_parsing.py` | `d3a4abcc22093ff6c4e06edebf249282f1fbac9d9eb3a575c618f28210742658` | 同 before |
| `dayu/cli/init_workspace.py` | `ABSENT` | `ABSENT` |
| `tests/cli/test_init_workspace.py` | `ABSENT` | `ABSENT` |

本 artifact 是唯一新增 retained Agent path。其最终行数、字节数与 SHA-256 在文件关闭后机械计算，并在 Controller
handoff 中报告，避免把文件自身完整 hash 写回自身形成不可能的 self-reference。

## 7. 已执行验证

| 验证 | 结果 |
|---|---|
| Authority/S1/S2 entry hashes | correction 后 authority 与全部锁定输入精确匹配 |
| Entry Ruff version | `ruff 0.15.11` |
| Entry full Ruff JSON | `144` / `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` |
| Real staging probe | 复现 public `.dayu` / `portfolio` side effect；CLI 安全失败、config 未 publish |
| Production/test restore hashes | 全部精确恢复 entry/S1 locks |
| `git diff --check` | PASS |
| staged tree | empty |

accepted plan §8 的累计 focused/runtime tests、五个 production 单文件 coverage、full pyright、scoped/full Ruff
终态 fingerprint 与完整 source/security/deferred scans没有继续执行。原因不是把验证 gap 延后，而是 authority 明确要求命中
§10.2 时立即停止；在没有合法 `init_workspace.py` implementation 的 entry tree 上运行 S2 completion profile也不能证明
S2 完成。

## 8. README、residual 与下一入口

- README：未修改。S2 authorization 明确把 README 更新延至 S3；当前也未形成可记录的完成态行为。
- S1 四文件：immutable，未修改。
- S3：未进入；未接 prewarm、未新增 smoke/Windows workflow、未宣称 Windows blocker 关闭。
- Residual：`REQUIRES CONTROLLER DECISION`——真实 discovery 的 public filesystem side effect 与 accepted validation
  root 发生 owner contradiction；推荐由 Controller 明确授权 transaction-private validation workspace root。
- 下一入口：`Controller stop-condition adjudication / amended S2 authorization`，不是 S2 validation、code review 或 S3。
