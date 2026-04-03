import pandas as pd
import yfinance as yf


def load_price_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Download historical price data for a given ticker and return
    a cleaned DataFrame with Date index and close price column.

    Parameters:
        ticker (str): Asset ticker, e.g. 'SPY', 'AAPL', 'BTC-USD'
        start_date (str): Start date in format 'YYYY-MM-DD'
        end_date (str): End date in format 'YYYY-MM-DD'

    Returns:
        pd.DataFrame: DataFrame containing historical close prices
    """
    data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=False)

    if data.empty:
        raise ValueError(f"No data downloaded for ticker {ticker}")

    data = data[["Close"]].copy()
    data.dropna(inplace=True)
    data.rename(columns={"Close": "close"}, inplace=True)

    return data