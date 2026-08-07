# PR 190 F17 Aggregate Review Adjudication

## Review inputs

- AgentDS：`docs/reviews/code-review-20260807-150010.md`，aggregate scope 正确，0 findings。
- AgentMiMo：`docs/reviews/code-review-20260807-150018.md`，产品结论为 0 findings，但 evidence
  inventory 含两条 stale claim。

## F17-A1：aggregate artifact 误用上一 gate 的 working-tree 状态

- 裁决：`accepted`
- 严重程度：低（evidence correctness；不影响产品 bytes）
- 直接证据：
  - artifact 第 56 行声称 `git diff HEAD --numstat` 有 2 个产品/测试文件，各 1/1；aggregate
    开始前两行变更已提交于 `305c1012`，因此 `git diff HEAD` 对这些文件应为空。
  - artifact 第 58 行声称唯一 untracked 文件是 implementation artifact；该 artifact 已随
    `305c1012` 提交。aggregate 取证完成后的实际 untracked 文件是两份 aggregate review
    artifacts。
  - 正确 committed scope 是
    `git diff e1217811ad57e48c90e3763994930e53378ba060..HEAD`：14 files，
    其中 2 个 product/test files 与 12 个 Gateflow evidence files，1236 insertions / 2 deletions。
- 修复要求：AgentCodex 只修正该 artifact 的 aggregate diff/untracked 描述，并明确 review 的
  committed base/head 时点；不得修改产品、测试、其它既有 review 结论或用当前变化的工作树状态
  冒充历史 review 时点。

## Gate decision

F17 产品实现与 publication truth 暂无 code finding，但 aggregate gate 在 F17-A1 修复并经
AgentMiMo/AgentDS 双路 re-review 前不接受。不得提交或 push。
