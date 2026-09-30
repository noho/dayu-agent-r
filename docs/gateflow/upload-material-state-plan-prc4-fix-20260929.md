# UM-O14/O15 state plan PR-C4-F1/F2 修订记录

- RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
- CANARY=gpt-6-sol-6ecb257c
- 工作范围：仅修 `docs/gateflow/upload-material-state-plan-20260929.md`，新增本记录；本轮不实施 O12/state，不修改产品、测试、README、goal、既有 review/裁决，不推进 review/commit/PR。

## 预检与精确版本

| 证据 | SHA-256 / commit |
| --- | --- |
| O12 accepted checkpoint | `b201d9f3b1c84e49fe0751d75ea7dc31e2c0f14c` |
| checkpoint 中 `docs/gateflow/upload-material-o12-company-plan-20260929.md` | `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60` |
| state goal | `6c673a48e7ed194fc060cf8569acf62974d2960ed7f9c580869cbaba92eb2c91` |
| MiMo `docs/reviews/plan-review-20260929-164438.md` | `c195066975ff055f787e5067815fbf300264ac643ade2ab3e6ab29aedd3eacd9` |
| 总控 `docs/gateflow/upload-material-state-plan-review-adjudication-20260929.md` | `45c9f5fe1c6b74fb0ca7c0d63a39051bae6a97450d939af287a6e0e611473e9c` |
| state plan 修改前 | `f2496dd1da34f0556cff7e032b6f68ba7e7918b525c7b7aae5318b5ddc420cee` |
| state plan 修改后 | `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6` |

直接阅读 `AGENTS.md`、goal、MiMo review、总控裁决末节、state plan 及 `dayu/fins/ingestion_runtime.py`、`dayu/fins/upload_format_contract.py`、`dayu/fins/upload_failure.py`、`dayu/fins/tools/upload_tools.py`、`tests/fins/test_company_identity_storage_contract.py`。O12 checkout 尚为 accepted plan；这里引用 checkpoint 的 commit 内文件，不声称 O12 产品接口已集成。

## 修复映射

| 裁决 | 一手反例 | plan 修订 |
| --- | --- | --- |
| PR-C4-F1 | `FinsUploadUsageFailure.code` 接受普通 usage 与 format kind；`fins_upload_usage_failure` 只处理普通 code，`_raise_upload_format_usage` 直接另造 fact。format error 自有 kind、角色文案和 canonical `file_label`，现有 public reason 却在 `upload_failure.py` 另写通用文案/hint。 | §5 明列现状，不虚称 format 已走统一 producer。未来将 usage code/fact/error/唯一 producer/普通文案与 hint 一起移到 Fins 下层 contract，使 runtime 与 `upload_failure.py` 共用；format owner 提供角色 usage message、现有通用 public message、现有 hint、canonical label，producer 只装箱。fact 的 `hint: str` 对所有既有/新增 usage code 和全部三个 format kind 必填，1..240、无控制字符/路径分隔符；仅 format/target 的 `public_message` 受 public reason path-free 校验，避免把 filing 原有 `YYYY-MM-DD`、`create/update` 文案错拒。`upload_failure.py` 单点把三 target 映为同值 `USAGE` public code，把三 format kind 映为既有 `UNSUPPORTED_UPLOAD_FORMAT`，原样消费 fact 的 public message/hint/label。tool 只消费同一 fact 的 usage message/hint，协议仍是 `invalid_argument`；direct/可达 awaited 使用同一 public mapper；不造不可达 target job。S1 白名单及 owner/入口测试增加 format contract 与双文案、label、hint 的断言。 |
| PR-C4-F2 | `tests/fins/test_company_identity_storage_contract.py` 已断言 alias conflict→`ticker_alias_conflict`、corruption→`storage_io` 与 alias JSON 往返，但 S1/S2 和 focused 命令遗漏。 | 把该文件加入 S1/S2 测试白名单、两条 focused pytest 命令；增加 alias/identity 分类、`retry_hint`、`file_label`、strict JSON round-trip 及 alias 与漂移同轮优先级要求。O12 实际 API 迁移时将 owner 测试迁到最终 owner 边界，保留合同断言。 |

这里显式保留 format 的两种**现有**输出：filing usage 的角色文案与 Fins public reason 的通用文案来自同一 format 真源，但并不虚称两者逐字相同。tool 现有协议没有单独的 `file_label` 字段，不新增字段，也不在 tool 重新拼标签；public reason/direct/可达 awaited 保留独立 `file_label`。三个 target 的 `USAGE` 映射、filing create/update 原文案与 format 既有 public code 不变。

## 验证与残余

- 静态核对通过：O12 commit 内 plan SHA、修改前/后 state plan SHA、S1/S2 白名单、两条 focused 命令、format owner 测试路径、停止条件与 O12/O34/UM-A09/F8–F11 文字边界。未运行 pytest/pyright；本轮只改计划文档，没有产品或测试代码改动。未来 implementation gate 仍须先激活 `.venv` 并执行计划中的 focused pytest、pyright 与逐文件覆盖率核对。
- O12 accepted plan 尚未实施/集成；O14/O15 S1/S2 仍以实际同版状态、公司独立提交、材料 writer-owned guard、alias 优先和 active-only job 终态 API 核对为硬门槛。O34 合法公司事实、UM-A09 同指纹旧版本、F8–F11、损坏状态 fail closed 与 tool 协议均未回退。该修订只形成待独立同 SHA re-review 的候选，不代表 plan gate pass 或 implementation ready。
- 先前一次精确路径探测误把 state plan 路径放到 O12 checkpoint 的 `git show`，内部 Git 返回 128；未从该探测得出结论。随即改读 commit 内正确的 O12 company plan，返回 0 且 SHA 与锁定值一致。另一次重复应用已成功的文本替换时，断言找不到旧锚点，检查命令 exit 1；先前命令实际已写入，随后核读三个新锚点及 plan SHA 均正确，未重复改写。除这次重复替换外，外层检查命令均 exit 0；两项偏差在此披露。
