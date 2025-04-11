from datetime import datetime
import numpy as np
import pandas as pd
import xgboost as xgb

def prepare_grimm_data(path):
    df = pd.read_csv(path, encoding='ISO-8859-1', skiprows=12, sep='\t', header=None)
    df.columns = ['datetime', 'pm10', 'pm2.5', 'pm1', 'inhalable', 'thoracic', 'alveolic']
    df = df[['datetime', 'pm10', 'pm2.5']].rename(columns={'datetime': 'date', 'pm10': 'grimm_pm10', 'pm2.5': 'grimm_pm25'})

    df['date'] = df['date'].str.replace('¿ÀÀü', 'AM', regex=False).str.replace('¿ÀÈÄ', 'PM', regex=False)
    df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d %p %I:%M:%S', errors='coerce').dt.round('5min')
    df['grimm_pm25'] = pd.to_numeric(df['grimm_pm25'], errors='coerce')
    df['grimm_pm10'] = pd.to_numeric(df['grimm_pm10'], errors='coerce')
    return df.dropna()

def prepare_aircok_data(path):
    df = pd.read_csv(path, usecols=['date', 'pm25', 'pm10'])
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    return df.dropna()

def train_and_predict_correction_factor(X, y):
    if len(X) < 3 or (y <= 0).any():
        return None
    model = xgb.XGBRegressor(objective='reg:squarederror', verbosity=0)
    model.fit(X, y)
    pred = model.predict(X)
    return round(float(np.median(pred)), 2)

def pm_cal(grimm_file_path, aircok_file_path):
    grimm = prepare_grimm_data(grimm_file_path)
    aircok = prepare_aircok_data(aircok_file_path)
    merged = pd.merge(grimm, aircok, on='date', how='inner').dropna()

    bins = [10, 30, 60, 100, 200]
    labels = ['10-30', '31-60', '61-100', '101-200']
    merged['pm25_range'] = pd.cut(merged['pm25'], bins=bins, labels=labels)
    merged['pm10_range'] = pd.cut(merged['pm10'], bins=bins, labels=labels)

    correction_factors_pm25, correction_factors_pm10 = [], []

    for label in labels:
        # PM2.5
        subset_25 = merged[merged['pm25_range'] == label]
        if not subset_25.empty:
            X_25 = subset_25[['pm25', 'pm10']]
            y_25 = subset_25['grimm_pm25'] / subset_25['pm25']
            factor_25 = train_and_predict_correction_factor(X_25, y_25)
            if factor_25:
                correction_factors_pm25.append((label, factor_25))
                merged.loc[merged['pm25_range'] == label, 'corrected_pm25'] = subset_25['pm25'] * factor_25

        # PM10
        subset_10 = merged[merged['pm10_range'] == label]
        if not subset_10.empty:
            X_10 = subset_10[['pm25', 'pm10']]
            y_10 = subset_10['grimm_pm10'] / subset_10['pm10']
            factor_10 = train_and_predict_correction_factor(X_10, y_10)
            if factor_10:
                correction_factors_pm10.append((label, factor_10))
                merged.loc[merged['pm10_range'] == label, 'corrected_pm10'] = subset_10['pm10'] * factor_10

    merged = merged.dropna(subset=['corrected_pm25', 'corrected_pm10'])

    def calc_accuracy(true, pred):
        return 100 - (abs(true - pred) / true).mean() * 100

    result = {
        "pm25_correction": correction_factors_pm25,
        "pm10_correction": correction_factors_pm10,
        "pm25_accuracy_pre": round(calc_accuracy(merged['grimm_pm25'], merged['pm25']), 2),
        "pm25_accuracy_post": round(calc_accuracy(merged['grimm_pm25'], merged['corrected_pm25']), 2),
        "pm10_accuracy_pre": round(calc_accuracy(merged['grimm_pm10'], merged['pm10']), 2),
        "pm10_accuracy_post": round(calc_accuracy(merged['grimm_pm10'], merged['corrected_pm10']), 2)
    }

    print(result)
    return result
