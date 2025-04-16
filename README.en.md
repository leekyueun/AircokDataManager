# Aircok Data Manager  
**Version: v1.0.1 (April 2025)**

Aircok Data Manager is a calibration and reporting tool designed to improve the accuracy of Aircok sensor data, including particulate matter (PM), temperature, humidity, and CO₂. It enables data correction using reference devices and exports the results in organized Excel reports.

---

## 🧩 Main Features

### 1. Load Files
Select reference data and Aircok device data to load.  
Provides a user-friendly interface to navigate and load files easily.

### 2. Calibrate Data
Click the **[Calibration]** button to execute the automated calibration algorithm for precise data correction.

### 3. View Results
You can inspect the calibrated data directly in the app and navigate sheets using previous/next buttons.

### 4. Export Calibration Results
Click **[Generate Calibration Results]** to export sensor-specific calibration data to an Excel file.

### 5. Generate Report
Click **[Generate Report]** to export merged and organized data into an Excel report.

---

## 🔧 Additional Tools

### ▪ Aircok Log Converter
Aircok LCD models store logs in `.txt` format via SD card.  
This tool converts those logs into readable `.csv` files.

### ▪ Aircok Data Extractor
Easily download Aircok data stored in a PostgreSQL database via a GUI-based extractor.

---

## 📈 Calibration Methods

### ▪ PM2.5 / PM10 Calibration
Uses an XGBoost model and a 3-step process:

1. **Segment Dust Levels**  
   PM data is grouped into four levels: `[10-30]`, `[31-60]`, `[61-100]`, `[101-200]`.

2. **Calculate Correction Factor**  
   The ratio between GRIMM and Aircok is analyzed.  
   XGBoost is used to predict the ratio, and the median is used to determine final correction values.

3. **Accuracy Evaluation**  
   Compares data before and after calibration to evaluate performance improvement.

### ▪ Temperature / Humidity / CO₂ Calibration
- Averages from the reference and Aircok data are compared to calculate a correction factor.
- These metrics are relatively stable, so simple averaging yields effective correction.
- Improvement is verified through before/after comparison.

---

## 🖥️ Screenshots

### ▪ Main Interface  
![image](https://github.com/user-attachments/assets/5a5bf2dd-024c-4784-8bc7-1405696ee52d)

### ▪ Aircok Data Extractor  
![image](https://github.com/user-attachments/assets/675aaa13-0c09-40d0-9d79-c679a3e02e67)

### ▪ Aircok Log Converter  
![image](https://github.com/user-attachments/assets/8fc250bf-309c-42f2-a916-169620c75000)

---

## 🚀 How to Run

1. Download `Aircok Data Manager.zip`.
2. Extract the files and run `Aircok Data Manager v1.0.1.exe`.

---

## 💻 Recommended Specifications

- **OS:** Windows 11 or higher  
- **RAM:** 8GB or more

> ⚠️ **Note:** This tool is still under testing.  
> On lower-spec environments, it may fail to run or behave unexpectedly.

---

## 📦 Version History

### v1.0.1 (2025-04)
- 🐞 Fixed calibration issues for PM and CO₂

### v1.0.0 (2025-04)
- 🎉 Official release with full feature stability

### v1.0.0-rc.1 (2025-04)
- 🔧 Final optimization and bug fixes

### v1.0.0-beta (2025-04)
- 🧪 Performance and stability testing

### v1.0.0-alpha.5 (2025-04)
- ➕ Added calibration result export  
- ➕ Added average sheet per sensor

### v1.0.0-alpha.4 (2025-04)
- ➕ Added DB switching and server selector

### v1.0.0-alpha.3 (2025-03)
- ➕ Added Aircok data downloader  
- 🐞 Fixed report generation bug  
- ⚙ Improved report generation performance

### v1.0.0-alpha.2 (2024-12)
- ➕ Added data reset and log converter

### v1.0.0-alpha.1 (2024-12)
- 🐞 Fixed CO₂ calibration issue  
- ➕ Added report generation and export

### v1.0.0-alpha (2024-11)
- 🚀 Initial alpha release with core features

---

## 🛠 Tech Stack

- **Python 3.10+**
- **PyQt5**
- **pandas**
- **XGBoost**
- **SQLAlchemy + PostgreSQL**

---

> 🇰🇷 [한국어 README 보기](README.md)   
> 🇯🇵 [日本語のREADME](README.ja.md)
