import pandas as pd

MA_PERIODS = (10, 60, 72, 100)


def add_sma(df: pd.DataFrame, periods=MA_PERIODS) -> pd.DataFrame:
    out = df.copy()
    for p in periods:
        out[f"ma{p}"] = out["close"].rolling(p).mean()
    return out
