# PR 190 F11/F12 S4.2 DS-F01 review fix

## Gate 与状态

- Gate：PR review `fix`。
- Work unit：PR 190 F11/F12 S4.2 accepted terminal payload。
- Controller 裁决：只修复 `DS-F01`。
- Completion status：`FIX_APPLIED_AWAITING_DUAL_REREVIEW`。
- Artifact path：`docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-f01-fix-20260805.md`。
- 未 commit、未 push、未调用 real provider、未调用 reviewer。

## Finding 与直接证据

`DS-F01` 成立。`DurableCompactArtifactProvider._load_compact_artifact_tx(...)` 已在 provider 的同一 read transaction 内读取最新 `CONTEXT_COMPACTED` row，但原实现调用 `_payload_object(row)`，只解析 EventLog hot `payload_json`。超限 terminal 的完整 canonical payload 由 `dayu.host.context_event_payload` 外置到 payload descriptor/blob，hot object 固定为 `{}`；因此后续 strict semantic parser 必然因 canonical 字段缺失而失败。

语义 owner 不变：`context_event_payload.resolve_context_compacted_payload(...)` 唯一负责从 inline 或 descriptor/blob 恢复并校验完整 accepted terminal payload；`parse_context_compacted_semantic_payload(...)` 继续唯一负责 typed compact semantic parsing。provider 只是遗漏的真实 consumer，不拥有新的 fallback 或兼容语义。

## Changed files

- `dayu/host/run_input.py`
  - `DurableCompactArtifactProvider._load_compact_artifact_tx(...)` 在当前 transaction 内复用 `resolve_context_compacted_payload(transaction, row)`。
  - strict semantic parser、compact artifact digest required-field 校验与返回 view contract 保持不变。
- `tests/host/test_run_input_builder.py`
  - 新增 descriptor-backed oversized owner test 与专用 durable seed helper。
  - 使用 2048-byte inline threshold 写入真实 artifact-backed `CONTEXT_COMPACTED`；断言 terminal descriptor kind/size、event ref、artifact ref/digest 和 represented evidence refs。
  - 篡改 EventLog terminal payload digest 后再次调用同一 provider，断言 strict resolver fail closed。
- `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-fix-20260805.md`
  - 将 implementation 状态更新为等待双路 re-review，并记录 DS-F01 fix 与验证结果。
- 本 artifact。

## Scope decision

- 只实现 controller accepted 的 `DS-F01`。
- `DS-F02` 至 `DS-F08` 均保持 `rejected-with-reason`，未修改 event id、filesystem rollback、Read API activity、rejected/failed terminal storage、PayloadStore 注入或 semantic builder size policy。
- 未增加 fallback、默认值、inline 特例、loose parser、compatibility shim 或第二真源。
- 未修改 real-provider wiring、oracle、scenario、registry 或 `dayu/host/context_events.py`。

## Tests 与 validation

- 定向 owner test：`1 passed in 0.44s`。
- 完整 `tests/host/test_run_input_builder.py`：`103 passed in 1.00s`。
- 受影响 regression：三组共 `798 passed`。
  - changed-test modules：`472 passed in 5.28s`。
  - compact material / terminal / proactive / memory / projection：`182 passed in 1.18s`。
  - compact contract / pipeline / artifact / operation / memory repair：`144 passed in 0.48s`。
- 全仓 pyright：`0 errors, 0 warnings, 0 informations`。
- changed-file `ruff check`：通过。
- `python -m compileall -q dayu tests utils`：通过。
- `git diff --check`：通过。

## Docs decision

已按触发规则检查 `dayu/host/README.md` 与 `tests/README.md` 的更新约束和当前 S4.2 diff。现有 Host README 已承诺 RunInputBuilder consumer 共用 accepted terminal strict resolver；现有 tests README 已记录 oversized descriptor/blob owner tests 与 digest drift fail-closed。DS-F01 只补齐遗漏 consumer 及其 owner test，不新增公共契约或测试层级，因此不再修改 README。

## Finding status

- `DS-F01`：`已修复`，待双路独立 re-review 验证。
- MiMo 首轮无实质 finding：保留原 review 结论，但需对完整修复后 diff re-review。
- `DS-F02` 至 `DS-F08`：controller `rejected-with-reason`，未实施。

## Residual risks 与下一入口

- 当前 fix 未发现未分类 residual risk。
- frozen real-provider bundle 仍是 partial/superseded evidence；按 controller 裁决，本 gate 不运行 real provider。
- 下一入口：由总控分别派发 MiMo、DeepSeek 对完整 S4.2 diff 进行独立 re-review；两路 accepted 前不得 commit/push，也不得重启 real-provider observation。
