# UF-FIX11 Slice 1 slice-boundary blocker

## Gate 状态

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- 当前 gate：Slice 1 implementation blocked
- 决策：当前 gate 不可接受、不可提交
- 下一入口：`plan amendment`

## 确定性红测

Slice 1 完整 focused suite 结果为 `639 passed, 1 failed`。唯一失败：

`tests/fins/test_sec_pipeline_upload_filing_stream.py::test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision`

该测试期望同内容 fresh recheck 为 `skipped`，实际为 `ok`。

## 直接冲突证据

1. Accepted Slice 1 要求 fresh 不同名称即使没有新 alias 也生成
   `stage/preserve_published` intent；当前 `resolve_upload_company_meta_decision` 已按此产生
   `CompanyMetaCommitIntent.requested_company_name`。
2. 现有 `filing_upload_publication._canonical_skip_requirements_are_met` 明确要求 company decision
   同时为 `keep` 且 `company_meta_intent is None`；因此上述合法 name-only intent 必然阻止 canonical skip，
   使同内容 filing 进入 publish。
3. 让 SKIP 携带 metadata-only commit 属于 accepted Slice 2 的 owner/state-machine 变更；Slice 1 allowed files
   不含该 publication owner。修改测试期望、在 producer 丢弃 intent或提前重算 warning 都会违反冻结契约和单一 owner。

## 处置

现有 Slice 1 domain/storage/protocol/fake 改动可保留，供 plan amendment 后合并 Slice 1+2 原子实现；本轮不改测试期望、
不越界实施 Slice 2、不创建 implementation acceptance artifact、不 stage/commit。必须先修订 slice boundary，再恢复验证与 review。
