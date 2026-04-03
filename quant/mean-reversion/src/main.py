from data_loader import load_price_data
from strategy import apply_mean_reversion_strategy
from backtest import run_backtest, calculate_performance_metrics
from visualization import (
    plot_price_and_mean,
    plot_z_score,
    plot_cumulative_returns
)
from optimizer import optimize_strategy_parameters


DEFAULT_TICKER = "SPY"
DEFAULT_START_DATE = "2020-01-01"
DEFAULT_END_DATE = "2024-12-31"

DEFAULT_WINDOW = 20
DEFAULT_ENTRY_THRESHOLD = 2.0
DEFAULT_EXIT_THRESHOLD = 0.5


def run_model(
    ticker: str,
    start_date: str,
    end_date: str,
    window: int,
    entry_threshold: float,
    exit_threshold: float
) -> None:
    """
    Run the full mean reversion pipeline:
    load data, apply strategy, backtest, print metrics, and show charts.
    """
    print("\nRunning mean reversion strategy with these parameters:")
    print(f"Ticker: {ticker}")
    print(f"Start date: {start_date}")
    print(f"End date: {end_date}")
    print(f"Window: {window}")
    print(f"Entry threshold: {entry_threshold}")
    print(f"Exit threshold: {exit_threshold}")

    print(f"\nLoading data for {ticker}...")
    price_data = load_price_data(ticker, start_date, end_date)

    print("Applying mean reversion strategy...")
    strategy_data = apply_mean_reversion_strategy(
        data=price_data,
        window=window,
        entry_threshold=entry_threshold,
        exit_threshold=exit_threshold
    )

    print("Running backtest...")
    backtest_data = run_backtest(strategy_data)

    print("Calculating performance metrics...")
    metrics = calculate_performance_metrics(backtest_data)

    print("\nLast 10 rows of backtest output:\n")
    print(backtest_data.tail(10).to_string())

    print("\nPerformance metrics:\n")
    for key, value in metrics.items():
        print(f"{key}: {value:.4f}")

    print("\nGenerating charts...")
    plot_price_and_mean(strategy_data, ticker)
    plot_z_score(strategy_data, entry_threshold, exit_threshold)
    plot_cumulative_returns(backtest_data, ticker)


def get_user_choice() -> str:
    """
    Ask the user whether to run the default model or a personalized one.
    """
    while True:
        choice = input("\nChoose mode: (D) Default / (P) Personalized: ").strip().upper()

        if choice in ["D", "P"]:
            return choice

        print("Invalid option. Please enter 'D' or 'P'.")


def get_personalized_parameters() -> tuple[int, float, float]:
    """
    Run parameter optimization, display the top combinations,
    and ask the user to enter personalized values.
    """
    print("\nLoading data for optimization...")
    price_data = load_price_data(
        DEFAULT_TICKER,
        DEFAULT_START_DATE,
        DEFAULT_END_DATE
    )

    print("Running parameter optimization using the custom score...")
    print("Score = 0.7 * Total Return + 0.2 * Sharpe Ratio - 0.1 * |Max Drawdown|")

    window_values = [5, 10, 15, 20, 30]
    entry_threshold_values = [1.5, 2.0, 2.5]
    exit_threshold_values = [0.3, 0.5, 0.8, 1.0]

    results_df = optimize_strategy_parameters(
        price_data=price_data,
        window_values=window_values,
        entry_threshold_values=entry_threshold_values,
        exit_threshold_values=exit_threshold_values,
        objective_metric="score",
        maximize=True
    )

    print("\nTop parameter combinations by score:\n")
    print(results_df.head(10).to_string(index=False))

    print("\nNow enter your personalized parameters.")
    print("Format:")
    print("  window -> integer, e.g. 20")
    print("  entry  -> float, e.g. 2.0")
    print("  exit   -> float, e.g. 0.5")

    while True:
        try:
            window = int(input("\nEnter window: ").strip())
            entry_threshold = float(input("Enter entry threshold: ").strip())
            exit_threshold = float(input("Enter exit threshold: ").strip())

            return window, entry_threshold, exit_threshold

        except ValueError:
            print("Invalid format. Please enter numeric values correctly.")


def main():
    choice = get_user_choice()

    if choice == "D":
        run_model(
            ticker=DEFAULT_TICKER,
            start_date=DEFAULT_START_DATE,
            end_date=DEFAULT_END_DATE,
            window=DEFAULT_WINDOW,
            entry_threshold=DEFAULT_ENTRY_THRESHOLD,
            exit_threshold=DEFAULT_EXIT_THRESHOLD
        )

    elif choice == "P":
        window, entry_threshold, exit_threshold = get_personalized_parameters()

        run_model(
            ticker=DEFAULT_TICKER,
            start_date=DEFAULT_START_DATE,
            end_date=DEFAULT_END_DATE,
            window=window,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold
        )


if __name__ == "__main__":
    main()