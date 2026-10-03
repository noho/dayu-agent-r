# UM-O18-F01 plan review F1–F6 修订记录

- 状态：仅候选计划修订；未通过 Kimi/MiMo 双路 re-review，未进入 implementation，也不是 accepted plan。
- 工作区：`/private/tmp/dayu-upload-o18`；分支 `codex/upload-material-o18`；HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 唯一修订计划：`docs/gateflow/upload-material-o18-amended-plan-20260929.md`；修订前 SHA-256 `13a1af30e49dfdd09b3b580a32b1fd32fc0f76e3ade05f27e1201904766223b5`，本轮候选 SHA-256 `162e28ca093379e55a7cd2f34b071169c54c4fd46caa6ad23cf5e70db5a03bc6`。修订前计划、goal、裁决和 review 在本隔离工作树均为已有未跟踪文件；本轮只改该计划并新建本 artifact。

## 动机与来源证据

`docs/gateflow/upload-material-o18-amended-goal-20260929.md` 要求同内容标记变化成为单一已发布事实；`docs/reviews/plan-review-20260929-044006.md` 的 F1–F6 和 `docs/gateflow/upload-material-o18-plan-review-adjudication-20260929.md` 给出本轮修订边界。动机成立：`dayu/fins/service_runtime.py:_run_material_upload` 的两路市场调用未传 `amended`；`dayu/fins/pipelines/docling_upload_service.py:prepare_upload/_can_skip_upload` 在 material 同指纹时 prepare 期提前 skip；`dayu/fins/ingestion_runtime.py:FinsUploadResultSummary` 的 `ok` 要求 stored=requested，闭集没有 metadata-only 状态；`dayu/fins/storage/_fs_source_document_core.py:_get_source_meta_unguarded` 返回前剥离私有 revision，而 `replace_source_meta` 只有无条件 staging 替换。`dayu/fins/storage/_fs_storage_infra.py:_commit_batch_with_publication_guard` 当前只在 guard 内 swap，未提供 O12 条件检查。`dayu/fins/domain/document_models.py:MaterialManifestItem` 当前没有 amended 字段；`dayu/fins/tools/read_runtime.py` 读取 amended 时默认 false；`dayu/fins/tools/upload_tools.py` 的共用参数 schema 仍说“上传文件是否为修订版本”。这些是当前 HEAD 的代码事实，不能用 A16/A17 冻结对照替代。

只读核对外部 O12 候选计划 `/private/tmp/dayu-upload-o12/docs/gateflow/upload-material-o12-company-plan-20260929.md`，其工作区 HEAD `b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c`、计划 SHA-256 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`。其 §「storage 同版状态与分阶段 guard」设计同版 company/source 完整业务 meta + opaque revision snapshot、材料 batch expected source state 和 publication guard 内 precondition；该计划本身仍待双路 re-review，O18 HEAD 中没有相应 public contract。O18 只能把它和 O14/O15 已实施集成列为 implementation 硬前置；实际接口不够表达 active/fingerprint/amended 时须回 plan review，不新增下游 private revision 或第二套 hook。

## 六项裁决的计划落点

| Finding | 本轮计划修订 | 实施前验收或停止信号 |
| --- | --- | --- |
| F1 | O12 同版 guard 与 O14/O15 共享 action/target 准入均须先实施集成；O18 skip/metadata-only 仅处理其允许的 upsert。active create-existing 无 overwrite 在共享准入前置 typed conflict。 | 核实际准入真源与 active/missing × create/update、overwrite 四象限；依赖缺席停 implementation，不定义过渡 FileExistsError/skip。 |
| F2 | `UploadOperationResult`、pipeline JSON、typed pipeline result 和 runtime summary 明确 `metadata_updated`，映射 completed、requested>=1、stored=0；`published_amended` 是 material 终态 typed bool/null，新增六类终态最小摘要片段。 | 逐状态核 status、计数、字段必填和来源；filing 状态/身份独立。取消 durable job 若无摘要不伪造发布事实。 |
| F3 | 消费 O12 完整 expected source state + opaque revision 的材料 batch precondition，在 guard 内首次 swap 前比较；计划加入真实仓储 A prepare→B commit→A commit 交错。 | A typed stale 拒绝且 B 的 source meta、manifest、资产不回退；实际 O12 public contract 不够表达则回审。 |
| F4 | 调用点统一写为 `service_runtime._run_material_upload`。 | 按真实符号和 US/CN/HK 实参核对。 |
| F5 | material 表写 prepare 期 identical skip，取既有已发布值且无本请求业务写入；保留 O33 一般竞争边界。 | 不借 filing canonical skip 设计 material batch 重裁决。 |
| F6 | material 请求摘要和 started 叫 `requested_amended`，已发布终态叫 `published_amended`；共享 tool schema 按 `upload_kind` 解释，计划白名单加入 schema、direct/Service 测试及 README 触发判断。 | 对照 LLM-facing 文本、job record、direct/CLI/tool 投影；不出现裸结果 `amended` 的歧义。 |

O13 重复 tombstone 时间规则只作合流回归；O33 一般同 identity 并发另案。filing identical skip 风险保持独立跟踪，不由 material O18 越权修复。

## 命令退出码与本轮验证

以下按本轮实际 shell 调用批次记载，每格 exit 序列与该批次 `exec_command` 顺序一一对应；复合命令记录 shell 最终 exit。`apply_patch` 是编辑工具，不是 shell 命令。读码/检索批次均为只读。

| 批次 | 依次执行的命令概要 | exit 序列 |
| --- | --- | --- |
| 1 | `pwd/git status/HEAD/rg MEMORY.md`；`cat AGENTS.md + 四份指定文档`；`cat canary.txt` | `0, 0, 0` |
| 2 | `nl plan`；`rg docs`；`rg --files dayu/tests`；`git log/branch/wc/rg review` | `0, 0, 0, 0` |
| 3 | `sed plan §5–8`；`rg O12/O14/O15 文档路径`；`rg runtime/storage 符号`；`rg amended 调用面` | `0, 0, 0, 0` |
| 4 | `sed ingestion`；`sed Docling`；`sed storage`；`rg --files 主工作区 O12/O14/O15` | `0, 0, 0, 0` |
| 5 | `rg 本仓 O12/O14/O15 文档`；`rg O12 guard 裁决`；`sed review/summary/schema`；`rg manifest/read/status + git status + 初始 SHA` | `0, 0, 0, 0` |
| 6 | `find /private/tmp -maxdepth 3 -iname '*o12*plan*.md'`；`rg O12/裁决 + sed market handoff`；`rg result/status 调用面` | `1, 0, 0` |
| 7 | `cat O12 task`；`ls /private/tmp/dayu* /private/tmp/*o12*`；`sed status mapping` | `0, 0, 0` |
| 8 | `git -C O12 status/HEAD + rg O12 plan`；`rg O12 storage/current adjudication`；`sed manifest/prepare/delete` | `0, 0, 0` |
| 9 | `rg O12 actual symbols + git ls-files + SHA`；`sed tool helper/events/pipeline`；`rg direct/CLI tests + README 约束` | `0, 0, 0` |
| 10 | `sed cancellation/progress/skip`；`sed O12 plan` | `0, 0` |
| 11 | `rg 已修订计划落点` | `0` |
| 12 | `sed progress/cancel job`；`rg tool/result builder` | `0, 0` |
| 13 | `sed tool/CLI rendering` | `0` |
| 14 | `shasum + git diff --no-index --check + git status`；`rg 计划合同`；`rg 禁用旧术语`；`test -f 白名单路径` | `0, 0, 1, 0` |
| 15 | `shasum + git diff --no-index --check` | `1` |
| 16 | `awk` 两份文档尾随空白；`shasum + git status + git diff --name-only + HEAD`；`rg` artifact 的 F1–F6 与状态字段 | `0, 0, 0` |
| 17 | `shasum` 最终计划 + `awk` 两份文档尾随空白 | `0` |

批次 6 的 `find` 因 `/private/tmp/codex-daemon-501: Operation not permitted` 退出 1；随后改用已知 `/private/tmp/dayu-upload-o12` 路径只读核对。批次 14 的 `rg` 退出 1 是预期零匹配：旧 `_upload_material_with_pipeline`、`canonical identical skip`、裸 `payload["amended"]` 均不在新计划。批次 15 的 `git diff --no-index --check` 对未跟踪新增文件与 `/dev/null` 比较时退出 1，输出只有 SHA 行、无空白错误诊断；退出 1 不记作通过。

本轮仅改 Markdown；未运行产品 pytest、pyright、coverage 或真实 CLI，亦未修改 README/产品/测试正文。计划中的测试与 canary 是未来 implementation 验收要求，当前均未通过或声称通过。

## 残余风险与交接

1. O12 候选计划仍在 review，O18 HEAD 无同版 public snapshot/guard；O14/O15 action/target 准入也未在本轮集成核实。implementation 硬停，待集成后重读实际 API 和回归。
2. 现有 durable cancel job 不保存 result summary；计划仅约束确实产生的 material pipeline/direct 取消结果为 `published_amended=null`，不伪造 durable 摘要。实施时须核实 tool/CLI 公开取消投影仍无发布断言。
3. material prepare 期 skip 的一般并发窗口及 O33 的其它同 identity 竞争仍独立；本计划只要求 metadata-only 的 O12 guarded commit 和真实双 batch 交错验收。
4. 计划候选已收敛 F1–F6 文本，但没有 Kimi/MiMo 有效双路 re-review；不得把本记录当作通过下一 gate 的证据。
