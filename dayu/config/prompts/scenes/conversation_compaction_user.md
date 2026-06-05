# 会话压缩请求

请基于下面的 compaction request 生成一个严格 JSON 对象：

<<compaction_request>>

输出 JSON schema：

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

字段要求：
- 顶层必须只输出上述 vNext 字段，不要输出 `candidate_id`、`episode_summary_candidate`、`pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preservation_evidence`、`stable_input`、`history_input` 或 `evidence_input`。
- `evidence_backed_facts[*].evidence_labels` 和 `source_labels` 只能引用请求里的 `E*` labels。
- 如果请求的 `evidence_material` 非空，必须为每个被保留的 evidence label 产出至少一个 `evidence_backed_facts` 条目；不得合成 fallback fact。
- `answer_anchors[*].answer_source_labels` 只能引用请求里的 `A*` labels。
- `forward_intents[*].source_labels` 与 `reference_continuity_items[*].source_labels` 只能引用 `P*`、`T*` 或 `A*` labels。
- `session_summary.source_labels` 可以引用 `P*`、`T*`、`E*`、`A*` labels，但不得引用 `C1`。
- 所有 source label 必须逐字复制请求中已有 label；不得生成旧 `H*` label 或任何不存在的 label。
- 如果没有足够来源支撑某类 candidate，输出对应空数组；不要用 diagnostics 替代必须保留的事实或连续性。
