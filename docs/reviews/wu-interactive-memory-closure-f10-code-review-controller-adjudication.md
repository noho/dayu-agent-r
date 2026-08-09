# F10 code review：总控逐项裁决

## Gate

- Work unit：Interactive Conversation Memory closure F08–F10
- Slice：F10
- Gate：implementation code review / fix / re-review
- 日期：2026-08-04
- 结论：**ACCEPTED / 可进入 accepted slice commit**

## Durable routes

- MiMo code review：`wu-interactive-memory-closure-f10-code-review-mimo.md`
- DS code review：`wu-interactive-memory-closure-f10-code-review-ds.md`
- Codex fix audit：`wu-interactive-memory-closure-f10-code-review-fix-codex.md`
- MiMo re-review：`wu-interactive-memory-closure-f10-code-rereview-mimo.md`
- DS re-review：`wu-interactive-memory-closure-f10-code-rereview-ds.md`

## Finding disposition

| Finding / observation | 总控裁决 | 直接依据 |
|---|---|---|
| MiMo：无 correctness / stability / ownership finding | 接受 | 独立 focused suite、类型检查及逐层数据流审查均通过；不能以该 PASS 代替下列逐项裁决。 |
| DS F1：evidence final-pack digest | 已关闭 | 单一 `_packed_content_digest` 区分 ordinary/evidence，并由 selection proof、ordinary/evidence pack 与 evidence provenance 直接复用；source digest 语义未改。 |
| DS F2：transient exact root subset | 已关闭 | 唯一 producer 只取 root proof；operation 对每个 id 做 exact-root-subset，并验证全体无重叠、无遗漏和每 pass pack。 |
| DS F3：excluded mapping 排序/不可变 | 已关闭 | constructor 先 key-sort copy，再以 `MappingProxyType` 保存；serialization/digest 使用同一 canonical order，mutation 反例被拒绝。 |
| DS F4：same-text dedup | 已关闭 | packer 不再 skip selected block；same-text/different-ref 保留；same current canonical ref 在 pipeline 与 operation provider 前失败。 |
| DS-1：operation 使用 refs/digest sorted multiset | `rejected-with-reason`，不构成当前 contract gap | source-snapshot owner 已按 block id/order 精确重建并比较 proof；operation 只拥有 final pack business multiset 与 pass partition，pack 不携带 block id。selected 内 A↔B proof 交换不改变 provider material、source boundary 或 durable semantic set；跨 selected/excluded 替换被现有校验拒绝。增加 label/section/ordinal 或新字段会违反 accepted minimal proof 边界。两路 re-review 均未找到可改变业务真源且通过 provider barrier 的反例。 |
| DS-2：transient snapshot validator 不单独接收 root selection | `rejected-with-reason`，不构成当前 contract gap | snapshot validator 拥有 source identity；唯一 transient producer 与 operation 拥有 root relationship。手工注入 root 未选 block 会在 per-id exact-root-subset 失败；向 snapshot validator 再传 root 会复制 owner。两路 re-review 均确认所有 provider path 被覆盖。 |
| initial selection 使用 prompt-local ids | accepted boundary | initial helper 明确没有 raw source snapshot，proof 直接来自 final pack，未与 recovery selection 混用；不是 schema alias 或 fallback。 |
| F09 hot-payload fixture migration | accepted | 只迁移 strict manifest contract 的真实 test fixture consumer；生产 resolver 未放松，未新增 compat 分支。 |

## Gate evidence

- Focused owner suite：337 passed，1 skipped；skip 为未启用的 real-compactor smoke。
- 完整 Host suite：2385 passed，1 skipped，6 deselected。
- Coverage owner suite：418 passed，1 skipped；六个修改 production owner 文件均为
  83%–92%，合计 85%。
- 全仓 pyright：724 files analyzed，0 errors / warnings / informations。
- F10 精确 Ruff、compileall、JSON validation、`git diff --check`：通过。
- 三份 frozen baseline digest 保持不变；五条正式 CLI scenarios 未运行。

## Residual classification

- DS-1 / DS-2 是 future-extension guardrail，不是当前 correctness residual。若未来增加绕过
  pipeline 的 request producer 或第二个 transient producer，则该新增路径的 Host owner 必须
  同时扩展现有 exact-proof barrier；当前 work unit 不预造兼容或冗余接口。
- 真实 provider 与五条正式 CLI scenarios：由后续 Oracle 总控 evidence/readiness gate
  覆盖。
- 全树 Ruff 基线债务：不属于本 work unit；F10 精确 pathspec 已 green。

没有 blocking open question，没有未分类 residual risk。F10 slice 可提交。
