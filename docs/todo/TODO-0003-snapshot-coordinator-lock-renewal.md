# TODO-0003 - Snapshot Coordinator Lock Renewal

> 状态：Open
>
> 优先级：P2
>
> 关联文档：
> - `docs/backend-evolution/BE-0002-snapshots-fanout.md`
> - `docs/prd/PRD-0001-market-watch.md`

## 1. 概览

当前 `snapshot-coordinator-refresh` 使用 Redis single-flight lock 防止多个 worker 同时刷新 watchlist snapshots。

现状是：

```text
task start
  -> acquire Redis lock with fixed TTL
  -> process all snapshot batches
  -> release lock
```

本次 review 发现：即使 lock TTL 已经调大并做成配置，只要一次 refresh 运行时间超过 TTL，lock 仍可能在任务尚未结束时过期。

## 2. 风险

可能出现的竞态：

```text
T+0s    worker A acquire lock
T+300s  lock expires
T+310s  worker B acquire new lock
T+310s  worker A still running
```

结果：

- 重复 Massive snapshot 请求
- 重复 Redis 写入
- provider quota 浪费
- coordinator 日志和指标噪音

该问题通常不会直接导致错误数据或用户请求失败，因此暂定为 P2。

## 3. 未来修复方向

推荐增加 token-checked lock renewal：

```text
Acquire lock(token, ttl)
  |
  v
for each snapshot batch:
  fetch Massive
  write Redis
  extend lock if redis.get(lock_key) == token
      |
      +-- success -> continue
      |
      +-- failed  -> stop or report lock_lost
```

注意不要直接 `EXPIRE lock_key`。必须先校验 token，避免 lock 已经过期并被其他 worker 重新获取后，旧 worker 误续新 worker 的 lock。

## 4. 触发时机

以下任一条件满足时，应优先处理：

- watchlist distinct ticker 数量明显增加
- Massive snapshot latency 变高
- coordinator 单次运行时间接近或超过 lock TTL
- 日志中出现重复 coordinator run / upstream call 异常增多
- Massive quota 成为实际瓶颈

## 5. 当前决定

当前暂不实现 lock renewal。

短期通过较长、可配置的 lock TTL 降低发生概率；后续在 watchlist 规模或 provider latency 数据明确后，再实现 token-checked renewal。
