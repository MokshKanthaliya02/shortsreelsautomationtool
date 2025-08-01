import os
import json
import time
import re
from dotenv import load_dotenv
import google.generativeai as genai

# === Load API Key ===
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY2")
if not API_KEY:
    raise ValueError("❌ GEMINI_API_KEY2 not found in .env file.")
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# === Config ===
BASE_DIR = r"D:\ShortsReelsAutomationTool"
SUMMARY_DIR = os.path.join(BASE_DIR, "Summaries")
SCRIPT_DIR = os.path.join(BASE_DIR, "Scripts")
PROMPT_PATH = os.path.join(BASE_DIR, "video_script_gen_prompt.json")
PROGRESS_PATH = os.path.join(SCRIPT_DIR, "progress.json")
MAX_FILES_PER_RUN = 10
WAIT_SECONDS = 5

os.makedirs(SCRIPT_DIR, exist_ok=True)

# === Load Prompt Template ===
with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    prompt_data = json.load(f)

# === Load Progress Tracking ===
if os.path.exists(PROGRESS_PATH):
    with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
        progress = json.load(f)
else:
    progress = {}

def build_prompt(summary_text):
    return (
        f"{prompt_data['instruction']}\n\n"
        f"Goal: {prompt_data['goal']}\n"
        f"Tone: {prompt_data['tone']}\n"
        f"Audience: {prompt_data['audience']}\n"
        f"Delivery: {prompt_data['style']['delivery']}\n"
        f"Structure: {', '.join(prompt_data['style']['structure'])}\n"
        f"Visuals: {', '.join(prompt_data['visuals']['instructions'])}\n\n"
        f"{prompt_data['task']}\n\n"
        f"=== BEGIN TOPIC SUMMARIES ===\n\n"
        f"{summary_text.strip()}\n\n"
        f"=== END ==="
    )

def clean_response(raw_output):
    # Remove triple backticks
    if raw_output.startswith("```"):
        raw_output = re.sub(r"^```(json)?\n?", "", raw_output.strip())
        raw_output = re.sub(r"\n?```$", "", raw_output.strip())

    # Replace smart quotes
    raw_output = raw_output.replace("“", '"').replace("”", '"')

    # Escape quotes inside narration field
    def escape_quotes_in_narration(match):
        content = match.group(1).replace('"', '\\"')
        return f'"narration": "{content}"'

    raw_output = re.sub(r'"narration"\s*:\s*"(.+?)"', escape_quotes_in_narration, raw_output)
    return raw_output

def save_progress():
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)

# === Batch Process Files ===
processed = 0
for filename in os.listdir(SUMMARY_DIR):
    if not filename.endswith(".txt"):
        continue

    summary_path = os.path.join(SUMMARY_DIR, filename)
    base_name = os.path.splitext(filename)[0]
    output_path = os.path.join(SCRIPT_DIR, f"{base_name}_scripts.json")

    # Skip already done
    if progress.get(filename, "") == "done":
        continue

    print(f"\n📄 Processing: {filename}")
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            summary_content = f.read()

        prompt = build_prompt(summary_content)
        response = model.generate_content(prompt)
        raw_output = response.text.strip()

        # Clean response
        cleaned = clean_response(raw_output)

        # Parse JSON
        parsed = json.loads(cleaned)

        # Save JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)

        print(f"✅ Saved to {output_path}")
        progress[filename] = "done"

    except Exception as e:
        print(f"❌ Failed on {filename}: {e}")
        progress[filename] = "failed"

    save_progress()
    processed += 1

    if processed >= MAX_FILES_PER_RUN:
        print(f"\n⚠️ Reached max limit of {MAX_FILES_PER_RUN} files this run.")
        break

    print(f"⏳ Waiting {WAIT_SECONDS} seconds to avoid rate limits...")
    time.sleep(WAIT_SECONDS)

print("\n✅ All possible files processed for this run.")
