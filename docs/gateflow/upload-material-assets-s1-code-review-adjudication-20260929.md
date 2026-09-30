# UM-O04/O23 S1 code review 总控裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；按 sub-agents 精确白名单为非致命诊断"
retry_class: none
```

- MiMo 独立 `$deepreview 当前改动`：`docs/reviews/code-review-20260929-114318.md`，runtime/provider/model 为 `claude/mimo/mimo-v2.6-pro[1m]`，label `assets-s1-code-review-mimo-20260929-01`。外部进程 exit 0，JSON `subtype=success`、`is_error=false`、`stop_reason=end_turn`、`terminal_reason=completed`，报告 canary `mimo-5a2fa687` 与预检原值一致；stderr 只有上述白名单诊断。结构化结果与 artifact 均已读。独立复跑为 1433 passed/1 skipped、pyright 0。
- 评审锁定 HEAD `1453a659`、tracked diff SHA-256 `837a486ef10f67e1e098457a1ef062302402c2768c0243add1a92767336c6ddf`，含六个未跟踪新生产/测试文件。该结果只对这一候选版有效。Kimi 第二路因供应商 HTTP 403 额度尚缺；不得视作 code gate pass。

## Finding 裁决

1. **001 中，采纳**。`ValidatedFinsUploadMaterialRequest` 是对外 typed handoff，但构造时不校验 selection/plan 对齐，下游分别把二者用于 `file_count`/事件和发布。应由此类型校验可验证的不变量，至少 ordered path 保序一致、material converter 与 ordered pairs 一致、filing primary 为空。原始请求与 selection 的比较应遵守当前 normalize/旧 delete 规则，不能借此片偷偷引入 O16 尚未裁决的 `delete+files` 业务拒绝。补构造期反例 owner 测试。
2. **002 低，采纳**。planner 已产生安全 basename，但 usage 投影丢弃它；大量文件冲突时用户无法定位。只改新增 planner reason 的投影文本和对应 owner/CLI 测试，复用的 create/update/原 CLI 缺失文件文案保持原契约。标签仍须有界且不泄露绝对路径。
3. **003 低，采纳**。material 指纹只含原件 name/hash/size/source，派生名不参与 skip；当前实施记录和 fins README 的一次性变化断言失实。改文档并引用实际公式；不改运行时 skip。
4. **004 低，采纳**。SEC/CN 两个残留 `FinsUploadMaterialFiles` 死导入删去，验证涉及 workflow 测试。
5. **005 低，部分采纳**。typed handoff 的对象身份与单次 admission 是本片 plan 明列的回归契约，应补在相应 owner/入口测试；`upload_failure` 斜杠白名单边界与陈旧测试名亦应收口。以精确行为断言为准，避免为了计数而插入只针对测试的生产 seam。

Open Questions：filing planner 的双输入单权威签名是本片原设计瑕疵，实施修复时若能不扩展语义地收敛应一并处理并补测试；若会改变 filing 身份则停止并单独登记。delete raw 携 files 的拒绝仍归 O16，不能在本片改动作合同。

当前 gate 为 `code review -> fix`；下一步 gpt-6-sol 仅修上述 accepted findings，重新跑受影响测试、pyright、逐文件覆盖与真实 CLI 必要回归，形成新精确 diff 后 Kimi/MiMo 同版 re-review。不得提交、集成或宣告通过。

## 总控对首轮 Sol fix 的新增反例（修复项持续登记）

- `assets-s1-code-review-fix-sol-20260929-01` 进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-a1333ea9` 匹配；但 70 个命令里六条非零，stderr 有 `apply_patch verification failed`，严格 `agent_status=failed`，只作代码候选。最终矩阵 1443 passed/1 skipped、pyright0、五个本轮改动生产文件覆盖91–95%、真实短文件名 CLI exit2 无发布。修复记录 `docs/gateflow/upload-material-assets-s1-code-review-fix-20260929.md` 已实读；当前 tracked diff SHA `ad8b77d51756bc12f176526e5599bb7fd05c6a53637550dbc54fdbf34a5502bd`，还有七个以上未跟踪新文件，不能以旧 MiMo review 放行。
- **F6 中，新发现且 accepted**：F2 把最多 240 码点的 canonical basename 放进上限同为 240 的完整 usage message，未扣除模板前后文长度。总控用本 checkout `.venv` 直接调用 `admit_fins_upload_material_request`：两个不同目录、相同 `"a"*222 + ".txt"` 路径，返回裸 `ValueError("usage failure message 超出长度上限")`，而短名返回 `FinsUploadUsageError(DUPLICATE_ORIGINAL_BASENAME)`；n=225/230/235 同样裸 ValueError。该文件名本身及其 `_docling.json` 派生名未超过 255 UTF-8 字节，故不是输入非法，而是唯一 usage 投影 owner 的有界预算错误。修复必须在 owner 边界保留 closed code 和安全、有界、可修正提示；若标签因消息预算需缩短，应由同一 helper 稳定裁剪/隐藏，不在 CLI/tool 下游兜底。补 owner 及真实 CLI 长 basename 重复冲突回归，断言 exit2、closed reason、消息≤240、不含绝对路径、零发布。
- **F7 低，新发现且 accepted**：material handoff `__post_init__` 用 `plan.converter_pairs is plan.ordered_pairs` 将 Python tuple 对象身份冒充业务同源语义。两组保序且元素相等的 tuple 语义一致，但手工构造会被拒绝；对象身份也不能证明来自同一次 planner。应按保序值相等校验并保留其后 pair name/path 不变量，补「值相等而 tuple 不同对象」构造成功与值不等失败的 owner 测试。此修正不影响 planner 正常产物或 O16 动作规则。
- F6/F7 同属当前 fix gate，先由 Sol 修再锁定新 diff 做双路 re-review。任何修复期间失败命令原样披露，不能以最终绿测抹去协议状态。

## F6/F7 二次修复候选核验

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol label `assets-s1-code-review-fix2-sol-20260929-01`，显式绝对 assets workspace，进程 exit0、JSONL `turn.completed`、36 条 command_execution 全 exit0、无 error/failed、stderr 空、canary `gpt-6-sol-23145034` 匹配。fix artifact `docs/gateflow/upload-material-assets-s1-code-review-fix2-20260929.md` 已实读；tracked diff SHA-256 `07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666`，未跟踪文件还须审查实读。
- F6 在唯一 `upload_usage_contract.py` 按模板前后文字计算标签预算，短名文案不变，长名保首尾和省略号、完整消息≤240；总控直接在同 checkout 重放两目录同名 `"a"*220/222/225/230/235+".txt"` 均得 `FinsUploadUsageError` 且消息长度240，240 个 `a` 则由原 canonical label 隐藏规则安全退为固定标签，不再裸抛。真实 CLI 反例、closed reason 与零发布由新测试断言。
- F7 改为保序值相等，构造期 owner 测试覆盖不同 tuple 对象等值成功和值不等拒绝。Sol 最终 1448 passed/1 skipped、pyright0、两改生产文件覆盖94/91%。环境仍复用主仓 site-packages；本轮前置拒绝未重跑真实 Docling，小 N 同 stem 真实转换仍由第一轮实施证据支撑。
- F6/F7 现标记「候选已修，待双路同版 re-review」；F1–F5 的修复亦待同一最终 diff 复审。不得因 Sol 派发 completed 或测试通过提前提交/集成。

## MiMo 同版 code re-review 与新增测试修复登记

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- label `assets-s1-code-rereview-mimo-20260929-01`：显式绝对 `/private/tmp/dayu-upload-assets`，独立 JSON/stderr/canary，进程 exit0，JSON `subtype=success/is_error=false/stop_reason=end_turn`、119 turns、canary `mimo-112adb9b` 匹配。review `docs/reviews/code-rereview-assets-s1-mimo-20260929.md` 已实读；锁定 HEAD `1453a659`、tracked diff SHA-256 `07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666` 与未跟踪候选。MiMo 独立复跑 1448 passed/1 skipped、pyright0、19/19 生产文件单独覆盖≥80%，并以聚焦探针复核 F1–F7 及真实 CLI 证据边界。结论 `pass-with-risks`，但 Kimi 同版有效第二路尚缺，**code gate 未通过**。
- **R1 低 accepted（测试修复）**：material planner 的两遍式原因分类旨在使 `a.txt` + `a.txt_docling.json` + `META.JSON` 的 `reserved_control_name` 不因输入正逆序改变；现实现/独立探针正确，现有 owner 测试只有单原因固定顺序。按已接受 plan 的 owner 矩阵补正逆序混合冲突断言，防未来单遍回退；不改产品代码或错误优先级。
- **R2 低 accepted（测试修复）**：F6 的完整 usage 240 码点预算已在 MiMo 长 UTF-8/隐藏标签探针中正确，但正式 owner 回归只用 ASCII。`tests/fins/test_upload_usage_contract.py` 补多字节长标签与 Cc 隐藏标签两组，断言 closed reason、完整文案≤240、可读且不泄漏路径；不重写现行正确 helper。此类边界测试直接锁用户可见合同，不是实现镜像。
- MiMo 的上限未来分离 OQ 仅为条件风险，当前 planner error 只由 material 抛出，不据此扩设计；O16/O25/O34 等原有残余保持。下一步 Sol 仅补 R1/R2 owner 测试并跑受影响测试/pyright/逐改文件 coverage；总控锁新 diff 后重新 Kimi/MiMo 同版 review。旧 MiMo 结果仍可作 F1–F7 修复证据，不能替代新 diff gate。

## Sol R1/R2 测试修复候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- label `assets-s1-code-rereview-r1r2-fix-sol-20260929-01`，显式绝对 assets workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、75 events/31 完成命令、canary `gpt-6-sol-a6078e2d` 匹配、stderr 空；三条命令 exit1（错误 plan 路径 `cat`、误查 `.venv/bin/pyright`、错误 fix artifact 路径 `sed`），故严格 `agent_status=failed`。修复记录 `docs/gateflow/upload-material-assets-s1-code-rereview-r1r2-fix-20260929.md` 已实读并逐条记失败，不能以最终绿测抵消。
- 总控独立读两个未跟踪 owner 测试：`test_upload_asset_plan.py` 增 3 文件正逆序均 `RESERVED_CONTROL_NAME`；`test_upload_usage_contract.py` 增长多字节规划错误的 240 码点有界完整消息及 Cc 固定隐藏标签，均走公开 planner→usage/public failure 路径、无产品改动。Sol 报 26 owner passed、571 相邻矩阵 passed、pyright 0、两 owner 覆盖率90/94%；本轮不把其自报当独立复测。tracked `git diff --binary` SHA 仍 `07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666`，**不覆盖未跟踪测试**；两测试内容 SHA-256 分别 `0e4fc501016f8eac9105542e6e907089aee6e8db9d69373b6a829a70d54f0143`、`2ff264cd6c75372dfd9cef58bcef9e15549718c00ec968a3ebd1489f748d7116`，总控复算一致。R1/R2 仅标候选已修，须按 tracked diff+两个文件 hash+未跟踪清单同版 Kimi/MiMo re-review 后才能接受/提交。环境仍复用主仓 site-packages；不把局部测试当全量发布验收。

## MiMo R1/R2 复审与新增 F8 裁决

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- MiMo `assets-s1-code-rereview2-mimo-20260929-01` 显式绝对 assets workspace，独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/terminal_reason=completed`、33 turns、canary `mimo-181dcbf4` 匹配。`docs/reviews/code-review-20260929-130410.md` 锁 HEAD `1453a659`、tracked diff `07281b59...` 与两个未跟踪测试 SHA；独立 26 owner/571 adjacent passed、pyright0。R1/R2 测试修复内容经总控实读公开 planner→usage→failure 断言后接受，F1–F7 无回退；这仍不是 Kimi/MiMo 双路 code gate pass。
- **F8 低，accepted／未修复**：`plan_upload_assets` 在同一逐文件循环中先判 `INVALID_ASSET_NAME`、再判 `RESERVED_CONTROL_NAME`，故同一批 `"a"*243+".pdf"` 与 `META.JSON` 正逆序返回不同 closed reason；review artifact 给两序直接探针，代码 `upload_asset_plan.py:268-283` 与 accepted plan“控制名分类不依赖原件遍历顺序”吻合。总控裁决控制名优先：整批先完成可判定的控制名分类，再对其它非法名报 INVALID，最后判普通业务资产碰撞。不得为此放宽非法名、只改 CLI 文案或在下游重算；在 owner 测试补 RESERVED×INVALID 两序且同 reason、转换前零副作用。若实现发现非法路径无法安全完成保留名判定，应保持 fail closed 并回裁决，不引入脆弱 fallback。
- R2 的测试精确断言消息填满 240 码点，强于公开“≤240”合同，登记为后续 helper 改动时需迁移的非阻断测试紧度风险；此刻生产文案行为未错。其它残余同前。下一 gate 仅 gpt-6-sol 修 F8 owner 代码/测试并验证，再锁新内容 SHA 由 Kimi/MiMo 双路同版 `$deepreview`；产品候选未提交/未进 PR #197。

## Sol F8 owner 修复候选核验

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `assets-s1-f8-fix-sol-20260929-01` 显式绝对 assets workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、26 完成命令全 exit0、无 error/failed、stderr 空、canary `gpt-6-sol-730be507` 匹配。fix artifact `docs/gateflow/upload-material-assets-s1-code-review-f8-fix-20260929.md` 已实读；HEAD `1453a659`，tracked diff SHA `07281b59ba635466ba700dbaf2a9b32f760e2efb4a33a618133ef39b1bd98666` 未变，因为两编辑文件均未跟踪，**不能单靠 tracked diff 认同版**。
- 总控实读 `upload_asset_plan.py`：在既有数量/重复前置规则后，保留首个非法名继续扫描其余可判定文件，控制名命中优先抛 `RESERVED_CONTROL_NAME`，全批扫描后才报 `INVALID_ASSET_NAME`，业务碰撞最后；无下游补偿。`test_upload_asset_plan.py` 新增 `"a"*243+".pdf"` 与 `META.JSON` 正逆序均预期 RESERVED，独立超长仍 INVALID，测试路径在 converter/storage 之前。两文件当前 SHA 分别 `3ad3d8551a1c94eec27b6f5b6180bf9264cf3e35e9f5ea40136d1c136f6a4780` 和 `c151535fed72342a801c367a9099e84d8991167ec9dec9b3a39f1f6fabef5225`；`test_upload_usage_contract.py` 仍为 `2ff264cd6c75372dfd9cef58bcef9e15549718c00ec968a3ebd1489f748d7116`。Sol 15 owner passed、该生产文件85.71%、相邻1212 passed/1 skipped、pyright0；混合超长名无法在本文件系统创建，真实 CLI 此反例未运行，纯 planner 前置拒绝为本边界证据。F8 标「候选已修，待双路同版 re-review」；F1–F7/R1/R2 均须随最终未跟踪清单复审后再接受 code gate。

## MiMo F8 复审与新增 F9–F11 裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- MiMo `assets-s1-code-rereview3-mimo-20260929-01` 显式绝对 assets workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、53 turns、canary `mimo-55d2b109` 匹配。`docs/reviews/code-review-20260929-133817.md` 锁 HEAD `1453a659`、tracked diff SHA `07281b59...` 与三份未跟踪 owner 文件 SHA；F8 的控制名×非法名正逆序已被独立确认，F1–F7/R1/R2 锚点无回退。独立 28 owner passed、相邻 1212 passed/1 skipped、pyright0。review artifact 披露一次非法 UTF-8 文件名探针命令 exit1（APFS Errno 92）；按逐命令协议严格 `agent_status=failed`，不能作有效 code gate。内容证据仍由总控实读 owner 后裁决。
- **F9 中，accepted／未修复**：planner 对含反斜杠的 POSIX basename 在碰撞键检查里识别非法，后续 `FinsUploadAssetPlanError.__init__` 又把该名交给严格 public label canonicalizer，后者抛裸 `ValueError`，覆盖了 typed `INVALID_ASSET_NAME`；同名重复路径的 `DUPLICATE_ORIGINAL_BASENAME` 亦如此。总控实读 `upload_asset_plan.py:69,275-297` 与 `direct_events.py:1094,1138-1140`，根因是错误 owner 向只接受合法 basename 的投影 owner 传非法输入。修在 planner 错误创建或其直接上游安全标签投影边界，保持 canonical label 唯一真源，不在 CLI/tool 下游兜底或放宽正常路径；测单名、重复名、长名混批正逆序均 typed、标签隐藏、有界无路径、零发布。
- **F10 低，accepted／未修复**：高代理名在 `normalize_upload_asset_path` 的 `Path.resolve` UTF-8 编码阶段抛 `UnicodeEncodeError`，早于 planner 分类循环；与 `META.JSON` 正逆序均绕过控制名优先和 sealed reason。总控实读 `upload_asset_plan.py:109,256,268-297`，确认异常边界位置；在 planner 同一 owner 对规范化失败分类为 `INVALID_ASSET_NAME`，保留可判定控制名扫描优先级；测高代理单名及与控制名正逆序 typed reason 和 UTF-8 可编码安全文案。不得以 APFS 无法创建该文件为 tool/JSON 输入不可达的理由。
- **F11 低，accepted／未修复**：低代理名在分类层可封闭拒绝，但 public label 隐藏规则仅看 Unicode `Cc/Cf`，漏 `Cs`，导致 typed failure 的 label/usage/JSON `ensure_ascii=False` 文案仍含不可 UTF-8 编码码位。总控实读 `direct_events.py:_public_file_label_requires_hiding` 与 planner 错误投影，确认 label owner 缺口；在统一 canonical label owner 对 `Cs` 隐藏，并测低代理 typed、完整 usage/public failure UTF-8 编码成功、标签不泄漏。不要靠每个消费者重算。
- F9～F11 均为当前资产规划公开失败合同的 owner 修复，不扩大到独立 O05/O16/O25；F8 标为内容已修但需随最终 diff 复审。下一 gate gpt-6-sol 修上述三项及对应 owner 测试，受影响测试、pyright、逐文件覆盖和真实可达 CLI 回归后再锁完整 tracked+未跟踪 SHA 进行 Kimi/MiMo 双路同版复审；不得提交或汇入 PR #197。

## Sol F9–F11 owner 修复候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `assets-s1-f9f11-fix-sol-20260929-01` 显式绝对 assets workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、38 条完成 shell 中两条 exit1（预检误写未跟踪路径；Python 汇总单行引号语法错误），stderr 空、canary `gpt-6-sol-6f4c08a6` 匹配，故严格 `agent_status=failed`，不能因最终绿测改判。fix artifact `docs/gateflow/upload-material-assets-s1-code-review-f9f11-fix-20260929.md` 原样记录失败；代码只作总控核读后的复审候选。
- 总控实读 `upload_asset_plan.py` 与 `direct_events.py` 差异：planner 错误投影改调用唯一 label owner 的已拒绝名称入口，严格合法 basename canonicalizer 未放宽；逐路径规范化捕获 `UnicodeEncodeError` 后继续扫描其它可判定控制名，控制名仍优先于非法名，碰撞最后；public label 隐藏判定加入 Unicode `Cs`。对应 owner/usage/公开 JSON/真实 CLI 回归在 fix artifact 列明。Sol 报相邻 1226 passed/1 skipped、聚焦 567 passed、两改生产文件覆盖 92%/86%、pyright0，真实 CLI 反斜杠名 exit2 零发布；代理字符在 APFS 不可建真实文件，以 planner/usage/JSON 边界测。总控没有把这些自报当独立复审。
- 当前 HEAD `1453a659`，tracked `git diff --binary` SHA-256 `d5fc19d7248dfc31d4865c03d12b585593107060f1ee9c07ccf22e90ebeba8ca`；未跟踪 planner `5fd4d7133ce4c908981adce9164bbd515818952fe200b8ad6e82ad67b5d252c3`、planner test `53a5b05d23962060b993b8f5cf76b67f9652824bbb9f4a3c891bd658d0cdd804`、usage test `1ce0bd923022196ea1842de91182852aab3088c010359ff38f71638f21950c4a`，其它未跟踪清单见 fix artifact。F9–F11 标「候选已修、待同版双路 code review」，F8 亦须复审；不提交/集成。

## MiMo F9–F11 同版复审与 F12/F13 裁决

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- MiMo `assets-s1-code-rereview4-mimo-20260929-01` 显式绝对 assets workspace、独立 JSON/stderr/canary，进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn`、88 turns、canary `mimo-6e2b92fb` 匹配。`docs/reviews/code-review-20260929-142240.md` 锁 HEAD `1453a659`、tracked diff `d5fc19d7...` 与三份未跟踪 owner SHA；内容确认 F9～F11、F8、F1～F7/R1/R2 无回退，独立 46 owner/1228 相邻 passed、pyright0、相关单文件覆盖达标。artifact 披露探针首跑缺 `PYTHONPATH` 的 `ModuleNotFoundError` exit1 与 zsh `===` 复合 shell exit1；严格 `agent_status=failed`，不能计有效 MiMo code gate。内容须由总控独立裁决。
- **F12 中，accepted／未修复**：真实 tool material 入口的 `_resolve_upload_file_path` 在唯一 admission 前内联 `expanduser().resolve()`，高代理/NUL 路径先抛原始 `UnicodeEncodeError`/`ValueError`，再被 tool `except ValueError` 的 `message=str(exc)` 投给 LLM；未知用户 `~name` 抛 `RuntimeError` 后被泛化为“上传任务未能启动”。总控实读 `upload_tools.py:490-515,121-137` 与 planner/admission 次序，根因是 tool 的第二路径规范化点遮蔽 planner typed owner。修复须让 material 的名字/解析失败先由唯一 planner/admission 形成封闭安全 usage（或其直接上游同源投影），保留现有文件存在性/大小预检的独立后续 WU 边界，不把原始异常文本投给 LLM，不复制第二套 code→message。补真实 tool JSON 高代理/NUL/未知用户与反斜杠名回归，断言封闭 reason、隐藏/有界文案、零 observation/job/发布；CLI 对实际可达同型输入给 usage exit 与安全文案，不对高代理 argv 作不可达承诺。
- **F13 低，accepted／未修复**：planner 逐路径规范化只捕 `UnicodeEncodeError`，`Path.resolve` 对 NUL 抛 `ValueError`、`expanduser` 对未知 `~name` 抛 `RuntimeError`，raw façade/direct 入口仍落裸异常或 `UNEXPECTED_RUNTIME`，与 F10「规范化失败属封闭 INVALID_ASSET_NAME」合同不符。总控实读 `upload_asset_plan.py:256-264` 与 reviewer 直接探针，修复在 planner owner 同一循环收口用户路径解析失败，并继续扫描可判定控制名，单独/混 `META.JSON` 正逆序测试封闭 reason；底层真正 OSError 操作失败保持独立分类，不以广泛 `except Exception` 吞掉。filing 路径有自己的 typed 投影，不据此强制两个来源同 code。
- F12/F13 与既有 `fins-material-file-existence-admission` 划界：本切片只修名字形状/解析失败的 owner 顺序与安全公开投影，存在性/非普通文件规则和旧成功路径不扩。F9～F11 标「内容候选已修、待最终双路复审」。下一 gate gpt-6-sol 修 F12/F13 及 owner/tool/可达 CLI 测试，锁 tracked+全部未跟踪 SHA 后 Kimi/MiMo 同版 code review；不得提交/集成。

## Sol F12/F13 候选与总控新增 F14

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `assets-s1-f12f13-fix-sol-20260929-01` 显式绝对 assets workspace、独立 JSONL/stderr/last-message/canary，进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-fe64fae9` 匹配；五条聚焦/coverage shell 非零与 README `apply_patch` 匹配失败如实记于 `docs/gateflow/upload-material-assets-s1-code-review-f12f13-fix-20260929.md`，严格 `agent_status=failed`，候选不计有效实施 gate。最终 agent 报相邻 1244 passed/1 skipped、pyright0、三改生产文件 coverage 92%/94%/86%。总控实读 planner 对 NUL/未知用户的封闭分类、material tool/CLI 先 admission 后文件状态预检及 owner/真实入口测试；F12/F13 **内容候选已修**，但以下新缺口须先修再双路 review。
- **F14 低，accepted／未修复**：tool 在 `except FinsUploadUsageError` 中以 `isinstance(exc.__cause__, FinsUploadAssetPlanError)` 决定 public `error` 用业务 code 还是 `invalid_argument`。同一 typed `FinsUploadUsageFailure` 一旦跨层重抛/重建而没有该 exception cause，tool 输出就变化；cause 是异常传播历史，非 usage 语义真源。总控实读 `upload_tools.py:122-141`、`ingestion_runtime.py:1488-1492`、`upload_usage_contract.py:48-89,259-281`：后者已有 planner reason→usage code 单一映射，公共 fact 仅 code/message。修复须在 Fins usage owner 明确并投影 tool 错误类别或等价 typed fact，使 tool 只消费同一 fact，不能按 `__cause__`、文案或第二张 planner code 表推断；保留 planner 公开 code 与 filing/ticker 等原有 `invalid_argument` 语义，补同一 fact 有/无 cause 的投影一致性及真实 tool/CLI 回归。若需增加字段，校验并测试 owner contract，避免把 tool 协议细节泄漏给 storage。禁止为旧测试添加下游兼容分支。
- F14 修后重锁 tracked diff、所有未跟踪 owner 文件并由 Kimi/MiMo 独立同版 `$deepreview`；F1～F13/R1/R2 仍需最终复审，未提交/集成。

## Sol F14 候选核验

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- gpt-6-sol `assets-s1-f14-fix-sol-20260929-01` JSONL `turn.completed`、canary `gpt-6-sol-9c18e1c9` 匹配，stderr 空、全部完成命令 exit0；会话中断后 exec session 句柄失效，进程退出码无法回读，故不把该次判为有效完成 gate。总控实读 `upload_usage_contract.py` 的 `REQUEST/ASSET_PLAN` typed category 与类别校验、planner 唯一 producer、tool 只消费 fact category，不再读取 `__cause__`；owner 测试覆盖共用 code 两种来源及有/无 cause 的真实 tool 同结果。**F14 内容候选已修**，有无 cause 的公开结果不再漂移。agent 报相邻 1515 passed/1 skipped、两改文件 coverage95%/94%、pyright0；总控尚未把自报代替独立复审。
- 当前 HEAD `1453a659`，tracked diff SHA `05d8977450722aa7cefbd51607ceec14721a1301b7d109ab4e98d46213b6c14b`，未跟踪 owner `upload_asset_plan.py` SHA `707d12a79c5cec4c97047749bc68bd0593a6e93adb39249aeac751bd791be7fc`、`upload_usage_contract.py` SHA `eac24f88fc6de8b8bd99811ce2e2042ff1cdd663e434d0ad417524e864bd532e`、对应 tests SHA 见 `docs/gateflow/upload-material-assets-s1-code-review-f14-fix-20260929.md`。下一 gate 同内容 Kimi/MiMo code review，未提交/集成。

## MiMo 最终 code review 新发现（Kimi 在途，修复已登记）

- MiMo `docs/reviews/code-review-assets-s1-final-mimo-20260929.md` 已落盘且进程 exit0；JSONL/canary 完整核验与 Kimi 同版仍待收齐。总控直接读了下列 owner 代码，不以 review 自述代替裁决。以下 F15～F18 均 **accepted／未修复**，须先 Sol owner 修复和测试，再双路锁新内容复审；本次不通过 code gate。
- **F15 中，路径循环误分类**：`upload_asset_plan.py` 的 `normalize_upload_asset_path` 对 `expanduser()` 与 `resolve(strict=False)` 合并调用，`plan_upload_assets` 合并捕 `RuntimeError` 并变成 `INVALID_ASSET_NAME`；自引用 symlink loop 属解析操作失败，不应给“改文件名”的 usage fact。于唯一路径 owner 分开未知 `~user` 等输入错误与 symlink loop/操作性解析错误，保留明确 typed operational projection；测真实 symlink loop 与 NUL/未知用户、有无其它控制名的首错顺序，并核 tool/CLI 零 observation/job/发布。不要在下游按异常文案补偿。
- **F16 中，裸资产计划绕过 handoff 不变量**：`UploadAssetPlan` 冻结字段但无构造不变量；`DoclingUploadService.prepare_upload` 公开收裸 plan，`_prepare_upload_asset_plan` 只做类型/空值判断，`_build_pending_assets` 由 ordered 原件名取 bytes 却由 converter pair 路径给转换文件名。`ValidatedFinsUploadMaterialRequest` 的检查不保护直接下层调用。于 plan owner 或 Docling 直接边界确保 material ordered/converter/path/name/docling 身份一致，在任何读取/转换/发布前拒绝；兼顾 filing converter 子集合法形状，补 plan 构造与 service 直调反例。
- **F17 低，usage category/code 校验单向**：`FinsUploadUsageFailure.__post_init__` 只拒绝 ASSET_PLAN 类别搭非 planner code，允许 planner-exclusive code 搭 REQUEST；tool 只能消费这个错误 fact。于 `upload_usage_contract.py` 明确 shared 与 planner-exclusive code 的双向不变量，并测构造拒绝、共享 code 双类别和 tool 有无 cause 同结果。
- **F18 低，LLM-facing files schema 规则不自足**：`FINS_UPLOAD_FORMAT_TEXT.upload_tool_files` 只说后缀/存在/非空，`maxItems` 只编码数量；遗漏重复 basename、控制名与 `deck.txt -> deck.txt_docling.json` 完整 basename 规则。由 `upload_format_contract.py` 文案 owner 给模型简短动作/输入约束及最小映射例，保持同一真源投影到 schema，并测 schema 实际内容。此处只写模型需要的可读规则，不暴露内部类型名或治理字段。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- MiMo `assets-s1-final-mimo-20260929-01` 进程 exit0、JSONL 309 条可解析、`turn.completed`、146 条 shell exit0、无 error/failed event、stderr 空、canary `mimo-ae05ea19` 匹配；一次预期无匹配的 `rg` exit1，违反本次任务正文额外“每条探索命令自身 exit0”，故不计有效双路 code gate。review 的四项 finding 由总控实读 owner 后分别接受，内容不能因结构化任务失败而丢失。文档锁漂移仅为总控 adjudication 自身后续追加，不影响三个 production owner 的哈希；下轮须重锁实际 owner/测试全体。

## Kimi 最终 code review 低风险项（进程在途，已登记）

- Kimi review artifact `docs/reviews/code-review-assets-s1-final-kimi-20260929.md` 已落盘，进程/JSON/canary 终态仍待收齐。总控实读本切片改动代码后接受下列 **F19/F20 低／未修复**；它们不替代 MiMo F15～F18，且不得让仍在旧快照上工作的 Kimi 遭并发写。已启动的 Sol F15～F18 在独立 clone 修复；本两项须在最终新快照单独交 Sol 或一并收口并复审。
- **F19 低，死导入**：`dayu/fins/pipelines/docling_upload_service.py` 已用 `UploadAssetPlan` 承 material selection，仍 import `FinsUploadMaterialFiles` 且无消费；删掉死导入，按相关模块测试和 pyright 验证。只处理该本切片遗留，不扩为所有 import 清理。
- **F20 低，修改函数 docstring 漂移**：`ingestion_runtime.py::_validate_runtime_upload_request` 实际 material 返回 `ValidatedFinsUploadMaterialRequest` 且可抛 `FinsUploadUsageError`，docstring 仍说 normalized request/只 filing usage；`docling_upload_service.py::_build_pending_assets` 的 `preparation` 已是 `UploadAssetPlan`，docstring 仍称 typed selection 投影。按实际签名/异常更新完整中文 docstring，勿借文档修订改变行为。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- Kimi `assets-s1-final-kimi-20260929-01` 进程 exit0、JSONL 316 条可解析、`turn.completed`、105 条 shell exit0、stderr 空、canary `kimi-c9124371` 匹配；两条 shell exit1（记忆无匹配与大矩阵测试失败）形成 `item.status=failed`，故不计有效双路 code gate。`docs/reviews/code-review-assets-s1-final-kimi-20260929.md` 内容 pass-with-risks、F19/F20 两个低 finding 已由总控直接确认。Kimi 的大矩阵 13 failed 经其拆分：12 个时序敏感用例在无 coverage 单独 12/12 通过，另一个 `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers` 在旧 HEAD 已有 service→fins import 违约，不能直接归因本资产切片；这两类仅记残余和验证条件，最终新快照仍须受影响测试、逐文件 coverage、pyright 与真实入口证据。F15～F20 均未关闭，产品未集成。

## 2026-09-30 主工作树集成候选：ds-flash 同版复审新增项（MiMo 在途）

资产候选已从隔离工作树三方合到 `codex/upload-material-oracle` 主工作树，O11 日期输入组合测试同步修正。冻结审查快照 base `359f907f`、manifest 56/56 SHA-256 一致，原始报告 `docs/reviews/code-review-20260930-085630.md`。第一路 codex/ds-flash 因越界探查 runner 配置及非零命令被中止、未采纳；一次修复性重派 claude/ds-flash 进程 exit0、JSON `subtype=success/is_error=false/stop_reason=end_turn/terminal_reason=completed`、canary `ds-flash-12b497c3` 逐字匹配，stderr 仅 `[claude-code:unrecognized_model]` 白名单告警。其审查中聚焦测试 880 passed/1 failed，失败为独立审查工作树共享主仓 venv 的 checkout 身份断言；总控在主工作树同范围 984 passed/1 skipped、pyright0。MiMo 同版终态仍待收齐，**code gate 未通过**。

总控按报告指向的同一 owner 调用链预登记下列 repair finding，MiMo 返回后再逐项最终裁决；不得因 F15～F20 候选已测绿而遗漏：

1. **I-R1 中／待修**：filing `_normalize_upload_path_for_filing` 只捕 `OSError/RuntimeError`，共享 `normalize_upload_asset_path` 现将未知用户目录的 `RuntimeError` 转成 `ValueError`，公开 filing prevalidate 于是越过 `FILE_NOT_FOUND` typed usage；tool filing 仍有第二路径解析点，会把同类输入误报 `job_start_failed` 或把 codec 原文投给 LLM。修复必须在 filing 路径准入 owner 与直接上游输入处收敛，不能只在 CLI/tool 下游兜底。
2. **I-R2 低／待修**：material delete + raw files 的新空 selection 绕过了旧 CLI 文件存在性/普通文件与数量守卫，但 summary/progress 仍读 raw 数量，形成已验证计划 0 与公开/持久计数 101 可不一致。O16 的最终业务拒绝规则仍待另议；本次至少恢复既有守卫并让数量事实同源，不擅自裁决 O16。
3. **I-R3 低／待修**：新 `UploadAssetPlan.validate()` 对手工构造的循环链接直接 `Path.resolve`，抛含绝对路径的裸 `RuntimeError`，与 F15 的操作失败分类及自身 Raises 不符；计划 owner 应给无路径明文的明确操作错误并测直接构造/Service 边界。
4. **I-R4 低／待修**：`DoclingUploadService.prepare_upload` 的公开 `selection`/Raises docstring 仍是旧 typed selection 描述，`normalize_upload_asset_path` 的 Raises 重复；按实际契约更新中文说明。

Open Questions 保留在原始报告：planner error 无标签构造、usage 固定文案斜杠白名单、schema 文案上限常量、O16 delete+files 最终规则；均不在未裁决前以局部 fallback 实施。下一 gate 为 MiMo 同版 review 终态、总控裁决，再交 Sol 修成立项并双路复审。

## 2026-09-30 集成候选修复与重新冻结

- 旧快照 MiMo 审查因运行会话中断，未取得结构化终态、canary 与审查 artifact，不计有效第二路。ds-flash 报告中的 I-R1～I-R4 经总控沿 owner 路径核证，全部采纳。
- gpt-6-sol 已在本地主工作树给出 I-R1～I-R4 修复候选，记录于 `docs/gateflow/upload-material-assets-s1-code-review-ir1ir4-fix-20260930.md`。Sol JSONL 有 `turn.completed` 与匹配 canary，但有五条失败命令且会话重启后退出码不可回读，严格 `agent_status=failed`，只能作内容候选。I-R1 将 filing 规范化的用户路径错误收敛到 typed usage，CLI/tool filing 去掉重复预解析；I-R2 恢复 material delete 原始文件上限、存在和普通文件守卫，且从已验证 selection/plan 投影统一 file_count；I-R3 在 plan owner 将循环链接解析失败收敛为不泄漏绝对路径的操作错误；I-R4 更新公开中文 docstring。O16 的 delete+files 最终业务规则仍保留另议。
- 总控在主工作树独立运行受影响与相邻 14 份测试文件，**1075 passed、1 skipped**；`python -m pyright dayu/ tests/ utils/` 为 **0 errors、0 warnings**，`git diff --check` 与 `git diff --cached --check` 通过。主工作树仍是 `codex/upload-material-oracle`、HEAD `359f907f`，本轮资产代码尚未提交或推送。
- 新候选已分别冻结到 `/private/tmp/dayu-upload-assets-review-final-mimo-20260930` 和 `/private/tmp/dayu-upload-assets-review-final-dsflash-20260930`。两份快照以 `359f907f` 为基线，56 个复制文件的 SHA-256 逐一相同，manifest JSON 的排序内容 SHA-256 为 `c64dfd78979605d3fd8c84becaf82bc1602dfc1e3df43b3bc6304f60ff1f4864`。MiMo 与 ds-flash 各自 preflight `setup_status=ok`、绝对 `--cwd`、独立 output/stderr/canary，正做同版复审；结果须经结构化核验和总控代码裁决，**code gate 尚未通过**。

## 2026-09-30 ds-flash 最终快照审查（MiMo 仍在途）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] deepseek-flash[1m]；精确白名单非致命诊断"
retry_class: none
```

- `assets-integrate-final-review-dsflash-20260930-01`：显式绝对审查 cwd、独立 JSON/stderr/canary，进程 exit0，JSON `subtype=success/is_error=false/stop_reason=end_turn/terminal_reason=completed`、141 turns，canary `ds-flash-8b808110` 与预检文件逐字相同。原始审查已复制为 `docs/reviews/code-review-20260930-093046.md`。独立审查工作树 56/56 快照 SHA 正确，聚焦 889 passed/1 checkout 身份环境失败、相邻 444 passed/1 skipped、pyright0；环境失败在主工作树的同范围绿测对照下不作产品 finding。
- **I-R5 低／accepted／未修复**：material delete 在 planner 的早退分支未规范化 raw 路径，CLI 后续 raw 文件守卫单独调用共享路径规范化。`~unknown/x.pdf` 的 `ValueError` 因而绕过 typed usage，真实 CLI exit1，而 create 同类输入为 `INVALID_ASSET_NAME`/exit2。总控实读 `upload_asset_plan.py` delete 早退、CLI 1167～1171 的第二解析点和公开 handler；应在 planner owner 对 delete raw 路径作同源形状分类，保留空转换计划和 O16 待裁决的业务动作规则，补 owner 与真实 CLI 回归。
- **I-R6 低／accepted／未修复**：`tests/fins/test_upload_asset_plan.py` 两处 `is` 把 tuple/条目对象身份固化为合同，但 owner 的 F7 裁决和 `UploadAssetPlan.validate()` 只要求保序值相等。改为值相等断言，并用等值不同对象的构造正例锁 owner 语义，不改生产身份算法。
- **I-R7 低／accepted／未修复**：`upload_format_contract.py` 的 LLM-facing 上限文本硬编码 `100`，而 tool schema `maxItems` 从 `MAX_MATERIAL_UPLOAD_FILES` 投影；测试也硬编码数字。当前两者相同，但未来改上限会使模型文案与准入分裂。把数量规则置于两层可共同依赖的唯一 owner，文案与 schema 同源投影并测一致；不得制造 import cycle 或让模型看到内部常量名。
- **I-R8 低／accepted／未修复**：`docling_upload_service.py::_build_upload_source_fingerprint` 签名已是 `filing_primary_original_name`，中文 Args 仍写旧 `filing_primary`。按实际仓储身份语义修 docstring，不改行为。
- 审查的其余 Open Questions（手工构造 validated handoff、O16 三入口 delete+files、planner 错误无标签、usage 斜杠白名单、重复 resolve）保持登记待单独证据/裁决；其中 O16 已由用户先前明确留给独立规则，不借本轮 I-R5 擅自统一所有入口。下一步等待 MiMo 同快照终态，再按证据合并修复清单；当前 code gate 不通过，不提交/推送资产代码。

## 2026-09-30 I-R5～I-R8 Sol 修复候选

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `assets-integrate-ir5ir8-sol-20260930-01` 在绝对主工作树执行，进程 exit0、JSONL `turn.completed`、全部完成命令 exit0、无 error/failed event、stderr 空，canary `gpt-6-sol-ff029304` 逐字匹配。修复记录 `docs/gateflow/upload-material-assets-s1-code-review-ir5ir8-fix-20260930.md` 已实读。Sol 未 stage、commit、push 或触及远端。
- 总控实读 `plan_upload_assets` 已让 material delete 在空计划早退前与 upsert 共用 raw 路径规范化分类；不可展开用户目录先成 `INVALID_ASSET_NAME`，循环链接仍抛无路径明文 `OSError`。两处身份测试按保序值相等，常量 `MAX_MATERIAL_UPLOAD_FILES` 在 `upload_format_contract.py` 唯一定义并由 planner/schema/文案消费，指纹 Args 已同步。Sol 新增真实 CLI owner 回归；O16 最终规则未改。
- 总控在主工作树独立运行扩展的受影响与相邻 17 份测试文件，**1347 passed、1 skipped**（3 条第三方废弃告警）；`python -m pyright dayu/ tests/ utils/` 为 **0 errors、0 warnings**；unstaged/staged diff check 均通过。I-R5～I-R8 状态改为「代码候选已修、待新快照双路复审」；MiMo 仍在读上一冻结快照，不可用其结论替代新代码审查。资产代码仍未提交或推送。
- 修复后第二版已分别冻结于 `/private/tmp/dayu-upload-assets-review-r2-dsflash-20260930` 和 `/private/tmp/dayu-upload-assets-review-r2-mimo-20260930`；两者基线同为 `359f907f`、manifest 完全相同，58/58 文件 SHA-256 匹配，排序 manifest SHA-256 为 `accb0da7dde2b94e1b39df079cd5b1d845f4f018f389a4692cfd249aba11688e`。ds-flash/MiMo 已各自 `setup_status=ok`、显式绝对 `--cwd`、独立 output/stderr/canary 后并行复审；旧快照 MiMo 的内容可作发现证据，但不能替代第二版 gate。

## 2026-09-30 第二版 ds-flash 复审裁决（MiMo 两版仍在途）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] deepseek-flash[1m]；精确白名单非致命诊断"
retry_class: none
```

- `assets-integrate-r2-review-dsflash-20260930-01` 进程 exit0，JSON `subtype=success/is_error=false/stop_reason=end_turn/terminal_reason=completed`、162 turns，canary `ds-flash-3b81ba13` 逐字匹配。58/58 SHA 与非 docs 改动覆盖通过；报告已复制为 `docs/reviews/code-review-20260930-100722.md`。独立聚焦 819 passed/1 checkout 身份环境失败、相邻 444 passed/1 skipped、pyright0；宽矩阵 76 失败有基线对照，其中 PTY/socket 沙箱、既有 service import 违约及 checkout 身份失败均不能直接归因本候选。总控主工作树 1347 passed/1 skipped、pyright0 保持。
- I-R5～I-R8 在第二版均被独立复核为有效；F15～F20、I-R1～I-R4、O11 组合未见回退。下列五项按 owner 源码和报告实际反例分别裁决，报告的「全低、无阻断」不替代修复 gate。
- **I-R9 低／accepted／未修复**：filing planner owner 测试 `test_upload_asset_plan.py:484` 仍 `selected is selection`，将对象身份误写为保序选择语义合同；改成值相等及必要字段身份断言，不改生产 planner 只为满足旧测试。
- **I-R10 低／accepted／未修复**：tool 共用 `files.maxItems` 取 material 100 上限，filing 静态准入取另一 `_MAX_TUPLE_ITEMS` 100。当前值一致但两个独立上限未来可能漂移，且 JSON schema 是两种上传共同字段；由公共上传数量规则 owner 明确共同 JSON 上界与各类准入的关系，schema 消费该合同、owner 测试锁关系。不得为了表面统一强迫两个业务类别永远同一上限，也不得让 schema 对合法 filing 输入错误限缩。
- **I-R11 低／accepted／未修复**：tool 新增直接 import `ingestion_runtime._validate_fins_upload_filing_static` 并读私有返回结构；filing 静态准入事实 owner 应提供公开朴素 API，tool 只消费公开文件选择。保持 Service/CLI/runtime 的现有校验与零 observation 语义，禁止兼容 wrapper 或第二套验证。
- **I-R12 低／deferred-with-owner**：material 现存文件状态预检的英文 LLM 文案与 filing typed 中文不同，直接证据成立，但 `git show HEAD` 可见该英文既存，且材料存在/非空准入已归独立 `fins-material-file-existence-admission` WU。本资产规划切片不凭表面文案改 tool 下游；队列保留 owner WU，待该 WU 把 typed failure 与文案同源收口。此项不阻断当前代码集成。
- **I-R13 低／accepted／未修复**：planner `_normalize_material_upload_paths` 的形状阶段先记录后项错误，组件阶段仅在 `invalid_path is None` 时登记，故同批 `a\\b.txt` 与 `~unknown/x.pdf` 两个顺序均把标签定为 `x.pdf`。reason 安全但定位偏离原始输入顺序。保留控制名优先的 reason 规则，在 planner owner 对同一 `INVALID_ASSET_NAME` reason 用原始保序索引选首个非法输入，补正逆序与隐藏标签回归。
- Open Questions 中 material raw 非法 action typed 化、validated handoff 手工构造、O16 三入口 delete+files 规则、planner 无标签错误、usage 斜杠白名单、重复解析、枚举值对齐均按各自 owner 保留；无当前真实入口与本修复片直接因果者不借本轮扩展。下一步 Sol 修 I-R9/I-R10/I-R11/I-R13，并等待 MiMo 两版的证据，若还有新成立项继续登记后同版复审。

## 2026-09-30 第一版 MiMo 审查文件中的中项预登记

- 第一版 MiMo 已在独立审查工作树写 `docs/reviews/code-review-20260930-101246.md`，但进程及 JSONL/canary 终态仍待收齐。总控先实读两条中项的同源代码；此处只登记内容裁决，不能把审查提前算有效 gate。该版测试存在共享 venv checkout 身份造成的一个非零命令，严格 runner 状态也须终态后单列。
- **I-R14 中／deferred-to-UM-O16**：raw Service/SEC/CN material delete 携缺失 `files` 仍会得到空 selection/plan，可能删除既有 source；CLI 独有的 raw 文件状态守卫不能成为共享合同。直接证据与 MiMo 001 相符，但这正是用户已确认的 `UM-O16-F01` goal（`docs/gateflow/upload-material-o16-action-files-goal-20260928.md` 明文要求 `delete` 必须零文件、共享 admission 在首事件前 typed 拒绝）；其实施计划仍未获双路 plan gate pass。资产规划 S1 本轮 I-R2 只恢复既有 CLI 守卫与统一零文件数，不能擅把 O16 未闭环计划作为本切片顺手实施。此项保留中严重度和唯一 owner WU，不宣称已修；PR 集成仍会带该已知行为，后续 O16 gate 完成后必须进入同一 PR #197。
- **I-R15 中／accepted／未修复**：material shared admission 对 `form_type=None`、`material_name=None` 仍能构造 `ValidatedFinsUploadMaterialRequest`，CLI/Service 会进入上传 lifecycle 后才被 SEC/CN workflow 的现有 `if form_type is None or material_name is None` 拒绝。现有 workflow 对包括 delete 的所有动作均要求两字段，因此没有动作歧义；应在 material admission owner 将缺少这两个必填业务身份投影为封闭 typed usage，在 Service factory/observation/job/首事件前拒绝，并以 CLI、tool、raw runtime、SEC/CN owner 回归证明零副作用。仅收口必填存在性，不借此提前实施 O06 长度或 O17 form 统一规则。下游旧校验应审查是否可移除，避免两套可漂移规则。
- MiMo 003 的 delete unknown-home 分类与已登记 I-R5 同一根因；第二版 ds-flash 已复核 I-R5 修复有效，不重复计新 finding。第二版 MiMo 仍在审冻结的 I-R5～I-R8 版本；I-R15 后续修复须再冻结新版本同版双路复审。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- 第一版 MiMo `assets-integrate-final-review-mimo-20260930-01` 后续进程 exit0、JSONL 402 条可解析且 `turn.completed`、canary `mimo-f33ee73e` 匹配、stderr 空；但七条 shell 命令 exit1/2（含 checkout 身份测试、预期失败 CLI 探针、coverage 依赖冲突、`git diff --no-index` 非零），严格 runner `agent_status=failed`，不计有效 code gate。原始报告已复制为 `docs/reviews/code-review-20260930-101246.md`；I-R14/I-R15 内容仍由总控按直接源码证据采纳或延后，不能因 runner 失败而遗失。第二版 MiMo 正在独立审修复候选。

## 2026-09-30 第二版 MiMo 审查文件中的裁决预登记

- 第二版 MiMo 已在独立工作树写出 `docs/reviews/code-review-20260930-102133.md`，进程/JSONL/canary 终态仍待收齐；当前结构化流已有非零命令，不能提前计有效 code gate。总控先沿同一 workflow 与持久化路径核对三个 finding，结果如下。
- **I-R16 高／rejected-with-user-contract**：报告认为 material 转换失败后已提交的公司 identity/meta 必须回滚。代码确实先提交公司 batch 再转换，探针所见公司独立持久化是真实观察；但 `docs/reviews/upload-material-um-o34-oracle-adjudication.md` 的用户已接受裁决明确：合法公司名称/ticker 是可独立复用的公司事实，F19/S19/L02/L04 材料失败或取消后可保留该已提交事实，材料文档仅在权威已发布 manifest 有条目时才算成功，CLI/Service 不得倒删公司来模拟跨事务回滚。故报告的预期行为与用户合同冲突；不改 company/source 为同 batch，不把该观察登记为待修 bug。审计仍应区分公司事实与材料成功。
- **I-R17 中／accepted／未修复**：public `ValidatedFinsUploadMaterialRequest` 可由调用方手工构造，`__post_init__` 只查资产对齐，不复用 raw `_normalize_upload_request` 的 strict O11 日期校验；runtime 对 validated handoff 原样返回，公开 SEC/CN validated 入口可写入 `2024-02-30` 并报告成功。总控实读 `ingestion_runtime.py` 构造器、raw 准入、validated shortcut 与 pipeline durable 写入路径，接受该同源反例。修复应在 validated handoff 构造/直接消费 owner 保证请求静态业务字段与唯一 admission 同源，非法日期、动作、ticker/必填身份不能绕过；不能在 SEC/CN 下游再解析日期。补手工构造、runtime/公开 pipeline 的零事件、零 job、零材料发布回归。
- **I-R18 中／deferred-to-file-state-admission，和 I-R12 同根因**：普通空 material 文件在 tool 被预检拒绝，而 CLI/Service 只查存在/普通文件，随后 converter 的 `input_bytes must not be empty` 被投为 `unexpected_runtime`。这是真实入口分裂，也会触发 O34 合法公司独立提交，但文件非空状态的跨入口 typed 准入已由 `fins-material-file-existence-admission` 独立 WU 拥有；此前资产 S1 goal/实施记录明确不扩到 file-state owner。I-R12 英文/中文文案也是该 WU 的同一根因投影，后续统一存在/普通/非空与 LLM-facing 文案。保留中严重度与原始反例，不在资产名规划切片加 CLI/tool 局部 `st_size` 补丁。
- 第二版 MiMo 的 F15～F20、I-R1～I-R8 回归意见作内容证据；I-R17 属新公开 validated handoff 引入的 owner 缺口，必须在本 S1 代码提交前修。I-R16/I-R18 不阻断本 S1 集成，但各自裁决/残余须进入 PR 证据。当前 Sol 正修 I-R9/I-R10/I-R11/I-R13，I-R15/I-R17 在同一主工作树串行后续修。

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- 第二版 MiMo `assets-integrate-r2-review-mimo-20260930-01` 进程 exit0、JSONL 230 条可解析且 `turn.completed`、canary `mimo-7999ebec` 匹配、stderr 空；但一次 jq 命令 exit127 和共享 venv 身份测试 exit1，严格 `agent_status=failed`，报告已复制为 `docs/reviews/code-review-20260930-102133.md`，只作 finding 内容证据。其高/中三项已按上述用户合同和 owner 链分别裁决，不能因 reviewer 自评「高」覆盖 O34 明确裁决。
- gpt-6-sol `assets-integrate-ir9ir13-sol-20260930-01` 进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-e194ab6e` 匹配；但四条 shell 非零及一次非白名单 patch stderr，严格 `agent_status=failed`，只作修复候选。总控已实读 `docs/gateflow/upload-material-assets-s1-code-review-ir9ir13-fix-20260930.md` 与关键代码：I-R9 改值相等测试；I-R10 的 filing/material 独立常量由 format contract 承载，共用 schema 取两者最大且实际准入各消费各自上限；I-R11 tool 消费公开 filing 静态 selection 投影；I-R13 planner 用原始输入索引选择同 reason 的首个非法标签。Sol 最终报告 840 passed、pyright0；总控 diff check 通过。四项状态为「代码候选已修、待主工作树独立测试与新快照双路复审」。
- I-R15/I-R17 的后续 Sol 主工作树派发已 `setup_status=ok`，显式绝对 `--cwd`、独立 output/stderr/canary，在途；不得把当前未完成修复算 closed。I-R14/I-R18 仍归已登记独立 owner WU。

## 2026-09-30 I-R15/I-R17 修复候选与总控验证

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `assets-integrate-ir15ir17-sol-20260930-01` 显式使用绝对主工作树，进程 exit0、JSONL 可解析且 `turn.completed`、stderr 空、canary `gpt-6-sol-99df71e4` 匹配；五条中途 shell 命令非零，依 runner 严格协议记 `agent_status=failed`，不能把这次 Agent gate 记为成功。代码与记录仍可供总控独立核证。原始 JSONL/stderr/last 位于 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.B7WO57/assets-integrate-ir15ir17-sol-20260930-01.*`；修复记录为 `docs/gateflow/upload-material-assets-s1-code-review-ir15ir17-fix-20260930.md`。
- 总控实读 owner：共享 material 准入现在拒绝缺失/空白 form 与 name，公开 validated handoff 构造和消费复核相同 raw normalization、文件选择与完整资产计划；SEC/CN 的公开 validated stream 在首事件前复核。没有实施 O06 名称长度、O17 表单规则、O16 delete+files 或材料文件状态 WU，也未改变 O34 公司事实独立提交裁决。I-R15/I-R17 状态为「修复候选，待同版双路复审」。
- 总控在主工作树独立运行 17 份受影响及相邻测试文件：**1376 passed、1 skipped**；`python -m pyright dayu/ tests/ utils/`：**0 errors、0 warnings**；staged/unstaged diff check 通过。仍须冻结同版候选并完成两路结构化复审，然后才能提交和推送资产代码。
- 用户在分支整合过程中进一步明确：所有尚未实施 WU 均须等待其它分支成果全部汇入 `codex/upload-material-oracle` 且近端/远端同步后才实施；本轮只处理整合代码自身的 review findings。I-R14/O16 与 I-R12/I-R18/file-state WU 保持 deferred，不在整合中顺带实施。

## 2026-09-30 I-R15 范围纠正与 r3 审查取消

- 总控交叉核对 `docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md` 的 **UM-O05-F01**、`docs/gateflow/upload-material-o05-required-identity-goal-20260929.md`、O07/O17 的既有依赖记录：material `form_type`/`material_name` 无条件必填且在生命周期前 typed 拒绝，正是**尚未实施的 O05 WU**。此前把 I-R15 判作资产 S1 整合必修并派 Sol 提前实现，是范围判断错误。现将 **I-R15 中／deferred-to-UM-O05**，保留原始复现与目标；不得在本次分支整合中提交其实现。I-R17 的 public validated handoff 绕过已实施 O11 严格日期准入仍属于当前资产 S1 新增边界的回归，可独立修复。
- r3 MiMo/ds-flash 快照 63 文件包含 O05 提前实施，因用户明确“先整合所有分支，后实施未实施 WU”而失效。两路 runner 均由总控送 SIGINT，进程各 exit130；不计 review gate pass，审查输出与工作树保留用于审计。总控先将 O05 代码从候选撤出并独立验证，再生成新快照双路复审。

## 2026-09-30 O05 撤出 / I-R17 保留的 Sol 候选

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `assets-integrate-remove-o05-keep-ir17-sol-20260930-01` 进程 exit0、JSONL `turn.completed`、stderr 空、canary `gpt-6-sol-443ec6c8` 匹配；两条中途 `rg` shell exit1，因此按 runner 严格协议记 `agent_status=failed`，仅采纳经总控核证的代码候选。JSONL/stderr/last 保存在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.oCmeks/`。修复记录 `docs/gateflow/upload-material-assets-s1-remove-o05-keep-ir17-20260930.md` 已实读。
- 总控代码核对：O05 专属 `_required_material_identity`、typed code/文案、validated 派生 form/name、前置身份拒绝及其测试/README 承诺已撤出；工具恢复原 `_required_text`，SEC/CN 恢复既有后期 `None` 判断。I-R17 保留共享 raw static admission 对公开 validated 构造/消费的日期、ticker、action、source kind、选择/plan 同源复核；未提前实施 O05。Sol 受影响测试 913 passed、pyright0；总控扩展测试与 pyright 正在独立重跑。通过后才冻结新同版快照复审。
- 总控扩展的 17 份受影响与相邻测试文件实际结果：**1374 passed、1 skipped**；`python -m pyright dayu/ tests/ utils/`：**0 errors、0 warnings**；staged/unstaged diff check 通过。O05 撤出后的代码候选可冻结为 r4，但仍须 MiMo/ds-flash 同版有效复审与总控裁决。
- r4 代码与相关裁决证据已冻结到 `/private/tmp/dayu-upload-assets-review-r4-mimo-20260930` 和 `/private/tmp/dayu-upload-assets-review-r4-dsflash-20260930`，64/64 文件 SHA 相同，排序 manifest SHA-256 `a86d47334574d6dbb4198ce2636418e4bdd8f1280a5c0c8529b26baf09adcddb`；两路各自预检 `setup_status=ok`、绝对 cwd、独立 output/stderr/canary 后并行在途。r3 被取消的结果不替代 r4 gate。
- **r4 审查准备错误／取消**：总控发现审查 prompt 指定的 `docs/gateflow/upload-material-o05-required-identity-goal-20260929.md` 未复制进两份 r4 快照，MiMo 对此 `sed` exit1；即使 runner 预检通过，审查材料不完整，不能计 gate。两路由总控 SIGINT 停止，进程各 exit130，原输出与快照保留。重新冻结时须把 O05 goal 纳入 manifest，并在派发前逐项核对 prompt 的所有相对文件均存在；代码候选本身未因该准备错误修改。
- r5 全新独立快照已补齐 O05 goal 并在派发前核对 prompt 指定的四份项目文件均存在；两树 65/65 文件 SHA 一致，排序 manifest SHA-256 `3ccfc2a2f57db9e2426a021150b53819c9125dc0bb3dcfa2b39e5a6891137fbe`。MiMo 与 ds-flash 均 `setup_status=ok`、绝对 cwd、独立 output/stderr/canary 并行在途。r3/r4 取消证据保留，不计 r5 gate。
- 总控另试对四个资产 owner 文件运行 `pytest --cov`，该可选覆盖率测量在收集阶段因本环境 NumPy `ImportError: cannot load module more than once per process` 退出 2，没有产出有效覆盖率，也没有执行用例；不得把它当产品回归或伪称达到单文件 80%。同一候选的不带 coverage 插件的 17 文件回归 **1374 passed、1 skipped** 与 pyright0 独立有效。若复审发现覆盖缺口再针对具体风险补证据。

## 2026-09-30 r5 ds-flash 审查与新修复项登记（MiMo 在途）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] deepseek-flash[1m]；精确白名单非致命诊断"
retry_class: none
```

- `assets-integrate-r5-review-dsflash-20260930-01` 进程 exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、135 turns、canary `ds-flash-26dd010f` 逐字匹配，stderr 仅上述白名单行。快照 65/65 SHA 与 manifest 匹配；原报告已复制到 `docs/reviews/code-review-20260930-112050.md`。审查者在 detached 树定向 1373 passed/1 skipped/1 个共享 venv checkout 身份环境失败、pyright0；总控主树同版 1374 passed/1 skipped、pyright0。
- 重点产品链路没有新的 correctness finding。审查确认 O05 专属前置必填未进入候选；O05、O16、material 文件状态继续 deferred，不把已接受 O34 合法公司事实独立提交误判为回滚缺陷。
- **I-R19 低／accepted／未修复**：总控实读四处 production import 块，`FinsUploadFormatFailureKind`、`sec_upload_workflow.Path`、`service_runtime.FinsUploadMaterialRequest/FinsUploadRequest`、`fins_direct.FinsUploadMaterialRequest` 在当前文件只出现在导入行；同块两个 filing/request 导入也已既存闲置。删除本切片新死导入及同块既存死导入，避免类型依赖与真实契约漂移；不改运行语义。用定向测试、pyright 和 AST/引用核对验证。
- **I-R20 低／accepted／未修复**：总控实读 `test_cn_pipeline.py` 与 `test_sec_pipeline_upload_material_stream.py` 共 14 行测试调用中 35 处恒真/恒假 `or` 表达式，如 `("create" or "auto")`、`(None or "auto")`、`tuple([file] or ())`，是从旧参数迁移到 request 时留下的死条件。改为当前实际值的直接字面量/tuple，测试断言和事件序列不变；不得以测试暗示 None 也经过当前 raw action API。
- 上述两项在 MiMo 同版结果回来后合并修复清单；所有低项仍须 owner 修复及复审，不因 reviewer 评为“非阻断”而直接提交。原报告的 `_MAX_TUPLE_ITEMS` 未来上限耦合、tool OSError hint 等列为 residual/open question，当前无上限分歧或新行为因果，不扩大当前 S1 范围。

## 2026-09-30 r5 MiMo 内容裁决与结构化失败

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: provider
```

- `assets-integrate-r5-review-mimo-20260930-01` 进程 exit0，JSONL 248 条可解析且 `turn.completed`、canary `mimo-3fc0576a` 逐字匹配、stderr 空，但一条未激活项目 `.venv` 的 Python 探针因系统 Python 缺 `docling_core.types.doc.items` 退出 1；后续已用 `.venv` 重试成功，也不能追认本轮严格 gate。原报告已复制为 `docs/reviews/code-review-20260930-112741.md`，仅作内容证据。需按 runner 规则用新 label 做一次同 provider 修复性同版重试，明确所有 Python 命令使用 `.venv/bin/python`、预期失败由脚本捕获且 shell exit0。
- **I-R21 中／accepted／未修复**：总控实读 `UploadAssetPlan.validate()` 仅核对路径、派生名和 exact 重复；`plan_upload_assets` 才核对控制名、casefold/Unicode 名碰撞、派生名 255 字节与 material suffix；`DoclingUploadService._prepare_upload_asset_plan` material 直接消费任意 `UploadAssetPlan`，只调用其不完整的 `validate()`。故直接 service 调用可绕过 planner 的前置拒绝。修复 owner 必须复用唯一 `plan_upload_assets` 名称/格式规则或收窄为不能伪造的准入 handoff，不能在 Service 下游另写一套校验。补手工计划带控制名、碰撞、非法后缀、超长派生名的 service 边界零读取/零转换/零发布回归；不改变 CLI/tool 正常语义。
- **I-R22 低／accepted／未修复**：总控实读 `plan_upload_assets` 先在 `seen_originals` 对重复 basename 抛错，再扫描 `is_document_source_control_name`；同批两个 `same.txt` 与 `META.JSON` 被判 duplicate，违背本 owner 注释和既有控制名优先回归所承诺的整批控制名先分类。将 duplicate 判断移到控制/非法形状分类之后、业务碰撞之前，并用两种输入顺序验证同一控制名 code、标签与安全文案。保持合法输入不变。
- I-R19/I-R20 的 ds-flash 证据仍成立；四项合并交给 Sol 在主工作树修复，再做新同版双路复审。MiMo 内容指出 O05 未提前实现，与总控核对一致。r5 至此不是双路有效 gate，资产代码仍未提交/推送。
- r5 MiMo 的一次同版修复性重试不再派发：I-R21/I-R22 已接受，r5 旧 SHA 必须修改，继续审旧 SHA 不可能通过内容 gate；该失败历史保留。Sol `assets-integrate-ir19ir22-sol-20260930-01` 已 `setup_status=ok`，显式绝对主工作树、独立 JSONL/stderr/last/canary，串行修四项在途。新候选冻结后再并行派 MiMo/ds-flash，且明确项目 Python 使用 `.venv/bin/python`。

## 2026-09-30 I-R19～I-R22 Sol 修复候选

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `assets-integrate-ir19ir22-sol-20260930-01` 进程 exit0、JSONL `turn.completed`、stderr 空、canary `gpt-6-sol-b8e20575` 匹配；中途五条命令 exit1（含初轮测试），严格记 `agent_status=failed`，代码仅作总控核证候选。报告 `docs/gateflow/upload-material-assets-s1-code-review-ir19ir22-fix-20260930.md` 已实读，原 JSONL/stderr/last 在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.QzqySd/`。
- 总控实读 `upload_asset_plan.py`：新私有 `_validate_material_asset_names` 是控制名、组件安全、派生名长度、duplicate basename、Unicode/casefold 碰撞与格式的唯一规则，plan 构造/`validate()` 和 planner 共用，service 的现有 plan `validate()` 因而在读取前拒绝损坏事实；没有在 Docling service 重算规则或引入 O05/O16。控制名检查移到 duplicate basename 前，其它优先级保留。总控实读 owner/direct service 新测试的控制名与重复名双顺序、五类裸计划与零读取/转换/发布断言；两份 pipeline 测试的死 `or` 已清除，七个死导入已删除。
- Sol 最终受影响及相邻 17 文件自报 **1386 passed、1 skipped**、全量 pyright0、diff check 通过；总控同范围独立重跑在途。通过后 I-R19～I-R22 状态为「代码候选已修，待新快照双路复审」，未提交/推送。
- 总控同一 17 文件矩阵独立运行结果 **1386 passed、1 skipped**，全量 `python -m pyright dayu/ tests/ utils/` **0 errors、0 warnings**，staged/unstaged diff check 通过。I-R19～I-R22 为「代码候选已修，待 r6 同版双路复审」；未改变 O05/O16/file-state 的 deferred 状态。
- r6 已分别冻结于 `/private/tmp/dayu-upload-assets-review-r6-mimo-20260930` 与 `/private/tmp/dayu-upload-assets-review-r6-dsflash-20260930`；68/68 文件 SHA 匹配，排序 manifest SHA-256 `dfc9af564931b07710b4ba0261f154ed61dd9d0d5ffe8501525a42fd3b4bd7f7`，六份 prompt 指定必读项目文件均存在。MiMo/ds-flash 各自 `setup_status=ok`、显式绝对 cwd、独立 JSON/JSONL、stderr、canary 并行在途；旧 r5 MiMo 的非零探针不追认有效。

## 2026-09-30 r6 ds-flash 复审与新修复项（MiMo 在途）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] deepseek-flash[1m]；精确白名单非致命诊断"
retry_class: none
```

- `assets-integrate-r6-review-dsflash-20260930-01` 进程 exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、89 turns、canary `ds-flash-c5e42878` 匹配，stderr 仅上述白名单提示；68/68 快照 SHA 正确。报告已复制到 `docs/reviews/code-review-20260930-115248.md`。审查确认 I-R19～I-R22 的主修复实际存在，I-R17/O11、O05 deferred、CLI/tool/Service 路径无回退；detached 17 文件 1385 passed/1 skipped/1 已知 checkout 身份环境失败、pyright0，主树同版 1386 passed/1 skipped、pyright0。
- **I-R23 低／accepted／未修复**：总控沿 `plan_upload_assets` 与 `FinsUploadMaterialFiles.__post_init__` 实读，正常路径先构造 selection，它立即检查 `.zip` 等 suffix；`UploadAssetPlan` 构造才执行整批控制名/重复名/碰撞分类。因此 `META.JSON + deck.zip` 在 planner/CLI/tool 得格式错误，裸 plan 得 `RESERVED_CONTROL_NAME`；本次 I-R22 修复反转了旧原因优先级。把 plan 构造/完整名称规则置于 selection 构造之前，或在同一 owner 先无条件完成分类；补混合输入双顺序、重复名+不支持格式与裸计划同结果的 code/标签/文案测试。仅改变非法混合输入的错误优先级，不改变合法发布。
- **I-R24 低／accepted／未修复，I-R21 相邻未闭合形态**：`UploadAssetPlan.validate()` 从 `filing_primary_original_name` 推断适用 filing/material 规则；Docling service 的 MATERIAL 分支仅调用无 source kind 的 `validate()`。带 filing primary 的手工 plan 可被 material 分支接受，绕过 material 名称/格式/数量检查，直到读取原件后由指纹函数抛未类型化 `ValueError`。在资产计划 owner 的公开消费校验中显式传入预期 source kind 或提供等价 typed 形态校验，MATERIAL 分支必须在任何文件读取前拒绝 filing 形态计划；不要在指纹或展示层补救。补 101 对与 `META.JSON` filing 形态计划的直接 service 零读取/零转换/零发布回归，filing 正常计划保持合法。
- **I-R25 低／accepted／未修复**：总控核查四个测试文件内 `FinsUploadMaterialFiles` 三处、`FinsUploadUsageFailure` 一处只在 import 行出现，均因本资产整合切片删除其用点而留下；测试 owner 也应移除闲置导入。另两处 base 即存在且导入块本轮未编辑，可一并清理但不虚报为新增。
- 三项已立即入队；待 MiMo 同版报告后合并派 Sol 修复，再冻结新快照。r6 当前不是 code gate pass，资产代码仍未提交/推送。原报告的未来上限耦合、tool OSError hint 等无本轮新直接缺陷，继续 residual，不顺带扩未实施 WU。

## 2026-09-30 r6 MiMo 内容裁决与合并修复清单

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: provider
```

- `assets-integrate-r6-review-mimo-20260930-01` 进程 exit0，JSONL 227 条可解析且 `turn.completed`、canary `mimo-229317e7` 匹配、stderr 空，但一次 `.venv` 探针对 macOS 未规范化 `/tmp` 路径直接调用 `filing_original_storage_name`，异常穿透导致 shell exit1；严格 `agent_status=failed`，后续规范化重跑不能追认本轮通过。报告已复制为 `docs/reviews/code-review-20260930-115848.md`，内容单独裁决。
- MiMo finding 001 与已登记 **I-R24 同一根因**，不另编号；其确认 direct material service 可接受 filing 形态计划，并在 `read_bytes` 后才由 fingerprint 的 `ValueError` 拒绝。依据更完整证据将 **I-R24 严重性调整为中**：公开直接 Service 边界的 owner 准入被绕过，存在整批原件 I/O 放大。修复仍限资产计划 owner/直接消费契约，不能靠 fingerprint 下游补救；显式 source kind 字段与类型拆分都是可选设计，Sol 应按现有调用图选择最小清晰方案，不把 reviewer 的结构偏好直接当成指定实现。
- **I-R26 低／accepted／未修复**：总控实读 owner 数量分支 `UploadAssetPlan.validate()` 对 material `>100` 拒绝，但现有 101 测试只走 planner 的先行上限；裸计划和直接 service 均无 101 对的判别性回归。补直接构造 101 个规范且不同名 material pairs 的 owner reason 断言，再在 direct service 边界对篡改计划断言零读取/零 converter/零发布。此项与 I-R24 101 filing 形态计划反例分别验证不同分支，不用一个冒充另一个。
- MiMo 未将测试死导入单列，其报告 residual 与 ds-flash I-R25 同根，不重复计 finding。r6 双路内容合并为 **I-R23/I-R24/I-R25/I-R26** 四项待修。r6 一路有效、MiMo 严格失败且内容有成立项，不计双路 gate；新 SHA 修复后重新冻结复审。O05/O16/file-state 仍 deferred，资产代码未提交/推送。
- Sol `assets-integrate-ir23ir26-sol-20260930-01` 已 `setup_status=ok`，显式绝对主工作树、独立 JSONL/stderr/last/canary，串行修 I-R23～I-R26 在途。要求在资产计划 owner 明确 source kind、复用唯一名称/格式规则，让直接 material service 在读取前拒绝 filing 计划；两类 101 文件反例分别证明，O05/O16/file-state 不得混入。

## 2026-09-30 I-R23～I-R26 Sol 修复候选

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `assets-integrate-ir23ir26-sol-20260930-01` 进程 exit0、JSONL `turn.completed`、stderr 空、canary `gpt-6-sol-1480043b` 匹配，但四条中途 shell 非零（含初轮用例失败），严格记 `agent_status=failed`，只作总控核证代码候选。原 JSONL/stderr/last 在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.uKU2UM/`；修复记录 `docs/gateflow/upload-material-assets-s1-code-review-ir23ir26-fix-20260930.md` 已实读。
- 总控实读 `UploadAssetPlan` 现必填显式 `source_kind: SourceKind`，构造及消费校验不再从 filing primary 反推类别；material service 在读取前与预期 source kind 对齐。planner 先构造完整 plan，再生成带格式校验的 selection，混合非法输入的资产原因优先级同源。四个测试模块死导入已清，裸 material 101 和 filing 计划误传 material 的零读取/转换/发布负例独立存在；O05/O16/file-state 与 O34 均未实施或改写。
- Sol 最终报告聚焦 **479 passed**、相邻原 655 passed/1 skipped/1 旧断言失败，更新断言后单项及两个关键 Service 反例各自绿；全量 pyright0、diff check 通过。因相邻矩阵未在最后断言修订后整组重跑，总控已启动完整 17 文件独立回归与 pyright；结果出来前不冻结或提交。
- 总控在最后断言修订后独立重跑完整 17 文件受影响及相邻矩阵：**1399 passed、1 skipped**；全量 `python -m pyright dayu/ tests/ utils/`：**0 errors、0 warnings**；staged/unstaged diff check 通过。I-R23～I-R26 为「代码候选已修，待新 SHA 双路复审」，仍未提交/推送。

## 2026-09-30 r7 ds-flash 复审与即时修复登记（MiMo 在途）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] deepseek-flash[1m]；精确白名单非致命诊断"
retry_class: none
```

- `assets-integrate-r7-review-dsflash-20260930-01` 进程 exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、134 turns、canary `ds-flash-edff21f9` 逐字匹配，stderr 仅上述白名单行。其报告已复制到 `docs/reviews/code-review-20260930-122553.md`；独立快照 71/71 SHA 与排序 manifest digest `80787926e966765aff7fa206d1eaf277dec3afbaf95cfb58d9b3ae9c5afbd579` 一致。审查确认 I-R23～I-R26、I-R17/O11 的修复保留，O05/O16/file-state 仍 deferred，O34 独立公司事实未回滚。
- **I-R27 低／accepted／未修复**：总控实读 `dayu/fins/ingestion_runtime.py:7833-7850`，`_raw_upload_request` 本轮把 material 入参改为 `ValidatedFinsUploadMaterialRequest` 后，`if isinstance(...Filing...)` 的两臂均 `return request.request`，且 Args 仍把 material 称 raw request。收敛为单次返回，更新中文参数说明；不加兼容分支。受影响准入/投影测试与 pyright 验证。
- **I-R28 低／accepted／未修复**：总控实读 `tests/fins/test_fins_service_runtime.py:326-387`，测试断言 filing 2 + material 1 = 总数 3，而 docstring 仍写“四个 parser callsite”。修测试文档为三个，运行该测试确认断言仍绿。
- 审查报告的 exact 重复规范路径与控制名先后只列 Open Question；本轮 plan/测试已有明确 `DUPLICATE_FILE_PATH` 先于名称分类的合同，且尚无用户裁决要求其反转，不作为新修复项顺带修改。O16 等其它未实施 WU 不在整合时启动。r7 MiMo 仍在途，其临时 digest 猜测脚本有 exit1，严格结果不能计有效第二路；其内容须待报告后总控再裁决。资产候选未提交/推送。

## 2026-09-30 I-R27／I-R28 Sol 修复候选

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `assets-integrate-ir27ir28-sol-20260930-01` 进程 exit0、JSONL `turn.completed`、stderr 空、canary `gpt-6-sol-ebac7635` 匹配；27 条命令完成 exit0，但两条探索命令 `rg` 无匹配、`ls` 包含不存在的下级 AGENTS.md 退出 1，严格记 `agent_status=failed`。JSONL/stderr/last 保存在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.QASyoZ/`，代码仅为总控核证候选。
- 总控已实读 `ingestion_runtime.py:7833-7848` 与 `test_fins_service_runtime.py:326-327`：前者为单次 `return request.request` 并更新 Args，后者 docstring 为“三个”；没有扩张 O05/O16 等 WU。修复记录 `docs/gateflow/upload-material-assets-s1-code-review-ir27ir28-fix-20260930.md` 已实读。Sol 指定两文件 446 passed、全量 pyright0、diff check 通过；总控最终完整矩阵与新快照复审尚待 MiMo r7 内容裁决后进行。I-R27/I-R28 状态为「代码候选已修，待复审」，未提交/推送。
- 总控在 I-R27/I-R28 最后改动后独立重跑 17 文件矩阵：**1399 passed、1 skipped**（仅第三方 edgar 弃用提示），全量 `python -m pyright dayu/ tests/ utils/`：**0 errors、0 warnings**。r7 MiMo 旧快照内容仍在途；若无新增成立 finding，再冻结修后快照复审。未提交/推送。

## 2026-09-30 r7 MiMo 内容裁决与结构化失败

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: provider
```

- `assets-integrate-r7-review-mimo-20260930-01` 进程 exit0、JSONL 362 条可解析、`turn.completed`、166 条 exit0 命令、canary `mimo-54f49ad9` 匹配；但六条命令非零（三处 Python 单行语法错误、一次 `rg` 参数错误、一次 `rg` 无匹配、一次受 sandbox 拒绝的 `pkill`），stderr 另有六行 router 函数参数解析错误，严格不能计有效第二路。原 JSONL/stderr/last 保存在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.JHe8G0/`，报告已复制到 `docs/reviews/code-review-20260930-124020.md`，只作内容证据。
- 总控实读该报告，MiMo 对 r7 冻结 71 文件给 `material finding 0`，确认 I-R23～I-R26、I-R17/O11、O05 deferred、O34 合法公司事实独立提交均无回退。其未发现 ds-flash 的 I-R27/I-R28，不推翻总控对源码和测试说明的直接证据；两项已按 owner 修复候选并通过总控 1399 passed/1 skipped、pyright0。未从 MiMo Open Questions 接受新修复项：斜杠白名单、O16、material file-state、filing provenance 均属既登记 residual/独立 WU 或未证实本轮回归。
- r7 只有 ds-flash 一路结构化有效，且之后代码已变。下一步在 I-R27/I-R28 修后同版快照做**新双路**复审；旧 MiMo 失败轮不追认，新 SHA 前不提交/推送。

## 2026-09-30 r8 ds-flash 修后复审与即时修复登记（MiMo 在途）

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] deepseek-flash[1m]；精确白名单非致命诊断"
retry_class: none
```

- `assets-integrate-r8-review-dsflash-20260930-01` 进程 exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、39 turns、canary `ds-flash-e0922887` 匹配，stderr 仅上述白名单行；报告已复制至 `docs/reviews/code-review-20260930-124812.md`。r8 冻结 74/74 文件 SHA、manifest 摘要 `04c8e41da9b06479803632c58f6364d12883cc167b8453c2154b8417d461282b` 是总控独立核对证据，审查者只读 manifest、未自称重算。其内容确认 I-R27/I-R28 同值收敛和说明修正无回归，I-R23～I-R26、I-R17/O11、O05 deferred、O34 均保持。
- **I-R29 低／accepted／未修复**：总控沿 `dayu/fins/service_runtime.py:139-154,198-234` 实读，`run_upload` material 分支传 `ticker=normalized.canonical` 到唯一 `_run_material_upload` 调用点；该私有方法的 `ticker: str` 与 Args 说明没有任何方法体引用，下游 pipeline 自己从 handoff raw request 的 ticker 归一化。故此参数无生效链，暗示 runner canonical ticker 生效但实际未消费。owner 为 runner 装配边界；删除私有形参与唯一调用点实参、对应 Args，不改变 market 路由、handoff 或下游 ticker owner。用 `test_fins_service_runtime.py` 和相邻 service 测试、pyright 验证；不转发另一份 ticker 造成双真源。
- 总控进一步对照 `git show HEAD:dayu/fins/service_runtime.py`：旧 `_run_material_upload` 曾把 `ticker` 传入 `sec_pipeline.upload_material(...)`，本次 validated handoff 改为调用 `upload_material_validated(request, ...)` 后失去该消费，证明是本整合切片引入的死参数，不是仅凭编辑器提示推断的旧代码味道。
- r8 MiMo 同版仍在途；I-R29 已即时入队，待其内容去重后让 Sol 窄修。未提交/推送，未实施 WU 不启动。

## 2026-09-30 I-R29 Sol 修复候选

```yaml
setup_status: ok
agent_status: failed
tool_evidence: yes
canary_status: match
warnings: []
retry_class: none
```

- `assets-integrate-ir29-sol-20260930-01` 进程 exit0、JSONL `turn.completed`、stderr 空、canary `gpt-6-sol-023f3ca8` 匹配；一条对记忆索引的无匹配 `rg` exit1，严格记 `agent_status=failed`，只作总控核证代码候选。原 JSONL/stderr/last 在 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.1ustbF/`。
- 总控实读 `dayu/fins/service_runtime.py:147-152,197-209`，唯一调用点和私有方法均已删除未消费 ticker，market/handoff 保持；修复记录 `docs/gateflow/upload-material-assets-s1-code-review-ir29-fix-20260930.md` 已实读。Sol 指定三个测试文件 **81 passed**、全量 pyright0、diff check 通过。r8 MiMo 旧快照仍在途；其内容裁决和总控完整矩阵、修后新同版复审前不提交/推送。I-R29 为「代码候选已修，待复审」。

## 2026-09-30 r8 MiMo 同版内容裁决及 I-R29 后总控验证

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

- `assets-integrate-r8-review-mimo-20260930-01` 进程 exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、42 turns、canary `mimo-1ae6b0ff` 匹配，stderr 仅上述白名单行；报告已复制到 `docs/reviews/code-review-20260930-124624.md`。该冻结快照报告 `material finding 0`，确认 I-R27/I-R28、I-R23～I-R26、I-R17/O11 无回退，O05 deferred、O34 独立公司事实保持。其未发现 I-R29 不推翻 ds-flash 与总控的同源代码证据；r8 两路结构化均有效，但 ds-flash 有 accepted I-R29，故内容 gate 未通过。
- 总控在 I-R29 最后改动后独立重跑完整 17 文件矩阵：**1399 passed、1 skipped**（仅第三方 edgar 弃用提示）；全量 `python -m pyright dayu/ tests/ utils/`：**0 errors、0 warnings**。I-R29 为「代码候选已修、待新同版双路复审」，资产代码和历史归档仍未提交/推送。r8 旧 SHA 的 MiMo 零 finding 不能替代新 SHA 复审。

## 2026-09-30 r9 修后同版双路最终裁决

MiMo：

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] mimo-v2.6-pro[1m]；精确白名单非致命诊断"
retry_class: none
```

ds-flash：

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
canary_status: match
warnings:
  - "Claude stderr: [claude-code:unrecognized_model] deepseek-flash[1m]；精确白名单非致命诊断"
retry_class: none
```

- 两份独立 detached 快照冻结同一 77 文件候选，逐文件 SHA 77/77 与主工作树一致，排序 manifest 摘要 `946fd54f2f78802801e92451b4d1a9764340c3a3b50f462343bbdd268ffba094`。MiMo `assets-integrate-r9-review-mimo-20260930-01` 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、42 turns、canary `mimo-2bcd968e` 匹配，报告已复制到 `docs/reviews/code-review-20260930-130612.md`，stderr 仅白名单行。ds-flash `assets-integrate-r9-review-dsflash-20260930-01` 同为 exit0/JSON success/completed、45 turns、canary `ds-flash-f157c3fb` 匹配，报告已复制到 `docs/reviews/code-review-20260930-130001.md`，stderr 仅白名单行。两路 output/stderr/canary 独立，绝对 cwd 分别为 `/private/tmp/dayu-upload-assets-review-r9-mimo-20260930` 与 `/private/tmp/dayu-upload-assets-review-r9-dsflash-20260930`。
- 总控实读两份完整 artifact，二者均给 `material finding 0`；I-R29 在 runner 装配边界只删未消费实参、形参及 Args 三行，`normalized.market` 路由、同一 validated handoff、SEC/CN 下游 ticker owner、filing 路径保持。I-R27/I-R28、I-R23～I-R26、I-R17/O11 无回退；O05/O16/material file-state 等独立 WU 继续 deferred；O34 合法公司事实独立持久化未被改写。r9 的 LSP 旧提示和 Open Questions 没有同源新增回归证据，按报告边界不扩大本轮修复。
- **资产 S1 本次待整合代码的 code review gate 通过**：r7 全链审查及 r8/r9 修后增量审查已由总控逐项裁决，I-R27～I-R29 和先前 in-scope accepted findings 有 owner 修复与回归；最终主树 17 文件矩阵 **1399 passed、1 skipped**，全量 pyright **0 errors、0 warnings**，diff check 无空白错误。该结论仅针对本资产整合切片与这些检查，不把尚未实施 WU 说成已完成，也不等同真实后端端到端验收。下一步在目标分支暂存、提交、推送，并读回 PR #197 head 与 `main`；用户自行 merge。
- 落地读回：上述资产代码、测试、历史裁决/审查档案已随 **233 文件**整合提交 `e215b446da89bccfea4856aceaa6dce807659b57` 普通推送至 `codex/upload-material-oracle`；远端 ref 与 PR #197 head 读回一致，`main` 未动。最终后补审计文档会在同一分支另行提交，其最终 PR head 以再次读回为准；未实施 O05/O16/file-state 等 WU 不因本次集成而宣称完成。
