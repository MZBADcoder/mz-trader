# BE-0001 — Auth + Watchlist Backend Evolution

> 状态：Completed
> 关联 PRD：`docs/prd/PRD-0001-market-watch.md`
> 范围：覆盖账号体系、watchlist，以及为 watchlist 添加服务的 ticker search lookup；不包含 snapshot、bars、stream 的实现

## 1. 目标

本阶段交付 Backend 的最小可用基础能力：

- 用户可通过邮箱注册与密码登录
- Backend 可签发并校验 JWT token
- 受保护接口可识别当前用户
- 每个用户拥有一个默认 watchlist
- 用户可增删查 watchlist 中的 ticker
- 用户可通过 ticker/company name 搜索候选 ticker，用于 watchlist 添加交互
- watchlist 满足去重、统一大写、持久化等 PRD 规则
- 为后续 snapshot/bars/stream 提供稳定的用户与 watchlist 基础

本阶段重点是先把“身份 + 用户级股票列表”做稳定，不引入行情数据复杂度。

## 2. 非目标

- 不包含邮箱验证
- 不包含忘记密码/重置密码
- 不包含第三方登录
- 不包含 refresh token、多端会话管理、设备管理
- 不包含多 watchlist、分组、排序拖拽、共享
- 不包含 snapshot、bars、stream 的业务实现

## 3. MVP 业务约束

### 3.1 用户

- 用户以 `email` 唯一标识
- `email` 全局唯一，注册时统一转小写并去除前后空白
- 密码采用安全哈希存储，不保存明文
- MVP 不要求邮箱验证，注册成功即可登录

### 3.2 鉴权

- 采用 Bearer JWT
- Access token 由 backend 签发
- JWT 至少包含：
  - `sub`: 用户 ID
  - `email`: 用户邮箱
  - `exp`: 过期时间
  - `iat`: 签发时间
- 所有业务接口默认要求鉴权，登录/注册接口除外

### 3.3 Watchlist

- MVP 采用“每个用户一个隐式默认 watchlist”模型，不单独暴露 watchlist 集合管理接口
- ticker 存储与返回时统一转为大写
- 同一用户下 ticker 去重
- 默认按创建顺序返回
- 删除不存在的 ticker 返回明确业务错误
- 添加 ticker 前，backend 需要校验该 ticker 在 Massive 的股票 ticker search 数据来源中存在
- 为与后续 snapshot 批量接口对齐，MVP 限制单用户 watchlist 最多 `50` 个 ticker

## 4. API 设计

### 4.1 统一约定

- API 前缀：`/api/v1`
- 请求/响应均使用 JSON，下载型接口除外
- 受保护接口通过 `Authorization: Bearer <token>` 传递 JWT
- 成功响应默认使用 `2xx`
- 失败响应统一返回错误对象
- 前后端交互中默认不使用 `null`；若错误附加说明为空，返回空字符串

统一错误响应建议：

```json
{
  "error": {
    "code": "AUTH_INVALID_CREDENTIALS",
    "message": "Email or password is incorrect.",
    "detail": "",
    "request_id": "req_123"
  }
}
```

字段说明：

- `code`: 稳定错误码，前后端联调用
- `message`: 面向开发和 UI 的简短错误说明
- `detail`: 错误附加说明，固定为字符串；无额外说明时返回空字符串
- `request_id`: 用于日志追踪

### 4.2 Auth API

#### `POST /api/v1/auth/register`

用途：

- 创建用户账号
- 注册成功后可直接返回 access token，减少一次额外登录请求

请求体：

```json
{
  "email": "user@example.com",
  "password": "StrongPassword123"
}
```

成功响应：`201 Created`

```json
{
  "user": {
    "id": "usr_123",
    "email": "user@example.com"
  },
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

错误：

- `400` `VALIDATION_ERROR`
- `409` `AUTH_EMAIL_ALREADY_EXISTS`

#### `POST /api/v1/auth/login`

请求体：

```json
{
  "email": "user@example.com",
  "password": "StrongPassword123"
}
```

成功响应：`200 OK`

```json
{
  "user": {
    "id": "usr_123",
    "email": "user@example.com"
  },
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

错误：

- `400` `VALIDATION_ERROR`
- `401` `AUTH_INVALID_CREDENTIALS`

#### `GET /api/v1/auth/me`

用途：

- 返回当前登录用户基础信息，供 frontend 启动时恢复 session

成功响应：`200 OK`

```json
{
  "user": {
    "id": "usr_123",
    "email": "user@example.com"
  }
}
```

错误：

- `401` `AUTH_REQUIRED`
- `401` `AUTH_TOKEN_INVALID`
- `401` `AUTH_TOKEN_EXPIRED`

### 4.3 Watchlist API

#### `GET /api/v1/watchlist`

用途：

- 返回当前用户默认 watchlist 的 ticker 列表

成功响应：`200 OK`

```json
{
  "items": [
    {
      "ticker": "AAPL",
      "created_at": "2026-03-13T10:00:00Z"
    },
    {
      "ticker": "NVDA",
      "created_at": "2026-03-13T10:02:00Z"
    }
  ]
}
```

错误：

- `401` `AUTH_REQUIRED`
- `401` `AUTH_TOKEN_INVALID`
- `401` `AUTH_TOKEN_EXPIRED`

#### `POST /api/v1/watchlist/items`

用途：

- 向当前用户默认 watchlist 中添加 ticker

请求体：

```json
{
  "ticker": "aapl"
}
```

处理规则：

- 统一转为大写
- 校验 ticker 格式
- 通过 Massive ticker search 数据接口校验 ticker 存在性
- 若已存在则返回业务错误，不做静默成功

成功响应：`201 Created`

```json
{
  "item": {
    "ticker": "AAPL",
    "created_at": "2026-03-13T10:00:00Z"
  }
}
```

错误：

- `400` `VALIDATION_ERROR`
- `401` `AUTH_REQUIRED`
- `409` `WATCHLIST_TICKER_DUPLICATE`
- `422` `WATCHLIST_TICKER_INVALID`
- `422` `WATCHLIST_TICKER_NOT_SUPPORTED`
- `409` `WATCHLIST_LIMIT_EXCEEDED`

#### `DELETE /api/v1/watchlist/items/{ticker}`

用途：

- 删除当前用户默认 watchlist 中的 ticker

路径参数：

- `ticker`: 不区分大小写，backend 内部统一转大写后处理

成功响应：`204 No Content`

错误：

- `401` `AUTH_REQUIRED`
- `404` `WATCHLIST_TICKER_NOT_FOUND`

### 4.4 Ticker Search API

#### `GET /api/v1/ticker-search/search`

用途：

- 为 frontend 的 ticker 添加下拉菜单提供候选项
- 支持输入 ticker 或常见公司名，如 `apple`、`sandisk`

查询参数：

- `query`: 必填，用户输入的搜索词
- `limit`: 可选，默认 `10`，最大 `20`

后端行为：

- 通过 Massive `GET /v3/reference/tickers` 做 ticker search 查询
- 固定带上 `market=stocks`
- 建议固定带上 `active=true`
- 使用 Massive 官方支持的 `search` 参数，在 ticker 与公司名中检索
- backend 对 Massive 响应做裁剪与归一化，不直接透传原始结构

成功响应：`200 OK`

```json
{
  "items": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "primary_exchange": "XNAS",
      "type": "CS",
      "active": true
    }
  ]
}
```

错误：

- `400` `VALIDATION_ERROR`
- `401` `AUTH_REQUIRED`

说明：

- 基于 Massive 官方 `All Tickers` 文档，`GET /v3/reference/tickers` 支持 `search` 参数，可在 `ticker and/or company name` 中搜索，因此能够满足 MVP 的 ticker 推荐需求。
- 这个结论来自 Massive 官方文档：[All Tickers | Stocks REST API](https://massive.com/docs/rest/stocks/tickers/all-tickers)

## 5. 错误码设计

### 5.1 设计原则

- 错误码稳定，避免把数据库异常或第三方异常直接泄漏给前端
- HTTP 状态码表达大类语义，`error.code` 表达精确业务含义
- 同一错误码在 REST 与后续 WS 语义上尽量保持一致

### 5.2 错误码清单

| HTTP | Code | 场景 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 请求字段缺失、类型错误、格式错误 |
| 401 | `AUTH_REQUIRED` | 未提供 token |
| 401 | `AUTH_TOKEN_INVALID` | token 非法、签名错误、结构错误 |
| 401 | `AUTH_TOKEN_EXPIRED` | token 已过期 |
| 401 | `AUTH_INVALID_CREDENTIALS` | 登录邮箱或密码错误 |
| 409 | `AUTH_EMAIL_ALREADY_EXISTS` | 注册邮箱已存在 |
| 422 | `WATCHLIST_TICKER_INVALID` | ticker 不满足格式规则 |
| 422 | `WATCHLIST_TICKER_NOT_SUPPORTED` | ticker 格式合法，但 Massive 股票 ticker search 数据来源中不存在 |
| 409 | `WATCHLIST_TICKER_DUPLICATE` | 同一用户重复添加同一 ticker |
| 404 | `WATCHLIST_TICKER_NOT_FOUND` | 删除或查询不存在的 watchlist item |
| 409 | `WATCHLIST_LIMIT_EXCEEDED` | watchlist 超过数量上限 |
| 500 | `INTERNAL_ERROR` | 未分类服务端错误 |

### 5.3 ticker 格式规则

MVP 建议采用保守规则：

- 只允许英文字母、数字、`.`、`-`
- 长度 `1..15`
- 统一转大写后再校验和存储

说明：

- 该规则用于输入层校验
- 本阶段需要额外做“必须在 Massive 股票 reference 数据中存在”的在线校验
- 建议通过 Massive `GET /v3/reference/tickers` 做 exact ticker 校验，查询条件至少包含：
  - `market=stocks`
  - `ticker=<normalized_ticker>`
  - `active=true`
  - `limit=1`
- 后续如需增强 ticker search 数据能力，可在独立 evolution 中增强

## 6. 数据模型建议

### 6.1 表结构方向

建议最小落库模型：

- `users`
  - `id`
  - `email`
  - `password_hash`
  - `created_at`
  - `updated_at`

- `watchlist_items`
  - `id`
  - `user_id`
  - `ticker`
  - `created_at`

约束建议：

- `users.email` 唯一索引
- `watchlist_items (user_id, ticker)` 唯一索引
- `watchlist_items.user_id` 普通索引

说明：

- MVP 不单独创建 `watchlists` 表，避免过早引入“多列表”抽象
- 如果未来需要多个 watchlist，可再演进为 `watchlists + watchlist_items`

## 7. DDD 分层落点

遵循仓库中的 backend 分层约束：

- `api/`
  - 定义 auth/watchlist 路由
  - 请求 DTO / 响应 DTO
  - JWT 鉴权依赖注入
- `application/`
  - 注册用户
  - 用户登录
  - 获取当前用户
  - 获取 watchlist
  - 添加 watchlist item
  - 删除 watchlist item
- `domain/`
  - `User`
  - `WatchlistItem`
  - 领域校验与简单业务规则
- `infrastructure/`
  - 密码哈希
  - JWT 编解码
  - SQLAlchemy ORM / repository
  - Massive ticker search client

不引入接口层；通过具体类做依赖注入。

## 8. 测试设计

### 8.1 测试目标

- 确认 auth 核心流程可用
- 确认 watchlist 规则不漂移
- 确认 ticker search 查询与存在性校验可用
- 确认错误码与 HTTP 状态码稳定
- 为后续 snapshot/market-data 接口提供可靠用户上下文基础

### 8.2 测试层次

#### A. Domain / Application 单元测试

覆盖重点：

- email 标准化
- ticker 标准化与格式校验
- Massive ticker existence 校验
- 重复 ticker 拒绝
- watchlist 上限拒绝
- 注册重复邮箱拒绝
- 密码校验失败

#### B. API 集成测试

覆盖重点：

- 注册成功返回 token
- 注册重复邮箱返回 `409 AUTH_EMAIL_ALREADY_EXISTS`
- 登录成功返回 token
- 错误密码返回 `401 AUTH_INVALID_CREDENTIALS`
- 未带 token 请求 `/watchlist` 返回 `401 AUTH_REQUIRED`
- 非法 token 返回 `401 AUTH_TOKEN_INVALID`
- 过期 token 返回 `401 AUTH_TOKEN_EXPIRED`
- 添加 ticker 成功
- 重复添加 ticker 返回 `409 WATCHLIST_TICKER_DUPLICATE`
- 非法 ticker 返回 `422 WATCHLIST_TICKER_INVALID`
- Massive 不存在的 ticker 返回 `422 WATCHLIST_TICKER_NOT_SUPPORTED`
- 删除不存在 ticker 返回 `404 WATCHLIST_TICKER_NOT_FOUND`
- watchlist 返回顺序为创建顺序
- `ticker-search/search` 可按公司名返回候选 ticker
- API 集成测试默认连接临时 PostgreSQL Docker 容器，不依赖开发机常驻数据库

#### C. Repository / Persistence 测试

覆盖重点：

- `users.email` 唯一约束生效
- `watchlist_items (user_id, ticker)` 唯一约束生效
- 用户之间 watchlist 隔离
- 删除操作仅影响当前用户数据
- 测试环境在每个用例开始前重建 ORM schema，保证用例隔离

#### D. External Integration 测试

覆盖重点：

- Massive `reference/tickers` 搜索结果可映射为内部统一结构
- exact ticker 校验在上游存在 / 不存在两种情况下行为稳定
- 上游超时或异常时，不把 Massive 原始错误直接泄漏到前端

### 8.3 建议测试用例清单

1. 注册新用户后返回 user + token。
2. 同邮箱重复注册被拒绝。
3. 登录成功后可访问 `/api/v1/auth/me`。
4. 未登录访问 `/api/v1/watchlist` 被拒绝。
5. 用户 A 无法看到用户 B 的 watchlist。
6. 添加小写 ticker 后，返回值和落库值均为大写。
7. 同一 ticker 重复添加被拒绝。
8. 非法 ticker 字符串被拒绝。
9. 格式合法但 Massive 不存在的 ticker 被拒绝。
10. watchlist 满 50 后继续添加被拒绝。
11. 删除 ticker 后再次删除同一 ticker 返回 `WATCHLIST_TICKER_NOT_FOUND`。
12. `ticker-search/search?query=apple` 能返回 `AAPL` 等相关候选。

## 9. 可观测性设计

- 每个请求生成或透传 `request_id`
- 认证失败记录安全相关日志，但不记录明文密码
- 注册、登录、watchlist 变更记录基础审计日志
- Massive ticker 校验与搜索失败记录上游调用日志与 `request_id`
- 错误响应中返回 `request_id`，便于前后端联调

## 10. 交付定义

本阶段完成后，应满足：

- Backend 有可用的注册、登录、当前用户接口
- Backend 有可用的 watchlist 增删查接口
- Backend 有可用的 ticker search 接口
- 统一错误模型已落地
- 主要 auth/watchlist 场景已有自动化测试覆盖
- 后续 snapshot 能直接复用当前用户与 watchlist 基础

## 11. 开放问题

当前已确认的决策：

- JWT 过期时间需要通过环境配置暴露，默认 `24h`
- 注册成功时不自动创建种子 watchlist 项，由用户自行添加
- `/auth/register` 成功后直接签发 token，降低 frontend 启动复杂度
