# UM-O17-F01 plan review 裁决

- 工作区 `/private/tmp/dayu-upload-o17`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。MiMo `docs/reviews/plan-review-20260929-030208.md` 进程 exit 0、JSON success、canary `mimo-ec49a3b5` 匹配、stderr 仅白名单模型提示；其逐层 owner 链无架构反例。Kimi 同轮 HTTP 403、exit 1、`is_error=true`，provider failure，无有效第二路。Sol 初 plan 三条失败 command，`agent_status=failed`，只作候选。当前 gate **plan review → fix**，未实施。

## Finding 与裁决

1. **F1 accepted/medium**：`FinsUploadMaterialRequest.form_type` 可为 `None`，而候选 `normalize_material_form_type(str)` 不能无条件调用；本项不得提前实现 O05 的 form 必填 typed usage。计划明确纯 canonical 函数仅对有效非空文本执行 `strip().upper()`，不承诺对 None/空白的使用错误新分类；material admission 对 `None`/空白保留现有后续失败边界，仅对有效文本替换成 canonical request。身份 builder 复用同一函数并保留既有空值拒绝；O05 合并后由其 owner 前置 typed 拒绝空白。测试锁定有效值同源、None/空白不被本切片变成新 typed 承诺，避免旧持久 job 时序被无意改写。
2. **F2 accepted/low**：真实 CLI 配对除 write 侧 source meta/manifest 外，还要用单独只读/跨命令读取路径核对同一 canonical form 与 ID；按当前公共 read 能力选择可执行命令，不假造不存在的字段。记录 argv/exit/双流/读回 artifact，若 read API 仅返回摘要不含 form 则明确查询受支持的 source meta read owner，不用显示层推断。

计划需消除“本函数拒绝空白/O05 已共享本函数边界”的提前实施暗示，锁定本隔离 checkout 的 Python3.11 venv/`dayu.__file__`，逐被改文件 coverage；其它 O07/O10 集成条款保留。Sol 修订后等有效 Kimi/MiMo 双路 re-review，不能凭当前单路进入实现。

## MiMo 第二次 plan re-review 总控裁决

`docs/reviews/plan-review-20260929-033846.md`：exit 0、结构化 success、canary `mimo-be6b9dbc` 匹配、stderr 仅白名单提示。原 F1/F2 均闭合，单一 form canonical owner、四入口有效值、ID/event/meta/manifest/result 同源、跨命令仓储读回、锁定 venv 与逐文件 coverage 方向成立。本轮新增低 finding：已有 raw form 的历史 source 被 skip/delete 时，新事件可能 canonical 而旧 meta 保留 raw。总控接受此**历史状态范围风险**并归已登记的 `fins-material-legacy-identity-seed-disposition`；本 O17 只承诺本修复后新写/同版状态，不做旧数据迁移。plan 验收句应明示该范围；不接受把「旧 meta 保持 raw、新事件 canonical」写成 owner 级通过测试，它会把不一致固化成合同。若集成需要处理存量数据，必须在独立 legacy WU 裁决 owner 级迁移或全新起算，不能在 read/事件层 fallback。

coverage 口径：每个实际改动生产 `.py` 文件单独 >=80%，在同一 checkout 锁定 Python3.11 环境对受影响测试量基线，再扩大到相关既有测试直至达标；不能用总体 coverage、测试镜像或「报告阻塞」宣告完成。README 若职责命中，用户已授权修复，可依 AGENTS.md 触发规则扩计划白名单并在实施时更新，不把“先申请扩大白名单”理解成要求重复征求用户授权。Kimi 403 仍无有效第二路；Sol 仅修 plan 范围文字后重新双路复审，不实施。

Sol 第二次 plan fix `o17-plan-fix2-sol-20260929-01` 进程 exit 0、JSONL `turn.completed`、28 条 command exit 0、无 error event/stderr、canary `gpt-6-sol-ad7e1bb8` 匹配，**agent_status=completed**。候选 plan SHA-256 `37d1c13e98e4db78d9ce02afe2dd6e92c53cead7e544690daa84e8845c4a3baf`，只改本 plan；总控复核第 42/49 行将验收限制为新写/同版材料、历史 raw form 明确归 legacy WU，不写旧不一致通过测试；第 22/31/38/40 行 README 条件白名单和逐文件 coverage 满足裁决。下一 gate 待 Kimi 额度恢复后与 MiMo 同时有效 plan re-review，产品未实施。

MiMo 第三次同 SHA plan re-review `docs/reviews/plan-review-o17-rereview3-mimo-20260929.md`：进程 exit 0、结构化 `subtype=success/is_error=false/terminal_reason=completed`、canary `mimo-271a5124` 匹配，stderr 仅白名单模型提示；结论 `pass-with-risks`、零 finding。三个 open question 属实施精度：admission 的有效值 guard、canonical 后异常/时序断言、跨命令读回的实际字段与顺序，实施任务需明确。六项 residual risks 中历史 raw form 仍归 `fins-material-legacy-identity-seed-disposition`，覆盖率门槛继续是实施硬条件。Kimi 同版 session `18650` HTTP 403、进程 exit 1、`is_error=true`，无有效第二路；**plan gate 未通过**，等额度恢复对同 SHA 新标签复审，产品未实施。

## Kimi 同版复审与新修复项

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Kimi `o17-plan-final-kimi-20260929-01` 锁定同一 plan SHA `37d1c13e...`，JSONL `turn.completed`、canary `kimi-5959955d` 匹配，stderr 空；原 exec session 在会话中断后失效，退出码无法回读。`docs/reviews/plan-review-20260929-164227.md` 自报一条错误路径 `sed` exit1、两次 `apply_patch` 工具失败，严格 `agent_status=failed`，不能计有效第二路。内容 `pass-with-risks` 仍由总控核对；唯一函数全链、None/空白 O05 边界、真实仓储读回与历史 raw 隔离的正向结论成立。
- **PR4-F1 低，accepted／未修复**：O09-F01 已裁决的 fiscal_year 域校验与 O17 同属 `build_material_ids` 的 before-seed owner/插入点；计划的串行集成清单只列 O05/O07/O10。补 O09 依赖登记及实施前按最终 HEAD 复核，不在 O17 偷做 fiscal 校验。该遗漏不是当前 form 语义冲突。
- **PR4-F2 低，accepted／未修复**：计划 slice 7 写 tool 的“observation/request 投影”断言 form，但当前 `FinsObservationSnapshot`、`FinsUploadResultSummary`、`_upload_result_details` 均无 form 字段。测试应锁真实事件流/结果 JSON 的 form 值与 runner 接收的准入后 request 值；不得给 observation snapshot 造字段或写空断言。
- Sol 只修两处 plan 与新 fix artifact，再锁新版 Kimi/MiMo 独立复审。O17 产品未实施，O05/O06 仍等待其 accepted+integrated。

## Sol PR4 计划候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o17-plan-fix-pr4-sol-20260929-01` 进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-f515a38a` 匹配、stderr 空；一次误写 `ingestion/ingestion_runtime.py` 的 rg exit2，严格 `agent_status=failed`，不能计有效 Sol gate。总控实读新计划 SHA `7c818f9dbc2a8276b5a47a49918307efb8437823b6c2cb677b3743b1e34eacd8` 与 `docs/gateflow/upload-material-o17-plan-fix-pr4-20260929.md`：O09 在 `build_material_ids` 的 before-seed 串行点、最终 HEAD 复核已登记；slice 7 指真实 tool runner request、material 事件与结果 JSON form，明确无 form 的 observation/result summary 不作断言。**PR4-F1/F2 计划内容候选已修**；唯一函数/O05/历史 raw/coverage 边界未回退。下一 gate 同 SHA Kimi/MiMo 双路复审，产品未实施。
## PR5-F1 batch material form 的同源规范化（MiMo 复审后登记）

- MiMo 对 PR4 SHA `7c818f9d...` 的 review artifact `docs/reviews/plan-review-o17-pr4-mimo-20260929.md` 已落盘，进程 exit0；结构化终态与 Kimi 同版仍待收齐。总控实读 `upload_batch.py::_validated_material_form`、CLI `_single_batch_material_form` 和 `build_material_ids`：三处当前分别做 `.strip().upper()` / `.upper()`，且 batch 产出的 `UploadBatchMaterialEntry.form_type` 会进入单份 `upload_material --forms`。用户已经明确要求 form 类别处理收敛到一个函数供其它调用点复用。
- **PR5-F1 低，accepted／未修复**：O17 plan 的 canonical helper 白名单遗漏 batch 入口。计划须把 batch form 的文本规范化改为复用唯一 `normalize_material_form_type`，仍由 batch owner 验证封闭 routing 值域；CLI `_single_batch_material_form` 只负责解析基数/空值，不再独立 `.upper()`，或明确传原值到共用 helper 并测试同一 canonical 值。增 batch typed entry → 生成 `--forms` → material request 的同值断言。不得在 CLI 再建业务兼容分支；如存在不同语义须一手证明后再裁决。此项先修计划，非产品实施。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- MiMo `o17-plan-pr4-mimo-20260929-01` 进程 exit0、JSONL 201 条可解析、`turn.completed`、92 条 shell exit0、无 error/failed event、stderr 空、canary `mimo-b316ea71` 匹配；但本次任务正文额外要求所有检查命令 exit0，三条探索命令分别 exit1/5/1。按该次合同 `agent_status=failed`；内容 `pass-with-risks` 与 PR5-F1 作总控候选证据，不计同版 plan gate。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Kimi `o17-plan-pr4-kimi-20260929-01` 进程 exit0、JSONL 166 条可解析、`turn.completed`、68 条 shell exit0、无 error/failed event、canary `kimi-84ae6c04` 匹配；stderr 有两次 `apply_patch` 格式校验 ERROR，review artifact 如实披露，按本次额外工具成功合同 `agent_status=failed`。其 `docs/reviews/plan-review-o17-pr4-kimi-20260929.md` 内容 `pass-with-risks`、零新 finding，仅供总控核验；MiMo 的 batch 同源 PR5-F1 已接受，Sol 新计划修订在途。

## Sol PR5-F1 计划修订候选

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o17-pr5-f1-sol-20260929-01` 进程 exit0、JSONL 116 条可解析、`turn.completed`、48 条 shell exit0、stderr 空、canary `gpt-6-sol-7c447486` 匹配；一条探索 `rg` exit1 在 JSONL 中仍是 `item.status=failed`，按 `$sub-agents` 条件**更正**先前 completed 为 `agent_status=failed`，不计 Sol gate。总控实读计划新 SHA `7b37c7279183bf56af2acfe722062f4b768a1f2e868eb96db37721d2578dbe24` 与 `docs/gateflow/upload-material-o17-plan-fix-pr5-20260929.md`：batch `_validated_material_form` 复用唯一函数后验证封闭 routing 值域；CLI batch 仅解析空值/基数、返回原候选；typed entry→argv→runner request 同值测试及文件白名单已补。**PR5-F1 计划内容候选已修**，同 SHA Kimi/MiMo 独立复审在途。实施时须验证 `_normalized_text_tuple` 当前会 strip，不可调用该函数后声称返回原始空白；plan 已明确改为保留原始候选，review 应查其可实现性。

## MiMo PR5 同版反例裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- MiMo `o17-pr5-mimo-20260929-01` 进程 exit0、JSONL 160 条可解析、`turn.completed`、70 条 shell exit0、canary `mimo-d2f92a18` 匹配；四条探索命令 exit2/2/1/1 形成 `item.status=failed`，故不计有效 plan gate。`docs/reviews/plan-review-o17-pr5-mimo-20260929.md` 内容 fail。总控直接核 `sec_upload_workflow.py:468-475`、`cn_pipeline.py:1087-1096` 与 CLI `_normalized_text_tuple`，接受以下两项 **未修复**，须先 Sol 修计划再同版复审；Kimi 旧 SHA 仍在途。
- **PR6-F1 高，material stream 首错时序**：现行 SEC 先 `normalize_ticker`/market，CN 先 ticker/company identity，之后才 `build_material_ids` 检 form。PR5 plan 写“stream 顶端”调用新函数会在非法 ticker/market 与空白 form 并存时提前报 form，违反 O17 goal 的失败时序边界。计划明确定位为保留现有 ticker/market/company 及其它既有首错后、ID/started/公司批次前；`build_material_ids` 内 form/name/period 多非法组合也要保持现行优先级。补 direct stream 双非法首错与零生命周期/发布断言，不扩大 O05。
- **PR6-F2 中，CLI raw 候选与空/多值顺序**：当前 `_normalized_text_tuple` 对每个 item `.strip()` 后返回，PR5 plan 却要求 `_single_batch_material_form` 把两端空白原样交 batch owner，未钉 raw parser 算法；直接复用旧 helper 会丢 raw，先判多值又会让 `['a','']` 首错由空值漂移。计划指定独立机械 raw-preserving split loop：先逐 item 用 stripped 副本判空但保存 raw，完整扫描后判多值；不得更改单条 `--forms` 解析。增 `None`、空列表/字符串、纯空白、空值与多值竞争、padded 大小写、regeneration argv 的矩阵测试。CLI 不做 form upper，batch owner 唯一函数处理有效文本。

## Kimi PR5 同版测试白名单反例

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Kimi `o17-pr5-kimi-20260929-01` 进程 exit0、JSONL 176 条可解析、`turn.completed`、64 条 shell exit0、无 failed/error event、stderr 空、canary `kimi-0704836b` 匹配。`docs/reviews/plan-review-o17-pr5-kimi-20260929.md` 内容 fail，提出一项新增中风险 finding；总控实读 `tests/cli/test_upload_filings_from_command.py:197-236` 与 plan 白名单确认，接受 **PR6-F3 中／未修复**：既有测试断言 `--material-forms " esg_report "` 到 batch request 已 upper/strip 且错误 echo canonical；PR5 承诺传 raw 后两断言确定性改变，而 plan 测试白名单只列 `tests/cli/test_fins_commands.py`（direct CLI），漏真正 `upload_filings_from` 命令测试。将 `tests/cli/test_upload_filings_from_command.py` 纳入 O17 实施白名单，更新该测试的 owner 级预期为 raw 候选由 CLI 机械传递、batch owner 统一 canonical/封闭分类，断言实际错误/无副作用；不得在产品保留旧 CLI upper 只为保旧测试。Sol PR6-F1/F2 已在独立 clone 运行，F3 须随后补进同版计划并复审，不得越过。
