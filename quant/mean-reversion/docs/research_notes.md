# Mean Reversion Strategy – Research Notes

## Objective

The goal of this project is to develop a mean reversion trading strategy and optimize its parameters.

The primary objective is to improve total return, while ensuring that other performance metrics remain within acceptable ranges.

## Optimization Philosophy

Maximizing total return alone is not sufficient.

A strategy with high returns but poor risk characteristics may not be viable in real-world conditions.

Therefore, optimization must consider multiple metrics simultaneously.

## Key Metrics

The following metrics are used to evaluate the strategy:

- **Total Return**: Overall profitability of the strategy
- **Sharpe Ratio**: Risk-adjusted return
- **Max Drawdown**: Maximum loss from peak to trough
- **Volatility (std of returns)**: Stability of returns

## Optimization Approach

Parameter optimization is performed using a grid search over:

- Rolling window size
- Entry threshold (z-score)
- Exit threshold (z-score)

Each parameter combination is evaluated using historical backtesting.

## Trade-offs

Improving one metric often worsens another:

- Higher returns may increase drawdown
- Lower thresholds increase trade frequency but add noise
- Shorter windows increase responsiveness but reduce stability

The goal is to find a balance between:

- profitability
- stability
- robustness

## Current Status

Initial experiments show that parameter choices significantly impact performance.

Further work is required to:

- test robustness across different assets
- evaluate performance in different market regimes
- avoid overfitting to a specific time period

## Next Steps

- Implement parameter optimization
- Analyze sensitivity of results to parameter changes
- Introduce out-of-sample testing
- Explore additional filters (e.g. volatility, regime detection)