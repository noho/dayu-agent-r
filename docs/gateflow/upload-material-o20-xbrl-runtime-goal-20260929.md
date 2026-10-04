# UM-O20-F02：受控 XBRL Docling 转换能力 goal confirmation

- 日期：2026-09-29；worktree `/private/tmp/dayu-upload-o20-f02`，branch `codex/upload-material-o20-f02`，基线为 PR #197 已推送 head `9735800cb55a40336469593fa2fddae43c9c69ad`。
- 用户明确裁决：“按受控 XBRL 支持推进”；目标是补齐受控依赖与 taxonomy 配置，用有效 XBRL instance 验证真实上传。若最终直接证据定位为 Docling 上游缺陷，保留可复现失败证据并向上游提 issue。用户此前明确：这些候选格式上传都经 Docling；内容抽取准确率属于 Docling 上游，不是 Dayu 自行纠错职责。
- 当前 Gateflow：**goal confirmation pass**；下一 entry 为 gpt-6-sol plan、Kimi/MiMo 同版 plan review。独立 evidence `docs/gateflow/upload-material-o20-e01-evidence-20260929.md` 是直接观察，不替代产品实现或有效 XBRL 成功。

## 动机与唯一 owner

动机成立且为真实部署能力缺口。`dayu/documents/docling_runtime.py:222-234` 的唯一 Docling capability 将 `.xml/.xbrl` 列为 `XML_XBRL` 候选；`pyproject.toml` 标准依赖有 Docling 但无其 XBRL 可选依赖。E01 对完整 AAPL XBRL instance 的真实 CLI 上传返回 typed `content/docling_converter_execution`、`stored_files=0`，无 material manifest；同环境直接第三方调用证明首个具体异常是缺 `arelle`。隔离安装 `arelle-release 2.44.8` 后，又证明默认 taxonomy local/remote fetch 均关闭；仅启 local fetch 时 AAPL fixture 仍在 Docling 的 `memberQname=None` 处失败，尚不能判定是远程 taxonomy 缺失还是上游后端缺陷。`DocumentStream` 无 sibling taxonomy 时可返回仅标题的 Docling SUCCESS；该事实不能被误写为财报事实抽取准确。

语义 owner：Docling runtime 装配和产品 capability 声明负责“可部署的转换候选能力”；包声明与锁定环境负责可安装依赖；Fins 文件准入与上传仅消费 capability/Docling conversion outcome，材料成功由权威 manifest 与材料提交结果定义。taxonomy 访问策略及源文件引用隔离由 Docling runtime 的直接上游输入/运行边界负责；不能在 CLI/tool/manifest 下游补特殊解析、字符串探测或伪成功。

## 已确认目标与成功信号

1. 选定可在 Python 3.11/项目支持平台解析并锁定的 Arelle/Docling XBRL 依赖组合，标准安装或明确产品支持的安装路径必须与公开 `XML_XBRL` 候选声明一致；不留下“默认宣称支持、实际稳定缺包”的部署态。
2. 给 XBRL conversion 配置受控 taxonomy 输入：默认不作不受控远程获取；若需要本地 taxonomy，必须明确可信输入位置、引用解析和文件系统边界，实测 XML 中的绝对 `file:`、路径穿越、远程 URL 等引用不能越过所承诺边界。不得只靠 `enable_remote_fetch=False`/Docling 临时目录推断本地安全。若经证据证明合理实现必须使用远程 taxonomy，须在 plan 中定义显式许可、域/缓存/超时/离线行为与安全边界，再由双路 plan review 裁决；不默默打开任意网络。
3. 完整、有效、具备所需 taxonomy 的 XBRL instance 真实 `dayu-cli upload_material` 从 Docling 转换成功并正常提交，读回原件、Docling 派生文件、source meta 与权威 material manifest 条目；失败时仍为 typed content failure、`stored_files=0` 且无本请求 material manifest 成功。CLI/tool 公开文案沿 O20-F01 唯一投影，同一 capability/部署事实，不把普通 XML、独立 linkbase 误承诺为可转换 instance。
4. E01 形成独立、可审计正负样本：输入来源/hash、相对 taxonomy 配套、依赖/配置快照、真实 argv、stdout/stderr/exit、文件系统与 manifest/durable 读回、证据 digest；冻结旧观察保持不变。Docling JSON 已验证成功，不因本项回退；普通 JSON/XML/linkbase 负样本保持内容不匹配处理。
5. 若受控完整 taxonomy 下有效 instance 的可复现失败定位为 Docling/Arelle 上游，保留最小复现及版本/日志、按用户授权向对应上游提 issue，并在本 work unit 明确可部署能力与公开声明的最终处理，不能把上游问题伪装成 Dayu 本地内容修复。抽取结果是否财务准确不设 Dayu 成功门槛；有可复现不准确则交上游 issue。

## 非目标与停止条件

- 不编写第二套 XBRL parser、财报事实修正器或从 Docling Markdown/JSON 内容猜转换正确性；不改变 O20-F01 文案已闭环的范围，不扩大普通 JSON/XML 或 linkbase 格式支持。
- 不用 `--no-deps` 的不完整临时叠层冒充生产部署；不凭单个 `ConversionStatus.SUCCESS` 或空标题文档称财报内容抽取准确。也不把缺包/不可取 taxonomy 的真实原因改写成“文件损坏”。
- 若 taxonomy 引用隔离无法证明、需要不受控本地/远程读取、受控安装无法解析或有效正样本仍失败且根因未定，停止实施成功声明，保留证据并回 Gateflow plan/fix/re-review；不能以关闭测试、静默移除 capability、放松安全边界或 fake/mock 代替真实 CLI 成功。
- 涉及 `dayu/documents`、`dayu/fins`、依赖/锁文件、README/测试时按 AGENTS.md 的 owner、中文 docstring、受影响测试、逐生产文件覆盖率目标、pyright 和 README 触发逐项验证。闭环代码入 PR #197，PR 保持 draft，用户手工 merge。
