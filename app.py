from flask import Flask, request, render_template, redirect, url_for, send_file, jsonify
import os, uuid, zipfile, json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from config import UPLOAD_FOLDER
from worker import process_job

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

executor = ThreadPoolExecutor(max_workers=4)
jobs = {}
metas = {}

def handle_submission(template_name):
    if request.method == "POST":
        api_key = request.form["api_key"]
        system_prompt = request.form["system_prompt"]
        model_custom = request.form.get("model_custom", "").strip()
        model_dropdown = request.form.get("model_dropdown", "google/gemini-3-flash-preview")
        model = model_custom if model_custom else model_dropdown
        file = request.files["zipfile"]

        job_id = str(uuid.uuid4())
        job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
        os.makedirs(job_dir, exist_ok=True)

        zip_path = os.path.join(job_dir, "input.zip")
        file.save(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(os.path.join(job_dir, "input"))

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        include_inputs = "include_inputs" in request.form

        meta = {
            "api_key": api_key,
            "system_prompt": system_prompt,
            "model": model,
            "submitted_at": timestamp,
            "include_inputs": include_inputs
        }

        with open(os.path.join(job_dir, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)

        future = executor.submit(process_job, job_id, meta)
        jobs[job_id] = future
        metas[job_id] = meta

        return redirect(url_for("status", job_id=job_id))

    return render_template(template_name)

@app.route("/", methods=["GET", "POST"])
def index():
    return handle_submission("index.html")

@app.route("/marc", methods=["GET", "POST"])
def marc():
    return handle_submission("marc.html")

@app.route("/status/<job_id>")
def status(job_id):
    if job_id not in jobs:
        return f"Unknown job {job_id}", 404

    future = jobs[job_id]
    meta = metas[job_id]
    model = meta.get("model", "unknown")
    submitted_at = meta.get("submitted_at", "unknown")
    completed_at = meta.get("completed_at", None)
    elapsed_time = meta.get("elapsed_time", None)

    if future.done():
        try:
            result_path = future.result()
            zip_filename = os.path.basename(result_path)
            return render_template(
                "status.html",
                job_id=job_id,
                status="Finished",
                model=model,
                submitted_at=submitted_at,
                completed_at=completed_at,
                elapsed_time=elapsed_time,
                result_url=url_for("download", job_id=job_id),
                zip_filename=zip_filename,
                include_inputs=meta.get("include_inputs", False)
            )
        except Exception as e:
            return render_template(
                "status.html",
                job_id=job_id,
                status=f"Error: {e}",
                model=model,
                submitted_at=submitted_at
            )
    else:
        return render_template(
            "status.html",
            job_id=job_id,
            status="Running",
            model=model,
            submitted_at=submitted_at,
            include_inputs=meta.get("include_inputs", False)
        )

@app.route("/download/<job_id>")
def download(job_id):
    job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
    if not os.path.exists(job_dir):
        return f"Job {job_id} not found", 404

    zips = [f for f in os.listdir(job_dir) if f.startswith("results_") and f.endswith(".zip")]
    if not zips:
        return f"No results for job {job_id}", 404

    latest_zip = max(zips)
    zip_path = os.path.join(job_dir, latest_zip)
    return send_file(zip_path, as_attachment=True)

@app.route("/progress/<job_id>")
def progress(job_id):
    job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
    meta_file = os.path.join(job_dir, "meta.json")
    if not os.path.exists(meta_file):
        return jsonify({"error": "No such job"}), 404
    with open(meta_file) as f:
        meta = json.load(f)
    total = meta.get("total_files", 0)
    done = meta.get("processed_files", 0)
    return jsonify({"processed": done, "total": total})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9513, debug=True)
