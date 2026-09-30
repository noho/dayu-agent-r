# UM-O21/O22 plan review 裁决

- 工作区 `/private/tmp/dayu-upload-content`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。MiMo `docs/reviews/plan-review-20260929-025500.md` 进程 exit 0、JSON `subtype=success`、`is_error=false`、canary `mimo-b924e24b` 匹配，stderr 仅白名单模型提示。Kimi 同轮 HTTP 403、exit 1、`is_error=true`，provider failure，无有效第二路。Sol 初 plan 两条失败命令并有非白名单 apply_patch stderr，`agent_status=failed`，计划只作候选。当前 gate 为 **plan review → fix**，未实施。

## Finding 与 owner 裁决

MiMo F1 **accepted/high**。`dayu/fins/tools/upload_tools.py:505-506` 的 `stat().st_size <= 0` 在 Fins 上传 owner 之前独立重判空字节，并投影为无文件标签的英文 `invalid_argument`；这与已确认的 O22「同一 0 字节内容在所有入口走同一 typed `content/empty_input_file` reason」冲突。计划白名单必须包含 tool 文件，移除这处文件大小业务事实重判，保留路径存在/普通文件结构检查；tool 正常创建 observation/job 后由同一 Docling service 原件字节 owner 分类，结果/事件/持久摘要沿 existing typed reason 传播。同步迁移 `tests/fins/test_fins_ingestion_tools.py:2260-2292` 的旧提前拒绝断言，覆盖 awaiting→failed outcome 的 reason/label；不得借旧测试固定漂移。无需扩 tool schema，不改变目标或公开字段。

其它 owner 链与 company meta 界限获 MiMo 独立复证。计划须点名 `test_sec_pipeline_upload_material_stream.py` 的旧 `file_label=None` 断言迁移，明确本工作区锁定 Python3.11 venv/`dayu.__file__` 验证与被改 tool 单文件 >=80% coverage；O04/O23 同文件集成继续串行审查。Sol 修 plan 后等有效 Kimi/MiMo 双路 re-review，不能凭当前单路进入实现。

## MiMo 第二次 plan re-review 裁决

`docs/reviews/plan-review-20260929-041253.md`：预检 ok、显式绝对 workspace、独立 output/stderr，进程 exit0，JSON `subtype=success/is_error=false`、85 turns、canary `mimo-6c3b2077` 匹配，stderr 仅白名单模型提示，`agent_status=completed`。首轮 st_size 截胡、旧标签断言、锁定 venv/coverage 在计划层已收敛；Kimi 第二路仍缺。新增 finding 经当前代码核对：

1. **F1 high accepted，修正 observation/job 语义**。tool 只调用 `prepare_observed_upload`，其 `_FinsIngestionExecutionContext.job_record=None`；它产生 awaiting handle 与 observation 终态，不建 durable job。现 plan 多处要求 tool 路径 `job failed`、`result_summary.failure`/`failure_summary` 持久双写，会与既有无 job 合同冲突。Sol 只修计划：tool 验收改为 `ToolAwaitingOutcome`→激活 observation→`poll_observation` terminal `details/error_message` 与 direct/CLI 的同一 typed reason `to_json()` 字段对照；durable job 双写仅归 `start_upload` 的真实 job 路径测试。现有 `FinsResultSummary.failure` 恒为 None，不用它冒充 typed reason。旧裁决中“observation/job”并列句以本段为准，tool 不要求 job；durable 查询记录 queried-but-absent。若真实 tool 终态无 typed reason，再基于直接证据停止并回到 owner，不加 adapter fallback。
2. **F2 low accepted，operator log 业务标签**。共同 `DoclingUploadService` catch 的两个日志仍写 `Filing upload`，material 内容失败将被误标。该模块本就在白名单；只把共享日志改为 filing/material 中立的上传描述，不改 failure reason 或引入第二套 owner；补日志断言如有必要，避免对原始本地路径泄露的旧文字固化。

下一 gate 仍为 Sol 仅修 plan，随后有效 Kimi/MiMo 双路 plan re-review；产品未实施。O04/O23、O34 与 #198 残余保持独立。

## Sol 第二次 plan fix 候选

`content-plan-fix2-sol-20260929-01`：预检 ok、显式绝对 `/private/tmp/dayu-upload-content`、独立 output/stderr，退出0，JSONL `turn.completed`、19 条 command execution 全成功、无 error/failed，stderr 空，canary `gpt-6-sol-d6fc825e` 匹配，`agent_status=completed`。总控核对计划 SHA-256 `95b1adecc95162ca64b67bf195c1e1f98e99a09c91c171e330f737221371f2fd`：tool awaiting→observation 的 `result.details/error_message` 与 `start_upload` durable job 的两处摘要已经分开，旧测试、真实 CLI/tool/job 证据与 stop condition 同步；共享 Docling catch 的两处日志中立化已列实施/测试要求。当前只达候选计划，下一 gate 为有效 Kimi/MiMo 双路 plan re-review；产品未实施。

## MiMo 第三次 plan re-review 通过（单路）

`docs/reviews/plan-review-20260929-044233.md`：预检 ok、显式 `/private/tmp/dayu-upload-content`、独立 output/stderr，exit0、Claude JSON `subtype=success/is_error=false`、83 turns、canary `mimo-fc8310e3` 匹配、stderr 仅白名单模型提示，`agent_status=completed`。总控核对其 HEAD/计划：首轮 tool st_size 截胡、二轮 observation/job 混淆和 operator log finding 在候选计划层已闭合；owner failure reason/安全文件标签、两行为切片、真实 CLI/tool/start_upload 与逐文件 coverage 配方没有新的阻塞发现。两个低 open question 不改变当前目标，按 review artifact residual 保留。**这只是 MiMo 一路 pass-with-risks；Kimi 有效 re-review 未完成，plan gate 未通过，产品未实施。**
