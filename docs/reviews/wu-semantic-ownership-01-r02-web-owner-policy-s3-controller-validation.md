# WU-SEMANTIC-OWNERSHIP-01 / R02-S3 Controller validation

## 1. Gate 结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- remediation sub-WU / slice：`R02 / S3`
- accepted S2 commit：`d8d6e9d9`
- implementation transition / diff base：`08c2380a`
- implementation artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s3-implementation-codex.md`
- Controller 结论：`PASS`，允许进入 AgentMiMo / AgentDS 双路完整 code review。

该结论只确认 R02-S3 implementation 达到 review 入口。它不接受代码、不关闭 R02 或 umbrella WU，也不授权 Issue 178 replacement lifecycle、R03、proxy credential schema 或统一 tool authorization framework。

## 2. 动机与 owner boundary 复核

当前代码证据与 controller discussion 的产品裁决一致：待删语义的 owner 是 diagnostic utility 内的 storage-state output / TTL / publish / reconcile / cleanup lifecycle；Web raw config 的解析、默认值和 typed resource budget 仍由 `dayu.tools.web.provider._parse_config` 及其 immutable config 类型拥有。修复发生在 owner boundary，没有把 lifecycle 搬到 writer、smoke fixture 或下游 adapter。

Controller 对 `08c2380a..worktree` 的 exact diff 复核确认：

- tracked code/doc changes仅为 `utils/diagnose_web_access.py`、`utils/smoke_web_ci.py`、两份对应测试和 `tests/README.md`；另有本 slice implementation artifact。
- `dayu/tools/web/web_diagnostics.py`、`dayu/tools/web/web_challenge_detection.py`、`utils/diag_web_batch.sh`、`dayu/config/README.md`、根 `README.md` 与 control doc 在 implementation validation 前均为零 diff。
- diagnostic utility 删除 output、TTL、owner filename、permission、publish、reconcile、failure/cancel cleanup 和旧 private-network CLI；没有 replacement lifecycle producer。
- 显式 `--storage-state-in` 只作为经过常规文件、UTF-8、JSON object 校验的 read input；`--storage-state-dir` 仍只进入既有 production provider resolver。artifact 只投影 `storage_state.input_used` 输入事实。
- `_provider_config` 的 raw mapping 只经一次 `_parse_config` 形成 typed snapshot；private/custom-port、browser capability、transport policy、diagnostic `error_chars/events` 均从该 snapshot 分发。`--max-network` 缺省为 `None`，显式 override 继续经过 `DiagnosticResourceBudget` 正整数校验。
- ordinary JSON / JSONL / summary writers 没有获得 credential lifecycle 语义。

## 3. 独立验证

### 3.1 Tests、coverage 与类型检查

Controller 独立执行：

```text
pytest tests/tools/web/test_web_tools_provider.py \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_config_loader.py -q
=> 310 passed, 1 skipped, 3 warnings

coverage run ... <三份 S3 tests>
=> 258 passed, 1 skipped, 3 warnings

utils/diagnose_web_access.py => 81.28523111612176%
utils/smoke_web_ci.py        => 81.32911392405063%

python -m pyright
=> 0 errors, 0 warnings, 0 informations

git diff --check
=> PASS
```

唯一 skip 是既有 opt-in live browser cleanup smoke；本 slice 的 deterministic local Playwright hard gate 未跳过。

### 3.2 Controller real smoke

Controller 使用独立输出目录执行：

```text
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-controller-s3 \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-controller-s3
=> exit 0
```

`summary.json` 为 `status=passed`、`exit_code=0`、11 local passed、0 failure、0 skip。关键直接证据：

- 版本化 filing HTTP：source/wire/decoded 均为 `1,503,780` bytes，completed。
- 版本化 filing Playwright：origin body `1,503,780` bytes、rendered DOM `1,515,212` chars、rendered text `209,272` chars、6 network events、`browser_executed=true`、`storage_state.input_used=true`。
- private deny overlay：`allow_private_network_url=false` 且 custom-port=true，经正式 assembly/callable 得到 `permission_denied`。
- custom-port deny overlay：`allow_custom_port_url=false` 且 private=true，经正式 assembly/callable 得到 `permission_denied`。
- filing HTTP / Playwright artifacts 的 credential 与 lifecycle field 精确扫描零命中；utility/smoke/batch 对 `--allow-private-network-url`、`--storage-state-out`、`--storage-state-ttl` 扫描零命中。

## 4. Security、deferred scope 与文档判定

- 保留 DNS / redirect recheck / peer proof / proxy conflict / HTTP-browser-diagnostics budgets / browser route / challenge detection / redaction / filesystem containment / symlink 等既有安全 owner；本 slice 没有删除生产 provider 防御路径。
- private 与 custom-port 默认 allow 的产品裁决仍由 `tool_discovery.json` typed config owner表达，两个显式 deny可独立工作；`browser_enabled` 没有重新与 private permission 耦合。
- 未实现统一 tool authorization framework，也未添加 permission schema、policy DSL、role/capability 或 sandbox。
- 未实现 Issue 178 replacement lifecycle；run-local 空 JSON 仅是 deterministic smoke 的显式 read-input fixture，不是 browser 生成、持久化、刷新、TTL、publish 或 cleanup authority。
- `tests/README.md` 的更新属于测试职责范围。`dayu/config/README.md` 已描述当前 config owner且 schema/default 未变；根 README 没有对应最终用户入口/工作流变化，因此两者不更新。

## 5. Residual risks 与下一入口

- 真实 external provider/browser credential lifecycle 仍归 Issue 178；R02-S3 不持有该语义。
- 既有 opt-in live browser cleanup smoke 需要环境变量才运行，但本 slice 已用本地真实 Playwright hard gate覆盖浏览器执行、输入读取、财报体量和 artifact contract。
- search provider diagnostic-only warnings来自保留的外部条件（测试 DNS / API key），不影响零 external fetch 的 deterministic local hard gate。

下一入口是双路完整 code review。所有 reviewer findings 必须由 Controller 裁决；accepted findings 必须由 AgentCodex 修复并经双路 re-review 后，才允许 accepted local commit。
