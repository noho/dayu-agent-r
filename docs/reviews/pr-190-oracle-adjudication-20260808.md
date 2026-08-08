# PR 190 init / prompt / interactive Oracle 裁决与剩余闭环

## 身份

- Branch：`codex/interactive-oracle`
- F17 final target：`857f9e8d1e16b578aebd3a7205bbbabd0859809e`
- F18 B1 evidence target：`ce0c171a022a073c6355ace44e7c5e34a668d4bb`
- PR：190
- 裁决日期：2026-08-08
- 裁决 owner：用户 / Oracle controller

## 本轮裁决

### F15 canonical renderer

裁决为通过。Host accepted answer-anchor 到 packed block、readable view 与 strict validator 共用同一 canonical
normalization truth。Owner tests 覆盖前后空白、重复空白、多行 Markdown、列表、表格及 detail 内部空行；fresh 真实 MiMo
运行覆盖多行 Markdown、列表和表格，但未把模型未实际产生的内部空行伪称为真实 provider 覆盖。

### F16 Run observation contract

裁决为通过。PTY process outcome、canonical Run terminal、dependency gate 与 evidence integrity 分开记录；fresh observation
共有 7 个进程 exit 0、28 个 accepted Run、28 个 `RUN_SUCCEEDED`，没有用进程 exit code 代替 Host terminal。

### `interactive.interactive.g06.rolling-correction-replacement@1`

裁决为 `accepted`。Fresh evidence：

- Root：`/Users/leo/workspace/.dayu-cli-ci/f15-f16-postfix-rerun-vNMkeVul`
- Human report SHA-256：`cbac55f151ec3091dbe7fd7872353d1ba21b7adf609393b82a3b90e88cd4b702`
- Execution index SHA-256：`426acb373aa4ea0bb12232bcf987e0c23b31b4651bc8bfa56564225b585692d6`
- Context observation SHA-256：`a9a1f68107c7e29f84499290149b58a2670b6d3bb5aa9a8f005c230afb646383`
- Secret scan SHA-256：`617a1be3c5155bf1e518fc3573ab7e897d0bd3af000cf7e43c13a08c3ac1ccec`

接受的行为是：真实 FY2025 evidence 将 current 口径从 FY2024 修正为 FY2025；FY2024 可以作为带原 provenance 的历史事实
保留；无工具证据的 21.7% 不得升级为 EvidenceFact。Accepted coverage frontier 只由
`compacted_source_refs` 累积派生，不能用 compact terminal sequence 反推；受 recent window 保护而尚未消费的完整 Run
材料离开保护窗口后重新进入后续 boundary。Artifact、EventLog、Memory、RunInput、Tool Trace 与跨进程 reconnect 同源。

## 后续问题与 F18 B1 裁决

### Tool Trace Analyzer 信噪比

真实报告中的 11 条 `host.duplicate_governance` info 全部是首次普通治理评估的 `allow`，没有 prior refs，不代表 11 次
重复调用。当前 Analyzer 把“执行了 duplicate governance evaluation”与“实际命中 prior duplicate fact”混成同一 finding。

- 原 Issue 70 已 completed/closed，不把未完成修复埋入关闭 Issue comment。
- Follow-up：GitHub Issue 192。
- Fins Tool 长期 trace-driven schema 优化：GitHub Issue 191。

### `interactive.interactive.g06.tool-trace-formal@2`

裁决为 `accepted`。Immutable bundle `pr190-formal-g1a2xu` 在 fresh production CLI、真实 MiMo 与真实
AAPL corpus 上形成 10 个 accepted 且 typed `RUN_SUCCEEDED` 的 Run。public Host Tool Trace resolver/analysis
response identity 与 canonical terminal 的 terminal sequence、operation id、attempt number、proposal manifest ref、
proposal manifest digest 与 successful response identity 六字段完成 6/6 exact match；secret/path scan 零命中。

- Human report：`evidence/public/observed-behavior-report.md`，SHA-256
  `de7ee64de11140add816facf9926c2cf17aa13a4176bd873bc0f91ed20b70f79`；
- B1 summary：`evidence/public/observation-summary.json#b1`，文件 SHA-256
  `dfe3604bba8c7f8bda6b0d8a80639a87ac77a2d1c03f0e7baa28236e554d7c0a`；
- cold public analysis JSON/Markdown SHA-256：
  `f1b162c185c977bdb24882cdc7b1eb8d273defe02cfa1dbf920248d07754ec3a` /
  `2bba07d27ec3307a44cc0d6531c73cb7565bcd72eea7304c7f56d1e0961c41da`；
- public digest / secret scan SHA-256：
  `567d5539d9e745e78379093117275231c7b96ab5ac03536f13aec9475e476153` /
  `6f33e30ced5dbbcc96c6cadcc93bf1c5c2ad3d261c5f3386ccbec74c3ba52ba8`。

Raw PTY owner 记录 `execution_outcome=error`、`exit_codes=[1]`；它与 canonical 10 Runs succeeded、evidence
sufficient、gap none 和 accepted Oracle 正交，不用业务成功改写 process outcome。cold analyzer
`compactor_responses=0` 与 provider-native request id unavailable 继续保留为 limitation/residual question，不是
该 scenario 的 mandatory readiness gap，也不在 F18 扩展 analyzer。

## 仍待补跑或裁决

### `interactive.interactive.g06.cap-constrained-memory-replacement@1`

保持 `unadjudicated`。旧 evidence 来自被后续 schema/owner 修复取代的实现，不能直接升级为当前 Oracle。必须在全部相关修复
完成后的最终 HEAD 上 fresh 运行真实 provider 场景，覆盖 initial caps、machine-detectable invalid candidate、bounded whole-candidate
repair、repair exhaustion/fallback、accepted durable truth、Memory/RunInput/Tool Trace/reconnect 同源，再交用户逐项裁决。

## 执行顺序

1. F18 Slice 1 把已有 B1 用户裁决投影到 registry/handbook；Issue 192 继续作为独立后续，不是 B1 mandatory gap。
2. 只在 accepted F18 plan 的 fresh fixed-profile 约束下观察 `cap-constrained-memory-replacement@1`，不复用 B1 bundle或旧 Trial state。
3. 产出 B2 逐项 observed-behavior report 与公开 evidence，交用户单独裁决；Agent 不替用户把 B2 标为 accepted。
4. B2 裁决后重新生成 init/prompt/interactive readiness proof；在此之前 registry 保持 `calibration`。

## 当前 readiness

- init Oracle/scenarios：既有 accepted 集合保留；F17 publication digest 已修复。
- prompt Oracle/scenarios：既有 accepted 集合保留。
- interactive：`rolling-correction-replacement@1` 与 `tool-trace-formal@2` accepted；
  `cap-constrained-memory-replacement@1` pending。
- 总体：尚不能宣称 init/prompt/interactive 已具备无条件第二轮 CI readiness。
