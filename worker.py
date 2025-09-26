import os, requests, pandas as pd, time, json, zipfile
from datetime import datetime
from config import UPLOAD_FOLDER

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def process_job(job_id, meta):
    job_dir = os.path.join(UPLOAD_FOLDER, job_id)
    input_dir = os.path.join(job_dir, "input")
    output_path = os.path.join(job_dir, "output.csv")

    # Generate timestamped ZIP name
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    zip_filename = f"results_{timestamp}.zip"
    zip_path = os.path.join(job_dir, zip_filename)

    system_prompt = meta["system_prompt"]
    api_key = meta["api_key"]
    model = meta.get("model", "google/gemini-2.5-flash")

    rows = []
    for fname in os.listdir(input_dir):
        fpath = os.path.join(input_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]
        }

        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)
            r.raise_for_status()
            data = r.json()
            reply = data["choices"][0]["message"]["content"]
        except Exception as e:
            reply = f"ERROR: {e}"

        rows.append({"file": fname, "output": reply})
        time.sleep(0.2)

    # Save CSV
    pd.DataFrame(rows).to_csv(output_path, index=False)

    # Save completion timestamp & elapsed time
    completed_at = datetime.now()
    meta["completed_at"] = completed_at.strftime("%Y-%m-%d %H:%M:%S")

    submitted_at_str = meta.get("submitted_at")
    if submitted_at_str:
        try:
            submitted_at = datetime.strptime(submitted_at_str, "%Y-%m-%d %H:%M:%S")
            elapsed = completed_at - submitted_at
            meta["elapsed_time"] = str(elapsed)
        except Exception:
            meta["elapsed_time"] = "unknown"

    meta_file = os.path.join(job_dir, "meta.json")
    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)

    # Create results.zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(output_path, arcname="output.csv")
        if os.path.exists(meta_file):
            zf.write(meta_file, arcname="meta.json")
        for fname in os.listdir(input_dir):
            fpath = os.path.join(input_dir, fname)
            zf.write(fpath, arcname=os.path.join("input", fname))

    return zip_path
