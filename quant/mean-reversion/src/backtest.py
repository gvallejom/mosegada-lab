import pandas as pd


def run_backtest(data: pd.DataFrame) -> pd.DataFrame:
    """
    Run a simple backtest using the generated positions.

    Assumptions:
    - Position at time t is applied to return from t to t+1
    - No transaction costs
    - No slippage

    Parameters:
        data (pd.DataFrame): DataFrame with 'close' and 'position'

    Returns:
        pd.DataFrame: DataFrame with returns and cumulative performance
    """
    df = data.copy()

    df["asset_return"] = df["close"].pct_change()

    # Shift position by 1 to avoid look-ahead bias
    df["strategy_return"] = df["position"].shift(1) * df["asset_return"]

    df["cumulative_asset_return"] = (1 + df["asset_return"]).cumprod()
    df["cumulative_strategy_return"] = (1 + df["strategy_return"]).cumprod()

    df.dropna(inplace=True)

    return df


def calculate_performance_metrics(data: pd.DataFrame) -> dict:
    """
    Calculate basic performance metrics for the strategy.

    Parameters:
        data (pd.DataFrame): DataFrame with 'strategy_return'

    Returns:
        dict: Dictionary with key performance metrics
    """
    strategy_returns = data["strategy_return"]

    total_return = (1 + strategy_returns).prod() - 1
    mean_daily_return = strategy_returns.mean()
    std_daily_return = strategy_returns.std()

    if std_daily_return != 0:
        sharpe_ratio = (mean_daily_return / std_daily_return) * (252 ** 0.5)
    else:
        sharpe_ratio = 0.0

    cumulative = (1 + strategy_returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()

    metrics = {
        "total_return": total_return,
        "mean_daily_return": mean_daily_return,
        "std_daily_return": std_daily_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
    }

    return metrics