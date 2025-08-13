from datetime import datetime
import numpy as np
import pandas as pd
import xgboost as xgb

# 선택적: sklearn이 없으면 딥러닝 방법은 자동 스킵
try:
    from sklearn.neural_network import MLPRegressor
    HAS_SKLEARN = True
except Exception:
    HAS_SKLEARN = False

# ---------- I/O & 전처리 ----------
def prepare_grimm_data(path):
    df = pd.read_csv(path, encoding='ISO-8859-1', skiprows=12, sep='\t', header=None)
    df.columns = ['datetime', 'pm10', 'pm2.5', 'pm1', 'inhalable', 'thoracic', 'alveolic']
    df = df[['datetime', 'pm10', 'pm2.5']].rename(
        columns={'datetime': 'date', 'pm10': 'grimm_pm10', 'pm2.5': 'grimm_pm25'}
    )

    # AM/PM 깨짐 보정
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

# ---------- 유틸 ----------
def calc_accuracy(true, pred, eps=1e-9):
    denom = np.where(true == 0, eps, true)
    return float(100 - (np.abs(true - pred) / denom).mean() * 100)

def safe_ratio(num, den, eps=1e-9):
    return num / np.where(den == 0, eps, den)

# ---------- 세 가지 방법 정의 ----------
def method_scalar(sensor, grimm):
    """
    단순 곱셈: 계수 = median(grimm/sensor)
    """
    y_ratio = safe_ratio(grimm, sensor)
    # 유효성 체크
    y_ratio = y_ratio[np.isfinite(y_ratio) & (y_ratio > 0)]
    if y_ratio.size < 3:
        return None
    factor = round(float(np.median(y_ratio)), 2)
    corrected = sensor * factor
    return {"name": "scalar", "factor": factor, "corrected": corrected}

def method_xgb(X, sensor, grimm):
    """
    XGBoost: target = grimm/sensor (비음수)
    """
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
    # 음수/NaN 방지
    pred_ratio = np.clip(pred_ratio, 1e-6, None)
    factor = round(float(np.median(pred_ratio)), 2)
    # 원본 X 전체가 아니라 같은 인덱스에서만 평가(정확한 비교 위해)
    corrected = sensor[mask] * pred_ratio
    true = grimm[mask]
    acc = calc_accuracy(true, corrected)
    # 전체 구간 corrected를 같은 길이로 돌려주기 위해 원래 인덱스 기준 재구성
    corrected_full = pd.Series(np.nan, index=sensor.index)
    corrected_full.loc[mask] = corrected
    return {"name": "xgb", "factor": factor, "corrected": corrected_full, "acc_on_mask": acc}

def method_mlp(X, sensor, grimm):
    """
    MLP(딥러닝 간단형): target = grimm/sensor
    """
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
    true = grimm[mask]
    acc = calc_accuracy(true, corrected)
    corrected_full = pd.Series(np.nan, index=sensor.index)
    corrected_full.loc[mask] = corrected
    return {"name": "mlp", "factor": factor, "corrected": corrected_full, "acc_on_mask": acc}

def evaluate_best_method(X, sensor, grimm):
    """
    세 방법 모두 시도 → 정확도 가장 높은 방법 선택
    - X: 특징 (DataFrame)
    - sensor: 센서 원시값(Series)
    - grimm: 참값(Series)
    반환: {"best_name": str, "factor": float, "corrected": Series}
    """
    candidates = []

    # 1) 단순 곱셈
    m_scalar = method_scalar(sensor, grimm)
    if m_scalar is not None:
        acc = calc_accuracy(grimm, m_scalar["corrected"])
        candidates.append({"name": "scalar", "factor": m_scalar["factor"], "corrected": m_scalar["corrected"], "acc": acc})

    # 2) XGB
    m_xgb = method_xgb(X, sensor, grimm)
    if m_xgb is not None:
        acc = calc_accuracy(grimm, m_xgb["corrected"].fillna(0))  # 누락은 0으로, 분모 보호됨
        candidates.append({"name": "xgb", "factor": m_xgb["factor"], "corrected": m_xgb["corrected"], "acc": acc})

    # 3) MLP
    m_mlp = method_mlp(X, sensor, grimm)
    if m_mlp is not None:
        acc = calc_accuracy(grimm, m_mlp["corrected"].fillna(0))
        candidates.append({"name": "mlp", "factor": m_mlp["factor"], "corrected": m_mlp["corrected"], "acc": acc})

    if not candidates:
        return None

    best = max(candidates, key=lambda d: d["acc"])
    return {"best_name": best["name"], "factor": best["factor"], "corrected": best["corrected"], "acc": best["acc"]}

# ---------- 메인 보정 ----------
def pm_cal(grimm_file_path, aircok_file_path):
    grimm = prepare_grimm_data(grimm_file_path)
    aircok = prepare_aircok_data(aircok_file_path)
    merged = pd.merge(grimm, aircok, on='date', how='inner').dropna().copy()

    # 구간 정의
    bins   = [10, 30, 60, 100, 200]
    labels = ['10-30', '31-60', '61-100', '101-200']
    merged['pm25_range'] = pd.cut(merged['pm2.5'], bins=bins, labels=labels, right=True, include_lowest=True)
    merged['pm10_range'] = pd.cut(merged['pm10'],  bins=bins, labels=labels, right=True, include_lowest=True)

    # 결과 저장용
    correction_factors_pm25, correction_factors_pm10 = [], []
    methods_pm25, methods_pm10 = [], []

    # 결과 컬럼 미리 생성
    merged['corrected_pm25'] = np.nan
    merged['corrected_pm10'] = np.nan

    # ---- 루프는 딱 한 번만! (콘솔 출력 + 선택 + append 모두 여기서) ----
    for label in labels:
        # ===== PM2.5 =====
        idx25 = merged.index[merged['pm25_range'] == label]
        if len(idx25) > 0:
            sub = merged.loc[idx25]
            X_25 = sub[['pm2.5', 'pm10']]
            sensor_25 = sub['pm2.5']
            true_25   = sub['grimm_pm25']

            # 모든 방식 시도
            m_scalar = method_scalar(sensor_25, true_25)
            m_xgb    = method_xgb(X_25, sensor_25, true_25)
            m_mlp    = method_mlp(X_25, sensor_25, true_25)

            # 콘솔 출력
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
                # 정확도 최대인 방법 선택
                best_name, best_factor, best_acc, best_corr = max(candidates_25, key=lambda x: x[2])
                print(f" >> 선택됨: {best_name} (factor={best_factor}, acc={best_acc:.2f}%)")
                correction_factors_pm25.append((label, best_factor))
                methods_pm25.append((label, best_name, round(best_acc, 2)))
                # 배열/시리즈 통일
                best_corr_vals = best_corr.values if isinstance(best_corr, pd.Series) else best_corr
                merged.loc[idx25, 'corrected_pm25'] = best_corr_vals

        # ===== PM10 =====
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

    # 선택된 보정값 없는 행 제거 후 결과 집계
    merged = merged.dropna(subset=['corrected_pm25', 'corrected_pm10'])

    result = {
        "pm25_correction": correction_factors_pm25,  # 각 4개
        "pm10_correction": correction_factors_pm10,  # 각 4개
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

