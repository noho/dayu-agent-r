# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 implementation stop-condition Controller 裁决

## 1. Gate 身份

- 这是既有 umbrella WU `WU-SEMANTIC-OWNERSHIP-01` 的 R12 cumulative S2 implementation stop-condition 裁决，不是新 WU。
- AgentCodex handoff：`docs/reviews/wu-semantic-ownership-01-r12-s2-implementation-codex.md`，155 行 / 9,139 字节 / SHA-256 `b123dff616a0c4ac22bb3d1f47b00fe5913a9747e9f3e413ff34462ddbd82fcd`。
- 本裁决只判断根因、owner 和下一 gate，不接受 S2 implementation，也不授权产品修改、S3、commit 或 aggregate。

## 2. Controller 独立复核

### 2.1 当前代码直接证据

真实调用链具有写 filesystem 的构造语义：

1. `dayu.service.host_assembly.assemble_effective_tool_provider_configs(...)` 通过 `_effective_fins_workspace_root_config_value(...)` 把调用方给出的 `workspace_root` 解析为 Fins provider 的绝对 effective config。
2. `discover_service_tools(...)` 执行真实 provider binding，不是 metadata-only schema parse。
3. Fins providers 调用 `DefaultFinsRuntime.create(workspace_root=...)`。
4. `DefaultFinsRuntime.create(...)` 构造 `build_fs_repository_set(...)` 和 `FsFinsIngestionJobStore.from_workspace_root(...)`。
5. `_FsRepositoryInfrastructure.__init__(..., create_directories=True)` 明确创建 `<root>/portfolio`、`<root>/.dayu/repo_batches`、backup/lock roots；`FsFinsIngestionJobStore.__post_init__` 创建 `<root>/.dayu/fins_ingestion/jobs`。

这证明副作用由真实 Service/Fins owner 产生，不是 init adapter、测试 fixture、日志或间接迹象。

### 2.2 真实 probe 磁盘证据

Agent 使用 fresh `workspace/tmp/r12-s2-probe-a`、package config 和非 secret Ollama 输入执行的完整链：

```text
staging ConfigLoader
-> assemble_effective_tool_provider_configs(workspace_root=<public workspace>)
-> discover_service_tools
-> SceneToolCatalog.from_tool_bundle
```

在 config publication 前真实创建：

- public `portfolio/`；
- public `.dayu/repo_batches`、`.dayu/repo_backups`、`.dayu/batch_locks`；
- public `.dayu/batch_recovery.lock`、`.dayu/fins_ingestion/jobs`。

Init 随后因 managed-root snapshot drift 安全失败，config 未 publish。Controller 核对上述路径当前确实存在于该 test-owned probe root。

### 2.3 回滚审计

Agent 在识别 stop condition 后完整撤回未完成实现：

- S1 四文件 hashes 与 final locks 精确一致；
- S2 四个 existing files hashes 与 entry locks 精确一致；
- `dayu/cli/init_workspace.py`、`tests/cli/test_init_workspace.py` 仍为 `ABSENT`；
- staged tree 为空，`git diff --check` 通过；
- retained Agent change 只有 stop-condition artifact。

## 3. Finding

### `R12-S2-IMPL-STOP-F01`（HIGH / plan defect）

状态：`ACCEPTED / REQUIRES PLAN CORRECTION BEFORE IMPLEMENTATION`。

Accepted plan §6.4 同时要求：

- 使用真实 Service discovery；
- 把 effective-provider assembly 的 root 指向 current public workspace；
- publication 前不改变 public managed roots；
- init 不创建/删除 `portfolio`，FIRST/PRESERVE/OVERWRITE 不创建/迁移 `.dayu`。

当前代码证据证明四项不能同时成立。继续原计划至少会要求以下一种越界补偿：修改 Service/Fins 为 metadata-only、把 portfolio 纳入 manifest、在 discovery 后删除 public Service/Fins 数据，或引入 synthetic provider/test shim；全部拒绝。

## 4. 最小 owner-correct correction

Plan 必须把 validation filesystem side effect 隔离到 transaction-owned private validation root：

1. staging `RuntimeConfig`、真实 effective-provider assembly/discovery、真实 `SceneToolCatalog.from_tool_bundle(...)` 和 13 个 production manifests 均保留；不降低验证真实性。
2. Assembly 的 `workspace_root` 改为当前 transaction private staging directory 内的专用 validation workspace root，不是用户 public workspace root，也不是 package/config root。
3. Fins discovery 产生的 private `.dayu` / `portfolio` 只属于本 transaction；必须由 transaction owner 用 identity-locked no-follow cleanup 处理。
4. Private validation root 在 config publication 前必须成功清理；cleanup/parent-fsync 失败属于 pre-publication failure，禁止 publish，且保留可定位 transaction-owned path 供诊断，不能清理 public paths。
5. 测试必须同时证明真实 Fins discovery 的 side effect 确实发生在 private root，并且 public `.dayu`、`portfolio`、`assets`、旧 config 在 validation/publish 前后遵守四态 contract。
6. 不修改 Service/Fins production，不引入 metadata-only 开关、synthetic provider、duplicate parser、fallback、compat 或 cleanup-after-public-side-effect 补偿。

这不是产品裁决变化：controller discussion 与 accepted plan 的稳定产品语义仍是 init 不拥有 public portfolio/assets，且 pre-publish validation 必须真实。修订只纠正 validation 的隔离位置和失败边界。

## 5. Gate 裁决

`STOP CONDITION ACCEPTED / PLAN CORRECTION REQUIRED / NO USER DECISION REQUIRED`

- design truth contradiction：`0`；冲突位于 R12 accepted plan 的 implementation seam，不在产品裁决或稳定设计真源。
- accepted/open plan finding：`1`（`R12-S2-IMPL-STOP-F01`）。
- local implementation blocker：`1`，直到 plan correction 经双路 review/re-review 关闭。
- S2 product implementation remains unauthorized。

下一入口：AgentCodex 只修改 `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` 并新增 `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-fix-codex.md`；随后 AgentMiMo/AgentDS 并发 complete plan review。不得修改 product/test/control/既有 artifacts，不得 stage/commit。
