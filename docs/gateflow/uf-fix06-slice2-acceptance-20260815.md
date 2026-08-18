# UF-FIX06 Slice 2 acceptance

## Gate 结论

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：2
- 日期：2026-08-15
- 结论：`SLICE ACCEPTED`
- 下一入口：implementation Slice 3

## 接受依据

- AgentCodex 已完成 Fins role owner、静态消费者迁移与 accepted A1-A5 code review fix。
- 初轮 review：AgentMiMo `pass`；AgentDS `pass-with-risks`。
- Controller 接受并要求修复 LLM-facing files 规则、240 字符 usage invariant、material CLI
  docstring、`.json` candidate 限定与无关格式化 churn。
- 最终双路 re-review：
  - `docs/reviews/code-re-review-slice2-mimo-20260815.md`：`pass`；
  - `docs/reviews/code-re-review-slice2-ds-20260815.md`：`pass`。
- 两路均确认 A1-A5 已闭环、blocking finding 为 0、delete + files 历史行为未越权改变。

## Accepted contract

- `FinsUploadFormatCapability` 仅投影 Slice 1 converter capability；primary/material 精确使用 13 个
  suffix，`.xsd` 仅为 filing companion-only overlay。
- `FinsUploadFilingFiles` 与 `FinsUploadMaterialFiles` 提供非空 upsert 和 typed delete empty；
  validated filing request 的 `file_selection` 必需且非 Optional。
- batch 只消费 `accepts_primary`，13 个 suffix 各自产生 standalone command；legacy、ZIP、`.xsd`
  与未选择第三方扩展稳定 skip，不做 companion 归组。
- CLI filing help 与 upload tool schema 消费同一静态 projection，自足说明 primary/companion/
  material 转换要求、files required/forbidden、XML/JSON candidate 限定及 suffix 不保证内容成功。
- 格式错误保留 canonical、path-free `file_label`；message 始终不超过 240 字符；usage public fact
  自身 fail-fast 校验 closed code union、非空和长度上界。
- 模块导入不加载第三方 Docling；旧 `FINS_UPLOAD_FILE_SUFFIXES` 已删除且无 Python 引用。

## 验证

- Focused tests：1030 passed，3 个既有 edgar deprecation warnings。
- Changed-file Pyright：0 errors。
- Changed production coverage：单文件 86%–99%，总计 92%。
- Ruff、Black changed-range checks、`git diff --check`：通过。
- 未执行 UF-PF06/UF-PF12；未修改 README、registry、oracle/scenario、design doc、冻结 evidence
  或 Slice 3 文件。

## Residual classification

- Service typed selection、旧 `SUPPORTED_UPLOAD_SUFFIXES` 删除与 workflow 转换行为：Slice 3。
- README 职责更新：Slice 4。
- delete + files 历史不一致：用户明确排除的其它 upload work unit。
- batch association、显式 primary、重复与 collision：UF-FIX07/后续 work unit。

Slice 2 blocking finding 为 0，允许进入 Slice 3。
