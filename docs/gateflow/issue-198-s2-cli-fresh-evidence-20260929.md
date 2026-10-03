# Issue #198 S2 隔离真实 CLI：fresh 发布、typed 失败与恢复

- Gate：S2 implementation validation；测试代码快照为 `/private/tmp/dayu-issue198-s2`，HEAD `7234d42dbaea603112c6fed52776281228d261a7` + 11 文件未提交 diff SHA-256 `d53e67f29e26c6d835c42ea81ce43aef34a27cf831959ee685c1802b42df14c5`。
- 隔离工作区：`/private/tmp/issue198-cli-wide2-9aklx640`，新建空目录，**没有复制 donor 或预置来源**。使用 `.venv` 中 Python 3.11.15 的真实 `dayu-cli`、CNInfo provider、Docling 转换及 Fins storage。未运行 `dayu-cli init`、未操作用户现有工作区。
- 与 accepted plan 的方法差异：计划指定 `2025-03-28..2025-03-28` 单日首次下载，实际本次 `discovered=0`；中国本地披露日 `2025-03-29..2025-03-29` 也为 0。为取得同一 FY2024 年报候选，受控验证改用 `2025-03-27..2025-03-31`，由本次真实 provider 发现目标并 fresh 转换/发布。这个差异只改变验证筛选窗口，不改 #198 产品行为或成功信号；单日发现问题仍归独立 CNInfo WU。本文件不把原单日命令标为通过。

## 三次同参数真实 CLI

共同命令形状：`dayu-cli --base <隔离工作区> download --ticker 000333 --forms FY --start 2025-03-27 --end 2025-03-31 --log-file <阶段日志>`。三次均从 `/private/tmp/dayu-issue198-s2` checkout 执行。

1. **fresh baseline**：首次目录为空；CNInfo 真实 provider 返回 `fil_cn_95d26c810c326725ece2cc478a6a4c012fe1c9ce`，Docling 转换完成并产生 PDF + `_docling.json`，仓储 manifest 登记成功。CLI 退出 0；stdout 末尾 `discovered=1 downloaded=1 skipped=0 rejected=0 failed=0 omitted=0`，文档行 `filing_date="2025-03-28"`、`disposition="downloaded"`；stderr 空。PDF SHA-256 `b17a9b9b84bca1d2a4e4a3cadc5dd5ba5c85e3f1fd2d758acd3315b5b040ecd9`，Docling JSON SHA-256 `bf98154fb967ea145a9b644dd2c05037f9f40fe10f54e25f65bed0aad452dc5d`，与发布 meta 登记一致。第一次较宽窗口 fresh 转换在执行人设的 180 秒上限前未完成；第二次新空目录以 600 秒受控上限完成，前一次不计成功。
2. **typed storage failure**：只在 `portfolio/000333/filings/` 根新建非点号普通文件 `issue198-unassignable-root.txt`，固定受控内容；其余来源/manifest/meta 不动。完全相同的下载筛选重跑退出 1。stdout 只有 `download.preparing` 和 `download.started`；stderr 为 `Fins failure`、结构化零候选摘要与 `classification="storage" source="cninfo" transport="-" reason_code="unsafe_publication" retry_hint="请检查并修复工作区来源状态后重试；重复下载不会自行修复。"`，没有误导性 execution 分类或盲目重试建议。`typed.log` 未出现 `fins.download.unexpected_failure`；五份已发布来源文件在注入前后逐文件 SHA-256 完全相同。
3. **清除唯一 mutation 后恢复**：断言该文件仍为普通文件且内容逐字等于固定标记，仅删除它；相同筛选再次运行退出 0，`discovered=1 downloaded=0 skipped=1`，同一目标按 `integrity_complete` 跳过，stderr 空。没有重新转换或发布已完整来源。

## 原始流哈希与安全核对

| 流 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `baseline.stdout` | 35262 | `23c41edaa321a62da1b138fd624baa8ebfb2a24011506931be2e8c712b167080` |
| `baseline.stderr` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `baseline.log` | 1842 | `3d31052aa9715c5f68ceaafd11f252784e21d58f26293fc9dd0d703f7cef35d4` |
| `typed.stdout` | 208 | `0804026d929cc3d8184a56a6de719c3a184292b7d4744da316a83067b7b96f46` |
| `typed.stderr` | 508 | `dc00b1c42a23303baa0f59f6570bbfb4223c07a2107b1c7ef41d23ddd3cdb81b` |
| `typed.log` | 168 | `93e88e898749e3909a613ecf24ae878c529d3b2dea7e8e1b7875bebc63219be8` |
| `recovery.stdout` | 862 | `1e5f1a468ebaa7b7024c66375687ba74b7f34613011333c6c5bd771acccad52a` |
| `recovery.stderr` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

对 `typed.stdout`、`typed.stderr`、`typed.log` 分别检查：没有受控外来 basename、`Traceback` 或 unknown 诊断事件。另用独立 Python 字面断言核对 `typed.stderr` 不含 `请使用 --log-file PATH 重试并查看日志`，`typed.log` 同时不含 `fins.download.unexpected_failure` 与 `fins.download.command_unexpected_failure`，并断言公开 `classification="storage"`、`reason_code="unsafe_publication"` 均在 stderr；检查退出 0、打印 `S2_TYPED_NEGATIVE_ASSERTIONS=PASS`。这只证明 typed 案例的公开/日志边界，未知异常的秘密注入由 S2 owner/CLI 测试断言。baseline stdout 的 Docling 第三方转换 WARNING 单独归转换流，不作为 #198 失败投影；抽取质量归 Docling 上游，不在本 issue 范围。

## 验收边界

这次 fresh provider→Docling→manifest 发布，以及同请求 typed 失败和恢复，满足 #198 的真实隔离 CLI 主链路成功信号。精确单日筛选仍未通过，不能因此声称 CNInfo 单日日期 WU 已修。若 code review 发现 S2 安全日志自身缺陷，必须先修并在最终代码快照复验必要路径；本证据只属于上述 S2 候选 SHA。
