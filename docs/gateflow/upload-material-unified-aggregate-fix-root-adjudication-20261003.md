# Aggregate 集中修复总控核收

## 身份、目标与状态

唯一 workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`，HEAD `ec54351e58e66cd5d00b009c862589b109064ade`；main `fac32ecbff9bfe792b63ee9667c8697826b631f4` 未动。三个 slices 已 accepted，本轮为 aggregate 同一 gate 的集中 fix，不新增 slice/WU。UA-R01/R02/R03/UA-E01 实施证据核收，四项仍须同版双路复审后才判 gate pass。

## 派发终态与独立核验

label `upload-material-unified-aggregate-fix-sol-20261003-01`；runtime codex / provider gpt-6-sol / actual model unknown（事件未提供，不猜）。独立绝对 cwd、fresh preflight、output/stderr/last-message；托管 session 76390 已返回 outer exit 0，126 个有效 JSONL events、54 个实际 command_execution、3 个 file_change，turn.completed、无 error events，stderr empty，指定读取结果逐字匹配。完整工具轨迹及 runner 原字节分别保存 workspace/evidence/sub-agents 与 output/evidence-backup/sub-agents 的本 label 目录；原始路径与所有 SHA 见 aggregate-fix-01/root-audit/runner-backups.json。

总控亲读 CLI shared handler→Service material 准入→typed source-integrity failure 同源链、新真实文件损坏测试、missing-identity 测试完整 diff；核 source-final-v2 的全部88文件、原84中仅两生产两测试变化，其余80完全相同。tests README 是单独受控输入，不误算进原84。十白名单逐SHA一致，9364保护项 zero drift，无白名单外更改。全部11验证 receipt 的 actual_wait/actual_exit/command/source manifest/双流字节SHA已独立核对；不以实施者摘要替代验证。

## 修改与实际验证

- UA-R01：CLI command owner 用实际 args.command_name 投影日志和错误前缀，typed failure/message/exit不变。12格材料真实仓储损坏×auto/update/delete，经实际 CLI/Service 准入拒绝，安全公开原因、正确命令归属、原 exception cause、业务目录 exactbytes 和 zero lifecycle writes 均断言；filing原6格+I/O/resolve边界保。
- UA-R02：移除无消费者私有旧常量，no-runner仍 shared owner；对应测试通过，不改变持久化或工作流。
- UA-R03：缺身份测试只用 tmp_path 隔离，4格仍相同 MISSING code、read_state.assert_not_called、目录不存在，不改产品校验顺序。
- UA-E01：carrier decoded exactbytes 等于 Git HEAD 原191字节，SHA `70a0f3577f8953319fd286c94822becc2dd8c6ec2ba6d76e8bc67172b4e12691`；原log明确ASCII导航而非历史stdout；manifest两受影响条目/validation同步真字节，其余24条和旧results/git_head不改，financial Raw不改。
- 两完整受影响测试文件：671 passed / 0 failed / 0 skipped，3个既有 edgartools warning；修改生产覆盖 CLI82.4411%、runtime90.6587%，全 pyright 0 errors/0 warnings/0 infos。
- `git diff --check main` actual0；新增carrier/report独立无尾空格/EOF空行。新增未跟踪文件最终仍须 accepted checkpoint 的完整 cached diff-check，不能以tracked结果替代。

紧凑长期验证：`evidence/upload-material-unified-repair-20261002/aggregate-fix-validation.json`；实施报告 SHA `0fdeca5adcc432c718c94589b104418b7ea118b94b96103393fe09e6f3e0fa99`；当前88输入 SHA `8b16119e01c413d869cf38a660ade0da5650ac4586a70530189abd002c1ca91d`。

## 全部可观测工具失败裁决

1. event17/item8 复合命令内部 rg 错写 dayu/ui/cli/commands/fins.py，NoSuchFile 被后续命令 outer0掩盖；event23实际 dayu/cli/commands/fins.py 正文恢复，总控亲读真实链，warning。
2. event34/item17 和38/item19 搜/读不存在 tests/fins/material_upload_test_support.py，复合outer0不代表该步成功；event40实际读 test_material_upload_publication.py 中 seed_material_upload_target，event52实际完整74–116 helper，最终新test直接引用该真实helper并671回归通过；warning，未声称不存在文件已读。
3. event60/item30 tests-union-01 actual2：两窄cov目标触发 NumPy collection import error，0测试执行。失败Raw/JUnit/receipt全部保留；event71独立import0，event90同源码同interpreter改用既有--cov=dayu完整671通过。内部NumPy根因未定位，不声称修复依赖；本轮必要验证已恢复，不新增生产/锁文件。
4. event73/item37 rg不存在 tests/cli/conftest.py actual2；event75/item38 tests/fins/conftest.py NoSuchFile内部失败被末命令0掩盖；实际 rg --files 定位仅 tests/conftest.py 并完整读取，warning，不虚报多conftest通过。
5. event100/item52 validation-readback-01 actual1：错误期待 before84 包含 tests README；event106实际枚举纠正四项变化，event108 readback02 actual0与root独立对照恢复，不改源或覆盖失败Raw。
6. event115/item60 carrier no-index diff-check actual1、双流empty，新增文件差异码为预期；完整tracked PRcheck0/新增carrier字节空白检查0。最终完整indexcheck仍为下一checkpoint gate要求，未冒no-index exit0。
7. event15大保护清单呈现截断，不作为逐字阅读证据；event19 compact manifest结构/identity检查、event27初扫/117末扫及root独立9364SHA zero恢复身份。工具正文的Traceback字样不是另一个工具失败。root自身先前大输出截断以精确error行和限定helper范围重读恢复，未缺关键证据。

全部其他actual命令轨迹已核，未恢复关键失败为空，不触发provider重派；完整trace `workspace/tmp/upload-material-unified-repair-20261002/aggregate-fix-01/root-audit/full-tool-trace.json`。delivery-readback event123 actual0，报告/summary/十路径SHA、newfile空白、保护清单与branch/head再次回读，receipt PID88516 actualwait0已核。

## 文档与风险

tests README职责内补充真实CLI损坏目标与隔离测试边界；根/fins README用户行为契约未新增，既有slice说明可继承。

- fixed in current slice：四项已实施，最终状态待同版双复审。
- fixed in current slice：原审scope缺口必须本gate补证；MiMo31tests+6配置/README完整变更逻辑，DS XBRL ZIP尾及 dayu README全文，不用grep名字冒覆盖。
- assigned to later work unit：用户已延期Linux/Windows部署验证，owner Documents/platform；当前仅macOS有效。
- tracked by existing issue：Docling抽取准确性与公开上游失败 Docling #4437，owner上游；版本升级/private backend稳定性另属 assigned to later work unit，owner Documents dependency maintainer，不误称#4437覆盖所有升级风险。
- assigned to later work unit：完整upload_material CLI CI及正式registry为修复WU后的独立阶段，由本总控继续执行；旧Raw已删除事实保留，不伪造历史。
- assigned to later work unit：既有22独立残余按原owner/destination保留，不本轮扩大目标；未来规模性能/对抗同进程不可变性需真实需求才评估，不新框架。

## 总控固定裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings: [recovered locator errors, recovered NumPy collection validation, corrected validation expectation, expected no-index difference, recovered large-output presentation]
evidence_gaps: []
retry_class: none
```

当前 next entry：同版 MiMo / ds-flash 两路 aggregate re-review，补原审实际scope缺口；aggregate尚未通过，不停普通gate、不进入CLI campaign。
