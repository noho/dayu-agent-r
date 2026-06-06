# WU-TOOLS-01 External Blocker Reconciliation Controller Adjudication

Gate: external blocker / residual reconciliation
Work unit: WU-TOOLS-01
Status: PASS-WITH-DEFERRED-HOST-BLOCKER

## 输入

- `docs/reviews/wu-tools-01-external-blocker-reconciliation-codex.md`
- `docs/reviews/wu-tools-01-external-blocker-reconciliation-review-mimo.md`
- `docs/reviews/wu-tools-01-external-blocker-reconciliation-review-ds.md`

## 裁决

MiMo 与 DS review 均为 PASS。Controller 接受本轮 reconciliation。

## Blocker 处理结果

- `WU-TOOLS-01-S6-R2` effective execution config one-system-message mismatch：closed。测试断言已同步到当前 accepted one-system-message production semantics，验证原 system prompt 仍位于 `Task Instructions`，并验证 `Execution Guidance` 与 no-tool guidance。
- `WU-TOOLS-01-S6-R3` wait / resume accepted-result text mismatch：closed。测试断言已同步到当前 resume guidance 业务语义，验证 tool name、completed resolution 与结果内容，并不再要求 LLM-facing text 暴露 `wait_id`。
- `WU-TOOLS-01-S6-R1` proactive compaction manifest ref failures：deferred-with-owner。直接根因不是“普通 generic compactor”和“prepared fake compactor”的二分；当前代码也不存在需要按该二分迁移的 `PreparedFakeContextCompactor` 真源。更准确的判断是：WU-CM-01 已把 ConversationMemory / Compact 升级到 accepted compact outcome 必须回指 durable proposal manifest ref / digest，而 Host proactive scheduler tests 仍沿用升级前的 fake compaction seam，导致测试路径没有履行当前 compact closeout contract。该问题需要 Host compactor seam / WU-CM-01 follow-up owner 裁决测试夹具与调度器测试边界，不在 WU-TOOLS provider migration scope 内用测试替身绕过。

## WU-TOOLS-01-S6-R1 修复方案

保持状态为 `deferred-with-owner`。后续 owner 应按以下方案关闭：

1. 保持 `dayu/host/dispatch.py` 中 accepted compaction 缺少 proposal manifest ref / digest 时 fail closed 的生产行为，不放宽、不绕过。
2. 以当前 `CompactorProposalPreparedCompactor` contract 为测试 seam 真源，新增或抽取一个 deterministic manifest-producing Host test compactor；可参考现有 focused tests 中的 prepared manifest compactor 形态。
3. 将 7 个 proactive scheduler compaction 失败测试从旧 fake compaction seam 迁移到 manifest-producing seam，使测试输入与 WU-CM-01 后的 ConversationMemory / Compact contract 同源。
4. 为 accepted compact event 明确断言 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest`，为 rejected attempt event 明确断言 `proposal_manifest_ref` / `proposal_manifest_digest`。
5. 复跑 broad Host validation；只有 proactive compaction manifest-ref 失败消失且没有新增 pyright / import-boundary regressions 时，关闭该 residual。

## Controller 验证

- 11 项 targeted 复测：7 failed, 4 passed；剩余 7 项全部为 `WU-TOOLS-01-S6-R1`。
- `source .venv/bin/activate && pyright`: 0 errors, 0 warnings, 0 informations。
- `git diff --check`: clean。

## 下一步

更新总控文档，将 `WU-TOOLS-01-S6-R2` 与 `WU-TOOLS-01-S6-R3` 从 active residual 中关闭，将 `WU-TOOLS-01-S6-R1` 标记为 deferred-with-owner。WU-TOOLS-01 provider migration 本身已完成；draft PR 前仍需确认 deferred Host blocker 是否允许带 owner 进入 PR，或转入独立 Host follow-up。
