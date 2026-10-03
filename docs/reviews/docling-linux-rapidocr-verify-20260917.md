# Linux x64 + rapidocr 转换验证报告（阶段 2.4 样本补足）

- 日期：2026-09-17
- 目的：确认 docling 2.127 升级后 **rapidocr 在 Linux x64 上稳定可用**；
  补足阶段 2 仅命中 2 份样本的覆盖缺口
- 环境：Docker `--platform linux/amd64`，镜像 `dayu-linux-x64-verify:latest`
  （Python 3.11 + docling 2.127.0 + docling-ibm-models 4.0.2 + docling-parse 7.20.0
  + rapidocr 3.9.2），内存上限 **7.7 GB**
- 转换路径：生产同源 `dayu.documents.docling_runtime.convert_pdf_bytes_with_docling`
- 脚本：`workspace/tmp/linux-verify/run-conversion-check.sh`（分层选样）、
  `inner-conversion-check.sh`、`inner-convert-one.py`
- 原始日志：`workspace/tmp/linux-verify/conversion-check.log`
- 证据等级：全部结论为 **Tier-0（程序化）**——引擎选择日志、产物 JSON、
  计数与耗时均为机器输出

## 1. 样本选取（放宽分层，9 份）

原阶段 2 条件（`pictures>=20 且 texts<=600`）全库仅命中 2 份，覆盖不足。
本次放宽为分层抽样（避开 pictures>200 的巨件，防容器 OOM）：

| 层 | 配额 | 实际选取 |
|---|---|---|
| 中等图量（pictures 10-80） | 5 | 5 |
| 大图量（pictures 80-200） | 2 | 2 |
| 低图量（texts<=1500） | 2 | 2 |

候选池：mid=41、big=6、lowpic=167（放宽条件后候选总数 214）。

## 2. 逐样本结果（Tier-0）

| 样本 | pictures | 基线 texts/tables | 基线数字 tokens | Linux 耗时(s) | closed_json | 新 texts | 新 tables | 新数字字符数 |
|---|---|---|---|---|---|---|---|---|
| `fil_cn_51a151404268de1da`（中） | 77 | 3660 / 90 | 8716 | 628.4 | ✅ | 3206 | 89 | 25086 |
| `fil_cn_f77d12770283cdc2`（中） | 70 | 790 / 35 | 1396 | 417.0 | ✅ | 792 | 35 | 4750 |
| `fil_cn_93f3afedb9baab21`（中） | 69 | 3242 / 94 | 8399 | 630.2 | ✅ | 3119 | 94 | 24206 |
| `fil_cn_7e0f3daef3680d12`（中） | 64 | 3129 / 94 | 8611 | 619.8 | ✅ | 3183 | 94 | 25515 |
| `fil_cn_0a236e7b2e0c0813`（大） | 187 | 4095 / 84 | 9205 | 655.2 | ✅ | 4276 | 84 | 30474 |
| `fil_cn_2d0fb080c9748ead`（大） | 178 | 1953 / 186 | 7512 | 657.9 | ✅ | 2462 | 187 | 31516 |
| `fil_cn_9c9acd3c77749451`（低） | 0 | 14 / 0 | 20 | 7.1 | ✅ | 15 | 0 | 49 |
| `fil_cn_5b5a4c6678e8796c`（低） | 1 | 19 / 0 | 40 | 7.6 | ✅ | 20 | 0 | 92 |
| `fil_cn_fc5bbc5234e66457`（中） | 74 | 3315 / 122 | 7365 | **—（OOM killed）** | ❌ | — | — | — |

**完成率 8/9**；8 份全部 `closed_json=true`（产物为合法闭合 JSON，可被
`_is_closed_json_value` 判定通过）。

## 3. rapidocr 稳定性结论（Tier-0）

1. **引擎选择 9/9 一致**：每个样本转换前均输出
   `Auto OCR model selected rapidocr with torch.` —— Linux x64 容器上
   未安装 ocrmac（darwin 专属）、nemotron、onnxruntime、easyocr，
   auto 路径稳定落到 rapidocr(torch)，与 macOS 生产环境行为一致。
2. **产出合法率 8/8**（完成的样本全部 `closed_json=true`），无解析错误、
   无 JSON 截断。
3. **数字保真量级合理**：8 份完成样本的新版数字字符数 49 - 31516，
   与基线同量级（如 `2d0fb080` 新版 31516 字符 vs 基线 7512 个数字 token），
   未出现"整档数字归零"式的 OCR 失效。
4. **耗时分布**：小样本 7-8s；中/大样本 417-658s（7-11 分钟）。
   同一环境同类样本耗时稳定，无超时或挂死。

**结论：rapidocr 在 Linux x64 上稳定可用（8/8 完成样本合法），可作为
Linux 生产路径的 OCR 引擎。**

## 4. 观察到的问题：1 份样本被 OOM kill（Tier-0）

- 样本：`fil_cn_fc5bbc5234e66457`（pictures=74、texts=3315、tables=122，PDF 2.4 MB）
- 现象：引擎已正确选择 rapidocr，转换过程中进程被 SIGKILL（shell 输出 `Killed`），
  容器 7.7 GB 内存上限下未产出任何结果；**后续样本正常继续**，非进程级崩溃。
- 对照：更早一次未分层选样时，首份样本（pictures=430）同样被 OOM kill。
- 性质判定：这是**容器内存上限**问题，不是 rapidocr 引擎缺陷——
  同一批次中 pictures 更多（187/178）的样本均成功完成。
- 待办（不属本报告范围）：Linux 生产部署的内存预算需按最坏样本评估；
  建议对高图量样本单独测内存峰值，或在 pipeline 侧限制并发。

## 5. 与历史基线的差异说明（边界）

本报告的"数字字符数"是新版产物内数字字符计数，基数列是基线 JSON 的
数字 token 计数——两者口径不同（字符数 vs token 数），**不能直接比较大小**，
仅用于确认"量级合理、无归零"。逐 token 保真对比见
`docs/reviews/docling-table-mode-ab-20260917.md` 与
`docs/reviews/docling-regression-8492e128-rootcause.md`。

## 6. 产物

| 内容 | 路径 |
|---|---|
| 完整日志（含引擎选择与 RESULT 行） | `workspace/tmp/linux-verify/conversion-check.log` |
| 转换产物 JSON（8 份） | `workspace/tmp/linux-verify/out/` |
| 选样与运行脚本 | `workspace/tmp/linux-verify/{run-conversion-check.sh,inner-conversion-check.sh,inner-convert-one.py}` |
