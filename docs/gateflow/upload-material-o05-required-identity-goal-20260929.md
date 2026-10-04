# UM-O05-F01：material form/name 无条件必填的前置契约

- Gate：`goal confirmation pass`；work unit：`UM-O05-F01`；workspace：`/private/tmp/dayu-upload-o05`；branch：`codex/upload-material-o05`；baseline：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 授权：主工作区 `docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md` 登记用户接受此裁决；用户随后授权按 Gateflow 修复完整清单，并将闭环代码纳入现有 draft PR #197，自己手工 merge。

## 动机和直接证据

动机成立，严重性是错误的生命周期语义和迟到的输入错误，不是错误材料已发布。冻结 UM-031/033/034 的缺失/空 name 或 form 案例先显示 `upload.started`，再失败，无 document publication。当前 HEAD 的 `FinsUploadMaterialRequest.form_type/material_name` 都为 `str | None`，CLI `_upload_material_stream` 将缺失参数变成 `None`；`_normalize_upload_request` 仅处理 ticker/action/source kind。`FinsIngestionRuntime.upload/start_upload` 都在创建事件流/job 前调用 `_validate_runtime_upload_request`，而 material 分支只转到该不足的 normalization；真正的 `build_material_ids` 很晚才拒绝空字段。Tool 入口当前 `_required_text`，但这只是单个消费入口的校验，不能成为共同业务真源。

## 目标、成功信号和边界

目标是在 Fins material request 的共同 admission owner 将 `form_type` 和 `material_name` 作为所有 action 的无条件业务必填字段；缺失、空串、只有空白的输入都在 upload lifecycle/job record/业务发布之前得到可行动的 typed usage 拒绝。direct CLI、job、tool/Service 等入口复用同一规则；CLI 不再先输出 `upload.started`。合法输入保持原有处理和 material ID 稳定语义。受影响测试、真实 CLI 缺失/空白与有效对照、pyright、单文件覆盖率及 README 职责检查共同验证。

非目标：不改变 material 名称长度上限（O06）、form canonical（O09）、action/files（O16）、目标状态或 schema；不让 CLI argparse 或 tool schema 重复实现业务校验；不把冻结无发布结果说成已发布错误。若当前 request 类型改成非可选会迫使所有调用点的类型和使用方式改变，plan 应依据调用图选择最小、清晰的 admission contract，不以兼容 wrapper 掩盖分歧。O16 与本项触及同一 admission owner，独立 worktree 串行集成到 PR；后集成者必须复核前者 HEAD 并解决同源合并，不能形成两套 helper。

## 停止条件及下一 gate

若代码证明 form/name 对任一已授权 action 合法可省略，或唯一 admission owner 不能覆盖公开入口，停止 implementation，提出直接证据重新裁定；若 typed usage projection 需要新增公开 schema，也先停下重拟目标。此 goal 基于用户既有明确裁决确认通过；当前/下一 gate 为 gpt-6-sol 编写可直接实施的 plan，随后 Kimi/MiMo 并行 plan review。不得越过 review gate。
