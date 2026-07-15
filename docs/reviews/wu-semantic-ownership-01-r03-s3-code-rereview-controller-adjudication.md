# WU-SEMANTIC-OWNERSHIP-01 R03-S3 Final Code Re-Review Controller Adjudication

## 1. Gate 与最终决定

- gate：R03-S3 dual final code re-review
- baseline / HEAD：`44e68550ed226a3a207a73bd257478ab1bbbdce4`
- MiMo artifact：`docs/reviews/wu-semantic-ownership-01-r03-s3-code-rereview-mimo.md`
- DS artifact：`docs/reviews/wu-semantic-ownership-01-r03-s3-code-rereview-ds.md`
- decision：`ACCEPTED_CODE_RE_REVIEW / ZERO_FINDING / ACCEPTED_LOCAL_COMMIT_AUTHORIZED`

两路 reviewer 都重新审查了 `44e68550..worktree` 的完整 S3 组合行为，而不是只看 zero-change fix artifact；两路最终 verdict 均为 `PASS`，material finding 为 `0`，open question 为 `0`。初始 accepted/rejected/deferred finding 仍全部为 `0`，`R03-S3-CV-F01..F05` 全部关闭。无需第三轮 fix/re-review。

## 2. Protected evidence 裁决

AgentCodex zero-change record、Controller 独立验证、MiMo final re-review 与 DS final re-review对同一固定 26-target 集合给出一致证据：

- path-set SHA-256：`acb20b019768832b83e99d0570c82638da478835ed6b8bb70ddd7894a76884aa`
- zero-change 时 content SHA-256：`fff5894ecd6e6de201fa21f1c6a8bfb8c40c0e37709c8b4756aa50dbaf0a5bfa`
- zero-change 时 status/path SHA-256：`e0c6799cbb40e8f905b5dbc6bbdefa16587667adf2e7e2d5bd73c91508c0d481`

final re-review 时，25 个非 control targets 的逐文件 SHA 与 zero-change 记录完全一致。唯一允许漂移是 `docs/host/issues-implementation-control.md`：它由 Controller 在 zero-change validation 后执行 gate 状态更新；另新增 Controller fix validation 与两路 final re-review artifacts。没有 production/test/README/smoke/accepted plan/既有 implementation-review artifact 漂移。

## 3. 语义与传播最终裁决

两路证据与 Controller 源码复核一致：

1. `evidence.py` 是 opaque envelope/ref codec 的 internal owner，继续保留 `OpaqueEvidenceRef` 与 envelope refs；`accepted_result_projection.py`、`run_input.py`、`memory.py`、`compact_material.py`、`tool_trace.py` 五个 shared/consumer 文件不携带该类型，sentinel refs 不进入 LLM-facing material。
2. readable business source 只来自 digest-checked completed-success outcome 的 exact `result.value.citation` object；Host canonical-render 整个 object，不枚举 key、不猜测 ref、不发明 BusinessSource abstraction。
3. RunInput 的 `_memory_projection_event_from_row` / `_fallback_message_from_material_block`、Memory 的 `_selected_evidence_text` / durable view、Compact typed invariant / pipeline consumer、LLM-ready Tool Trace 均对 canonical material corruption fail closed，没有 skip、limited signal、fallback 或 consumer repair。
4. Tool Trace request 通过真实 EventLog row 与 `tool_call_request_atoms` 读取 exact canonical arguments/query；readable result 的 source text/state 与 shared projection 同源。
5. public-run smoke 使用真实 assembly/public submit 链；五个 exact calls、`TOOL_AWAITING` strict link/no-copy、same-ticker `list_documents` grounding 后的 `get_document_sections` citation read 均有 deterministic assembly guards。

## 4. Reviewer artifact correction 裁决

Controller 要求两路各自修正了记录性表述：

- MiMo：把 `evidence.py` 正确恢复为 internal ref owner；修正 RunInput/Memory helper 归属；把 16 个 §11.2 implementation paths 与 Controller control diff 分开。
- DS：修正 RunInput/Memory helper 归属及 Compact dataclass/consumer error boundary；把 16 个 §11.2 implementation paths 与 Controller control diff 分开。

这些 correction 只修改各自 final re-review artifact，verdict/findings 不变，不是新产品 finding，也不触发新 fix gate。

## 5. 验证与边界

最终链已具备以下独立绿色证据：

- accepted S3 matrix：`354 passed, 1 skipped, 3 warnings`
- propagation filter：`261 passed, 63 deselected`
- full Host：`1972 passed, 2 skipped, 5 deselected`（F05 smoke-only correction 前；F05 后 exact S3 matrix重跑）
- final re-review independent suites：DS `354 passed, 1 skipped` + filter `261 passed, 63 deselected`；MiMo `337 passed, 1 skipped`
- full pyright：`0 errors`
- changed production coverage：86%-96%；`evidence.py` branch coverage 91%
- Ruff、`git diff --check`、allowlist、no-diff owner、active source scans：PASS

Doc `allowed_paths`、Web network defense、path containment、symlink、DNS/peer/resource budget、atomic write、process fencing 与 Host durable integrity 均保留。没有实现统一 tool authorization framework；Issue 142、151、175、177、178 和 Web/WeChat/render tracker scope 未偷带。

accepted plan §12 的真实 provider/Web/Fins aggregate public-run smoke仍未运行、未标 skip/PASS；它继续阻塞 R03 aggregate completion，但不阻塞 S3 slice acceptance。

## 6. 下一 gate

Controller 授权创建 R03-S3 accepted local commit，提交范围必须精确包含本 slice production/tests/README/smoke、implementation/validation/review/fix/re-review/controller artifacts 与当前 control state，不得包含其它路径，不得 push。

accepted commit 后只能进入 R03 aggregate validation/deepreview gates。R03-S3 acceptance 不关闭 R03，更不关闭 umbrella `WU-SEMANTIC-OWNERSHIP-01`；R04 及后续 remediation sub-WU 仍未授权。
