"""Retrospective Brent features with an explicit availability proxy, not vintages."""

import numpy as np
import pandas as pd

BRENT_COLUMNS = ["brent_return_5", "brent_return_20", "brent_volatility_20", "brent_age", "brent_missing"]


def add_brent(frame, path):
    data = pd.read_csv(path, na_values=["."])
    if list(data.columns) != ["observation_date", "DCOILBRENTEU"]:
        raise ValueError("Expected FRED observation_date,DCOILBRENTEU CSV")
    data["observation_date"] = pd.to_datetime(data.observation_date, format="%Y-%m-%d", errors="raise")
    data["value"] = pd.to_numeric(data.DCOILBRENTEU, errors="raise")
    if data.observation_date.isna().any() or data.observation_date.duplicated().any():
        raise ValueError("Invalid or duplicate Brent dates")
    valid = data.value.notna()
    if (
        not valid.any()
        or not np.isfinite(data.loc[valid, "value"]).all()
        or (data.loc[valid, "value"] <= 0).any()
    ):
        raise ValueError("Invalid Brent values")
    data = data[valid].sort_values("observation_date").copy()
    values = np.log(data.value)
    data["brent_return_5"] = values.diff(5)
    data["brent_return_20"] = values.diff(20)
    data["brent_volatility_20"] = values.diff().rolling(20).std()
    # Deliberate research proxy. Seven days is NOT proof of historic availability.
    data["assumed_available_date"] = data.observation_date + pd.Timedelta(days=7)
    left = frame.assign(origin_date=pd.to_datetime(frame.session)).sort_values("origin_date")
    joined = pd.merge_asof(
        left,
        data[["observation_date", "assumed_available_date"] + BRENT_COLUMNS[:3]],
        left_on="origin_date",
        right_on="assumed_available_date",
        direction="backward",
    )
    age = (joined.origin_date - joined.observation_date).dt.days
    missing = age.isna() | (age > 21) | joined[BRENT_COLUMNS[:3]].isna().any(axis=1)
    joined["brent_age"] = age.clip(upper=21).fillna(21)
    joined["brent_missing"] = missing.astype(float)
    joined.loc[missing, BRENT_COLUMNS[:3]] = 0.0
    usable = joined["brent_missing"].eq(0)
    if not usable.any():
        raise ValueError("No usable Brent history overlaps the index observations")
    if not (joined.loc[usable, "assumed_available_date"] <= joined.loc[usable, "origin_date"]).all():
        raise ValueError("Future Brent data joined to earlier observations")
    return joined.drop(columns=["origin_date", "observation_date", "assumed_available_date"])
