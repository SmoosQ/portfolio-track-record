# Portfolio Track Record

[![Update Trading Performance](https://github.com/SmoosQ/portfolio-track-record/actions/workflows/update_performance.yml/badge.svg)](https://github.com/SmoosQ/portfolio-track-record/actions/workflows/update_performance.yml)

A privacy-preserving, automatically refreshed view of live `USDC` USD-M Futures performance from **2026-07-01 00:00 UTC**. This repository is designed for interview and professional evaluation.

GitHub Actions uses Binance read-only endpoints to retrieve daily income history, calculate daily PnL and risk metrics, and update the public charts. No fabricated PnL data is committed.

## Latest performance

The images appear after the first successful authenticated workflow run.

![Normalized USDC equity curve](reports/normalized_equity_curve.png)

![Cumulative USDC PnL](reports/cumulative_pnl_curve.png)

![USDC drawdown curve](reports/drawdown_curve.png)

Additional outputs:

- [Daily returns](reports/daily_returns.png)
- [Monthly returns](reports/monthly_returns.png)
- [Performance summary](reports/performance_summary.md)
- [Normalized daily data](data/processed/normalized_daily_equity.csv)

## Security model

- Credentials are read only from `BINANCE_API_KEY` and `BINANCE_API_SECRET`.
- GitHub Actions injects them from Repository Secrets only into the report step.
- The client exposes two signed `GET` operations: USD-M Futures account information and income history.
- There is no order, cancellation, deposit, withdrawal, or transfer operation in the code.
- The program never logs credentials, signatures, query strings, or authentication headers.
- Missing credentials stop execution with a non-zero status.
- Absolute account equity and account identifiers are never published. The equity curve starts at `1.0`.

Use a dedicated Binance key with read permission only. Do **not** enable Spot trading, Futures trading, withdrawals, or transfers.

## Performance scope

Only income rows whose asset is exactly `USDC` are included. Every observation is assigned to a UTC calendar day.

| Component | Treatment |
|---|---|
| `REALIZED_PNL` | Included in daily PnL |
| `COMMISSION` | Included in daily PnL, normally negative |
| `FUNDING_FEE` | Included in daily PnL with its Binance sign |
| `TRANSFER` | Used in memory to adjust the return capital base; excluded from PnL and not published as a transfer record |
| Other income types | Conservatively treated as capital adjustments and disclosed as a non-sensitive warning |
| Unrealized PnL | Not included in this realized daily performance report |

The public CSV contains daily returns, normalized equity, drawdown, daily realized PnL, commission, funding, net PnL, and trade count. It never contains the account balance, API metadata, UID, email, wallet address, or transaction hash.

## GitHub setup and first run

The repository expects these two **Repository Secrets**, which are never committed:

- `BINANCE_API_KEY`
- `BINANCE_API_SECRET`

To test the first run:

1. Open **Actions** on GitHub.
2. Select **Update Trading Performance**.
3. Click **Run workflow** and select `main`.
4. Confirm the run generates all report files and creates a `chore: update trading performance` commit.
5. Review the charts and metric definitions before sharing the repository.

The workflow runs:

- manually through `workflow_dispatch`;
- whenever `src/**`, `requirements.txt`, or the workflow file is pushed to `main`;
- every day at `00:00 UTC` as a fallback.

It uses `github-actions[bot]` for report commits and does not create an empty commit. If it cannot push, check **Settings → Actions → General → Workflow permissions** and allow read and write permissions.

## Daily metric definitions

Crypto markets trade continuously, so annualization uses `365` days.

| Metric | Definition |
|---|---|
| Daily net PnL | Daily USDC realized PnL + commission + funding fee |
| Daily return | Daily net PnL divided by reconstructed starting USDC capital; positive same-day transfers are conservatively added to the denominator |
| Normalized equity | Cumulative product of `(1 + daily return)`, starting at `1.0` |
| Cumulative return | Final normalized equity minus `1.0` |
| Annualized return | Geometric cumulative return raised to `365 / valid daily observations`, minus one |
| Annualized volatility | Sample standard deviation of daily returns multiplied by `sqrt(365)` |
| Sharpe ratio | Mean daily return divided by sample daily volatility, multiplied by `sqrt(365)`; risk-free rate is zero |
| Sortino ratio | Mean daily return divided by sample downside deviation, multiplied by `sqrt(365)`; target return is zero |
| Maximum drawdown | Largest percentage decline from a prior normalized-equity peak |
| Calmar ratio | Annualized return divided by the absolute maximum drawdown |
| Win rate | Positive net-PnL days divided by non-zero net-PnL days |
| Profit factor | Sum of positive daily net PnL divided by the absolute sum of negative daily net PnL |

Zero denominators, insufficient samples, missing rows, and invalid reconstructed capital bases return `null` or are explicitly excluded; they never become infinity or a made-up value.

## API retention and historical continuity

Binance's standard USD-M Futures income endpoint currently exposes only the latest three months. The workflow requests data in seven-day windows and paginates every window. While July 2026 remains available, the first run establishes the full inception history. Later runs preserve already verified daily rows that have aged out of the API window, overwrite all overlapping days with fresh Binance results, and recompute the entire normalized curve and risk metrics. This makes repeated runs idempotent without duplicating records.

## Local execution

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
python -m src.generate_report
```

## Limitations

- The track record begins on 2026-07-01 and covers USDC USD-M Futures only.
- Daily flow timing is approximated because only event timestamps and daily aggregation are available. Positive same-day transfers are added to the denominator to avoid overstating returns.
- The curve is realized-return based. Current unrealized PnL is separate.
- If the account uses multi-asset collateral, the USDC asset row may not capture economic exposure caused by price changes in other collateral assets.
- The first successful workflow run must occur before July rows age out of Binance's standard income-history retention window.

This repository is for interviews and professional evaluation only. It is not investment advice, a solicitation, or a guarantee of future performance.
