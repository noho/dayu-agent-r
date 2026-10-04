# F4 aggregate deepreview 总控裁决

## 裁决与下一入口

**F4 aggregate deepreview pass**，没有新 accepted 未修复 finding。下一入口 accepted deepreview commit，之后在最终同版 PR head 执行 PR review / final closeout；本文件不是整 PR 或所有 WU 完成声明。

既有 accepted slice `75fec034d8993f300c2f2e2c8b9c574e243f8538` 已入 draft PR197；当前 F4 源码与该 slice 字节相同，main不变。全部开发仍只在 `codex/upload-material-oracle`。

## 结构化与输入核收

| 路由/label | 托管终态 | 实际 metadata | 正式报告 |
| --- | --- | --- | --- |
| claude/mimo/pr197-f4-aggregate-mimo-20261001-01 | 48266 outer0 | success/is_error=false，110turns，mimo-v2.6-pro[1m] | docs/reviews/code-review-20261001-110655.md |
| claude/kimi/pr197-f4-aggregate-kimi-20261001-01 | 10989 outer0 | success/is_error=false，94turns，kimi-k3[1m] | docs/reviews/code-review-20261001-110953.md |

root全文读取两份报告、完整JSON及stderr，各本轮随机读取凭据与基准相等；permission_denials均空，stderr只有精确unrecognized_model warning。Claude只有summary，没有逐工具轨迹，不以turns/canary声称中间工具全部成功。

两个任务分别使用以下固定核收块，accepted仅表示本aggregate审查证据可采纳：

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: summary_only
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - precise unrecognized_model metadata warning
  - Claude summary does not expose every intermediate command
  - MiMo zsh diagnostic and temporary annotation rewrite recovered
  - report checkpoint and count claims limited by root actual frozen identity
evidence_gaps: []
retry_class: none
```

双流完整路径：MiMo `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.r3S6Si/`，Kimi `.../sub-agents.Dvj95A/`（同完整父目录）；各唯一label为文件前缀。没有quota失败、重派或provider切换。

root实算freeze59当前+59aggregate原件+38初始原件+45fix前原件，共**201项**全部匹配。MiMo仅报142不含aggregate原件，root补核59；Kimi的HEAD4a描述为初始checkpoint，MiMo观察到后续docs0060/854，root实际当前local/tracking/live/PR854114a3已核，相关F4字节没有漂移。这不是针对最终整PR版本的review。

## 独立 owner / 验证裁决

root再次读真实 core 的同guard完整枚举→getter顺序→仅ValueError/OSError保存前缀→fresh JSON parse投影→MappingProxy→finally释放，以及identity build/resolve全部错误优先序；同前次完整增量核收对照W0共享/start-stream-retry新窗、cancel时点和原ordinary/typed投影边界。没有向view/index添加完整性证明或写授权，没有下游raw重推断，没有更改用户财期、来源选择或manifest成功裁决。

Kimi本轮新增实跑日志39passed/exit0/stderr空，覆盖6个deep JSON真实提交回归+33identity；root读取该双流/exit，不冒称自己重复跑或39代表全量。先前794tests/default full pyright0/八prod各≥80由root真实交付核收，冻结再次验证同版；无需无理由重复测试。

MiMo两组JSON loads/dumps临时探针源码/结果由root实读：递归limit1000时600/900可roundtrip，1000及以上loads/dumps均RecursionError。报告所述一次zsh解析噪音内容恢复、临时注解去掉Any/object后执行0，root以实际可读原件/日志恢复关键证据；不声称取得其缺失逐工具trace。

## MiMo Open Question：超深盘外输入

**rejected-with-reason（作为当前F4阻塞/finding）**。accepted plan §4明确仅保存getter契约 `ValueError | OSError` 前缀，其它未声明异常立即原样传播，core/docstrings/tests按该边界实现。盘外手工构造≥1000层JSON时，若前项同时缺internal，异常先后可与旧按候选扫描不同；这是已声明未预期异常面，不把所有异常吸入业务prefix，也不补新限深规则。真实当前writer `_write_json` 同源json.dumps在该极限自身失败；没有复现通过当前仓储写入而旧读可成功的新拒绝（原600层deepcopy问题已修）。

root不声称任意外部writer/任意递归limit永远无法产生此输入。若需要对盘外/不同进程深度的所有未声明异常也保持候选优先序，属于新的完整读取失败合同，owner storage observation，destination 独立goal/明确用户裁决，分类 **requiring new issue or explicit user decision**。不新建外部issue、不暗改schema/解析器、不借此扩本F4，也不将它登记为当前必实施WU。

## 残余与覆盖

F4-R01跨writer集合唯一性保留requiring new issue or explicit user decision；F4-R02扫描总成本、start/stream跨发布事件观察、未来caller空索引边界由既有owner后续WU复审。可选assert清理不作finding。八prod关键链/全累积diff与合同已核；大测试未改段、其它WU、全仓内部逐行、全部OS/JSON形态、真实网络/OCR不冒称覆盖。

README职责与两个README合同对齐已核，无其它用户入口/分层变更。F3/F5/F6/F7及原upload队列仍继续，F3实现服务阻塞不否定本F4证据。全部授权修复后的最终真实CLI CI→upload_material oracle/scenarios/readiness仍必须完成；现有download/upload registry的ready不替代该目标。
