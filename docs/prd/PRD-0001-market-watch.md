# PRD-0001 — 股票行情 / 数据观察

> 状态：IN PROGRESS (2026-03-13)

## 0. 范围声明

- 本 PRD 当前仅覆盖 **美股股票（Stocks）**。
- 本 PRD 面向后续 `docs/backend-evolution/` 与 `docs/frontend-evolution/` 的拆分，不在这里展开复杂实现细节。
- Frontend 不直接访问 Massive；所有行情、鉴权、以及可选的数据更新能力均通过 Backend 暴露。
- Massive 的能力边界与计划差异参考 `docs/external-api-reference/massive-stocks-api-reference.md`。

## 1. 背景

我们要建设一个自用的 Web Trader Terminal，用于股票行情观察，MVP 先覆盖：

- 基础用户认证
- 用户级 watchlist 管理
- 快照行情展示（`last/change/change_pct/open/high/low/volume`）
- 历史 bars（day/minute）
- snapshots 持续刷新与可选增量更新（backend controlled refresh + fallback）

目标是先把“股票主线”做到稳定可用，再考虑后续扩展。

## 2. 目标与非目标

### 2.1 目标

- G1：用户可完成注册、登录，并维护与自己账户绑定的 watchlist。
- G2：用户可查看 watchlist 的批量 snapshot 行情，并感知当前数据延迟模式。
- G3：用户可按 ticker 查看历史 bars，并支持基础时间粒度切换。
- G4：系统具备持续更新能力；在不依赖 frontend 直连上游的前提下，页面可通过 polling 或 SSE 等方式更新，更新链路异常时核心页面仍可读。
- G5：前后端数据口径统一，关键错误码和关键失败路径可观测。

### 2.2 非目标

- N1：不包含期权等衍生品数据。
- N2：不包含下单交易能力。
- N3：不包含告警编排与通知系统。
- N4：不包含邮箱验证、忘记密码、第三方登录、复杂权限体系。
- N5：不在本 PRD 中定义 bars 的底层聚合、补齐、拼接、固化细节；该部分由单独 backend evolution 文档展开。
- N6：不在本期引入 quote-dependent 的高级能力；MVP 仅依赖 Developer/Advanced 共同支持的 Massive 能力。

## 3. 核心产品原则

### 3.1 鉴权与账户

- MVP 包含基础 Auth。
- 初期 Auth 使用简单的 JWT token 体系。
- 仅支持邮箱注册与密码登录；注册时暂不要求邮箱验证。
- watchlist、用户偏好等数据均与用户账户绑定。

### 3.2 市场数据模式

- Massive 的上游 plan差异通过项目配置抽象，不直接暴露给前端。
- MVP 只使用 Developer 与 Advanced 都支持的 Massive 接口能力。
- 系统通过统一配置声明当前数据延迟模式，建议命名为 `delay_minutes`，MVP 支持：
  - `0`：实时模式
  - `15`：15 分钟延迟模式
- Frontend 通过 Backend 提供的能力/配置接口获取当前模式，不自行推断。
- 本期不引入 quote-dependent 字段或功能作为必需能力。

### 3.3 数据访问边界

- Frontend 仅面向 Backend API；如后续需要增量更新，也只面向 Backend 暴露的统一更新通道，不与 Massive 直接交互。
- Backend 是唯一的数据编排与归一化入口。
- 对历史 bars 的默认读取流程为：`frontend -> backend -> database`；API 请求路径只读数据库，不在请求中主动回源 Massive。
- bars 的 Massive 回源、初始化、当前交易日刷新、历史缺口修复、收盘固化与清理由 backend 后台任务负责；若本地数据暂缺，API 返回当前已知可用数据，并通过 `readiness` / `X-Partial-Range` 表达准备状态或区间不完整。
- 对 snapshots 的共享拉取、请求合并、缓存/预热、以及后续如需增量更新时的分发与 fallback 策略均由 backend 负责。

## 4. 用户场景

1. 用户完成注册并登录后进入 `/terminal`，看到自己的 watchlist、当前数据模式，以及快照新鲜度或更新时间。
2. 用户新增 `AAPL`、`NVDA` 等 ticker，列表显示最新快照。
3. 用户刷新页面后，watchlist 仍然存在，因为其已与用户账户持久化绑定。
4. 用户点击某个 ticker 查看 bars，并切换 `1m/5m/15m/60m/day/week/month` 等基础时间粒度。
5. 页面通过 snapshots 刷新或可选增量更新机制持续更新；当更新链路异常时，前端进入降级状态并通过 backend fallback 维持可读。

## 5. 统一领域口径

### 5.1 Snapshot 字段定义

- `last`：最新成交价；若当前时刻无新成交，则使用最近可用成交价。
- `change`：`last - prev_close`。
- `change_pct`：`change / prev_close`。
- `open`：当前交易日开盘价。
- `high`：当前交易日最高价。
- `low`：当前交易日最低价。
- `volume`：当前交易日累计成交量。
- `prev_close`：上一交易日收盘价。
- `market_status`：市场状态，MVP 统一为 `pre_market | regular | after_hours | closed`；该字段只描述 snapshot 当前市场状态，不表示 bars 支持盘前/盘后数据。
- `delay_minutes`：当前环境配置的统一延迟分钟数，MVP 仅支持 `0` 或 `15`。
- `is_realtime`：当 `delay_minutes == 0` 时为 `true`。
- `provider_updated_at`：上游行情提供方返回的该条 snapshot 数据时间，不表示 backend 缓存写入时间。

### 5.2 Watchlist 默认规则

- ticker 做格式校验并统一转为大写。
- 同一用户下 ticker 去重。
- watchlist 持久化存储。
- MVP 默认按创建顺序展示。
- 首次进入页面时默认选中第一支股票。
- 删除当前选中项后，自动选中删除后列表中的第一项；若列表为空则进入 empty state。
- MVP 不做拖拽排序、分组、共享 watchlist。

## 6. 功能需求（MVP）

### F1：Auth

- 支持邮箱注册。
- 支持邮箱 + 密码登录。
- 登录成功后由 backend 签发 JWT token。
- watchlist、market data、以及可选更新接口均为受保护接口。

### F2：Watchlist

- 支持新增/删除/查询 ticker。
- watchlist 与用户账户绑定。
- 返回的 ticker 列表需满足去重、统一大写、稳定排序的默认规则。

### F3：Market Snapshots

- 支持按 tickers 批量拉取快照。
- 支持交易时段与非交易时段展示（`market_status`）。
- 返回统一字段口径，不直接透传上游 Massive 原始结构。
- 响应中应包含当前数据延迟模式信息，供前端展示。

### F4：Market Bars

- 提供 `GET /api/v1/market-data/bars`。
- 最小查询维度为单个 `ticker`。
- 前端面向统一参数模型，不直接暴露 Massive 原始 `timespan` / `multiplier` 风格参数。
- bars 接口至少支持：
  - `resolution`
  - `session`
  - `from`
  - `to`
  - `count_back`
  - `adjustment`
  - `fill`
  - `include_partial`
- `resolution` 至少支持：
  - `1m`
  - `5m`
  - `15m`
  - `30m`
  - `60m`
  - `1D`
  - `1W`
  - `1M`
- `session` 在 MVP 仅支持：
  - `regular`
- 当前阶段不查询、不持久化、不展示 `pre_market` / `after_hours` bars；snapshot 仍可展示当前市场状态。
- bars 查询只读取数据库；数据库 miss 不在请求路径回源 Massive。
- bars 存储层以 `1m` 与 `1d` 为 canonical source；其它 resolution 由 backend 聚合。
- MVP bars 价格口径固定为 `split_adjusted`；未复权 `raw` 价格不作为当前产品需求。
- `1d` canonical 只保存 completed regular-day bars；当前未完成的 `1D / 1W / 1M` 最后一根可由 `1m` 动态拼接。
- 对当前交易日的 mutable tail，backend 通过后台 refresh 任务回源 Massive 并 upsert `1m` canonical。
- Massive provider truth 可能是 sparse 的；backend 需要支持可选的 fill 策略供图表连续显示。
- 返回 `X-Data-Source` 与 `X-Partial-Range`，用于前端可视化数据来源与范围截断。
- bars 的实时拼接、最终固化、以及与未来增量更新机制的精细协同逻辑不在本 PRD 细化，由单独 backend evolution 文档定义。

### F5：Incremental Update Delivery

- G2 不要求 WebSocket。
- Backend 可根据实现复杂度与收益选择：
  - 继续使用 snapshots REST + polling
  - 或在后续阶段提供 SSE 作为单向增量更新通道
- Frontend 只消费 backend 定义的统一数据更新语义，不感知 Massive 原始事件类型。
- 当增量更新通道不可用时，frontend 必须能回退到 snapshots REST，保证核心页面继续可读。

## 7. 非功能需求

- 安全：Massive API Key 不暴露到前端；受保护 REST API 与可选更新通道必须鉴权。
- 可用性：更新链路异常时自动降级，核心页面仍可读。
- 性能：watchlist 批量快照请求支持最多 50 个 ticker。
- 一致性：前端只依赖 backend 的统一字段口径和错误模型。
- 可观测性：关键失败路径需要有统一错误码、日志或事件记录。
- 质量：后端边界检查与测试、前端 lint/test/build 全部通过。
- 配置：backend 需通过单一配置声明当前 `delay_minutes`，frontend 通过 backend 获取该值并展示。

## 8. 验收标准（DoD）

- [ ] 用户可完成邮箱注册与密码登录；登录成功后可拿到 JWT token。
- [ ] 未登录访问 watchlist、market data、以及可选更新接口等受保护接口时，返回统一鉴权错误。
- [ ] 用户可完成 watchlist 的增删查；同一用户下 ticker 去重、统一大写、刷新后仍持久化存在。
- [ ] snapshots 接口可按最多 50 个 ticker 批量返回统一口径的股票快照，并在前端正确渲染。
- [ ] snapshots 或能力配置接口可让前端感知当前 `delay_minutes` / realtime 模式。
- [ ] bars 接口可按 ticker 与时间区间稳定返回数据库中的历史数据；数据库 miss 不在请求路径回源，缺失数据由后台任务初始化、刷新或修复。
- [ ] bars 接口返回的数据来源与部分区间状态可被前端感知。
- [ ] 页面在 G2 阶段可通过 snapshots 持续刷新保持可读；若后续启用增量更新通道，该通道异常时前端可自动降级且核心页面可继续读取。
- [ ] 前后端错误码与错误语义一致，关键失败路径可追踪。

## 9. 里程碑

1. M1：Auth + Watchlist + snapshots 稳定可用。
2. M2：bars 查询链路、后台回源/回写与前端详情图表稳定可用。
3. M3：持续更新、降级与恢复闭环完成（实现方式可为 polling 或 SSE）。

## 10. 风险

- Massive 上游限流、配额策略与实际延迟模式需要持续验证。
- snapshots 刷新频率、共享拉取策略与 Massive 限流/配额之间需要持续验证。
- 交易日、节假日、盘前盘后边界需要通过自动化测试守护。
- bars 的缓存、固化、补齐与流式拼接策略复杂度较高，需要在单独 backend evolution 中提前收敛。
