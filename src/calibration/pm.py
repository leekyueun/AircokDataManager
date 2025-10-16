from datetime import datetime
import numpy as np
import pandas as pd
import xgboost as xgb

try:
    from sklearn.neural_network import MLPRegressor
    HAS_SKLEARN = True
except Exception:
    HAS_SKLEARN = False

def prepare_grimm_data(path):
    df = pd.read_csv(path, encoding='ISO-8859-1', skiprows=12, sep='\t', header=None)
    df.columns = ['datetime', 'pm10', 'pm2.5', 'pm1', 'inhalable', 'thoracic', 'alveolic']
    df = df[['datetime', 'pm10', 'pm2.5']].rename(
        columns={'datetime': 'date', 'pm10': 'grimm_pm10', 'pm2.5': 'grimm_pm25'}
    )
    df['date'] = df['date'].str.replace('¿ÀÀü', 'AM', regex=False).str.replace('¿ÀÈÄ', 'PM', regex=False)
    df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d %p %I:%M:%S', errors='coerce').dt.round('5min')
    df['grimm_pm25'] = pd.to_numeric(df['grimm_pm25'], errors='coerce')
    df['grimm_pm10'] = pd.to_numeric(df['grimm_pm10'], errors='coerce')
    return df.dropna()

def prepare_aircok_data(path):
    df = pd.read_csv(path, usecols=['date', 'pm2.5', 'pm10'])
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['pm2.5'] = pd.to_numeric(df['pm2.5'], errors='coerce')
    df['pm10']  = pd.to_numeric(df['pm10'],  errors='coerce')
    return df.dropna()

def calc_accuracy(true, pred, eps=1e-9):
    denom = np.where(true == 0, eps, true)
    return float(100 - (np.abs(true - pred) / denom).mean() * 100)

def safe_ratio(num, den, eps=1e-9):
    return num / np.where(den == 0, eps, den)

def method_scalar(sensor, grimm):
    y_ratio = safe_ratio(grimm, sensor)
    y_ratio = y_ratio[np.isfinite(y_ratio) & (y_ratio > 0)]
    if y_ratio.size < 3:
        return None
    factor = round(float(np.median(y_ratio)), 2)
    corrected = sensor * factor
    return {"name": "scalar", "factor": factor, "corrected": corrected}

def method_xgb(X, sensor, grimm):
    y_ratio = safe_ratio(grimm, sensor)
    mask = np.isfinite(y_ratio) & (y_ratio > 0)
    X_ = X[mask]
    y_ = y_ratio[mask]
    if len(X_) < 3:
        return None
    model = xgb.XGBRegressor(objective='reg:squarederror', verbosity=0)
    model.fit(X_, y_)
    pred_ratio = model.predict(X_)
    if pred_ratio.size == 0:
        return None
    pred_ratio = np.clip(pred_ratio, 1e-6, None)
    factor = round(float(np.median(pred_ratio)), 2)
    corrected = sensor[mask] * pred_ratio
    corrected_full = pd.Series(np.nan, index=sensor.index)
    corrected_full.loc[mask] = corrected
    return {"name": "xgb", "factor": factor, "corrected": corrected_full}

def method_mlp(X, sensor, grimm):
    if not HAS_SKLEARN:
        return None
    y_ratio = safe_ratio(grimm, sensor)
    mask = np.isfinite(y_ratio) & (y_ratio > 0)
    X_ = X[mask]
    y_ = y_ratio[mask]
    if len(X_) < 3:
        return None
    mlp = MLPRegressor(hidden_layer_sizes=(32, 16), activation='relu', max_iter=1000, random_state=42)
    mlp.fit(X_, y_)
    pred_ratio = mlp.predict(X_)
    pred_ratio = np.clip(pred_ratio, 1e-6, None)
    factor = round(float(np.median(pred_ratio)), 2)
    corrected = sensor[mask] * pred_ratio
    corrected_full = pd.Series(np.nan, index=sensor.index)
    corrected_full.loc[mask] = corrected
    return {"name": "mlp", "factor": factor, "corrected": corrected_full}

def pm_cal(grimm_file_path, aircok_file_path):
    grimm = prepare_grimm_data(grimm_file_path)
    aircok = prepare_aircok_data(aircok_file_path)
    merged = pd.merge(grimm, aircok, on='date', how='inner').dropna().copy()
    bins   = [10, 30, 60, 100, 200]
    labels = ['10-30', '31-60', '61-100', '101-200']
    merged['pm25_range'] = pd.cut(merged['pm2.5'], bins=bins, labels=labels, right=True, include_lowest=True)
    merged['pm10_range'] = pd.cut(merged['pm10'],  bins=bins, labels=labels, right=True, include_lowest=True)
    correction_factors_pm25, correction_factors_pm10 = [], []
    methods_pm25, methods_pm10 = [], []
    merged['corrected_pm25'] = np.nan
    merged['corrected_pm10'] = np.nan

    for label in labels:
        idx25 = merged.index[merged['pm25_range'] == label]
        if len(idx25) > 0:
            sub = merged.loc[idx25]
            X_25 = sub[['pm2.5', 'pm10']]
            sensor_25 = sub['pm2.5']
            true_25   = sub['grimm_pm25']
            m_scalar = method_scalar(sensor_25, true_25)
            m_xgb    = method_xgb(X_25, sensor_25, true_25)
            m_mlp    = method_mlp(X_25, sensor_25, true_25)
            print(f"\n[PM2.5] 구간: {label} (샘플 {len(sub)})")
            candidates_25 = []
            for m in [m_scalar, m_xgb, m_mlp]:
                if m is None:
                    continue
                name   = m['name']
                factor = m['factor']
                acc    = calc_accuracy(true_25, m['corrected'].fillna(0) if isinstance(m['corrected'], pd.Series) else m['corrected'])
                candidates_25.append((name, factor, acc, m['corrected']))
                c_min = np.nanmin(m['corrected']) if isinstance(m['corrected'], (pd.Series, np.ndarray)) else float(np.min(m['corrected']))
                c_max = np.nanmax(m['corrected']) if isinstance(m['corrected'], (pd.Series, np.ndarray)) else float(np.max(m['corrected']))
                print(f" - {name:<6} | factor={factor:.2f} | acc={acc:.2f}% | min={c_min:.2f} max={c_max:.2f}")
            if candidates_25:
                best_name, best_factor, best_acc, best_corr = max(candidates_25, key=lambda x: x[2])
                print(f" >> 선택됨: {best_name} (factor={best_factor}, acc={best_acc:.2f}%)")
                correction_factors_pm25.append((label, best_factor))
                methods_pm25.append((label, best_name, round(best_acc, 2)))
                best_corr_vals = best_corr.values if isinstance(best_corr, pd.Series) else best_corr
                merged.loc[idx25, 'corrected_pm25'] = best_corr_vals
            else:
                print(f" >> 선택됨: default (factor=1.00, acc=0.00%)")
                correction_factors_pm25.append((label, 1.0))
                methods_pm25.append((label, "default", 0.0))
                merged.loc[idx25, 'corrected_pm25'] = sensor_25.values
        else:
            print(f"\n[PM2.5] 구간: {label} (샘플 0)")
            print(f" >> 선택됨: default (factor=1.00, acc=0.00%)")
            correction_factors_pm25.append((label, 1.0))
            methods_pm25.append((label, "default", 0.0))

        idx10 = merged.index[merged['pm10_range'] == label]
        if len(idx10) > 0:
            sub = merged.loc[idx10]
            X_10 = sub[['pm2.5', 'pm10']]
            sensor_10 = sub['pm10']
            true_10   = sub['grimm_pm10']
            m_scalar = method_scalar(sensor_10, true_10)
            m_xgb    = method_xgb(X_10, sensor_10, true_10)
            m_mlp    = method_mlp(X_10, sensor_10, true_10)
            print(f"\n[PM10 ] 구간: {label} (샘플 {len(sub)})")
            candidates_10 = []
            for m in [m_scalar, m_xgb, m_mlp]:
                if m is None:
                    continue
                name   = m['name']
                factor = m['factor']
                acc    = calc_accuracy(true_10, m['corrected'].fillna(0) if isinstance(m['corrected'], pd.Series) else m['corrected'])
                candidates_10.append((name, factor, acc, m['corrected']))
                c_min = np.nanmin(m['corrected']) if isinstance(m['corrected'], (pd.Series, np.ndarray)) else float(np.min(m['corrected']))
                c_max = np.nanmax(m['corrected']) if isinstance(m['corrected'], (pd.Series, np.ndarray)) else float(np.max(m['corrected']))
                print(f" - {name:<6} | factor={factor:.2f} | acc={acc:.2f}% | min={c_min:.2f} max={c_max:.2f}")
            if candidates_10:
                best_name, best_factor, best_acc, best_corr = max(candidates_10, key=lambda x: x[2])
                print(f" >> 선택됨: {best_name} (factor={best_factor}, acc={best_acc:.2f}%)")
                correction_factors_pm10.append((label, best_factor))
                methods_pm10.append((label, best_name, round(best_acc, 2)))
                best_corr_vals = best_corr.values if isinstance(best_corr, pd.Series) else best_corr
                merged.loc[idx10, 'corrected_pm10'] = best_corr_vals
            else:
                print(f" >> 선택됨: default (factor=1.00, acc=0.00%)")
                correction_factors_pm10.append((label, 1.0))
                methods_pm10.append((label, "default", 0.0))
                merged.loc[idx10, 'corrected_pm10'] = sensor_10.values
        else:
            print(f"\n[PM10 ] 구간: {label} (샘플 0)")
            print(f" >> 선택됨: default (factor=1.00, acc=0.00%)")
            correction_factors_pm10.append((label, 1.0))
            methods_pm10.append((label, "default", 0.0))

    merged = merged.dropna(subset=['corrected_pm25', 'corrected_pm10'])

    result = {
        "pm25_correction": correction_factors_pm25,
        "pm10_correction": correction_factors_pm10,
        "pm25_methods": methods_pm25,
        "pm10_methods": methods_pm10,
        "pm25_accuracy_pre":  round(calc_accuracy(merged['grimm_pm25'].to_numpy(), merged['pm2.5'].to_numpy()), 2),
        "pm25_accuracy_post": round(calc_accuracy(merged['grimm_pm25'].to_numpy(), merged['corrected_pm25'].to_numpy()), 2),
        "pm10_accuracy_pre":  round(calc_accuracy(merged['grimm_pm10'].to_numpy(), merged['pm10'].to_numpy()), 2),
        "pm10_accuracy_post": round(calc_accuracy(merged['grimm_pm10'].to_numpy(), merged['corrected_pm10'].to_numpy()), 2),
    }

    print("\n[SUMMARY] pm25_correction:", result["pm25_correction"])
    print("[SUMMARY] pm10_correction:", result["pm10_correction"])
    return result
