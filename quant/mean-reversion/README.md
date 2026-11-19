# Mean Reversion Strategy (z-score)

Research project that designs, backtests and optimises a **mean reversion** trading strategy on daily price data (default: SPY, 2020–2024).

The question behind it: *if a price moves far away from its recent average, does it tend to come back, and can that be traded?*

## How it works

1. **Data**: daily close prices downloaded with `yfinance`.
2. **Signal**: rolling mean and standard deviation over a window, and the **z-score**

   `z = (price - rolling_mean) / rolling_std`

3. **Trading rules**
   - Go **long** when `z < -entry_threshold` (price unusually low)
   - Go **short** when `z > entry_threshold` (price unusually high)
   - **Exit** when `|z| < exit_threshold` (price back near its mean)
4. **Backtest**: positions are applied with a one-day delay to avoid look-ahead bias.
5. **Metrics**: total return, mean and volatility of daily returns, annualised **Sharpe ratio** and **max drawdown**.
6. **Optimisation**: grid search over window, entry and exit thresholds, ranked by a custom score that balances return and risk:

   `score = 0.7 · total_return + 0.2 · sharpe - 0.1 · |max_drawdown|`

7. **Charts**: price vs rolling mean, z-score with thresholds, and cumulative returns vs buy-and-hold.

## Run it

```bash
pip install -r requirements.txt
cd src
python main.py
```

Choose **(D)** to run with default parameters, or **(P)** to see the best parameter combinations from the grid search and enter your own.

## Project structure

```
mean-reversion/
├── src/
│   ├── main.py            # CLI entry point: default or personalised run
│   ├── data_loader.py     # price download and cleaning
│   ├── strategy.py        # z-score signal and position logic
│   ├── backtest.py        # returns, cumulative performance, metrics
│   ├── optimizer.py       # grid search with custom objective
│   └── visualization.py   # matplotlib charts
└── docs/
    └── research_notes.md  # methodology, observations and limitations
```

## Findings and limitations

From the [research notes](docs/research_notes.md):

- The strategy tends to **underperform buy-and-hold in strong trending markets**, where prices don't revert.
- Results are **highly sensitive to parameters**: shorter windows react faster but are noisier; larger windows are more robust but trade less.
- The backtest has **no transaction costs or slippage** and **no out-of-sample validation**, so optimised results are likely optimistic (overfitting risk).

**Next steps:** transaction costs, walk-forward validation, volatility/regime filters and testing across multiple assets.

## Tech stack

Python · pandas · NumPy · yfinance · matplotlib
