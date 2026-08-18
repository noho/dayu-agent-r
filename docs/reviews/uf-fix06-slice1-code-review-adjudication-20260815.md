# UF-FIX06 Slice 1 code review Controller 裁决

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：1
- 日期：2026-08-15
- 输入：
  - `docs/reviews/code-review-slice1-mimo-20260815.md`：`pass`
  - `docs/reviews/code-review-slice1-ds-20260815.md`：`pass-with-risks`
- 结论：`CODE FIX REQUIRED`
- 下一入口：AgentCodex Slice 1 code review fix

## Controller 裁决

| ID | 来源 | 裁决 | 必须落实的修复 |
| --- | --- | --- | --- |
| F1 | AgentDS low | accepted | Documents capability 必须保持角色中立。把 `primary_suffixes` / `accepts_primary_suffix` 改为 `product_suffixes` / `accepts_product_suffix`，同步 tests 与 implementation artifact；不得保留兼容 alias/re-export。 |
| F2 | AgentDS low | partially accepted | 接受并补齐 `FormatToExtensions` 整项缺失的 typed fail-fast owner test；另补最小声明不变量测试：空 suffix/空 formats/重复 format id/跨格式重复 suffix。无需为每个等价 ValueError 分支堆机械 case，逐文件 coverage 仍须 >=80%。 |
| O1 | AgentDS open question | accepted | admission predicate 是跨层共享的查询 API，必须对任意 `str` 全定义：空白、空串、`.` 均返回 `False`，不得抛 `ValueError`。严格 normalization helper 仍可对非法声明抛 `ValueError`；predicate 在 owner 内先识别无有效 suffix。补空串、空白、`.`、无 suffix/dotfile 等价输入测试，Slice 2 consumer 不允许自行加 fallback。 |
| O2 | AgentDS open question | accepted（语义澄清） | `do_ocr/do_table_structure/table_mode/device_name` 是 PDF pipeline 配置，只作用于 PDF；其余 8 个允许格式使用 Docling 2.90.0 constructor 的默认 format options。这不是另一个产品 capability owner：产品只声明允许格式/suffix，真实内容成功仍由 converter 调用裁决。生产代码补中文意图注释/docstring；owner test 断言真实 constructed converter 的 `format_to_options` keys 覆盖且只覆盖 `allowed_formats`，PDF 继续使用 Dayu 自定义 option，既有 PDF option regression 不变。不复制或重建第三方默认 option 表。 |

## 不采纳项与 residual

- MiMo 的 private helper test coupling 与第三方未选择 suffix 列表过期：记录为低 residual，不要求当前改为 public API 或动态反向枚举；动态枚举会违背产品受控子集。
- DS 的第三方畸形映射项产生裸 `ValueError`：当前不接受为产品 finding；依赖元数据内部自相矛盾不属于已证明场景，构造链仍会 bounded 包装。aggregate review 可再次检查。
- later slices 尚未删除旧 allow-list：属于 accepted plan 排序，不是 Slice 1 缺陷。

## 验证要求

- 只修改 Slice 1 已授权的两个 code/test 文件和原 implementation artifact；新增 code-fix artifact。
- 运行 focused tests、两文件 pyright、ruff/black、逐文件 coverage >=80%、`git diff --check`。
- 不修改 README、plan、registry、oracle/scenario、冻结 evidence，不运行 UF-PF06/UF-PF12，不 commit。
- F1/F2/O1/O2 全部标记 `已修复` 后进入双路 re-review。
