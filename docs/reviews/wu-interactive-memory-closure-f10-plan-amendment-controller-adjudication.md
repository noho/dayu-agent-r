# F10 plan amendment：总控最终裁决

## Gate

- Work unit：Interactive Conversation Memory closure F08–F10
- Slice：F10
- Gate：blocked implementation 的 plan amendment review / fix / re-review
- 裁决日期：2026-08-04
- 结论：**ACCEPTED / implementation 可恢复**

## Durable review routes

- MiMo initial review：
  `wu-interactive-memory-closure-f10-plan-amendment-review-mimo.md`
- DS initial review：
  `wu-interactive-memory-closure-f10-plan-amendment-review-ds.md`
- 总控 fix：
  `wu-interactive-memory-closure-f10-plan-amendment-fix-controller.md`
- MiMo first re-review：
  `wu-interactive-memory-closure-f10-plan-amendment-rereview-mimo.md`
- MiMo accepted re-review：
  `wu-interactive-memory-closure-f10-plan-amendment-rereview2-mimo.md`
- DS first re-review：
  `wu-interactive-memory-closure-f10-plan-amendment-rereview-ds.md`
- DS accepted re-review：
  `wu-interactive-memory-closure-f10-plan-amendment-rereview2-ds.md`

前述 NEEDS_FIX artifact 均原样保留；后续 artifact 只关闭 finding，不覆盖原始证据。

## Finding-by-finding disposition

| Finding | 总控裁决 | 关闭依据 |
|---|---|---|
| DS F1：accepted evidence 的 RunInput digest 与 final-pack digest 不是同一语义 | 接受 | 改用 `packed_content_digest`；明确 `_packed_content_digest(block)` 的签名、ordinary/evidence 算法、四个调用点以及 source digest 不变。 |
| DS F2：transient proof subset 验证位置不清 | 接受 | `_single_block_segment_selection` 只能取 root entry；`_operation_pass_requests` 对每 pass 做 exact root subset，并验证全体无重叠、无遗漏；provider 前再核对自身 pack。 |
| DS F3：excluded mapping 的存储顺序、序列化和 digest 可能漂移 | 接受 | `__post_init__` 先 key-sort copy，再冻结只读 view；stored mapping、`to_json()`、selection digest 共用同一 canonical order。 |
| DS F4：same-ref 与 same-text dedup 边界不清 | 接受并收紧 | packer 不再删除任何 selected block；same-text/different-ref 保留；same canonical current ref 在 pipeline/provider 前 fail closed。 |
| MiMo first re-review F1：single helper 缺少可执行签名与调用点 | 接受 | fix artifact 已补充精确 helper contract、调用位置和端到端 owner test；MiMo re-review2 判定关闭。 |
| DS first re-review 对 partial implementation 的未完成项 | 作为后续 implementation review checklist 保留，不作为 plan finding | 该 artifact 将“计划尚未实施”误判为“计划不可执行”；DS re-review2 已纠正审查对象并确认 amendment 本身可生成代码。其列出的未完成代码项必须在 F10 code review 逐项复核。 |
| MiMo initial PASS 中未识别 evidence digest 转换差异 | 证据范围有限，不作为否定 DS 直接证据的理由 | 总控采用 DS 对四行 source render 与 `result_text` digest 差异的直接代码证据，已通过 fix 关闭。 |

## Accepted implementation contract

1. root selection 以稳定顺序持久化每个 selected block 的 id、canonical refs 与
   final-pack digest；proof 不进入 LLM-facing schema。
2. recovery transient selection 必须是同一 root proof 的精确分区，不能替换 singleton、
   拆分 turn group、重叠或遗漏。
3. selected history/evidence 不做文本 dedup；current anchor canonical ref 冲突是
   source/request invariant violation，必须在 provider 前失败。
4. repair feedback 同时绑定 immutable request digest 与 source-boundary digest；任一变化
   都清空旧 feedback。
5. turn-group completeness、budget boundedness、feedback binding 与 provider 前防御性校验
   均由 Host owner 保证；Memory projector、renderer、CLI 和 fixture 不做补偿。

## Stop-condition assessment

没有 frozen oracle、design truth 与正确 Host owner contract 无法同时满足的冲突；当前
没有 blocking open question。恢复 AgentCodex F10 implementation，之后仍须完整执行两路
code review、fix、re-review 和 accepted slice commit。
