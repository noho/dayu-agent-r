# WU-SEMANTIC-OWNERSHIP-01 / R06-S2 Controller validation

## 结论

`PASS / READY_FOR_DUAL_CUMULATIVE_CODE_REVIEW`

本 gate 只接受 R06-S2 为 S1/S2/S3 同一 breaking cutover 的累计 checkpoint，不创建中间 accepted commit，也不授权 S3。AgentCodex implementation artifact 为 `docs/reviews/wu-semantic-ownership-01-r06-s2-implementation-codex.md`。

## 独立代码复核

Controller 直接检查了 S2 七个 production owner 文件和四个 allowlist test 文件，确认：

- `SourceHandle` blob write 只依赖同 core、同 ticker、仍开放的显式 `BatchToken`；source blob-first 不再要求 preliminary meta，processed blob 仍由 processed meta 授权；
- `stage_source_document`、stable staging fields、acknowledgement re-entry 和 first-file primary fallback 已从 storage owner 删除；
- final source mutation 由 storage 覆盖 ticker/document/source-kind，强制 `ingest_complete=True`，显式 false fail closed，并复用 `SourceDocumentProvenance` 校验 ingest method/provider；
- `commit_batch` 在获取 publication swap guard 和任何 target rename 之前固定遍历完整 staged ticker tree；validator 不维护 touched set，也不从 processed/company/maintenance consumer 反推 source；
- validator 校验 source directory/meta identity、typed provenance、true completion、非空且唯一 files、URI/size/sha 与 contained non-symlink regular file、精确 primary、physical/files 双向一致，以及 filing/material source/manifest 双向 identity 与 exact projection；
- validator failure 走 storage-owned precommit restore，消费 capability 并保留 old；长 validator 不持 publication guard，published reader 仍及时读取 old；
- retained containment、symlink、writer/publication lock 分离、atomic swap/recovery 和 primary-error precedence 未被删除或放宽；未引入统一 authorization、R07 selector/snapshot 或 Issue 175/177 能力。

未发现需要在进入双路 cumulative code review 前修复的 Controller validation finding。

## 独立测试与覆盖率

Controller 在激活 `.venv` 后重跑四个累计 S1/S2 allowlist test files：

```text
232 passed, 3 warnings in 9.71s
```

三条 warning 均来自 `edgar` 依赖的既有 deprecation warning。

Controller 另建 coverage data 并重跑相同 232 tests。S2 实际 changed production 的 line coverage 为：

| File | Covered / statements | Line coverage |
| --- | ---: | ---: |
| `dayu/fins/domain/document_models.py` | 417 / 434 | 96.08% |
| `dayu/fins/storage/repository_protocols.py` | 59 / 59 | 100.00% |
| `dayu/fins/storage/_fs_storage_infra.py` | 727 / 813 | 89.42% |
| `dayu/fins/storage/_fs_blob_core.py` | 58 / 64 | 90.62% |
| `dayu/fins/storage/_fs_source_document_core.py` | 328 / 397 | 82.62% |
| `dayu/fins/storage/fs_document_blob_repository.py` | 20 / 20 | 100.00% |
| `dayu/fins/storage/fs_source_document_repository.py` | 72 / 77 | 93.51% |

全部达到单文件 80% 目标。

## 类型、风格与精确扫描

- scoped pyright（7 production + 4 tests）：`0 errors, 0 warnings, 0 informations`；
- scoped Ruff：`All checks passed`；
- full pyright：`108 errors` / 682 files，changed owner/test 命中 0；错误只位于 accepted plan 已列明的 S3 producer、producer tests 与 combined acceptance propagation；
- full Ruff：160，changed owner/test 命中 0，未高于当前 cumulative baseline；
- ambient authority scan：0；storage acknowledgement/false-completion owner scan：0；
- aggregate acknowledgement scan：35，精确归因于 S3 producer/tests、S3/final README 更新和两条 fail-closed owner tests；
- source owner fallback/compat scan：0；journal owner PID/hostname scan：0；
- staged paths：0；`git diff --check`：通过。

## README 与 residual

S2 是不可独立发布的中间 checkpoint。`dayu/fins/README.md` 和 `tests/README.md` 的旧 acknowledgement 描述必须在 S3 propagation 与 final cumulative contract 同步时删除；本 gate 不把中间态写成 current product contract。

当前唯一已知 gate residual 是 full pyright 108 及 aggregate acknowledgement 传播残留，owner/destination 均为 accepted R06-S3 producer propagation。它们未被隐藏、豁免或用兼容代码消除。下一 gate 仅为 AgentMiMo / AgentDS 对完整累计 S1+S2 tree 的并发 code review。
