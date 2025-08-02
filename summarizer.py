# summarizer.py

import os
import csv
import json
import re
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# --- Load API Key ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY1")
if not API_KEY:
    raise ValueError("❌ GEMINI_API_KEY1 not found in .env file.")

# --- Configure Gemini ---
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# --- Configuration ---
MAX_TOPICS_PER_BATCH = 25  # Optimal batch size for JSON generation
RETRY_ATTEMPTS = 3
JSON_FIX_ATTEMPTS = 2

# --- Paths ---
BASE_DIR = r"D:\ShortsReelsAutomationTool"
CSV_FOLDER = os.path.join(BASE_DIR, "Google Trends")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "Summaries")
PROMPT_TEMPLATE_PATH = os.path.join(BASE_DIR, "sum_gen_prompt.json")
FAILED_ROWS_PATH = os.path.join(OUTPUT_FOLDER, "failed_rows.json")
PROGRESS_PATH = os.path.join(OUTPUT_FOLDER, "progress.json")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# --- Load Prompt Template ---
with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
    prompt_json = json.load(f)
    base_prompt = prompt_json.get("prompt", "")
    if not base_prompt:
        raise ValueError("❌ 'prompt' key not found or is empty in sum_gen_prompt.json.")

# --- Load Progress ---
progress = {}
if os.path.exists(PROGRESS_PATH):
    with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
        progress = json.load(f)

def fix_json_response(response_text):
    """
    Advanced JSON fixing with multiple strategies
    """
    fixes_applied = []
    
    # Strategy 1: Clean markdown blocks
    if "```json" in response_text or "```" in response_text:
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        response_text = re.sub(r'^```\s*', '', response_text)
        fixes_applied.append("Removed markdown blocks")
    
    # Strategy 2: Fix common JSON errors
    # Remove trailing commas
    response_text = re.sub(r',(\s*[}\]])', r'\1', response_text)
    fixes_applied.append("Removed trailing commas")
    
    # Strategy 3: Fix unescaped quotes in strings
    # This is complex, so we'll use a more conservative approach
    lines = response_text.split('\n')
    fixed_lines = []
    
    for line in lines:
        # Skip lines that are likely JSON structure
        if any(x in line for x in ['{', '}', '[', ']', ':', ',']):
            # Look for unescaped quotes within string values
            if '"summary":' in line or '"topic_title":' in line or '"error_reason":' in line:
                # Find the value part after the colon
                if ':' in line:
                    key_part, value_part = line.split(':', 1)
                    # Fix quotes in the value part only
                    value_part = fix_quotes_in_string(value_part)
                    line = key_part + ':' + value_part
        fixed_lines.append(line)
    
    response_text = '\n'.join(fixed_lines)
    
    # Strategy 4: Fix unterminated strings
    # Look for lines that start with a quote but don't end with one
    lines = response_text.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('"') and not (stripped.endswith('"') or stripped.endswith('",') or stripped.endswith('",')):
            # This might be an unterminated string, try to fix it
            if i < len(lines) - 1:  # Not the last line
                next_line = lines[i + 1].strip()
                if not next_line.startswith('"'):
                    # Likely continuation of current string
                    line = line + " " + next_line
                    lines[i + 1] = ""  # Remove the next line
        fixed_lines.append(line)
    
    response_text = '\n'.join([line for line in fixed_lines if line])
    
    if fixes_applied:
        fixes_applied.append("Fixed unterminated strings")
    
    # Strategy 5: Ensure proper JSON structure
    response_text = response_text.strip()
    if not response_text.startswith('{'):
        response_text = '{' + response_text
    if not response_text.endswith('}'):
        response_text = response_text + '}'
    
    return response_text, fixes_applied

def fix_quotes_in_string(text):
    """
    Fix unescaped quotes within JSON string values
    """
    # This is a simplified approach - in a real implementation,
    # you'd want more sophisticated parsing
    if text.count('"') > 2:  # More than opening and closing quotes
        # Find content between first and last quote
        first_quote = text.find('"')
        last_quote = text.rfind('"')
        if first_quote != -1 and last_quote != -1 and first_quote != last_quote:
            before = text[:first_quote + 1]
            content = text[first_quote + 1:last_quote]
            after = text[last_quote:]
            # Escape quotes in the content
            content = content.replace('"', '\\"')
            text = before + content + after
    return text

def validate_and_parse_json_response(response_text, filename):
    """
    Enhanced JSON validation and parsing with multiple fix attempts
    """
    original_text = response_text
    
    for attempt in range(JSON_FIX_ATTEMPTS + 1):
        try:
            # Clean the response text
            cleaned_response = response_text.strip()
            
            # Try to parse JSON
            parsed_json = json.loads(cleaned_response)
            
            # Validate required structure
            if not isinstance(parsed_json, dict):
                raise ValueError("Response is not a JSON object")
            
            if "summaries" not in parsed_json:
                raise ValueError("Missing 'summaries' key in response")
            
            if "metadata" not in parsed_json:
                # Add default metadata if missing
                parsed_json["metadata"] = {
                    "total_topics": len(parsed_json.get("summaries", [])),
                    "processed_topics": len(parsed_json.get("summaries", [])),
                    "failed_topics": len(parsed_json.get("errors", [])),
                    "processing_date": datetime.now().strftime("%Y-%m-%d"),
                    "source": "Viral Content Research"
                }
            
            if "errors" not in parsed_json:
                parsed_json["errors"] = []
            
            return parsed_json, None
            
        except json.JSONDecodeError as e:
            if attempt < JSON_FIX_ATTEMPTS:
                print(f"🔧 JSON parsing attempt {attempt + 1} failed, trying to fix...")
                response_text, fixes = fix_json_response(response_text)
                print(f"   Applied fixes: {', '.join(fixes)}")
                continue
            else:
                error_msg = f"JSON parsing error after {JSON_FIX_ATTEMPTS + 1} attempts: {str(e)}"
                return None, error_msg
        except Exception as e:
            error_msg = f"Response validation error: {str(e)}"
            return None, error_msg
    
    return None, "Failed to parse JSON after all fix attempts"

def create_fallback_json(filename, topics_data, error_message):
    """
    Create a fallback JSON structure when Gemini response fails
    """
    return {
        "metadata": {
            "total_topics": len(topics_data),
            "processed_topics": 0,
            "failed_topics": len(topics_data),
            "processing_date": datetime.now().strftime("%Y-%m-%d"),
            "source": "Viral Content Research",
            "processing_error": error_message,
            "fallback_mode": True
        },
        "summaries": [],
        "errors": [
            {
                "topic_title": topic.get("keyword", "Unknown Topic"),
                "trend_keyword": topic.get("keyword", ""),
                "error_reason": f"Processing failed due to: {error_message}",
                "status": "failed"
            } for topic in topics_data
        ]
    }

def split_topics_into_batches(topics_data, batch_size=MAX_TOPICS_PER_BATCH):
    """
    Split topics into smaller batches for better JSON generation
    """
    batches = []
    for i in range(0, len(topics_data), batch_size):
        batch = topics_data[i:i + batch_size]
        batches.append(batch)
    return batches

def process_batch(batch_topics, batch_num, total_batches, filename):
    """
    Process a single batch of topics
    """
    print(f"🔄 Processing batch {batch_num}/{total_batches} ({len(batch_topics)} topics)...")
    
    # Create bulk entries for this batch
    bulk_trend_entries = []
    for i, topic in enumerate(batch_topics, start=1):
        bulk_trend_entries.append(
            f"{i}. Keyword: {topic['keyword']}\n"
            f"   Breakdown: {topic['breakdown']}\n"
            f"   Timestamp: {topic['timestamp']}\n"
            f"   Link: {topic['link']}\n"
        )
    
    topic_count = len(batch_topics)
    
    # Replace placeholders in prompt
    batch_prompt = base_prompt.replace("{{bulk_trend_entries}}", "\n".join(bulk_trend_entries))
    batch_prompt = batch_prompt.replace("{{topic_count}}", str(topic_count))
    
    # Try processing with retries
    for attempt in range(RETRY_ATTEMPTS):
        try:
            print(f"🤖 API call attempt {attempt + 1}/{RETRY_ATTEMPTS}...")
            response = model.generate_content(batch_prompt)
            response_text = response.text.strip()
            
            # Validate and parse JSON response
            parsed_json, error_msg = validate_and_parse_json_response(response_text, filename)
            
            if parsed_json is not None:
                print(f"✅ Batch {batch_num} processed successfully!")
                return parsed_json, None
            else:
                print(f"⚠️ Batch {batch_num} attempt {attempt + 1} failed: {error_msg}")
                if attempt == RETRY_ATTEMPTS - 1:
                    return None, error_msg
                
        except Exception as e:
            print(f"❌ API error on attempt {attempt + 1}: {str(e)}")
            if attempt == RETRY_ATTEMPTS - 1:
                return None, f"API error after {RETRY_ATTEMPTS} attempts: {str(e)}"
    
    return None, "All retry attempts failed"

def merge_batch_results(batch_results):
    """
    Merge multiple batch results into a single JSON structure
    """
    merged = {
        "metadata": {
            "total_topics": 0,
            "processed_topics": 0,
            "failed_topics": 0,
            "processing_date": datetime.now().strftime("%Y-%m-%d"),
            "source": "Viral Content Research",
            "batch_processing": True,
            "total_batches": len(batch_results)
        },
        "summaries": [],
        "errors": []
    }
    
    for batch_result in batch_results:
        if batch_result:
            merged["summaries"].extend(batch_result.get("summaries", []))
            merged["errors"].extend(batch_result.get("errors", []))
            
            # Update metadata
            batch_metadata = batch_result.get("metadata", {})
            merged["metadata"]["total_topics"] += batch_metadata.get("total_topics", 0)
            merged["metadata"]["processed_topics"] += batch_metadata.get("processed_topics", 0)
            merged["metadata"]["failed_topics"] += batch_metadata.get("failed_topics", 0)
    
    return merged

# --- Process CSV Files ---
for filename in os.listdir(CSV_FOLDER):
    if not filename.endswith(".csv"):
        continue

    if progress.get(filename) == "done":
        print(f"⏭️  Skipping {filename}, already processed.")
        continue

    print(f"\n📄 Processing file: {filename}")
    csv_path = os.path.join(CSV_FOLDER, filename)
    output_path = os.path.join(OUTPUT_FOLDER, os.path.splitext(filename)[0] + "_summary.json")

    topics_data = []
    
    try:
        with open(csv_path, "r", encoding="utf-8") as csvfile:
            reader = list(csv.DictReader(csvfile))

            if not reader:
                print(f"⚠️ No rows found in {filename}. Skipping.")
                continue

            # Extract topic data
            for row in reader:
                keyword = (row.get("Trends") or "").strip()
                breakdown = (row.get("Trend breakdown") or "").strip()
                timestamp = (row.get("Started") or "").strip()
                link = (row.get("Explore link") or "").strip()

                if not keyword:
                    continue

                topics_data.append({
                    "keyword": keyword,
                    "breakdown": breakdown,
                    "timestamp": timestamp,
                    "link": link
                })

            if not topics_data:
                print(f"⚠️ No valid topics found in {filename}.")
                continue

            total_topics = len(topics_data)
            print(f"📊 Total topics to process: {total_topics}")

            # Split into batches if needed
            if total_topics > MAX_TOPICS_PER_BATCH:
                print(f"🔄 Large file detected. Splitting into batches of {MAX_TOPICS_PER_BATCH} topics each...")
                batches = split_topics_into_batches(topics_data)
                print(f"📦 Created {len(batches)} batches")
                
                batch_results = []
                failed_batches = 0
                
                for i, batch in enumerate(batches, 1):
                    batch_result, error = process_batch(batch, i, len(batches), filename)
                    if batch_result:
                        batch_results.append(batch_result)
                    else:
                        failed_batches += 1
                        print(f"❌ Batch {i} failed: {error}")
                        # Create fallback for failed batch
                        fallback = create_fallback_json(f"{filename}_batch_{i}", batch, error)
                        batch_results.append(fallback)
                
                # Merge all batch results
                if batch_results:
                    final_result = merge_batch_results(batch_results)
                    print(f"🔀 Merged {len(batch_results)} batches ({failed_batches} failed)")
                else:
                    final_result = create_fallback_json(filename, topics_data, "All batches failed")
                    
            else:
                # Process as single batch
                print(f"📝 Processing as single batch...")
                final_result, error = process_batch(topics_data, 1, 1, filename)
                if not final_result:
                    print(f"❌ Single batch processing failed: {error}")
                    final_result = create_fallback_json(filename, topics_data, error)

            # Write final JSON output
            with open(output_path, "w", encoding="utf-8") as outfile:
                json.dump(final_result, outfile, indent=2, ensure_ascii=False)

            processed_count = final_result.get("metadata", {}).get("processed_topics", 0)
            failed_count = final_result.get("metadata", {}).get("failed_topics", 0)
            success_rate = (processed_count / total_topics) * 100 if total_topics > 0 else 0
            
            print(f"✅ JSON summary written to: {output_path}")
            print(f"📊 Results: {processed_count} success, {failed_count} failed ({success_rate:.1f}% success rate)")
            
            progress[filename] = "done"
            with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
                json.dump(progress, f, indent=2)

    except Exception as e:
        print(f"❌ Failed to process {filename}: {e}")
        
        # Create fallback JSON and save it
        fallback_json = create_fallback_json(filename, topics_data if 'topics_data' in locals() else [], str(e))
        with open(output_path, "w", encoding="utf-8") as outfile:
            json.dump(fallback_json, outfile, indent=2, ensure_ascii=False)
        
        # Log to failed rows
        failed_entry = {
            "file": filename,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "topics_count": len(topics_data) if topics_data else 0
        }
        
        if os.path.exists(FAILED_ROWS_PATH):
            with open(FAILED_ROWS_PATH, "r", encoding="utf-8") as f:
                existing_failed = json.load(f)
        else:
            existing_failed = []

        existing_failed.append(failed_entry)
        with open(FAILED_ROWS_PATH, "w", encoding="utf-8") as f:
            json.dump(existing_failed, f, indent=2)

print("\n🎉 Processing complete!")
print(f"📋 Summary:")
print(f"   - Batch size: {MAX_TOPICS_PER_BATCH} topics per batch")
print(f"   - Retry attempts: {RETRY_ATTEMPTS} per batch")
print(f"   - JSON fix attempts: {JSON_FIX_ATTEMPTS} per response")
print(f"   - Enhanced error handling and JSON repair enabled")