# UF-FIX07 Slice 3 acceptance

## Gate 结论

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Slice：3（collision-free asset publication / downstream primary consumption）
- 日期：2026-08-15
- 结论：`SLICE ACCEPTED`
- Base checkpoint：`3911c790`
- 下一入口：implementation Slice 4

## 接受依据

- AgentCodex 已完成 filing asset identity、原始文件名投影、derived 关联、authoritative primary 转换与下游消费的端到端实现。
- 初轮双路 review：
  - `docs/reviews/code-review-20260815-204338.md`：AgentMiMo `PASS`；
  - `docs/reviews/code-review-20260815-205240.md`：AgentDS 无 blocker / 中高严重度 finding，提出两项 LOW 与一项 portability residual。
- 主控接受两项 LOW 与 portability residual：修正文档异常契约、补 fresh-target 第 N 次 blob 写入失败的零发布测试、显式归一化测试路径。
- AgentCodex 已在 `docs/gateflow/uf-fix07-slice3-review-fix-20260815.md` 完成修复。
- 最终双路 re-review：
  - `docs/reviews/code-review-20260815-210310.md`：AgentDS `PASS`；
  - `docs/reviews/code-review-20260815-210350.md`：AgentMiMo `PASS`。
- 两路均确认全部 findings / residual 闭环，无新 finding、blocker 或未分类风险。

## Accepted contract

- filing original asset identity 由 normalized absolute input path 经带版本域分隔的完整 SHA-256 唯一产生，同时以
  `original_filename` 保留用户可理解的原文件名投影；不同路径的相同 basename、相同 stem 的不同后缀不会覆盖或混淆。
- derived asset identity 只从对应 primary original identity 派生，并通过 `derived_from` 明确关联；禁止按 basename、stem、
  文件系统顺序或已生成文件反推关联。
- `FinsUploadFilingFiles.primary_file` 是唯一 primary 事实；publication 只转换该文件一次，companions 仅原样保存且不产生
  converted/process 语义。
- filing source fingerprint 排除 path-derived identity，但保留业务可见文件名、内容 hash、size 与 source；移动目录不触发
  虚假更新，改名或内容变化仍触发 update。
- request-local identity collision 在 converter 与 batch mutation 前 fail closed。
- snapshot、process 与 read 链路只消费 storage publication 中的 exact derived primary bytes，不从输入顺序或文件名重建 primary。
- 100 个 originals 可原子发布为 100 个 originals + 1 个 primary derived；conversion、任一 blob staging、final source 或 commit
  失败时 fresh target 均保持零发布，existing target 保持原树不变。
- material 路径保持 UF-FIX06 的既有 capability/companion contract，不泄漏 filing-only metadata。

## 验证

- Affected tests：630 passed，1 skipped，3 warnings。
- Targeted pyright：0 errors。
- `dayu/fins/pipelines/docling_upload_service.py` 覆盖率：86%。
- `git diff --check`：通过。
- 未执行 UF-PF07/UF-PF12 或真实 CLI evidence；未修改 README、registry、oracle/scenario 或冻结 evidence。

Slice 3 blocking finding 为 0，允许进入 Slice 4。旧 basename-based source 的自动修复、并发 writer 与 fresh company meta
warning 分别保留给 UF-FIX08、UF-FIX10、UF-FIX11；README 同步与最终全量验证由 accepted Slice 4 负责。
