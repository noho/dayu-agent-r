# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 Controller implementation authorization

## 1. Gate 身份与动机

- 这是既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 R12 cumulative slice S2，不是新 WU。
- S1 final adjudication：`docs/reviews/wu-semantic-ownership-01-r12-s1-code-final-rereview-controller-adjudication.md`，结论 `PASS / R12 S1 COMPLETE / READY_FOR_CUMULATIVE_S2_IMPLEMENTATION`。
- S1 不独立 commit；accepted plan 要求三个 cumulative slices，S2 在已通过 review 的 S1 未提交树上继续。
- 当前根因成立：现有 init 仍以拒绝式 existing-assets 与旧树 overlay 表达行为，没有唯一 workspace transaction owner，也没有 FIRST/PRESERVE/OVERWRITE/RESET 四态的正确 mutation boundary。

## 2. Authority locks

- HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Accepted plan：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，608 行，SHA-256 `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`。
- S1 final adjudication：89 行，SHA-256 `2872241503564cd45899fae732150880571d4ec01482376a825fb9611584bd5c`。

S1 immutable input contract：

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

`dayu/cli/init_workspace.py` 与 `tests/cli/test_init_workspace.py` 在 entry 时均为 `ABSENT`。

## 3. Exact writable scope

累计 product/test allowlist：

- 保留并按需引用 S1 四个路径；只有发现与 accepted S2 contract 的直接集成矛盾时才可修改，否则保持上述锁。
- 新增 `dayu/cli/init_workspace.py`。
- 修改 `dayu/cli/commands/init.py`。
- 修改 `dayu/cli/arg_parsing.py`。
- 新增 `tests/cli/test_init_workspace.py`。
- 修改 `tests/cli/test_init_command.py`。
- 修改 `tests/cli/test_arg_parsing.py`。
- 新增唯一 Agent artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-implementation-codex.md`。

不得修改 plan、control、既有 review artifacts、README、workflow、package JSON/manifests、runtime/Service/Host/Engine/Fins/Web/WeChat/render production；不得 stage、commit、push 或开 PR。

## 4. Required owner implementation

1. `init_workspace.py` 唯一拥有 `ManagedRootManifest({.dayu, config})`、typed snapshot/mode/request/result、no-follow containment、same-parent/same-filesystem private staging/backup、publish/rollback 与 cleanup-warning truth。
2. 删除 `commands/init.py` 的 `_raise_for_existing_assets` 拒绝语义和 overwrite 旧树 overlay；不得留 wrapper、fallback 或双 authority。
3. `commands/init.py` 只编排 plan §6.3 的固定顺序，并显式以 `timeout_seconds=None`、`create_parent_dirs=False` 获取 init lock；fresh root bootstrap 是它的唯一 owner，后续失败不得删除 root。
4. 完整实现 FIRST/PRESERVE/OVERWRITE/RESET 四态；PRESERVE 只补 missing prompt file，OVERWRITE/RESET 不 merge 旧树；按 plan §6.2，`reset+overwrite` 由 RESET 显式支配，不引入第五态或兼容报错。
5. RESET 先警告并显示精确 existing targets，默认 No/EOF/SIGINT 在 mutation 前终止；不得调用 Host lock/process discovery/kill。
6. publication boundary 前 staging 必须用真实 `RuntimeConfig`、既有 Service effective-provider assembly/discovery 和 `SceneToolCatalog.from_tool_bundle` 验证 13 个 runtime manifests，并传两个锁定空 slot；三个 `manual-smoke` manifest 仍仅由 test fixture 验证。
7. Environment persistence 失败不得 publish workspace；publication 后 backup delete/fsync failure 只能产生准确 warning、不得 rollback。
8. `arg_parsing.py` 仅更新 `--reset` / `--overwrite` 的真实四态帮助语义，不增加旧 workflow hidden flag。

## 5. S2 strict boundary

- 不接入 S3 exact-two-root import-only prewarm。
- 不新增 `tests/cli/test_init_smoke.py` 或 `.github/workflows/r12-init-windows.yml`。
- 不修改任何 README；README 更新属于 S3 完成态。
- 不宣称真实 POSIX/Windows subprocess smoke 或 release blocker 已关闭。
- 不实现 Issue 142/151/175/177/178、统一 tool authorization、Topic 8/9 或 Web/WeChat/render tracker 能力。
- `assets` 与 `portfolio` 永不成为 managed roots，package/user assets 不创建、不删除。

## 6. Mandatory verification

必须执行 accepted plan §8 S2 的全部命令，并在 artifact 记录 exit/result：

- 累计五文件 CLI tests；runtime filelock/config-loader/scene-prepare regression；
- 五个 production 文件逐文件 coverage `>=80%`，其中 `commands/init.py` 只使用 S2 已存在的 `test_init_command.py`；
- full pyright 零诊断；累计 changed-path Ruff 零诊断；
- full Ruff JSON 精确 `144` / `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` / baseline `cmp=0`；
- `git diff --check`、staged empty、exact-scope/source/security/deferred scans；
- 按 plan 对四态、fresh-root race、symlink/containment、real lock competition、全部 pre-publication fault points、post-publication cleanup fault、secret persistence failure 做 owner contract assertions。

## 7. Stop conditions

命中 accepted plan §10.2 任一条件立即停回 Controller；尤其：

- 需要改动 allowlist 外 production/package 配置才能完成真实 staging validation；
- 13/3 manifest 或 required context slot 真值漂移；
- 必须把 assets/portfolio 纳入 managed roots；
- 必须调用 Host lifecycle/process kill、使用 finite magic lock timeout、兼容旧 schema 或引入 test shim；
- full pyright 非零、changed-path Ruff 非零、full Ruff fingerprint 漂移。

## 8. Authorized next gate

`AgentCodex R12 S2 cumulative implementation only`。

完成后停回 Controller validation；S2 code review、S3、aggregate、accepted implementation commit 仍需分别授权。
