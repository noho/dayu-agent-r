# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 stop-condition plan fix

## 1. Gate 身份与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 cumulative S2 的 plan-only correction，不是新 WU。
- Finding：accepted HIGH `R12-S2-IMPL-STOP-F01`。
- 结论：`PLAN-FIX SELF-CHECK PASS / READY_FOR_CONTROLLER VALIDATION / IMPLEMENTATION UNAUTHORIZED`。
- 本轮只修改 `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，并只新增本 artifact；未修改 product/test/control/既有 artifact，未进入 S2 implementation、S3、aggregate、stage、commit、push 或 PR。

## 2. Authority 与 before/after plan identity

完整读取并据此修订：

| Authority | SHA-256 |
|---|---|
| 更新后的 `docs/reviews/wu-semantic-ownership-01-r12-s2-controller-authorization.md` | `259abecca9fb36112013dcc3be72320d9fe824604ca39eeddb44936f779c2f86` |
| `docs/reviews/wu-semantic-ownership-01-r12-s2-implementation-codex.md` | `b123dff616a0c4ac22bb3d1f47b00fe5913a9747e9f3e413ff34462ddbd82fcd` |
| `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-controller-adjudication.md` | `f2bb4029d83716e5e2a18e16fe1ac8c7970db7396adf54e951d9378ae4e3785c` |

Plan identity：

| 状态 | 行数 | 字节数 | SHA-256 |
|---|---:|---:|---|
| before accepted plan | 608 | 71,044 | `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2` |
| after corrected plan | 634 | 81,713 | `1f4df5f942a49a5c95bd60f75d0ef3e8a3cbfacede2c2d8f7ecf3c42a1436715` |

Plan tracked diff：`51 insertions / 25 deletions`。完整 after hash 在 plan 关闭后机械计算；未写回 plan 形成 self-reference。

## 3. 动机、root cause 与 owner 判定

动机成立，严重程度 HIGH 正确。真实代码链把调用方提供的 `workspace_root` 注入 Fins effective provider config，随后真实 discovery 构造 Fins runtime 并在该 root 创建 `.dayu` / `portfolio`。原 accepted plan 又把该参数指定为 public workspace，因而在 config publication 前改变 public filesystem truth；这与 public portfolio/assets 非 init-owned、managed-root snapshot 和 pre-publication failure boundary 直接冲突。

最小且 owner-correct 的修复不是修改 Service/Fins，也不是让 init 删除 public side effect，而是：

- Service/Fins 继续拥有真实 provider binding 与 private root 内的 runtime layout/content；
- `init_workspace.py` transaction owner 拥有 dedicated validation container 的 identity、containment、no-follow cleanup 与 durability；
- assembly 只消费该 transaction-private root；public `.dayu` / `portfolio` / `assets` 不成为验证输入或 cleanup target；
- validation cleanup/parent-fsync 是 pre-publication gate，post-publication backup cleanup 仍是另一条 warning boundary。

该方案不改变产品裁决、四态、managed-root manifest、S3 或分层方向，也没有引入 callback/factory、第二套 parser/provider 或 Service/Fins 配置开关。

## 4. `R12-S2-IMPL-STOP-F01` 逐处 closure

| Plan 位置 | Before defect | After closure |
|---|---|---|
| §1.1 / §1.2 | 完成信号未表达真实 discovery side-effect isolation | 明确 transaction-private validation workspace，并锁定 validation/cleanup 前后 public `.dayu`、`portfolio`、`assets`、旧 `config` byte/identity 不变 |
| §3 | transaction container 与 Fins runtime content 的 owner 未拆开 | `init_workspace.py` 唯一拥有 private container identity/cleanup/durability；Service/Fins 保持 runtime layout/content owner |
| §6.1 | “init 不创建/删除 portfolio”未区分 public 与 private validation side effect | public portfolio/assets 继续不在 manifest且不可触碰；private `.dayu`/`portfolio` 只随 transaction-owned container 在 publication 前清理 |
| §6.3 | staging/backup 有 containment，但没有 dedicated validation root identity/cleanup contract | validation root 固定在 transaction private staging 内，非 public/package/config/backup；传入 assembly 前记录 identity，cleanup 时重新核验 containment/type/symlink |
| §6.4 validate | assembly root 错误指向 `<current workspace>` | 改为 `<transaction private staging/validation-workspace>`；保留 staging `RuntimeConfig`、真实 effective assembly/discovery、`SceneToolCatalog.from_tool_bundle`、13 production manifests、两个 required slots与 3 个 test-owned manual-smoke boundary |
| §6.4 cleanup/fault | validation side effect 没有独立 pre-publication cleanup durability gate | 13 manifests 通过后 identity-locked/no-follow 删除 private validation tree并 fsync private parent；identity/delete/fsync fault abort publication并保留可定位 private staging path |
| §6.4 publication | validation cleanup 与 post-publication backup cleanup 容易共用 warning 语义 | publication success boundary 现在显式以前者 cleanup/fsync 成功为前置；前者失败，后者 warning，禁止互换 |
| §8 S2 order/assertions | 只断言真实 catalog，未证明真实 Fins side effect 隔离与 cleanup fault | 顺序加入 private validation cleanup/fsync；测试必须观察 private `.dayu`/`portfolio`、验证 public byte/identity、覆盖 identity/delete/fsync fault，并保持 RESET 对 public `.dayu` 的既定四态语义 |
| §8 S2 verification/review | 没有机械证明 Service/Fins/package manifest 零改动 | 增加 tracked + untracked exact-status gate；review 明确拒绝 synthetic/fake provider、metadata-only discovery、duplicate parser、test shim |
| §9.2 scans | `portfolio` 与 assembly scan 解释会把新真实验证误判，且缺少正/负链路扫描 | 区分 public/private portfolio；增加真实 Service chain positive scan、synthetic/metadata-only/test-shim negative scan及 Service/Fins/models/manifests exact-diff/status scan |
| §10.1 / §10.2 | 残余与 stop condition 仍基于 public-root contradiction | 改为 private side effect 的 fail-closed containment/cleanup 风险；side effect 逃逸、cleanup 无法 fsync、需要 Service/Fins 改动或 public cleanup 均立即停止 |
| §10.3 / §11 | 最小性与 completion evidence 未包含 corrected seam | 明确只改变既有 assembly 显式 root 参数；implementation report 必须记录真实 side effect isolation、cleanup fault、public identities和零生产改动证据 |
| §15 | 无本 stop-condition correction provenance | 记录 before hash、authority、retained scope、禁止实现与 Controller validation 下一入口 |

## 5. Retained decisions 与 adversarial checks

- `FIRST / PRESERVE / OVERWRITE / RESET` 与 `RESET > OVERWRITE` 未改；特别保留 RESET publication 后移除 public `.dayu`，只要求它在 validation/private cleanup 期间不变。
- staging `RuntimeConfig`、真实 Service effective-provider assembly/discovery、`SceneToolCatalog.from_tool_bundle`、13 production manifests、两个 required slots全部保留；三个 manual-smoke manifests 仍仅使用 exact test-owned fixture。
- public managed-root manifest 仍精确是 `.dayu` / `config`；public `portfolio` / `assets` 没有加入 manifest，也没有 cleanup fallback。
- S1、S3、prewarm、Windows/POSIX smoke、README、产品裁决、deferred issues 与统一 authorization scope 均未改变。
- architecture / best-practice / optimal-solution / overengineering / overcoupling lenses 未发现剩余 material finding：方案复用现有显式 `workspace_root` seam 与 transaction owner，不修改下游 producer，不增加通用 sandbox/runtime abstraction，也不把 Service/Fins 生命周期耦合进 public workspace。

## 6. Scope、diff 与 staged 记录

Entry 时已有且不属于本 gate 的 dirty state 包括：`docs/host/issues-implementation-control.md` 的既有 tracked 修改、S1 四个 product/test untracked paths及既有 S1/S2 review artifacts。它们均被保留，本轮未编辑。

本 gate 相对 entry status 的唯一 delta：

| 路径 | 状态 | 本轮作用 |
|---|---|---|
| `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` | modified | 关闭 `R12-S2-IMPL-STOP-F01` 的 plan defect |
| `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-fix-codex.md` | added | 本 closure / handoff artifact |

机械检查记录：

- `git diff --check`：PASS，无 whitespace error。
- corrected plan `git diff --numstat`：`51 25`。
- corrected plan no-index whitespace check：PASS；exit `1` 只表示相对 `/dev/null` 存在预期整文件 diff，stdout 无 whitespace diagnostic。
- 本 artifact no-index whitespace check：PASS；作为新增文件，no-index exit `1` 只表示存在预期 diff，stdout 无 whitespace diagnostic。
- entry 已有 S1 四个 untracked product/test paths 重新计算后仍精确匹配 updated authorization locks：`dayu/cli/init_catalog.py=937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754`、`dayu/cli/init_environment.py=71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f`、`tests/cli/test_init_catalog.py=086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f`、`tests/cli/test_init_environment.py=820c2bf262dd77628201977e7d4f823265e141ac0ae6a28791bd7d12cf5ad01a`；本 gate 没有产品/测试内容漂移。
- `git diff --cached --name-only`：empty；未 stage。
- 未运行 pytest、coverage、pyright、Ruff 或 smoke：本 gate 明确是 plan-only correction，运行 implementation profile不能验证文本修订，且会越过 Controller 指定的停止点。

## 7. Residual 与下一入口

- Open finding：`0`（AgentCodex plan-fix self-check）；最终 acceptance 仍归 Controller 与后续双路 complete plan review。
- Product residual：无新增；真实 Service/Fins side effect 本身是 retained production behavior，不是待改产品缺陷。
- Implementation residual：S2 仍未实现；private root identity/no-follow cleanup、parent fsync及 fault injection 只形成 code-generation-ready plan contract，不能宣称已有运行证据。
- 下一入口：`Controller R12 S2 stop-condition corrected-plan validation`。
- 当前禁止 implementation、双路 review/re-review、S3、aggregate、stage、commit、push 或 PR；后续 gate 只能由 Controller 授权。
