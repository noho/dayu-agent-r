# WU-SEMANTIC-OWNERSHIP-01 / R06-S2 complete cumulative code re-review Controller adjudication

## 结论

`PASS / R06-S2 CUMULATIVE CHECKPOINT ACCEPTED`

AgentMiMo 与 AgentDS 对 `d048adf7ec1135aaf575384432ebf1137f8a34f2` 到当前 working tree 的完整 R06-S1+S2 累计代码均返回 `PASS / 0 material findings / 0 blocking questions`。Controller 接受两路结果，不创建中间 accepted commit；S1/S2/S3 仍是同一次 breaking cutover 的累计 checkpoints。

## Finding 最终状态

| Finding | 最终状态 | 裁决证据 |
| --- | --- | --- |
| `R06-S2-CR-F01` | `CLOSED` | `_resolve_primary_uri` 在唯一派生 owner 中只允许显式 primary 精确命中；missing/mismatch 返回 `None`，无 first-file fallback、caller compensation 或 validator weakening。 |
| `R06-S1-CR-F01` | `CLOSED / NO REGRESSION` | maintenance public read 仍为 outer publication guard + private unguarded I/O graph。 |
| `R06-S1-CR-F02` | `CLOSED / NO REGRESSION` | processed meta 只读取 `tool_snapshot_meta.json`，无虚构 fallback。 |
| `R06-S1-CR-F03` | `CLOSED / NO REGRESSION` | reprocess marker protocol/wrapper/core 统一 `-> None`，无死返回值消费者。 |

两路 observations 均不构成 accepted finding。尤其是 S3 producer residual、README 旧叙述和 full pyright 108 已由 accepted plan 明确分配给 R06-S3，不得在 S2 重复修复或作为兼容理由。

## 累计行为裁决

Controller 接受以下 S1+S2 contract 保持成立：

- registry-only explicit batch authority、opaque public token、writer mutex 与 publication guard 分离、published/private read graph、guarded delayed opener、minimal journal 与 recovery；
- blob-first source staging、final complete-source single mutation、storage-owned true completion、prepublication full-tree validator；
- source/files/primary/provenance/physical blob 与 filing/material manifest 双向一致；
- validator failure 消费 capability、old/absent published state 保持、长 staging/validator 不阻塞 reader、rename window 由 publication guard 排除；
- containment、symlink、atomic swap/recovery 等安全机制保持；无 ambient authority、first-file fallback、compat shim、统一 authorization 或 Issue 142/151/175/177/178 越界。

## 独立复审证据

- AgentMiMo：`235 passed`，scoped pyright `0`，scoped Ruff pass，`git diff --check` pass。
- AgentDS：`235 passed`，scoped pyright `0`，full pyright `108` 与 accepted S3 baseline 一致，`git diff --check` pass。
- Controller fix validation：`235 passed`，所有累计 S2 changed production line coverage `>=80%`，full baselines `108/160` 未新增或扩散。

## 下一 gate

下一 gate 仅为 accepted plan 的 R06-S3：迁移所有真实 producer/callback/composition root 到显式 shared-core batching，删除 ack/false-completion 残留，补齐测试与 README current contract，并把 full pyright 降为 0。不得重写 S2 validator，不得进入 R07、Issue 142/151/175/177/178 或统一 tool authorization。
