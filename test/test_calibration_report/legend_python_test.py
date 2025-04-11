import os
import pandas as pd

def format_date_columns(df):
    for col in df.select_dtypes(include=['object', 'datetime']).columns:
        try:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            continue
    return df

def prepare_simple_sheet(column_name, dfs, file_labels):
    merged_df = pd.DataFrame()
    for df, label in zip(dfs, file_labels):
        temp_df = df[['date', column_name]].rename(columns={column_name: label})
        if merged_df.empty:
            merged_df = temp_df
        else:
            merged_df = pd.merge(merged_df, temp_df, on="date", how="outer", validate="many_to_many")

    merged_df = merged_df.rename(columns={"date": "Date"})
    merged_df[['Date', 'Time']] = merged_df['Date'].str.split(' ', expand=True)
    merged_df['Time'] = pd.to_datetime(merged_df['Time'], format='%H:%M:%S.%f', errors='coerce').dt.strftime('%H:%M:%S')
    merged_df = merged_df.dropna()
    merged_df = merged_df[['Date', 'Time'] + file_labels]

    return merged_df

def merge_and_save_aircok_files(file_paths, output_file):
    columns = ['pm25', 'pm10', 'temp', 'humi', 'org_hcho', 'noise', 'co2', 'co', 'org_vocs', 'no2']
    adjusted_columns = ['pm2.5', 'pm10', 'temp', 'humi', 'hcho', 'noise', 'co2', 'co', 'vocs', 'no2']
    column_mapping = dict(zip(columns, adjusted_columns))

    dfs = [pd.read_csv(file) for file in file_paths]
    file_labels = [os.path.splitext(os.path.basename(file))[0] for file in file_paths]

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        for original, adjusted in column_mapping.items():
            specific_sheet = prepare_simple_sheet(original, dfs, file_labels)
            if not specific_sheet.empty:
                specific_sheet.to_excel(writer, sheet_name=adjusted, index=False)

        for df, label in zip(dfs, file_labels):
            df = format_date_columns(df)
            df.to_excel(writer, sheet_name=label, index=False)

if __name__ == "__main__":
    file_paths = [
        r"C:/Users/User/Desktop/test/2305test07.csv",
        r"C:/Users/User/Desktop/test/2305test09.csv"
    ]
    output_file = r"legend.xlsx"

    merge_and_save_aircok_files(file_paths, output_file)
    print(f"보고서가 저장되었습니다: {output_file}")
