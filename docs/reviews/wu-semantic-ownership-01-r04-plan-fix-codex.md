# WU-SEMANTIC-OWNERSHIP-01 R04 plan fix — AgentCodex

## 1. Gate 与范围

- gate：既有 umbrella WU 的 R04 plan fix；不是新 WU，不授权 implementation。
- target：`docs/host/wu-semantic-ownership-01-r04-awaiting-provider-resolution-composition-plan.md`。
- changed files：上述 plan 与本 fix artifact；control、reviewer artifacts、代码、测试、README、design 均未修改。
- Controller dispositions：保留 `R04-PLAN-F01..F04` closure，并追加处理 `R04-PLAN-CV-F05`；全部 rejected/no-fix/observation 裁决保持不变，不增加 source-scan 例外，不修改 Host API/open_host，不重开 12 个 packaged 数值裁决。

## 2. Finding closure

| Finding | Before | After | Evidence | 状态 |
|---|---|---|---|---|
| `R04-PLAN-F01` | “删除 tool-name 推断”可能误删结构映射，且 `_binding_for_tool_name` 的 `POLL` 硬编码未明确归属 | S1 明确由 typed `AwaitingResolutionMode` 映射 `POLL/CALLBACK/MANUAL`，替换硬编码；明确保留 `_operation_kind_from_tool_name` | 当前 `_binding_for_tool_name` 固定返回 `WaitResumePolicy.POLL`；`_operation_kind_from_tool_name` 被 snapshot/activation handle 恢复调用 | 已修复 |
| `R04-PLAN-F02` | 原 S2 删除 override、原 S3 才替换 `_compose_options`，形成 broken slice | 首轮先合并原 S2/S3；本轮再按 F05 将该闭环与原 S1 合并为唯一原子 S1，JSON/config、Host defaults、override/helper 删除与 typed composition 始终同时完成 | `ServiceAssemblyOverrides.wait_poller_policy` 与 `_compose_options` 消费点同在 `host_assembly.py`；scene helper 还无参构造 Host policy | 已修复 |
| `R04-PLAN-F03` | disabled 与 non-awaiting mode 校验 owner/时序不明确 | Service 在 active filtering 前用现有 identity 路由当前三个 Fins awaiting providers 到 Fins parser；recognized non-awaiting 只做字段存在 misuse check；明确 typed metadata 准入顺序与三类 tests | 当前 registry input loop 先跳过 disabled；generic provider config 是 opaque mapping；现有 Service 已持有 Fins awaiting/read/web identities | 已修复 |
| `R04-PLAN-F04` | 旧 override/scene/Host/provider tests 缺少迁移分类 | 增加删除/重写/保留分类；要求 §6.3 每行都有 typed owner、registry、policy projection 或 pre-open error 断言 | 现有测试直接构造 override、单测 scene helper，并已有 Host fail-closed cases | 已修复 |
| `R04-PLAN-CV-F05` | 两-slice 计划在 S1 暴露 manual/callback typed contract，但旧 scene-derived poller authority 到 S2 才删除，形成错误过渡语义 | 当前 S1/S2 合并为唯一原子 S1；mode、policy、Host default/fallback 删除、override/scene 删除、typed composition、tests/README/scans/smoke 同时完成，禁止中间 commit/checkpoint 或 seam | `with_entrypoint_wait_poller_policy -> _scene_selects_fins_awaiting_tools` 不消费 typed mode；manual 会被错误启用 poller，callback 可能走错 missing-registry failure | 已修复 |

## 3. Residual risks

| Risk | Classification / owner |
|---|---|
| authenticated callback transport 尚不存在 | `assigned to later work unit`：WU-WAIT-01 / Issue #89；R04 继续 fail-closed |
| fresh `host_runtime.json` schema 不兼容旧 workspace | 预期 fresh-schema 行为；R04 禁止兼容读取，无额外实施项 |
| NumPy multi-module coverage double-load | 已由既有等价验证处置：单一 `--cov=dayu` session 后逐文件读取 JSON |

没有 unclassified residual risk。下一 gate 为 Controller re-validation，随后双路完整 plan re-review；本 artifact 不接受计划。

## 4. Validation

- plan 共 212 行，artifact 加入本节后仍小于 120 行。
- `git diff --check` 通过；对两个 untracked target 的独立 `--no-index --check` 均无 whitespace error 输出。
- 最终 status 路径集合与本轮 preflight 一致；只在既有 untracked plan 与同一个 fix artifact 内继续编辑，未新增或修改其他路径。
- `git diff --name-only f7006a80 --` 仍只列本轮前已存在的 tracked control/R03 文档差异；Controller validation、review artifacts、代码、测试、README 与 design 未修改。
- Controller re-validation 文本纠正：plan §3 的 composition baseline 交叉引用由 §5 修正为实际 matrix 所在的 §6.3；无其他内容变更。
