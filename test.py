import os
import csv
import time
import json
from dotenv import load_dotenv
import google.generativeai as genai

# --- Load API Key from .env ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("❌ GEMINI_API_KEY not found in .env file.")

# --- Configure Gemini API ---
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# --- File Paths ---
BASE_DIR = r"D:\ShortsReelsAutomationTool"
CSV_FOLDER = os.path.join(BASE_DIR, "Google Trends")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "Summaries")
PROMPT_TEMPLATE_PATH = os.path.join(BASE_DIR, "sum_gen_prompt.txt")
FAILED_ROWS_PATH = os.path.join(OUTPUT_FOLDER, "failed_rows.json")
PROGRESS_PATH = os.path.join(OUTPUT_FOLDER, "progress.json")

# --- Ensure Output Directory Exists ---
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --- Load Prompt Template ---
with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
    base_prompt = f.read()

# --- Load Progress ---
progress = {}
if os.path.exists(PROGRESS_PATH):
    with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
        progress = json.load(f)

# --- Process CSV Files ---
for filename in os.listdir(CSV_FOLDER):
    if not filename.endswith(".csv"):
        continue

    if progress.get(filename) == "done":
        print(f"⏭️  Skipping {filename}, already processed.")
        continue

    print(f"\n📄 Processing file: {filename}")
    csv_path = os.path.join(CSV_FOLDER, filename)
    output_path = os.path.join(OUTPUT_FOLDER, os.path.splitext(filename)[0] + "_summary.txt")

    try:
        with open(csv_path, "r", encoding="utf-8") as csvfile:
            reader = list(csv.DictReader(csvfile))

            if not reader:
                print(f"⚠️ No rows found in {filename}. Skipping.")
                continue

            bulk_trend_entries = []
            for i, row in enumerate(reader, start=1):
                keyword = (row.get("Trends") or "").strip()
                breakdown = (row.get("Trend breakdown") or "").strip()
                timestamp = (row.get("Started") or "").strip()
                link = (row.get("Explore link") or "").strip()

                if not keyword:
                    continue

                bulk_trend_entries.append(
                    f"{i}. Keyword: {keyword}\n"
                    f"   Breakdown: {breakdown}\n"
                    f"   Timestamp: {timestamp}\n"
                    f"   Link: {link}\n"
                )

            final_prompt = base_prompt.replace("{{bulk_trend_entries}}", "\n".join(bulk_trend_entries))

            try:
                response = model.generate_content(final_prompt)
                summary = response.text.strip()

                with open(output_path, "w", encoding="utf-8") as outfile:
                    outfile.write(summary)

                print(f"✅ Summary written to: {output_path}")

                # Update progress
                progress[filename] = "done"
                with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                    json.dump(progress, f)

            except Exception as e:
                print(f"❌ Error summarizing {filename}: {e}")
                failed_entry = {
                    "file": filename,
                    "prompt": final_prompt[:1000],  # Optional: trim long prompts
                    "error": str(e)
                }
                if os.path.exists(FAILED_ROWS_PATH):
                    with open(FAILED_ROWS_PATH, "r", encoding="utf-8") as f:
                        existing_failed = json.load(f)
                else:
                    existing_failed = []

                existing_failed.append(failed_entry)
                with open(FAILED_ROWS_PATH, "w", encoding="utf-8") as f:
                    json.dump(existing_failed, f, indent=2)

    except Exception as e:
        print(f"❌ Failed to process {filename}: {e}")
