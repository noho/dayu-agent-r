# Issue #198 S2 plan review 总控登记

- 当前 gate：plan review 尚未启动，候选 `docs/gateflow/issue-198-unknown-download-diagnostics-plan-20260929.md`，SHA-256 `cdb57a252298d7bf08399fcdb37e3f78fc3e355f80a63b48aea9b92f1138776e`；产品未改。
- Sol `issue198-s2-plan-sol-20260929-01` 预检 ok、显式 `/private/tmp/dayu-upload-issue198-s2`、独立 output/stderr、process exit0、JSONL `turn.completed`、canary `gpt-6-sol-6731fee2` 匹配、stderr 空，但四条探测命令因不存在路径/venv 返回非零，按执行协议 **agent_status=failed**；候选文本只由总控独立读取，不作 gate pass。

## 总控预审待双路挑战

**C1：异常类型诊断的可定位性。** #198 期望脱敏后仍有原始异常**类型**和栈定位；候选 formatter 对所有自定义类一律输出 `custom_exception`。这保护任意恶意类名，但可能让生产中常见的 Docling、storage 或 provider 自定义异常丢失最有价值的类型标签。plan review 应以实际异常来源、模块身份与日志敏感边界判断是否需要对可信 `dayu.*` 类显示精确类名、对第三方保持有界安全类别，或给出能满足排障目标的等价封闭分类；不得直接输出未经证明安全的任意 `__name__`/`__module__`。若固定泛类已足够，review 必须用真实异常定位案例说明。

**C2：S1 集成后的 job 真源。** S2 候选设计下载专属 `_save_download_failed_from_exception` 并保持现有 `failure_summary={"message": ...}`，而 #198 S1 计划正在修改 typed 失败的 job summary 与 public failure 投影。S2 是 S1 implementation 后置，plan review 应要求同一 owner helper 消费 S1 **实际集成**的 closed failure/summary contract；不能以当前未实施的旧 message-only job 形状作为 S2 实施验收，亦不能覆盖 typed reason。若依赖尚未落地，允许条件计划，但须明确实施前重基线/重审触点。

以上是总控预审问题，不代表最终 finding。Kimi/MiMo 两路有效 planreview 后逐项裁决并登记修复。

## MiMo 首轮 planreview 与总控裁决

MiMo `docs/reviews/plan-review-20260929-053621.md` 预检 ok、显式 `/private/tmp/dayu-upload-issue198-s2`、独立 output/stderr、process exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、48 turns、canary `mimo-58e762be` 匹配，stderr 仅白名单模型名提示，`agent_status=completed`；结论 **fail**，F1/F2 高项未闭合。Kimi 有效第二路尚缺。

| Finding | 总控裁决 | Sol plan fix / 验收 |
| --- | --- | --- |
| F1 高：自定义类型全 `custom_exception` 且末 16 外部帧抹掉唯一 `dayu` 定位 | **accepted**。#198 要有可区分异常类型与可定位安全栈；现候选对深第三方栈双落空。采用同一 #198 S1 计划已裁决的内建祖先 + `SHA-256(module + NUL + qualname)` 截 16 hex 指纹，原类名/消息不输出；安全栈必须在有可信帧时保留至少一个 `dayu/…py:line` 与末端抛出位置信息，深外部栈以固定占位/计数压缩。 | 不另建 `safe_exception_diagnostic.py` 第二套 helper；消费 S1 已约定的 `dayu.runtime.log.safe_exception_trace` 或 S1 实际集成等价层中立 helper。两类自定义异常的指纹须不同且无秘密；>16 外部帧时仍保留可信 Dayu 调用帧，且不打印原始 filename、源码行、cause/locals。若 S1 合同变动，实读后回本 plan。 |
| F2 高：S2 与在世 S1 S2 段多个公开/诊断合同互斥 | **accepted**。S1 是前置，S2 应明确消费它的最终同源 contract，而非并列发明 helper、事件名、hint、CLI 常量或旧 message-only job 形状。 | plan 加 **supersession/消费映射表**：S1 最终 helper/格式/事件 `fins.download.unexpected_failure` 与 `fins.download.command_unexpected_failure`、未知 retry hint 的逐字合同、`output.py` 独占 CLI 提示及退役 `fins.py` 常量、typed job 二次 WARN 固定标识、generic download job safe message 的后置边界；哪些 S1 plan S2 预设计由本独立 WU 承接、哪些仍由 S1 实现，逐项明示且实施前以 accepted+integrated HEAD 核对，不重写 typed summary。`fins-other-raw-diagnostics-audit` 的旧泛 generic job 登记按本项 download 切片 supersede，仅余非 download；文档索引同步。无「例如」文本或 pre-S1 `保持原形` 模糊验收。 |
| F3 低：EXECUTION 中已知 sibling 的 direct/job 安全诊断不对称 | **accepted 为已知残余并固定测试政策**。S1 对 revision conflict/repair blocked 暂保 EXECUTION，direct 可记安全 `unexpected_failure`；job typed catch 在 generic 之前，不记同一事件。这个不对称归 `fins-download-storage-sibling-errors`，S2 不借日志给它新业务分类。 | plan 用精确 direct/job×typed/generic 矩阵说明，测试不声称「所有 typed 均无事件」；未知 generic 路径仍有安全日志和无 raw durable message。 |

OQ1 **accepted 测试边界**：stdlib handler 自诊断 stderr 可有自身 stack，但只允许固定事件名/安全参数，不能有原异常消息/URL/路径；断言无原始异常到 `threading.excepthook`，不要求 stderr 绝无 `Traceback` 字样。OQ2 S1 未集成是真实硬依赖，不把本计划 conditional review 说成实施可执行；实施前按映射表重基线/重审。OQ3 direct/job unsupported source 文案差异登记独立 `fins-download-unsupported-source-public-consistency`，不在安全诊断 S2 改公开业务文案。异常链排除造成的诊断局限交 `fins-other-raw-diagnostics-audit` 后续判断，不偷偷把 raw cause 打日志。

Sol 下一轮仅修 plan；修订后 Kimi/MiMo 对同版有效 re-review。当前无产品实施、commit 或 PR 增量。
## Sol 修订候选状态（2026-09-29）

`issue198-s2-plan-fix-sol-20260929-01` 预检 `setup_status=ok`，显式 `/private/tmp/dayu-upload-issue198-s2`、独立 output/stderr/last-message，process exit0、JSONL `turn.completed`、canary `gpt-6-sol-c470cc84`，stderr 空；但 `git diff --no-index --check /dev/null ...` 对未跟踪计划返回 exit1，按严格协议 `agent_status=failed`，只采纳总控独立实读的候选文本。计划 SHA-256 `bed6c924b7ecb43c591ff05af39e9803a04590a349e4ef2761fe13e8d881798f`。F1 安全类型指纹与深栈可信帧、F2 S1→S2 七项 supersession/消费、F3 sibling direct/job 事件矩阵、OQ1 handler 自诊断、OQ2 S1 accepted+integrated 硬前置均已落候选文本；S1 仍未集成。下一步 MiMo/Kimi 对同版有效 plan re-review；本项产品未实施。

## MiMo 同版复审与总控裁决（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-s2-rereview-mimo.md` 对 SHA `bed6c924b7ecb43c591ff05af39e9803a04590a349e4ef2761fe13e8d881798f` 审查：预检 ok、绝对 cwd/独立 output+stderr，process exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `mimo-cff2015e`，stderr 仅白名单模型提示，`agent_status=completed`；结论 **fail**。F1–F4 均由总控按直接代码证据接受，计划仍在 fix gate，Kimi 有效第二路未齐，S1 accepted+integrated 前不得实施。

- **F1 中 accepted**：当前 `_download_public_failure_from_exception` 默认分支同时覆盖 unknown 和 direct `_UnsupportedDownloadSourceError`，直接替换 hint 会把 unsupported 文案改成指向并不存在的安全诊断。S2 只对 `EXECUTION` 且非 unsupported 的未知异常改用已定逐字 hint；unsupported direct 的现有 message/hint 逐字保持，实施前核对清单与真实入口测试同时钉住。unsupported direct/job 文案长期差异仍归独立 WU。
- **F2 中 accepted，纳入本 S2 owner 修复**：`_save_failed` 后 event-append WARN 与 `_emit_progress_event` 的失败日志在 download 路径仍可输出 `type(exc).__name__`，含秘密自定义类名可泄。既然 S2 goal 承诺未知 download 捕获路径的 operator 诊断无秘密且原 plan 声称 download 二次 WARN 已收口，应在同一 `ingestion_runtime.py` 日志 owner 将共享 event-append/progress 二次失败 WARN 收成固定事件标识、无动态 exception 类名/message/path/`exc_info`；这会使其它操作沿共用 helper 的日志也变安全，但不改变其业务状态/结果。测试在真实 download job 失败链注入 `job_store.append_job_event` 与 progress 保存失败的秘密类名异常，断言日志、job durable 和公开面均无秘密，且失败终态/取消仲裁不变。S1 typed WARN 旧合同仍保留，映射表明确三类下载二次日志覆盖范围；其它非 download 原始异常链仍由 `fins-other-raw-diagnostics-audit` 跟踪。
- **F3 低 accepted**：安全事件只在 `try` 正常结束后、`sys.exc_info()` 空且无正在传播的原/次异常时发射；禁止在 `except`、`finally` 或传播路径发射。补 RESULT 投递失败+handler 自诊断失败的双故障：S2 事件应跳过，不让它引出原业务异常链；RESULT 本身 failsafe 泄漏另归 `fins-direct-projection-failsafe`，断言和报告分开。
- **F4 低 accepted**：矩阵增 adapter wrapper 携非 typed cause 的防御形状：direct 按 EXECUTION 记一次，job 由 S1 typed catch 收口不记；业务分类问题仍归 sibling WU。测试该事件数，不把它误当 storage preflight。

OQ-B 三条终态 helper 去重在 S1/S2 集成后的 code review 按实际重复与 owner 再裁，不预造跨操作 god helper；OQ-C 安全栈单行格式补最小逐字示例以稳定日志解析和测试。Sol 只修本 S2 plan，然后 Kimi/MiMo 同版复审；产品未实施。

## Sol 第二轮修订候选与总控核对（2026-09-29）

`issue198-s2-plan-fix2-sol-20260929-02` 预检 ok、绝对 `/private/tmp/dayu-upload-issue198-s2`、独立 JSONL/stderr/last-message，进程 exit0、`turn.completed`、canary `gpt-6-sol-69a5f245` 匹配、stderr 空；一次复合 `sed` 因 review 文件路径/行域返回 exit1，严格协议 **agent_status=failed**。总控独立实读候选 SHA-256 `f3643583a29577e6aedbc87e52243028453c38dbd5834607011abd43ab1da4b8`：只对未知 EXECUTION 改 hint，unsupported direct 逐字不变；共享 event-append/progress 固定 WARN、正常 try 后且 `sys.exc_info() is None` 才记安全 ERROR、RESULT+handler 双故障跳过 S2 事件、non-typed cause adapter 矩阵及安全栈单行例均入 plan。S1→S2 映射与 accepted+integrated 前置仍在。此仅为待 Kimi/MiMo 同版复审的计划候选，**非产品修复或 gate pass**；若 S1 最终合同不同须重基线再审。

## 第二轮 Kimi/MiMo 同版计划复审总控裁决（2026-09-29）

Kimi `docs/reviews/plan-review-20260929-100231-s2-rereview2-kimi.md` 与 MiMo `docs/reviews/plan-review-20260929-100903-s2-rereview2-mimo.md` 均对 SHA `f3643583...da4b8` 进程 exit0、结构化 success、canary `kimi-ac5cdf23` / `mimo-712e84dd` 匹配，stderr 仅白名单提示；两路结论 **fail**。两路实读现有 Fins/CLI/runtime owner；旧 hint、supersession、深栈、安全类型与 non-typed cause 矩阵的主体方向成立，但当前计划 gate 未过。总控接受以下修复项，并保持每项未修复直至同新版复审：

- **S2-PR2-F1（中，Kimi）**：共享 `_append_job_event_warn`/`_emit_progress_event` 在活动业务异常内二次失败，若因 `sys.exc_info` guard 抑制日志，则原计划所要求的固定 WARN 出现断言在真实 download 链必失败；若在原 catch 中直接 logger，则 handler 自诊断可能复制业务异常链。总控选择安全优先的最小合同：活动异常期仅抑制该二次 WARN（不调用 logger），保留业务结果/终态，不发明跨操作暂存队列；在正常无活动异常调用点仍用固定事件标识记录。计划须把“活动异常期该诊断会被抑制”明确列为已知可观测性取舍，并把注入验收改为断言无秘密、无异常链、业务终态不变、该路径 WARN 缺席符合合同。primary unknown download 安全事件仍须在 try 后可达且实际发射。若 owner 证据显示同一共享 helper 的正常路径仍泄漏，另行处理，不把非 download 原始异常审计吞入 S2。
- **S2-PR2-F2（低，Kimi）**：`sys.exc_info()` 始终是三元组；四处 `sys.exc_info() is None` 恒假。统一精确为 `sys.exc_info()[0] is None`，测试断言“无活动异常且事件确实发射”，不能仅断言前者。
- **S2-PR2-F3（中，MiMo）**：plan 自锁的 S1 HEAD/三产品未提交 diff SHA 在同轮复审期间已变，且“S1 typed job catch 未落地”的现状陈述已假。S1 accepted plan `47a9cb64` 与正在实施的候选不能冒充 integrated HEAD。待 S1 代码评审、accepted slice 与 PR 集成稳定后，按实际 HEAD/符号/行为逐行重基线，删过期未提交 SHA 锁或更新为可核证集成值；七项 supersession 映射须重新实读确认，不凭当前兼容判断提前实施。
- **S2-PR2-F4（低，MiMo）**：CLI 现有 generic except 直接 render/return，不能在 except 外发安全事件又保持“发射先于 stderr”而不改控制流。计划钉死 generic except 仅暂存安全串、固定事件名、待渲染消息/退出码；try 正常收口后检查 `sys.exc_info()[0] is None` → 发射 → render → return；typed except 保持旧 render/return。测试同时验证时序、固定 stderr/exit 与 handler 自诊断无原异常链。

MiMo 的矩阵非 typed cause 前提、栈压缩断言按性质而非密度、取消竞争事件计数列实施检查点，不扩业务目标。S1 当前仍未 accepted+integrated，**S2 plan gate fail，下一 entry 为等待 S1 稳定后的 Sol plan 重基线/fix，再 Kimi/MiMo 同版 review；S2 产品不得实施。**
