# Performance Summary

Generated at: **2026-08-15T00:10:07Z**<br>
Coverage: **2026-07-01 to 2026-08-15 (UTC)**<br>
Scope: **Daily USDC USD-M Futures realized performance**

Absolute account values are not published. USD-M Futures transfers are excluded from trading return.
Sharpe and Sortino use private total daily returns including unrealized PnL; unrealized amounts and daily total returns are not published.

| Metric | Value |
|---|---:|
| Cumulative Return | 3.78% |
| Latest Daily Return | 0.00% |
| Annualized Return | 37.06% |
| Annualized Volatility | 1.29% |
| Sharpe Ratio | 6.283070 |
| Sortino Ratio | 11.254884 |
| Maximum Drawdown | -0.01% |
| Calmar Ratio | 4056.982186 |
| Win Rate | 97.37% |
| Profit Factor | 1536.827400 |
| Total Realized Pnl Usdc | 166.657999 |
| Total Commission Usdc | -0.075227 |
| Total Funding Fee Usdc | 1.670714 |
| Total Net Pnl Usdc | 168.253485 |
| Number Of Trading Days | 38 |
| Number Of Trades | 1179 |
| Valid Return Days | 43 |
| Excluded Return Days | 3 |
| Annualization Factor | 365 |

## Warnings and coverage notes

- Non-performance income types were treated as capital adjustments: COIN_SWAP_DEPOSIT
- 3 day(s) were excluded from ratios because the reconstructed capital base was invalid.
- Sharpe and Sortino include unrealized PnL and begin on 2026-07-06 because earlier official equity snapshots are unavailable.

## Definitions

- **Performance Scope**: Daily realized USDC USD-M Futures performance from 2026-07-01, using UTC day boundaries.
- **Daily Net Pnl**: USDC realized PnL + USDC commission + USDC funding fee for each UTC day.
- **Daily Return**: Daily net PnL divided by reconstructed starting USDC capital; positive same-day transfers are added to the denominator.
- **Cumulative Return**: Product of (1 + daily return) minus 1.
- **Annualized Return**: Geometric cumulative return annualized with 365 calendar days.
- **Annualized Volatility**: Sample standard deviation of daily returns multiplied by sqrt(365).
- **Sharpe Ratio**: Private total daily return including changes in unrealized PnL divided by sample daily standard deviation, multiplied by sqrt(365); only the ratio is published and the risk-free rate is 0.
- **Sortino Ratio**: Private total daily return including changes in unrealized PnL divided by sample downside deviation, multiplied by sqrt(365); only the ratio is published and the target return is 0.
- **Maximum Drawdown**: Largest decline from a prior peak in normalized equity.
- **Calmar Ratio**: Annualized return divided by the absolute maximum drawdown.
- **Win Rate**: Positive daily net-PnL days divided by non-zero daily net-PnL days.
- **Profit Factor**: Sum of positive daily net PnL divided by absolute negative daily net PnL.
- **Annualization Factor**: 365 calendar days because crypto markets trade continuously.

This report is for professional evaluation only and is not investment advice.
