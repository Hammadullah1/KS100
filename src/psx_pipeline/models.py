"""Bounded CPU models with JSON/text persistence, never arbitrary pickle loading."""

import numpy as np
from lightgbm import Booster, LGBMClassifier, early_stopping
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from .storage import digest

FEATURE_COLUMNS = ["return_1", "return_5", "return_20", "volatility_20"]


COMPANY_COLUMNS = FEATURE_COLUMNS + ["bank_sector", "exporter_exposure", "exporter_missing"]


def fit_model(name, frame, columns=FEATURE_COLUMNS):
    x = frame[columns].to_numpy(float)
    y = frame.label.to_numpy(int)
    if len(np.unique(y)) < 2:
        raise ValueError("two classes required for training")
    medians = np.nanmedian(x, axis=0)
    if not np.isfinite(medians).all():
        raise ValueError("feature is entirely missing in fit data")
    x = np.where(np.isnan(x), medians, x)
    artifact = {"name": name, "columns": columns, "medians": medians.tolist()}
    if name == "frequency":
        artifact["p"] = float(y.mean())
    elif name == "majority":
        artifact["p"] = float(y.mean() >= 0.5)
    elif name == "lagged_return":
        pass
    elif name == "logistic":
        scaler = StandardScaler().fit(x)
        model = LogisticRegression(C=1, max_iter=500, random_state=731).fit(scaler.transform(x), y)
        artifact.update(
            mean=scaler.mean_.tolist(),
            scale=scaler.scale_.tolist(),
            coef=model.coef_[0].tolist(),
            intercept=float(model.intercept_[0]),
        )
    elif name == "lightgbm":
        # Inner chronological early stopping is contained in the fit block.
        dates = sorted(frame.session.unique())
        split = dates[-max(20, len(dates) // 5)]
        train = frame[(frame.session < split) & (frame.target_session < split)]
        validation = frame[frame.session >= split]
        model = LGBMClassifier(
            n_estimators=200,
            num_leaves=7,
            max_depth=3,
            learning_rate=0.03,
            min_child_samples=30,
            reg_lambda=5,
            n_jobs=2,
            verbosity=-1,
            random_state=731,
            deterministic=True,
            force_col_wise=True,
        )
        model.fit(
            train[columns],
            train.label,
            eval_set=[(validation[columns], validation.label)],
            callbacks=[early_stopping(20, verbose=False)],
        )
        artifact["text"] = model.booster_.model_to_string()
        artifact["best_iteration"] = model.best_iteration_
    elif name == "blend":
        raise ValueError("blend must use out-of-time predictions")
    else:
        raise ValueError("unknown model")
    return artifact


def predict_model(artifact, frame):
    name = artifact["name"]
    x = frame[artifact["columns"]].to_numpy(float)
    if name in {"frequency", "majority"}:
        p = np.full(len(x), artifact["p"])
    elif name == "lagged_return":
        p = np.where(frame.return_1.to_numpy() > 0, 0.6, 0.4)
    elif name == "logistic":
        x = np.where(np.isnan(x), artifact["medians"], x)
        p = expit(
            ((x - artifact["mean"]) / artifact["scale"]) @ np.array(artifact["coef"]) + artifact["intercept"]
        )
    elif name == "lightgbm":
        p = Booster(model_str=artifact["text"]).predict(x, num_threads=2)
    elif name == "blend":
        p = sum(w * predict_model(m, frame) for w, m in zip(artifact["weights"], artifact["models"]))
    else:
        raise ValueError("unrecognized safe model format")
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("invalid model probability")
    return p


def choose_predictor(models, oot):
    scored = [
        (float(np.mean((predict_model(m, oot) - oot.label.to_numpy()) ** 2)), m)
        for m in models
        if m["name"] != "majority"
    ]
    # Prespecified simplex grid, fit exclusively on later out-of-time rows.
    pair = [next(m for m in models if m["name"] == n) for n in ["logistic", "lightgbm"]]
    for w in [0.25, 0.5, 0.75]:
        blend = {"name": "blend", "columns": pair[0]["columns"], "weights": [w, 1 - w], "models": pair}
        scored.append((float(np.mean((predict_model(blend, oot) - oot.label.to_numpy()) ** 2)), blend))
    return min(scored, key=lambda item: item[0])[1]


def calibrate(artifact, frame):
    p = predict_model(artifact, frame)
    if frame.label.nunique() < 2:
        raise ValueError("calibration block lacks two classes")
    model = LogisticRegression(C=1, max_iter=500).fit(
        logit(np.clip(p, 1e-6, 1 - 1e-6)).reshape(-1, 1), frame.label
    )
    return {"method": "sigmoid", "coef": float(model.coef_[0, 0]), "intercept": float(model.intercept_[0])}


def calibrated(artifact, calibrator, frame):
    p = predict_model(artifact, frame)
    return expit(calibrator["coef"] * logit(np.clip(p, 1e-6, 1 - 1e-6)) + calibrator["intercept"])


def model_version(artifact):
    return "model-" + digest(artifact)[:16]


def model_slot(candidate):
    suffix = digest(candidate["instrument_ids"][0])[:12] if candidate["scope"] == "index" else "pooled"
    return f"{candidate['scope']}-{suffix}-h{candidate['horizon']}"
