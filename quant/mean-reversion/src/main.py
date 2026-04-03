from data_loader import load_price_data
from strategy import apply_mean_reversion_strategy
from backtest import run_backtest, calculate_performance_metrics


def main():
    ticker = "SPY"
    start_date = "2020-01-01"
    end_date = "2024-12-31"

    window = 20
    entry_threshold = 2.0
    exit_threshold = 0.5

    print(f"\nLoading data for {ticker}...")
    price_data = load_price_data(ticker, start_date, end_date)

    print("Applying mean reversion strategy...")
    strategy_data = apply_mean_reversion_strategy(
        price_data,
        window=window,
        entry_threshold=entry_threshold,
        exit_threshold=exit_threshold
    )

    print("Running backtest...")
    backtest_data = run_backtest(strategy_data)

    print("Calculating performance metrics...")
    metrics = calculate_performance_metrics(backtest_data)

    print("\nLast 10 rows of backtest output:\n")
    print(backtest_data.tail(10))

    print("\nPerformance metrics:\n")
    for key, value in metrics.items():
        print(f"{key}: {value:.4f}")


if __name__ == "__main__":
    main()