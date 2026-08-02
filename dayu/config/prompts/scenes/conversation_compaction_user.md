# 会话压缩请求

请根据下面的输入生成一个完整 replacement candidate。只输出一个严格 JSON object，不输出 Markdown、注释或解释。

<<compaction_request>>

输入 schema：

- 顶层必须只含 `schema`、`current_input`、`source_boundary`。
- `schema` 必须为字符串 `dayu.context_compaction.input.v2`。
- `current_input` 必须是只含 `readable_text` 的 object。它是本轮必须保留的当前输入，只帮助理解任务；它没有 source label，不能被输出引用，也不参与覆盖。
- `source_boundary` 必须是 array。每项只含：
  - `source_label`: 非空字符串，仅是本次请求内的引用标签，不是业务事实。
  - `source_kind`: 字符串，只可能为 `previous_session_summary`、`previous_evidence_fact`、`previous_answer_anchor`、`previous_forward_intent`、`previous_reference_continuity`、`trace_material`、`evidence_material`、`answer_material`。
  - `readable_text`: 非空字符串，说明该 source 的业务可读内容。

输出必须完整且只含以下字段；全部字段必填：

- `schema`: 字符串，必须为 `dayu.context_compaction.output.v2`。
- `session_summary`: null，或只含 `text`、`source_labels` 的 object。
  - `text`: 非空字符串。
  - `source_labels`: 非空字符串 array。
- `evidence_facts`: array；每项只含：
  - `claim`: 非空字符串。
  - `support_labels`: 非空字符串 array，只能引用 kind 为 `evidence_material` 或 `previous_evidence_fact` 的 source。
  - `context_labels`: 字符串 array，可空，只能引用 kind 为 `trace_material` 或 `answer_material` 的 source。
- `answer_anchors`: array；每项只含：
  - `title`: 非空字符串。
  - `detail`: 非空字符串。
  - `source_labels`: 非空字符串 array，只能引用 kind 为 `answer_material` 或 `previous_answer_anchor` 的 source。
- `forward_intents`: array；每项只含：
  - `intent_type`: 非空字符串。
  - `text`: 非空字符串。
  - `status`: 字符串，只能为 `open`、`blocked`、`superseded`。
  - `source_labels`: 非空字符串 array，只能引用 kind 为 `trace_material`、`answer_material` 或 `previous_forward_intent` 的 source。
- `reference_continuity`: array；每项只含：
  - `text`: 非空字符串。
  - `reason`: 非空字符串。
  - `source_labels`: 非空字符串 array，只能引用 kind 为 `trace_material`、`evidence_material`、`answer_material` 或 `previous_reference_continuity` 的 source。
- `diagnostics`: array；每项只含：
  - `code`: 非空字符串。
  - `message`: 非空字符串。
  - `source_labels`: 字符串 array，可空。diagnostics 只解释问题，不代表 source 已被保留。
- `explicitly_dropped_sources`: array；每项只含：
  - `source_label`: 非空字符串。
  - `reason`: 字符串，只能为 `superseded`、`redundant`、`out_of_scope`、`policy_limit`。

覆盖规则：

- 每个 `source_boundary[*].source_label` 必须恰好走一条路径：被至少一个业务语义项引用，或在 `explicitly_dropped_sources` 中出现一次。
- 业务语义项仅指 `session_summary`、`evidence_facts`、`answer_anchors`、`forward_intents`、`reference_continuity`；`diagnostics` 不算覆盖。
- 不得引用输入中不存在的 label，不得在单个 label array 内重复，不得同时保留和丢弃同一 source。
- 输出空业务语义、仅 diagnostics、全部 source 都丢弃、低信息复述、重复业务项或相互矛盾项都会被拒绝。
- 只保留后续对话需要的信息；不得发明输入中没有的事实、偏好、结论或任务。

如果请求末尾包含 `repair_feedback`，它是前一次完整 candidate 的脱敏校验报告。按其中的 `code`、`json_path`、`message` 修复，但必须从同一份输入重新生成整个 JSON object：它不是 patch，不得沿用、拼接或补写前一次输出的任何部分。

最小形状示例：

```json
{
  "schema": "dayu.context_compaction.output.v2",
  "session_summary": {"text": "已确认下一步分析目标", "source_labels": ["T1"]},
  "evidence_facts": [],
  "answer_anchors": [],
  "forward_intents": [],
  "reference_continuity": [],
  "diagnostics": [],
  "explicitly_dropped_sources": []
}
```
