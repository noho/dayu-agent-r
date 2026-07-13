# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Slice S1 Implementation（AgentCodex）

## Scope

本 artifact 只记录 R3-E Slice S1「Web egress 与 response ownership」实现。实现闭合：

`WebEgressPolicy -> AuthorizedHttpTarget -> target-bound requests/urllib3 transport -> AuthorizedResponseLease -> Playwright safe-profile gate -> diagnostic raw-path wiring`

未进入 S2/S3/S4；未实现 WebResourceBudget、codec/DOM cap、challenge/DDG parser、diagnostic schema/storage-state lifecycle/smoke oracle、Documents bounded source，也未修改 Fins、Host、Engine lifecycle、tool-security framework 或 upload/download schema。

## Changed files

- `dayu/tools/web/web_egress_policy.py`（新增）
- `dayu/tools/web/web_http_session.py`
- `dayu/tools/web/web_fetch_orchestrator.py`
- `dayu/tools/web/web_playwright_backend.py`
- `dayu/tools/web/web_tools.py`
- `utils/diagnose_web_access.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/tools/web/test_diagnose_web_access.py`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-implementation-codex.md`（本 artifact，新增）

没有修改 provider config、生产/测试 README、Host、Engine、Documents 或 Fins 文件。

## Semantic owners

1. `WebEgressPolicy` 是 URL 语法、userinfo/port、DNS 结果集合、private/link-local/metadata/benchmark/mapped address 与 local/dev profile 的唯一 owner；每个 HTTP hop 只产生一个不可变 `AuthorizedHttpTarget`。
2. `web_http_session.py` 是 authorized target 到 socket destination 的 transport owner。它不重新判断业务 URL，而只消费 target 中的 IDNA hostname、port 与 immutable approved numeric set。
3. `_request_with_safe_redirects` 是 redirect 重新授权与 response lease transfer owner；每个 Location 都先产生新 target，不能沿用旧 hop 的授权。
4. `AuthorizedResponseLease` 是 response 与该 hop 私有 adapter/pool 的唯一 lifetime owner；callee 未 transfer 或 caller 消费完成后均由 lease 幂等关闭。
5. `web_playwright_backend.py` 是 browser safe-profile gate owner：公网 direct 无法证明实际 peer，返回 `browser_egress_policy_unavailable`；只有显式 `allow_private_network_url=True` 的 local/dev profile 才允许 direct browser，并继续用同一 policy 裁决导航与 subrequest。
6. `utils/diagnose_web_access.py` 只选择并复用同一个 policy profile；raw requests 使用生产 redirect/lease owner，已删除自建 `_validate_url_safety` / literal-host predicate。

## Implementation decisions

- 目标依赖扩展点按 `requests==2.33.1` / `urllib3==2.6.3` 实现并由测试锁定。
- 每 hop 创建私有 `_TargetBoundHTTPAdapter` 与私有 pool；没有在共享 ambient session 上临时 mount target adapter。source session 仅提供 retry/cookie/header/TLS 配置。
- 自定义 `HTTPConnection` / `HTTPSConnection` 只 override `_new_conn()`：按确定顺序连接 target 的 numeric addresses，并在 socket 返回给 HTTP/TLS 层前调用 `getpeername()` 验证 peer。
- pool 的 `host` 始终保持原 IDNA hostname。因此 HTTP `Host`、TLS SNI 和 certificate hostname verification 保持原 host；仅 TCP destination 使用 numeric address。
- `trust_env=False`、显式空 proxy，target-bound adapter 拒绝 proxy；没有 global DNS monkeypatch、thread-local/contextvar target、broad proxy framework 或 lazy import seam。
- urllib3 connect/read/status retry 复用同一个 adapter/pool 和 immutable target；connect retry 与 retry exhaustion 测试证明所有 `_new_conn()` 尝试只看到同一 approved address，且不会 fallback 到 hostname DNS。
- response URL 只允许与当前 target 同 origin，且校验不重新解析 DNS；redirect Location 则创建新的 authorized target。
- warmup、HEAD/GET probe、main fetch、redirect reject、response URL reject、Location reject、too-many-redirects 与 request 后取消均改为 lease context。`_FetchContentResult` 不再携带 live `requests.Response`，challenge consumer 改为消费已复制的 status/header/content facts。
- diagnostic raw requests 不再使用 `allow_redirects=True`，而是复用 production `_request_with_safe_redirects` 与 response lease。

## Tests / pyright / diff-check

实现期额外运行两个受影响测试文件全量回归：

```text
pytest tests/tools/web/test_web_tools_provider.py tests/tools/web/test_diagnose_web_access.py -q
87 passed, 1 skipped
```

指定 S1 验证：

```text
pytest tests/tools/web/test_web_tools_provider.py -q -k 'url or egress or redirect or response or peer or playwright'
38 passed, 1 skipped, 27 deselected

pytest tests/tools/web/test_diagnose_web_access.py -q -k 'url or egress or redirect'
5 passed, 17 deselected

pyright
0 errors
```

覆盖重点：

- unsafe URL/address matrix、mixed public/private A/AAAA、userinfo、custom port、metadata、`198.18/15`、IPv4-mapped IPv6；
- 真实 target-bound HTTP loopback integration；
- 本地 CA HTTPS integration，断言 numeric destination、原 `Host`、`pinned.test` SNI 与证书 hostname；
- HTTPS/HTTP 首次 connect 失败后 retry 固定地址，以及所有地址失败后的 retry exhaustion/no fallback DNS；
- peer mismatch 在 socket 交给 HTTP 层前关闭；
- final response transfer、request 后 cancel、response URL reject、Location reject、next-hop reject、too many redirects 与 HEAD success 的 exactly-once close；
- public Playwright typed unavailable 与 private subrequest fail-closed；
- diagnostic raw path 的 shared-policy rejection 与 public browser typed unavailable。

最终 whitespace/scope 验证：

```text
git diff --check
exit 0，无输出

git diff --no-index --check /dev/null dayu/tools/web/web_egress_policy.py
无 whitespace diagnostics（no-index 因存在预期差异返回 1）

git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-implementation-codex.md
无 whitespace diagnostics（no-index 因存在预期差异返回 1）

git status --short
仅 7 个允许修改的 tracked S1 文件，以及新增 web_egress_policy.py / 本 artifact；没有 production/test README、S2/S3/S4、Host、Engine、Documents 或 Fins 文件。
```

## README trigger decision

- 根 README：S1 不改变安装、CLI 正式入口、最终用户工作流或日志位置，不触发。
- `dayu/README.md`：S1 不改变 `UI -> Service -> Host -> Engine` 或包依赖方向，不触发。
- provider config：没有新增字段，不触发 `dayu/config/README.md`。
- `tests/README.md`：已读取其 Web tests 边界；plan §10 明确要求 S1-S4 行为全部 accepted 后再更新 Web/Documents 测试分层。本 gate 不提前写流水账，因此 S1 不修改，留到 aggregate accepted 后处理。

## Propagation audit

执行了以下 source audit：

```text
rg -n "_is_safe_public_url|_validate_url_safety|_is_private_or_local_host|socket\.getaddrinfo|allow_redirects=True|session\.(get|post|head|request|send)\(|requests\.(get|post|head|request)\(" dayu/tools/web utils/diagnose_web_access.py
rg -n "response\.close\(|_close_response_safely|AuthorizedResponseLease|_request_with_safe_redirects" dayu/tools/web utils/diagnose_web_access.py
rg -n "page\.goto\(|route\.continue_|browser_egress_policy_unavailable|allows_private_network" dayu/tools/web/web_playwright_backend.py utils/diagnose_web_access.py
```

结论：

- production fetch 与 diagnostic 中没有第二套 URL safety predicate；唯一 DNS 决策位于 `WebEgressPolicy`。search result filter 的布尔 helper 只直接投影该 owner，不重写规则。
- fetch/warmup/probe/diagnostic raw path 没有直接 `allow_redirects=True`、裸 `session.send/request` 或 response close 分支；所有 live response 均进入 `AuthorizedResponseLease`。
- `web_search_providers.py` 仍有三个固定 provider endpoint 的 `requests.get/post`。该文件由 S2 的 search resource/parser slice 修改，本 S1 handoff 明确禁止进入 DDG/S2；这些调用不是用户 URL safety predicate，且当前均为 `stream=False`，response body 在返回前 materialize 并释放 pool connection，不构成 S1 fetch lease 漏洞。S2 review 仍须按其 resource/parser owner 重新审计。
- Playwright 的 `page.goto` / `route.continue_` 命中只存在于 `allows_private_network=True` gate 之后；公网 direct 在 import/worker/browser 启动前 typed fail closed。

## Residual risks

1. transport 依赖 requests/urllib3 私有/半公共扩展点形状；依赖升级必须由 Web transport owner 重跑 HTTP/HTTPS/retry/peer integration matrix。
2. 公网 Playwright direct 现在明确不可用，client-rendered 公网站点可用性会下降。可信 browser egress proxy/network sandbox 归后续 deployment/browser WU，不能恢复成字符串 URL 检查。
3. 显式 local/dev Playwright profile 允许浏览器自己连接，不能外推为公网 peer proof；它只服务人工/local fixture 场景。
4. S2-owned search provider 固定 endpoint、resource budget 与 DuckDuckGo parser 尚未修改；本 artifact 不把它们声明为已完成。
5. response/pool close 异常按 contract 被吞掉，避免覆盖原业务异常；若需要 close failure telemetry，应由后续 diagnostic owner增加不可逆计数，不改变 lease 所有权。

## Stop status

S1 implementation 已完成，未触发 stop condition：当前实现能在发送 HTTP request bytes 前证明 peer 属于 authorized set，且不需要 global DNS monkeypatch、broad proxy framework 或 lazy import seam；response negative matrix 的 close owner 已确定。

本 Agent 在此停止于 S1 implementation artifact，等待 Slice S1 implementation review；不进入 S2/S3/S4，不 stage/commit/push。

Blocking questions：无。
