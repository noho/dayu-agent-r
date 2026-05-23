# 会话压缩请求

请基于下面的 compaction request 生成一个严格 JSON 对象：

<<compaction_request>>

输出 JSON schema：

```json
{
  "episode_summary_candidate": {
    "episode_title": "non-empty text",
    "goal": "non-empty text",
    "completed_actions": ["text"],
    "confirmed_fact_refs": ["existing evidence_backed_fact_ref"],
    "confirmed_fact_summaries": ["text"],
    "user_constraints": ["text"],
    "open_questions": ["text"],
    "next_step": "text or null",
    "tool_finding_refs": ["accepted evidence ref"]
  },
  "pinned_state_patch_candidate": {
    "current_goal": {"operation": "missing|clear|replace", "value": "text or null"},
    "confirmed_subjects": {"operation": "missing|clear|replace", "value": ["text"] or null},
    "user_constraints": {"operation": "missing|clear|replace", "value": ["text"] or null},
    "open_questions": {"operation": "missing|clear|replace", "value": ["text"] or null}
  },
  "evidence_backed_fact_candidates": [
    {
      "candidate_id": "local id",
      "claim_text": "bounded text",
      "evidence_kind": "observed_value|quoted_statement|table_value|derived_from_evidence",
      "evidence_refs": ["accepted evidence ref"],
      "attributes": {}
    }
  ],
  "minimum_preserve_item_candidates": [
    {
      "item_id": "local id",
      "label": "short text",
      "text": "bounded text",
      "source_refs": ["input event ref"],
      "preserve_reason": "needed_for_recent_reference|needed_for_ordered_item_reference|needed_for_local_followup"
    }
  ],
  "retained_current_user_input_ref": "current user input ref from request",
  "preserved_input_event_refs": ["input event refs"],
  "preserved_accepted_evidence_refs": ["accepted evidence refs"],
  "preserved_evidence_backed_fact_refs": ["evidence-backed fact refs"],
  "dropped_ranges": [],
  "summarized_ranges": []
}
```

字段要求：
- `retained_current_user_input_ref` 必须等于请求里的 `current_user_input_ref`。
- `evidence_backed_fact_candidates[*].evidence_refs` 只能引用请求里的 `accepted_evidence_refs`。
- `preserved_accepted_evidence_refs` 必须包含所有被 fact candidate 引用的 evidence refs。
- `preserved_input_event_refs` 只能引用请求里的 `input_event_refs`，且必须包含 `current_user_input_ref`。
- `dropped_ranges` 和 `summarized_ranges` 默认输出空数组；除非能逐字复制请求里的 input refs 作为 range 边界，否则不要生成 range。
- 必须保留 open questions / working assumptions：`episode_summary_candidate.open_questions` 必须非空，或 `pinned_state_patch_candidate.open_questions` 使用 `replace` 且 `value` 非空。
- 如果输入没有显式疑问，但当前 Run 仍需要连续推进，open questions / working assumptions 应保留为“继续处理当前用户输入”这类短连续性项。
- 若没有可靠证据支撑新 fact，输出空 `evidence_backed_fact_candidates`，不得合成 fallback fact。
- minimum preserve item 只保留短链路追问所需的最小连续性内容，不保留整段长输入。
