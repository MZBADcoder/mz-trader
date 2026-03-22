# Massive Stocks API Reference

Last verified: 2026-03-08

## Purpose

This document is the stock data integration reference for this repository.

It is intended to:

- provide one official reference baseline before implementation starts
- cover the Massive stocks REST and WebSocket surfaces from the official docs, not only what the legacy project happened to call
- document permission expectations only for the plans we care about: `Stocks Developer` and `Stocks Advanced`
- give backend and frontend a shared capability model for environment-based feature gating

## Source Policy

This document is based on:

- Massive official documentation
- Massive official pricing information
- the official Python package version imported by the legacy project

This document is not limited by the legacy application's actual call paths.

Legacy is used here only for SDK baseline and compatibility context:

- package name: `massive`
- locked version in legacy: `2.2.0`
- legacy dependency files:
  - `/Users/mz/pmf/trader-helper/backend/pyproject.toml`
  - `/Users/mz/pmf/trader-helper/backend/poetry.lock`

## Official Sources

- REST stocks index: [Massive REST docs](https://massive.com/docs/rest/llms.txt)
- WebSocket stocks index: [Massive WebSocket docs](https://massive.com/docs/websocket/llms.txt)
- Pricing: [Massive Stocks pricing](https://massive.com/pricing?product=stocks)

Key endpoint docs referenced while writing this file:

- [Stocks Custom Bars](https://massive.com/docs/rest/stocks/aggregates/custom-bars)
- [Stocks Full Market Snapshot](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot)
- [Stocks Single Ticker Snapshot](https://massive.com/docs/rest/stocks/snapshots/single-ticker-snapshot)
- [Stocks Market Holidays](https://massive.com/docs/rest/stocks/market-operations/market-holidays)
- [Stocks Market Status](https://massive.com/docs/rest/stocks/market-operations/market-status)
- [Stocks Last Quote](https://massive.com/docs/rest/stocks/trades-quotes/last-quote)
- [Stocks Last Trade](https://massive.com/docs/rest/stocks/trades-quotes/last-trade)
- [Stocks Quotes](https://massive.com/docs/rest/stocks/trades-quotes/quotes)
- [Stocks Trades](https://massive.com/docs/rest/stocks/trades-quotes/trades)
- [WS Quotes](https://massive.com/docs/websocket/stocks/quotes)
- [WS Trades](https://massive.com/docs/websocket/stocks/trades)
- [WS Aggregates Per Minute](https://massive.com/docs/websocket/stocks/aggregates-per-minute)
- [WS Aggregates Per Second](https://massive.com/docs/websocket/stocks/aggregates-per-second)
- [WS Fair Market Value](https://massive.com/docs/websocket/stocks/fair-market-value)
- [WS NOI](https://massive.com/docs/websocket/stocks/imbalances)
- [WS LULD](https://massive.com/docs/websocket/stocks/luld)

## Plan Scope

Only these two stock plans matter for this repository:

- `developer`
- `advanced`

Everything else is intentionally out of scope.

## Recommended Environment Variables

These are project conventions:

- `MASSIVE_API_KEY`
- `MASSIVE_STOCK_PLAN=developer|advanced`

Recommended derived flags:

- `massive_has_realtime`
- `massive_has_quotes`
- `massive_has_trades`
- `massive_has_snapshots`
- `massive_has_second_aggs`
- `massive_has_ws_quotes`
- `massive_has_ws_trades`
- `massive_has_ws_minute_aggs`
- `massive_has_ws_second_aggs`

Recommended defaults:

| Plan | snapshots | quotes | trades | second aggs | ws minute aggs | ws second aggs | ws trades | ws quotes | latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| developer | yes | no | yes | yes | yes | yes | yes | no | 15-minute delayed |
| advanced | yes | yes | yes | yes | yes | yes | yes | yes | real-time |

Basis:

- from the official stocks pricing page feature grid
- from snapshot docs saying quote and trade sections appear only if the plan includes them

## Plan Permission Summary

This section captures only what is relevant to `developer` and `advanced`.

### Clearly Included In Both Developer And Advanced

- REST aggregate bars
- REST snapshots
- REST trades
- REST last trade
- REST market status
- REST market holidays
- REST reference-data style endpoints such as tickers, exchanges, condition codes
- WebSocket minute aggregates
- WebSocket second aggregates
- WebSocket trades

### Advanced Only

- REST quote-bearing snapshot fields
- REST last quote
- REST historical quotes
- WebSocket quotes
- real-time stock feed instead of 15-minute delayed stock feed
- financials and ratios, according to the pricing page feature grid

### Requires Separate Verification Or Separate Entitlement

- WebSocket FMV
  - official doc says Business plan only
- WebSocket NOI
  - pricing page exposes a separate NYSE Order Imbalances product
- WebSocket LULD
  - stock docs exist, but the public pricing grid does not clearly map this feed to Developer or Advanced
- filings endpoints
  - official docs exist, but public pricing grid does not clearly map them to Developer or Advanced
- news endpoint
  - official docs exist, but public pricing grid does not clearly map it to Developer or Advanced

## Stocks REST Catalog

The list below follows the official Massive REST stocks index. The `Permission` column is intentionally conservative:

- `Developer` means the pricing/docs combination gives a strong basis for Developer access
- `Advanced` means clearly available but we should assume Advanced if quotes or real-time are involved
- `Verify` means docs exist but the public pricing grid does not clearly disclose plan entitlement

| Group | Endpoint / Doc | Permission | Notes |
| --- | --- | --- | --- |
| Aggregates | Custom Bars | Developer | historical OHLC range endpoint |
| Aggregates | Daily Market Summary | Developer | daily market-wide OHLC summary |
| Aggregates | Daily Ticker Summary | Developer | single-day ticker OHLC summary |
| Aggregates | Previous Day Bar | Developer | previous trading day OHLC |
| Corporate Actions | Dividends | Developer | pricing page shows corporate actions on Developer and Advanced |
| Corporate Actions | IPOs | Verify | official docs exist; pricing grid does not explicitly list IPOs |
| Corporate Actions | Splits | Developer | pricing page shows corporate actions on Developer and Advanced |
| Corporate Actions | Ticker Events | Verify | official docs exist; pricing grid does not explicitly list ticker events |
| Filings | 10-K Sections | Verify | official docs exist; entitlement not explicit in pricing grid |
| Filings | 8-K Text | Verify | official docs exist; entitlement not explicit in pricing grid |
| Filings | SEC EDGAR Index | Verify | official docs exist; entitlement not explicit in pricing grid |
| Filings | Risk Categories | Verify | official docs exist; entitlement not explicit in pricing grid |
| Filings | Risk Factors | Verify | official docs exist; entitlement not explicit in pricing grid |
| Fundamentals | Balance Sheets | Advanced | pricing page explicitly mentions financials and ratios on Advanced |
| Fundamentals | Cash Flow Statements | Advanced | same basis as above |
| Fundamentals | Float | Verify | docs exist; not explicit in pricing grid |
| Fundamentals | Income Statements | Advanced | same basis as above |
| Fundamentals | Ratios | Advanced | pricing page explicitly mentions financials and ratios on Advanced |
| Fundamentals | Short Interest | Verify | docs exist; not explicit in pricing grid |
| Fundamentals | Short Volume | Verify | docs exist; not explicit in pricing grid |
| Market Operations | Condition Codes | Developer | fits reference-data capability |
| Market Operations | Exchanges | Developer | fits reference-data capability |
| Market Operations | Market Holidays | Developer | used as reference-data style endpoint |
| Market Operations | Market Status | Developer | used as reference-data style endpoint |
| News | News | Verify | docs exist; pricing grid does not explicitly map it |
| Snapshots | Full Market Snapshot | Developer | endpoint available at Starter+, therefore available for both target plans |
| Snapshots | Single Ticker Snapshot | Developer | same as above |
| Snapshots | Top Market Movers | Developer | snapshot family endpoint |
| Snapshots | Unified Snapshot | Verify | multi-asset endpoint; pricing mapping not explicit |
| Technical Indicators | EMA | Developer | pricing page lists technical indicators on Developer and Advanced |
| Technical Indicators | MACD | Developer | same basis |
| Technical Indicators | RSI | Developer | same basis |
| Technical Indicators | SMA | Developer | same basis |
| Tickers | All Tickers | Developer | fits reference-data capability |
| Tickers | Related Tickers | Verify | docs exist; pricing grid does not explicitly map it |
| Tickers | Ticker Overview | Developer | fits reference-data capability |
| Tickers | Ticker Types | Developer | fits reference-data capability |
| Trades/Quotes | Last Quote | Advanced | quotes are Advanced-only in public pricing |
| Trades/Quotes | Last Trade | Developer | trades are available on Developer and Advanced |
| Trades/Quotes | Quotes | Advanced | quotes are Advanced-only in public pricing |
| Trades/Quotes | Trades | Developer | trades are available on Developer and Advanced |

## REST Endpoints Most Likely To Matter First

Even though this document covers the full official stocks catalog, the following endpoints are the most likely first implementation targets for trading UI and market data services:

### Market Data Core

- `GET /v2/aggs/ticker/{stocksTicker}/range/{multiplier}/{timespan}/{from}/{to}`
- `GET /v2/snapshot/locale/us/markets/stocks/tickers`
- `GET /v2/snapshot/locale/us/markets/stocks/tickers/{stocksTicker}`
- `GET /v2/last/trade/{stocksTicker}`
- `GET /v3/trades/{stockTicker}`

### Quote-Specific, Advanced Only

- `GET /v2/last/nbbo/{stocksTicker}`
- `GET /v3/quotes/{stockTicker}`

### Market Calendar And State

- `GET /v1/marketstatus/now`
- `GET /v1/marketstatus/upcoming`

### Reference Data For Ticker Lookup

- `GET /v3/reference/tickers`
  - supports exact ticker lookup
  - supports `search` against ticker and/or company name
  - can be used for:
    - validating whether a ticker exists before adding it to a watchlist
    - powering frontend autocomplete such as `apple` -> `AAPL`
  - project guidance:
    - set `market=stocks`
    - prefer `active=true` for MVP watchlist flows
    - normalize the Massive response in backend instead of exposing it directly to frontend

## Stocks WebSocket Catalog

Official stocks WebSocket feeds currently listed in the public docs:

| Feed | Endpoint | Permission | Notes |
| --- | --- | --- | --- |
| Aggregates Per Minute | `WS /stocks/AM` | Developer | available because websocket minute aggregates exist on Developer |
| Aggregates Per Second | `WS /stocks/A` | Developer | available because websocket second aggregates exist on Developer |
| Fair Market Value | `WS /business/stocks/FMV` | Verify | official doc says Business plan users |
| Net Order Imbalance | `WS /stocks/NOI` | Verify | likely separate entitlement based on pricing page NOI product |
| Limit Up - Limit Down | `WS /stocks/LULD` | Verify | public pricing grid does not clearly map entitlement |
| Quotes | `WS /stocks/Q` | Advanced | quotes are Advanced-only in public pricing |
| Trades | `WS /stocks/T` | Developer | trades are available on Developer and Advanced |

## WebSocket Feeds Most Likely To Matter First

### Developer And Advanced Shared

- `WS /stocks/A`
- `WS /stocks/AM`
- `WS /stocks/T`

### Advanced Only

- `WS /stocks/Q`

## Snapshot Field-Level Plan Behavior

The snapshot docs explicitly state that some nested fields are conditional on plan entitlements.

### Full Market Snapshot

- Endpoint: `GET /v2/snapshot/locale/us/markets/stocks/tickers`

Field behavior:

- `tickers[].lastTrade` appears only if the current plan includes trades
- `tickers[].lastQuote` appears only if the current plan includes quotes

Project implication:

- on `developer`, snapshot responses should be expected to contain `lastTrade` but not `lastQuote`
- on `advanced`, both can be expected

### Single Ticker Snapshot

- Endpoint: `GET /v2/snapshot/locale/us/markets/stocks/tickers/{stocksTicker}`

Field behavior:

- `ticker.lastTrade` appears only if the current plan includes trades
- `ticker.lastQuote` appears only if the current plan includes quotes

Project implication:

- treat quote sections as optional unless `MASSIVE_STOCK_PLAN=advanced`

## Connection Notes For Stocks WebSocket

Official stock feeds live under:

- `wss://socket.massive.com/stocks`

Important event codes from the official docs:

- `A` second aggregate
- `AM` minute aggregate
- `T` trade
- `Q` quote
- `NOI` net order imbalance
- `LULD` limit up / limit down
- `FMV` fair market value on business feed

The public markdown export for the WebSocket quickstart is sparse, so the exact auth and subscribe payloads should be verified during implementation against a live sandbox or the latest interactive docs.

## SDK Baseline

The official Python package baseline imported by the legacy project is:

- package: `massive`
- version: `2.2.0`

Project guidance:

- use this as the first compatibility target when building the new integration layer
- do not assume the new repository must preserve the legacy wrapper API
- prefer a new adapter layer that maps the official SDK and official HTTP/WebSocket docs into this repository's own domain model

## Implementation Rules For This Repository

- gate every quote-dependent feature behind `MASSIVE_STOCK_PLAN=advanced`
- allow trade and aggregate features on both `developer` and `advanced`
- treat all `developer` market data as delayed
- treat `advanced` as real-time capable
- keep plan capability resolution centralized in one backend module
- expose the resolved capabilities to the frontend rather than recomputing them in multiple places
- do not make undocumented assumptions about FMV, NOI, LULD, filings, or news entitlements

## Open Verification Items

- exact entitlement for filings endpoints under public self-serve stock plans
- exact entitlement for the stock news endpoint
- whether `LULD` is bundled in Developer, Advanced, or a separate add-on
- current WebSocket auth and subscription payload shape in the live platform docs
- whether the `massive` Python SDK exposes all stock surfaces needed directly, or whether some endpoints should be called over raw HTTP instead of SDK convenience methods
