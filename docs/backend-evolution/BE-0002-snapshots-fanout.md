# BE-0002 — Watchlist Snapshots + Redis Snapshot Cache

> 状态：Reviewed
> 关联 PRD：`docs/prd/PRD-0001-market-watch.md`
> 范围：覆盖 G2 的批量 snapshot 行情能力，重点解决 backend 统一批量拉取、Redis 快照缓存、请求级 fallback；不包含增量推送通道、bars 持久化

## 1. 概览

本阶段直接收敛到一个简单、明确、可落地的方案：

- Frontend 不直接访问 Massive
- Frontend 通过 polling 调用 backend snapshots API
- Backend 定时从 Massive 批量拉取 snapshot
- 拉取集合直接来自 `watchlist_items` 的全局 `unique tickers`
- Backend 将最新 snapshot 写入 Redis
- 前端请求优先读 Redis
- 若 Redis 中缺少某些 ticker，backend 在同一个 snapshots API 内部回源 Massive，归一化后写回 Redis，再返回前端

本阶段的目标是先把“统一批量拉取 + Redis 缓存 + polling 可用”做稳定。

## 2. 目标

本阶段交付的核心能力：

- 用户可按最多 `50` 个 ticker 批量读取统一口径的 snapshots
- 响应可明确返回 `delay_minutes` / `is_realtime`
- Backend 内部具备统一的 Massive batch snapshot 拉取能力
- 系统通过后台定时任务刷新 Redis 中的 snapshot
- snapshots API 优先从 Redis 读取
- Redis miss 时，snapshots API 会在内部 fallback 回源 Massive，而不是要求 frontend 调用额外接口

本阶段重点是稳定和简单，而不是最大化实时性。

## 3. 非目标

- 不包含 bars 查询、回源、落库、补齐
- 不包含 quote-dependent 字段与能力
- 不包含增量推送通道
- 不包含 active set 跟踪
- 不把 snapshot 视图持久化到 PostgreSQL

## 4. 设计结论

### 4.1 最终方案

本阶段采用：

- 后台 `snapshot coordinator`
  - 定时读取 `watchlist_items` 的全局 `distinct ticker`
  - 按批次调用 Massive snapshot REST
  - 归一化后写入 Redis
- 前台 `snapshots API`
  - 优先从 Redis 读取
  - 缺失 ticker 在同一请求内部 fallback 回源 Massive
  - fallback 成功后写回 Redis

### 4.2 设计原则

- G2 的 snapshot 统一通过 REST 提供
- Backend 统一批量拉取 Massive，不让 frontend 直接承受上游模型复杂度
- Redis 是本阶段必须的共享快照层，不采用 in-memory 作为正式方案
- fallback 是同一个 snapshots API 的内部行为，不对 frontend 暴露单独 fallback 接口
- Massive 响应必须先归一化，再返回给 frontend；不能透传 Massive 原始结构

## 5. 目标架构

### 5.1 总体拓扑

```text
                     +----------------------+
                     |     Massive REST     |
                     +----------+-----------+
                                ^
                                |
            +-------------------+-------------------+
            |                                       |
            |                                       |
            v                                       |
 +--------------------------+                       |
 | Snapshot Coordinator     |                       |
 | - read distinct tickers  |                       |
 | - batch pull Massive     |                       |
 | - normalize snapshots    |                       |
 | - write Redis            |                       |
 +-------------+------------+                       |
               |                                    |
               v                                    |
      +----------------------+                      |
      |        Redis         |----------------------+
      | snapshot:{ticker}    |
      | updated_at / ttl     |
      +----------+-----------+
                 ^
                 |
                 |
      +----------+-----------+
      | Snapshots API        |
      | - read Redis         |
      | - fallback Massive   |
      | - write Redis        |
      +----------+-----------+
                 |
                 v
            Frontend Polling
```

### 5.2 执行顺序

```text
Background refresh
  -> select distinct ticker from watchlist_items
  -> chunk tickers
  -> batch fetch Massive snapshots
  -> normalize
  -> write Redis

Frontend request
  -> GET /market-data/snapshots
  -> backend reads Redis
  -> if any ticker missing:
       fetch missing tickers from Massive
       normalize
       write Redis
  -> return unified response
```

## 6. 范围拆分

### 6.1 Now

本阶段建议直接完成：

- `GET /api/v1/market-data/snapshots`
- `GET /api/v1/market-data/capabilities`
- Redis snapshot cache
- 基于 `watchlist_items` 的定时批量 refresh coordinator
- snapshots API 内部 fallback 回源 Massive

### 6.2 Next

下一阶段可以在本设计上继续补：

- 更细的 stale 语义与恢复策略
- 按 market status 区分刷新频率
- 更细的回源去重策略

## 7. ticker 集合策略

### 7.1 当前方案

定时刷新使用的数据集合直接定义为：

- `watchlist_items` 表中的全局 `distinct ticker`

也就是：

```text
watchlist_items
  -> select distinct ticker
  -> refresh all unique tickers on schedule
```

### 7.2 说明

- 实现简单
- 不需要先建设 session/activity 跟踪
- 与当前产品规模更匹配

补充说明：

- 某些 ticker 即使当前没有人在看，只要仍存在于 watchlist 中，也会继续被刷新
- 本阶段接受这个约束，以换取实现简单和行为稳定

## 8. Snapshot 视图模型

### 8.1 frontend 公共字段

对 frontend 暴露的字段沿用 PRD 口径：

- `ticker`
- `last`
- `change`
- `change_pct`
- `open`
- `high`
- `low`
- `volume`
- `prev_close`
- `market_status`
- `delay_minutes`
- `is_realtime`
- `updated_at`

### 8.2 backend 内部元数据

backend 可以额外维护但不对 frontend 暴露：

- `data_source`
- `fetched_at`
- `stale_reason`
- `refresh_batch_id`
- `partial_response`

说明：

- `data_source` 只用于 backend 日志、调试、可观测性
- frontend 不依赖 backend 的内部取数路径
- 若本次响应构成 `partial_response`，当前阶段只要求打印 `WARN` 日志

## 9. API 设计

### 9.1 统一约定

- API 前缀：`/api/v1`
- 所有 market data 接口均为受保护接口
- ticker 统一转大写
- 单次 snapshots 查询最多 `50` 个 ticker
- 单次请求内部要做去重，避免 `AAPL,AAPL` 这类重复输入放大内部处理

### 9.2 `GET /api/v1/market-data/capabilities`

用途：

- 返回 frontend 展示当前数据模式所需的最小能力信息

成功响应：`200 OK`

```json
{
  "market_data": {
    "delay_minutes": 15,
    "is_realtime": false,
    "supports_stream": false
  }
}
```

说明：

- `supports_stream` 在本阶段建议返回 `false`
- frontend 不根据 Massive plan 自行推断能力

### 9.3 `GET /api/v1/market-data/snapshots`

查询参数：

- `tickers`: 必填，逗号分隔 ticker 列表，如 `AAPL,NVDA,MSFT`

用途：

- 批量读取统一口径的 watchlist snapshots
- 优先从 Redis 读取
- 若部分 ticker miss，则在同一请求内部回源 Massive
- fallback 成功后写回 Redis

成功响应：`200 OK`

```json
{
  "items": [
    {
      "ticker": "AAPL",
      "last": 212.34,
      "change": 1.23,
      "change_pct": 0.58,
      "open": 211.10,
      "high": 213.00,
      "low": 210.60,
      "volume": 45678901,
      "prev_close": 211.11,
      "market_status": "regular",
      "delay_minutes": 15,
      "is_realtime": false,
      "updated_at": "2026-04-08T08:30:00Z"
    }
  ],
  "meta": {
    "delay_minutes": 15,
    "is_realtime": false,
    "request_id": "req_123"
  }
}
```

建议行为：

- 优先返回可用部分数据，而不是因为个别 ticker miss 直接整批失败
- Redis miss 时，只回源缺失 ticker，不整批重拉
- 若部分 ticker 当前不可用，响应中只返回成功解析的 ticker；是否构成 partial response 由 backend 内部记录
- 若全部 ticker 都不可用且上游回源失败，再返回明确业务错误

建议错误：

- `400` `VALIDATION_ERROR`
- `401` `AUTH_REQUIRED`
- `422` `MARKET_DATA_TICKER_INVALID`
- `409` `MARKET_DATA_TICKER_LIMIT_EXCEEDED`
- `503` `MARKET_SNAPSHOT_UPSTREAM_UNAVAILABLE`

## 10. 内部组件设计

### 10.1 Snapshot Coordinator

职责：

- 定时从数据库读取 `watchlist_items` 的全局 `distinct ticker`
- 对 ticker 按批次分片
- 调用 Massive batch snapshot REST
- 将 Massive 响应归一化后写入 Redis

关键说明：

- 这是后台定时刷新链路，不直接处理 frontend 请求
- worker 调度实现先统一走 `Celery`
- 刷新频率按当前 market data mode 分档：
  - `delay_minutes == 0` 时，默认 `3s`
  - `delay_minutes == 15` 时，默认 `10s`
- Massive 支持多 ticker 批量 snapshot，因此 coordinator 应优先使用批量接口
- Massive 官方 `Full Market Snapshot` 文档说明 `tickers` 参数支持逗号分隔列表，留空时可查询全市场；当前实现先将单次 batch chunk size 固定为 `100`

### 10.2 Redis Snapshot Store

职责：

- 保存每个 ticker 的最新快照
- 保存必要的时间元数据
- 为 snapshots API 提供快速读取

本阶段要求：

- Redis 为正式方案
- 不使用单机内存缓存作为主要实现

原因：

- Redis 更适合 TTL 管理
- Redis 更适合多实例共享
- Redis 更适合作为 coordinator 和 API 节点之间的共享层

### 10.3 Snapshots API Fallback Path

职责：

- 读取 Redis
- 找出缺失 ticker
- 在当前请求内部回源 Massive
- 归一化并写回 Redis
- 返回统一响应

关键规则：

- fallback 是已有 snapshots API 的内部行为
- 不新增单独的 frontend fallback endpoint
- fallback 返回的仍然是项目统一 snapshot schema，而不是 Massive 原始响应
- 该路径属于 `GetBatchSnapshots` use case 的内部执行步骤，不单独作为 API-facing use case 暴露

## 11. Redis 设计建议

### 11.1 key 设计

建议最小 key 设计：

- `snapshot:{ticker}`
  - value: 单 ticker snapshot JSON

### 11.2 value 建议字段

- `ticker`
- `last`
- `change`
- `change_pct`
- `open`
- `high`
- `low`
- `volume`
- `prev_close`
- `market_status`
- `delay_minutes`
- `is_realtime`
- `updated_at`
- `fetched_at`

### 11.3 TTL 方向

建议：

- Redis key 设置 TTL
- 同时在 value 中保存 `updated_at` / `fetched_at`
- TTL 默认设置为当前刷新周期的 `5` 倍
  - `delay_minutes == 0` 时，默认 TTL `15s`
  - `delay_minutes == 15` 时，默认 TTL `50s`

原因：

- TTL 适合清理陈旧 key
- `updated_at` 适合对 frontend 返回明确新鲜度信息
- key 过期后通常会表现为 Redis miss；Redis miss 时应重新回源 Massive

## 12. 冷启动、fallback 与 stale

### 12.1 冷启动

场景：

- 某个 ticker 已存在于 watchlist 中
- 但 Redis 中还没有对应 snapshot

建议处理：

```text
Frontend request
  -> read Redis
  -> find missing tickers
  -> fetch missing tickers from Massive
  -> normalize
  -> write Redis
  -> return
```

### 12.2 fallback 原则

建议优先顺序：

```text
Redis snapshot
  -> Massive fallback for missing tickers
  -> return resolved tickers if some tickers still unavailable
  -> fail only when nothing usable exists
```

### 12.3 stale 语义

建议：

- stale 判断由 backend 负责
- Redis hit 后，snapshot freshness 通过 `updated_at` / `fetched_at` 判定
- snapshot age 超过当前刷新周期时，可视为 stale-but-usable
- Redis miss 时，统一触发 Massive fallback；不要把 TTL 直接等同于业务 stale 判定
- frontend 首版只依赖：
  - `delay_minutes`
  - `updated_at`

## 13. DDD 分层落点

遵循仓库 backend 分层约束：

- `api/`
  - `market_data` REST 路由
  - 请求与响应 DTO
- `application/`
  - `GetMarketDataCapabilities`
  - `GetBatchSnapshots`
  - `RunSnapshotCoordinatorRefresh`
- `domain/`
  - `Snapshot`
  - `MarketDataMode`
  - stale/freshness 规则
- `infrastructure/`
  - Massive REST client
  - Redis snapshot store
  - watchlist distinct ticker query
- `worker/`
  - snapshot coordinator 入口

不引入 interface-only 抽象；通过具体类做依赖注入。

说明：

- `GetBatchSnapshots` 是对外主 use case
- Redis 读取、missing ticker 判定、fallback Massive、写回 Redis 都属于 `GetBatchSnapshots` 的内部流程
- 如需复用 fallback 逻辑，可抽成内部 collaborator，但不单独定义为 API-facing use case

## 14. 分阶段执行建议

### P0 配置与能力收敛

- 统一 `delay_minutes`
- 统一 Massive plan capability 解析
- 明确 G2 使用 polling + Redis snapshots

### P1 Redis snapshot store

- 建立 `snapshot:{ticker}` key 结构
- 确定 TTL 策略
- 建立读写路径

### P2 coordinator refresh

- 查询 `watchlist_items distinct ticker`
- 按批次拉取 Massive snapshot
- 归一化并写入 Redis

### P3 snapshots API

- `/market-data/capabilities`
- `/market-data/snapshots`
- Redis read + missing ticker fallback

### P4 stale / partial 语义

- 明确部分 ticker 缺失时的返回规则
- 明确 stale 规则
- 明确错误码、`request_id` 与 partial warn 日志

## 15. 测试设计

### 15.1 测试目标

- 确认 snapshots API 字段口径稳定
- 确认 coordinator 可从 `watchlist_items` 正确提取 unique tickers
- 确认 Massive batch snapshot 可正确映射到 Redis snapshot 结构
- 确认 Redis miss 时 API fallback 可用
- 确认 Massive 异常时可返回已解析 ticker，而不是整批崩溃

### 15.2 建议测试层次

#### A. Domain / Application

- ticker 去重与标准化
- 部分 ticker 缺失时的响应组装
- stale/freshness 判定

#### B. Infrastructure

- `distinct ticker` 查询正确
- Massive batch snapshot 映射正确
- Redis snapshot store 读写正确

#### C. API 集成测试

- `GET /market-data/capabilities` 返回统一模式
- `GET /market-data/snapshots` 可批量返回最多 50 个 ticker
- 重复 ticker 输入被去重
- Redis 命中时成功返回
- Redis miss 时触发 Massive fallback
- 部分 ticker 回源失败时返回已解析 ticker 集合
- 未登录访问被拒绝

#### D. Worker / Coordinator 测试

- coordinator 能按批次刷新全局 unique tickers
- coordinator 刷新结果可被 API 节点读取

## 16. 日志要求

- 当前阶段不建设额外的 observability infra
- 所有 snapshots 请求记录 `request_id`
- Massive 上游调用状态记录基础结构化日志
- 记录关键字段：
  - `ticker_count`
  - `redis_hit_count`
  - `redis_miss_count`
  - `user_id`
  - `request_id`
  - `upstream_latency_ms`
- 若本次响应构成 `partial_response`，打印 `WARN` 日志，并记录缺失或异常 ticker
- coordinator 侧记录基础事件日志：
  - distinct ticker count
  - batch refresh start / success / failure
  - fallback start / success / failure

## 17. 交付定义

本阶段完成后，应满足：

- Backend 有稳定的批量 snapshots 接口
- Frontend 能通过 backend 获取统一 `delay_minutes`
- Frontend 使用 polling 即可稳定读取 snapshots
- Backend 通过 coordinator 定时将 `watchlist_items` 的 unique tickers 批量导入 Redis
- snapshots API 在 Redis miss 时可内部 fallback 回源 Massive
- 前端不需要了解 backend 的 fallback 细节，也不需要调用额外 fallback 接口

## 18. 当前默认值与待验证项

- coordinator 刷新频率按当前 mode 分档：
  - `delay_minutes == 0` 时，默认 `3s`
  - `delay_minutes == 15` 时，默认 `10s`
- coordinator 调度实现当前走 `Celery Beat`
- Redis TTL 默认设置为刷新周期的 `5` 倍：
  - `delay_minutes == 0` 时，默认 `15s`
  - `delay_minutes == 15` 时，默认 `50s`
- Massive batch snapshot 的 chunk size 当前固定为 `100`
- partial response 当前不对 frontend 外显，只写 `WARN` 日志并打印缺失或异常 ticker
