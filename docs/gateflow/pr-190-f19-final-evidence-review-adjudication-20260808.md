# PR 190 F19 final evidence review adjudication（2026-08-08）

## Review inputs

- DS：`docs/reviews/plan-review-20260808-194613.md`，二值`PASS`，SHA-256
  `e0d9e933b5a76491925290363fe00a07a670039b549a0f9323403fe31addcaa0`。
- MiMo：`docs/reviews/plan-review-20260808-194759.md`，二值`FAIL`，SHA-256
  `8c7b07541d3d58d190363a78bd7b8318da46832ec9ffb6ce22eb96c37d27008e`。
- Controller已直接复算public digest/scan、execution-index refs、private typed counts与canonical terminals；reviewer自报不替代
  Controller核验。

## Controller adjudication

接受MiMo的唯一finding `F19-B2-EVIDENCE-001`；DS的综合PASS不足以推翻该精确owner-level证据：

1. 冻结plan明确要求`observation-summary.json`逐链包含budget、actual ordinary/compactor calls、terminal refs、seal/verdict。
2. 实际三个`chains[]` keys均没有`budget`。Chain 01/02 budget只存在于另一份summary的逐segment wrapper projection；
   `execution-index.json`没有绑定两个private chain deadline owner files的relative ref与file-byte SHA；Chain 03也没有逐链
   no-deadline budget record。
3. 顶层global/provider/per-chain cap是共享policy，不拥有各链deadline identity、实际窗口或not-started state，不能补偿缺失的
   逐链publication contract。
4. digest与final scan证明冻结bytes完整、无secret/path/raw-DB/symlink问题，不证明缺失的semantic field存在。

因此publication verdict必须从候选的`PASS/conforming`纠正为`FAIL/nonconforming`。该finding不改变五个canonical
`RUN_SUCCEEDED`，不把0 compaction的non-covering观察改写成产品failure，也不改变B2的`unadjudicated`或overall not-ready。

## Scope decision

F19 public tree已由`secret-scan.json`封存，禁止原地回写。创建新的publication revision会引入新的work unit/publication identity，
不属于本closeout的自动修写权限；本次不扩scope、不追加provider、不修改产品/CLI/analyzer/oracle/scenario。仓库只记录finding、
证据入口与五项诚实verdict。
