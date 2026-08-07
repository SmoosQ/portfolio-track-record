# Performance Summary

Generated at: **2026-08-07T00:10:07Z**<br>
Coverage: **2026-07-01 to 2026-08-07 (UTC)**<br>
Scope: **Daily USDC USD-M Futures realized performance**

Absolute account values are not published. USD-M Futures transfers are excluded from trading return.
Sharpe and Sortino use private total daily returns including unrealized PnL; unrealized amounts and daily total returns are not published.

| Metric | Value |
|---|---:|
| Cumulative Return | 3.04% |
| Latest Daily Return | 0.00% |
| Annualized Return | 36.64% |
| Annualized Volatility | 1.36% |
| Sharpe Ratio | 5.721263 |
| Sortino Ratio | 10.150423 |
| Maximum Drawdown | -0.01% |
| Calmar Ratio | 4011.427138 |
| Win Rate | 96.67% |
| Profit Factor | 1231.145563 |
| Total Realized Pnl Usdc | 133.137399 |
| Total Commission Usdc | -0.075227 |
| Total Funding Fee Usdc | 1.703154 |
| Total Net Pnl Usdc | 134.765325 |
| Number Of Trading Days | 30 |
| Number Of Trades | 957 |
| Valid Return Days | 35 |
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
