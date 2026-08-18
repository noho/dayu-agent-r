# UF-FIX03 S2 accepted slice

## 结论

UF-FIX03-S2（filing pre-publication admission、closed typed failure 与 canonical public label）已通过 implementation、双路 code review、finding 裁决、review-fix 与双路 re-review，结论为 **PASS**。

## 接受的契约

- filing 空文件在 converter 与 publication batch 前以 `content/empty_input_file` 拒绝。
- filing Docling conversion failure 在当前 original 文件边界映射为 closed content code、固定有界 message/retry hint，并保留内部 cause 仅供 operator log。
- valid+corrupt mixed input sequential fail-fast，整批不开始 batch、company/source stage 或 filing publication，terminal stored 为零。
- `FinsUploadFailureReason` 为 fresh exact five-field schema；`file_label` 无 default、可 null，并由 constructor 调用唯一 label validator。
- canonicalizer 对普通安全 basename 原样公开；fragment、`Cc/Cf` 与超过 240 的合法 basename 投影固定隐藏标签；pathful/empty/dot basename 在 static admission 以前置 closed usage fact 拒绝。
- workflow、runtime、durable/direct projection 只消费 typed reason，不从异常字符串重分类或重建 label。

## Review 证据

- 初始 reviews：
  - `docs/reviews/code-review-20260813-223608.md`
  - `docs/reviews/code-review-20260813-224126.md`
- 裁决：`docs/gateflow/uf-fix03-s2-code-review-adjudication-20260813.md`
- 修复：`docs/gateflow/uf-fix03-s2-review-fix-20260813.md`
- re-reviews：
  - `docs/reviews/code-review-20260813-225433.md`
  - `docs/reviews/code-review-20260813-225730.md`

两路 re-review 均为 PASS，无未裁决实质 finding。

## 验证

- S2 focused：`325 passed, 3 warnings`。
- S1 regression：`334 passed, 3 warnings`。
- changed-file coverage run：`1404 passed, 1 skipped, 1 deselected`；六个修改生产文件 87%–96%，aggregate 91%。
- pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`、old-field、constructor、no-touch 与 frozen SHA audit 通过。
- 未运行 UF-PF03；未修改冻结 JSON/evidence。

## 下一入口

本 slice 接受后进入 UF-FIX03-S3；S3 只完成 CLI bounded unknown stderr、direct no-artifact regression、README/documentation checks 与最终验证，不得重新实现 S2 typed owner。

