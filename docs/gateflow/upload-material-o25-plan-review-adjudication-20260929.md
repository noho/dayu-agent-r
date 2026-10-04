# UM-O25-F01 plan review 总控裁决登记

- Gate：`plan review` 在途；MiMo label `o25-plan-review-mimo-20260929-01` 正审计划 SHA-256 `20eb093d0071c654c38582231fcca693ee775115aec2be009ac76df89278fc34`，Kimi 有效第二路尚缺。产品未实施。本文件先登记总控独立发现，不预判 reviewer 或 gate 结论。

## F1 中：material delete/files 优先级依赖 O16，计划误称已有

**直接证据**：本计划「确定性前置时序」写 delete 携 `files` 沿用“现有 files/delete usage”，且指定该错误先于 `primary_not_allowed_for_delete`；同时「非目标」排除 O16，实施硬依赖仅列 O04/O23。O04/O23 最新实施候选 `dayu/fins/upload_asset_plan.py:250-253` 对 material delete 直接返回空 selection/plan、忽略 `files`；`dayu/fins/ingestion_runtime.py:7610-7628` 的 material `_normalize_upload_request` 只规范 action 后 `replace`，不查 delete/files。`ValidatedFinsUploadMaterialRequest.__post_init__` 还写明“旧 delete admission 忽略 raw files；O16 尚未裁决其动作规则”。filing 的 `FILES_NOT_ALLOWED_FOR_DELETE` 在另一独立静态 owner `ingestion_runtime.py:1113-1119`，不能把 filing 合同误当 material 已有行为。

**总控裁决：accepted，待 plan fix**。O25 若在 O16 未落地时只增 selector，可使 `delete + files + --primary` 返回 selector 错误而非计划承诺的 files/delete 优先级，或被 O04 plan 吞掉 files，测试也无法真实验证“沿用已有”路径。最小修法是将 O16 的 material action/files 静态准入列为 O25 实施硬依赖，并在集成基线重新核对该 typed code 与优先级；O25 只新增主原件 selector 规则，不在本项复制 O16 的动作 owner。若 O16 最终合同不同，先回本计划裁决，不临时在 CLI/adapter 补偿。当前 MiMo review 继续；其后由 Sol 与其它 findings 一次修计划，再同版 Kimi/MiMo 复审。

## MiMo 首轮计划复审与总控裁决（2026-09-29）

- `setup_status: ok`，`agent_status: completed`，`tool_evidence: yes`，`canary_status: match`（`mimo-08769a9c`），`warnings: [claude-code:unrecognized_model]`，`retry_class: none`。Claude/MiMo 进程 exit 0、JSON `subtype=success`、`is_error=false`、`num_turns=76`；独立 artifact `docs/reviews/plan-review-20260929-125449.md` 对计划 SHA `20eb093d0071c654c38582231fcca693ee775115aec2be009ac76df89278fc34` 判 `fail`。总控对照实际 `ingestion_runtime.py` usage 文案、`docling_upload_service.py` 的 skip/version 两处门条件及计划 S1–S3 后采纳下列修复项；不把一条已通过的外部 review 当作实施许可。
- **PR1-F1 高，accepted／未修复**：`delete + files + selector` 的“沿用现有 typed usage”不是 material 当前 owner 的事实。按既有总控裁决，O16 material action/files admission accepted+integrated 是 O25 实施硬依赖；本计划仅定义 selector 规则和相对已生效 action/files admission 的次序，不在 O25 偷做 O16 的半项。计划须去掉跨入口总序的无条件承诺，并注明与 O05 form/name 共边界时重核次序。
- **PR1-F2 中，accepted／未修复**：共享 `MISSING_MULTI_FILE_PRIMARY` 现文案为“多文件 filing……”，不能直接投影给 material。O04/O23 集成后在 usage owner 中改为 kind 中性文案，明确四个复用 reason 的文本/投影，并将其 owner 测试列为白名单；CLI/tool 文案同源。
- **PR1-F3 中，accepted／未修复**：S1 admission、S2 入口、S3 Docling 消费分片会产生“入口不可表达 selector”及“已承诺选中却仍读首项”的中间态。计划改为一个端到端行为切片，或仅保留不会对用户宣称错误行为、可独立验收的切片；迁移旧首项断言与真实 CLI/read 验证在同一闭环。
- **PR1-F4 低，accepted／未修复**：指纹、skip、版本合同须明列 `identical_skip_safe` 的 material 取值/依据；A→B 版本递增、B→B 同角色逆序 skip 版本不变写入真实仓储断言。
- **OQ／残余**：O04/O23 的 typed plan/pair 接口未 accepted+integrated，实施前只以其最终 public contract 定落点；O16 与 O05 的全局 admission 次序留共同 owner 校验。CLI 无独立 read 命令，跨命令证据以真实 `process_material` 加 read runtime/snapshot 测试承载。产品未实施；下一 gate 为 gpt-6-sol 限定计划修订，再对同一内容执行 Kimi/MiMo 双路 `$planreview`。

## Sol PR1 候选与总控新增 LLM 文案裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o25-plan-fix-pr1-sol-20260929-01` 显式绝对 O25 workspace，独立 JSONL/stderr/last-message/canary，进程 exit0、`turn.completed`、canary `gpt-6-sol-a8ef1f3b` 匹配、stderr 空；至少一条 `command_execution` exit2（把 `git diff --no-index --check` 的差异状态误判为空白错误），另有探索脚本因扫描无关 `/private/tmp/codex-daemon-501` 而 `PermissionError`，其失败由 agent 自述/修复记录披露。严格 `agent_status=failed`；候选计划 SHA `9590f021d8c4316d8166de00b93f1a154945b3774ef633662d0b538d663981fd` 只作内容复审输入，fix artifact `docs/gateflow/upload-material-o25-plan-review-pr1-fix-20260929.md`。总控实读候选：O16 实施硬依赖、单行为闭环切片、`identical_skip_safe`/版本和 read 验收均已入文，PR1-F1～F4 内容候选已修，仍待有效双路 review。
- **PR1-F5 中，accepted／未修复**：候选计划 §共享 usage 文案仍把四条原样 `--primary` / `--files` CLI 选项消息投影给 tool，且直接写“CLI 与 tool 投影该事实”。但 tool 的公开输入是 JSON 字段 `primary`/`files`，没有 CLI 选项；该文本进入 LLM-facing tool 错误，会指示错误调用表面。O25 oracle 要求 CLI help、tool schema、错误说明同源且可行动，AGENTS.md 明确 LLM-facing 只能给当前任务必要动作。此项只针对本 WU 四个 selector reason，在唯一 usage owner 改为通道中性的业务句，例如“多文件必须指定一个主文件”“主文件只能指定一次”“主文件必须精确匹配本次文件之一”“delete 不能指定主文件”；CLI help 明确 `--primary`、tool schema 明确 `primary`，两者各自映射同一业务规则。旧 filing/tool 断言随本次共享四句迁移；全局其它 usage 文案仍归已登记的 `fins-upload-usage-message-channel-neutral`，不在 O25 扩大。需 Sol 只修计划与 fix artifact 后再锁 SHA 双路 planreview，产品未实施。

## Sol PR1-F5 补修候选核验

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `o25-plan-fix-f5-sol-20260929-01` 显式绝对 O25 workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、20 完成命令全 exit0、无 error/failed、stderr 空、canary `gpt-6-sol-cf4adee3` 匹配。总控核读计划 SHA `bd5b18013d0bc98d3467c867328de85278ebafff8fdb156247115978baadf72e`：四个 selector message 改为“多文件必须指定一个主文件”“主文件只能指定一次”“主文件路径必须精确匹配本次上传文件路径之一”“删除时不得指定主文件”；CLI help 仍指 `--primary`/`--files`，tool schema 仍指 JSON `primary`/`files`，旧 filing/tool 断言迁移入测试清单。PR1-F1～F4 内容候选未变，F5 标「候选已修，待同版双路 planreview」；产品未实施，O04/O23/O16 accepted+integrated 仍是实施硬依赖。

## MiMo PR1-F5 同版复审与严格结果

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- MiMo `o25-plan-rereview2-mimo-20260929-01` 显式绝对 O25 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、53 turns、canary `mimo-cded4372` 匹配。`docs/reviews/plan-review-20260929-134300.md` 锁计划 SHA `bd5b18013d0bc98d3467c867328de85278ebafff8fdb156247115978baadf72e`，内容 pass-with-risks、无新 material finding；PR1-F1～F5 的依赖、通道中性文案、单闭环、指纹/skip/版本与最终 O04/O23 契约硬停均有一手代码对照。
- 该 artifact 如实披露复合 shell 的 zsh `====` 解析 exit1、grep 无匹配 exit1，以及管道遮蔽的 `ls .venv` 失败；按全命令协议严格 `agent_status=failed`，不能计 MiMo 有效 plan gate。总控接受内容反证但不把它当正式通过；OQ-A 的 A→B→B 多文件逆序构造、OQ-B 复合错误归属、OQ-C 同 stem 预期均按最终集成契约在实施前核对，不据此发明跨 owner 总序或预设未集成接口。下一步同 SHA 修复性 MiMo review；Kimi 第二路仍缺，O25 产品未实施。

## MiMo 第三轮修复性同版复审通过

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- MiMo `o25-plan-rereview3-mimo-20260929-01` 显式绝对 O25 workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、43 turns、canary `mimo-f6a82bde` 匹配；`docs/reviews/plan-review-20260929-140124.md` 锁计划 SHA `bd5b18013d0bc98d3467c867328de85278ebafff8fdb156247115978baadf72e`。全部工具/命令自身 exit0，内容 pass-with-risks、零 material finding。总控实读计划与报告对 O16/O04/O23 未集成合同、四条通道中性文案、单闭环切片、role fingerprint/skip/version/read 的对应证据；PR1-F1～F5 内容修复成立。
- OQ-A/B/C 保持实施前按集成合同核对，R1～R7 各归依赖、共同准入、独立文件存在性 WU、实施验证与 filing 文案回归；无新未分类修复项。**MiMo 有效一路 plan review 通过，Kimi 同 SHA 有效第二路仍缺，故 O25 plan gate 未通过，实施硬依赖 O04/O23/O16 仍未达。** 下一 entry 为 Kimi 独立同版 `$planreview`，随后才可裁决 accepted plan checkpoint；产品未实施。
