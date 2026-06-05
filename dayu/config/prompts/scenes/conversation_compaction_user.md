# 会话压缩请求

请基于下面的 compaction request 生成一个严格 JSON 对象：

<<compaction_request>>

输入 JSON 说明：
- 顶层是一个 JSON object，所有顶层字段都是必填字段。
- `schema_version`：JSON string。输入数据格式标识，只用于识别本次请求的数据形态，不是业务事实。
- `previous_compacted_view`：JSON object 或 null。此前已整理出的可读记忆；为 null 表示没有此前记忆。
- `previous_compacted_view.session_summary`：JSON string 或 null。此前会话摘要。
- `previous_compacted_view.evidence_backed_facts`：JSON array。每个元素包含 `source_label`、`claim_text`、`evidence_kind`，表示此前保留的证据支撑事实。
- `previous_compacted_view.answer_anchors`：JSON array。每个元素包含 `source_label`、`anchor_title`、`anchor_items`，表示此前回答中的可复用结论。
- `previous_compacted_view.forward_intents`：JSON array。每个元素包含 `source_label`、`intent_type`、`text`、`status`，表示此前对下一步的开放意图。
- `previous_compacted_view.reference_continuity_items`：JSON array。每个元素包含 `source_label`、`text`、`reason`，表示后续代词、序号或省略表达需要承接的上下文。
- `trace_material`：JSON array。每个元素包含 `source_label`、`trace_kind`、`text`。`trace_kind` 允许值为 `user_input`、`assistant_final_answer`、`user_visible_run_state`。
- `evidence_material`：JSON array。每个元素包含 `source_label`、`tool_name`、`query_text`、`response_text`、`source_note`。`query_text` 与 `source_note` 可以为 JSON string 或 null；`response_text` 是可用于生成事实的证据文本。
- `answer_material`：JSON array。每个元素包含 `source_label`、`answer_text`，表示此前助手最终回答文本。
- `current_input_anchor`：JSON object，包含 `anchor_label` 与 `text`。它帮助理解当前用户输入，但其 `anchor_label` 不允许出现在任何输出 label 列表中。
- `instruction`：JSON object，包含 `output_schema_name` 与 `compact_goal`。它说明本次整理目标；不要把该字段内容当成财报事实。

label 规则：
- label 是本次请求内的引用标签，只能逐字复制输入里已有的 `source_label` 或 `anchor_label`；不要生成不存在的 label。
- label 只说明“输出内容来自哪段输入”，不是业务事实、财报事实、用户意图或结论。
- 不要引用 `current_input_anchor.anchor_label`。
- `evidence_material` 的 label 通常形如 `E1`；`answer_material` 的 label 通常形如 `A1`；其它可引用材料的 label 可能形如 `P1` 或 `T1`。具体以本次输入实际出现的 label 为准。

输出 JSON 字段：
- 顶层必须是 JSON object，且必须只包含 `schema_version`、`session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`。
- `schema_version`：必填 JSON string，唯一允许值为 `conversation_compact_output_v1`。
- `session_summary`：必填 JSON object 或 null。有足够来源时输出 object；没有足够来源时输出 null。
- `session_summary.summary_text`：当 `session_summary` 为 object 时必填，JSON string，简短概括仍需保留的会话状态。
- `session_summary.source_labels`：当 `session_summary` 为 object 时必填，JSON string array。只能引用 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material` 中的 label。
- `evidence_backed_facts`：必填 JSON array。每个元素是一条被证据文本直接支撑的事实；没有足够证据时输出空数组。
- `evidence_backed_facts[*].claim_text`：必填 JSON string，只写可由证据文本支撑的事实。
- `evidence_backed_facts[*].evidence_labels`：必填 JSON string array，必须非空，只能引用 `evidence_material` 中的 label。
- `evidence_backed_facts[*].evidence_kind`：必填 JSON string，允许值为 `tool_result`、`tool_source_text`、`accepted_evidence_material`。
- `evidence_backed_facts[*].source_labels`：必填 JSON string array，只能引用 `evidence_material` 中的 label；无法补充时可为空数组。
- `answer_anchors`：必填 JSON array。每个元素保留此前回答中后续可能被“刚才的结论”等表达引用的内容；没有足够来源时输出空数组。
- `answer_anchors[*].anchor_title`：必填 JSON string，短标题。
- `answer_anchors[*].anchor_items`：必填 JSON array，必须非空。
- `answer_anchors[*].anchor_items[*].display_text`：必填 JSON string，回答中的可复用条目。
- `answer_anchors[*].anchor_items[*].ordinal`：必填 JSON number 或 null；有明确序号时填非负整数，否则填 null。
- `answer_anchors[*].answer_source_labels`：必填 JSON string array，必须非空，只能引用 `answer_material` 中的 label。
- `forward_intents`：必填 JSON array。每个元素记录仍需后续处理的开放事项；没有足够来源时输出空数组。
- `forward_intents[*].intent_type`：必填 JSON string，允许值为 `next_step_note`、`open_question`、`pending_clarification`、`pending_user_visible_task`。
- `forward_intents[*].text`：必填 JSON string。
- `forward_intents[*].status`：必填 JSON string，允许值为 `open`、`blocked`、`superseded`。
- `forward_intents[*].source_labels`：必填 JSON string array，必须非空，只能引用 `previous_compacted_view`、`trace_material`、`answer_material` 中的 label。
- `reference_continuity_items`：必填 JSON array。每个元素保留后续理解本地指代、序号指代、省略或近期状态所需的信息；没有足够来源时输出空数组。
- `reference_continuity_items[*].text`：必填 JSON string。
- `reference_continuity_items[*].reason`：必填 JSON string，允许值为 `local_reference`、`ordinal_reference`、`ellipsis_recovery`、`recent_state`。
- `reference_continuity_items[*].source_labels`：必填 JSON string array，必须非空，只能引用 `previous_compacted_view`、`trace_material`、`answer_material` 中的 label。
- `diagnostics`：必填 JSON array。仅在无法按要求整理某段输入且需要说明原因时使用；不要用它替代应保留的事实、回答锚点、后续意图或指代连续性。
- `diagnostics[*].code`：必填 JSON string，使用简短小写代码。
- `diagnostics[*].text`：必填 JSON string，说明问题。
- `diagnostics[*].source_labels`：必填 JSON string array，可为空；只能引用 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material` 中的 label。

输出 JSON 最小示例：

```json
{
  "schema_version": "conversation_compact_output_v1",
  "session_summary": {
    "summary_text": "non-empty text",
    "source_labels": ["P1", "T1", "E1", "A1"]
  },
  "evidence_backed_facts": [
    {
      "claim_text": "bounded text",
      "evidence_labels": ["E1"],
      "evidence_kind": "tool_result|tool_source_text|accepted_evidence_material",
      "source_labels": ["E1"]
    }
  ],
  "answer_anchors": [
    {
      "anchor_title": "short title",
      "anchor_items": [
        {"display_text": "bounded answer item", "ordinal": null}
      ],
      "answer_source_labels": ["A1"]
    }
  ],
  "forward_intents": [
    {
      "intent_type": "next_step_note|open_question|pending_clarification|pending_user_visible_task",
      "text": "bounded text",
      "status": "open|blocked|superseded",
      "source_labels": ["T1"]
    }
  ],
  "reference_continuity_items": [
    {
      "text": "bounded text",
      "reason": "local_reference|ordinal_reference|ellipsis_recovery|recent_state",
      "source_labels": ["T1"]
    }
  ],
  "diagnostics": []
}
```

保留规则：
- 如果 `evidence_material` 非空，必须为每个确实需要保留的 evidence label 产出至少一个 evidence_backed_facts 条目；不得合成无证据事实。
- 所有输出文本都必须简洁、有界，只保留后续对话需要继续使用的信息。
- 如果没有足够来源支撑某类内容，输出对应空数组或 null。
