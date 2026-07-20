# WU-SEMANTIC-OWNERSHIP-01 / R06-S2 code review Controller adjudication

## 结论

`FIX REQUIRED`

第一路 AgentMiMo artifact 为 `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-mimo.md`，结论 `PASS / 0 findings / 0 blockers`。第二路 AgentDS artifact 为 `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-ds.md`，结论 `PASS — 1 Low material finding / 0 blockers`。

Controller 对两路 evidence 和实际调用图复核后，接受 1 个 finding group；blocking product/design question 为 0。

## Finding ledger

### R06-S2-CR-F01 — 接受：删除 `_resolve_primary_uri` 的 first-file 猜测

- 来源：AgentDS `R06-S2-CR-F01`；MiMo 未报告该点。
- 裁决：`ACCEPTED / FIX REQUIRED`。
- 直接证据：`dayu/fins/storage/_fs_storage_utils.py::_resolve_primary_uri` 的 contract 声明“未找到返回 None”，但当显式 `primary_name` 未命中时仍返回 `file_payloads[0].uri`；其两个 production caller 都把结果写入 `DocumentHandle.primary_file_uri`。
- 动机：accepted R06 plan 明确要求删除 first-file primary fallback；`DocumentHandle.primary_file_uri` 虽不拥有 durable publication qualification，也不能在 source owner 已给出显式 primary identity 后静默猜另一个文件。commit validator 后续 fail closed 不能证明此前返回的派生值正确，也不能作为下游补偿理由。
- owner boundary：修复应位于 `_resolve_primary_uri` 的唯一派生 helper，使其只在显式 primary name 精确命中文件时返回 URI，否则返回 `None`；不得在两个 caller 分别补条件、不得放宽 validator、不得添加兼容分支。
- allowlist refinement：`dayu/fins/storage/_fs_storage_utils.py` 是该派生语义的直接 owner，属于 accepted finding 要求的最小 root-boundary refinement；不是 S3 producer、R07 或新能力扩域。
- 验证：必须增加 owner/public-contract test，证明显式 primary 未命中时 `DocumentHandle.primary_file_uri is None`，且 commit validator 仍拒绝并消费 token、published state 不出现 half source；保留精确命中成功与 logical delete/restore 行为。

## 未接受为 finding 的 observations

- DS O-02 `ProcessedManifestItem` 没有 `from_processed_meta`：当前没有 correctness/ownership drift 证据，也不属于 S2 complete-source contract；不接受为当前 finding。
- DS O-03/O-05 私有 state/path test injection：这是 crash/validator corruption owner tests 的必要 test seam，S1 已记录；不要求 production compatibility 或新 public test API。
- DS O-04 recovery journal read 时序：S1 已验证 global recovery lock、ticker writer lock、journal containment/recovery phase；本轮没有直接 failure evidence，不接受为新 finding。
- MiMo 记录的 validator 未覆盖分支：当前 22 格 failure matrix、双向 manifest、filing/material、rollback/recovery/online barrier 与逐文件覆盖率已达到 accepted gate；信息级 residual 不阻塞当前修复，但 re-review 应确认新增 F01 owner path 有测试。

## 下一 gate

AgentCodex 只修复 `R06-S2-CR-F01`，更新/新增唯一 fix artifact `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-fix-codex.md`，并重跑受影响测试、coverage、scoped pyright/Ruff、full baselines、exact scans 和 `git diff --check`。不得进入 S3、修改 README final contract、创建中间 commit 或实现 R07/Issue 175/177。

Controller validation 通过后，AgentMiMo / AgentDS 必须并发完整 re-review，明确关闭 `R06-S2-CR-F01` 且检查 S1 closure 未回退；只有两路 re-review 和 Controller adjudication 都通过，才能进入 S3。
