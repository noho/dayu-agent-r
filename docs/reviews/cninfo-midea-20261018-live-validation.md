# 美的真实普通增量 CLI 验收

总控已等待 implementation runner 实际退出（外层/runtime 均 0），完整读取其 final、实现记录和验证收据后执行。当前行为版本为 base `1b2166305428d894696974519615cfc4a0ca3b20` 上的本任务未提交组合版本；35 个保存文件 hash 与 implementation receipt 全部一致，保存 tar SHA256 校验一致。生产代码、测试和验收工具未在双跑期间修改。

## 实际命令与结果

先 `source .venv/bin/activate`，运行 implementation artifact 中的固定验收脚本，分别指定全新 `cli-first-01` 和 `cli-repeat-01`，后者显式引用前者。每个托管进程均已取得实际退出 0。

两次子进程真实 argv 均为（仅日志目录不同）：

```text
/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli --base /Users/leo/workspace/portfolio-manager-v2/workspace --log-file /Users/leo/workspace/dayu-agent-r/workspace/tmp/cninfo-midea-20261018/<本次新目录>/dayu.log download --ticker SZ:000333 --start 2025-01-01 --end 2026-10-18
```

没有传 forms、overwrite 或 rebuild，没有清空/手动改写业务来源。观察工具不替换响应、不改请求或返回结果；通过正式仓储协议读回来源。

| 事实 | 首跑 | 再次普通增量 |
| --- | --- | --- |
| CLI PID | 29478 | 29866 |
| UTC 开始/结束（2026-10-18） | 06:24:17.540431 / 06:24:30.917617 | 06:25:15.541411 / 06:25:25.256270 |
| CLI actual_exit_code / 辅助进程退出 | 0 / 0 | 0 / 0 |
| diagnostics status / terminal_disposition | success / succeeded | success / succeeded |
| discovered / downloaded / skipped | 7 / 0 / 7 | 7 / 0 / 7 |
| failed / rejected / uncertain | 0 / 0 / 0 | 0 / 0 / 0 |
| 真实 transport / wire sends / response bodies | 12 / 12 / 12 | 12 / 12 / 12 |
| PDF GET / Docling 转换调用 | 0 / 0 | 0 / 0 |
| 来源前后 publication 相等 | true | true，且与首跑 after 相等 |
| 原始官方响应集合相等 | — | true |

每次均只有一份同源 diagnostics，failure=null、failed_documents=[]，此处空失败行由成功终态支持，不能与原 exit 1 的全零结果混淆。七个选中来源与冻结响应一致：2026 H1/Q1、2025 FY/H1/Q1/Q3、2024 FY。

可取回完整证据根：`workspace/tmp/cninfo-midea-20261018/cli-first-01/` 与 `cli-repeat-01/`。每处包含实际 run.json、stdout/stderr、dayu.log、diagnostics、版本/工作树保存快照、原始官方 response bodies、观察 JSONL、HTTP/转换汇总、source-before/source-after 和 comparison。原始失败日志未覆盖。

## 入口、字节、原文事实与复用

- 两次实际解释器均为 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python`，实际 dayu import 为本仓库；CLI shebang/脚本 hash 与版本快照一起保存。Python 3.11.15、pypdf 6.1.3、httpx 0.28.1、httpcore 1.0.9。观察 started/finished 各一次，hooks_intact=true，error_count=0，PID 对应真实 CLI；零 GET/转换来自实际 wire/透传调用观察，非从 skipped 或缺少日志反推。
- 正式仓储读回共 31 份 COMPLETE 来源和一个 canonical manifest JSON 观察。首跑前后、首跑后与 repeat 前后均完全相等，覆盖 source_meta、revision、全部资产实际 bytes/hash、主源/provenance 及 manifest 规范 JSON。没有重新发布已有来源。
- source `1225065145` 对应仓储真实 `fil_cn_2370958d587deecf28535f0243468efeba805cc8`，revision `de6150711df44bf9a65c05223afa9238`。实际完整 PDF 为 5,942,399 bytes、SHA256 `16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`，与官方当前取证同字节；真实 facts owner 从完整原件返回 2025/full，与持久化财年一致。
- source `1222951181` 对应 `fil_cn_95d26c810c326725ece2cc478a6a4c012fe1c9ce`，revision `7d79bbc27992444fb50380c122669116`。完整 PDF 为 6,737,887 bytes、SHA256 `b17a9b9b84bca1d2a4e4a3cadc5dd5ba5c85e3f1fd2d758acd3315b5b040ecd9`；facts 为 2024/full，与持久化财年一致。
- 两份既有真实 Docling JSON 均可解析为 DoclingDocument 1.10.0，origin mimetype=application/pdf、filename 对应各自原件。2025 为 18,856,529 bytes / SHA256 `c945d5173c005461f27e642163c8af88aca82d0e8d2ca992ded68692c35e7c98`；2024 为 22,960,914 bytes / `bf98154fb967ea145a9b644dd2c05037f9f40fe10f54e25f65bed0aad452dc5d`。实际资产而非测试转换结果，双跑字节均不变。
- 已有七份完整来源全部合法 skipped；本次没有重新执行真实 Docling 转换或新增业务下载。新的远端发现/下载/转换调度路径由官方字节 + 真实 Fs + 明确测试 converter 的离线回归支持，不能把其结果写成新执行的真实 Docling 转换。

## 证明边界与相邻观察

- 本次当前失败机制已由原件和原 owner replay 证明，修复后的原绝对入口已正常完成；原始失败时没有响应/PDF/本地 revision 快照，仍不能唯一指认其历史 source ID。
- 两份既有 FY 的 `fiscal_year_source` 保留旧 publication 的 `title_or_category_inferred`；当前原件 facts 重新证明实际财年/全文，与该原 publication 的历史生成标签不是同一个业务事实。本轮没有迁移历史元数据，新发布 FY 的 `source_document` 合同由真实 owner/Fs 回归验证。不宣称已有标签被升级。
- 计划中的日期表展示官方 PDF locator 的路径日期。实际 `_format_announcement_date` 沿用既有 `time.gmtime` 将 announcementTime 投影为 UTC 日期：本次 2025 FY 的结果/既有 meta 为 2026-03-30，locator 路径为 2026-03-31；其他条目也观察到相同一天差异。本次没有修改日期 owner；路径不是日期真源，缺 provider 时区契约依据不能仅凭路径裁定正确日期。当前七份来源远离查询边界，不影响本次发现/身份/财年/全文验收。若需核查日期语义，交 Fins 维护者单独取得 provider 契约及边界证据，不把未经证实的解释带入本轮修复。

## 总控裁决与风险

- implementation / validation：当前目标行为与必要验证已满足，进入最终组合 code review，尚未宣称 review pass 或 work unit completed。
- 合法“全文”拒绝、实际入口及普通增量复用：fixed in current slice，待独立双审裁决；owner 总控 / code review。
- 无新真实转换执行：assigned to later work unit，owner Fins 维护者；若后续出现新转换问题按实际来源另案。本轮全部来源已完整、验收允许合法 skipped，不通过清库/覆盖创造新下载。
- 原始历史来源不可唯一追溯、未知首页布局：assigned to later work unit，owner Fins 维护者；分别以新历史证据或新官方失败来源启动，当前证明边界不扩大。
- 公告时区及历史 provenance 标签的相邻观察：assigned to later work unit，owner Fins 维护者；先核清字段/来源契约再决定变化。本轮不增加日期或元数据迁移目标，亦不以这些观察推断根因。
