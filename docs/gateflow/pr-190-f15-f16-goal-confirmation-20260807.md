# PR 190 F15 / F16 Goal Confirmation

## Preflight

- Branch: `codex/interactive-oracle`
- Worktree: clean
- HEAD: `97c049868e6f11115f56f4a66029cc8f66c1dd0c`
- Local `main` / `github/main`: `113ea34d47b95812d79aa31705949bbb46bc6061`，已 fast-forward 对齐
- HEAD 相对 `github/main`: ahead 95 / behind 0
- Merge / rebase / cherry-pick / revert state: none
- PR: 190，OPEN、draft、base `main`、head `codex/interactive-oracle`、merge state `CLEAN`、无 review request
- Git boundary: 只复用 PR 190；不新建 PR，不 merge、mark ready、approve/request reviewers、rebase、force-push 或删除分支。

## 直接证据与动机裁决

动机成立，并且必须把两个独立缺陷分开治理，不能回滚 F14：

1. 独立 fresh production rerun 的 harness SHA-256 为
   `1de6956e6d1888387ea8fd75f37b35eb76a36849552edb9859d77f982153397c`，observed report SHA-256 为
   `bc70bbfad98387b44b74aed69a0003e0be169e1f58034581da4cc0241f7fb133`。
2. 28 个 `RUN_ACCEPTED` 只有 8 个 `RUN_SUCCEEDED`，20 个以
   `runner_candidate_invalid` 进入 `RUN_FAILED`；interactive process 最终 exit 0，只有一次
   `CONTEXT_COMPACTED`。
3. debug traceback 的确定性链为
   `_previous_compacted_view_pair_from_replacement` ->
   `validate_previous_compacted_view_pair` ->
   `previous answer_anchors block text mismatch` ->
   `HostDurableError(previous compacted view pair is invalid)` ->
   `runner_candidate_invalid`。
4. accepted replacement 中合法的多段 `answer_anchor.detail` 被
   `run_input_material_block` / `normalized_material_text` 去除空行并折叠空白；paired readable view
   仍保留原始 detail，validator 又从原始 typed 字段渲染文本。因此这是合法输入稳定触发的 Host
   双投影缺陷，不是 provider 波动或 prompt 遵从性问题。
5. 当前 observation harness 的 PTY trigger 只等待 terminal 总数，scenario row 的
   `execution_outcome` 只由 process exit / timeout 产生；REPL 按产品设计在单 Run 失败后继续，故 process
   success 被错误当成 required ordinary Runs success，并继续执行依赖链。

F14 的 accepted coverage frontier 仍由 accepted chain 累积的
`compacted_source_refs` 派生；本次证据没有否定该修复。F15/F16 不修改该 frontier，不把 terminal
sequence 重新引入 coverage 判断。

## 唯一语义 owner 与不变量

### F15

- Accepted compact replacement 的 durable truth owner 是 Host canonical
  `CONTEXT_COMPACTED` strict typed accepted replacement。
- `dayu.host.compact_material` 是该 replacement 到 previous compacted material pair 的 Host
  projection owner；`normalized_material_text` / `run_input_material_block` 已是 ordinary / compact
  material 可读文本的 canonical normalization boundary。
- `PreviousCompactReadableView` 与 packed `CompactMaterialBlock` 是同一 accepted atom 的两个同步投影，
  不是两个可独立清洗的 source。pair validator 只验证 owner 产出的 exact pair，不重新发明 normalization
  或放宽比较。
- 修复必须在 pair 构造 owner 内先形成一次 canonical answer-anchor projection，再由该 projection同时产生
  packed block 与 readable view；空行、首尾空白、重复空白、多段 Markdown、列表和表格均属于合法文本。
- durable reload、reconnect、recovery transform 与下一 ordinary Run 必须继续消费同一 pair；不得从 block
  字符串逆向解析 typed view，不得通过 prompt、下游 fallback、loose comparison、heuristic 或忽略 validator
  补偿。

### F16

- 单个 Run 的 canonical terminal type / reason owner 是 Host EventLog 与共享 lifecycle terminal contract；
  `RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED` 必须逐 Run 记录，`RUN_LOST` 只能按其既有非 public / lost
  语义单独处理，不能伪装为 success。
- CLI process exit / signal / timeout owner 是 OS process observation。interactive process exit 0 只表示 REPL
  正常退出，不能覆盖其内部任一 Run terminal。
- CLI CI harness/evidence index 是上述两类事实的只读 projection owner：process outcome 与 per-Run terminal
  records 必须分字段保存；required ordinary Run 的非 succeeded terminal 使该依赖链不具备 scenario-success
  证据，并停止或隔离依赖该成功结果的后续步骤。独立 mandatory observation 仍可继续，不能把业务回答
  oracle 硬编码进 harness。
- `docs/cli_ci.md` 是后续 init/prompt/interactive observation 的复用 handbook truth；需要补足 per-Run terminal
  与 dependent-chain stop gate，但不建立第二套产品 verdict。

## 目标

1. 根治 F15：同一 accepted answer anchor 的 packed block/readable view exact 同源，合法格式在 reload、reconnect
   和 ordinary dispatch 全链成立。
2. 根治 F16：通用 observation 边界逐 Run 投影 canonical terminal type/reason，并与 process outcome 分离；
   required ordinary Run 失败时不得输出 scenario success或继续伪装依赖验证已完成。
3. 保持 F14 cumulative accepted-consumption frontier、turn-group atomicity、canonical order、exact-once 与五类
   projection 同源 contract 不变。
4. 用 fresh production interactive POSIX PTY、真实 provider、production 财报工具和真实 AAPL corpus完成至少一份
   post-fix observation；formal scenarios 保持 `unadjudicated`，交 Oracle 总控裁决。

## 非目标

- 不修改 compactor prompt、provider/model、财报工具、recent floor/cap、accepted oracle 或 scenario predicate。
- 不改变 REPL 单 Run 失败后继续运行的产品语义；修复的是 observation classification 与依赖链 gate。
- 不增加 schema alias、兼容读取、双 cursor、第二 source truth、loose parsing 或 UI/Service fallback。
- 不由 harness 判断 FY2025/FY2024/21.7% 的业务正确性；这些仍由 accepted contract、真实 evidence 和用户/Oracle
  裁决。

## Schema / public contract 裁决

当前直接证据不要求修改 Host durable schema、Engine contract、CLI public surface 或 compactor LLM-facing schema。
F15 是 Host internal projection owner 修复；F16 是 tracked reusable observation helper / evidence index 与 handbook
contract 修复。若 plan/implementation 发现必须扩大上述 public contract，立即停止并回到 Goal Confirmation，不自行扩域。

## Gate 进入条件

正确 owner 清楚、scope 无冲突、无需 public contract 扩大。用户已明确授权按 Gateflow 完成全部 gates，因此本
Goal Confirmation 直接进入 plan；AgentController 保留语义裁决、gate order、证据审计和 final closeout 总控。
