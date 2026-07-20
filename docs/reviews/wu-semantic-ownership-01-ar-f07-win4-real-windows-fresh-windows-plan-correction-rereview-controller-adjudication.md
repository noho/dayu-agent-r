# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 Corrected-plan Final Re-review — Controller Adjudication

## Gate identity and verdict

- Timestamp：`2026-07-20T09:32:42+0800`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；本 gate 仍是 `AR-F07 WIN4-RW-RF01` remediation continuation，不是新 WU。
- Frozen corrected plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，`1124` lines / SHA-256
  `571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2`。
- Verdict：`PASS / MATERIAL_FINDING=0 / BACKFLOW=0 / BLOCKER=0 / CORRECTED_PLAN_ACCEPTED / EXACT_DOCS_COMMIT_AUTHORIZED / IMPLEMENTATION_NOT_YET_AUTHORIZED`。

## Dual re-review evidence

| Reviewer | Artifact | Lines | SHA-256 | Verdict |
| --- | --- | ---: | --- | --- |
| AgentMiMo | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-plan-correction-rereview-mimo.md` | `349` | `082f9453cbe6ad4e9717af5d324515d7bb801deb8afbe607e5e78fbcc6e1d0b5` | PASS / material `0` / backflow `0` |
| AgentDS | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-plan-correction-rereview-ds.md` | `388` | `1a606b687d9e19caaf9d307e70b5990bad32a967e5969dd68b131e7f20e5e84c` | PASS / material `0` / backflow `0` / blocker `0` |

AgentMiMo 初稿曾把 `bffa43c3...` 与 `86450472...` 两个不同阶段的 Controller validation artifacts误述为同一
文件的 normalization mismatch。Controller 基于 exact filenames与 hashes纠正；AgentMiMo同一任务 follow-up 已原位修复，
删除无证据的 line-ending推测，并纠正 AgentDS已完成后的 next gate。该 review-record defect 不构成 plan finding，final artifact
以上表 SHA 为准。AgentDS artifact无需修改。

## Finding disposition

1. `WIN4-RW-RF01` 保持 accepted root cause：remote release-gate test越权规定 raw source必须等于 Fins-owned primary；
   这不是 production upload/Fins defect。
2. Corrected contract保持两个独立 owner facts：primary exact-name唯一命中 public descriptor；raw source exact basename唯一命中
   descriptor且 public `sha256` 等于同一 fixture bytes SHA-256。二者允许不同，任一 zero/multiple/empty/mismatch均 fail closed。
3. 初审 MiMo optional sha/rglob INFO 与 DS exact-one OBS均由 zero-change fix消费为 implementation/review checkpoints；
   没有遗漏、升级或 backflow，accepted/new/open finding均为 `0`。
4. `rglob`/physical tree只保留 artifact integrity；private meta/raw storage path、hardcoded Docling expected primary、helper/import、
   schema/oracle字段、README/workflow/Fins/product扩张继续禁止。
5. R11/R12 metadata-before-evidence、same-run artifact/log integrity、R12 value-free canary先扫后读、安全边界与 deferred issue
   destinations保持不变；没有引入统一 tool authorization framework，也没有读取 GitHub Secrets/configured secret values。

## Ledger

| Category | Count | Status |
| --- | ---: | --- |
| Accepted plan finding still open | `0` | CLOSED |
| New material finding | `0` | CLOSED |
| Backflow finding | `0` | CLOSED |
| Blocker / needs-evidence / design contradiction | `0` | CLOSED |
| Unclassified residual | `0` | CLOSED |

## Authorized next gate

只授权 Controller 形成一个 exact-scope docs/control/reviews accepted corrected-plan commit。该 commit不得包含 product、test、
README、design 或 workflow delta。commit 后必须另做 Controller post-commit validation与 control transition；只有该 transition
明确授权后，AgentCodex才可实施 plan限定的一个 test snapshot assertion block。当前不得进入 implementation、push、remote
dispatch、PR review或 final closeout。
