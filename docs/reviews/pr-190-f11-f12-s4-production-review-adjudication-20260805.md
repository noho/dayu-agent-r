# PR 190 F11/F12 S4.1 Production Review 裁决

## Scope

- Base: `c824ea9038ecb4084621117c6806764cd63e9a20`
- Inputs:
  - `docs/reviews/code-review-20260805-215757.md`
  - `docs/reviews/pr-190-f11-f12-s4-production-mimo-review-20260805.md`
  - `docs/reviews/pr-190-f11-f12-s4-production-ds-review-20260805.md`
  - `docs/reviews/pr-190-f11-f12-s4-production-fix-20260805.md`
- Owner under review: fallback selection/replay current-input material construction and EventLog-backed material reconstruction.

## Finding 裁决

| Finding | 裁决 | 依据与动作 |
|---|---|---|
| MiMo `001` / DS `1`：跨模块导入私有 helper | 接受（中） | correctness 已恢复，但 `compact_pipeline` 直接依赖 `context_fallback` 私有函数违反模块封装。修复必须继续复用 `compact_material.run_input_material_block` 的 normalization/size/digest owner，同时消除跨模块私有依赖；不得为此扩张 package/public export。首选两个 producer 直接调用现有公开 owner，并用 owner test 锁定 fallback block id/section/kind/text/size/digest 等价。 |
| MiMo `002`：proactive 与 reactive 来源不同 | 不成立 | selection 使用冻结 `CompactPipelineSourceSnapshot`，durable replay 必须从 canonical EventLog 重新读取；来源阶段不同是生命周期要求，不是第二语义 owner。两路已经通过同一 EventLog material view 与 `run_input_material_block` contract 收敛，并由 exact digest/source/id 校验约束。 |
| MiMo `003`：deterministic test 使用 rejecting compactor | 不成立 | 此测试验证 Host exhausted-fallback 状态机与 material replay，受控 compactor 是 owner-level deterministic input，不承担真实 provider conformance。真实 provider 必须在后续 fresh evidence root 单独验证，二者不能互相替代。 |
| S4-001 proactive raw/normalized digest | 已修复，待 fix re-review | red proof 与当前 owner tests直接证明 selection/replay digest 同源、两次 rejected、唯一 failed terminal、fallback dispatch/manifest/cleanup。 |
| S4-001 reactive protected-recent block identity | 已修复，待 fix re-review | valid reactive durable load 现在重建 EventLog-backed material blocks，测试直接证明 protected recent id/order/content、digest、recovery Attempt 与 Run cleanup。 |
| `ActiveRecentWindowFallback.material_blocks` docstring | 接受（低，controller 补充） | docstring 仍写“仅 proactive ... 填充”，与当前 proactive/reactive valid durable loader 均填充的事实冲突；只更新 owner docstring，不改类型或 schema。 |
| RunInput `material_blocks is None` legacy consumer branches | 接受为分类 residual，不在本 slice 扩张 | 当前 production durable loader 对 valid proactive/reactive trigger 均返回 non-None blocks；`None` 分支主要服务注入式 contract/tests，未构成本次真实失败路径。其长期 owner 是 RunInput/ContextFallback contract；本 slice不将其机械改成必填，以免扩大接口迁移。Aggregate deepreview 若找到真实 production 可达反例，再升级为 blocking finding。 |

## Fix acceptance

1. 消除 `compact_pipeline -> context_fallback` 私有 helper import，不新增 compatibility wrapper、re-export 或新 public surface。
2. selection 与 replay 都继续直接委托 `compact_material.run_input_material_block`；不得恢复 raw digest 手工构造。
3. owner test 对两条路径的 fallback current-input block construction 等价作直接断言，避免未来 block id/section/kind 漂移。
4. 修正 `ActiveRecentWindowFallback.material_blocks` docstring。
5. 重跑两条回归、受影响 Host tests、全量 Host tests、全仓 pyright、coverage 与 `git diff --check`。

## Gate 状态

`ACCEPTED`。

- AgentMiMo re-review：`docs/reviews/pr-190-f11-f12-s4-production-mimo-rereview-20260805.md`，PASS，无新增 finding。
- AgentDS re-review：`docs/reviews/pr-190-f11-f12-s4-production-ds-rereview-20260805.md`，PASS，无新增 finding。
- 私有 helper import 与过期 docstring 已关闭；MiMo `002/003` 保持不成立；RunInput `None` 分支保持已分类 residual。
- 定向 owner tests 3 passed；受影响 Host tests 409 passed、1 skipped；全量 Host tests 2423 passed、1 skipped、6 deselected；coverage `compact_pipeline.py=90%`、`context_fallback.py=87%`；全仓 pyright 0 errors；`git diff --check` 通过。
- 下一入口：S4.1 accepted commit/push，然后从新的 immutable evidence root 重跑 S4 mandatory real-provider observation。
