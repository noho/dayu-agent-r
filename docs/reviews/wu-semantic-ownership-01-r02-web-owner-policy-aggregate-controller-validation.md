# WU-SEMANTIC-OWNERSHIP-01 / R02 aggregate Controller validation

## 1. Gate 结论

- aggregate validation artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-validation.md`
- accepted plan：`2d42ceb6`
- accepted slices：S1=`c7b01d82`、S2=`d8d6e9d9`、S3=`7e679796`
- validation HEAD：`4240ee75`
- Controller verdict：`PASS`，允许进入 AgentMiMo / AgentDS 双路 aggregate deepreview。

该结论只接受组合验证证据，不等于 R02 accepted，不关闭 umbrella WU，不创建 completion，不授权 R03、Issue 178 replacement lifecycle、proxy credential schema或统一 tool authorization framework。

## 2. 第一性原理与 owner 复核

R02 的三个 slice 分别改变 config/budget owner、HTTP/browser transport consumer和 diagnostic lifecycle utility；单 slice PASS 不能证明同一 accepted tree 上仍只有一个 raw parser/default source、三个 child budget没有交叉复用、transport/browser和diagnostic utility没有各自恢复默认，也不能证明保留的安全策略与真实财报体量能够组合工作。因此 aggregate gate 的动机真实成立。

Controller 检查 `7e679796..4240ee75`，确认只存在 control gate transition，产品、测试、utility、config和 README 零 diff。AgentCodex 本 gate 唯一 authored path 是 aggregate validation artifact，没有修改受测 target。

## 3. Controller 独立执行

### 3.1 Aggregate tests 与类型检查

Controller 独立执行：

```text
pytest tests/tools/web/test_web_tools_provider.py \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_config_loader.py -q
=> 310 passed, 1 skipped, 3 warnings

python -m pyright
=> 0 errors, 0 warnings, 0 informations

git diff --check
=> PASS
```

唯一 skip 是既有 opt-in live browser cleanup smoke；aggregate 的本地真实 Playwright gate 没有 skip。三条 warning 均来自 `edgar` 依赖弃用提示。

### 3.2 独立 deterministic / real Playwright smoke

Controller 使用新的独立目录执行：

```text
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-controller-aggregate \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-controller-aggregate
=> exit 0
```

直接结果为 `status=passed`、11 local passed、0 failure、0 skip、0 external fetch。关键 artifacts：

- filing HTTP：v2/revision2、HTTP 200、completed、`1,503,780 B`。
- filing Playwright：v2/revision2、completed、`browser_executed=true`、origin body `1,503,780 B`、DOM `1,515,212 chars`、text `209,272 chars`、6 events、显式 input used。
- private deny：private=false/custom=true，expected/observed=`permission_denied`。
- custom-port deny：private=true/custom=false，expected/observed=`permission_denied`。

上述真实 metrics 均低于 128/256 MiB、16/8 Mi chars、512 events等冻结 ceiling，没有 ceiling-induced business failure，不触发 stop rule。search provider 的测试 DNS/API key结果只作为 diagnostic-only，未替代 local gate。

### 3.3 Coverage、source 与 scope

Controller 独立读取 aggregate coverage JSON，确认 `2d42ceb6..7e679796` 的 11 个 changed production Python 文件均存在结果且 `>=80%`；范围为 `80.0561797752809%` 至 `100%`，两份 `utils` 也分别大于 81%。

精确 source scans 再确认：

- `WebResourceBudget`、storage output/TTL/lifecycle/owner filename：零命中。
- utility-local `_DEFAULT_DIAGNOSTIC_ERROR_CHARS|1_024|default=80`：零命中。
- aggregate artifact 报告的 target-specific transport signature audit 为 `2 issues=0`，accepted-contract docstring audit为 aggregate `236 issues=0`、S2 `99 issues=0`、S3 signature subset `36 issues=0`。
- allowed-file exact set为 18 actual / 0 extras；根/分层 README、challenge/recovery/projection、batch和 deferred scope路径零越界。

`web_tools.py` 与 `web_playwright_backend.py` 接近但仍高于 80%，属于 aggregate deepreview 复核触发，不是当前 threshold failure。

## 4. Validation harness 失误裁决

AgentCodex 如实记录了三次只读 harness invocation 问题：

1. coverage 辅助循环把 zsh 特殊变量 `path` 当循环变量，覆盖 `PATH`，在实际 coverage 命令前 exit 127；corrected loop 的 11 个 `--fail-under=80` 全部 exit 0。
2. docstring audit 首版对 AST list 调用 `ast.dump`，在判定前 TypeError；无 source pass/fail结果。
3. 第二版把仓库接受的 Sphinx docstring 误限定为 Google sections，并把普通 test fake class 套用 S2 强化 class contract，产生 38 个假阳性；按 accepted plan/Controller 口径重跑后 aggregate/S2/S3 issues均为0。

这些是验证器调用/口径错误，不是产品、测试或 docstring defect；AgentCodex 没有通过改代码消除结果。Controller 接受 corrected canonical runs，同时要求 aggregate deepreview 挑战 audit口径与 qualified-name completeness。

## 5. Security 与 deferred scope

组合证据保留：DNS/dangerous/mixed addresses、redirect recheck、numeric peer proof、proxy selected-state conflict、HTTP/browser/diagnostic budgets、browser route/capability、challenge、redaction、containment/symlink和ordinary writer边界。credential/lifecycle artifact scans零非法命中。

没有实现统一 authorization；没有删除现有 defensive controls；没有进入 Issue 178 replacement lifecycle、R03 LLM-facing projection或proxy credential schema。

## 6. Residual destinations 与下一入口

- replacement credential lifecycle：Issue 178。
- future live-site size variability：Web config owner；只有直接 ceiling failure才另立 config change。
- proxy/browser peer-proof limitations：既有 typed fail-closed transport/browser owner。
- external provider variability：Web diagnostics/smoke owner；local hard gate为真源。
- two near-threshold coverage files：aggregate deepreview verification trigger；未来触及者重跑逐文件 gate。
- accepted-result / LLM projection：R03，当前未授权。
- unified authorization：Topic 9 no-code decision。

下一入口是双路 aggregate deepreview。reviewer 必须覆盖 S1-S3 组合行为、完整 accepted diff、aggregate验证真源、harness归因、retained security和 residual destination；任一 finding 必须由 Controller逐项裁决。
