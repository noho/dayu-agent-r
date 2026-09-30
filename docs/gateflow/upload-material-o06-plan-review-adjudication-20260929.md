# UM-O06-F01 计划审查裁决登记

- 2026-09-29 用户已确定 `material_name` 按 `len(name.strip())` 最多 240 个 Unicode 码点；本项只可在同一 Fins admission owner 实施，O05 必填与 O17 form canonical 是前置依赖。
- Sol 计划候选 `upload-material-o06-name-length-plan-20260929.md`，SHA-256 `fd95ede94a6746da266630661b8802c564c556357c8aa882d8dbd1fe9fc24400`。进程 exit 0、JSONL turn.completed、canary `gpt-6-sol-47de4437` 匹配，但查询不存在的 O16 路径有一条 command exit 1；按 sub-agents 协议 `setup_status=ok, agent_status=failed, tool_evidence=yes, canary_status=match, retry_class=none`。总控独立读到计划文件，只作待审候选，不视为 plan gate pass。
- 总控预审待双路反证：共同 validator 是否确实能覆盖 direct、observation、job 以及独立 US/CN/HK workflow，尤其 workflow `try` 前 typed 错误；O17→O05→O16→O06 的顺序是否为真实代码依赖；schema 的 optional 类型与“必填”描述是否在 O05 集成后同源；真实 CLI 通过原件及 `.venv` 是否可达；`strip()` 只用于计数、不改变身份是否与现有输入投影一致。不能因计划声称前置顺序就倒逼其它 work unit。
- 下一步：Kimi/MiMo 对同一 SHA 独立 `$planreview`，总控检查结构化结果并裁决。产品未改。

## MiMo 同版 plan review 与跨项 owner 裁决（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-o06-mimo.md` 对 SHA `fd95ede94a6746da266630661b8802c564c556357c8aa882d8dbd1fe9fc24400` 进程 exit0、结构化 success、canary `mimo-31c0eb33` 匹配，stderr 只有白名单模型提示；结论 pass-with-risks，2 中/3 低 finding。Kimi 同版进程 exit1、JSON `is_error=true/terminal_reason=api_error`、HTTP 403 五小时额度，未写有效 artifact、未完成审查，不算第二路。**plan gate 未通过**。

- **O06-PR-F1（中，接受并归 O05 owner 前置）**：独立 US/CN/HK workflow 可绕过 runtime 的 O05 必填校验。若 O06 在它们的 ID 前仅调用“非空 `str` 专用长度叶子”，空串/纯白可进入 `build_material_ids` 的 raw `ValueError`，与 runtime 的 O05 typed usage 分叉。O05 goal 的唯一共同 admission owner 应覆盖这些公开 pipeline 入口；其当前候选计划白名单却不含两个 workflow，已在 O05 adjudication 另登记 C2。O06 实施须消费**同一个完整 O05+O06 名称 admission 函数**或已经验证的共享准入对象，不复制空值分支、不只调用长度叶子；workflow 空值、240/241 均在 ID/started/业务读写前同源 typed 拒绝。O05 修订与集成前 O06 不能实施。
- **O06-PR-F2（中，接受）**：O16 action/files 与 O06 超长名称同时非法时优先报 O16 的静态动作/文件组合错误，再报 O05 必填、O06 长度；对 O05 form/name 双空维持 form 优先。与 O16 共享 owner 实际调用顺序合流，在 direct、job、observation、独立 workflow 加 joint-invalid owner 断言；不得让集成顺序决定输出。因该共同 owner 顺序，保留 O16 accepted+integrated 为 O06 implementation 前置有直接行为理由。
- **O06-PR-F3（低，部分驳回）**：MiMo 认为 O16 前置纯属无功能依赖，所引“无 plan/未排期”是旧队列状态；本时点 O16 已到第五版同 SHA plan review。F2 的联合非法错误优先级和同一 `_normalize_upload_request` owner 使串行先合 O16 更可审计，保留依赖，但计划必须写明这条具体行为依赖，不只笼统说避免冲突。
- **O06-PR-F4（低，接受）**：同源 usage message 除一致外还须自足说明去首尾空白后的 240 Unicode 码点上限和可行动修正；schema 与错误两处均由同一业务规则表达，测试断言要素，不以“名称过长”空泛文案验收。
- **O06-PR-F5（低，接受为独立发现）**：`upload_filings_from` 的 `dayu/fins/upload_batch.py:_derive_material_name` 可从合法文件名派生超过 240 码点的脚本参数，生成脚本成功、执行时统一 admission 拒绝。此处 owner 是**批量脚本生成时的 material 名称投影**，不是 O04/O23 原件→Docling 资产文件名；在总队列新增 `fins-upload-batch-derived-material-name-admission`，依赖 O06 同源规则，不允许 batch 侧截断/另造阈值。本 O06 plan 在 README/残余中说明该交互，不扩大其产品白名单。

下一 entry：Sol 只修 O06 plan，明确 O05 C2 与 O16 的实际集成前置、联合非法优先级、消息内容/测试、batch 后续 owner；再同版有效双路复审。产品未改。
