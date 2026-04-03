import pandas as pd


def apply_mean_reversion_strategy(
    data: pd.DataFrame,
    window: int = 10,
    entry_threshold: float = 1.5,
    exit_threshold: float = 0.8
) -> pd.DataFrame:
    """
    Apply a simple mean reversion strategy using rolling mean, rolling std,
    and z-score.

    Trading logic:
    - Enter long when z_score < -entry_threshold
    - Enter short when z_score > entry_threshold
    - Exit when absolute z_score < exit_threshold

    Parameters:
        data (pd.DataFrame): DataFrame with a 'close' column
        window (int): Rolling window for mean and std
        entry_threshold (float): Absolute z-score threshold for entering trades
        exit_threshold (float): Absolute z-score threshold for exiting trades

    Returns:
        pd.DataFrame: DataFrame with indicators and trading positions
    """
    df = data.copy()

    df["rolling_mean"] = df["close"].rolling(window=window).mean()
    df["rolling_std"] = df["close"].rolling(window=window).std()

    df["z_score"] = (df["close"] - df["rolling_mean"]) / df["rolling_std"]

    df.dropna(inplace=True)

    positions = []
    current_position = 0

    for _, row in df.iterrows():
        z_score = row["z_score"]

        if current_position == 0:
            if z_score < -entry_threshold:
                current_position = 1
            elif z_score > entry_threshold:
                current_position = -1

        elif current_position == 1:
            if abs(z_score) < exit_threshold:
                current_position = 0

        elif current_position == -1:
            if abs(z_score) < exit_threshold:
                current_position = 0

        positions.append(current_position)

    df["position"] = positions

    return df