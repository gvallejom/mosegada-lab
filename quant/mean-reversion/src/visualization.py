import matplotlib.pyplot as plt
import pandas as pd


def plot_price_and_mean(data: pd.DataFrame, ticker: str) -> None:
    """
    Plot close price and rolling mean.
    """
    plt.figure(figsize=(12, 6))
    plt.plot(data.index, data["close"], label="Close Price")
    plt.plot(data.index, data["rolling_mean"], label="Rolling Mean")
    plt.title(f"{ticker} - Price vs Rolling Mean")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def plot_z_score(data: pd.DataFrame, entry_threshold: float, exit_threshold: float) -> None:
    """
    Plot z-score with entry and exit thresholds.
    """
    plt.figure(figsize=(12, 6))
    plt.plot(data.index, data["z_score"], label="Z-Score")
    plt.axhline(entry_threshold, linestyle="--", label=f"Short Entry: +{entry_threshold}")
    plt.axhline(-entry_threshold, linestyle="--", label=f"Long Entry: -{entry_threshold}")
    plt.axhline(exit_threshold, linestyle=":", label=f"Exit: +{exit_threshold}")
    plt.axhline(-exit_threshold, linestyle=":", label=f"Exit: -{exit_threshold}")
    plt.axhline(0, linestyle="-", label="Mean Level")
    plt.title("Z-Score and Trading Thresholds")
    plt.xlabel("Date")
    plt.ylabel("Z-Score")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def plot_cumulative_returns(data: pd.DataFrame, ticker: str) -> None:
    """
    Plot cumulative asset return vs cumulative strategy return.
    """
    plt.figure(figsize=(12, 6))
    plt.plot(data.index, data["cumulative_asset_return"], label=f"{ticker} Buy and Hold")
    plt.plot(data.index, data["cumulative_strategy_return"], label="Mean Reversion Strategy")
    plt.title(f"{ticker} - Cumulative Returns")
    plt.xlabel("Date")
    plt.ylabel("Cumulative Return")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()