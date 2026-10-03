# S3 ds-flash 审查总控核收

## 当前 gate 与身份

- 当前 gate：`code review S3`；MiMo 仍在途。下一项为两路核收后集中 fix，不是 slice pass。
- 唯一 workspace/branch：`/Users/leo/workspace/dayu-agent-r` / `codex/upload-material-oracle`；HEAD `a514dea14c0ce66722da034502f3af54a54c3238`；main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。
- runtime/provider/actual model：claude / ds-flash / `deepseek-flash[1m]`（实际 init event，非仅自报）。label `upload-material-unified-s3-review-ds-flash-20261003-01`。
- 托管 session `87781` 经 `write_stdin` 返回 outer exit=0；84,067 个可解析 JSONL events，148 次实际工具调用/结果，唯一结构化终态 success、is_error=false、terminal_reason=completed；canary 与原 expected 逐字匹配。
- Artifact：`docs/reviews/code-review-20261003-072851.md`，实际 SHA256 `54ad6184e97a4cbddafc36d01445175ac0ff98db10e00ca6a81e05ec412b15fc`。总控另逐项实读冻结 12,123 个输入，零漂移，24 个 scope 在其中；未修改源码、测试、README 或既有冻结证据。

## findings 自行裁决

- finding 1 → **US3-R01 accepted / 未修复 / P2**，根因与最小 owner 修复见 `upload-material-unified-s3-review-findings-register-20261003.md`。总控已读实际 Documents helper、worker finally、Docling `InputDocument._init_doc` 以及实际探针源码/工具输出。有效输入前访问 backend 是确定缺陷；不靠双路一致判定。
- finding 2 → **rejected-with-reason**：非 3.11 支持不在当前 macOS/Python3.11 binding scope，报告自己也明确本机没有实际缺陷。未来解释器平台验证记录 residual，不通过 review 扩目标。
- US3-D01 → 原 accepted / 未修复保持，与全部本轮成立 finding 一次集中 fix。
- 报告关于该坏输入的 CLI IPC 终局仅是同路径源码推导，并非实跑 CLI 事实；后续 fix 验证须明确这一差别。只读生产 helper 已直接复现 AttributeError，足以裁决 root cause。

## 全轨迹失败和恢复

完整 148 工具轨迹：`workspace/tmp/upload-material-unified-repair-20261002/s3-review-01/root-audit/ds-full-tool-trace.json`。不以外层 success 或报告遗漏覆盖内部失败。

| JSONL 行 / tool ID | 实际失败 | 恢复和影响 |
| --- | --- | --- |
| 1273 / `call_00_0VRH3Hx1HUwU7frAQcXy6063` | zsh 未匹配 `workspace/tmp/*venv*`，outer 工具 exit1 | 1327 `call_00_ubPOGa6nqXyrpzrTFqa15745` 实际找到冻结 standard-venv；后续使用该解释器成功。探索失败已恢复。 |
| 20771 / `call_00_D2lGirOsqjD78YNzSfwI9271` | 猜错第三方 backend 路径；`echo ====` 又触发 zsh 错误，exit1 | 20874 定位实际 `backend/xml/xbrl_backend.py`；20927 `call_00_SNmRR8M2j7vIdZj7Ck052964` 成功读实际源码。关键上游取证恢复。 |
| 36267 / `call_00_ET_qRWnAAYS2JelPmfY6Owh6310` | 探针错误按 class 调实例方法；内部 exit1 被末尾 cat 的 outer0 掩盖，工具明确输出 `EXIT=1` | 36384 取得实际 TypeError；36434 `call_00_ET_eSoG5bhMFDH69KuLUOhQ8273` 实例调用恢复、内部 `EXIT=0`、实际 XML_XBRL 路由。非产品缺陷。 |
| 40704 / `call_00_IaIITrlX2gQNJfhqukn91744` | 复合命令 `echo ====` zsh 错误，exit1，后半失败映射搜索未完成 | 40780 单独读取 runtime 消息映射；40808 及 78961 实际读取 Fins kind→公开码映射，取证恢复。 |
| 40783 / `call_01_0NoKuU5fCDWr6jPFvWGW8464` | 未引用 `--include=*.py`，zsh no matches；末尾 head 掩盖前错 | 40808 `call_00_jnEvM1GdtFKxNK6xhIL60203` 改正确引用后成功读取唯一映射 owner。 |
| 54469 / `call_00_Zns6vISqGNRKmj6QWPGD1873` | cwd 改动后相对票据路径不存在，管道/echo 掩盖前错 | 54552 显式回唯一绝对 workspace；54558 实读 coverage、54993 实读源绑定与新 owner coverage，74986 核 11 组继承 ledger/SHA 无 mismatch。未把缺读当通过。 |

- stderr 仅 `[claude-code:unrecognized_model]` 精确前缀 warning，依 skill 不判失败。
- `probe-unload-invalid-xbrl` / production-helper / iXBRL 输出中的 AttributeError、XML syntax error 是有效失败内容反例，不是工具失败；探针真实 exit0 仅表示完成观察，不表示材料成功。
- 报告写“所有命令独立 exit/双流、无 compound 掩盖前错”与实际轨迹不符，**该自报不采纳**，以上根独立分类为准。首次 guess-format `.out/.err` 被同名重跑覆盖，不能声称两个原始文件都还在；旧失败事实已在原 JSONL 工具返回和根完整轨迹保全，不重造旧 raw。
- 若原报告说 4 个负例均有格式路由实测，根仅采实际探针 JSON 列出的 3 个旧 XML 负例和本次新 XML_XBRL 正确路由；不把未列 payload 扩写为独立实测。

## 验证与副本

- 总控实核 structured result、工具执行、canary、实际模型、artifact 字节 SHA、冻结文件逐项 SHA、source/probe/上游合同及所有 6 次可观测失败/隐藏失败的恢复。
- 未重跑大回归、全量类型、安装或 OS 矩阵；此前票据仍为原版执行事实。
- 原 runner prompt/JSONL/stderr/canary 已原字节双副本保全：`workspace/evidence/upload-material-unified-repair-20261002/runner-streams/<label>/` 与 `output/evidence-backup/upload-material-unified-repair-20261002/runner-streams/<label>/`；原 TMP 不删除。副本索引与 SHA：`workspace/tmp/upload-material-unified-repair-20261002/s3-review-01/root-audit/ds-runner-backups.json`。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings: [6次工具或内部失败均实际恢复, unrecognized_model精确warning, 复合命令及旧raw保全自报已按实际轨迹纠正, CLI终局仅源码推导不可冒实跑]
evidence_gaps: []
retry_class: none
```

accepted 只表示本路审查证据和经总控限定的结论可采；US3-R01/D01 未修、另一独立路在途，代码不能放行。没有重派或 provider switch。Linux/Windows/未来解释器验证为后续平台工作（用户延期）；抽取准确性归 Docling 上游既有 issue；完整 upload CLI CI/registry 是 WU 后独立阶段；其余 aggregate/正式 PR 为后续 gate。

历史笔误补充：集中收尾 root artifact 写“首轮21项工具恢复”，实际首轮完整 trace 和原表是 **22** 项；这里只纠正数量，不覆原冻结 artifact 或丢历史证据。
