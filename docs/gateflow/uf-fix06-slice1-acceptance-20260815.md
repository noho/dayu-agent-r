# UF-FIX06 Slice 1 acceptance

## Gate 结论

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：1
- 日期：2026-08-15
- 结论：`SLICE ACCEPTED`
- 下一入口：implementation Slice 2

## 接受依据

- AgentCodex 已完成 capability owner 实现与 code review fix。
- 初轮 review：AgentMiMo `pass`；AgentDS `pass-with-risks`。
- Controller accepted F1/F2/O1/O2 均已修复。
- 最终双路 re-review：
  - `docs/reviews/code-re-review-slice1-mimo-20260815.md`：`pass`；
  - `docs/reviews/code-re-review-slice1-ds-20260815.md`：`pass`。
- 两路均确认既有 fallback、PDF options、独立输入流及首因/末因语义无回退。

## Accepted contract

- `DOCLING_CONVERTER_CAPABILITY` 冻结 9 个 format id 与 13 个有序 product suffix。
- 模块静态投影不 import Docling；converter construction 才 lazy 验证产品声明是
  `FormatToExtensions` 的子集。
- `DocumentConverter.allowed_formats` 与产品 format id 同源；非 PDF 使用 Docling constructor
  默认 format options，PDF 继续使用 Dayu 自定义 pipeline/backend 配置。
- Documents 层公开角色中立的 `product_suffixes` / `accepts_product_suffix`；predicate 对任意
  `str` 全定义，无有效 suffix 时返回 `False`。
- format id、mapping 或产品 suffix 缺失均 typed fail-fast，不回退默认全格式。

## 验证

- Focused tests：28 passed。
- Pyright：0 errors。
- Coverage：production 91%，test 99%。
- Ruff、Black、`git diff --check`：通过。
- 未执行 UF-PF06/UF-PF12；未修改 README、registry、oracle/scenario 或冻结 evidence。

Slice 1 blocking finding 为 0，允许进入 Slice 2。
