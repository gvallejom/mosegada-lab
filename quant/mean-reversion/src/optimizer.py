import itertools
import pandas as pd

from strategy import apply_mean_reversion_strategy
from backtest import run_backtest, calculate_performance_metrics


def optimize_strategy_parameters(
    price_data: pd.DataFrame,
    window_values: list[int],
    entry_threshold_values: list[float],
    exit_threshold_values: list[float],
    objective_metric: str = "score",
    maximize: bool = True
) -> pd.DataFrame:
    """
    Test all parameter combinations for the mean reversion strategy and
    return a DataFrame sorted by the selected objective metric.

    Parameters:
        price_data (pd.DataFrame): Historical price data
        window_values (list[int]): List of rolling window values
        entry_threshold_values (list[float]): List of entry thresholds
        exit_threshold_values (list[float]): List of exit thresholds
        objective_metric (str): Metric used to rank combinations.
                                Options:
                                - "total_return"
                                - "sharpe_ratio"
                                - "max_drawdown"
                                - "score"
        maximize (bool): If True, sort descending. If False, ascending.

    Returns:
        pd.DataFrame: DataFrame with all parameter combinations and metrics
    """
    results = []

    parameter_combinations = itertools.product(
        window_values,
        entry_threshold_values,
        exit_threshold_values
    )

    for window, entry_threshold, exit_threshold in parameter_combinations:
        try:
            strategy_data = apply_mean_reversion_strategy(
                data=price_data,
                window=window,
                entry_threshold=entry_threshold,
                exit_threshold=exit_threshold
            )

            backtest_data = run_backtest(strategy_data)
            metrics = calculate_performance_metrics(backtest_data)

            # Objective function:
            # prioritize total return, then reward Sharpe, then penalize drawdown
            score = (
                0.7 * metrics["total_return"]
                + 0.2 * metrics["sharpe_ratio"]
                - 0.1 * abs(metrics["max_drawdown"])
            )

            result_row = {
                "window": window,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "total_return": metrics["total_return"],
                "mean_daily_return": metrics["mean_daily_return"],
                "std_daily_return": metrics["std_daily_return"],
                "sharpe_ratio": metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"],
                "score": score,
            }

            results.append(result_row)

        except Exception as e:
            print(
                f"Error with parameters "
                f"(window={window}, entry={entry_threshold}, exit={exit_threshold}): {e}"
            )

    results_df = pd.DataFrame(results)

    valid_metrics = [
        "total_return",
        "sharpe_ratio",
        "max_drawdown",
        "score"
    ]

    if objective_metric not in valid_metrics:
        raise ValueError(
            f"Invalid objective_metric: {objective_metric}. "
            f"Choose one of {valid_metrics}"
        )

    results_df.sort_values(
        by=objective_metric,
        ascending=not maximize,
        inplace=True
    )
    results_df.reset_index(drop=True, inplace=True)

    return results_df