# TODO-0001 — Market Status / Halt / LULD Awareness

> 状态：Open
>
> 优先级：P2
>
> 关联文档：
> - `docs/backend-evolution/BE-0003-bars-query-materialization.md`
> - `docs/prd/PRD-0001-market-watch.md`

## 1. 概览

当前 bars MVP 只覆盖：

- `1m/1d` canonical storage
- query-time aggregation
- trading calendar + `pre_market / regular / after_hours`
- mutable tail / gap repair

本期 **不处理** 市场状态事件驱动的图表语义，例如：

- Trading Halt
- Resume
- Volatility Trading Pause
- LULD 状态变化
- Market-Wide Circuit Breaker

这些能力在产品级行情应用中通常会影响：

- 图表上的状态提示
- fill / gap 的解释语义
- refresh 策略
- 用户通知与告警

因此单独记录为后续待办。

## 2. 为什么需要这个待办

当前实现默认把 bars 问题分成两类：

```text
calendar / session truth
  -> regular / pre_market / after_hours

provider sparse / mutable tail
  -> gap repair
  -> carry-forward fill
```

但如果发生下列事件：

- 单股停牌
- LULD pause
- 熔断后恢复交易
- 市场级 circuit breaker

则“某段时间没有 bar”未必代表：

- 没有成交

也可能代表：

- 市场中断
- 交易暂停
- 交易受限

如果系统不知道这些状态，就可能：

- 把中断时段误判为普通 sparse interval
- 错误应用 carry-forward fill
- 错误触发 gap repair
- 前端无法解释为什么图表突然不动

## 3. 当前对 Massive 能力的结论

当前已确认 Massive 具备以下相关能力：

- REST / docs 层面可提供 market hours 与 market holidays
- WebSocket 可提供与市场状态相关的实时事件流
- stocks trades 流包含 `conditions`
- 官方资料包含与以下状态相关的条件或事件语义：
  - `Trading Halt`
  - `Resume`
  - `Volatility Trading Pause`
  - `LULD`
  - `Market-Wide Circuit Breaker`

当前未把 Massive 当作“完整 interruption calendar”的原因：

- 它更偏实时事件流与 condition 信号
- 不是本项目当前 session truth 的主来源
- `regular open/close + trading day` 仍应以交易所日历为准

当前推荐边界：

```text
exchange_calendars
  -> trading day / regular session truth

our product logic
  -> pre_market / after_hours

Massive realtime events
  -> halt / resume / LULD / market status awareness
```

## 4. 未来实现目标

后续若进入 product-level 行情能力，建议补上以下链路：

```text
Massive WebSocket
  -> backend market-status consumer
  -> normalize halt / resume / LULD event
  -> persist latest status or publish internal event
  -> frontend websocket / sse
  -> chart badge / banner / tooltip / notification
```

建议至少支持：

- 当前 ticker 是否处于 halt / pause 状态
- 最近一次状态变化时间
- resume 状态
- market-wide circuit breaker 的全局提示

## 5. 对 bars 系统的预期影响

后续落这项能力时，需要重新检查 [BE-0003-bars-query-materialization.md](/Users/mz/pmf/trader-refactor/docs/backend-evolution/BE-0003-bars-query-materialization.md) 中以下规则：

- `gap` 的定义
- `carry-forward fill` 的适用边界
- mutable tail refresh 策略
- 前端 `partial_range` / `is_synthetic` 的解释文案
- regular / pre_market / after_hours 图表在 halt 期间的展示语义

建议新增明确规则：

- halt / pause 时段是否禁止 synthetic fill
- halt / pause 时段是否仍允许 request-time repair
- 图表是否显示专用 market-status overlay

## 6. 触发时机

以下任一条件满足时，应把本待办提升为正式实现项：

- 前端开始接入 WebSocket / SSE 实时行情
- 需要在图表上展示停牌 / 熔断状态
- 需要向用户主动发送市场状态通知
- 需要区分“无成交”与“暂停交易”
- 后续扩展到更多存在午休或中断语义的市场

## 7. 下一步建议

P0 当前不做实现，只保留文档结论。

P1 当进入实时推送阶段时，新增一份 backend evolution 文档，单独设计：

- market status event ingestion
- state normalization
- persistence / cache
- frontend push contract
- bars 与 market status 的协同语义
