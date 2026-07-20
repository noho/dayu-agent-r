# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN3-F01 code-review zero-change disposition — AgentCodex

## Gate、边界与结论

- Gate：同一 `WU-SEMANTIC-OWNERSHIP-01` / `AR-F07` / `WIN3-F01` code-review fix；不是新 WU。
- immutable baseline / HEAD：`4814b7dc93052f5742ab8b7f33a8dff9377c5ff6`；branch：
  `phaseflow/host-issues-control`。
- Controller 唯一 finding 裁决真源：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-controller-adjudication.md`。
- 决策：`ZERO_CHANGE_FIX_PASS / READY_FOR_CONTROLLER_VALIDATION / WINDOWS_RERUN_REQUIRED`。
- 两路 reviewer material finding 均为 `0`；Controller accepted code finding、rejected material finding、
  deferred code finding、blocking open question、design contradiction 与 local blocker均为 `0`。
- 当前没有可实施的产品、test、README、workflow 或 control 修复。除新增本 artifact 外，既有实现与 evidence/review/control
  内容均保持不变。
- 未 stage、commit、push、创建或修改 PR、dispatch workflow、更新 control，亦未关闭 WIN3-F01、WIN2-F01/F02/F03、
  AR-F07 或 umbrella。

## 已完整读取的真源输入

| 输入 | 行数 / 字节数 | SHA-256 | 结论 / 职责 |
|---|---:|---|---|
| `docs/reviews/code-review-20260720-002828.md` | 195 / 14,659 | `bb81e30e03b4cb98df1efcd039c790584c94770a438427fa1a3a9eff68b18fa8` | `PASS / MATERIAL_FINDING_0 / READY_FOR_WINDOWS_RERUN` |
| `docs/reviews/code-review-20260720-003027.md` | 154 / 18,126 | `d2e1f9c398a3055e14f96ba765bb31986aa2cb25a951e4073c21cedc9a25d9ce` | `PASS / material finding 0`；其中两项单因归类不被 Controller 接受 |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-controller-adjudication.md` | 39 / 3,915 | `087f0817c9bc872c0900b7d8a6c59a51c8ce1a5260b60054ef23abf803f68f16` | `PASS / ACCEPTED_CODE_FINDING=0 / ZERO-CHANGE DISPOSITION REQUIRED` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-codex.md` | 125 / 9,473 | `1761ea0b41f1dc469ebb44559c098f3a2469ef121f282c115967755070cdbbfd` | 当前 implementation / fix artifact |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-controller-validation.md` | 40 / 3,199 | `1596a71226bbadbfce84ad89d401704f91e21b338b37cdcf607bf2e33a515c1b` | `PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / WINDOWS_RERUN_REQUIRED` |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-evidence-controller-adjudication.md` | 41 / 4,328 | `7ae06070fb37f2660f043ec8ed9f14d86555035b93a7ae4a21380130ea0e065d` | WIN3-F01 的 evidence 与 owner 真源 |
| `docs/host/issues-implementation-control.md` | 2,348 / 604,706 | `ff434894d8321fbceee1d2722afafb324a1fb730ac09e9f2b137e35311691f93` | 当前 gate 与 next entry point 真源 |

两路 review 与 Controller adjudication 的排序 manifest digest 为
`47020f059c51efbc311a267afef344658c0c38b1cb99e1090668725bfc5412f2`。Control 当前 gate 明确要求仅写本
zero-change disposition；implementation 与 Controller validation 均锁定相同四个 implementation paths 和相同 binary diff。

## 第一性原理与 owner 判断

WIN3-F01 的已证实 defect 位于直接消费 Dayu CLI UTF-8 bytes 的测试 subprocess boundary，七个 direct consumers 已在该
owner 处声明 `encoding="utf-8", errors="strict"`。两路 review 没有发现新的 material defect，Controller accepted code finding
为 `0`。因此当前修改产品 producer、native command、workflow、测试策略或 README 都不能关闭一个新证实的 owner defect；这样做
只会越过 owner boundary或为假设性未来行为增加第二套策略。本 gate 的正确处置是保持实现树不变并完整记录裁决。

## Controller observation 逐项 disposition

1. **第三轮 setx timeout**：`NEEDS_REMOTE_EVIDENCE / NO CURRENT CODE FIX`。现有 evidence 证明 ambient cp1252 consumer 是
   真实 defect，但不能证明 setx timeout 必然只有这一原因。不得把 timeout 提前单因归类为 reader decode failure；第四轮真实
   Windows rerun 若仍 timeout，必须基于新 artifact 重新确定 root cause 与 owner。
2. **R11 generated CLI script `returncode=1`**：`NEEDS_REMOTE_EVIDENCE / NO CURRENT CODE FIX`。
   `CompletedProcess.returncode` 是真实 `cmd.exe` 退出码；reader exception 能解释 stdout/stderr 丢失，却不能单独证明子进程为何
   返回 `1`。第四轮若仍非零，必须保留 strict UTF-8 stderr 并以其建立新 root cause，不得用 WIN3-F01 掩盖。
3. **module-help 未加入 R11/R12 workflow**：`NO CURRENT FIX`。Darwin owner contract 已直接消费含中文输出；R11/R12 已运行
   generation/execution/init 的实际 Windows consumers。没有当前 defect 证据支持再增加 workflow 节点。
4. **prewarm/recorder 未来可能输出非 ASCII**：`REJECTED-WITH-REASON / NO CURRENT FIX`。它们当前不消费 Dayu CLI 输出，
   且职责和现有输出契约清晰；未来若新增非 ASCII，应由对应调用自己的 output owner 决定编码，不在当前 README 或调用点预设。

以上 observation 均不形成 accepted current fix 或 deferred Issue。第四轮 remote rerun 是当前 gate 的必要 evidence closure，
不是“未来优化”。

## 四个 implementation paths 内容锁

入口、focused tests、full pyright 与终态扫描前后，逐路径 SHA-256 均保持如下：

| Path | SHA-256 |
|---|---|
| `tests/README.md` | `504b7c1ff84ed15e1f64a50decbad60841336d46a99662aadaabc45b1566af4b` |
| `tests/cli/test_arg_parsing.py` | `89f355d9959f456975036935871aa22b337636c081fc3c832c289e543025ea6c` |
| `tests/cli/test_init_smoke.py` | `565b108b6a6796ee0393d9f472cb83a3eb287f7af1c465d8d9e99cf51c4e5f56` |
| `tests/cli/test_upload_filings_from_command.py` | `7c105d40f3a16e92fd4a4f95f7df69337b5d642aeca48a68e2c52a53f1e3b649` |

- 四路径相对 baseline 的 canonical `git diff --binary` SHA-256：
  `9477cef2dfbba98050193f5801dc77c3a469591cfc50463dc4dffdb84341b469`，与 implementation artifact 和
  Controller validation 完全一致。
- `git diff --numstat` 依次为 `3/1`、`6/3`、`4/0`、`8/0`；合计 `21 insertions / 4 deletions`。
- 四路径没有在本 gate 被修改；其 strict UTF-8 owner contract、native-command 排除与 README 表述无漂移。

## Review-entry 与完整新树内容锁

pre-review target 是四个 implementation paths 加 control、evidence adjudication、implementation artifact 和 pre-review
Controller validation，共 8 paths；其排序 manifest digest 在本 gate 前后均为
`3fcc078d3e92679344b98f9edc2c56c623aa52e0ffc7578f82baa18b4d6529ae`。

加入两路 review 与 code-review Controller adjudication 后，disposition 入口的完整 11-path tree 如下：

| 分类 | Path | SHA-256 |
|---|---|---|
| implementation | `tests/README.md` | `504b7c1ff84ed15e1f64a50decbad60841336d46a99662aadaabc45b1566af4b` |
| implementation | `tests/cli/test_arg_parsing.py` | `89f355d9959f456975036935871aa22b337636c081fc3c832c289e543025ea6c` |
| implementation | `tests/cli/test_init_smoke.py` | `565b108b6a6796ee0393d9f472cb83a3eb287f7af1c465d8d9e99cf51c4e5f56` |
| implementation | `tests/cli/test_upload_filings_from_command.py` | `7c105d40f3a16e92fd4a4f95f7df69337b5d642aeca48a68e2c52a53f1e3b649` |
| control | `docs/host/issues-implementation-control.md` | `ff434894d8321fbceee1d2722afafb324a1fb730ac09e9f2b137e35311691f93` |
| evidence | `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-evidence-controller-adjudication.md` | `7ae06070fb37f2660f043ec8ed9f14d86555035b93a7ae4a21380130ea0e065d` |
| implementation artifact | `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-codex.md` | `1761ea0b41f1dc469ebb44559c098f3a2469ef121f282c115967755070cdbbfd` |
| Controller validation | `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-fix-controller-validation.md` | `1596a71226bbadbfce84ad89d401704f91e21b338b37cdcf607bf2e33a515c1b` |
| review | `docs/reviews/code-review-20260720-002828.md` | `bb81e30e03b4cb98df1efcd039c790584c94770a438427fa1a3a9eff68b18fa8` |
| review | `docs/reviews/code-review-20260720-003027.md` | `d2e1f9c398a3055e14f96ba765bb31986aa2cb25a951e4073c21cedc9a25d9ce` |
| adjudication | `docs/reviews/wu-semantic-ownership-01-ar-f07-third-windows-code-review-controller-adjudication.md` | `087f0817c9bc872c0900b7d8a6c59a51c8ce1a5260b60054ef23abf803f68f16` |

上述 11 paths 的排序 manifest digest 在本 gate 前后均为
`ecdf6a4dd729f9d89276c7edec3f204848d4a888b94549cdd759964e3f943917`。本 artifact 是完整新树唯一新增的第 12 个 path；
其终态行数、字节数与 SHA-256 由写入后的机械核验给出，不回写正文，避免 self-hash 递归。

## Fresh validation 与 scans

所有 Python 命令均在 `source .venv/bin/activate` 后执行：

| Gate | Result |
|---|---|
| 三个 affected test files | `98 passed, 7 skipped, 3 warnings in 27.46s`；7 个 skip 均为本机 Windows-only |
| full pyright `dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | PASS |
| staged tree | empty |
| 四路径 binary diff / per-path hash | 与 implementation / Controller validation 锁完全一致 |
| prohibited encoding/shim scan | 新增 `cp1252`、`errors=ignore/replace`、`PYTHONIOENCODING`、`PYTHONUTF8`、`shell=True` 命中 `0` |
| configured-secret value scan | 新增 Bearer / `sk-` / API-key / Authorization value 形态命中 `0` |
| production/workflow/root README scan | `dayu/`、`.github/`、根 `README.md` 零 diff |
| deferred/design path scan | control 之外的 `docs/host/`、`docs/engine/`、`docs/fins/`、`docs/config/` 零 diff |

pytest 的三个 warnings 仅为既有 `edgar` deprecation warnings。当前主机是 Darwin；本地 skip 不构成真实 Windows pass。
本 artifact 以 `git diff --no-index --check /dev/null <artifact>` 单独验证通过；该命令对新增文件返回预期 diff exit `1`，
但没有 whitespace error。

## Finding 与 residual 状态

- 本 code-review loop：`accepted/open code finding = 0`，无需产品/test/README/workflow/control fix。
- WIN3-F01：`LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`。
- WIN2-F01/F02/F03：`EVIDENCE_POSITIVE / OPEN UNTIL CLEAN RERUN`。
- 第四轮 R11 必须以真实 `windows-latest` evidence 证明完整 `4/4`；若 generated CLI script 仍返回非零，必须保留其
  strict UTF-8 stderr 并重新裁决 root cause。
- 第四轮 R12 必须证明 init `9/9`、内嵌 R11 `2/2`；若 setx 仍 timeout，必须作为新 evidence 重新归因，不能沿用
  “必然由 decode failure 导致”的单因结论。
- artifacts 继续保持 names-only / secret-plaintext-zero；不得保存 API key、header 或 registry value。

上述 remote evidence 是 AR-F07 的必要 release closure，owner 是后续已授权的第四轮 R11/R12 rerun 与 Controller evidence
adjudication；它不是当前可实施的 code-review fix，也不形成新的 deferred Issue。

## Next entry point

仅允许 Controller validation 本 zero-change disposition 与终态 path/hash/stage/diff evidence；之后由 AgentMiMo / AgentDS 对
完整新树并发 complete code re-review。re-review 前不得 stage、commit、push、创建或修改 PR、dispatch workflow、修改 control
或提前关闭任何 Windows finding。
