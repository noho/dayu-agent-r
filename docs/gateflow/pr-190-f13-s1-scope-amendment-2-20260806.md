# PR 190 F13 S1 Scope Amendment 2

## Trigger and direct evidence

第一次amendment的scan聚焦被删除Python symbols；实现期对schema literals做独立扫描后发现一处active漏项：

- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:1096`构造`dayu.context_compaction.input.v3`。
- 同文件`:1120`断言helper输出`dayu.context_compaction.output.v3`，root exact keys也缺required retain selector。
- 被测对象是已进入S1 helper scope的`utils/smoke_host_public_conversation_memory_scenarios.py`；helper切到v4后，该配套test若不机械迁移会失败。

另有`tests/service/test_host_assembly.py:335-336`只断言v3 schema不出现在system prompt中，属于fresh contract negative assertion，不是active reader/fixture，不需要修改。除Host allowed tests正在迁移的schema-4断言外，`tests/`未发现其它active v3 literal。

## Amendment

- S1 allowed tests新增上述runtime test，仅迁移input/output schema、required selector与exact key断言，不扩展runtime业务语义。
- residue rule从“任何字符串零命中”精确为“active v3 contract零命中”；明确reject/absence negative assertions可保留，并在C3 artifact列明。

## Goal and owner impact

Goal、production owner、schema、S1/S2边界与single atomic commit均不变；不新增compatibility、alias或测试专用生产分支。这是随已接受utils helper机械迁移的配套test scope completeness修正。

## Gate state

`accepted`。两位原plan reviewer均确认：该runtime test是已纳入S1的utils smoke helper的配套active v3 consumer；迁移仅限schema、required selector与exact-key断言；service层两条v3命中是应保留的negative absence assertions。DS指出的smoke helper缺required selector属于既有S1实现遗漏，已纳入实现修复，不阻塞本amendment。

Review evidence：

- `docs/reviews/plan-review-20260806-f13-s1-scope2-mimo.md`
- `docs/reviews/plan-review-20260806-f13-s1-scope2-ds.md`
