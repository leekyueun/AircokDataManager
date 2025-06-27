import sys
import os
import re
import traceback
import pandas as pd
from PyQt5.uic import loadUi
from PyQt5.QtWidgets import (
    QApplication, QWidget, QFileDialog, QMessageBox,
    QDialog, QVBoxLayout, QLabel, QProgressBar
)
from PyQt5.QtCore import QDateTime, Qt
from sqlalchemy import create_engine
from sqlalchemy.exc import ProgrammingError
from dotenv import load_dotenv

base_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(base_dir, ".env"))

class ProgressDialog(QDialog):
    def __init__(self, total, parent=None):
        super().__init__(parent)
        self.setWindowTitle("다운로드 진행 중...")
        self.setFixedSize(350, 100)

        self.layout = QVBoxLayout()
        self.label = QLabel("다운로드 중입니다...")
        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(total)

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.progress)
        self.setLayout(self.layout)

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

    def update_progress(self, value, current_filename):
        self.progress.setValue(value)
        self.label.setText(f"{current_filename} 저장 중... ({value}/{self.progress.maximum()})")

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class DataDownloader(QWidget):
    def __init__(self):
        super().__init__()
        ui_path = resource_path('src/modules/downloader/data_downloader.ui')
        loadUi(ui_path, self)

        self.dateTimeEdit.setCalendarPopup(True)
        self.dateTimeEdit_2.setCalendarPopup(True)
        self.dateTimeEdit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dateTimeEdit_2.setDisplayFormat("yyyy-MM-dd HH:mm")

        now = QDateTime.currentDateTime()
        self.dateTimeEdit.setDateTime(now)
        self.dateTimeEdit_2.setDateTime(now)

        self.downloadButton.clicked.connect(self.download_data)
        self.checkAllBox.stateChanged.connect(self.toggle_all_checks)

    def toggle_all_checks(self, state):
        for i in range(self.sensorGrid.count()):
            widget = self.sensorGrid.itemAt(i).widget()
            if hasattr(widget, 'setChecked'):
                widget.setChecked(state)

    def get_db_engine(self):
        db_choice = self.dbSelectCombo.currentText()

        if db_choice == "운영 DB":
            db_url = os.getenv("DB_URL_PROD")
        elif db_choice == "테스트 DB":
            db_url = os.getenv("DB_URL_TEST")
        else:
            QMessageBox.critical(self, "오류", "DB를 선택해주세요.")
            return None

        print(f"선택된 DB: {db_choice}")
        print(f"로드된 DB URL: {db_url}")

        if not db_url or db_url.strip() == "":
            QMessageBox.critical(self, "오류", f"{db_choice}의 DB URL을 .env 파일에서 찾을 수 없습니다.")
            return None

        try:
            return create_engine(db_url, echo=True)
        except Exception as e:
            QMessageBox.critical(self, "DB 접속 오류", f"DB URL 형식 또는 접속 문제가 발생했습니다:\n{e}")
            traceback.print_exc()
            return None

    def download_data(self):
        sn_start = self.snStartEdit.text().strip()
        sn_end = self.snEndEdit.text().strip()
        start_dt = self.dateTimeEdit.dateTime().toString("yyyy-MM-dd HH:mm")
        end_dt = self.dateTimeEdit_2.dateTime().toString("yyyy-MM-dd HH:mm")

        sensor_map = {
            "check_PM25": "pm25 AS \"pm2.5\"",
            "check_PM10": "pm10",
            "check_TEMP": "tem AS temp",
            "check_HUMI": "hum AS humi",
            "check_HCHO": "org_hcho AS hcho",
            "check_NOISE": "noise",
            "check_CO2": "co2",
            "check_CO": "co",
            "check_VOC": "org_vocs AS vocs",
            "check_NO2": "no2"
        }

        selected_columns = ["data_reg_dt AS date"]
        for key, column in sensor_map.items():
            if getattr(self, key).isChecked():
                selected_columns.append(column)

        if len(selected_columns) == 1:
            QMessageBox.warning(self, "오류", "센서를 하나 이상 선택해주세요.")
            return

        folder = QFileDialog.getExistingDirectory(self, "저장할 폴더 선택")
        if not folder:
            return

        if len(sn_start) != 10:
            QMessageBox.critical(self, "오류", "SN은 10자리여야 합니다.")
            return

        match = re.search(r"\d+$", sn_start)
        if not match:
            QMessageBox.critical(self, "오류", "SN에 숫자 부분이 없습니다.")
            return

        number_part = match.group()
        number_index = match.start()
        prefix_code = sn_start[:number_index]
        prefix = "dvc_" + prefix_code.lower()

        try:
            start_num = int(number_part)
            end_num = int(sn_end)
        except:
            QMessageBox.critical(self, "오류", "숫자 범위가 잘못되었습니다.")
            return

        engine = self.get_db_engine()
        if engine is None:
            return

        total = end_num - start_num + 1
        progress_dialog = ProgressDialog(total, self)
        progress_dialog.show()

        failures = []

        for idx, i in enumerate(range(start_num, end_num + 1), 1):
            sn = f"{prefix}{str(i).zfill(len(number_part))}"
            filename = f"{sn.replace('dvc_', '')}.csv"
            file_path = os.path.join(folder, filename)

            query = f"""
            SELECT {', '.join(selected_columns)}
            FROM aircok_device.{sn}
            WHERE data_reg_dt >= '{start_dt}' AND data_reg_dt <= '{end_dt}'
            ORDER BY data_reg_dt
            """

            try:
                df = pd.read_sql_query(query, engine)
                df.to_csv(file_path, index=False, encoding='utf-8-sig')
                print(f"[{idx}] {filename} 저장 완료")
            except ProgrammingError as pe:
                print(f"[{idx}] {filename} 실패 (테이블 없음): {pe}")
                failures.append(filename)
                continue
            except Exception as e:
                print(f"[{idx}] {filename} 실패: {e}")
                traceback.print_exc()
                failures.append(filename)
                continue

            if progress_dialog and progress_dialog.isVisible():
                progress_dialog.update_progress(idx, filename)
            QApplication.processEvents()

        if progress_dialog and progress_dialog.isVisible():
            progress_dialog.close()

        if failures:
            QMessageBox.warning(self, "완료 (일부 실패)", f"다음 테이블 저장 실패:\n{', '.join(failures)}")
        else:
            QMessageBox.information(self, "완료", "데이터 다운로드가 완료되었습니다.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DataDownloader()
    window.show()
    sys.exit(app.exec_())
