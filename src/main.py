# 2024-11-19
# 파일 선택 기능 개발 완료
# 파일 보정 기능 개발 완료
# 여러개 파일 보정 기능 개발 완료
#
# 2024-11-22
# co2 보정 부분 버그 수정
#
# 2024-12-03
# 에어콕 데이터 보고서(데이터 합병) 기능 개발 완료
#
# 2024-12-04
# LCD 로그 데이터 변환 기능 연결
#
# 2024-12-05
# 초기화 기능 추가
#
# 2025-03-28
# 데이터 보고서 버그 수정 및 성능 개선(fuck)
# 에어콕 데이터 다운로드 기능 추가
#
# 2025-04-02
# 데이터 다운로더 운영/테스트 DB 전환 기능 추가
#
# 2025-04-09
# 전체 기능 최적화 및 성능 개선
#
# 2025-04-15
# 보고서 센서 평균 추가
# 보정 결과 다운로드 기능 추가
#
# 2025-04-16
# 미세먼지 보정 부분 수정
# co2 보정 단위 버그 수정
#
# 2025-05-29
# 누적 보정값 계산 기능 추가
#
# 2025-05-30 ~
# 온습도 단위 버그 수정
# 파일 폴더 구조 최적화
# 변수명 최적화

import os
import sys
from PyQt5 import uic
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QDialog,
    QProgressDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from src.calibration.co2 import co2_cal
from src.calibration.pm import pm_cal
from src.calibration.temp_humi import temp_humi_cal
from src.report.aircok_report import ReportGeneratorThread
from modules.parsing.lcd_parsing import LogConverterApp
from modules.downloader.data_downloader import DataDownloader
from src.report.calibration_report import generate_calibration_report as export_calibration_report
from src.calibration.cumulative_calibration import load_previous_calibration, apply_calibration_merge


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class CalibrationThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, aircok_files, grimm_file, testo_file, wolfsense_file):
        super().__init__()
        self.aircok_files = aircok_files
        self.grimm_file = grimm_file
        self.testo_file = testo_file
        self.wolfsense_file = wolfsense_file

    def run(self):
        try:
            results = {}
            for aircok_file in self.aircok_files:
                file_result = {}
                if self.grimm_file:
                    file_result.update(pm_cal(self.grimm_file, aircok_file))
                if self.testo_file:
                    file_result.update(temp_humi_cal(self.testo_file, aircok_file))
                if self.wolfsense_file:
                    file_result.update(co2_cal(self.wolfsense_file, aircok_file))
                results[aircok_file] = file_result
                self.progress.emit(f"{aircok_file} 보정 완료")
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

class WindowClass(QMainWindow, uic.loadUiType(resource_path("ui/main_window.ui"))[0]):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setFixedSize(self.width(), self.height())
        self.setWindowTitle("Aircok Data Manager v1.1.0 (2025.05)")
        self.setWindowIcon(QIcon(resource_path("img/smartaircok.ico")))

        self.grimm_file = None
        self.testo_file = None
        self.wolfsense_file = None
        self.aircok_files = []
        self.current_file_index = 0
        self.aircok_report = {}

        self.grimm_button.clicked.connect(self.grimm_button_clicked)
        self.testo_button.clicked.connect(self.testo_button_clicked)
        self.wolfsense_button.clicked.connect(self.wolfsense_button_clicked)
        self.aircok_button.clicked.connect(self.aircok_button_clicked)
        self.calibration_button.clicked.connect(self.calibration_button_clicked)
        self.result_button.clicked.connect(self.generate_calibration_report)
        self.report_button.clicked.connect(self.generate_aircok_report)
        self.prev_button.clicked.connect(self.previous_result)
        self.next_button.clicked.connect(self.next_result)
        self.reset_button.clicked.connect(self.reset)
        self.re_calibration_button.clicked.connect(self.recalculation)

        self.user_guide_window = None
        self.actionUser_guide.triggered.connect(self.open_user_guide)

        self.about_window = None
        self.actionAbout.triggered.connect(self.open_about)

        self.log_converter_window = None
        self.lcd_loger_parsing.triggered.connect(self.open_log_converter)

        self.data_downloader_window = None
        self.aircok_data_downloader.triggered.connect(self.open_data_downloader)

    def short_path(self, full_path, depth=2):
        parts = full_path.replace("\\", "/").split("/")
        return "/".join(parts[-depth:])

    def open_user_guide(self):
        if not self.user_guide_window:
            self.user_guide_window = UserGuideWindow()
        self.user_guide_window.show()

    def open_about(self):
        if not self.about_window:
            self.about_window = AboutWindow()
        self.about_window.show()

    def open_log_converter(self):
        if not self.log_converter_window:
            self.log_converter_window = LogConverterApp()
            self.log_converter_window.finished.connect(self.cleanup_log_converter)
        self.log_converter_window.show()

    def cleanup_log_converter(self):
        self.log_converter_window = None

    def open_data_downloader(self):
        if not self.data_downloader_window:
            self.data_downloader_window = DataDownloader()
            self.data_downloader_window.setWindowTitle("Aircok Data Extractor v1.1.1")
            self.data_downloader_window.setAttribute(Qt.WA_DeleteOnClose)
            self.data_downloader_window.destroyed.connect(self.cleanup_data_downloader)
        self.data_downloader_window.show()

    def cleanup_data_downloader(self):
        self.data_downloader_window = None

    def grimm_button_clicked(self):
        self.grimm_file, _ = QFileDialog.getOpenFileName(self, "Grimm 파일 열기", "", "Grimm 파일 (*.dat)")
        if self.grimm_file:
            self.consol.append(f"Grimm 파일 로드 완료: {self.short_path(self.grimm_file)}")

    def testo_button_clicked(self):
        self.testo_file, _ = QFileDialog.getOpenFileName(self, "Testo 파일 열기", "", "Testo 파일 (*.csv)")
        if self.testo_file:
            self.consol.append(f"Testo 파일 로드 완료: {self.short_path(self.testo_file)}")

    def wolfsense_button_clicked(self):
        self.wolfsense_file, _ = QFileDialog.getOpenFileName(self, "Wolfsense 파일 열기", "", "Wolfsense 파일 (*.xls)")
        if self.wolfsense_file:
            self.consol.append(f"Wolfsense 파일 로드 완료: {self.short_path(self.wolfsense_file)}")

    def aircok_button_clicked(self):
        self.aircok_files, _ = QFileDialog.getOpenFileNames(self, "Aircok 데이터 파일 열기", "", "Aircok 파일 (*.csv)")
        if self.aircok_files:
            self.consol.append(f"Aircok 파일 {len(self.aircok_files)}개 로드 완료")
            self.current_file_index = 0

    def calibration_button_clicked(self):
        if not self.aircok_files:
            QMessageBox.warning(self, "파일 없음", "Aircok 파일을 먼저 선택해주세요.")
            return

        self.progress_dialog = QProgressDialog("보정 중입니다...", None, 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowFlags(self.progress_dialog.windowFlags() & ~Qt.WindowCloseButtonHint)
        self.progress_dialog.setFixedSize(self.progress_dialog.sizeHint())
        self.progress_dialog.show()

        self.calibration_thread = CalibrationThread(
            self.aircok_files, self.grimm_file, self.testo_file, self.wolfsense_file
        )
        self.calibration_thread.progress.connect(lambda msg: self.consol.append(msg))
        self.calibration_thread.finished.connect(self._calibration_done)
        self.calibration_thread.error.connect(self._calibration_failed)
        self.calibration_thread.start()

    def _calibration_done(self, results):
        self.progress_dialog.close()
        self.aircok_report = results
        self.current_file_index = 0
        self.display_calibration_result()
        self.calibration_thread = None

    def _calibration_failed(self, msg):
        self.progress_dialog.close()
        QMessageBox.critical(self, "보정 오류", msg)
        self.calibration_thread = None

    def clear_text_widgets(self):
        widgets = [
            self.sn_number, self.pm25_cal, self.pm10_cal,
            self.pm25_before_accuracy, self.pm25_after_accuracy,
            self.pm10_before_accuracy, self.pm10_after_accuracy,
            self.temp_cal, self.humi_cal,
            self.temp_before_accuracy, self.temp_after_accuracy,
            self.humi_before_accuracy, self.humi_after_accuracy,
            self.co2_cal, self.co2_before_accuracy, self.co2_after_accuracy
        ]
        for w in widgets:
            w.clear()

    def display_calibration_result(self):
        if not self.aircok_files:
            return

        current_file = self.aircok_files[self.current_file_index]
        result = self.aircok_report.get(current_file, {})

        self.sn_number.setText(os.path.splitext(os.path.basename(current_file))[0])
        self.pm25_cal.setPlainText(",".join([f"*{v}" for _, v in result.get("pm25_correction", [])]))
        self.pm10_cal.setPlainText(",".join([f"*{v}" for _, v in result.get("pm10_correction", [])]))

        self.pm25_before_accuracy.setPlainText(f"{result.get('pm25_accuracy_pre', 0):.2f}%")
        self.pm25_after_accuracy.setPlainText(f"{result.get('pm25_accuracy_post', 0):.2f}%")
        self.pm10_before_accuracy.setPlainText(f"{result.get('pm10_accuracy_pre', 0):.2f}%")
        self.pm10_after_accuracy.setPlainText(f"{result.get('pm10_accuracy_post', 0):.2f}%")

        self.temp_cal.setPlainText(f"{result.get('temp_correction', 0)}")
        self.humi_cal.setPlainText(f"{result.get('humi_correction', 0)}")

        self.temp_before_accuracy.setPlainText(f"{result.get('temp_accuracy', 0):.2f}%")
        self.temp_after_accuracy.setPlainText(f"{result.get('temp_corrected_accuracy', 0):.2f}%")
        self.humi_before_accuracy.setPlainText(f"{result.get('humi_accuracy', 0):.2f}%")
        self.humi_after_accuracy.setPlainText(f"{result.get('humi_corrected_accuracy', 0):.2f}%")

        self.co2_cal.setPlainText(f"{result.get('co2_correction_str', '')}")

        self.co2_before_accuracy.setPlainText(f"{result.get('pre_correction_accuracy', 0):.2f}%")
        self.co2_after_accuracy.setPlainText(f"{result.get('post_correction_accuracy', 0):.2f}%")

    def previous_result(self):
        if self.current_file_index > 0:
            self.current_file_index -= 1
            self.display_calibration_result()

    def next_result(self):
        if self.current_file_index < len(self.aircok_files) - 1:
            self.current_file_index += 1
            self.display_calibration_result()

    def reset(self):
        self.grimm_file = None
        self.testo_file = None
        self.wolfsense_file = None
        self.aircok_files = []
        self.current_file_index = 0
        self.aircok_report = {}
        self.clear_text_widgets()
        self.consol.clear()
        QMessageBox.information(self, "초기화 완료", "모든 데이터와 입력값이 초기화되었습니다.")

    def generate_calibration_report(self):
        if not self.aircok_report:
            QMessageBox.warning(self, "데이터 없음", "보정 결과가 없습니다. 먼저 보정을 수행해주세요.")
            return

        output_file, _ = QFileDialog.getSaveFileName(
            self, "보정 보고서 저장", "calibration_report.xlsx", "Excel 파일 (*.xlsx)"
        )
        if not output_file:
            return
        if not output_file.endswith(".xlsx"):
            output_file += ".xlsx"

        try:
            export_calibration_report(self.aircok_report, output_file)
            QMessageBox.information(self, "완료", f"보정 보고서가 저장되었습니다:\n{output_file}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 저장 중 오류 발생:\n{str(e)}")

    def generate_aircok_report(self):
        if not self.aircok_files:
            QMessageBox.warning(self, "파일 없음", "먼저 Aircok 파일을 선택해주세요.")
            return

        output_file, _ = QFileDialog.getSaveFileName(
            self, "보고서 저장", "aircok_report.xlsx", "Excel 파일 (*.xlsx)"
        )
        if not output_file:
            return
        if not output_file.endswith(".xlsx"):
            output_file += ".xlsx"

        self.progress_dialog = QProgressDialog("보고서를 생성 중입니다...", None, 0, 100, self)
        self.progress_dialog.setWindowTitle("진행 중")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowFlags(self.progress_dialog.windowFlags() & ~Qt.WindowCloseButtonHint)
        self.progress_dialog.setFixedSize(self.progress_dialog.sizeHint())

        self.progress_dialog.show()

        self.thread = ReportGeneratorThread(self.aircok_files, output_file)
        self.thread.progress.connect(self._update_report_progress)
        self.thread.finished.connect(self._report_generation_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.error.connect(self._report_generation_failed)
        self.thread.start()

    def _update_report_progress(self, status_text, step_index):
        self.progress_dialog.setLabelText(status_text)
        self.progress_dialog.setValue(step_index)
        QApplication.processEvents()

    def _report_generation_finished(self, file_path):
        self.progress_dialog.close()
        QMessageBox.information(self, "성공", f"보고서 생성 완료: {file_path}")
        self.thread = None

    def _report_generation_failed(self, error_message):
        self.progress_dialog.close()
        QMessageBox.critical(self, "오류", f"보고서 생성 중 오류 발생: {error_message}")
        self.thread = None

    def generate_aircok_report(self):
        if not self.aircok_files:
            QMessageBox.warning(self, "파일 없음", "먼저 Aircok 파일을 선택해주세요.")
            return

        output_file, _ = QFileDialog.getSaveFileName(
            self, "보고서 저장", "aircok_report.xlsx", "Excel 파일 (*.xlsx)"
        )
        if not output_file:
            return
        if not output_file.endswith(".xlsx"):
            output_file += ".xlsx"

        self.progress_dialog = QProgressDialog("보고서를 생성 중입니다...", None, 0, 100, self)
        self.progress_dialog.setWindowTitle("진행 중")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowFlags(self.progress_dialog.windowFlags() & ~Qt.WindowCloseButtonHint)
        self.progress_dialog.setFixedSize(self.progress_dialog.sizeHint())

        self.progress_dialog.show()

        self.thread = ReportGeneratorThread(self.aircok_files, output_file)
        self.thread.progress.connect(self._update_report_progress)
        self.thread.finished.connect(self._report_generation_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.error.connect(self._report_generation_failed)
        self.thread.start()

    def _update_report_progress(self, status_text, step_index):
        self.progress_dialog.setLabelText(status_text)
        self.progress_dialog.setValue(step_index)
        QApplication.processEvents()

    def _report_generation_finished(self, file_path):
        self.progress_dialog.close()
        QMessageBox.information(self, "성공", f"보고서 생성 완료: {file_path}")
        self.thread = None

    def _report_generation_failed(self, error_message):
        self.progress_dialog.close()
        QMessageBox.critical(self, "오류", f"보고서 생성 중 오류 발생: {error_message}")
        self.thread = None

    def recalculation(self):
        if not self.aircok_report:
            QMessageBox.warning(self, "데이터 없음", "먼저 보정을 완료한 후에 재계산을 진행해주세요.")
            return

        prev_file, _ = QFileDialog.getOpenFileName(self, "이전 보정 보고서 선택", "", "Excel 파일 (*.xlsx)")
        if not prev_file:
            return

        try:
            prev_data = load_previous_calibration(prev_file)
            apply_calibration_merge(self.aircok_report, prev_data)
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))
            return

        QMessageBox.information(self, "완료", "누적 보정값이 적용되었습니다.")
        self.consol.append("보정값 누적 계산 완료. 결과는 화면에 반영되었습니다.")
        self.display_calibration_result()

class UserGuideWindow(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi(resource_path("ui/guide.ui"), self)
        self.setWindowTitle("User Guide")

class AboutWindow(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi(resource_path("ui/about.ui"), self)
        self.setWindowTitle("About")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    mainWindow = WindowClass()
    mainWindow.show()
    sys.exit(app.exec_())