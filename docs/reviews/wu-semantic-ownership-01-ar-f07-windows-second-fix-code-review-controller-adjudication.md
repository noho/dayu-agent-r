# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 第二轮 Windows code review Controller adjudication

## Review inputs

- immutable baseline：`ac5e755ba7148a5d2f30f3f11222548b3c57cd9e`。
- reviewed target：Controller validation 固定的 10 paths；target path digest `2f481388c463bc072f3d3f2c73300fef57a56a9a796fb601290e641dd2f35e01`，review-entry tracked binary diff `41bf22a19b45894dcfd13a351baed6bf4d934c27375b5c144ba98fbe8ea1fd23`。
- AgentMiMo：`docs/reviews/wu-semantic-ownership-01-ar-f07-windows-second-fix-code-review-mimo-20260719-234121.md`，SHA-256 `3530671635e73d21d6efd7445ab12e6792a38c46d8b8a4ecccec511fa1de441b`，结论 `PASS / 0 findings`。
- AgentDS：`docs/reviews/code-review-20260719-233825.md`，SHA-256 `b7ab6db9e79c1d382fc8ef71377eb8968364d4be632b2dd5effc0373aa86ff6a`，结论 `PASS / NO_MATERIAL_FINDING`。

两路均完整读取 10-path target、真源、第二轮 Windows evidence 和关键调用链；均明确没有把本地 decoder 当作真实 Windows pass。

## Controller finding adjudication

### Material findings

- accepted：0。
- rejected-with-reason：0 个 reviewer material finding；两路均未提出 material finding。
- deferred-with-owner：0。
- needs-more-evidence：0。
- blocking open question：0。

WIN2-F01/F02/F03 不是本轮 reviewer 新 finding；它们仍保持
`LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`，最终状态只能由修复后 R11/R12 真实 runner evidence决定。

### Reviewer observations 的最终裁决

1. AgentMiMo 的 Windows-only、workflow字符串断言与 help exit 稳定性三项均是已经记录的真实 runner residual / fail-closed behavior，不产生当前代码修复。
2. AgentDS 的 `_escape_windows_comment` 独立 parametrized test 建议：`rejected-with-reason / NO CURRENT FIX`。现有 renderer contract 已覆盖 regeneration `%` 与 metacharacter，第二轮根因和失败路径在 body quote owner，不存在可复现 comment defect；新增重复 helper test 不会关闭当前风险。
3. AgentDS 的 `Invoke-CmdEvidence` 显式 per-process timeout 建议：`rejected-with-reason / NO CURRENT FIX`。两个命令是本地瞬时 `ver`/help，workflow 已有 30 分钟 hard timeout与失败 artifact；没有当前 hang evidence，引入第二套 timeout/policy 属于过度设计。
4. AgentDS 的 test decoder 不支持 caret line continuation：`rejected-with-reason / NO CURRENT FIX`。production renderer 在唯一 owner 明确拒绝 CR/LF，oracle 不应实现生产输入域之外的 batch grammar。

这些裁决不形成 residual risk；真实 Windows rerun 是当前 gate 的必要外部验证，不是 deferred finding。

## Retained boundary judgment

- CLI strict UTF-8 只在共同进程入口配置具体 `TextIOWrapper`，不产生下游 fallback。
- Windows renderer 仍是固定 argv quote/escape 的唯一 owner，保留 direct executable body、raw `%*`、CRLF、`DisableDelayedExpansion`、containment/symlink/atomic publisher 与无 JSON-argv contract。
- workflow 不全局忽略 native failure，不改变 registry/setx owner，不暴露 secret value。
- Config/Host internal SQLite/EventLog trusted-local 裁决未改变；Tool Trace/audit/public/LLM/log/output 仍要求 secret plaintext-zero。
- 未实现统一 authorization 或任何 deferred Issue。

## Decision 与下一 gate

结论：`PASS / ACCEPTED_CODE_FINDING=0 / ZERO-CHANGE DISPOSITION REQUIRED`。

按本 umbrella 已采用的完整 gate 顺序，下一步由 AgentCodex只写一个 zero-change fix/disposition artifact，证明 10-path reviewed target 的产品/tests/README/workflow/control 内容无变化，并记录所有 observation 的 Controller 裁决。随后 AgentMiMo/AgentDS 对完整新树并发 re-review。re-review 前不授权 stage、commit、push、PR修改或 workflow dispatch。
