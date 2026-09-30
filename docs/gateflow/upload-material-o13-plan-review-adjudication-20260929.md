# UM-O13-F01 plan review 总控裁决

- Gate：`plan review -> fix`，候选 `docs/gateflow/upload-material-o13-tombstone-plan-20260929.md`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，产品未实施。
- MiMo `docs/reviews/plan-review-20260929-043830.md`：预检 ok、显式 `/private/tmp/dayu-upload-o13`、独立 output/stderr，exit0、Claude JSON `subtype=success/is_error=false`、66 turns、canary `mimo-e69db9e8` 匹配，stderr 仅模型名白名单提示，`agent_status=completed`。Kimi 有效第二路尚缺，不能放行 plan。

## findings 与修复登记

| Finding | 总控裁决 | plan 修订与完成信号 |
| --- | --- | --- |
| F1 高：隔离 checkout 无 `.venv`，主工作区 `dayu-cli` 导入错误代码 | **accepted**。reviewer 已直接实测 `dayu.__file__` 指向主工作区，真实 CLI 证据身份必须先修。 | 实施前在本 checkout 用 Python 3.11 与锁定依赖建立独立 `.venv` 并安装本 checkout；每次真实 CLI 前记录/断言解释器、`dayu.__file__`、checkout HEAD 与 CLI console script 指向同一 checkout。主工作区 venv 不可冒充；环境装不成则验证 gate 停止。 |
| F2 中：该测试集单文件覆盖率基线 79%，原计划“两处边界测试足以”无依据 | **accepted**。407 passed 不等于 >=80 覆盖。 | 明记 reviewer 的 473 statements/97 misses/79% 基线；参数化真实仓储测试覆盖 filing/material 首删、重复删除、恢复和新周期，并补当前未覆盖且与同一状态 owner 相关的 filing restore/update 路径，不为凑数写实现镜像测试。实施后逐文件 coverage >=80；若仍未达标，补 owner 级有意义的状态转换用例并重新 review，不降低门槛。 |
| F3 中：no-op 用 raw `meta.get('is_deleted') is True` 自立读者，损坏值会被覆写 | **accepted**。项目 `require_source_meta_is_deleted` 是唯一精确读取真源。 | `_toggle_source_deleted` 读取 meta 后先调用该 helper；缺失或非 bool fail closed，不新造 tombstone 时间，不走覆写修复。加入损坏值 owner 测试断言无 source/meta/manifest 业务更改；此为已有 README/完整性合同直接执行，不是另造兼容分支。 |
| F4 低：delete 无 `DocumentHandle` 返回；固定时钟不能区分一次/两次取时 | **accepted（缩小测试合同）**。 | delete 只从仓储读取/locator、source meta、manifest 断言；`DocumentHandle` 只在 restore 返回值上断言。用户确认的是同周期重删时间不变，**未要求首次删除的 `deleted_at` 与 `updated_at` 必须逐字相等**；移除计划中“首次 delete 只调用一次时钟/两字段同值”的新验收，不为其写步进时钟实现测试。现有首次删除两次取时行为可保持，重删不得取新时间或写 source。 |

Review Q1 重复 restore-on-active 非幂等是另一状态合同，登记为后续 `fins-source-restore-active-idempotency`，不在 O13 扩权；O14/O15 状态前置与 O18 amended 合流时核对。Q3 **accepted**：计划明确同周期 no-op revision 不变，首删/恢复/新周期真实转换 revision 翻新，测试断言语义而不固定 UUID。物理 batch copy/swap、文件 mtime/inode 不在本业务字节合同；O33 并发仍独立。

Sol 下一轮只修 plan，之后有效 Kimi/MiMo 双路 re-review；不得据当前单路结果实施或提交。所有修复项已落本 artifact，并同步主总控队列。

## 总控追加裁决（README 实施白名单）

Sol 首次 plan fix 候选 `56411bf07213167397fa99c0f8c04f303b0083cc4c2c874469ceb75b712a57d3` 已识别 `dayu/fins/README.md` 的状态契约需要同步更新，却仍把实施文件白名单限定在一个产品文件和两个测试文件，并将 README 纳入范围留给实施前再次裁决。这会令已确认的必需文档工作在实施 gate 被白名单阻断。**accepted F5**：本轮 plan 修订直接把 `dayu/fins/README.md` 列入允许且必需的实施文档，说明按已读的 README 更新约束，仅在实现状态转换后同步修正重复 tombstone/no-op、revision 和损坏 `is_deleted` 的描述；其余 README 仍按触发条件检查。不提前改 README 正文，不扩大产品代码白名单。Sol 再修 plan，然后有效双路复审。

Sol 第二次 plan fix `o13-plan-fix2-sol-20260929-01` 预检 ok、显式 checkout、独立 output/stderr、process exit0、JSONL turn.completed、canary `gpt-6-sol-dd64fe14` 匹配、stderr 空；但 `ls -ld .venv ...` 因未创建的 `.venv` 返回 1，按执行协议 **agent_status=failed**，报告只作候选。总控独立核对 plan SHA `fd7fef7080f48a6b208d12d0ecfad10009157618f05cf854186ceaf539690396`，F5 已直接列 README 为实施白名单第 4 项并删除再次裁决阻断句，F1-F4 保留；该工作树无产品/测试/README 正文改动。待 Kimi/MiMo 有效双路 plan re-review，不计单路通过。

## MiMo 第二轮同版 plan re-review 与总控裁决

MiMo label `o13-plan-rereview2-mimo-20260929-01`、显式绝对 O13 checkout，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、canary `mimo-1455ffb9` 匹配、stderr 仅白名单 model 诊断；`setup_status=ok, agent_status=completed, tool_evidence=yes, canary_status=match, retry_class=none`。artifact `docs/reviews/plan-review-o13-rereview2-mimo-20260929.md` 已实读。对计划 SHA `fd7fef70...` 复测 407 passed、owner 文件覆盖率基线 79%，F1–F5 在计划层成立；结论 pass-with-risks，但新增两处低规格缝隙，按同一 owner 直接代码裁决 **接受并保持 plan review -> fix**：

1. **O13-PR2-F1 低 accepted**：`_toggle_source_deleted` 的 `require_source_meta_is_deleted` 应对 delete 与 restore 均先行；损坏/缺失值无论方向均 fail closed，不可在 restore 时以赋值 False 静默治愈。状态表补 restore 行，真实仓储损坏 meta 测试参数化两方向、断言无业务字节变化。与当前 `dayu/fins/README.md:101` 的统一精确读取合同一致，不扩 goal 动作语义。
2. **O13-PR2-F2 低 accepted**：缺失字段可由 canonical helper 抛 `KeyError`，当前公开 `fs_source_document_repository.py` 与 `repository_protocols.py` 的 delete/restore docstring Raises 未列。实施白名单增加**仅这两处 docstring**同步（连同必要的 `dayu/fins/README.md`），或计划精确指出若现有 Raises 已覆盖该类错误的证据；不得在 core 中为配合旧文档把 `KeyError` 随意翻译成另一原因。新增测试断言缺失/非布尔各自真实异常及字节不变，生产行为仍只在 `_fs_source_document_core.py` owner。

review Q1：`document_models.py` 的 `from_source_meta` 仍用 raw `meta.get("is_deleted") is True` 投影 tombstone，与唯一 reader helper 有潜在 drift；本 O13 的重复 delete 修复不顺手扩大投影路径，登记独立 `fins-source-meta-is-deleted-reader-contract`，待 O14/O15 同版 storage guard 合流时实读是否仍可接触损坏值。若真实路径可吞损坏 meta，须在原 reader owner 修，不能靠下游默认值。Q2 corrupt meta 的公开失败映射归既有 O14/O15 typed 目标前置，不在 O13 自造 reason。Kimi 对新计划的有效第二路尚缺；Sol 只修 F1/F2 计划后同版双路复审，产品未实施。

## Sol PR2 计划修订核验

label `o13-plan-fix-pr2-sol-20260929-01`：预检 ok、显式绝对 `/private/tmp/dayu-upload-o13`、独立 JSONL/stderr/last-message/canary；进程 exit0、JSONL `turn.completed`、27 条命令全 exit0、stderr 空、canary `gpt-6-sol-9f842ba3` 匹配，严格 `setup_status=ok, agent_status=completed, tool_evidence=yes, canary_status=match, warnings=[], retry_class=none`。修复报告 `docs/gateflow/upload-material-o13-plan-fix-pr2-20260929.md` 已实读，计划 SHA-256 `5b02d9e62362a2dd88006a25dffab76803983bfcb2cb488aa5bea34add7c5d58`。

总控接受此**计划候选**：delete 与 restore 均在改写/no-op 前调用 canonical `is_deleted` reader，缺失/非 bool fail closed；真实仓储测试覆盖两方向、异常类型及字节不变；实施白名单仅为仓储/协议 delete/restore 的 Raises docstring 加两处文件，不扩产品行为。原 F1–F5 与独立 reader follow-up 保留。仍须 Kimi/MiMo 对同 SHA 有效复审；产品、测试和 README 正文均未实施。

## MiMo 第三轮 plan re-review 与总控裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

MiMo label `o13-plan-rereview3-mimo-20260929-01`，显式绝对 O13 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、53 turns、canary `mimo-3182bdce` 匹配。artifact `docs/reviews/plan-review-o13-rereview3-mimo-20260929.md` 已实读，锁计划 SHA `5b02d9e6...`；结论 pass-with-risks。PR2-F1 双向 fail-closed、真实仓储测试与原 F1–F5 的计划合同均成立，但另有两项低缺口。总控实读 `docling_upload_service.py:447-453,560-603,858-889` 与 `document_models.py:168-176` 后作如下裁决：

1. **O13-PR3-F1 低 accepted**：delete 的 `prepare_upload` 不读取 `is_deleted`，损坏 meta 的 `KeyError/ValueError` 首次可经 `publish_prepared_upload`→`_delete_source_document` 公开冒出。当前两者 Raises 分别缺 `KeyError` 或 `KeyError/ValueError`，原仓储/协议两文件 doc-only 白名单不够。计划增加 `dayu/fins/pipelines/docling_upload_service.py`，**仅**这两个方法的 Raises docstring 同步真实异常类型，兼顾现存 `FileNotFoundError`；不改服务行为或在下游翻译异常。
2. **O13-PR3-F2 低 accepted**：同一 `KeyError` 不仅由缺 `is_deleted` 触发，真实 `_prepare_complete_source_meta`→`SourceDocumentProvenance.from_meta` 的 `meta["ingest_method"]`/`meta["source_provider"]` 缺失亦触发。仓储、协议及上述服务 Raises 文案写“source meta 缺少必需字段（含 is_deleted 与 provenance）”，`ValueError` 写非布尔/非法值，不把文档缩窄为新修的一种字段；不改变当前 exception owner。

MiMo 的 R9 no-op provenance 重校验疑点已有计划的 commit 完整校验与证伪停点，暂作为实施期真实仓储测试风险，不另添当前行为。独立 `fins-source-meta-is-deleted-reader-contract`、O14/O15 typed 映射、O33 并发均保留。Sol 仅修上述计划/白名单文字后同版 Kimi/MiMo 复审；产品未实施，不能将 MiMo 单路 pass 算 gate pass。

## Sol PR3 计划修订候选核验

label `o13-plan-fix-pr3-sol-20260929-01`：预检 ok、绝对 O13 workspace、独立 JSONL/stderr/last-message/canary；进程 exit0、JSONL `turn.completed`、27 完成命令中一条自写静态断言 exit1，另有一次工具脚本语法错误发生于 shell 启动前；canary `gpt-6-sol-74ec2d44` 匹配、stderr 空。严格 `setup_status=ok, agent_status=failed, tool_evidence=yes, canary_status=match, warnings=[], retry_class=none`，修复报告 `docs/gateflow/upload-material-o13-plan-fix-pr3-20260929.md` 只作候选。总控实读计划 SHA-256 `bb4542115c8823ba2f754768bd15dfbf8ac081d19eba32aeeaaa663ed5af03c8`：服务文件仅两方法 Raises docstring 纳白名单；仓储/协议/服务的 `KeyError` 覆盖缺 `is_deleted` 与 provenance 必需字段，`ValueError`/`FileNotFoundError` 同真实传播；不改行为、旧门槛或独立残余。待同版 Kimi/MiMo plan re-review，产品未实施。
- 2026-09-29 MiMo PR3 同版 `$planreview`（label `o13-plan-rereview4-mimo-20260929-01`）锁计划 SHA `bb4542115c8823ba2f754768bd15dfbf8ac081d19eba32aeeaaa663ed5af03c8`，进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、50 turns、canary `mimo-e95f5a50` 匹配、stderr 仅白名单模型提示；但 artifact `docs/reviews/plan-review-20260929-131155.md` 明列一次 zsh 解析 `===` 的复合 shell exit1。严格 `setup_status=ok/agent_status=failed/tool_evidence=yes/canary_status=match/retry_class=none`，内容结论 pass-with-risks 不计有效 plan gate pass，Kimi 同版第二路亦缺。
- **PR4-F1 低，accepted／未修复**：计划白名单第 1 项只泛称在共用 `_toggle_source_deleted` owner 补 Raises，未点名同文件 `delete_material`、`restore_material`、`delete_filing`、`restore_filing` 四个直调入口；实读其现有 Raises 均无 `KeyError`，而 canonical reader 缺 `is_deleted` 与 provenance 字段的 `KeyError` 可沿该路径冒出。为使 AGENTS.md 完整 docstring 合同与真实传播链一致，实施白名单须在同一 core 文件明确四入口同步完整 `KeyError`/`ValueError` 原因及保留已有异常，无行为改动；服务/协议 doc-only 第 5–7 项仍按 PR3 修订，不扩到 CLI/adapter。
- MiMo 的 update 路径 `publish_prepared_upload` 异常原因措辞 Q1 归实施 code review 核对：最终 Raises 不应误限定为仅 delete；现计划的通用缺字段/非法值用语足以覆盖，暂不扩 scope。其它残余同前。下一 gate 为 gpt-6-sol 仅修 PR4-F1 计划与新 fix artifact，再用新 label Kimi/MiMo 对相同最终 SHA 复审；O13 产品未实施。

## Sol PR4 计划修订候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o13-plan-fix-pr4-sol-20260929-01` 显式绝对 O13 workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、23 完成 shell 命令全 exit0、stderr 空、canary `gpt-6-sol-5ef576dc` 匹配；其最终消息披露一条 `functions.exec` JavaScript 包装调用在 shell 前因语法错误失败。按全工具执行协议严格 `agent_status=failed`，不能仅按 shell 命令集改判 completed。修复 artifact `docs/gateflow/upload-material-o13-plan-fix-pr4-20260929.md` 只作候选。
- 总控实读计划新 SHA `ce9f3e7a55d17afb2894bd0d4eb98c4b051214abfe4500ba7d40a759f4a7870c`：白名单第 1 项明确 core 四入口和 `_toggle_source_deleted` 的 `KeyError`/`ValueError` Causes、保留既有异常；第 7 项 `publish_prepared_upload` 的通用原因不限定 delete。PR4-F1 内容候选已修，尚待有效 Kimi/MiMo 同版 `$planreview`，无 O13 产品修改。

## MiMo PR5 同版复审与严格结果

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro；按精确白名单为非致命诊断"
retry_class: none
```

- `o13-plan-rereview5-mimo-20260929-01` 显式绝对 O13 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `mimo-b660d8ac` 匹配。review artifact `docs/reviews/plan-review-20260929-133330.md` 锁同一计划 SHA `ce9f3e7a55d17afb2894bd0d4eb98c4b051214abfe4500ba7d40a759f4a7870c`，内容 pass-with-risks、零新 material finding，PR4-F1 内容成立。
- 该 artifact 如实披露一条 grep 无匹配的语义 exit1，即使外围工具调用未报错，严格逐命令协议仍判 `agent_status=failed`。内容只能作为总控候选证据，不能计 MiMo 有效 plan gate；Kimi 同版有效第二路亦缺。下一步对同 SHA 派发修复性 MiMo 复审，明确避免以无匹配命令作为成功检查；产品未实施。

## MiMo PR6 修复性同版复审通过

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- MiMo `o13-plan-rereview6-mimo-20260929-01` 显式绝对 O13 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、49 turns、canary `mimo-6e3631fe` 匹配；`docs/reviews/plan-review-20260929-135201.md` 锁计划 SHA `ce9f3e7a55d17afb2894bd0d4eb98c4b051214abfe4500ba7d40a759f4a7870c`。本轮命令记录全部自身 exit0，未重现无匹配 grep 问题；内容判 pass-with-risks、零 material finding。总控实读 report 中四 core 入口→共用 `_toggle_source_deleted`→reader/provenance 的异常链、manifest upsert `updated_at` 的写入面和 no-op 整段跳过必要性，PR4-F1 内容修复成立。
- Q1 `FileExistsError` 可达性、Q2 既有与新增 ValueError Raises 原因须合并、Q3 覆盖基线79% 需在实施环境重测，均归实施 code review/validation，不在 plan 阶段臆造新合同。R1～R10 已分类到 O14/O15/O18/O33、独立 reader WU、实施/PR 集成等 owner；无本轮未分类新风险。
- **MiMo 有效一路 plan review 通过，Kimi 同一 SHA 的有效第二路仍缺；O13 plan gate 未通过，不得 accepted plan commit/实施。** 下一 entry 为额度恢复后 Kimi 独立同版 `$planreview`，总控裁决后按 Gateflow 自动推进。
