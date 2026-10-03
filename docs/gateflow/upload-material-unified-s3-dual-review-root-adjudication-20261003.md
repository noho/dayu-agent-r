# S3 首轮双路审查总控裁决

## gate、输入与执行

- 当前/下一入口：**fix S3（一次集中修复）**。普通 gate 连续推进；不是 S3 checkpoint/pass、不是正式 PR review。
- Workspace `/Users/leo/workspace/dayu-agent-r`，唯一开发 branch `codex/upload-material-oracle`；HEAD/base `a514dea14c0ce66722da034502f3af54a54c3238`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4`，均未改。
- 两路共同冻结：`workspace/tmp/upload-material-unified-repair-20261002/s3-review-01/frozen/identity.json`，SHA `71ba4bf96daa5807b1c6487c203005e5dd5a7a23b52915760595d647b8fe20ac`；24 个实际 S3 文件。总控在两路结束后分别逐项实核 12,123 原输入，零漂移。
- ds-flash：claude / `deepseek-flash[1m]`（init），label `upload-material-unified-s3-review-ds-flash-20261003-01`，session87781 托管 outer0、84,067 events/148 tool results、result success/is_error=false、canary match；完整根核收见 `upload-material-unified-s3-ds-review-root-adjudication-20261003.md`。
- MiMo：claude / `mimo-v2.6-pro[1m]`（init），label `upload-material-unified-s3-review-mimo-20261003-01`，session92805 托管 outer0、20,344 events/89 tool results、result success/is_error=false、canary match。
- 报告：`docs/reviews/code-review-20261003-072851.md` SHA `54ad6184e97a4cbddafc36d01445175ac0ff98db10e00ca6a81e05ec412b15fc`；`docs/reviews/code-review-20261003-074930.md` SHA `f36378dd2b9abccac2fc0007c848ea8086bd6e0c1c0853ef0e2f62c2a3924894`，实际字节已核。

## 自行裁决、去重与唯一修复集合

| 源 finding | 根 ID/裁决/状态 | owner、直接证据与动作 |
| --- | --- | --- |
| DS 1 | US3-R01 / accepted / 未修复 / P2 | Documents 实际 backend 生命周期。总控读生产卸载 helper、worker finally、Docling `_init_doc` 和实际 helper 探针；valid=false 未绑定 backend 时先访问属性，次生 AttributeError 替换内容 execution descriptor。只改 owner 访问时序及同源测试。 |
| MiMo 002 | US3-R02 / accepted / 未修复 / P2 | Fins worker owner tests。总控核现有非 XBRL targets 与外部资源 skip；需无资源的 dispatch/status/errors/export/finally 合同矩阵，R01 实际失败说明此缺口已产生漏检风险。与 R01 测试统一设计，不重复/镜像。 |
| 两路 D01 | US3-D01 / accepted / 未修复 / P2 | README 配置说明。仅改原件和管理员 taxonomy 源/请求快照文案，不新增原件位置限制。 |
| DS 2 / MiMo 003 | rejected-with-reason；去重同项 | 非 Python3.11 解释器支持超出当前 macOS arm64/Python3.11 已确认验收，当前实际路径存在且部署成功；不采 MiMo 顺带当前修自适应的建议。未来解释器/平台验证有 owner/destination，不改本目标。 |

全 accepted 集合 **R01/R02/D01** 已即时登记 `upload-material-unified-s3-review-findings-register-20261003.md`，当前三项都未修复，必须集中 fix + 同版独立双路 re-review 后才能 slice 放行。其它轻微抽象、字面量、未来 native 依赖/HOME 布局观察没有同源当前失败，不纳产品修复。

两路对已登记 T01/V02/E01/C01 的证据在当前冻结版本可采，尤其 C01 的三面 cause 与 35 个独立真实 ZIP owner tests 通过。不采“所有可能 stdlib 异常都不逃逸”的无界外推，仅已覆盖类别及同版本源码结论。

R01 父投影补充：`_read_terminal_result` 对失败 wait result 的 exitcode==0 为 IPC_PROTOCOL，**其它含 None 为 CHILD_CRASH**。此前坏输入只实跑 helper，不实跑 CLI；两路的固定 IPC 终局推断不能冒已经观察。缺陷是原 execution 被次生异常替换，不依赖唯一某个错误投影。修复后应取得实际 execution 结果。

## MiMo 完整轨迹失败与恢复

原完整轨迹：`workspace/tmp/upload-material-unified-repair-20261002/s3-review-01/root-audit/mimo-full-tool-trace.json`。已检查全部 89 工具结果，而非只看 final/成功共识。

| JSONL 行 / tool ID | 失败或预期反例 | 根核恢复与影响 |
| --- | --- | --- |
| 9817 / `call_f4dac610502c4418b8dd6a84` | `echo ===` 触发 zsh `== not found`，复合末0 | 9904 实际重新检查 requirements；其内容只是 `-e .[test,dev,browser]` 入口，依赖真源是 pyproject。无产品缺陷。 |
| 10657 / `call_75b6a27d6ee14ea2a482d575`，10665 错误读取 | 探针内部 exit1，首案例相对/非规范路径被 loader 提前拒；case2 父目录未建立抛 FileNotFoundError | 10711 修 `.resolve()`/parents，11772 修探针 case4 参数，11933 重跑内部 EXIT0；最终确在 ZIP 构造/读取边界观察 typed XbrlConfigurationError，而非仅准入提前拒绝。 |
| 11764 / `call_900b99ec7c6d4dde88e8e247` | cwd 已在 own tmp，重复相对 cd 不存在，工具 exit1 | 11772 在实际 own cwd 修改探针；11933 显式绝对 workspace 执行恢复。 |
| 20222 / `call_890629c7f1a74819a31f87f9` | 系统 timestamp 的待创建报告 `ls` 不存在 | 预期 exclusive-create 前置检查，不是关键来源读取失败；20248 `open('xb')` 实际创建并核 SHA 成功。 |

- 两路 stderr 均只有 `[claude-code:unrecognized_model]` 精确前缀 warning；不按失败处理。
- MiMo 的 probe 原 stdout/stderr 同名重跑覆盖，own synthetic probe-root 被清理重建；报告“首版 raw 保留”的自报不采。旧失败完整内容在 JSONL 工具结果和根轨迹原样保全，不能重造旧 raw。产品、既有历史工作/证据未被改动，12,123 保护字节均一致。
- MiMo 临时探针含 `object`/type ignore，与项目严格类型纪律不符；**不作为可维护工具或产品交付**，不提交该脚本，不作为类型通过证明。有效观察只采实际执行且由现有 typed owner 测试/根实际源码复核的部分。后续修复工具必须遵守类型纪律。
- 35 owner tests 的 actual EXIT0、`35 passed in 0.19s`、stderr0 实际工具返回可核；未重装、重跑668/全类型/OSmatrix。不把声明代替执行。

## 独立复核与保全

根实际读 Documents/config/Process/factory/runtime policy、actual Docling backend/`InputDocument` 合同、owner tests、README、两路报告和完整逐调用轨迹；各项成立动机及范围自行裁决，不凭双路一致。两路都核同版 24scope/12,123 输入字节、原 expected token 和模型 init；旧技术性 OS/取消证据仍按实际继承边界，不冒新实跑。

两路原 prompt/JSONL/stderr/canary 各有无损双副本（原 TMP 保留）于 `workspace/evidence/upload-material-unified-repair-20261002/runner-streams/<label>/` 与 `output/evidence-backup/upload-material-unified-repair-20261002/runner-streams/<label>/`，根 SHA 索引为 review root-audit 的 `mimo-runner-backups.json` / `ds-runner-backups.json`。许可财报/taxonomy raw 不入 Git。

MiMo 裁决块：

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings: [复合命令与探针自身失败已恢复, 首版raw自报按完整事件纠正, 临时不合规类型探针不作代码交付, unrecognized_model精确warning, 已限定无界成功外推]
evidence_gaps: []
retry_class: none
```

只表示经根限定的 review 结果可采，代码未放行。无 provider retry/switch。

## 文档与残余分类

- D01 fixed-in-current-S3-required-fix；R01/R02 同类，owner/destination 如表，当前未修。
- Linux/Windows 及未来解释器验证 assigned to later platform work，用户明确延期；Docling准确性 tracked by upstream #4437；FTP unknown、特殊 XML 关系未尝试、取消模型未观察保有界技术限制，不加准入。
- aggregate deepreview/正式 PR197 review 为后续 gate；完整 upload_material CLI CI/registry 是修复 WU closeout 后独立阶段，不能并入修复 WU。
- 当前 root control 下一入口同步为 fix；集中做完三项后冻结最终源，双路仅审本次修复与旧 finding closure，未变源按确切 SHA 继承已有走读，不重复安装/大回归/OS矩阵。aggregate 再一次统一受影响测试并集及全类型。
