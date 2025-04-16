import pandas as pd

def co2_calibration(co2_file_path, aircok_file_path):
    co2_data = pd.read_excel(co2_file_path)
    co2_data = co2_data[['Date Time', 'Carbon Dioxide ppm']]
    co2_data.columns = ['date', 'co2']
    co2_data['date'] = pd.to_datetime(co2_data['date'], format='%Y-%m-%d %p %I:%M:%S')
    co2_data['date'] = co2_data['date'].dt.round('5min')
    co2_data['co2'] = co2_data['co2'].clip(lower=400)

    aircok_data = pd.read_csv(aircok_file_path)
    aircok_data = aircok_data[['date', 'co2']].copy()
    aircok_data['date'] = pd.to_datetime(aircok_data['date'])
    aircok_data['co2'] = aircok_data['co2'].clip(lower=400)

    merged = pd.merge(co2_data, aircok_data, on='date', how='inner').dropna()

    pre_error = (merged['co2_x'] - merged['co2_y']).abs().mean()
    pre_acc = 100 - (pre_error / merged['co2_x'].mean()) * 100

    mean_bias = (merged['co2_x'] - merged['co2_y']).mean()
    aircok_data['co2_corrected'] = aircok_data['co2'] + mean_bias

    corrected = pd.merge(co2_data, aircok_data[['date', 'co2_corrected']], on='date', how='inner').dropna()
    post_error = (corrected['co2'] - corrected['co2_corrected']).abs().mean()
    post_acc = 100 - (post_error / corrected['co2'].mean()) * 100

    result = {
        "co2_correction_str": f"{'+' if mean_bias >= 0 else ''}{round(mean_bias, 2)}",
        "pre_correction_accuracy": round(pre_acc, 2),
        "post_correction_accuracy": round(post_acc, 2)
    }

    print(result)
    return result
