import os
import math
import pandas as pd
import matplotlib.pyplot as plt
from typing import List, Tuple, Optional
import numpy as np

# --------- 내부 유틸 ---------
def _downsample(df: pd.DataFrame, max_points: int, time_col: str) -> pd.DataFrame:
    df = df.sort_values(time_col)
    if len(df) > max_points:
        step = math.ceil(len(df) / max_points)
        df = df.iloc[::step, :]
    return df

def _metrics(y_true: np.ndarray, y_pred: np.ndarray):
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if mask.sum() < 3:
        return {"RMSE": np.nan, "MAE": np.nan, "R2": np.nan}
    yt, yp = y_true[mask], y_pred[mask]
    rmse = np.sqrt(np.mean((yt - yp) ** 2))
    mae  = np.mean(np.abs(yt - yp))
    # R2 (SStot가 0인 경우 방어)
    ss_res = np.sum((yt - yp) ** 2)
    ss_tot = np.sum((yt - np.mean(yt)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"RMSE": rmse, "MAE": mae, "R2": r2}

def _annotate_metrics(ax, metrics: dict, title_suffix: str = ""):
    txt = f"RMSE: {metrics['RMSE']:.3f}\nMAE: {metrics['MAE']:.3f}\nR²: {metrics['R2']:.3f}"
    ax.text(0.02, 0.98, txt, transform=ax.transAxes, va="top", ha="left",
            bbox=dict(boxstyle="round", alpha=0.15), fontsize=9)
    if title_suffix:
        ax.set_title(ax.get_title() + f" | {title_suffix}")

# --------- 공개 API ---------
def generate_ref_comparison_plots(
    df: pd.DataFrame,
    out_dir: str,
    device_col: str = "device_id",
    time_col: str = "date",
    # (raw_col, cal_col, ref_col, pretty_name)
    metrics: List[Tuple[str, str, str, str]] = (
        ("pm25_raw", "pm25_cal", "pm25_ref", "PM2.5"),
        ("pm10_raw", "pm10_cal", "pm10_ref", "PM10"),
        ("temp_raw", "temp_cal", "temp_ref", "TEMP"),
        ("humi_raw", "humi_cal", "humi_ref", "HUMI"),
        ("co2_raw",  "co2_cal",  "co2_ref",  "CO2"),
    ),
    max_points: int = 5000,
    line_width: float = 1.2,
    include_scatter: bool = True,
    scatter_sample: Optional[int] = 8000,  # 산점도 점수 과밀 시 샘플링
) -> list:
    """
    기준장비(reference)와 비교하는 그래프 생성.
    각 항목에 대해:
      1) 시계열: Before(Ref vs Raw), After(Ref vs Cal) 각 1장
      2) (옵션) 산점도: Ref vs Raw, Ref vs Cal 각 1장
    return: 저장된 이미지 경로 리스트
    """
    os.makedirs(out_dir, exist_ok=True)
    img_paths = []

    # 장비 축 설정
    if device_col in df.columns:
        devices = df[device_col].dropna().unique().tolist()
    else:
        df["_single"] = "_single"
        device_col = "_single"
        devices = ["_single"]

    for dev in devices:
        sub = df[df[device_col] == dev]
        if sub.empty:
            continue
        sub = _downsample(sub, max_points, time_col)

        for raw_col, cal_col, ref_col, pretty in metrics:
            has_raw = raw_col in sub.columns
            has_cal = cal_col in sub.columns
            has_ref = ref_col in sub.columns
            if not has_ref:
                continue

            # ----- 시계열: Before (Ref vs Raw) -----
            if has_raw:
                fig = plt.figure(figsize=(10, 4.2))
                ax = plt.gca()
                ax.plot(sub[time_col], sub[ref_col], linewidth=line_width, label=f"{pretty} Ref")
                ax.plot(sub[time_col], sub[raw_col], linewidth=line_width, label=f"{pretty} Raw")
                ax.set_title(f"{dev} | {pretty} - Before (Ref vs Raw)")
                ax.set_xlabel("Time")
                ax.set_ylabel(pretty)
                ax.legend()
                plt.tight_layout()
                fname = f"{dev}_{pretty}_before_ref_vs_raw.png".replace(" ", "")
                path = os.path.join(out_dir, fname)
                fig.savefig(path, dpi=150)
                plt.close(fig)
                img_paths.append(path)

            # ----- 시계열: After (Ref vs Cal) -----
            if has_cal:
                fig = plt.figure(figsize=(10, 4.2))
                ax = plt.gca()
                ax.plot(sub[time_col], sub[ref_col], linewidth=line_width, label=f"{pretty} Ref")
                ax.plot(sub[time_col], sub[cal_col], linewidth=line_width, label=f"{pretty} Cal")
                ax.set_title(f"{dev} | {pretty} - After (Ref vs Cal)")
                ax.set_xlabel("Time")
                ax.set_ylabel(pretty)
                ax.legend()
                plt.tight_layout()
                fname = f"{dev}_{pretty}_after_ref_vs_cal.png".replace(" ", "")
                path = os.path.join(out_dir, fname)
                fig.savefig(path, dpi=150)
                plt.close(fig)
                img_paths.append(path)

            if include_scatter:
                # 산점도는 ref를 X, raw/cal을 Y로
                if scatter_sample and len(sub) > scatter_sample:
                    sub_sc = sub.sample(scatter_sample, random_state=42)
                else:
                    sub_sc = sub

                # ----- 산점도: Ref vs Raw -----
                if has_raw:
                    x = sub_sc[ref_col].to_numpy()
                    y = sub_sc[raw_col].to_numpy()
                    m = _metrics(x, y)

                    fig = plt.figure(figsize=(4.8, 4.8))
                    ax = plt.gca()
                    ax.scatter(x, y, s=8, alpha=0.6)
                    # y=x 기준선
                    lims = [np.nanmin([x, y]), np.nanmax([x, y])]
                    if np.isfinite(lims).all():
                        ax.plot(lims, lims)
                        ax.set_xlim(lims)
                        ax.set_ylim(lims)
                    ax.set_xlabel(f"{pretty} Ref")
                    ax.set_ylabel(f"{pretty} Raw")
                    ax.set_title(f"{dev} | {pretty} - Scatter (Raw)")
                    _annotate_metrics(ax, m)
                    plt.tight_layout()
                    fname = f"{dev}_{pretty}_scatter_raw.png".replace(" ", "")
                    path = os.path.join(out_dir, fname)
                    fig.savefig(path, dpi=150)
                    plt.close(fig)
                    img_paths.append(path)

                # ----- 산점도: Ref vs Cal -----
                if has_cal:
                    x = sub_sc[ref_col].to_numpy()
                    y = sub_sc[cal_col].to_numpy()
                    m = _metrics(x, y)

                    fig = plt.figure(figsize=(4.8, 4.8))
                    ax = plt.gca()
                    ax.scatter(x, y, s=8, alpha=0.6)
                    lims = [np.nanmin([x, y]), np.nanmax([x, y])]
                    if np.isfinite(lims).all():
                        ax.plot(lims, lims)
                        ax.set_xlim(lims)
                        ax.set_ylim(lims)
                    ax.set_xlabel(f"{pretty} Ref")
                    ax.set_ylabel(f"{pretty} Cal")
                    ax.set_title(f"{dev} | {pretty} - Scatter (Cal)")
                    _annotate_metrics(ax, m)
                    plt.tight_layout()
                    fname = f"{dev}_{pretty}_scatter_cal.png".replace(" ", "")
                    path = os.path.join(out_dir, fname)
                    fig.savefig(path, dpi=150)
                    plt.close(fig)
                    img_paths.append(path)

    return img_paths


def add_images_to_excel(
    writer: pd.ExcelWriter,
    image_paths: list,
    sheet_name: str = "comparison",
    start_row: int = 1,
    images_per_row: int = 2,
    cell_width: int = 32,
    row_height: int = 220,
):
    """
    pandas.ExcelWriter(xlsxwriter 엔진)로 열린 상태에서 image_paths를 격자로 삽입.
    """
    wb = writer.book
    ws = wb.add_worksheet(sheet_name)

    title_fmt = wb.add_format({"bold": True, "font_size": 14})
    ws.write(0, 0, "Reference Comparison (Timeseries & Scatter)", title_fmt)

    for c in range(images_per_row * 8):
        ws.set_column(c, c, cell_width)

    per_img_cols = 8
    r = start_row
    for idx, p in enumerate(image_paths):
        row = r + (idx // images_per_row) * 15
        col = (idx % images_per_row) * per_img_cols
        for rr in range(row, row + 14):
            ws.set_row(rr, row_height)
        ws.insert_image(row, col, p, {"x_scale": 1.0, "y_scale": 1.0, "positioning": 1})
