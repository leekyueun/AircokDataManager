import os
import numpy as np
import pandas as pd
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QObject
from PyQt5.QtGui import QFont
import pyqtgraph as pg
import pyqtgraph.exporters  # PNG 내보내기

# --------- 공통 유틸 ---------
def _read_csv_guess(path):
    for enc in ["utf-8-sig", "cp949", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            try:
                return pd.read_csv(path, encoding=enc, sep=None, engine="python")
            except Exception:
                continue
    raise RuntimeError(f"CSV를 읽을 수 없습니다: {path}")

def _to_datetime_5min(series):
    dt = pd.to_datetime(series, errors="coerce")
    return dt.dt.round("5min")

def _setup_plot(plot):
    plot.setBackground("w")
    plot.showGrid(x=True, y=True, alpha=0.25)

    # 축 글꼴/색 설정(검은색, 진하게)
    font = QFont()
    font.setPointSize(9)
    font.setWeight(QFont.DemiBold)

    for side in ("left", "bottom"):
        ax = plot.getAxis(side)
        ax.setPen('k')
        ax.setTextPen('k')
        ax.setTickFont(font)

    # 범례
    legend = plot.addLegend()
    try:
        legend.setLabelTextColor('k')
    except Exception:
        pass

def _plot_triple(plot, df, tcol, ref_col, raw_col, corr_col, title,
                 names=("기준값", "보정 전", "보정 후")):
    plot.clear()
    _setup_plot(plot)
    plot.setTitle(f"<span style='color:black; font-weight:600'>{title}</span>")

    df = df.sort_values(tcol).dropna(subset=[tcol])
    x = df[tcol].astype("int64") // 10**9

    PEN_REF  = pg.mkPen((220, 0,   0),   width=3)                    # 빨강
    PEN_RAW  = pg.mkPen((0,   90,  255), width=3, style=Qt.DashLine) # 파랑(점선)
    PEN_CORR = pg.mkPen((0,   160, 0),   width=3)                    # 초록

    if ref_col in df.columns:
        y = pd.to_numeric(df[ref_col], errors="coerce")
        m = y.notna()
        if m.any():
            plot.plot(x[m], y[m], name=names[0], pen=PEN_REF)

    if raw_col in df.columns:
        y = pd.to_numeric(df[raw_col], errors="coerce")
        m = y.notna()
        if m.any():
            plot.plot(x[m], y[m], name=names[1], pen=PEN_RAW)

    if corr_col in df.columns:
        y = pd.to_numeric(df[corr_col], errors="coerce")
        m = y.notna()
        if m.any():
            plot.plot(x[m], y[m], name=names[2], pen=PEN_CORR)

# --------- 데이터 구성 ---------
def build_pm_series(grimm_file, aircok_file):
    # Grimm
    g = pd.read_csv(grimm_file, encoding='ISO-8859-1', skiprows=12, sep='\t', header=None)
    g.columns = ['datetime', 'pm10', 'pm2.5', 'pm1', 'inhalable', 'thoracic', 'alveolic']
    g = g[['datetime', 'pm10', 'pm2.5']].rename(
        columns={'datetime': 'date', 'pm10': 'grimm_pm10', 'pm2.5': 'grimm_pm25'}
    )
    g['date'] = g['date'].str.replace('¿ÀÀü', 'AM', regex=False).str.replace('¿ÀÈÄ', 'PM', regex=False)
    g['date'] = pd.to_datetime(g['date'], format='%Y-%m-%d %p %I:%M:%S', errors='coerce').dt.round('5min')
    g['grimm_pm25'] = pd.to_numeric(g['grimm_pm25'], errors='coerce')
    g['grimm_pm10'] = pd.to_numeric(g['grimm_pm10'], errors='coerce')
    g = g.dropna()

    # Aircok
    a = _read_csv_guess(aircok_file)
    a = a[['date', 'pm2.5', 'pm10']].copy()
    a['date'] = pd.to_datetime(a['date'], errors='coerce')
    a['pm2.5'] = pd.to_numeric(a['pm2.5'], errors='coerce')
    a['pm10']  = pd.to_numeric(a['pm10'],  errors='coerce')
    a = a.dropna()

    m = pd.merge(g, a, on='date', how='inner').dropna().copy()

    bins   = [10, 30, 60, 100, 200]
    labels = ['10-30', '31-60', '61-100', '101-200']
    m['pm25_range'] = pd.cut(m['pm2.5'], bins=bins, labels=labels, right=True, include_lowest=True)
    m['pm10_range'] = pd.cut(m['pm10'],  bins=bins, labels=labels, right=True, include_lowest=True)

    def apply_range_factor(raw, ref, rng):
        out = raw.astype(float).copy()  # dtype 경고 방지
        for lab in labels:
            idx = (rng == lab)
            if not idx.any():
                continue
            chunk = raw[idx]
            base  = ref[idx]
            ratio = (base / chunk.replace(0, pd.NA)).replace(
                [pd.NA, pd.NaT, np.inf, -np.inf], pd.NA
            ).dropna()
            if ratio.empty:
                continue
            factor = float(ratio.median())
            out.loc[idx] = raw.loc[idx] * factor
        return out

    m['pm25_raw'] = m['pm2.5']
    m['pm10_raw'] = m['pm10']
    m['pm25_corr'] = apply_range_factor(m['pm2.5'], m['grimm_pm25'], m['pm25_range'])
    m['pm10_corr'] = apply_range_factor(m['pm10'],  m['grimm_pm10'], m['pm10_range'])

    return m[['date','grimm_pm25','pm25_raw','pm25_corr','grimm_pm10','pm10_raw','pm10_corr']].copy()

# --- Testo CSV 로더: 세미콜론, 오전/오후 → AM/PM, 포맷 명시 ---
def load_testo_data(path):
    df = pd.read_csv(path, sep=";")[['날짜', '습도[%RH]', '온도[°C]']]
    df.columns = ['date', 'humidity', 'temperature']
    df['date'] = df['date'].astype(str).str.replace('오전', 'AM', regex=False).str.replace('오후', 'PM', regex=False)
    # 형식 고정: YYYY-MM-DD AM/PM hh:mm:ss
    df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d %p %I:%M:%S', errors='coerce')
    df['date'] = df['date'].dt.round('5min')
    # 숫자화
    df['humidity'] = pd.to_numeric(df['humidity'], errors='coerce')
    df['temperature'] = pd.to_numeric(df['temperature'], errors='coerce')
    return df.dropna(subset=['date', 'humidity', 'temperature'])

def build_temp_humi_series(testo_file, aircok_file):
    """온습도: 기준값=Testo(세미콜론 CSV), 보정전=Aircok, 보정후=평균 편차 보정"""
    # Testo 로드 (네가 준 포맷 그대로)
    t = load_testo_data(testo_file)

    # Aircok 로드 (date/temp/humi 필요)
    a = _read_csv_guess(aircok_file)
    required = {'date', 'temp', 'humi'}
    if not required.issubset(set(a.columns)):
        missing = required - set(a.columns)
        raise KeyError(f"Aircok 파일에 필요한 컬럼이 없습니다: {sorted(missing)}")

    a = a[['date', 'temp', 'humi']].copy()
    a['date'] = pd.to_datetime(a['date'], errors='coerce').dt.round('5min')
    a['temp'] = pd.to_numeric(a['temp'], errors='coerce')
    a['humi'] = pd.to_numeric(a['humi'], errors='coerce')
    a = a.dropna(subset=['date', 'temp', 'humi'])

    # 병합
    m = pd.merge(t, a, on='date', how='inner').dropna().copy()
    if m.empty:
        raise ValueError("Testo와 Aircok의 시간대가 맞는 교집합이 없습니다. (5분 단위 반올림 기준)")

    # 평균 바이어스 보정
    temp_bias = (m['temperature'] - m['temp']).mean()
    humi_bias = (m['humidity']    - m['humi']).mean()

    m['temp_raw']  = m['temp']
    m['temp_corr'] = m['temp'] + temp_bias
    m['humi_raw']  = m['humi']
    m['humi_corr'] = m['humi'] + humi_bias

    return m[['date','temperature','temp_raw','temp_corr','humidity','humi_raw','humi_corr']].copy()



def build_co2_series(wolfsense_file, aircok_file):
    w = pd.read_excel(wolfsense_file)
    w = w[['Date Time','Carbon Dioxide ppm']].rename(columns={'Date Time':'date','Carbon Dioxide ppm':'co2'})
    w['date'] = pd.to_datetime(w['date'], format='%Y-%m-%d %p %I:%M:%S')
    w['date'] = w['date'].dt.round('5min')
    w['co2']  = pd.to_numeric(w['co2'], errors="coerce").clip(lower=400)

    a = _read_csv_guess(aircok_file)[['date','co2']].copy()
    a['date'] = pd.to_datetime(a['date'], errors='coerce')
    a['co2']  = pd.to_numeric(a['co2'], errors="coerce").clip(lower=400)

    m = pd.merge(w, a, on='date', how='inner').dropna().copy()
    bias = (m['co2_x'] - m['co2_y']).mean()
    m['co2_raw']  = m['co2_y']
    m['co2_corr'] = m['co2_y'] + bias
    m['co2_ref']  = m['co2_x']

    return m[['date','co2_ref','co2_raw','co2_corr']].copy()

# --------- 다이얼로그 ---------
class GraphCompareDialog(QDialog):
    def __init__(
        self,
        parent=None,
        aircok_file=None,          # 단일 파일 모드(호환용)
        grimm_file=None,
        testo_file=None,
        wolfsense_file=None,
        aircok_files=None,         # 여러 파일
        start_index: int = 0
    ):
        super().__init__(parent)
        self.setWindowTitle("그래프 비교")
        self.resize(1200, 680)

        # 파일 세트 설정
        if aircok_files and len(aircok_files) > 0:
            self.aircok_files = aircok_files
            self.idx = max(0, min(start_index, len(aircok_files) - 1))
        else:
            self.aircok_files = [aircok_file] if aircok_file else []
            self.idx = 0

        self.grimm_file     = grimm_file
        self.testo_file     = testo_file
        self.wolfsense_file = wolfsense_file

        self.plot = pg.PlotWidget()
        _setup_plot(self.plot)

        # 상단 바: 파일 탐색 + 항목 선택
        top = QHBoxLayout()
        self.info = QLabel("-")

        self.btn_prev   = QPushButton("◀ 이전")
        self.file_combo = QComboBox()
        self.btn_next   = QPushButton("다음 ▶")

        self.sel        = QComboBox()
        self.btn_redraw = QPushButton("다시 그리기")
        self.btn_export = QPushButton("PNG로 저장")

        # 파일 콤보 채우기 (전체 경로 표시, 한 번에 많이 보이도록)
        self.file_combo.clear()
        self.file_combo.addItems(self.aircok_files)
        self.file_combo.setMaxVisibleItems(min(len(self.aircok_files), 50))
        self.file_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.file_combo.setMinimumWidth(520)
        self.file_combo.view().setUniformItemSizes(True)
        for i, p in enumerate(self.aircok_files):
            self.file_combo.setItemData(i, p, Qt.ToolTipRole)

        top.addWidget(self.info)
        top.addStretch(1)
        top.addWidget(self.btn_prev)
        top.addWidget(self.file_combo)
        top.addWidget(self.btn_next)

        top.addSpacing(16)
        top.addWidget(QLabel("항목:"))
        self.sel.addItems(["PM2.5","PM10","Temp","Humi","CO2"])
        top.addWidget(self.sel)
        top.addWidget(self.btn_redraw)
        top.addWidget(self.btn_export)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.plot)

        # 시그널
        self.btn_redraw.clicked.connect(self.redraw)
        self.btn_export.clicked.connect(self.export_png)
        self.sel.currentIndexChanged.connect(self.redraw)
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_next.clicked.connect(self._go_next)
        self.file_combo.activated.connect(self._go_index)  # 한 번 클릭으로 바로 전환

        self._install_key_nav()
        self._sync_file_ui()
        self.redraw()

    # ---- 파일 네비게이션 ----
    def _current_aircok_file(self):
        if not self.aircok_files:
            return None
        return self.aircok_files[self.idx]

    def _sync_file_ui(self):
        current = self._current_aircok_file()
        self.info.setText(f"파일: {os.path.basename(current) if current else '-'}")
        if 0 <= self.idx < self.file_combo.count():
            if self.file_combo.currentIndex() != self.idx:
                self.file_combo.blockSignals(True)
                self.file_combo.setCurrentIndex(self.idx)
                self.file_combo.blockSignals(False)

    def _go_prev(self):
        if not self.aircok_files: return
        self.idx = (self.idx - 1) % len(self.aircok_files)
        self._sync_file_ui()
        self.redraw()

    def _go_next(self):
        if not self.aircok_files: return
        self.idx = (self.idx + 1) % len(self.aircok_files)
        self._sync_file_ui()
        self.redraw()

    def _go_index(self, i):
        if not self.aircok_files: return
        self.idx = max(0, min(int(i), len(self.aircok_files) - 1))
        self._sync_file_ui()
        self.redraw()

    def _install_key_nav(self):
        class _Filter(QObject):
            def __init__(self, outer):
                super().__init__(); self.outer = outer
            def eventFilter(self, obj, ev):
                if ev.type() == ev.KeyPress:
                    if ev.key() in (Qt.Key_Left, Qt.Key_A):
                        self.outer._go_prev(); return True
                    if ev.key() in (Qt.Key_Right, Qt.Key_D):
                        self.outer._go_next(); return True
                return False
        self._f = _Filter(self)
        self.installEventFilter(self._f)

    # ---- 그리기 ----
    def redraw(self):
        try:
            current_aircok = self._current_aircok_file()
            item = self.sel.currentText()

            if item in ("PM2.5","PM10"):
                if not (self.grimm_file and current_aircok):
                    self.plot.clear(); self.plot.setTitle("Grimm/Aircok 파일이 필요합니다."); return
                df = build_pm_series(self.grimm_file, current_aircok)
                if item == "PM2.5":
                    _plot_triple(self.plot, df, "date", "grimm_pm25", "pm25_raw", "pm25_corr", "PM2.5 비교")
                else:
                    _plot_triple(self.plot, df, "date", "grimm_pm10", "pm10_raw", "pm10_corr", "PM10 비교")

            elif item == "Temp":
                if not (self.testo_file and current_aircok):
                    self.plot.clear(); self.plot.setTitle("Testo/Aircok 파일이 필요합니다."); return
                df = build_temp_humi_series(self.testo_file, current_aircok)
                _plot_triple(self.plot, df, "date", "temperature", "temp_raw", "temp_corr",
                             "온도 비교", names=("기준값(℃)","보정 전","보정 후"))

            elif item == "Humi":
                if not (self.testo_file and current_aircok):
                    self.plot.clear(); self.plot.setTitle("Testo/Aircok 파일이 필요합니다."); return
                df = build_temp_humi_series(self.testo_file, current_aircok)
                _plot_triple(self.plot, df, "date", "humidity", "humi_raw", "humi_corr",
                             "습도 비교", names=("기준값(%RH)","보정 전","보정 후"))

            elif item == "CO2":
                if not (self.wolfsense_file and current_aircok):
                    self.plot.clear(); self.plot.setTitle("Wolfsense/Aircok 파일이 필요합니다."); return
                df = build_co2_series(self.wolfsense_file, current_aircok)
                _plot_triple(self.plot, df, "date", "co2_ref", "co2_raw", "co2_corr",
                             "CO₂ 비교", names=("기준값(ppm)","보정 전","보정 후"))

        except Exception as e:
            self.plot.clear()
            self.plot.setTitle(f"오류: {e}")

    # ---- 내보내기 ----
    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "PNG로 저장", "graph.png", "PNG Files (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            exporter = pg.exporters.ImageExporter(self.plot.plotItem)
            exporter.export(path)
            QMessageBox.information(self, "저장 완료", f"저장됨: {path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패: {e}")
