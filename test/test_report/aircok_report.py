import os
import pandas as pd
from PyQt5.QtCore import QThread, pyqtSignal

# 날짜 포맷
def format_date_columns(df):
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
    return df

# 센서별 시트 준비
def prepare_simple_sheet(sensor_name, dfs, file_labels):
    merged_df = pd.DataFrame()
    valid_labels = []

    for df, label in zip(dfs, file_labels):
        if sensor_name not in df.columns or 'date' not in df.columns:
            continue

        temp_df = df[['date', sensor_name]].drop_duplicates('date').copy()
        temp_df = temp_df.rename(columns={sensor_name: label})
        valid_labels.append(label)

        if merged_df.empty:
            merged_df = temp_df
        else:
            merged_df = pd.merge(merged_df, temp_df, on='date', how='outer')

    if merged_df.empty:
        return pd.DataFrame()

    merged_df = merged_df.dropna(subset=['date'])
    merged_df['Date'] = merged_df['date'].dt.strftime('%Y-%m-%d')
    merged_df['Time'] = merged_df['date'].dt.strftime('%H:%M:%S')
    merged_df = merged_df.drop(columns=['date'])
    return merged_df[['Date', 'Time'] + valid_labels]

# 센서 정렬 순서
def get_ordered_sensors(dfs):
    priority_order = ['pm2.5', 'pm10', 'temp', 'humi', 'hcho', 'noise', 'co2', 'co', 'vocs', 'no2']
    all_sensors = {col for df in dfs for col in df.columns if col != 'date'}
    ordered = [s for s in priority_order if s in all_sensors]
    remaining = sorted(all_sensors - set(ordered))
    return ordered + remaining

# 요약 시트 생성 (파일명 = SN 기준)
def prepare_summary_sheet(dfs, file_labels):
    summary_rows = []

    for df, label in zip(dfs, file_labels):
        numeric_cols = [col for col in df.columns if col != 'date']
        if not numeric_cols:
            continue
        avg_row = df[numeric_cols].mean(numeric_only=True).round(1)
        avg_row['SN'] = label
        summary_rows.append(avg_row)

    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        cols = ['SN'] + [col for col in summary_df.columns if col != 'SN']
        return summary_df[cols]
    return pd.DataFrame()

# 메인 저장 함수
def merge_and_save_aircok_files(file_paths, output_file, update_callback=None):
    dfs, file_labels = [], []

    for i, file in enumerate(file_paths):
        try:
            df = pd.read_csv(file)
            df = format_date_columns(df)
            dfs.append(df)
            label = os.path.splitext(os.path.basename(file))[0]
            file_labels.append(label)
            if update_callback:
                update_callback(f"파일 로드: {label}", i)
        except Exception as e:
            if update_callback:
                update_callback(f"파일 로드 실패: {file} ({e})", i)
            continue

    sensor_columns = get_ordered_sensors(dfs)

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        for idx, sensor in enumerate(sensor_columns):
            sensor_df = prepare_simple_sheet(sensor, dfs, file_labels)
            if not sensor_df.empty:
                sensor_df.to_excel(writer, sheet_name=sensor[:31], index=False)
            if update_callback:
                update_callback(f"센서 시트 생성: {sensor}", len(file_paths) + idx)

        # 평균 요약 시트 생성
        summary_df = prepare_summary_sheet(dfs, file_labels)
        if not summary_df.empty:
            summary_df.to_excel(writer, sheet_name='Summary_by_SN', index=False)
            if update_callback:
                update_callback("요약 시트 생성: Summary_by_SN", len(file_paths) + len(sensor_columns))

        for i, (df, label) in enumerate(zip(dfs, file_labels)):
            df.to_excel(writer, sheet_name=label[:31], index=False)
            if update_callback:
                update_callback(f"원본 시트 저장: {label}", len(file_paths) + len(sensor_columns) + i)

# QThread 백그라운드 처리
class ReportGeneratorThread(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, aircok_files, output_file):
        super().__init__()
        self.aircok_files = aircok_files
        self.output_file = output_file

    def run(self):
        try:
            dfs = []
            file_labels = []
            num_files = len(self.aircok_files)

            file_load_weight = 0.3
            sensor_sheet_weight = 0.3
            summary_sheet_weight = 0.1
            original_sheet_weight = 0.29

            for i, file in enumerate(self.aircok_files):
                df = pd.read_csv(file)
                df = format_date_columns(df)
                dfs.append(df)
                label = os.path.splitext(os.path.basename(file))[0]
                file_labels.append(label)
                percent = int((i + 1) / num_files * file_load_weight * 100)
                self._emit_progress(f"파일 로드: {label}", percent)

            sensor_columns = get_ordered_sensors(dfs)
            num_sensors = len(sensor_columns)

            with pd.ExcelWriter(self.output_file, engine='openpyxl') as writer:
                for idx, sensor in enumerate(sensor_columns):
                    sensor_df = prepare_simple_sheet(sensor, dfs, file_labels)
                    if not sensor_df.empty:
                        sensor_df.to_excel(writer, sheet_name=sensor[:31], index=False)
                    percent = int(file_load_weight * 100 + (idx + 1) / num_sensors * sensor_sheet_weight * 100)
                    self._emit_progress(f"센서 시트 생성: {sensor}", percent)

                summary_df = prepare_summary_sheet(dfs, file_labels)
                if not summary_df.empty:
                    summary_df.to_excel(writer, sheet_name='센서 평균', index=False)
                    self._emit_progress("평균 생성", int(file_load_weight * 100 + sensor_sheet_weight * 100 + summary_sheet_weight * 100))

                for i, (df, label) in enumerate(zip(dfs, file_labels)):
                    df.to_excel(writer, sheet_name=label[:31], index=False)
                    percent = int(file_load_weight * 100 + sensor_sheet_weight * 100 + summary_sheet_weight * 100 +
                                  (i + 1) / num_files * original_sheet_weight * 100)
                    self._emit_progress(f"원본 시트 저장: {label}", percent)

            self._emit_progress("완료", 100)
            self.finished.emit(self.output_file)

        except Exception as e:
            self.error.emit(str(e))

    def _emit_progress(self, status_text, step_index):
        self.progress.emit(status_text, step_index)
