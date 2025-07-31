import os
import time
import datetime
import logging
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Sheet update helpers
from sheetupdate import setup_sheet, get_or_create_status_column, update_status, get_sheet_data

# === CONFIGURATION ===
download_folder = r"D:\ShortsReelsAutomationTool\Google Trends"
chromedriver_path = r"D:\ShortsReelsAutomationTool\chromedriver.exe"

# === LOGGING CONFIGURATION ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# === WebDriver Setup ===
def setup_driver():
    chrome_options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": download_folder,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver, WebDriverWait(driver, 20)

# === Helper: Retry Web Load ===
def safe_get(driver, url, retries=3, wait_time=3):
    for i in range(retries):
        try:
            driver.get(url)
            return True
        except Exception as e:
            logging.warning(f"Retry {i+1}/{retries} - Failed to load {url}: {e}")
            time.sleep(wait_time)
    return False

# === Helper: CSV Validity ===
def is_valid_csv(path):
    try:
        pd.read_csv(path, nrows=1)
        return True
    except Exception:
        return False

# === Core Function: Download + Rename ===
def download_csv_and_rename(driver, wait, url, filename_base):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    expected_filename = f"{filename_base}_{today_str}.csv"
    expected_path = os.path.join(download_folder, expected_filename)

    if os.path.exists(expected_path):
        logging.info(f"⏭️  Skipping: {expected_filename} already exists.")
        return True

    logging.info(f"🔗 Opening: {url}")
    if not safe_get(driver, url):
        logging.error(f"❌ Failed to load {url}")
        return False

    before_files = set(os.listdir(download_folder))

    try:
        export_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "Export")]')))
        export_button.click()
        time.sleep(1)

        download_option = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//li[@role="menuitem" and @aria-label="Download CSV"]')))
        driver.execute_script("arguments[0].click();", download_option)
        logging.info("✅ Download triggered...")

        timeout = 30
        downloaded_file = None
        for _ in range(timeout):
            current_files = set(os.listdir(download_folder))
            new_files = current_files - before_files
            csv_files = [f for f in new_files if f.endswith(".csv")]
            if csv_files:
                downloaded_file = os.path.join(download_folder, csv_files[0])
                break
            time.sleep(1)

        if downloaded_file and is_valid_csv(downloaded_file):
            os.rename(downloaded_file, expected_path)
            logging.info(f"📁 Saved as: {expected_filename}")
            return True
        else:
            logging.error("❌ CSV download failed or file invalid.")
            return False

    except Exception as e:
        logging.error(f"⚠️ Error while processing {url}: {e}")
        return False

# === MAIN SCRIPT ===
if __name__ == "__main__":
    sheet, col_index, rows = get_sheet_data()
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    expected = []

    for row in rows:
        if len(row) < 2:
            continue
        filename, url = row[0].strip(), row[1].strip()
        if filename and url:
            expected.append((f"{filename}_{today_str}.csv", filename, url))

    driver, wait = setup_driver()
    failed = []

    # FIRST ATTEMPT
    for row_index, (expected_filename, filename_base, url) in enumerate(expected):
        success = download_csv_and_rename(driver, wait, url, filename_base)
        status = "Done" if success else "Failed"
        update_status(sheet, row_index + 2, col_index, status)
        if not success:
            failed.append((row_index, expected_filename, filename_base, url))

    # RETRY LOGIC
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        if not failed:
            break
        logging.warning(f"🔁 Retry attempt {attempt} for {len(failed)} files...")
        retry_failed = []
        for row_index, expected_filename, filename_base, url in failed:
            if not os.path.exists(os.path.join(download_folder, expected_filename)):
                success = download_csv_and_rename(driver, wait, url, filename_base)
                status = "Done" if success else "Failed"
                update_status(sheet, row_index + 2, col_index, status)
                if not success:
                    retry_failed.append((row_index, expected_filename, filename_base, url))
        failed = retry_failed

    driver.quit()

    if failed:
        logging.error("❌ Some files still failed after retries:")
        for f in failed:
            logging.error(f"- {f[1]}")
    else:
        logging.info("✅ All downloads completed successfully, including retries.")
