import pandas as pd

def load_testo_data(path):
    df = pd.read_csv(path, sep=";")[['날짜', '습도[%RH]', '온도[°C]']]
    df.columns = ['date', 'humidity', 'temperature']
    df['date'] = df['date'].str.replace('오전', 'AM', regex=False).str.replace('오후', 'PM', regex=False)
    df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d %p %I:%M:%S', errors='coerce')
    df['date'] = df['date'].dt.round('5min')
    return df.dropna()

def load_aircok_data(path):
    df = pd.read_csv(path, usecols=['date', 'temp', 'humi'])
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    return df.dropna()

def calculate_correction(true_avg, raw_avg, values, tolerance=0.01):
    correction = true_avg - raw_avg
    if abs(correction) < tolerance:
        corrected = values
        corrected_accuracy = 100 - abs(true_avg - raw_avg) / true_avg * 100
        correction_str = "0"
    else:
        corrected = values + correction
        corrected_mean = corrected.mean()
        corrected_error = abs(true_avg - corrected_mean) / true_avg * 100
        corrected_accuracy = 100 - corrected_error
        correction_str = f"{'+' if correction >= 0 else ''}{round(correction, 2)}"
    return corrected, correction_str, round(corrected_accuracy, 2)

def temp_humi_cal(testo_file_path, aircok_file_path):
    testo = load_testo_data(testo_file_path)
    aircok = load_aircok_data(aircok_file_path)
    merged = pd.merge(testo, aircok, on='date', how='inner').dropna()

    t_temp, a_temp = merged['temperature'].mean(), merged['temp'].mean()
    t_humi, a_humi = merged['humidity'].mean(), merged['humi'].mean()

    temp_acc = 100 - abs(t_temp - a_temp) / t_temp * 100
    humi_acc = 100 - abs(t_humi - a_humi) / t_humi * 100

    temp_corr, temp_str, temp_acc_post = calculate_correction(t_temp, a_temp, merged['temp'])
    humi_corr, humi_str, humi_acc_post = calculate_correction(t_humi, a_humi, merged['humi'])

    result = {
        "temp_correction": temp_str,
        "temp_accuracy": round(temp_acc, 2),
        "temp_corrected_accuracy": temp_acc_post,
        "humi_correction": humi_str,
        "humi_accuracy": round(humi_acc, 2),
        "humi_corrected_accuracy": humi_acc_post
    }

    print(result)
    return result
