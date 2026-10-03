# Code review 修复与裁决

- work unit：midea-q1-full-report；gate：code review → fix → re-review。
- reviewed target：`docs/reviews/code-review-20260915-203849.md`。
- scope：`cn_report_selection.py` 和 `test_cn_report_selection.py`；无 schema/公开接口/缓存状态机变更。

## Findings 裁决

| Finding | Controller decision | 最终状态 | 证据及动作 |
|---|---|---|---|
| F1 README 跳过因果 | rejected-with-reason | 证据失效 | reviewer 声称“无论文件是否齐全同财期永远 skip”不成立。阶段机先调用 storage.classify_source_integrity；只有 COMPLETE/non-overwrite 才 skip，损坏来源走已有 repair。README 写“完整的本地文件”，同时明确内容原表需要核对，并无错误承诺。保持原文。 |
| F2 amended 双点计算 | accepted | 已修复 | `_is_cninfo_amended_title` 统一标记判断；排序 key 与 candidate.amended 复用同一 helper。无 token 扩展或语义改变。 |
| F3 同日混合修订组合 | accepted | 已修复 | 新增更正正文/未更正全文同日参数行，两种顺序均断言正文优先且 amended=True。 |

另外要求 reviewer 纠正两处审查叙述：DS 自己的 selection diagnosis 不属于 MiMo；ID 排序不应由未经证实的“单调递增/近似发布序”支持，只承诺确定性。

## 验证

- `source .venv/bin/activate` 后 focused 三文件 pytest + selection coverage；结果见 `workspace/tmp/midea-q1-cli/workpapers/review-fixed-tests.txt`。
- 全量 `python -m pyright dayu/ tests/ utils/`；结果见 `workspace/tmp/midea-q1-cli/workpapers/review-fixed-pyright.txt`。
- 修复只是既有 amended 表达式的函数收敛，修复前后的相同 Raw 候选选择行为不变；真实五轮 CLI 证据仍适用，修复后另跑普通 CLI 幂等验证。

## 来源证据纠错

MiMo 旧 v1 的 max 平手说法、时间与 commit 记录失效；v2 Raw 可独立核对，但 manifest 自身 hash 因回写失效、脚本复跑可能覆盖 HEAD。保留原件用于解释差异，不作为最终来源 manifest。

Controller 最终独立提取：`workspace/tmp/midea-q1-cli/workpapers/source_probe.py`，保存完整请求、每请求真实时刻、git HEAD、脚本 hash、原始 HTTP response bytes 与 headers；每轮时间戳目录不覆盖。最终源审核底稿：`workspace/tmp/midea-q1-cli/workpapers/source-probe-20260915T124607546138Z-audit.json`，两个窗口均 3 条、无下一页、ID 唯一、同公司、同时间戳、同候选集合和顺序，全部通过。

## Docs / residual risks / completion

- README 无需因被驳回的 F1 修改；保留已实现用户指引。
- F2/F3：fixed in current slice。
- 同一 reviewer re-review 已通过，三项 finding 均已裁决；最终 controller 验证 210 passed、selection coverage 92%、全量 pyright 0 errors，accepted slice no-commit（用户约束），进入 aggregate deepreview。
- 图片表格 OCR 质量与投资 G1 核数仍归后续 owner，按 implementation artifact 分类，不以源修复掩盖。
- 不提交、不推送、不创建 PR。
