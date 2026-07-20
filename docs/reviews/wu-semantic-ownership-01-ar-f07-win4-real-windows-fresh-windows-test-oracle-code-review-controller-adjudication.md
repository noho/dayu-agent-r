# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 One-test Code Review — Controller Adjudication

## Gate identity and verdict

- Timestamp：`2026-07-20T09:57:54+0800`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；本 gate仍属于最后一个内部 remediation sub-WU `AR-F07 WIN4-RW-RF01`。
- Mechanical base：`39926eb85aa25441f5209a128a3c971f451b5b25`。
- Frozen code diff SHA-256：`fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`。
- Verdict：`PASS / ACCEPTED_CODE_FINDING=0 / BLOCKER=0 / ZERO_CHANGE_FIX_AND_DUAL_REREVIEW_REQUIRED`。

## Dual review evidence

| Reviewer | Artifact | Lines | SHA-256 | Final verdict |
| --- | --- | ---: | --- | --- |
| AgentMiMo | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-code-review-mimo.md` | `160` | `0fbf17bb730ec1b3cb4cb1093135acd3516de342b5e4a38caf312cefdb84d7b2` | PASS / finding `0` / blocker `0` / open `0` / backflow `0` |
| AgentDS | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-test-oracle-code-review-ds.md` | `239` | `c60a8db64800f37a26fdb1a384b5f980ad8d434b1a7ca765cc414a4ddbb78b4d` | PASS / material `0` / blocker `0` / open `0` / backflow `0` |

AgentMiMo 初稿以 plain diff bytes计算 `f4dd...`，误写成冻结 identity mismatch。Controller 指出冻结 identity必须使用
`LC_ALL=C git diff --binary --full-index --no-ext-diff --no-renames`；same-task follow-up独立复算并得到 exact
`fcecb15c...f2169`，final artifact已删除假 residual。该纠正是 review method fix，不是 code finding。

## Finding disposition

1. 两路均确认 primary与raw-source使用独立 exact-name filters，`len == 1`对 zero/multiple hits fail closed；raw-source
   optional `sha256`先显式非空，再与 fixture bytes hash精确比较。
2. 合法 `primary != raw-source` 不再失败；test没有硬编码 Docling expected primary，也没有从 private meta、physical tree或
   `rglob`反推 publication。
3. Diff只有 exact function现有 snapshot assertion block；product、其它 test、import/helper/schema/oracle字段、README、design、
   workflow零 implementation delta。
4. MiMo 提到的 POSIX assertion asymmetry是 pre-existing/out-of-scope non-finding；本轮 POSIX real smoke已通过，且该观察不影响
   Windows owner contract，不接受修复或 residual ledger entry。
5. 真实 Windows pending是唯一 residual：owner/destination为 Controller在 accepted implementation与aggregate gates后执行
   fresh R11/R12；不是 code finding或 waiver。
6. trusted-local config/Host durable secret与 Tool Trace/audit不泄露明文的安全裁决不变；无统一 authorization framework，
   deferred Issue 142/151/175/177/178及 Web/WeChat/render范围零漂移。

## Ledger and authorized next gate

| Category | Count | Status |
| --- | ---: | --- |
| Accepted code finding | `0` | CLOSED |
| New/backflow finding | `0` | CLOSED |
| Blocker/open/design contradiction | `0` | CLOSED |
| Residual requiring later evidence | `1` | R11/R12 / Controller-owned |

按用户固定流程，即使 accepted finding为零，下一 gate仍是 AgentCodex zero-change code-review fix record与Controller validation，
随后 AgentMiMo/AgentDS双路完整 immutable re-review。不得直接 commit、push、dispatch、aggregate、PR review或 final closeout。
