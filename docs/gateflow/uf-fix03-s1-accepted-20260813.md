# UF-FIX03 S1 accepted slice

## 结论

UF-FIX03-S1（publication-owned requested/stored count contract）已通过 implementation、双路 code review、finding 裁决、review-fix 与双路 re-review，结论为 **PASS**。

## 接受的业务契约

- 请求文件数由 request owner 提供；实际存储数只在 publication commit 成功后由 publication result 提供。
- 只有成功存储的 user-input original 文件计入 `stored_file_count`；Docling 派生文件不计入。
- `ok` 要求 stored 与 requested 一致且至少为一；`skipped/deleted/cancelled/failed` 的 stored 必须为零。
- durable summary 与 direct RESULT 只消费同一 typed summary；progress 的既有 `file_count` 与 fingerprint canonical bytes 不变。
- material 仅完成共享 required count 的机械迁移，没有改变其既有 failure 或 publication 行为。
- workflow 中不可达的重复 conversion-cancelled catch 已删除；cancellation typed owner 保持在 `DoclingUploadService`。

## Review 证据

- 初始 reviews：
  - `docs/reviews/code-review-20260813-213823.md`
  - `docs/reviews/code-review-20260813-214459.md`
- 裁决：`docs/gateflow/uf-fix03-s1-code-review-adjudication-20260813.md`
- 修复：`docs/gateflow/uf-fix03-s1-review-fix-20260813.md`
- re-reviews：
  - `docs/reviews/code-review-20260813-215907.md`
  - `docs/reviews/code-review-20260813-220018.md`

两路 re-review 均为 PASS，无未裁决实质 finding。

## 验证

- focused pytest：`286 passed, 3 warnings`；warnings 为既有第三方弃用提示。
- pyright：`0 errors, 0 warnings, 0 informations`。
- 修改生产文件 aggregate coverage：88%；`cn_pipeline.py` 69% 的剩余缺口均为既有未修改分支，已分类为后续测试覆盖风险。
- `uploaded_files` Python 残留为零；constructor inventory 为 summary 4 点、operation 4 点、pipeline parser 1 点。
- `git diff --check` 通过；冻结 JSON SHA 未变化；未运行 UF-PF03。

## 下一入口

本 slice 接受后进入 UF-FIX03-S2；S2 不得修改本 slice 已接受的 count owner contract。

