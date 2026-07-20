# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 amended Controller implementation authorization

## 1. Gate 身份与授权结论

- 这是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 cumulative slice S2 continuation，不是新 WU、不是新 feature/issue，也不是重新打开历史 sub-WU。
- 原 S2 implementation 命中真实 stop condition 后已完整恢复 entry tree；旧 authorization 仅保留历史 provenance，本文件以 fixed plan 和最终双路 re-review 裁决 supersede 其 plan hash、Service zero-diff 与 writable-scope 部分。
- Fixed-plan final Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-final-rereview-controller-adjudication.md`，结论 `PASS / R12-S2-PR-F01..F06 CLOSED 6/6`。
- Authorized next gate：`AgentCodex R12 S2 cumulative implementation continuation only`。

## 2. Authority locks

- HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Fixed plan：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，708 行 / 105,368 字节 / SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`。
- AgentMiMo final re-review：369 行 / 32,071 字节 / SHA-256 `67814b7b48fce0987de2efc843e2444369c2d2eee2d5ac45eea6ad305f09f49b`。
- AgentDS final re-review：457 行 / 38,671 字节 / SHA-256 `f2155645fdb218b520d9ef3ef4315c5854af90f2d169b6412d9fb5d79d2de61f`。
- 原 stop handoff：`docs/reviews/wu-semantic-ownership-01-r12-s2-implementation-codex.md`，155 行 / 9,139 字节 / SHA-256 `b123dff616a0c4ac22bb3d1f47b00fe5913a9747e9f3e413ff34462ddbd82fcd`；只读，不覆盖。

S1 terminal inputs 必须保持不变：

| 路径 | SHA-256 |
|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` |
| `dayu/cli/init_environment.py` | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` |
| `tests/cli/test_init_catalog.py` | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` |
| `tests/cli/test_init_environment.py` | `820c2bf262dd77628201977e7d4f823265e141ac0ae6a28791bd7d12cf5ad01a` |

S2 existing-file entry locks：

| 路径 | 行数 | SHA-256 |
|---|---:|---|
| `dayu/cli/commands/init.py` | 470 | `c33db7318476e54f81630c5e5ec8b33e94a6281dd12ecd2ddc7ee85da57b10ab` |
| `dayu/cli/arg_parsing.py` | 949 | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` |
| `tests/cli/test_init_command.py` | 587 | `c7d226ed8f72ae846c3f3cca1cd500a2342e7050750415cb0022ea5e5bb15364` |
| `tests/cli/test_arg_parsing.py` | 1240 | `d3a4abcc22093ff6c4e06edebf249282f1fbac9d9eb3a575c618f28210742658` |
| `dayu/service/host_assembly.py` | 2349 | `54559d2ea0446316b4ff82bf66594dfaa5d7b75067d495f5d3558d2ea94bbe52` |
| `dayu/service/entrypoint_runtime.py` | 1866 | `014c5ea0cf16d3538793883277672d70764d5a812054028369c98c229c0115c6` |
| `tests/service/test_host_assembly.py` | 3248 | `04675e6629e80d8348e9abc1f87f4c4b7762b59e9eef17d6dd67f1b3689a203e` |
| `dayu/service/README.md` | 42 | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` |

`dayu/cli/init_workspace.py` 与 `tests/cli/test_init_workspace.py` 在 resume entry 均为 `ABSENT`。

## 3. Exact writable scope

S2 product/test/owner-doc allowlist 精确为：

- 新增 `dayu/cli/init_workspace.py`；
- 修改 `dayu/cli/commands/init.py`；
- 修改 `dayu/cli/arg_parsing.py`；
- 新增 `tests/cli/test_init_workspace.py`；
- 修改 `tests/cli/test_init_command.py`；
- 修改 `tests/cli/test_arg_parsing.py`；
- 修改 `dayu/service/host_assembly.py`；
- 修改 `dayu/service/entrypoint_runtime.py`；
- 修改 `tests/service/test_host_assembly.py`；
- 按 README 内约束只记录本 finding 所需 owner contract，修改 `dayu/service/README.md`；
- 新增唯一 Agent resume artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-implementation-resume-codex.md`。

S1 四路径可被调用但不可修改。旧 stop artifact、plan、control、既有 reviews、root/config/tests README、workflow、package JSON/manifests、runtime/Host/Engine/Fins/Tool/Web/WeChat/render production 均不可修改。不得 stage、commit、push 或开 PR。

## 4. Required implementation contracts

1. `init_workspace.py` 唯一拥有 `ManagedRootManifest({.dayu, config})`、typed snapshot/mode/request/result、fresh root 后的 containment/identity、same-parent/same-filesystem staging/backup、transaction-private validation workspace、platform-specific no-follow cleanup、publish/rollback 和 truthful cleanup/durability result。
2. 删除 `commands/init.py` 的 existing-assets 拒绝语义和旧树 overlay；唯一实现 FIRST/PRESERVE/OVERWRITE/RESET，`RESET > OVERWRITE`，不增加第五态、兼容报错、fallback 或双 authority。
3. RESET 在 mutation/bootstrap 前显示 active-process 警告和 exact targets，默认 No/EOF/SIGINT 零 mutation；不得调用 Host lock/process discovery/kill。fresh workspace root 只能由 orchestrator 显式创建，init lock 必须 `timeout_seconds=None`、`create_parent_dirs=False`。
4. `host_assembly.py` 在既有 effective-config owner 增加 keyword-only `fins_workspace_root_override: pathlib.Path | None = None`。raw Fins `config.workspace_root` 必须先通过现行 type/non-empty grammar；对合法未配置、显式绝对、显式相对 raw，non-`None` override 在 raw path selection/return 前成为 canonical absolute effective Fins root。relative override 必须拒绝。
5. `entrypoint_runtime.py` ordinary caller 显式传 `fins_workspace_root_override=None`，保持用户 raw explicit root 语义。R12 init validation 是唯一 production non-`None` consumer；CLI 不复制 Fins provider classification，不 strip/改写 raw config，不新增 schema、metadata-only discovery、synthetic/fake provider、compat/fallback 或 production test seam。
6. Staging validation 必须使用 public canonical ordinary `workspace_root` 加 private absolute Fins override，真实 `ConfigLoader`、Service effective-provider assembly、一次真实 `discover_service_tools(...)` 和 `SceneToolCatalog.from_tool_bundle(...)`，验证 13 个 runtime manifests与两个锁定空 slot。三个 manual-smoke manifests 只由 test-owned explicit catalog fixture 验证。
7. 三类合法 raw Fins root 都要观察到真实 `.dayu` / `portfolio` side effect 只落入 transaction-private validation root；raw/staging/public bytes不变，非 Fins/Web 继续使用 ordinary public root。validation cleanup必须在 publication 前完成并按平台 contract fail closed，不能清理 public `.dayu`/`portfolio`/`assets` 补偿。
8. POSIX 只有 `shutil.rmtree.avoids_symlink_attacks is True` 时可使用 fd-safe `rmtree`；Windows 使用 identity/quarantine/reparse-point contract，正常 init 不能因 capability flag 缺失被永久拒绝。pre-seeded junction/symlink必须 pre-publication fail closed并保持外部 sentinel；scan-delete race必须独立证明不跟随外部目标。
9. 完整实现 fixed plan §8 fault matrix：test 可在 owner module boundary monkeypatch syscall fault，但不得向 production 增加 callback/factory seam。validation child已删但 POSIX parent sync失败、partial deletion、publication rollback、post-publication cleanup warning都必须报告唯一 truthful retained state。
10. Environment persistence failure 不得 publish workspace；publish 后 backup delete/sync failure只能 warning，不得 rollback。`arg_parsing.py` 只更新 `--reset`/`--overwrite` 真实四态帮助。

## 5. Mandatory verification

必须执行 fixed plan §8 S2 与 §9 的完整 profile，并在 resume artifact 记录 exact command/result：

- cumulative CLI + Service focused regression；
- `init_catalog.py`、`init_environment.py`、`init_workspace.py`、`commands/init.py`、`arg_parsing.py`、`host_assembly.py`、`entrypoint_runtime.py` 七个 production 文件逐文件 coverage `>=80%`；
- full `python -m pyright dayu/ tests/ utils/` 零诊断；
- cumulative changed-path Ruff 零诊断，full Ruff JSON 精确 `144` / `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` / baseline `cmp=0`；
- `git diff --check`、staged empty、exact scope、Service exact four-path diff、Fins/package/Host/Engine/Tool/runtime/design/deferred zero diff；
- override consumer、ordinary `None`、CLI provider-classification/raw-strip、duplicate discovery/parser、synthetic/metadata-only/test-shim、security/containment/source propagation scans；
- 四态、fresh-root race、real lock competition、raw Fins root三态、invalid raw不被 override掩盖、non-Fins isolation、public byte/identity isolation、nested symlink/dangling symlink、Windows reparse/junction模拟、root identity drift、外部 sentinel、全部 fault rows、secret persistence failure的 owner assertions；
- 按 `dayu/service/README.md` 与 `tests/README.md` 内约束检查 README trigger；S2 只允许 Service owner README 改动，其它 README 推迟到 S3。

## 6. Stop conditions

命中 fixed plan §10.2 任一条件立即停止并交 Controller。特别是：

- 13/3 manifests、tags、slots 或 Service Fins classification 漂移；
- override 需要跳过 raw grammar、改 raw bytes/schema、进入非 Fins/Web，或需要第二个 classification/discovery chain；
- 真实 Fins side effect 逃出 private validation root，或需要清理 public path；
- 需要 allowlist 外 Service/Fins/package/runtime/Host/Engine/Tool production、Issue 142/151/175/177/178、Topic 8/9、统一 tool authorization或 Web/WeChat/render 能力；
- POSIX/Windows no-follow contract无法安全实现，或普通 Windows init只能永久 fail closed；
- full pyright非零、changed-path Ruff非零、full Ruff fingerprint漂移、S1 locks漂移或 staged tree非空。

## 7. Authorized next checkpoint

AgentCodex 完成 S2 实施与全部验证后停止到 Controller validation。S2 code review、S3、aggregate、accepted local implementation commit、Windows release claim、push 和 PR 仍需后续独立授权。
