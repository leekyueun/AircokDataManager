import sys
import os
import copy
import pandas as pd
from glob import glob
from datetime import datetime
from PyQt5.QtWidgets import QDialog, QFileDialog, QMessageBox
from PyQt5.uic import loadUi
from PyQt5.QtCore import QThread, pyqtSignal


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


class ConvertThread(QThread):
    progress_signal = pyqtSignal(str, str)

    def __init__(self, txt_file, dir_path, parent=None):
        super().__init__(parent)
        self.txt_file = txt_file
        self.dir_path = dir_path

    def run(self):
        try:
            resolution = os.path.basename(self.txt_file)[:4]
            content = {col: [] for col in ["date", "pm2.5", "pm10", "temp", "humi", "noise", "hcho", "co2", "co", "voc", "no2"]}
            measurement = {",10008,": "pm2.5", ",10007,": "pm10", ",20003,": "temp", ",20004,": "humi",
                           ",40001,": "noise", ",50001,": "hcho", ",30006,": "co2", ",10002,": "co",
                           ",50002,": "voc", ",10006,": "no2"}
            error_log = []
            STX = 32
            CATEGORY = 7
            DATA_LENGTH = 7
            DEV_STATE = 2
            DATA = {
                "date": 13,
                "pm2.5": CATEGORY + DATA_LENGTH + DEV_STATE,
                "pm10": CATEGORY + DATA_LENGTH + DEV_STATE,
                "temp": CATEGORY + DATA_LENGTH + DEV_STATE,
                "humi": CATEGORY + DATA_LENGTH + DEV_STATE,
                "noise": CATEGORY + DATA_LENGTH + DEV_STATE,
                "hcho": CATEGORY + DATA_LENGTH + DEV_STATE,
                "co2": CATEGORY + DATA_LENGTH + DEV_STATE,
                "co": CATEGORY + DATA_LENGTH + DEV_STATE,
                "voc": CATEGORY + DATA_LENGTH + DEV_STATE,
                "no2": CATEGORY + DATA_LENGTH + DEV_STATE
            }

            if not os.path.isfile(self.txt_file):
                self.progress_signal.emit("에러 발생", "파일이 유효하지 않습니다.")
                return

            for file in glob(self.txt_file, recursive=True):
                with open(file) as f:
                    for line in f.readlines():
                        if "\n" in line:
                            line = line[:-1]
                        if resolution in line:
                            start = STX
                            for col in content.keys():
                                if col in measurement.values():
                                    block_size = CATEGORY + DATA_LENGTH + DEV_STATE
                                    code = line[start: (start + block_size)][:CATEGORY]
                                    if code in measurement:
                                        measured_data = line[start: (start + block_size)][CATEGORY: (block_size - DEV_STATE)]
                                        content[measurement[code]].append(float(measured_data) if measured_data != "" else "")
                                elif col == "date":
                                    try:
                                        date_temp = str(line[start: (start + DATA[col])])
                                        date_temp = date_temp.lstrip(',')
                                        if date_temp[-4:-2] == "24":
                                            date_temp = date_temp[:-4] + "00" + date_temp[-2:]
                                        content[col].append(datetime.strptime(date_temp, "%Y%m%d,%H%M"))
                                    except Exception:
                                        error_log.append({"file_name": file.split("/")[-1], "line": line})
                                        content[col].append(datetime.strptime("197001010000", "%Y%m%d%H%M"))
                                else:
                                    content[col].append(line[start: (start + DATA[col])])
                                start += DATA[col]

            max_length = max(len(content[key]) for key in content.keys())
            for key in content.keys():
                while len(content[key]) < max_length:
                    content[key].append(None)

            result = copy.deepcopy(content)
            df = pd.DataFrame(result)
            save_path = os.path.join(self.dir_path, f"{os.path.basename(self.txt_file)}.csv")
            df.to_csv(save_path, index=False, encoding="cp949")
            self.progress_signal.emit("변환 완료", save_path)
        except Exception as e:
            self.progress_signal.emit("에러 발생", str(e))


class LogConverterApp(QDialog):
    def __init__(self):
        super().__init__()
        ui_path = resource_path("src/modules/parsing/parsing.ui")
        if not os.path.exists(ui_path):
            raise FileNotFoundError(f"UI 파일이 존재하지 않습니다: {ui_path}")
        loadUi(ui_path, self)
        self.setWindowTitle("Aircok Log Converter v1.3.0")


        self.dir_path = None
        self.txt_file = None
        self.convert_thread = None

        self.select_save_path.clicked.connect(self.select_path)
        self.select_aircok_file_path.clicked.connect(self.txt_file_open)
        self.conversion.clicked.connect(self.start_convert)

    def select_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "저장할 위치 선택")
        if dir_path:
            self.dir_path = dir_path
            QMessageBox.information(self, "경로 선택", f"저장 경로가 설정되었습니다:\n{self.dir_path}")

    def txt_file_open(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "변환할 파일 선택", "", "TXT Files (*.txt)")
        if file_path:
            self.txt_file = file_path
            QMessageBox.information(self, "파일 선택", f"파일이 선택되었습니다:\n{self.txt_file}")

    def start_convert(self):
        if not self.dir_path or not self.txt_file:
            QMessageBox.warning(self, "경고", "저장할 위치와 파일을 선택해 주세요!")
            return

        self.convert_thread = ConvertThread(self.txt_file, self.dir_path, self)
        self.convert_thread.finished.connect(self.cleanup_thread)
        self.convert_thread.progress_signal.connect(self.show_message)
        self.convert_thread.start()
        self.setEnabled(False)

    def cleanup_thread(self):
        self.convert_thread = None
        self.setEnabled(True)

    def show_message(self, message, file_path):
        if "변환 완료" in message:
            QMessageBox.information(self, "알림", f"{message}: {file_path}")
        else:
            QMessageBox.critical(self, "에러", f"{message}")
