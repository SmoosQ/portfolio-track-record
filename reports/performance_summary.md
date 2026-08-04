# Performance Summary

Generated at: **2026-08-04T05:57:04Z**<br>
Coverage: **2026-07-01 to 2026-08-04 (UTC)**<br>
Scope: **Daily USDC USD-M Futures realized performance**

Absolute account values are not published. USD-M Futures transfers are excluded from trading return.

| Metric | Value |
|---|---:|
| Cumulative Return | 2.68% |
| Latest Daily Return | 0.03% |
| Annualized Return | 35.26% |
| Annualized Volatility | 1.39% |
| Sharpe Ratio | 21.770745 |
| Sortino Ratio | 816.926741 |
| Maximum Drawdown | -0.01% |
| Calmar Ratio | 3218.675892 |
| Win Rate | 96.30% |
| Profit Factor | 1086.048870 |
| Total Realized Pnl Usdc | 117.225099 |
| Total Commission Usdc | -0.075227 |
| Total Funding Fee Usdc | 1.719771 |
| Total Net Pnl Usdc | 118.869643 |
| Number Of Trading Days | 27 |
| Number Of Trades | 844 |
| Valid Return Days | 32 |
| Excluded Return Days | 3 |
| Annualization Factor | 365 |

## Warnings and coverage notes

- Non-performance income types were treated as capital adjustments: COIN_SWAP_DEPOSIT
- 3 day(s) were excluded from ratios because the reconstructed capital base was invalid.

## Definitions

- **Performance Scope**: Daily realized USDC USD-M Futures performance from 2026-07-01, using UTC day boundaries.
- **Daily Net Pnl**: USDC realized PnL + USDC commission + USDC funding fee for each UTC day.
- **Daily Return**: Daily net PnL divided by reconstructed starting USDC capital; positive same-day transfers are added to the denominator.
- **Cumulative Return**: Product of (1 + daily return) minus 1.
- **Annualized Return**: Geometric cumulative return annualized with 365 calendar days.
- **Annualized Volatility**: Sample standard deviation of daily returns multiplied by sqrt(365).
- **Sharpe Ratio**: Mean daily return divided by sample daily standard deviation, multiplied by sqrt(365); risk-free rate is 0.
- **Sortino Ratio**: Mean daily return divided by sample downside deviation, multiplied by sqrt(365); target return is 0.
- **Maximum Drawdown**: Largest decline from a prior peak in normalized equity.
- **Calmar Ratio**: Annualized return divided by the absolute maximum drawdown.
- **Win Rate**: Positive daily net-PnL days divided by non-zero daily net-PnL days.
- **Profit Factor**: Sum of positive daily net PnL divided by absolute negative daily net PnL.
- **Annualization Factor**: 365 calendar days because crypto markets trade continuously.

This report is for professional evaluation only and is not investment advice.
