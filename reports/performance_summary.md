# Performance Summary

Generated at: **2026-08-20T00:10:08Z**<br>
Coverage: **2026-07-01 to 2026-08-20 (UTC)**<br>
Scope: **Daily USDC USD-M Futures realized performance**

Absolute account values are not published. USD-M Futures transfers are excluded from trading return.
Sharpe and Sortino use private total daily returns including unrealized PnL; unrealized amounts and daily total returns are not published.

| Metric | Value |
|---|---:|
| Cumulative Return | 4.40% |
| Latest Daily Return | 0.11% |
| Annualized Return | 38.74% |
| Annualized Volatility | 1.27% |
| Sharpe Ratio | -2.282085 |
| Sortino Ratio | -2.296151 |
| Maximum Drawdown | -0.01% |
| Calmar Ratio | 4241.746807 |
| Win Rate | 97.67% |
| Profit Factor | 1790.123598 |
| Total Realized Pnl Usdc | 186.829498 |
| Total Commission Usdc | -0.075227 |
| Total Funding Fee Usdc | 9.248406 |
| Total Net Pnl Usdc | 196.002677 |
| Number Of Trading Days | 43 |
| Number Of Trades | 1355 |
| Valid Return Days | 48 |
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
