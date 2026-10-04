# S3 六项增量双路复审核收与跨 slice 修复入口

总控裁决；不是完整 PR review，不给 S3 pass。

## 冻结同版与终态

HEAD a514dea14c0ce66722da034502f3af54a54c3238；main fac32ecbff9bfe792b63ee9667c8697826b631f4。唯一开发分支 codex/upload-material-oracle。旧 re-review 输入 12370 项 root 实际逐 SHA 零漂移，scope 24 项 SHA 6aae2616a06581a2439bd3b396ce8da8c17b1c1884fddc6d72715f3b9528333f。

MiMo label upload-material-unified-s3-rereview-mimo-20261003-01，runtime claude，实际 init model mimo-v2.6-pro[1m]；托管 write_stdin(session67966) 返回 actual outer0。12555 JSONL 全部有效，82 tool_use/results 一一匹配，result success/is_error false，canary match；报告 docs/reviews/code-review-20261003-090951.md SHA 8b64974fe72bfe2c46780fc19c928ee6668bfbde99a46b3d84ddc01bd1e0a77c。DS 终态和全部116工具独立核收详见 upload-material-unified-s3-ds-rereview-root-adjudication-20261003.md。两者都只采纳六项增量及必要主链，18 项未变源码按 SHA 继承。原 TMP 和双 runner-streams 备份逐字节同 SHA，不删。

## MiMo 可观测失败与恢复

完整 trace 保存 workspace/tmp/upload-material-unified-repair-20261002/s3-rereview-01/root-audit/mimo-full-tool-trace.json；以下行号为原 JSONL tool_use。

- 2063/2086/2142/7625/7638：第三方模块/类定位错误，前三处 stderr 被重定向 /dev/null，因此不声称诊断完整。2105/2155/2171/7655/7682/8161 后续实际定位并读取 InputDocument、XBRLDocumentBackend、document_converter、SimplePipeline，必要源码证据恢复。
- 5682：自写验证器遗漏带引号的 CLI failure 标记，错误返回 overall_ok false；5914/12285 修正后 12 receipt 与真实 CLI streams 同源，原失败输出保留。root 实际 CLI 已独立执行、公共仓储读回，不依赖该验证器。
- 7042：reverse check 实际0；已应用 after 状态的 forward check 必然不适用，打印的 forward-check-exit=0 是管道 head 退出，不能冒 git apply 通过。root 只采 reverse 与原始 before 六项 SHA 实证，不采该 forward 伪退出。
- 10867/10955/11387：自写校验工具类型/语法错误，管道的 PIPESTATUS 在该 shell 为空，不采它作类型退出证明；11512 实际工具输出0 errors 后必要字节扫描成功。11050误执行目录 actual126，11119绝对路径恢复。
- 首版自写 helper 被原地修改，没有独立旧脚本文件；不采报告“首版脚本保留”字面声明。完整原 Write/Edit/Bash 源内容留在 JSONL/full trace 可追溯；原失败流未消失。自写 helper 不作为产品合同或新增正式 harness。
- stderr 精确 unrecognized_model 是 skill warning；OMP179 不影响读取。其余 error-like 是读取既有失败证据/生产错误分支，不是新的工具失败。

## 裁决与入口

US3-R01/R02/D01 均已修复：valid=False 不访问未绑定 backend；child-owned 分类、单次 XBRL/PDF零调用/释放五格及真实坏输入；README管理员配置与用户原件边界一致。owner源码、真实 Docling 路径、12票据、native CLI execution失败/publication缺失均已 root 核。两个子 review 结论 accepted；不以报告一致代替直接证据。

root 另以最终源码实际运行42文件并集：2834 passed、7 failed、3 skipped；38修改生产文件覆盖最低84.825%，真实外部XBRL正例和四负例均 passed。新成立 US3-T03/T04 已即时登记 upload-material-unified-s3-cross-slice-validation-findings-20261003.md，均是 tests/fins/test_fins_ingestion_tools.py 迁移遗漏。该两项不在旧六项增量范围，不能用旧 review 放行完整 S3。旧失败 Raw/JUnit 保留。下一入口 fix S3：一次 gpt-6-sol 完成两处测试迁移，完整该文件/full pyright、生产字节零变；按原41未变测试及覆盖精确 SHA 继承后同版 focused双复审。不开新 slice/WU，不重复旧裁决或平台矩阵。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings: [third_party_locator_recovered, evidence_validator_recovered, forward_pipeline_exit_rejected, helper_types_recovered, initial_helper_preservation_claim_limited_to_stream, exact_model_warning]
evidence_gaps: []
retry_class: none
```

此块只验收 MiMo 指定增量复审，不代表 S3 gate pass。跨平台延期/Docling上游质量/FTP unknown/特殊XML未观察请求/取消模型未观察均保原残余，不新加业务规则。完整 CLI CI 与正式登记仍在修复WU closeout之后另阶段。
