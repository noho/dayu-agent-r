# PR 190 F18 final closeout（2026-08-08）

## Final verdicts

- Product/setup implementation verdict：`PASS / no product change / setup correction`。F18没有修改产品、schema、runtime、
  harness或README；fixed-profile production assembly与两条canonical success证明产品路径可运行，实际修正面是scenario
  material与预算解释。
- Evidence publication verdict：`FAIL / nonconforming`。冻结public summary含一个无法与目标artifact对齐的
  `material_audit_sha256`、缺少per-chain budget/count/terminal refs，并缺少accepted plan要求的per-attempt public resolver/
  Tool Trace analysis与`execution-index.json`；final scan后不得回写修复。
- Real observation verdict：`needs-more-evidence`。两条provider segment共7个ordinary calls、`42.5896s`，均
  `RUN_SUCCEEDED`但non-covering；第三条在CLI spawn前被empty-prompt precondition拒绝，provider未启动。三条均无compactor
  operation，replacement、repair、fallback、durable同源与reconnect未覆盖。
- Oracle status：`interactive.interactive.g06.cap-constrained-memory-replacement@1`保持`unadjudicated`；registry保持
  `calibration`，overall readiness保持not ready。本closeout不替用户接受B2。

MiMo/DS独立plan review均为PASS：`docs/reviews/plan-review-20260808-172014.md`、
`docs/reviews/plan-review-20260808-172234.md`。纠正后的下一provider segment在frozen monotonic
`global_deadline - 180s`门关闭后没有启动；这是预算owner的deadline stop，不是产品failure。

## Frozen publication

Public bundle：`pr190-f18-b2-fixed-XUmH8YBg`。最终SHA-256：

- observed report：`0969738ba5d75b4749b785fc6d8203cfd53e55a6cf850cbd3ad2408eacc3f8aa`；
- observation summary：`1bc5eeb1f2c5537e0e5ebd60ad7f6e06c244f8d10802bb2cb6a42cd6d65d2457`；
- material audit：`6399d1280a7c567ed96e563739f0338b32371f01ea3c578357582ff38c15af8f`；
- calibration summary：`2b855885e5820bf2e902b64b3352425cef8486498bf17ae8655c14031436baa1`；
- digest：`36fd642ad1700a7386ad7263bd1ef52496ba465ffea5dd367abcc2f175e4a627`；
- secret scan：`40f7885d6d1c517c2db40289d636b02a2cc3837bc5c04081f15432ad294e4f47`。

Final scan覆盖5个文件、`27,450` bytes，secret/path/errors均为0；final scan后public tree无后续写入。

这些顶层SHA与scan hygiene结论正确，但不消除publication contract finding：summary中的
`material_audit_sha256=37eee3c...`与material file SHA `6399d128...`及canonical JSON SHA `18284f2e...`均不一致；bundle也没有
per-chain budget/count/terminal refs、per-attempt public resolver/Tool Trace JSON/Markdown或`execution-index.json`。因此F18
public evidence只能作为immutable failed publication保留，不能作为B2 mandatory evidence或readiness proof。

## F19 handoff

F19必须创建新work unit、新global deadline、新bundle与fresh workspace，从首次opener固定同一profile，执行已经双审PASS的
`s_0003 business-risk previous fact -> s_0013 FY2025 financial evidence -> no-tool target -> reconnect`链。不得复制F18
durable state，不得覆盖两条non-covering结果，不得在真实模型未触发时伪造replacement、repair或fallback。完成新的逐项人类可读
报告后仍须由用户单独裁决B2。F19 publication必须为每条attempted chain发布path-redacted resolver/Tool Trace analysis与
`execution-index.json`，所有跨文件digest字段须声明domain并在final scan前由目标artifact直接复算一致。
