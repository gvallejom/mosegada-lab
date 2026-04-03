# Mean Reversion Strategy – Research Notes

---

## 1. Objective

The objective of this project is to design, implement, and analyze a mean reversion trading strategy.

The strategy aims to exploit temporary deviations of asset prices from their statistical mean, under the assumption that prices tend to revert over time.

The goal is not only to maximize total return, but to achieve a balance between profitability and risk.

---

## 2. Strategy Description

The strategy is based on the z-score of the price relative to its rolling mean.

### Core Logic

- A rolling mean and rolling standard deviation are computed over a fixed window
- The z-score is calculated as:

  z = (price - rolling_mean) / rolling_std

### Trading Rules

- Enter **long** when z-score < -entry_threshold
- Enter **short** when z-score > entry_threshold
- Exit position when |z-score| < exit_threshold

### Key Parameters

- **Window**: Number of periods used to compute mean and standard deviation
- **Entry Threshold**: Z-score level required to open a position
- **Exit Threshold**: Z-score level at which positions are closed

---

## 3. Backtesting Framework

The strategy is evaluated using a simple backtesting framework.

### Assumptions

- Positions are applied with a one-period delay (to avoid look-ahead bias)
- No transaction costs or slippage are included
- Strategy returns are computed as:

  strategy_return = position(t-1) * asset_return(t)

### Performance Metrics

The following metrics are used:

- **Total Return**: Overall profitability of the strategy
- **Mean Daily Return**: Average daily return
- **Volatility (Std of Returns)**: Stability of returns
- **Sharpe Ratio**: Risk-adjusted performance
- **Max Drawdown**: Maximum loss from peak to trough

---

## 4. Parameter Optimization

Parameter optimization is performed using a grid search over:

- Rolling window
- Entry threshold
- Exit threshold

Each parameter combination is evaluated using historical data.

---

## 5. Objective Function

Optimization is not based solely on total return.

A combined score is used to balance profitability and risk:

Score = 0.7 * Total Return + 0.2 * Sharpe Ratio - 0.1 * |Max Drawdown|

### Interpretation

- Total Return has the highest weight → profitability is prioritized
- Sharpe Ratio ensures quality and consistency of returns
- Max Drawdown penalizes excessive losses

This reflects a realistic objective: maximize returns without ignoring risk.

---

## 6. Observations

Initial experiments reveal several key behaviors:

- The strategy tends to underperform buy-and-hold in strong trending markets
- Performance is highly sensitive to parameter selection
- Lower entry thresholds increase trade frequency but introduce noise
- Shorter windows increase responsiveness but reduce stability
- Larger windows generate fewer signals but improve robustness

The model exhibits a clear trade-off between responsiveness and stability.

---

## 7. Risk vs Return Trade-off

Improving total return often comes at the cost of increased risk.

Observed patterns include:

- Higher returns are often associated with larger drawdowns
- Aggressive parameter configurations lead to unstable performance
- Conservative configurations reduce drawdown but limit returns

The objective is not to maximize a single metric, but to find a balanced configuration.

---

## 8. Limitations

The current implementation has several limitations:

- Assumes mean-reverting behavior, which is not always present
- Does not include transaction costs or slippage
- Results may be affected by overfitting to the selected time period
- No out-of-sample validation has been performed
- Only a single asset is analyzed

These limitations must be addressed before any real-world deployment.

---

## 9. Next Steps

Planned improvements include:

- Introduce transaction costs and execution constraints
- Perform out-of-sample and walk-forward validation
- Add volatility or regime filters
- Compare performance across different assets
- Explore alternative signals beyond z-score
- Improve the objective function using normalized metrics

---

## 10. Conceptual Insight

This project highlights a key principle:

A strategy is not defined only by its logic, but by the criteria used to evaluate it.

Changing the objective function changes what is considered "optimal".

Therefore, defining the optimization goal is as important as designing the strategy itself.

---

## 11. Personal Approach

The approach followed in this project prioritizes:

- Understanding model behavior over blindly maximizing results
- Evaluating trade-offs between return and risk
- Building a structured and explainable framework

This reflects a research-oriented mindset rather than pure optimization.

---