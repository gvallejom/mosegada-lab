import pandas as pd
import yfinance as yf


def load_price_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Download historical price data for a given ticker and return
    a cleaned DataFrame with Date index and a single 'close' column.
    """
    data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=False)

    if data.empty:
        raise ValueError(f"No data downloaded for ticker {ticker}")

    # Si las columnas vienen como MultiIndex, nos quedamos con la parte útil
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data[["Close"]].copy()
    data.dropna(inplace=True)
    data.columns = ["close"]

    return data