# WU-CLI-CONFORMANCE-F01-F07 — S8 Code/Evidence Review Controller Adjudication

## Scope

- Base: `cd6344c0`
- Reviewed implementation target: `9fec164715bc6af7a4a7d7446cb45d49593ec64f`
- Reviewed S8 files: `README.md`, `dayu/config/README.md`, `dayu/host/README.md`,
  `tests/README.md`, `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md`
- Immutable evidence bundle:
  `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T022326Z-9fec164715bc/bundle`
- Bundle digest:
  `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`
- Review inputs:
  - `docs/reviews/wu-cli-conformance-f01-f07-s8-code-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s8-code-review-ds.md`

## Controller 独立复核

Controller 独立执行并确认：`sha256sum -c SHA256SUMS` 全部通过；
`sha256sum SHA256SUMS` 与 `bundle-digest.txt` 都等于上述 digest；最终 secret scan
为 442 files / 0 findings；Python mode-bit 扫描 bundle root、目录和文件均无 writable
path；frozen oracle、scenario 与 handbook hash 精确保持为：

- oracle: `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
- scenario: `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
- handbook: `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82`

## Finding-by-finding adjudication

MiMo 报告“未发现实质性问题”，但提出两个 residual observations。DeepSeek 把检查项
展开为 15 项 PASS。Controller 不以两路结论一致代替证据，逐项裁决如下。

| ID | Reviewer item | Controller direct evidence | Adjudication |
|---|---|---|---|
| D01 | F01 全局 `--config` 删除 | `f01-matrix.json`：81 parser actions 无 config；四份 help 0 命中；七个前/后置 argv 均 exit 2；active source scan 0 | 接受 PASS |
| D02 | F02 显式无效 editor | 三条真实 lane 的 Run/Attempt/Tool Trace 都为 0，draft occurrence 至少 1，进程 exit 0 且 terminal restored | 接受 PASS |
| D03 | F03 ESC sequence disambiguation | prompt/interactive CSI、Alt+X same/cross chunk、bracketed paste 全部 `conforms=true`；standalone ESC 单独走 ambiguity closeout | 接受 PASS |
| D04 | F03 pre-accept Escape | 0/10/20ms 三条真实 lane 均跨 acceptance barrier 形成 canonical cancel，回到 REPL 后 exit 0 | 接受 PASS |
| D05 | F03 double Ctrl+C | provider wait/tool-await/closeout 三 lane 均只有一个 `CANCEL_REQUESTED`、一个 `RUN_CANCELLED`，self-exit 130 且 terminal restored | 接受 PASS；见 C01 边界说明 |
| D06 | F04 READ_ONLY fresh attach | 真实双 attachment timeline：B 两次 rejection 时 Run=0 且存活；A 退出后 B fresh attach；最终 Session 恰好两个 succeeded Runs | 接受 PASS；review 中“两个 request id 不同证明 fresh attach”的表述本身证据不足，但不影响结论，见 C02 |
| D07 | F05 effective tool set | Host effective schema 有 download/list/read，无 `start_fins_preprocess` | 接受 PASS |
| D08 | F05 真实工具链 | 真实 Mimo 三个 succeeded Runs，canonical Tool Trace 和 165 个财报生成物共同证明 download/list/read/sections 路径 | 接受 PASS |
| D09 | F06 trigger rename | 三个 success terminal 与一个 failure terminal 后的 manifest 都是 `context_governance_resolved`，exact outcome 仍由各自 canonical terminal 拥有 | 接受 PASS |
| D10 | F07 strict v2 accept/repair | typed v2 contract、strict boundary、accepted truth、repair feedback 与真实 attempt 2 accepted/attempts exhausted 证据同源 | 接受 PASS |
| D11 | F07 post-compact continuity | 三个真实 follow-up 分别证明旧 AAPL fact、新 scope 与真实 list/get/read 工具结果 | 接受 PASS |
| D12 | F07 deterministic owner matrix | accepted 15-file matrix 串行复验为 711 passed / 1 skipped；完整 suite 6603 passed；首次并发唯一 0.01s lane timeout 单测与串行矩阵均通过，无稳定产品复现 | 接受 PASS；保留 CI timing residual |
| D13 | Bundle integrity/secret | checksum、digest、0 finding scan、443 index entries 与 0 writable paths 已由 Controller 独立复核 | 接受 PASS |
| D14 | Frozen inputs | 三个 frozen hash 与 pre-S8 baseline 精确一致 | 接受 PASS |
| D15 | README accuracy | 四份 README 的 diff 分别落在终端用户、scene/config、Host owner、测试职责边界；`dayu/README.md` 与 `dayu/engine/README.md` 未触发职责内更新 | 接受 PASS |

## Controller boundary clarifications

### C01 — tool-await lane 的 Attempt `SUSPENDED`

MiMo 将该点列为 residual observation，DeepSeek 判为 PASS。Controller 读取同一 lane 的
canonical EventLog：`TOOL_AWAITING` sequence 16、`RUN_WAITING` 17、
`ATTEMPT_SUSPENDED` 18，随后才是 `CANCEL_REQUESTED` 20 与 `RUN_CANCELLED` 21。
因此 cancel 到达时 Attempt 已按 Engine/Host waiting contract 成为不可重写的 terminal
`SUSPENDED`，不存在 running Attempt 残留，也不应伪造第二个 `ATTEMPT_CANCELLED`。Run 的
canonical terminal 是 `CANCELLED`。这满足本 work unit 禁止“强杀或残留 running”的 owner
约束，不是 implementation finding。

### C02 — F04 stable `client_request_id`

两条最终 Run id 分别属于 A 与 B，彼此不同不能单独证明 B 的 rejected retry identity 稳定。
稳定性由 `_InteractivePendingMutation` 在 Host acceptance barrier 前冻结
`client_request_id`，且只有 draft/revision 变化才创建新 identity；owner tests 直接断言
READ_ONLY→READ_WRITE 与 repeated READ_ONLY 的 mutation attempts 使用相同 request id。
真实双 attachment lane 再证明 B 两次拒绝时零 Run、fresh attach 后恰好一个 B Run。组合证据
满足 frozen requirement；review 的局部论证措辞不升级为 finding。

## Residual risks

- 真实 provider 输出具有通常的非确定性；deterministic owner matrix 与真实成功、repair、
  exhaust、fallback、Memory/Tool follow-up 的 conjunction 已降低风险。
- 首轮并发 S7 matrix 的 0.01 秒 lane acquire timeout 没有稳定复现；串行 node、完整串行
  matrix 与 full suite 均通过。若 CI 高负载复现，由 test-runtime lane scheduler owner 诊断，
  不据此修改产品或放宽断言。
- CI raw durable stores 会持久化 resolved provider Authorization；本次 bundle 已在投影后删除
  CI-owned raw carriers并通过零 finding scan。生产 durable execution projection 的 secret
  persistence 是已分配、超出本 work unit 的 residual，不在下游 evidence formatter 补偿。

## Gate verdict

`S8-CODE-REVIEW-PASS — READY-FOR-S8-ACCEPTED-COMMIT`

没有 blocking open question；无需修改 production、tests、README 或 sealed evidence。
