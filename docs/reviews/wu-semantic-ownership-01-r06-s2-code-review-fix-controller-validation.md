# WU-SEMANTIC-OWNERSHIP-01 / R06-S2 code-review fix Controller validation

## 结论

`PASS / READY_FOR_DUAL_COMPLETE_REREVIEW`

Controller 接受 AgentCodex 对 `R06-S2-CR-F01` 的 owner-boundary 修复。当前仍是同一 umbrella WU 内的 R06-S2 累计 checkpoint；不创建中间 accepted commit，也不授权 R06-S3。

## 独立代码复核

Controller 直接检查了 `dayu/fins/storage/_fs_storage_utils.py::_resolve_primary_uri`、两个既有 production caller、新增 owner/public-contract tests 与 fix artifact，确认：

- primary name 缺失时返回 `None`；
- primary name 非空时只接受 file entry canonical name 的精确匹配；
- 显式 primary 未命中时返回 `None`，不再读取 `file_payloads[0]`；
- `_fs_source_document_core.py` 两个 caller 未增加补偿分支；
- complete-source commit validator 未放宽，错误 primary 仍在 publication 前 fail closed；
- public repository test 覆盖 old-absent / old-present 两格，验证错误 projection 为 `None`、commit capability 被消费、非法 source 不可见、已有 source 与 blob 保持；
- exact-match create 及既有 logical delete/restore 路径保持；未引入 loose parsing、兼容 shim、默认 primary 或统一 authorization。

`R06-S2-CR-F01` 的根因位于共享派生 owner，修复边界正确；没有把 durable publication qualification 与临时 `DocumentHandle` projection 混为同一 owner。

## 独立验证

所有命令均在 `source .venv/bin/activate` 后执行。

- 四个累计 S1/S2 allowlist test files：`235 passed, 3 warnings in 10.67s`；warning 仅为既有 `edgar` deprecation warning。
- line coverage（covered lines / statements）：`_fs_storage_utils.py 161/184 = 87.50%`；其余累计 S2 production owner 为 `82.62%`-`100%`，全部达到单文件 80% 目标。
- scoped pyright（8 production + 4 allowlist tests）：`0 errors, 0 warnings, 0 informations`。
- scoped Ruff：`All checks passed!`。
- full pyright：`108 errors`，与 accepted S2 baseline 一致；均位于已分配给 R06-S3 的 producer/callback/test propagation，当前 owner/test scope 为 0。
- full Ruff：`160`，规则分布仍为 `E402=66`、`F401=79`、`F541=3`、`F821=1`、`F841=11`；当前 scope 为 0。
- `file_payloads[0]` primary fallback scan：0；storage ambient authority scan：0；storage acknowledgement/false-completion scan：0。
- `git diff --check`：通过；staged diff：空。

## Finding 与 residual

- `R06-S2-CR-F01`：`FIXED / READY_FOR_REREVIEW`。
- R06-S1 的 `CR-F01..03` 与所有 validation findings 保持关闭，须由两路 complete cumulative re-review 再确认。
- full pyright 108 与 aggregate acknowledgement propagation 仍由 accepted R06-S3 owner 关闭；本 gate 不将其降级、隐藏或兼容。
- R07 snapshot/revision、Issue 142/151/175/177/178、README final contract、统一 authorization、push/PR 均未进入当前修复。

下一 gate 仅为 AgentMiMo / AgentDS 并发 complete cumulative S1+S2 re-review；reviewer 必须显式关闭 `R06-S2-CR-F01`，并复核 R06-S1 已关闭 findings 未回归。
