# docling 2.127 升级 PPTX/DOCX 真实转换冒烟报告

- 日期：2026-09-17
- 执行：实施 Agent
- 方案：`docs/plans/docling-2-127-upgrade.md` 步骤 2.5（F06 修订版）
- 脚本：`utils/pptx_docx_smoke.py`（pyright 0 errors）
- 样本：`workspace/tmp/pptx-docx-samples/`（python-pptx / python-docx 自建，每次运行幂等重建）
- 汇总产物：`workspace/tmp/pptx-docx-samples/smoke-summary.json`

## 1. 背景

样本库无真实财报 PPT/DOCX（覆盖缺口见方案 2.5），本冒烟用自建样本验证升级后
PPTX/DOCX 转换链：v2.113.0 原生图表解析、v2.118.0 DOCX 页眉页脚保留与 PPT
形状视觉阅读顺序、v2.118.1 表格单元格内图片保留、v2.122.0 行尾连字符处理等
修复是否正常生效。

判定链与生产入口一致：`dayu.documents.docling_runtime.convert_pdf_bytes_with_docling`
（stream_name 带原扩展名，converter 由 `build_docling_pdf_converter` 构造、非 PDF
格式走 docling 默认 options），判定 = 转换成功 + export_to_dict 为 closed JSON +
`DoclingDocument.model_validate_json` 可解析 + 表格数字保真（merged 口径
texts ∪ table_cells 的哨兵数字命中率）。

## 2. 样本与结果

| 样本 | 特征 | 转换 | closed JSON | 可解析 | texts/tables/pictures | 数字保真（埋入哨兵命中） |
|---|---|---|---|---|---|---|
| pptx_merged_tables.pptx | 3 页复杂合并单元格表格（横向合并表头/纵向合并首列/块合并） | ✓ | ✓ | ✓ | 0 / 3 / 0 | **1.0**（全命中） |
| pptx_charts.pptx | 柱状图 + 折线图 + 饼图 | ✓ | ✓ | ✓ | 0 / 0 / 3 | 不适用（图表数值按设计不进 texts/tables；图表以 3 张 picture 保留） |
| docx_columns.docx | 双栏分栏 + 表格 | ✓ | ✓ | ✓ | 8 / 1 / 0 | **1.0**（全命中） |
| docx_header_footer.docx | 页眉 + 页脚（含数字）+ 正文表格 | ✓ | ✓ | ✓ | 5 / 1 / 0 | **1.0**（全命中，含页脚数字） |
| docx_mixed.docx | 两级标题 + 列表 + 5×3 表格 | ✓ | ✓ | ✓ | 9 / 1 / 0 | **1.0**（全命中） |

## 3. 事实性观察

1. **5/5 样本转换成功、closed JSON、可解析**，schema 契约完整（顶层 key 集与
   PDF 产物一致）。
2. **表格数字保真 4/4 适用样本全命中**：合并单元格、分栏内表格、页眉页脚样本、
   混合文档的哨兵数字（千分位/小数/百分比/负数）在 merged 口径（texts ∪
   table_cells）中全部找到，含页脚中的数字。
3. **图表以 picture 形式保留**（3 张图表 → 3 张 pictures），picture 条目无
   `data`（无 chart_data 字段）——图表数值不进入 texts/tables 口径，数字保真
   判定对纯图表样本不适用（按方案判定标准未将图表数值列为保真对象）。
4. **DOCX 页眉页脚文本进入 texts**（docx_header_footer 样本 texts=5，含页眉
   "某某股份有限公司 2026 年半年度报告" 与页脚内容），符合 v2.118.0 页眉页脚
   保留的升级收益预期。

## 4. 残余限制

- 自建样本的结构复杂度低于真实财报 PPT/DOCX（如真实合并单元格表头树、跨页
  表格、嵌入对象）；方案 2.5 的"首批 10 份真实上传人工抽检"仍是最终防线。
- 图表数值解析（v2.113 原生图表解析）在本轮 docling 版本下未观察到进入文本
  口径的行为（以 picture 保留）——与 PDF 样本库观察一致，属事实记录。
- 未做 PPTX 页眉页脚（python-pptx 无原生 API）与 DOCX 分栏与页眉页脚同页
  组合样本。
