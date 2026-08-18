# UF-FIX03 plan re-review adjudication

## Gate

- work unit：`UF-FIX03 summary-and-bounded-errors`
- gate：`plan re-review -> controller adjudication`
- reviewed plan：`docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`
- re-review artifacts：
  - `docs/reviews/plan-review-20260813-210131.md`（AgentMiMo，`pass`）
  - `docs/reviews/plan-review-20260813-210506.md`（AgentDS，`pass`，3 个低风险新发现）
- decision time：`20260813-210651`
- overall decision：**PASS AFTER SMALL PLAN FIX AND TARGETED RE-REVIEW**

## Accepted findings

### N1 — pipeline `cancelled` 状态矩阵遗漏

- 裁决：`accepted`
- 直接证据：当前 `_UPLOAD_TERMINAL_DISPOSITIONS` 接受 `cancelled`，shared cancelled producer 也会产生该状态；plan §5.2 却只列出
  `skipped/deleted/failed` 的 stored-zero 约束，fix artifact C4 的“避免给 pipeline 虚构 cancelled 状态”事实前提错误。
- 必须修复：`FinsUploadPipelineResult.__post_init__()` 的 owner 状态矩阵显式包含 `cancelled -> stored_file_count == 0`；测试同时覆盖
  direct constructor 与 parser。不得把 cancelled 留给 summary 下游兜底。

### N2 — 超长 basename 不得使 known failure 降级

- 裁决：`accepted`
- 直接证据：plan 让 canonicalizer 对 `>240` 字符 basename 直接拒绝；该调用位于 filing empty/conversion failure producer 路径，拒绝会让
  原本已知 content failure 无法形成 typed reason，违背唯一 typed owner 与 bounded public reason 目标。
- 必须修复：pathful 输入仍拒绝，因为调用者契约必须提供 basename；合法 basename 若超过 public label 上限，与 fragment、URL、`Cc/Cf`
  一样确定性投影为固定标签 `输入文件（文件名已隐藏）`。测试覆盖超长合法 basename 仍产生原 content kind/code，且所有 consumer 使用
  同一 canonical label。

### N3 — reason constructor 必须拥有 label 防御

- 裁决：`accepted`
- 直接证据：只要求 JSON parser 调 validator，不能约束 owner 内 factory 或未来 direct constructor；这会让同一 public reason 类型出现
  parser 与 constructor 两套接受集。
- 必须修复：`FinsUploadFailureReason.__post_init__()` 在 `file_label is not None` 时调用唯一
  `validate_fins_public_file_label(...)`。parser 只做 exact key/type 读取并调用 constructor，不复制 label 规则。测试直接构造非法 label
  并断言拒绝。

## Rejected or deferred findings

无。三项均为 owner contract 的小修订，不能仅作为 residual risk 留到实现后处理。

## Scope and next entry

- AgentCodex 只允许修改 plan 与新增 plan re-review fix artifact；不得修改生产代码、测试、README、冻结 JSON 或 evidence。
- 修订完成后由 AgentMiMo / AgentDS 定向复核 N1–N3；两路确认无 blocker 后进入 accepted plan commit。
- 不执行 UF-PF03，不创建 PR，不扩大 material 业务 scope。
