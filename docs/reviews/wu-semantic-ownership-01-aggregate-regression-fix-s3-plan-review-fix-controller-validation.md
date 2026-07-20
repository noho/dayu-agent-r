# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Plan-review Fix Controller Validation

## Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` continuation；不是新 WU。
- Gate：AgentCodex corrected-plan review fix 后的 Controller validation。
- Final plan SHA-256：`e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`。
- Updated correction artifact SHA-256：`f7500f03c9b8b703690c78e81cc75af3c15077b3e8e699757fec226345065c09`。
- Fix artifact SHA-256：`1bce1c0b3db1719dbe59b02c46162d4af5339a46948422469a01511fce790eb0`。

## Validation

Controller逐项确认：

- `CF01`：root ref使用`_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"`与typed `cref`在resolve前处理；没有扩大`RuntimeError`catch或添加warning/log/raw parser。
- `CF02`：`cref`/`$ref` Python/serialized alias边界明确。
- `CF03`：page fixture使用真实`ProvenanceItem`与`BoundingBox`，经serialize/load和public view。
- `CF04`：单空格/case-sensitive规则有直接数据模型与业务保真理由，无标点猜测/casefold/Unicode新框架。
- `CF05`：coverage前exact collect-only必须唯一收集AR-F06 node，否则STOP。
- Rejected/no-action proposals均未进入plan。

Plan-only fix没有新增production/tests/README/utility mutation；六个Slice 3 test locks及Controller/reviewer artifacts保持；`git diff --check`通过，staged tree为空。

```text
PASS / CF01_CF05_FIXED_IN_PLAN / READY_FOR_DUAL_COMPLETE_PLAN_REREVIEW
```

下一gate只授权AgentMiMo/AgentDS对完整final plan双路complete re-review；不得implementation、stage、commit、code review、aggregate、push、PR或closeout。
