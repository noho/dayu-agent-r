# UM-O11-F01 计划审查裁决

- Gate：plan review → fix。工作区 `/private/tmp/dayu-upload-o11`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- MiMo `docs/reviews/plan-review-20260929-015241.md` 退出 0，JSON `subtype=success`、`is_error=false`，canary `mimo-c889c320` 匹配，stderr 仅白名单模型名提示；结论 accept-with-fix。Sol 原计划派发三条失败命令，计划只作候选。Kimi 额度 403，尚无有效第二路，不能宣告 gate pass。

## Findings 裁决与修复登记

1. **F1 accepted，必须修计划**。非 `None` 的 raw `filing_date/report_date` 空串及纯空白由共享 admission 严格 parser 拒绝；这确实改变今日 raw 空串穿透持久化的错误行为，不能再写“raw 策略保持”。CLI 显式 `--filing-date ""`→`None` 是已接受的唯一入口投影例外；不把它扩大到 raw request 或 tool。计划 R2 限定为 CLI 折叠与 tool 拒绝结果保持。
2. **F2 accepted，必须修计划**。tool schema 的两个日期参数描述均自足说明业务日期含义、文本格式 `YYYY-MM-DD`、可省略或 `null` 表示未提供、真实公历示例 `2024-02-29`、空串/纯空白/首尾空白均非法；同步更新 owner schema 断言。不得让 LLM 依赖内部 parser/type 名。
3. **F3 accepted**。根 README 的变动原因改为非空非法/带空白日期的拒绝收紧，以及既有 CLI 显式空 filing_date→null 的说明；不得虚构该空值行为变化。
4. **F4 accepted**。被改生产单文件覆盖率目标各 ≥80%；若有效增量测试后仍不足，记录准确数字、原因与未达标残余，不静默写 pass，也不为指标写镜像测试。
5. **F5 accepted（测试边界）**。以 owner 接受/拒绝/typed 字段消息和入口副作用为主断言；monkeypatch parser 调用仅是同源辅助，不能固化调用次数/私有步骤。计划应调整。

审查证明的 parser 严格性、direct/job/observation 共同 admission 与 README 职责判断接受。集成时与 O05/O16 串行核对字段错误优先级；`upload_filings_from` 日期预折叠差异继续独立残余，不进入 O11。修订后双路 plan re-review；产品未改。
## Kimi/MiMo 修订计划双路复审与接受裁决（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-022441.md`、Kimi `docs/reviews/plan-review-20260929-024457.md` 各自进程 exit 0、JSON success、canary `mimo-51420059`/`kimi-2fcd3157` 匹配、stderr 仅白名单模型提示。两路独立核对 raw 非 None 空白日期拒绝、CLI 显式空 filing_date 例外、LLM schema 自足、三入口共用 admission、O05/O16 同函数集成与逐文件覆盖率诚实登记，均无阻塞 finding。总控裁决 **plan review gate pass**；Sol fix 因一条失败 `rg` event 保持 `agent_status=failed`，计划内容以双路重证接受，不追认派发。

实施时须在本 worktree 建立/核对 Python 3.11 锁定环境与 `dayu.__file__`；CLI material 纯空白折叠与 raw/tool 严拒的现有入口差异按 plan R2 记录。下一 gate：accepted plan commit，再由 Sol 实施；O05/O16/O11 同 owner 的实际合并须在 PR 集成时串行校验错误优先级。
