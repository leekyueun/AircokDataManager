import os
import re
import pandas as pd

def load_previous_calibration(xlsx_file):
    try:
        xl = pd.ExcelFile(xlsx_file)
        sheet_name = "보정값"
        if sheet_name not in xl.sheet_names:
            raise ValueError(f"'{sheet_name}' 시트를 찾을 수 없습니다.")
        df = xl.parse(sheet_name)
    except Exception as e:
        raise RuntimeError(f"보정 리포트를 불러올 수 없습니다: {str(e)}")

    calibrations = {}
    for _, row in df.iterrows():
        sn = str(row.get("SN"))
        if not sn or sn.strip() in ["보정 전", "보정 후"]:
            continue

        def parse_list(val):
            return [float(x.replace("*", "")) for x in str(val).split(",") if re.match(r"\*\d+(\.\d+)?", x)]

        def parse_float(val):
            try:
                return float(val)
            except:
                return 0.0

        calibrations[sn] = {
            "pm25": parse_list(row.get("pm2.5", "")),
            "pm10": parse_list(row.get("pm10", "")),
            "temp": parse_float(row.get("temp", 0)),
            "humi": parse_float(row.get("humi", 0)),
            "co2": str(row.get("co2", "") or "")
        }

    return calibrations


def apply_calibration_merge(current_report, previous_data):
    def safe_float(v):
        try:
            return float(v)
        except:
            return 1.0

    for file_path, result in current_report.items():
        sn = os.path.splitext(os.path.basename(file_path))[0]
        prev = previous_data.get(sn, {})

        for key in ["pm25", "pm10"]:
            cur_items = result.get(f"{key}_correction", [])
            cur_list = [safe_float(val) for _, val in cur_items]
            prev_list = prev.get(key, [])
            if len(cur_list) == len(prev_list):
                combined = [round(a * b, 2) for a, b in zip(prev_list, cur_list)]
                result[f"{key}_correction"] = [(i, v) for i, v in enumerate(combined)]
            else:
                result[f"{key}_correction"] = [(i, round(v, 2)) for i, v in enumerate(cur_list)]

        for key in ["temp", "humi", "co2"]:
            cur_val = result.get(f"{key}_correction", 0)
            prev_val = prev.get(key, 0)

            try:
                cur_val = float(cur_val)
            except:
                cur_val = 0.0

            try:
                prev_val = float(prev_val)
            except:
                prev_val = 0.0

            total = cur_val + prev_val
            result[f"{key}_correction"] = f"{total:+.2f}"
