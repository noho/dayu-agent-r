# 601225-annual-fulltext：final closeout

- Decision：**final closeout pass**；work unit completed=true。draft-PR-pass已满足：两正式PRreview+root裁决通过、accepted PR review commit b3d4a533cdffe9ba6c70d79f2e9a34c50f821cb2已实际push exit0，GitHub fresh head与本地相等，PR保持open/draft，无未修accepted/needs-more-evidence/blocking OQ，风险均有分类和owner/destination。
- Draft PR：https://github.com/noho/dayu-agent-r/pull/201。未merge、未转ready、未invite reviewers、未approve/comment/issue/删除分支；未clear或打断其它任务。
- 代码commit：e5238119c0eaf7957b57ffb972fcea60ddeb4804；accepted plan7709c015，aggregate4d7ef056，PRreview b3d4a533。后续收尾提交只发布此summary/state，无执行路径变化。两PRreview精确审查版本为4d7ef056/base7637bb0，之后code/tests/deps/config/README blob均与e5238119全等，不宣称文档新head重新全面review。

## 改了什么与直接根因

当前原参数production发现的官方FY19条包含三全文；旧selection对无财年“年报全文”按披露年分组，再被较新跨年公告淘汰。修正候选财年alone又会碰到财期ID与已持独立摘要同槽，原COMPLETE skip不绑定真实source。两条链均由同源raw/owner重放和隔离真实仓储直接证实；原历史raw/启动树未冻结，不把当前复现冒充历史逐阶段全链，未归责标题过滤或Dayu改写。

修复在Fins owner：从官方实际PDF首页确认财年+全文/摘要，selection只消费事实；discovery交付同次prepared原件或同revision本地witness，完整性/发布严格核当前原件；source身份按provider/source_id复用或来源hash独立分配，双external/internal占用拒绝；selectedrepair按来源intent及expectedID关闸，fresh漂移应用前abort。没有公司/三ID/特定年份补丁、披露年减一或调用方兜底，HK/H1/Q原业务保留，storage schema/CLI/Service/Host/Engine/调用方未变。

## 真实验收

| 官方source ID | 官方原文财年/性质 | 实际原PDF SHA256 |
| --- | --- | --- |
| 1213161683 | FY2021 / 全文，287页 | 41ec9bdf696e9e40a650288d042346ad03d05325a921e88fdc735efd5a7ccdb8 |
| 1219815158 | FY2023 / 全文，297页 | 080827a40f33e613f876e60606daae838b83b715701c12a4f124712aa8bcbb7e |
| 1223301988 | FY2024 / 全文，294页 | f3422819a11c1962ed4ae74d9a62e47a44635fc9e8b9d4de1e446824bbb91b86 |

- 激活.venv后受影响13测试文件758 passed，pyright0 errors/0 warnings，pipcheck0；24修改生产/测试文件coverage均≥80%，最低85.03%。DS aggregate独立复现758，PR阶段另312聚焦测试/pyright通过；mimo-flash完成独立精确交付/证据适用性判断及两base verify/compare。现有结果对最终同代码/deps/config版本适用，没有仅依赖裸pass。
- 六次真实普通公开CLI，均独立tmpbase+新日志、原ticker/start/end、无overwrite/rebuild/FY-only，真实原exit0。clean/seeded首轮各取得35个完整候选；seeded保留原2摘要(1213161682/1223301999)共37源，与全文独立身份。三目标真实PDF、完成meta和真实SDK Docling模型/原件origin/fingerprint/非空正文一致，不用直链补下载代入口。
- 四次repeat均35skip、0conversion、已持完整源/三目标0PDF GET；落选GET精确clean4/seeded2各一次。所有source metadata/revision/PDF/JSON SHA及seed摘要全记录保持，原始HTTP transport/wire闭合、FYraw19未改写，failed/rejected/uncertain0。
- 修后两套真实顺序pureowner allocation replay各35pair相等，以及最终版两次真repeat通过；r1只两guard，正常发现/事实/取得/转换路径未变。首下载曾在未冻结工作树运行，三处后续收束成功路径等价与版本边界明示；不是新版首网络下载或历史raw/FILING_STARTED本体伪造。
- 原134证据清单最终逐hash仍相等；调用方受管目录/原日志未写。当前CLIhelp exit0、dayu import指向本工作仓库、pypdf6.1.3；包仍0.1.4，没有新发布。**本工作分支普通公开download入口已验收可用**；验证命令形态：

```bash
.venv/bin/dayu-cli --base <独立临时base> --log-file <新log> download --ticker 601225.SH --start 2018-01-01 --end 2026-10-12
```

## 审核、文档与风险

plan/planreview含真实fix/re-review已闭环；code两findingMiMo-01/02 accepted已修复，经DS194843+mimo-flash210515验证；aggregate两路正式pass；PR两路214956/214957正式pass。MiMo/Flash progress-only退出曾拒收，保留原记录并按规定一次补交/持久会话续收，未以runner0/建PR/自报替验收。用户改provider为mimo-flash已落实，DS Flash并行；Sol负责实际plan/implement/fix，总控逐gate裁决。三新版SKILL已重读并按当前gate职责复用同版真实验证，无空fix或额外全面重扫承诺。

README根/Fins/tests按职责更新；新增goal/plan/根因/实施/fix/各review裁决/ready与本closeout文档，two utils仅验收辅助不进生产。完整验收记录见[s1-controller-validation](601225-annual-fulltext-s1-controller-validation.md)、[code-fix-r1](601225-annual-fulltext-code-fix-r1.md)、[aggregate-adjudication](601225-annual-fulltext-aggregate-adjudication.md)、[PRreview裁决](601225-annual-fulltext-pr-review-adjudication.md)。这些可取回代码/文档版本与保存raw/命令/结果支持上述实际结论，不只是链接列表。

| 剩余风险/未覆盖 | Gateflow分类 | owner / destination与非阻塞边界 |
| --- | --- | --- |
| 历史启动树/raw/FILING_STARTED缺证、首下载最终commit未冻结 | assigned to later work unit | 总控/取证维护者；按需历史追溯或正常路径未来变化的新首验。用户禁止伪造历史，本次等价边界+两真repeat已证。 |
| 未知/OCR首页、其它公司公告、一般日期/财务处理、旧坏身份错年恢复 | assigned to later work unit | Fins discovery/facts/date/integrity维护者；真实输入后独立任务。goal非目标，未知闭合失败，当前三目标已验收。 |
| repeat落选原件GET成本、SDK有损origin/无durable derived_from历史因果 | assigned to later work unit | Fins性能/审计维护者；按需缓存性能或独立来源审计。完整源零GET/转换与实际两资产SHA均已证，不扩schema/cache。 |
| 资源全故障注入、防御分支/docstring、既有identity观察微窗口、外部gate/runtime投影 | assigned to later work unit | Fins source/workflow/identity/gate/runtime维护者；既有按需资源回归/并发契约/真实gate装配/投影任务。当前失败/取消/repair/正确摘要保留均有同源断言，无新反例。 |
| SEC旧repair模式存在性观察 | assigned to later work unit | SEC workflow维护者；真实输入后独立同源取证。非本PR改动，未证缺陷，不扩其它市场。 |
| GitHub无CI(checkruns/statuses0，headtree无workflow) | assigned to later work unit | repo CI维护者；按需独立CI建设。非本目标mandatory，当前本地checks充分，不称CI通过，不要求当前用户新决策。 |

两历史finding fixed in current slice；其它未分类风险/当前需newissue或用户决策项目为0。外部源/Docling本次真实验收通过，不承诺未来任意版本可用。

## issue状态与next entry

本任务是用户确认的独立bugfix，无给定GitHub issue，不创建issue/comment或虚构关联。

当前工作单元完成；下一入口为用户review draftPR并另行决定merge。merge/release后可按正常发布/安装流程使用修复入口，本次不操作调用方或merge。
