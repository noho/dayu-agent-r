# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN3-F01 code review Controller adjudication

## Review inputs

- baseline：`4814b7dc93052f5742ab8b7f33a8dff9377c5ff6`。
- AgentMiMo：`docs/reviews/code-review-20260720-002828.md`，SHA-256 `bb81e30e03b4cb98df1efcd039c790584c94770a438427fa1a3a9eff68b18fa8`，结论 `PASS / MATERIAL_FINDING_0 / READY_FOR_WINDOWS_RERUN`。
- AgentDS：`docs/reviews/code-review-20260720-003027.md`，SHA-256 `d2e1f9c398a3055e14f96ba765bb31986aa2cb25a951e4073c21cedc9a25d9ce`，结论 `PASS / material finding 0 / READY FOR ACCEPTED COMMIT`。
- 两路均完整读取当前 implementation/control/artifact target，审计 direct/non-CLI consumers，运行 `98 passed, 7 skipped` 与 full pyright zero；均没有把 Darwin skip 当 Windows pass。

## Material finding 裁决

- accepted：0。
- rejected-with-reason：0 个 reviewer material finding；两路均未提出 material finding。
- deferred-with-owner：0 个新 code finding。
- blocking open question / design contradiction / local blocker：0。

WIN3-F01 继续是 `LOCAL_FIX_VALIDATED / ACCEPTED-OPEN UNTIL WINDOWS RERUN`，不是 code-review 新 finding。WIN2-F01/F02/F03 继续是 `EVIDENCE_POSITIVE / OPEN UNTIL CLEAN RERUN`。

## Reviewer observation 裁决

1. **第三轮 setx timeout 的独立性**：采用 AgentMiMo 的保守结论，状态为 `NEEDS_REMOTE_EVIDENCE / NO CURRENT CODE FIX`。现有 evidence 证明 ambient cp1252 consumer 是真实 defect，但不能证明 setx timeout 必然只有这一原因。第四轮若仍 timeout，必须以新 evidence 重新归因；当前没有可实施的第二个 owner fix。
2. **R11 generated CLI script 的 `returncode=1`**：AgentDS 将其完全归因于 reader decode failure 的说法不接受。`CompletedProcess.returncode` 是真实 `cmd.exe` 退出码，reader exception 会丢失 stdout/stderr，但不能单独证明子进程为何返回 1。当前 strict-decode fix 是读取真实失败/成功输出的必要修复；第四轮若仍非零，必须保留实际 UTF-8 stderr并建立新 root cause，不得被本 finding 掩盖。
3. **module-help 未列入 R11/R12**：`NO CURRENT FIX`。Darwin owner contract直接验证含中文的严格 UTF-8 consumer；R11/R12 已运行 generation/execution/init 的实际 Windows consumers。为同一语义再扩 workflow 节点没有当前缺陷证据。
4. **prewarm/recorder 未来可能输出非 ASCII**：`REJECTED-WITH-REASON / NO CURRENT FIX`。它们当前不消费 Dayu CLI 输出且职责清晰；为假设性未来输出增加 README policy 或 encoding 会扩大当前 owner。新增非 ASCII 时应由该调用自己的输出契约决定。

这些 observation 不形成 deferred Issue 或 accepted current fix；remote rerun 是当前 gate 的必要验证，不是“后续优化”。

## Retained boundary judgment

- 七个 strict UTF-8 declarations 都位于实际 Dayu CLI output consumer；`reg.exe`、junction、prewarm、recorder 保持自己的命令输出契约。
- `text=True, encoding="utf-8", errors="strict"` 是 Python 3.11 明确 text pipe contract；没有 loose decode、fallback、全局环境 shim 或通用 framework。
- 产品/workflow/deferred paths 零 diff；Config/Host internal SQLite/EventLog trusted-local 与 Tool Trace/audit/public/LLM/log/output secret-zero 裁决不变。
- 未实施统一 authorization 或任何 deferred Issue。

## Decision 与下一 gate

结论：`PASS / ACCEPTED_CODE_FINDING=0 / ZERO-CHANGE DISPOSITION REQUIRED`。

为完成本 umbrella 既定 review→fix→re-review 顺序，下一步由 AgentCodex只写 zero-change disposition artifact，锁定四个 implementation paths、Controller/reviewer artifacts和上述 observation裁决，不修改产品/tests/README/workflow/control内容。Controller验证后，AgentMiMo/AgentDS 对完整新树并发 re-review。re-review 前不授权 stage、commit、push 或 workflow dispatch。
