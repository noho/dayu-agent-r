# PR197 当前完成项与剩余执行清单

核对时间：2026-10-01 09:04:42。最新用户要求继续全部授权WU，全部完成后再停下汇报，期间简报实际进展；用户现成裁决为准。本文计数区分产品修复标签、已确认WU和待goal残余候选，不把每个review finding算新WU，不重复计F4/F5/F6/F7的独立owner名称。

## 已交付入PR的成果

- issue198 S1/S2完整final closeout pass，已授权评论发布/读回，待用户merge自动关闭issue。
- UM-O03工作区目标类型校验、安全点号元数据、UM-O11严格日期、UM-O20-F01公开格式说明：已实现/局部门禁并入PR。不能由旧局部验收推定当前整个PR通过。
- UM-O04/O23统一全资产命名/Docling文件名规划：实现及同版代码审查通过，资产整合e215/审计9c70已推；O25 primary消费仍未闭环。
- PR197-R1/F2测试作用域两行修复及同版双审/类型验证已通过并入PR，是优先六项中唯一当前局部闭合项。

## 首轮PR review优先六项

| WU | 完成了什么 | 还剩什么 |
| --- | --- | --- |
| F2 | owner修复/双审/验证/入PR | 由最终整PR验证覆盖 |
| F3 分析脚本参数化 | 初步五utils实现保全；计划几轮纠正，最新2983两句候选核收 | 当前MiMo/Kimi窄复审→accepted amendment→C01固定汇总冲突/C02物理cache别名sourcefix→code/aggregate/PR review/closeout |
| F4 HK身份批量读取 | accepted plan dc29；14文件实现候选，788修前测试/type0/八filecov>=80；两路code-review已收 | Sol当前S1修A1深JSON/A2测试契约→同版复审/修后tests/type/cov→accepted slice→aggregate/PR review/closeout |
| F5 HK财期锚点一致性 | 目标/提案/官方非空raw补证；N01/N02已登记 | Q1未知财期是否继续确定报告待用户具体裁决→计划修订/审查→实现及后续全部门禁 |
| F6 storage sibling错误公开语义 | 已有目标与直接证据 | plan及后续全部门禁，sharedCN源码串行 |
| F7 下载status唯一owner | 实现/双审/aggregate accepted，314/2cc已推 | 同一最终PR版本PR review及closeout；不能算完整WU已结束 |

因此优先批次6项：F2局部闭合，5项仍待完整闭环。F3/F4不能把文字或代码候选算修复通过；F7剩收口不是重新实现。

## 原upload修复队列

原22个accepted修复标签中，O03/O04/O11/O20-F01/O23已有实现交付；尚未完整闭环的17个标签如下，按owner依赖合并成WU执行，不承诺17个独立WU：

- `UM-O05-F01`
- `UM-O06-F01`
- `UM-O07-F01`
- `UM-O07-F02`
- `UM-O09-F01`
- `UM-O10-F01`
- `UM-O12-F01`
- `UM-O13-F01`
- `UM-O14-F01`
- `UM-O15-F01`
- `UM-O16-F01`
- `UM-O17-F01`
- `UM-O18-F01`
- `UM-O21-F01`
- `UM-O22-F01`
- `UM-O25-F01`
- `UM-O33-F01`

另有已授权受控XBRL支持UM-O20-F02，前置O20-E01补证/依赖/taxonomy/OS隔离与真实Docling→manifest成功；已报Docling上游4437不代表Dayu支持完成。仅部署支持与转换/manifest责任；内容抽取准确性归上游。CNInfo新下载中国本地披露日独立项保留，历史迁移另议。

## 后续独立登记条目

主队列独立表26个具名条目，其中4个已经对应F4/F5/F6/F7，不能重复算剩余WU。其余22个以下保持原登记状态：不少只是需先核证据/goal确认的残余，不等于已经批准了22项产品变更。用户继续全部WU不自动选择schema/历史迁移/新业务取舍。

| 独立work unit或候选 | 原直接缺口 | 依赖/状态 |
| --- | --- | --- |
| `fins-download-indeterminate-publication-state` | storage batch swap/rollback 双失败时 durable 发布确定性不足 | storage owner 先给 typed 确定性，再同源投影；待 goal。 |
| `fins-download-other-source-summary-conservation` | 其它下载来源 typed 中止后已处理行可能归零 | #198 S1 之后；待 goal。 |
| `fins-other-raw-diagnostics-audit` | 非 download job/CLI 原始异常与 traceback 日志/持久化泄漏；异常链诊断是否可安全补充 | #198 S2 接管 download generic，原泛 download 登记由 S2 supersede；待 goal。 |
| `fins-direct-projection-failsafe` | direct RESULT 自身投影/投递二次失败可能逃至线程原始 traceback | #198 S2 之外；待 goal。 |
| `fins-download-no-source-retry-hint` | 无来源文档的非异常 RESULT 仍可能误导盲重试 | 独立公开文案 owner；待 goal。 |
| `fins-download-job-reason-code-persistence` | #198 S1 direct/CLI/wait 有结构化 public `reason_code`，job durable failed record 只有安全 message 与结构化 download 摘要；后续按消息反推原因会漂移 | #198 accepted plan 明示不扩 job schema；由 job record schema/Service 读取 owner 单独确认是否需要持久化/投影结构化原因；待 goal，不在 #198 补字段。 |
| `fins-source-integrity-reason-constructor-invariant` | `SourceIntegrityPreflightError` 构造器未校验封闭 reason 成员：普通非成员在 `reason.value` 处失败，带 `value` 的伪对象可到 Fins 映射 KeyError；当前生产构造点均传有效枚举。若未来触发，#198 新的 typed job 保存把 public 映射置于自身 try 外，裸 Thread 可输出原始 traceback 且 job 停 `running` | storage 异常构造 owner 待 goal/证据确认；job 终态后果与 `fins-direct-projection-failsafe` 一并审。#198 aggregate OQ1 当前不可达，禁止 Fins 下游临时 fallback；若出现生产调用先重开 #198 可达性裁决。 |
| `fins-cancellation-coverage-order-sensitivity` | 九文件 coverage 组合中两个既有 CLI 取消时序测试复现失败，普通 856/892 套件、单文件/单用例插桩通过；尚未同口径跑共同基线，不能断言 #198 新测试无顺序影响 | CLI stream owner 与测试夹具 owner 待 goal/证据确认；#198 aggregate MiMo r2，普通验收及单文件覆盖率达标，不在当前 issue 用跳过掩盖。 |
| `fins-download-unsupported-source-public-consistency` | direct/job 对 unsupported source 的公开文案不一致 | #198 S2 不改此业务分类；待 goal。 |
| `fins-material-legacy-identity-seed-disposition` | 新 canonical form 与旧 raw 已发布身份跨代分叉 | O17/O07 稳定后；待 goal。 |
| `fins-material-form-consumer-matching-audit` | read/preprocess 的 form 比较、历史别名和 document_type 词表需核与新写 canonical form 真源的消费边界，避免按旧 raw 再造 durable 事实 | O17 集成后以真实 read/preprocess 路径审计；待 goal，不将查询容错写进 ID canonical owner。 |
| `fins-material-legacy-invalid-fiscal-identity-recovery` | 旧非法 fiscal seed 的已发布寻址处置 | O09/O10/O07 后，与上一项同源合流裁决。 |
| `fins-upload-usage-message-channel-neutral` | 共享 usage 文案含 CLI 专属术语而进入 tool/LLM | O09/O10 后按同一 public owner；待 goal。 |
| `fins-filing-amended-identical-skip` | filing 同内容跳过可能吞 amended 标记 | O18 只修 material；待 goal。 |
| `fins-material-processed-amended-projection` | processed meta/manifest 保存 preprocess 时点 amended，材料 metadata-only 切换后与当前 source meta/manifest 不同；需证明快照语义、消费与是否重处理 | O18 定义当前发布事实后核真实消费者；待 goal，不从 processed 推断当前发布。 |
| `fins-source-restore-active-idempotency` | active source 重复 restore 的状态/时间语义 | O13 后；待 goal。 |
| `fins-source-meta-is-deleted-reader-contract` | `document_models.from_source_meta` 以 raw `meta.get("is_deleted") is True` 投影 tombstone，可能与精确 reader helper 及 storage fail-closed 合同漂移 | O13/O14/O15 storage 同版状态后核真实可达路径；待 goal，不在 O13 下游补偿。 |
| `fins-material-file-existence-admission` | 非 CLI material 缺文件/非普通文件可能落 generic，CLI 可能回显绝对路径 | O04/O23 身份规划后，与 O21/O22 标签合同核对；待 goal。 |
| `fins-upload-batch-derived-material-name-admission` | `upload_filings_from` 可生成 `material_name` 超过 O06 240 码点的脚本，生成成功但执行必然被拒 | O06 同源长度规则集成后，由 batch 脚本生成 owner 前置处理；待 goal，不截断或复制阈值。 |
| `fins-filing-tool-combination-owner` | filing tool 参数组合与业务准入的独立 owner 缺口 | filing 范围；待 goal。 |
| `fins-cninfo-single-day-discovery-window`（待重订 goal） | 初始同日零结果被一手 provider 时间戳反证：巨潮按中国本地 2025-03-29 返回两公告，Dayu 用 UTC `gmtime` 错投 2025-03-28；真实缺口是公开 `filing_date` 与 provider 查询日历不一致，不能据此推断相等端点错误。 | 隔离 `docs/gateflow/fins-cninfo-single-day-plan-adjudication-20260929.md`；待用户裁决日期真源/历史来源影响后重订 goal，#198 S1 不顺手改日期。 |
| `fins-cninfo-default-window-local-day` | 无显式日期时 `resolve_window` 取宿主本地日而 docstring 称 UTC，与新中国本地披露日可能差一天 | CNInfo 显式日期 WU 后核窗口 owner/用户默认日语义；待 goal，不在 DTO 日期修复中猜。 |

此外共享临时根/公开entrypoint测试隔离和F4-R01集合唯一性、R02成本/原startstream事件观察边界为既有待核goal残余，未被上述计数冒充完成或新增必须实施的业务规则。

## 当前运行与Git

- Sol22860 / MiMo11067 / Kimi61008均outer0完成并根核收。F3 amendment pass待accepted commit和源码fix；F4 delivery accepted，794passed/fulltype0/八prod>=80，同版re-review next。
- 最近实时local/tracking/live/PRhead同dc29c1fe5e173d9ef710cd7f44fd0889e0da46c9；PR OPEN/draft，main本地/live/base同fac32ecbff9bfe792b63ee9667c8697826b631f4。F3/F4未提交候选保全，仅codex/upload-material-oracle开发，未改main。
- 本次不是整PRcloseout，没有整仓pytest/CI绿结论。当前已成立新findings均独立登记root F4 code-review adjudication及三份current入口。

2026-10-01 09:09:14补充：文档证据保存commit 87dfbeae8625e34162812c06886610c37ba0f4e9 已普通push并live/PR/main读回；产品候选未accepted，不能把该docs checkpoint当源码修复完成。当前source Sol的九模块794 passed仅在途修后候选进展，全量类型首次4errors仍须恢复并最终收取，不作通过。

root最新核收：首次4条新测试类型错误已实际修复，最终default full pyright0，794同版矩阵重跑通过；旧在途描述是历史，不作当前状态。F3两句双审与独立保全证明pass，C01/C02源码仍未修。F5 Q1待回答，不影响其它WU推进。详新F3 amendment final adjudication与F4 fix receipt。
