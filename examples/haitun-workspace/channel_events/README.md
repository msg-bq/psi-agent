# channel_events — Channel 侧事件定义（agent 包）

> 有定事类用户需求时，**默认来这里按需注册事件**，≈ 加 tool；**不要**改 Channel 源码。

事件注册在 **agent 包**，由对应 Channel 进程加载并转发到 Session `POST /events`。
Session **不**维护业务事件 catalog。

## 布局

```text
channel_events/
  <channel>/                 # feishu | …
    <event_slug>/
      EVENT.yaml             # name / source / kind / platform_event? / description
      map.py                 # kind=platform_map：map_event(raw) -> list[envelope]
      produce.py             # kind=synthetic：async produce(ctx)；await ctx.emit(...)
      # kind=durable：只需 EVENT.yaml，由独立 eventd/event-consumer 投递
```

## 加事件 ≈ 加 tool（验收）

在 **Feishu Channel 已接线** 的前提下，按需新增目录 + **重启 Channel** 即可：

| kind | 生产者 | 你写 |
|------|--------|------|
| `platform_map` | 飞书官方推送 | `EVENT.yaml` + `map.py` |
| `synthetic` | 本目录 `produce.py`（Channel 统一 runner 拉起） | `EVENT.yaml` + `produce.py` |
| `durable` | 独立 Event Daemon + 租约 Consumer | `EVENT.yaml` + `cloudevent_type` |

示例：`feishu/member_added`（官方）、`feishu/demo_tick`（自定义模板，默认空转）。

`durable` 不会由 Channel 启动；它用于声明 eventd 已持久化并经 Consumer 投递的稳定
业务名，例如 `feishu.approval.status.changed`。不要把可靠守护进程写进 `produce.py`。

## 与 TRIGGER

- **channel_events**：什么信号能进总线（命名 + map/produce）
- **triggers/**：进总线后干什么（挂钩）

NL「有人进群提醒我」只写 TRIGGER，不 invent channel_events。
