# BE-0003 — Bars Query + Canonical Storage + Aggregation

> 状态：Draft
> 
> 关联 PRD：`docs/prd/PRD-0001-market-watch.md`
> 
> 关联参考：`docs/external-api-reference/massive-stocks-api-reference.md`
> 
> 范围：覆盖美股股票 bars 的统一读取接口、交易日与 session 规则、`1m/1d` canonical storage、其它 resolution 聚合、后台刷新/初始化/清理策略、fill 语义、以及与图表技术指标相关的 backend 边界；不包含 SSE/WebSocket 推送实现

## 1. 概览

本阶段收敛到一个明确方案：

- 这是一个 **基础 MVP** 方案，优先保证口径清晰、实现简单、查询稳定
- Frontend 只调用一个统一 bars 接口
- Backend 只把 `1m` 与 `1d` 作为 canonical storage 落库
- 其它 resolution 全部由 backend 在读路径聚合
- `1m` canonical 保存 provider truth，不保存 synthetic fill bars
- `1d` canonical 仅保存 **completed regular-day bars**
- `Massive` 在 MVP 中只作为 **后台写入源**
- API 请求路径 **只读数据库**，不在请求中主动 read-through Massive
- `1m` canonical 由后台 bootstrap / refresh / finalizer / cleanup 任务维护
- `1m` 历史保留窗口收敛为 **最近 10 个 trading days**
- `1d` 历史保留窗口收敛为 **最近 10 years**
- `1W/1M/1Q` 基于 `1d` regular bars 聚合；当前未完成 bucket 通过 `1m` stitch
- 技术指标在 MVP 阶段默认由 frontend 计算，backend 先稳定 bars 口径

MVP 与 product-level 路线的边界：

```text
MVP
  -> REST polling
  -> 1m/1d canonical storage
  -> background-only Massive ingestion
  -> query-time aggregation
  -> only current open bucket stitch
  -> 10 trading days 1m retention
  -> 10 years 1d retention

Later
  -> WebSocket / SSE incremental updates
  -> pre-aggregated views / materialized views
  -> short-TTL hot cache
  -> server-side indicators
  -> broader session / market coverage
```

总体读路径：

```text
Frontend
  -> GET /api/v1/market-data/bars
  -> normalize query
  -> resolve mode
       latest session slice | explicit range
  -> resolve calendar + session window
  -> choose canonical source
       intraday / non-regular day -> 1m
       regular 1D/1W/1M/1Q       -> 1d (+ optional 1m stitch)
  -> read DB
  -> aggregate
  -> apply fill
  -> mark partial/final
  -> return bars + meta

Background jobs
  -> bootstrap ticker bars
  -> refresh current-day 1m
  -> finalize post-close 1D
  -> reconcile historical gaps
  -> cleanup expired 1m rows
```

## 2. 目标

本阶段要交付的核心能力：

- 提供一个统一的 `GET /api/v1/market-data/bars`
- 支持 `1m / 5m / 15m / 30m / 60m / 1D / 1W / 1M / 1Q`
- 支持 `pre_market / regular / after_hours`
- 对非交易日、节假日、half-day、DST 使用统一交易日历规则
- bars 查询严格只读数据库，不在请求路径中依赖 Massive
- 在 1 分钟级 polling 下，最新未完成 bucket 能稳定返回且明确标记 `is_final=false`
- 用一致、可测试的规则处理 sparse provider bars 和 synthetic fill bars
- 提供后台初始化、刷新、收盘固化与清理任务
- 为 frontend 计算 MA/BOLL 等指标提供稳定 bars 口径和足够 warm-up 数据

## 3. 非目标

- 不包含 SSE / WebSocket push
- 不包含 quote-dependent 技术指标
- 不包含 overnight session
- 不包含 futures、options、crypto 等多市场日历
- 不包含服务端指标计算 API
- 不包含 corporate actions 全量本地建模；MVP 只为 adjustment 维度预留扩展位

## 4. 设计结论

### 4.1 一句话结论

- **存储层只保存 provider truth**
- **展示层才做 session filtering、resolution aggregation、carry-forward fill、partial stitching**
- **这套设计优先服务 MVP，不预设为最终 product-level 架构**

### 4.2 为什么只存 `1m + 1d`

- `1m` 是所有 intraday resolution 的单一事实源
- `1d` 是 regular `1D/1W/1M/1Q` 的高效事实源
- 只存两个 canonical layer，可以避免多套物化粒度之间的修复与一致性问题
- 未来若某些 resolution 查询量极高，再针对热点做派生物化，不影响当前 API 契约

### 4.3 为什么 `1d` 只存 completed regular-day bars

- `1d` 是高阶 regular K 的历史事实层，天然更适合保存完成态
- 当前 trading day 的 daily / weekly / monthly / quarterly partial bar，统一由 `1m` stitch，避免 current day 的 `1d` 行频繁被改写
- `pre_market` 与 `after_hours` 的 day-level 聚合直接由 `1m` 生成，不单独存 daily canonical

### 4.4 为什么 MVP 先不做预聚合视图

- 当前优先目标是把接口语义、交易日规则、fill 规则、partial 语义定义清楚
- 在需求尚未稳定前，过早引入多层预聚合，容易把错误口径固化成额外存储成本
- 先用 `1m/1d + query-time stitch` 可以更快验证：
  - 哪些 resolution 查询最热
  - 哪些图表最需要低延迟
  - 哪些 session 规则最容易引发修正

product-level 阶段若观测到热点，再考虑：

- 数据库 view / materialized view
- 后台预聚合作业
- Redis hot-range cache
- WebSocket minute/second 增量驱动

## 5. 统一术语

本文件后续统一使用下列术语：

- `bar`
  - 一根时间 bucket 内的聚合行情
- `resolution`
  - frontend 请求的图表粒度，如 `1m`、`5m`、`1D`、`1W`
- `canonical storage`
  - backend 落库的事实层 bars，只允许 `1m` 与 `1d`
- `provider truth`
  - 上游 Massive 返回的真实聚合结果，不含 backend synthetic fill
  - 它可能是 sparse 的，因为某些时间 bucket 若没有合格成交，provider 可能不会返回 bar
- `trading day`
  - 以 `America/New_York` 为基准的市场交易日，而不是 UTC 日期
- `session`
  - 本期只支持：
    - `pre_market`
    - `regular`
    - `after_hours`
- `partial bar`
  - 当前 bucket 尚未结束、后续仍可能变化的 bar
- `final bar`
  - 当前 bucket 已结束，backend 认为在请求路径中不再变动的 bar
- `mutable tail`
  - 当前 trading day 内、仍可能被后台刷新任务覆盖更新的最新时间段
  - 在本期 MVP 中，它是 **后台写路径概念**，不是请求路径回源概念
- `synthetic fill bar`
  - backend 为连续显示而补出的 bar，非 provider 真值
- `carry-forward fill`
  - 用上一可用 `close` 衍生 synthetic fill bars 的策略
- `VW`
  - `volume-weighted average price`，即成交量加权平均价
- `adjustment`
  - 价格复权模式。本文件只定义：
    - `split_adjusted`
    - `raw`

## 6. 支持范围

### 6.1 Resolution 支持矩阵

| Resolution | Source | Session 支持 | 说明 |
| --- | --- | --- | --- |
| `1m` | `1m` | 全部 3 个 | 分时基础粒度 |
| `5m` | `1m` | 全部 3 个 | session 内聚合 |
| `15m` | `1m` | 全部 3 个 | session 内聚合 |
| `30m` | `1m` | 全部 3 个 | session 内聚合 |
| `60m` | `1m` | 全部 3 个 | session 内聚合 |
| `1D` | `1d` 或 `1m` | 全部 3 个 | `regular` 优先用 `1d`，非 regular 用 `1m` |
| `1W` | `1d` + `1m stitch` | `regular` only | 当前 bucket 可 stitch |
| `1M` | `1d` + `1m stitch` | `regular` only | 当前 bucket 可 stitch |
| `1Q` | `1d` + `1m stitch` | `regular` only | 当前 bucket 可 stitch |

### 6.2 Session 支持边界

- 本期不支持 `overnight`
- `1W / 1M / 1Q` 只支持 `regular`
- 对 `1W / 1M / 1Q` 请求 `pre_market` 或 `after_hours` 时，返回明确业务错误：
  - `422 MARKET_BARS_UNSUPPORTED_SESSION_RESOLUTION`

这样做的原因：

- `1W / 1M / 1Q` 若支持 non-regular，需要长期依赖 `1m` 聚合，历史成本高
- `1d` canonical 只保存 completed regular bars，先把 regular K 链路做稳定

## 7. API 设计

### 7.1 Endpoint

- `GET /api/v1/market-data/bars`

frontend-facing 参数模型在本阶段做一次收敛：

- 不直接暴露 Massive 风格的 `timespan + multiplier + limit`
- 统一改为：
  - `resolution`
  - `count_back`
  - `from/to`

这样可以把 provider 参数细节留在 backend adapter 内部。

### 7.2 Query 参数

#### 必填参数

- `ticker`
  - 单个 ticker，统一转大写
- `resolution`
  - 枚举：`1m|5m|15m|30m|60m|1D|1W|1M|1Q`
- `session`
  - 枚举：`pre_market|regular|after_hours`

#### 可选参数

- `from`
  - RFC3339 UTC 时间戳
- `to`
  - RFC3339 UTC 时间戳
- `count_back`
  - 需要的输出 bars 数量
- `adjustment`
  - 枚举：`split_adjusted|raw`
  - 默认：`split_adjusted`
- `fill`
  - 枚举：`carry_forward|none`
  - 默认：`carry_forward`
- `include_partial`
  - `true|false`
  - 默认：`true`

### 7.3 查询模式

本接口只允许两种查询模式：

1. `explicit range mode`
   - 必须提供 `from` + `to`
   - `count_back` 不允许同时出现
2. `latest mode`
   - 不提供 `from`
   - 允许提供 `to`
   - 允许提供 `count_back`

校验规则：

- `from >= to` 返回 `422 MARKET_BARS_RANGE_INVALID`
- `count_back <= 0` 返回 `422 MARKET_BARS_COUNT_BACK_INVALID`
- `explicit range mode` 中若同时传 `count_back`，返回 `422 MARKET_BARS_QUERY_MODE_INVALID`
- `count_back > 2000` 返回 `422 MARKET_BARS_COUNT_BACK_TOO_LARGE`

### 7.4 Latest Mode Anchor 与 `count_back` 语义

latest mode 先计算一个 `anchor_time`：

```text
anchor_time = min(request.to or effective_now, effective_now)
```

后续所有“今天是不是交易日”“当前 session 是否已开始”的判断，都基于 `anchor_time` 对应的 `America/New_York` 日期，而不是机器当前日期。

#### Intraday latest mode

适用：`1m / 5m / 15m / 30m / 60m`

规则：

- 返回一个 **单 session slice**
- 若 `count_back` 缺失：
  - 返回该 session slice 从 session start 到 `anchor_time` 的全部可用 bars
- 若 `count_back` 存在：
  - 只返回该 session slice 内最后 `count_back` 根 bars
  - 不跨 trading day 回补

#### Day-or-higher latest mode

适用：`1D / 1W / 1M / 1Q`

规则：

- 若 `count_back` 缺失：
  - 返回 backend 默认窗口
  - 推荐默认值：
    - `1D`: `120`
    - `1W`: `104`
    - `1M`: `120`
    - `1Q`: `80`
- 若 `count_back` 存在：
  - 返回以最近可用 bucket 为终点的最后 `count_back` 根

默认窗口的目的：

- 避免 frontend 忘记传 `count_back` 时返回无界历史
- 给日线指标 warm-up 留出基本空间

### 7.5 输出条数保护

为了控制 DB 和 provider 成本，本接口增加两条保护：

- latest mode：
  - 受 `count_back <= 2000` 约束
- explicit range mode：
  - backend 在 calendar-aware 估算输出 bars 数量后，若预计超过 `5000`
  - 返回 `422 MARKET_BARS_RANGE_TOO_LARGE`

### 7.6 输出结构

成功响应：`200 OK`

```json
{
  "bars": [
    {
      "time": "2026-04-10T13:30:00Z",
      "open": 182.10,
      "high": 182.44,
      "low": 181.98,
      "close": 182.30,
      "volume": 483210,
      "vw": 182.22,
      "trade_count": 1521,
      "is_final": true,
      "is_synthetic": false
    }
  ],
  "meta": {
    "ticker": "AAPL",
    "resolution": "5m",
    "session": "regular",
    "adjustment": "split_adjusted",
    "fill": "carry_forward",
    "requested_from": "",
    "requested_to": "",
    "effective_from": "2026-04-10T13:30:00Z",
    "effective_to": "2026-04-10T15:05:20Z",
    "effective_trading_day": "2026-04-10",
    "market_timezone": "America/New_York",
    "source_granularity": "1m",
    "data_source": "db",
    "partial_range": false,
    "readiness": "ready",
    "calendar_shifted": false,
    "contains_partial_bar": true,
    "delay_minutes": 15,
    "request_id": "req_123"
  }
}
```

### 7.7 Response 头

响应头保留 PRD 里要求的两个字段：

- `X-Data-Source: db`
- `X-Partial-Range: true|false`

说明：

- body 中的 `meta` 是 canonical 语义
- 响应头只是便于前端快速读取，不单独承载业务语义

### 7.8 Bars 字段定义

- `time`
  - bucket 开始时间，RFC3339 UTC
- `open/high/low/close`
  - 标准 OHLC
- `volume`
  - bucket 内累计成交量
- `vw`
  - bucket 内成交量加权平均价；无成交时为 `null`
- `trade_count`
  - bucket 内成交笔数；无成交时为 `0`
- `is_final`
  - 当前 bucket 是否已经完成
- `is_synthetic`
  - 是否为 backend 补出的 synthetic fill bar

### 7.9 Meta 字段定义

- `requested_from/requested_to`
  - 原始请求区间；latest mode 下可为空字符串
- `effective_from/effective_to`
  - backend 实际参与查询和聚合的区间
- `effective_trading_day`
  - latest intraday mode 下解析出的交易日
- `source_granularity`
  - `1m` 或 `1d`
- `data_source`
  - MVP 固定为 `db`
- `partial_range`
  - MVP 阶段用于表达“请求左边界或已检测到的中间区间不能完整满足”
  - 典型场景：
    - 数据超出本地最早已知历史边界
    - backend 在有效查询区间内检测到 expected bucket / trading day 缺口
    - 当前请求被 backend 主动裁剪为较小有效区间后仍返回成功
  - MVP 阶段不承诺 latest-tail freshness：
    - latest mode 若后台刷新尚未覆盖到最新 `anchor_time`
    - 只返回当前 DB 中已知可用结果
    - 不仅因为最新尾部数据暂缺就把 `partial_range` 置为 `true`
  - latest-tail stale / refresh miss 优先通过后台任务重试、`readiness=degraded`、日志与后续 reconciliation 表达
- `readiness`
  - `pending|initializing|ready|degraded|failed`
  - 反映该 ticker 的 backend bars 准备状态
- `calendar_shifted`
  - latest mode 因节假日/周末 fallback 到最近交易日时为 `true`
- `contains_partial_bar`
  - 响应中至少一根 `is_final=false`

## 8. 交易日历与 Session 模型

### 8.1 统一时区

- 市场日历判定时区：`America/New_York`
- API 时间戳返回：统一 UTC
- 所有“属于哪个交易日”的判断，都必须基于 `America/New_York`

### 8.2 Session 定义

本期股票 session 统一定义为：

- `pre_market`
  - `04:00:00 ET <= t < regular_open`
- `regular`
  - `regular_open <= t < regular_close`
- `after_hours`
  - `regular_close <= t < 20:00:00 ET`

其中：

- `regular_open` 通常是 `09:30 ET`
- `regular_close` 通常是 `16:00 ET`
- half-day 时，`regular_close` 使用交易日历给出的提前收盘时间，而不是固定 `16:00 ET`

### 8.3 Session 判定规则

给定一个 `1m` bar 的 `bucket_start_at`：

```text
UTC timestamp
  -> convert to America/New_York
  -> find trading_day
  -> load regular_open / regular_close for that trading_day
  -> classify into
       pre_market | regular | after_hours | unsupported
```

`unsupported` 说明：

- 落在 `20:00 ET` 之后、`04:00 ET` 之前的数据，本期视为 unsupported
- 若 provider 返回该类分钟 bars，backend 不落库，不对 frontend 暴露

### 8.4 Latest Mode 交易日 fallback

latest mode 的 fallback 不是“统一退到最近交易日”，而是按 resolution 区分：

#### Intraday resolutions

适用：`1m / 5m / 15m / 30m / 60m`

规则：

- 若今天不是交易日：
  - fallback 到最近一个交易日的同一 session
  - `calendar_shifted=true`
- 若今天是交易日，且所选 session 尚未开始：
  - 返回空 bars
  - 不 fallback 到上一个交易日
- 若今天是交易日，且所选 session 已开始：
  - 返回今天该 session 的 bars

这条规则用于满足产品约束：

- 若盘前已有数据，但 regular 尚未开始，regular 分时图应为空

#### Day-or-higher resolutions

适用：`1D / 1W / 1M / 1Q`

规则：

- latest mode 总是锚定“最近可用 completed bucket”
- 若当前 bucket 已开始且 `include_partial=true`：
  - 在历史 completed buckets 后追加一个 partial bucket
- 若当前 bucket 尚未开始：
  - 不追加 partial bucket
- 不因为“今天 regular 尚未开始”而清空整个图表

说明：

- 这样 regular 日 K 在开盘前仍能看到历史日线
- 但 intraday regular 分时图在开盘前保持空

### 8.5 Explicit Range Mode

explicit range mode 不做自动交易日 fallback：

- backend 仅返回 `[from, to)` 内、且属于所选 session 的 bars
- 周末/节假日区间没有命中 bars 时，正常返回空数组
- `calendar_shifted=false`

## 9. Canonical Storage 设计

### 9.1 总原则

- DB 只保存 provider truth
- synthetic fill bars 只在 read path 中临时生成
- canonical rows 使用 upsert，按自然键覆盖
- `regular` `1m` canonical 保留最近 `10` 个 trading days
- `pre_market` / `after_hours` `1m` canonical 只保留最新 `1` 个 trading day
- `1d` canonical 只保留最近 `10` years

### 9.2 `market_bars_1m`

用途：

- 承接 provider 的 minute bars，并按 session-aware retention 写入
- 覆盖 `pre_market / regular / after_hours`
- 作为所有 intraday resolution 的事实层
- 作为 current day / current bucket stitch 的事实层

建议字段：

- `ticker`
- `adjustment`
- `bucket_start_at_utc`
- `trading_day`
  - `America/New_York` 视角的交易日
- `session_kind`
  - `pre_market|regular|after_hours`
  - 写入时派生
- `open`
- `high`
- `low`
- `close`
- `volume`
- `vw`
- `trade_count`
- `provider_updated_at`
- `is_final`
- `first_synced_at`
- `last_synced_at`

自然键建议：

- `(ticker, adjustment, bucket_start_at_utc)`

重要约束：

- 只保存 provider 返回的真实 `1m` bars
- 不保存 `5m/15m/30m/60m`
- 不保存 synthetic fill bars
- `regular` 只保留最近 `10` 个 trading days
- `pre_market` / `after_hours` 只保留最新 `1` 个 trading day

### 9.3 `market_bars_1d`

用途：

- 保存 completed regular-day bars
- 作为 regular `1D / 1W / 1M / 1Q` 的历史事实层

建议字段：

- `ticker`
- `adjustment`
- `trading_day`
- `bucket_start_at_utc`
  - 该 trading day 的 regular open UTC
- `open`
- `high`
- `low`
- `close`
- `volume`
- `vw`
- `trade_count`
- `provider_updated_at`
- `first_synced_at`
- `last_synced_at`

自然键建议：

- `(ticker, adjustment, trading_day)`

重要约束：

- 只保存 `session=regular`
- 只保存 completed trading day
- 当前未完成 trading day 不写入 `1d`
- 只保留最近 `10` years

### 9.4 Adjustment 维度

本期 schema 必须预留 `adjustment` 维度：

- `split_adjusted`
- `raw`

MVP 建议：

- 默认只实现 `split_adjusted`
- `raw` 可以暂时返回 `422 MARKET_BARS_ADJUSTMENT_UNSUPPORTED`
- 但表结构和 API 契约不要把 `raw` 封死

## 10. Read Path

### 10.1 主流程

```text
request
  -> validate query
  -> resolve market data mode (delay_minutes)
  -> clamp "now" by delay_minutes
  -> resolve query mode
  -> resolve session window(s)
  -> choose source layer
  -> read DB
  -> aggregate to requested resolution
  -> apply fill
  -> mark partial bars
  -> build response meta
```

### 10.2 Delay Clamp

若环境是 delayed mode：

```text
effective_now = now_utc - delay_minutes
```

后续所有 latest / mutable / partial 判定，都基于 `effective_now`，而不是机器当前时间。

这样可以避免：

- 前端看到“15 分钟延迟”标识
- 但 backend 却把延迟窗口之后的 bars 提前返回

### 10.3 Source Layer 选择

规则：

- `1m / 5m / 15m / 30m / 60m`
  - 总是从 `1m` 读取
- `1D + regular`
  - completed days 优先从 `1d`
  - current day partial 由 `1m` stitch
- `1D + pre_market/after_hours`
  - 从 `1m` 读取并按 trading day 聚合
- `1W / 1M / 1Q + regular`
  - completed days 从 `1d`
  - current open bucket 由 `1m` stitch current day

## 11. 后台写入与 Gap Reconciliation

### 11.1 总原则

- `Massive` 只在后台任务中访问
- API 请求路径不主动回源 provider
- canonical rows 使用 upsert，不做 append-only
- gap repair、首次初始化、当前日刷新、收盘固化都属于后台写路径职责

### 11.2 Gap 定义

本文件里的 `gap` 指 canonical storage 中本应存在、但当前缺失的 provider truth 区间。

按粒度分为：

- `1m gap`
  - 某个 trading day 的 minute 区间存在缺失 bucket
- `1d gap`
  - 某个 completed regular trading day 的 daily row 缺失

gap detection 必须基于 **期望时间栅格**，不是只看“表里是否有部分数据”。

### 11.3 后台回源粒度选择

- 写入 `1m` 事实层时：
  - 调 Massive minute range
  - 回写 `market_bars_1m`
- 写入 `1d` regular 历史层时：
  - 优先使用 completed regular-day 的 `1m` 聚合结果
  - 如历史 `1d` 缺失，也可调 Massive daily range 回写 `market_bars_1d`

### 11.4 后台任务失败后的行为

- 后台 refresh / bootstrap / reconciliation 失败：
  - 不阻塞已完成请求
  - 记录 `WARN/ERROR`
  - 依赖下一轮任务重试
- 请求路径不承担兜底回源职责
  - 若当前 DB 中缺数据，则返回已知可用结果
  - `meta.partial_range=true`
  - `X-Partial-Range: true`

### 11.5 Gap Repair 与 Fill 的边界

gap repair 与 fill 不是同一个概念：

- `gap repair`
  - 目的是补 provider truth
  - 只在后台任务中执行
- `fill`
  - 目的是给图表提供连续展示
  - 只在 read path 中临时生成

因此：

- 不能用 synthetic fill bar 代替 canonical gap 修复
- 即使最终返回给 frontend 的结果经过 fill，canonical storage 中的 gap 仍应被后台任务识别并修复

## 12. Aggregation 规则

### 12.1 通用聚合公式

从 child bars 聚合 parent bar 时：

- `open`
  - 第一个 child 的 `open`
- `high`
  - 所有 child 的 `high` 最大值
- `low`
  - 所有 child 的 `low` 最小值
- `close`
  - 最后一个 child 的 `close`
- `volume`
  - `sum(child.volume)`
- `trade_count`
  - `sum(child.trade_count)`
- `vw`
  - `sum(child.vw * child.volume) / sum(child.volume)`，只统计 `volume > 0` 的 child
  - 若总 `volume == 0`，则 `vw = null`

### 12.2 Intraday Bucket 对齐

`5m / 15m / 30m / 60m` 的 bucket 对齐点，统一以 **session start** 为 anchor，而不是自然小时整点。

例子：

```text
regular 5m
  09:30-09:34
  09:35-09:39
  ...

regular 60m
  09:30-10:29
  10:30-11:29
  ...

pre_market 60m
  04:00-04:59
  05:00-05:59
  ...
```

这样可以避免：

- `regular 60m` 被切成 `09:00-09:59` 这种无意义 bucket

### 12.3 `1D` 聚合

#### `1D + regular`

- completed trading day：
  - 使用 `market_bars_1d`
- current trading day partial：
  - 从 `market_bars_1m` 中筛出 current day `regular` rows 聚合

#### `1D + pre_market`

- 每个 trading day 聚合该日 `04:00 ET` 到 `regular_open` 的 `1m`

#### `1D + after_hours`

- 每个 trading day 聚合该日 `regular_close` 到 `20:00 ET` 的 `1m`

### 12.4 `1W / 1M / 1Q` 聚合

适用：`session=regular`

规则：

- 历史 completed days 来自 `market_bars_1d`
- current day 若存在且 `include_partial=true`，先由 `1m` 聚成 current partial `1D`，再并入当前 `1W / 1M / 1Q`

## 13. 时间 Bucket 边界

### 13.1 `1W`

- 以 `America/New_York` 的 calendar week 为准
- 周起点：周一 `00:00 ET`
- 一根 week bar 包含该周内所有 regular trading days
- 若周一休市，则 week bar 从该周第一个交易日开始

### 13.2 `1M`

- 以 `America/New_York` 的 calendar month 为准
- 一根 month bar 包含该月内所有 regular trading days
- 若月初是休市日，则从该月第一个交易日开始

### 13.3 `1Q`

- 固定自然季度：
  - `Q1 = 1-3 月`
  - `Q2 = 4-6 月`
  - `Q3 = 7-9 月`
  - `Q4 = 10-12 月`
- 一根 quarter bar 包含该季度内所有 regular trading days

### 13.4 高阶 Bucket 时间戳

高阶 bucket 的 `time` 统一使用：

- bucket 内 **第一个交易日的 regular open UTC**

示例：

- `1W`：该周第一个交易日的 regular open
- `1M`：该月第一个交易日的 regular open
- `1Q`：该季度第一个交易日的 regular open

## 14. Mutable Tail 与 Partial 规则

### 14.1 `1m`

- 当前 open minute bucket 视为 mutable
- 在 polling 场景下，同一 `1m` bar 允许被后台 refresh/finalizer 多次 upsert
- `effective_now` 未越过该 minute bucket 的结束边界前：
  - `is_final=false`

### 14.2 `5m / 15m / 30m / 60m`

- 若 parent bucket 中包含尚未 final 的 child `1m`
- 或者 `effective_now` 仍位于该 parent bucket 内
- 则 parent `is_final=false`

### 14.3 `1D`

- `regular`
  - current trading day 的 daily bar 在 regular session 结束前始终 `is_final=false`
- `pre_market`
  - current trading day 在 regular open 前，若已有 bars，`is_final=false`
  - regular open 到达后，该 trading day 的 pre_market `is_final=true`
- `after_hours`
  - current trading day 在 `20:00 ET` 前始终可能变化，`is_final=false`

### 14.4 `1W / 1M / 1Q`

- 当前 open bucket 只要仍包含 current trading day partial `1D`
- 则该 bucket `is_final=false`

### 14.5 MVP 的 Mutable 边界

MVP 后台写路径里，把 mutable tail 收敛为：

- **当前 trading day**

也就是：

- 后台 refresh 任务只主动覆盖当前 trading day 的 `1m`
- 已完成的过去 trading day，默认视为 immutable
- 对过去 trading day 的修复只由 bootstrap / reconciler / finalizer 触发

补充说明：

- 市场里确实可能有迟到成交、订正、corporate actions 影响
- 但 MVP 不在请求路径里做 provider repair
- 若后续发现需要更低延迟，可在 product-level 阶段重新引入流式增量链路

### 14.6 `1D / 1W / 1M / 1Q` 的 Current Bucket Stitch

当前未完成 bucket 的处理不是“每次重算整段历史”，而是：

```text
historical completed part
  -> read 1d

current open part
  -> read only current trading day 1m
  -> build current partial 1D
  -> if resolution is 1W/1M/1Q:
       merge partial 1D into current parent bucket
```

说明：

- `1D`
  - 只需聚合 current trading day 的 `1m`
- `1W / 1M / 1Q`
  - 只需把 current trading day partial `1D` 并入当前 open parent bucket
- backend 不应在每次请求时把整周、整月、整个季度的所有 `1m` 全量重算

### 14.7 `1d canonical` 的 Final 语义

`1d canonical` 保存的是 completed regular-day bars，因此在在线查询路径中，默认将其视为 stable final bars。

更准确地说：

```text
online request path
  -> treat historical 1d as final

offline repair path
  -> still allow explicit backfill / reconciliation overwrite
```

这意味着：

- 盘中不会把 current trading day 的 partial daily row 持续写进 `1d`
- 收盘后形成 final `1D`，才进入 `1d canonical`
- 若后续存在 corporate-action backfill 或历史修复，允许离线覆盖历史 `1d`

## 15. Fill 规则

### 15.1 总原则

- provider truth 可能是 sparse 的
- 对 frontend 默认返回连续可画的 bars
- 但 synthetic bars 必须可识别

### 15.2 `fill=none`

- 不补空
- 没有 provider truth 的 bucket 直接跳过

### 15.3 `fill=carry_forward`

若某个 bucket 没有 provider truth，则生成 synthetic fill bar：

- `open = seed_close`
- `high = seed_close`
- `low = seed_close`
- `close = seed_close`
- `volume = 0`
- `trade_count = 0`
- `vw = null`
- `is_synthetic = true`

### 15.4 Fill Seed 规则

`seed_close` 取值统一如下：

- `pre_market`
  - 上一个 trading day 的 regular close
- `regular`
  - 上一个 trading day 的 regular close
- `after_hours`
  - 当前 trading day 的 regular close

session 开始后：

- 若 session 内部再次出现空 bucket
  - `seed_close` 使用响应中上一根 bar 的 `close`

### 15.5 Fill 边界

- 只在 session 已开始后生成 synthetic bars
- session 尚未开始时，不因为 `fill=carry_forward` 自动生成整段空图
- 这保证：
  - regular 开盘前，regular 分时图仍为空

### 15.6 聚合后 Synthetic 规则

对 parent aggregated bar：

- 若所有 child 都是 synthetic
  - parent `is_synthetic=true`
- 若至少有一根 child 是真实 provider bar
  - parent `is_synthetic=false`

## 16. 技术指标边界

### 16.1 MVP 归属

以下技术指标在 MVP 阶段默认由 frontend 计算：

- `MA20`
- `MA200`
- `BOLL`
- 其它纯图表 overlay 指标

backend 本阶段不提供：

- `GET /indicators/...`
- 在 bars 响应中附带指标数组

### 16.2 为什么先放 frontend

- 降低 backend 实现复杂度
- bars 口径先统一，再谈指标统一
- 图表交互切换 resolution 时，frontend 本地计算更直接

### 16.3 Backend 需要保证的前提

- `count_back` 能支持指标 warm-up
- `is_synthetic` 与 `is_final` 对 frontend 可见
- `vw`、`trade_count` 不丢失

### 16.4 指标口径预设

即使指标先放 frontend，也要先定口径：

- 日线指标默认基于 `session=regular`
- 默认包含 synthetic bars
- 默认不包含 `is_final=false` 的最后一根，避免 polling 时指标抖动

若未来 backend 接管指标计算，应沿用这套口径，避免前后端漂移。

## 17. 第三方依赖建议

### 17.1 必要依赖：交易日历库

本阶段建议引入一个交易日历依赖，原因：

- 周末和节假日不够
- 还要处理 half-day / early close
- 还要稳定处理 DST

推荐方向：

- 使用 `exchange_calendars`
  - 对交易所 session / trading day 判定更贴合本项目当前实现模型
  - 能稳定提供 holiday、early close、session open/close 等规则
- 将其隔离在 `infrastructure/calendar/` 下
- Domain / Application 不直接依赖第三方 calendar 对象

推荐接入方式：

```text
Application Service
  -> TradingCalendarGateway (concrete class)
  -> exchange_calendars adapter
  -> normalized calendar DTO
```

### 17.2 Session 建模原则

即使引入交易日历库，本期也不直接依赖第三方去定义 `pre_market / after_hours`：

- `pre_market` 固定从 `04:00 ET` 开始
- `after_hours` 固定到 `20:00 ET` 结束
- `regular_open / regular_close` 由交易日历库提供

原因：

- 本期只做美股股票，不做更复杂的 venue-specific phase
- 这样更贴近当前产品需求，也更容易测试

### 17.3 可选增强

如果未来需要：

- 多市场支持
- 更细的交易阶段
- 商业级 schedule 准确性和外部 SLA

可再评估类似 `TradingHours.com` 这类商业日历服务。

## 18. 性能与演进说明

### 18.1 MVP 性能结论

在当前范围内，query-time stitch 的成本通常可控，因为：

- 单次 bars 请求只面向单个 ticker
- 历史 completed 部分优先读取 `1d`
- 只有当前 open bucket 需要读取少量 `1m`
- polling 频率预计在 `1m`

可以把读路径理解为：

```text
historical stable part
  -> cheap

current mutable part
  -> small incremental compute
```

### 18.2 各 resolution 的临时计算量

| Resolution | Query-time 额外计算量 | 说明 |
| --- | --- | --- |
| `1D regular` | 当天最多约 `390` 根 `1m` | 只处理 current trading day |
| `1W regular` | 本周已完成 `1d` + 当天最多约 `390` 根 `1m` | 不扫全周 minute |
| `1M regular` | 本月已完成 `1d` + 当天最多约 `390` 根 `1m` | 不扫全月 minute |
| `1Q regular` | 本季度已完成 `1d` + 当天最多约 `390` 根 `1m` | 不扫全季 minute |

half-day 下，regular 当前日的 `1m` 数量更少。

### 18.3 MVP 需要避免的坏实现

以下实现会把可控成本放大成性能问题：

- 每次查看 `1W/1M/1Q` 都从 `1m` 全量重算整个区间
- 没有 `count_back` / explicit range 上限
- 在 Python 层做无界列表拼接和排序
- 缺少合适索引，导致按 ticker + time 扫表

### 18.4 基础索引要求

`market_bars_1m` 至少需要：

- 主键或唯一键：`(ticker, adjustment, bucket_start_at_utc)`
- 辅助索引建议：
  - `(ticker, adjustment, trading_day, session_kind, bucket_start_at_utc)`

`market_bars_1d` 至少需要：

- 主键或唯一键：`(ticker, adjustment, trading_day)`
- 辅助索引建议：
  - `(ticker, adjustment, bucket_start_at_utc)`

### 18.5 MVP 可接受的优化边界

MVP 阶段可以接受的优化：

- SQL 层完成时间范围过滤与排序
- application 层完成有限集合聚合
- 对 hot ticker 的 bars 响应做短 TTL cache
- 在请求路径内只 stitch 当前 open bucket

MVP 阶段不建议过早引入：

- 多套 resolution 预物化表
- 复杂增量聚合作业编排
- 依赖 WebSocket 的强一致实时更新链路

### 18.6 Product-Level 演进方向

如果后续把它做成更完整的 product-level 行情产品，应考虑引入下列能力：

#### WebSocket / SSE

用途：

- 降低前端 polling 成本
- 更平滑地刷新 current minute / current session
- 为 active chart 提供更低延迟的 mutable tail 更新

建议顺序：

- 先 SSE 单向推送 minute aggregate 更新
- 后续再评估 WebSocket trades / minute aggs 是否值得直连 backend fanout

#### 预聚合视图

可选形态：

- PostgreSQL view
- PostgreSQL materialized view
- 后台 job 产出的聚合表

适用场景：

- `5m/15m/30m/60m` 请求量持续很高
- 同一批热门 ticker 被大量重复读取
- `1W/1M/1Q` 与指标计算开始成为热点

引入原则：

- 仍以 `1m/1d` 为 canonical source
- 预聚合层只作为性能优化层，不作为新的事实源
- 任何预聚合都必须可重建

#### Hot Cache

可选形态：

- Redis 短 TTL bars cache
- ticker + resolution + session + adjustment 维度的缓存键

适用场景：

- 高频访问的单 ticker 详情图
- 同一个 open session 中重复读取相近区间

### 18.7 演进决策信号

当出现以下信号时，说明该从 MVP 架构演进到更重的 product-level 架构：

- `1W/1M/1Q` 查询明显成为热点
- bars 请求的 P95 / P99 延迟持续偏高
- 同一 ticker 在短时间内被大量重复读取
- polling 对 backend / provider 成本开始不可接受
- 后端开始承担指标、筛选、告警等更多复用计算

### 18.8 Refresh Strategy

本节是 bars 刷新、初始化与清理机制的 **source of truth**。

本期采用 **后台单写入源** 方案：

```text
background jobs
  -> bootstrap ticker history
  -> refresh current-day 1m
  -> finalize completed 1D
  -> reconcile historical gaps
  -> cleanup expired 1m

request path
  -> DB only
```

### 18.8.1 目标

本策略要同时满足：

- 请求路径保持简单，避免把 provider 变成在线依赖
- 当前 chart 在 `1m` polling 下有稳定可用的数据
- 历史数据能通过后台补数逐步趋于完整
- `1m` canonical 存储量保持可控

### 18.8.2 职责分工

```text
background jobs
  -> own all Massive access
  -> write canonical 1m/1d
  -> maintain data freshness and completeness

request path
  -> read DB
  -> aggregate
  -> fill
  -> return
```

职责边界：

- 后台任务负责“把库维持在可查询状态”
- 请求路径不承担 provider fallback、repair、重试职责

### 18.8.3 后台任务类型

本期定义 5 类后台任务。

#### A. Ticker Bootstrap Job

用途：

- 服务首次上线时初始化已跟踪 ticker 的 bars
- 用户新增 ticker 后，异步初始化该 ticker 的基础历史

建议流程：

```text
ticker discovered
  -> enqueue bootstrap
  -> fetch recent 1d history
  -> fetch current-day 1m if applicable
  -> upsert canonical rows
  -> mark ticker ready
```

MVP 建议：

- `1d`
  - 回填最近 `10 years`
- `1m`
  - 只回填当前 trading day

#### A1. Ticker Bars State Model

为避免 bootstrap / refresh / finalizer / reconciler 之间的职责漂移，本期建议增加 ticker 级 bars 状态表。

建议表名：

- `market_ticker_bars_state`

建议字段：

- `ticker`
- `status`
  - `pending`
  - `initializing`
  - `ready`
  - `degraded`
  - `failed`
- `bootstrap_requested_at`
- `bootstrap_started_at`
- `bootstrap_finished_at`
- `bootstrap_failed_at`
- `last_reconciled_at`
- `last_1m_trading_day`
- `last_1m_bucket_start_at`
- `earliest_1d_trading_day`
- `latest_1d_trading_day`
- `last_error_code`
- `last_error_message`
- `created_at`
- `updated_at`

设计目的：

- 明确某个 ticker 的 bars 是否已可查询
- 明确 bootstrap 是否中断
- 给 startup reconciliation 提供判定依据
- 给 frontend 暴露 `readiness` 状态提供基础

最小状态流转：

```text
pending
  -> initializing
  -> ready

pending
  -> initializing
  -> failed

ready
  -> degraded
  -> ready
```

实现约束：

- state 的 owner 是 `ticker`，不是 user
- 同一个 ticker 全局只初始化一次
- 所有后台任务都只能通过同一个 ticker state 入口更新状态
- fresh `initializing` 表示已有 bootstrap 在执行，普通周期任务不能重复接管
- `initializing` 只有超过初始化超时窗口后，才能由 startup / historical reconciliation 恢复
- ticker bootstrap 周期扫描也必须检测超时 `initializing`，先标记为 `failed` 再纳入本轮重试

#### B. Current-Day `1m` Refresher

用途：

- 在交易时段内持续刷新当前 trading day 的 `1m` canonical

运行时段：

- `pre_market`
- `regular`
- `after_hours`

建议频率：

- 每 `60s`

处理对象：

- 已 bootstrap 完成的 ticker 集合
- MVP 先定义为 `watchlist_items` 的全局 `distinct ticker`

单轮执行流程：

```text
select tracked tickers
  -> fetch recent minute window from Massive
  -> normalize
  -> upsert 1m canonical
  -> record success / failure / lag
```

实现约束：

- 不必每轮重拉整天
- 优先拉最近小窗口并允许覆盖 mutable tail

#### C. Post-Close Finalizer

用途：

- 在 `regular` 结束后，把当日 final `1D` 写入 `market_bars_1d`
- 对当日 `1m` 再做一次收尾补齐

触发时机：

- regular close 之后的安全延迟窗口
- 建议：close 后 `2-5` 分钟启动首轮

执行流程：

```text
for each tracked ticker
  -> skip ticker unless state is ready/degraded
  -> fetch current-day regular 1m from Massive
  -> upsert 1m canonical
  -> aggregate final regular 1D
  -> upsert market_bars_1d
```

说明：

- `1d canonical` 不在盘中持续更新
- 只有 close 后 finalizer 才负责把当日 final `1D` 固化

#### D. Historical Gap Reconciler

用途：

- 异步补 regular 历史 `1m` / `1d` gaps
- 不阻塞用户当前请求

建议频率：

- 低频运行即可
- 如每小时、每晚、或运维手动触发

处理优先级：

- 先基于交易日历生成 expected regular `1m` buckets 与 completed regular `1d` days
- 对照 DB 已有 canonical rows
- 只向 Massive 请求缺失的连续 gap ranges
- fresh `initializing` ticker 不参与本轮 reconciliation
- timed-out `initializing` ticker 可交给 bootstrap 恢复

执行流程：

```text
for each ready tracked ticker
  -> list existing regular 1m rows in retained window
  -> list existing completed 1d rows in recent daily window
  -> compute missing minute/day ranges
  -> fetch only missing ranges from Massive
  -> upsert returned provider truth
```

说明：

- historical reconciler 不处理 `pre_market` / `after_hours`
- extended-hours current tail 由 current-day refresher 维护，并由 session-aware retention 控制保留范围
- 可通过 Celery 手动触发：
  - `PYTHONPATH=src poetry run celery -A worker.celery_app call worker.tasks.bar_refresh.run_historical_bars_gap_reconciliation`
- `historical gap reconciler` 与 `startup reconciliation` 在概念上分属两个场景：
  - `startup reconciliation`
    - 冷启动恢复
  - `historical gap reconciler`
    - 稳态周期补漏
- 但实现上 **不要求两套完全独立的扫描逻辑**
- 推荐做法是复用同一个 `reconcile engine`，只区分：
  - `trigger_mode=startup`
  - `trigger_mode=periodic`
- 差异主要体现在：
  - 触发时机不同
  - 扫描范围不同
  - 优先级不同

#### E. `1m` Retention Cleanup Job

用途：

- 删除超出保留窗口的 `1m` canonical rows
- 控制 minute 表规模

MVP 保留策略：

- `regular` session 保留最近 `10` 个 trading days 的 `1m`
- `pre_market` / `after_hours` 只保留最新 `1` 个 trading day 的 `1m`
- 只保留最近 `10` years 的 `1d`

执行规则：

```text
daily cleanup
  -> compute oldest retained trading day for regular 1m
  -> delete all 1m rows older than regular threshold
  -> compute latest retained trading day for extended-session 1m
  -> delete pre_market / after_hours rows older than extended threshold
  -> compute oldest retained day for 1d
  -> delete 1d rows older than threshold
```

写入规则：

```text
bootstrap / historical reconcile
  -> fetch retained 1m range from Massive
  -> keep historical regular rows
  -> keep extended-session rows only for latest retained trading day
  -> upsert 1m canonical
```

说明：

- MVP 中历史图表的主要 source of truth 是 `regular` session
- `pre_market` / `after_hours` 主要服务当天盘前异动、盘后反应、当前价格上下文
- 若未来产品需要历史 extended-hours overlay，应作为显式升级重新调整 retention 与查询语义

### 18.8.4 初始化策略

本期不依赖请求路径做首次回源。

初始化场景：

1. 服务启动后发现系统内已有 tracked tickers
   - 批量 enqueue bootstrap jobs
2. 用户新增 ticker
   - 写入 watchlist
   - 异步 enqueue bootstrap job

这意味着：

- 新 ticker 在 bootstrap 完成前，bars 接口可能返回空或 partial 结果
- frontend 需要接受“初始化中”的短暂状态

### 18.8.5 Startup Reconciliation

每次服务启动后，必须触发一轮 **异步 startup reconciliation**。

原因：

- bootstrap 可能在服务中断前只完成了一半
- current-day refresher 只维护最新 minute 数据，不能自动补回中间缺口
- post-close finalizer 可能因重启错过一次执行

startup reconciliation 的职责不是“全量重建”，而是：

- 识别中断中的 bootstrap
- 识别 current-day `1m` 缺口
- 识别 recent `1d` 缺失
- enqueue 后续 bootstrap / reconcile / finalize 任务

建议流程：

```text
service start
  -> load tracked tickers
  -> load market_ticker_bars_state
  -> classify ticker health

classify
  A. no state
     -> enqueue bootstrap
  B. initializing timeout
     -> mark degraded
     -> enqueue bootstrap resume
  C. ready but stale / incomplete current-day 1m
     -> enqueue current-day reconcile
  D. ready but recent 1d gap
     -> enqueue daily reconcile
  E. healthy
     -> no-op
```

启动校准必须是：

- **异步**
- **轻量**
- **面向最近窗口**

而不是阻塞式全量扫描。

推荐校验范围：

- `1m`
  - 当前 trading day
- `1d`
  - 最近 `30-90` 个 trading days

超出该范围的更老历史，交给低频 `historical gap reconciler`。

实现建议：

- `startup reconciliation` 与 `historical gap reconciler` 可以共用同一个 `reconcile engine`
- `startup` 模式：
  - 扫描范围更小
  - 优先级更高
  - 目标是尽快恢复服务健康
- `periodic` 模式：
  - 扫描范围更大
  - 频率更低
  - 目标是补齐长尾遗漏

#### `initializing` timeout 规则

若某个 ticker：

- `status=initializing`
- 且 `bootstrap_started_at` 距今超过阈值

则视为中断 bootstrap。

MVP 建议：

- timeout：`10 minutes`

超时后的处理：

```text
initializing timeout
  -> mark failed/degraded by recovery entrypoint
  -> bootstrap retry / reconciliation resume
```

这样可以避免 ticker 永远卡在 `initializing`。

### 18.8.6 Provider Fetch 分片规则

后台任务都必须遵守统一的 provider fetch 分片策略：

- 按 ticker chunk
- 按时间窗口 chunk
- 单次请求不追求覆盖过大区间

约束：

- current-day refresh 只拉最近小窗口 minute 数据
- post-close finalizer 只拉当前 trading day regular 相关区间
- historical reconciler 分 trading day 或小范围时间片补

### 18.8.7 失败与降级语义

后台刷新失败：

- 不直接让接口失败
- 记录日志与指标
- 等待下一轮刷新或后续重试

请求路径：

- 不主动 repair
- 若当前 DB 在请求左边界或已检测到的中间区间缺数据
  - 返回已知可用结果
  - `partial_range=true`
- 若只是 latest-tail 尚未刷新到最新 `anchor_time`
  - 返回当前 DB 中已知可用结果
  - MVP 阶段不要求 `partial_range=true`

建议在 `meta` 中增加：

- `readiness`
  - `pending|initializing|ready|degraded|failed`

这样 frontend 能区分：

- 数据尚未初始化
- 初始化中断，正在后台修复
- 数据已就绪但存在已知退化

### 18.8.8 观测指标

至少记录：

- `bars_refresh_job_duration_ms`
- `bars_refresh_job_ticker_count`
- `bars_refresh_job_failed_ticker_count`
- `bars_gap_detected_count`
- `bars_current_day_lag_seconds`
- `bars_bootstrap_job_duration_ms`
- `bars_bootstrap_failed_ticker_count`
- `bars_cleanup_deleted_row_count`
- `bars_cleanup_deleted_1d_row_count`
- `bars_startup_reconciliation_duration_ms`
- `bars_startup_reconciliation_enqueued_ticker_count`
- `bars_partial_range_response_count`

### 18.8.9 为什么 MVP 选择后台单写入源

- 系统复杂度明显更低
- 避免 request repair 与后台 refresh 的并发冲突
- provider 限流、失败重试、告警更容易统一治理
- `1m` 是最高 resolution，前端按分钟轮询可接受

### 18.8.10 MVP 推荐参数

本期默认建议如下：

- current-day `1m` refresher：
  - `60s`
- post-close finalizer：
  - close 后 `2-5` 分钟首轮
- historical reconciler：
  - 每天 `02:00 ET` 运行一次
  - 运行窗口位于 after-hours 结束与 pre-market 开始之间
- initializing timeout：
  - `10 minutes`
- regular `1m` retention：
  - 最近 `10` 个 trading days
- pre/after `1m` retention：
  - 最新 `1` 个 trading day
- `1d` retention：
  - 最近 `10` years

### 18.8.11 与未来实时链路的关系

- product-level 阶段可以引入 Massive WebSocket minute aggregates / trades
- backend 再向 frontend fanout 到 SSE / WebSocket
- 以实时增量更新 current tail，而不是完全依赖 polling

## 19. 测试要求

### 19.1 核心测试矩阵

至少覆盖：

- 周末 latest intraday fallback 到最近交易日
- 交易日 pre-open 时 regular intraday 为空
- 交易日 pre-open 时 pre_market intraday 可读
- half-day regular close 正确提前
- after_hours 从 half-day close 开始计算
- `1m -> 5m/15m/30m/60m` bucket anchor 正确
- `1d + current day stitch` 正确
- `1W/1M/1Q` 当前 bucket partial 正确
- bootstrap job 能正确初始化新 ticker 的 `1d/1m`
- background gap reconciliation 不破坏在线查询语义
- current-day refresher 能稳定覆盖 mutable tail，不需要请求路径 repair
- post-close finalizer 只在 completed regular-day 后写入 `1d`
- cleanup job 正确删除超过保留窗口的 `1m/1d`
- `fill=carry_forward` 正确生成 synthetic bars
- `fill=none` 正确保留 sparse 结果
- delayed mode 下 `effective_now` clamp 正确
- DST 切换周的 trading day / session classification 正确

### 19.2 回归测试重点

- 周 K / 月 K / 季度 K 的 bucket 边界
- current day 未开始、进行中、结束后的 `is_final` 切换
- regular 与 pre/after 不混 session
- `partial_range` 与 `calendar_shifted` 语义稳定
- `1d canonical` 只在 completed regular-day 后写入
- 当前 trading day `1m` mutable tail upsert 语义稳定
- refresh job 失败后，请求路径仍保持 DB-only 语义
- 同一 ticker 的 bootstrap / refresh / finalizer / cleanup 之间不会破坏 canonical 结果

## 20. 实施顺序

### 20.1 Now

本阶段建议直接完成：

- `GET /api/v1/market-data/bars` schema
- 交易日历 adapter
- `market_bars_1m` / `market_bars_1d` 表
- Massive bars client
- canonical upsert 统一入口
- ticker bootstrap job
- current-day background refresh / reconciliation
- post-close finalizer
- `1m/1d` retention cleanup job
- intraday latest mode + explicit range mode
- `1m/5m/15m/30m/60m/1D/1W/1M/1Q` 聚合
- carry-forward fill
- current day partial stitching

### 20.2 Next

后续再补：

- `raw` adjustment
- server-side indicators
- non-regular `1W/1M/1Q`
- SSE / stream delivery

## 21. 下一步

按本文件继续推进时，建议顺序如下：

1. 先落 API schema 和统一术语，再建表。
2. 先实现 `regular` intraday + `regular` day/week/month/quarter，再补 `pre_market` / `after_hours`。
3. 先用 automated tests 锁住 holiday / half-day / pre-open empty regular chart 这几个最容易漂的点。
