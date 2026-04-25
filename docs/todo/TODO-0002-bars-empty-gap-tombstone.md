# TODO-0002 - Bars Empty-Gap Tombstone

> 状态：Open
>
> 优先级：P2
>
> 关联文档：
> - `docs/backend-evolution/BE-0003-bars-query-materialization.md`
> - `docs/prd/PRD-0001-market-watch.md`

## 1. 概览

当前 `historical-bars-gap-reconciliation` 已改为按 DB gap 拉取缺失数据，并增加了每 ticker 每轮 provider call 上限。

但 Massive aggregate bars 对 sparse intervals 的语义是：

```text
no eligible trades during an aggregate period
  -> no aggregate bar is generated
```

因此 DB 中缺少某个 regular minute bucket 不一定代表数据缺失，也可能只是该 ticker 在这一分钟没有 eligible trade。

## 2. 为什么需要这个待办

当前 gap repair 的核心判断仍是：

```text
calendar expected regular minute
  -> DB missing bucket
  -> fetch provider
```

对于高流动性 ticker，这通常可行；对于低流动性 ticker，可能出现：

```text
minute has no eligible trade
  -> Massive returns empty result
  -> DB remains missing
  -> next daily reconciliation sees the same gap again
  -> repeated provider calls forever
```

当前 provider call cap 可以防止单轮任务失控，但不能从语义上记住“这个 gap 已经向 provider 验证过为空”。

## 3. 未来实现目标

建议引入 empty-gap tombstone 或 reconciliation checkpoint，用来记录 provider 已确认为空的 gap range。

候选模型：

```text
bars_gap_reconciliation_checks
  ticker
  adjustment
  granularity
  session_kind
  range_start_at / range_end_at
  provider
  checked_at
  result = empty | partial | filled
  expires_at
```

对 `1d` 可使用：

```text
range_start_day / range_end_day
```

也可以先只支持 `1m regular`，因为 sparse minute bars 是主要问题。

## 4. 预期行为

后续 reconciliation 流程应变为：

```text
find DB gaps
  -> subtract unexpired empty-gap tombstones
  -> cap provider calls per ticker
  -> fetch provider
  -> upsert returned bars
  -> record empty tombstone for ranges with no returned bars
```

建议 tombstone 设置 TTL，避免 provider 后续修正历史数据时我们永久跳过。

初始 TTL 可考虑：

- mutable tail 内：短 TTL，例如 1-3 天
- 超出 mutable tail 后：较长 TTL，例如 14-30 天

## 5. 触发时机

以下任一条件满足时，应提升为正式实现项：

- watchlist ticker 数量明显增加
- 用户开始添加低流动性 ticker
- nightly reconciliation 的 provider call 数量持续偏高
- 日志中频繁出现 provider call budget reached
- Massive quota / latency 成为实际瓶颈

## 6. 下一步建议

当前不做实现，只保留 provider call cap 作为保护。

后续实现时建议补齐：

- DB migration
- repository methods
- reconciliation service tombstone filtering
- empty response recording
- TTL 策略测试
- sparse ticker 单测
