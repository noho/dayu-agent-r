# 美的 2021Q1 完整报告补源修复交接

生成时间：2026-09-15T12:53:09.709189+00:00；版本：handoff-v1；数据期间：2021Q1；审核单位：公告/文档（不含财务数值计算）。

## 结论与根因

本地修复、代码复审和 aggregate deepreview 已完成。巨潮存在中文完整报告 `1209870320`，公开 CLI 已取得 17 页 PDF；第 11–12 页原图确认 2021-03-31 资产负债表的合并列及货币资金、短期借款、长期借款、股本行。不能写成“公司未披露”。

两个日期窗口均查到三条同日公告，顺序为英文全文 `1209870381`、中文正文 `1209870319`、中文全文 `1209870320`。原代码过滤英文后只按修订/日期比较，中文两项同分，`max()` 取先遇到的正文。另一个障碍是 CN 同财期非修订公告共用文档身份，已有物理完整缓存默认 skip；选择修复后，旧缓存必须显式覆盖。

## 源码与文档改动

- `dayu/fins/pipelines/cn_report_selection.py`：同修订、同日优先非正文，剩余平手按 ID/URL 稳定裁决；正文仍为合法唯一来源；修订/日期优先保持，amended 判断统一由私有 helper 持有。
- `tests/fins/test_cn_report_selection.py`：Q1/Q3、普通/全文标题、唯一正文、修订/日期、同日混合修订、英文/摘要排除、输入顺序和 ID/URL 平手。
- `tests/fins/test_cn_download_workflow.py`：扩展既有真实仓储 skip/overwrite/再次 skip 回归，核对当前来源、文件与清单一致性。
- `README.md`、`dayu/fins/README.md`、`tests/README.md`：分别说明公开补源操作、选择契约与测试入口。

生产仅一文件，无 schema/身份/存储/默认增量合同变更。没有修改投资 workspace，没有提交、推送或创建 PR。

## 验证结果

| 实际公开 CLI 轮次 | 持久化 source_id | downloaded | skipped | failed |
|---|---|---:|---:|---:|
| before-v1 | 1209870319 | 1 | 0 | 0 |
| fixed-skip-v1 | 1209870319 | 0 | 1 | 0 |
| overwrite-v1 | 1209870320 | 1 | 0 | 0 |
| incremental-v1 | 1209870320 | 0 | 1 | 0 |
| fresh-v1 | 1209870320 | 1 | 0 | 0 |
| final-incremental-v1 | 1209870320 | 0 | 1 | 0 |

每轮 discovered=1、rejected=0、exit code=0。覆盖和新 workspace 下载的全文 PDF SHA256 相同：`f68e946df248e9b3cf27ad684910928431ae112605a23f1e3429808637e1b4b6`。

已审核：唯一文档、精确 PDF/Docling 两文件集合、每文件 hash/size、pdf_sha256、内容 fingerprint、HEAD raw 重放 remote_fingerprint、provider/财期身份、source meta 与 manifest 投影。默认 skip 前后和最终再次 skip 前后冻结文件字节完全相同。

```bash
cd /Users/leo/workspace/dayu-agent-r
source .venv/bin/activate
python -m pytest tests/fins/test_cn_report_selection.py tests/fins/test_cninfo_downloader.py tests/fins/test_cn_download_workflow.py --cov=dayu.fins.pipelines.cn_report_selection --cov-report=term-missing -q
python -m pyright dayu/ tests/ utils/
```

结果：**210 passed，selection 覆盖率 92%，pyright 0 errors / 0 warnings**；git diff --check 通过。记录：`/Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/workpapers/review-fixed-tests.txt`、`/Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/workpapers/review-fixed-pyright.txt`。

## 独立验证的精确公开命令

在新的隔离 workspace 首次运行，预期 downloaded=1、全文 source_id=1209870320；原样再次运行预期 skipped=1：

```bash
/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli download --base /Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-independent --ticker 000333 --forms Q1 --start 2021-04-29 --end 2021-04-30
```

验证已有正文缓存的公开替换方式（此命令只指向本轮隔离 workspace）：

```bash
/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli download --base /Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/isolated-workspace --ticker 000333 --forms Q1 --start 2021-04-29 --end 2021-04-30 --overwrite
```

`--rebuild` 不下载远端全文，不能替代覆盖。投资 workspace 的同类操作由原投资 Agent 独立验证后决定，本轮没有代执行。

## 四层产物与复现

1. 来源和请求：`/Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/data/source_manifest/`；最终候选源 manifest：`source-probe-20260915T124607546138Z.json`；保存真实请求/时钟/代码版本/原始响应 hash。各 CLI 轮次含请求、patch、stdout/stderr、日志和退出码；`head-v1.json` 记录 HEAD。
2. Raw：`/Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/data/raw/`；候选原始 HTTP bytes：`source-probe-20260915T124607546138Z/`；六轮文档快照各自独立目录；`head-v1/` 保留响应字段。不静默改写旧 Raw。
3. 审核：`/Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/workpapers/`；`source_probe.py` 提取并审核候选，`run_cli.py` 执行公开 CLI 留痕，`snapshot.py` 通过 storage 冻结/审核文件，`reconcile.py` 勾稽全链。总底稿 `/Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/workpapers/reconciliation-v1.json`；来源底稿 `/Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/workpapers/source-probe-20260915T124607546138Z-audit.json`；PDF 页面核查图在 `overwrite-v1/page-11.png` 与 `page-12.png`。
4. 最终结果：`/Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/outputs/` 中 `reconciliation-v1.json`、最终 source-probe JSON 和 `handoff-v1.md`；本文件由 `workpapers/build_handoff.py` 从审核通过底稿生成，并镜像到 `docs/reviews/midea-q1-closeout.md`。

## 审查裁决与风险

- Plan review：`docs/reviews/plan-review-20260915-203419.md`。
- Code review/re-review：`docs/reviews/code-review-20260915-203849.md`。F1 因误解 COMPLETE 门槛 rejected-with-reason；F2/F3 accepted 且已修复。最终测试数字以本报告保存日志为准，早期审查中的 209/91% 属修复前版本。
- Fix：`docs/reviews/midea-q1-review-fix.md`；aggregate deepreview：`docs/reviews/code-review-20260915-205037.md`，PASS，无未解决 accepted finding。
- 证据例外：MiMo v1 叙述的平手规则/时间/commit 失效，v2 manifest 自身 hash 因回写失效；原件保留。最终结论采用 controller 独立原始响应与审核链，不采用失效摘要。
- **图片表格 OCR 仍不完整**：Docling 的第 11–12 页表结构有数据，但中文行名缺失；owner 为后续 Docling/财表提取维护 work unit。原投资 Agent 必须看原图核数，不得仅凭 JSON 内部一致性接受 G1。
- 跨日期/修订级别优先级和覆盖版本策略保持原有边界；不承诺通用 PDF 内容完整性或历史版本递增。source meta 的 report_date 仍为 null，财期是 2021/Q1；原图报表日为 2021-03-31，未手改元数据。
- 日期窗口保留两天：原始时间戳为北京时间 4月30日/UTC 4月29日，现有 Dayu filing_date 为 2021-04-29；本轮不修改日期归一规则。

## 本地 closeout 与 next entry point

用户授权范围内的本地代码修复和审核完成。accepted plan/slice/deepreview commit 均按“不自动提交”记 no-commit；push、draft PR、PR review 未执行，**不宣称 Gateflow draft-PR-pass 或 final-closeout-pass**。无 issue/PR URL。

下一步由原投资 workflow 主 Agent 使用上述公开命令独立核验全文及财务原图后，再更新投资 workspace 和裁决 G1。若未来另行授权 Git 发布，需创建真实 checkpoints 并完整推进 PR review 链，不能把本地记录当作已完成 PR。
