# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Second Stop Scope（Codex）

## 结论

当前 implementation 已在 S3 focused gate 上通过，但 `tests/host/test_watch_session_events.py` 里又出现了一个新的、真实的 S3 contract migration 停止点。它不属于已接受的 S3 Allowed tests，因此这里必须停下，不能继续改实现文件，也不能继续修这个 test。

## 触发的 failing assertion

失败来自 `tests/host/test_watch_session_events.py` 的 dual-opener barrier case：

```text
assert local_hook_calls.call_count == 0
```

在当前行为下，这个断言不成立，因为 A opener 的本地 terminal hook 可以前进一次，而 C opener 仍应保持不变。也就是说，真正要证明的是 C-side / no-cross-opener barrier，而不是“全局总计数必须为 0”。

## 为什么这是一个真实的 S3 contract migration

这个 case 不是普通的测试噪声，而是 S3 的 owner 语义迁移点：

- A 的 local terminal hook 前进是允许的。
- C 侧必须保持不变，不能因为 A 的终态而发生 cross-opener wake。
- 当前 test 用的是全局计数器，所以它把 A 的合法本地动作和 C 的 barrier 验证混在一起了。

因此，正确的 owner 不是 production fallback，而是这个 test 里要切换成 C-side 的观测方式，或者把 barrier instrumentation 挪成 opener-local 的断言。这个变化需要另一个最小 plan amendment，而不是继续在当前 accepted/amended S3 Allowed tests 外直接动代码。

## 最小授权建议

如果要继续，最小授权应该只覆盖：

- `tests/host/test_watch_session_events.py`

授权内容只限于把这条 barrier 从“全局 hook 计数”改成“C opener 局部 hook / no-cross-opener wake 观测”，并保持 A 侧本地 hook 允许前进、C 侧不变的语义。

不应授权：

- 任何 production 文件改动。
- 任何额外 test / control / review 文件改动。
- 任何 fallback、默认值、兼容分支或新的跨 opener 补偿逻辑。

## 最小验证建议

若后续获得新的最小 plan amendment，验证只应包括：

1. `tests/host/test_watch_session_events.py` 中这条 dual-opener barrier case。
2. `pytest tests/host -q` 的相关 affected subset，确认没有引入新的 cross-opener regression。
3. `pyright` 与 `git diff --check`。

## 是否已知第三个新的 scope file

当前没有已知的第三个新 scope file。

已知的新 stop 目标只有：

- `tests/host/test_watch_session_events.py`

STOP_CONDITION
