from flask import Flask, request, render_template, redirect, url_for, send_file, jsonify
import os, uuid, zipfile, json, shutil
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from config import BASE_DIR, UPLOAD_FOLDER
from worker import process_job

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["EXISTING_ZIPS_FOLDER"] = os.path.join(BASE_DIR, "data", "zips")

executor = ThreadPoolExecutor(max_workers=4)
jobs = {}
metas = {}

def format_file_size(size_bytes):
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    unit_idx = 0
    while value >= 1024 and unit_idx < len(units) - 1:
        value /= 1024
        unit_idx += 1
    if unit_idx == 0:
        return f"{int(value)} {units[unit_idx]}"
    return f"{value:.2f} {units[unit_idx]}"

def resolve_existing_zip(zip_name):
    candidate_name = os.path.basename((zip_name or "").strip())
    if not candidate_name or not candidate_name.lower().endswith(".zip"):
        return None, None

    base_dir = os.path.abspath(app.config["EXISTING_ZIPS_FOLDER"])
    zip_path = os.path.abspath(os.path.join(base_dir, candidate_name))
    if os.path.commonpath([base_dir, zip_path]) != base_dir:
        return None, None

    if not os.path.isfile(zip_path):
        return None, None

    return candidate_name, zip_path

def list_existing_zips():
    zips_dir = app.config["EXISTING_ZIPS_FOLDER"]
    if not os.path.isdir(zips_dir):
        return []

    entries = []
    for filename in os.listdir(zips_dir):
        if not filename.lower().endswith(".zip"):
            continue

        zip_path = os.path.join(zips_dir, filename)
        if not os.path.isfile(zip_path):
            continue

        stat = os.stat(zip_path)
        entries.append({
            "name": filename,
            "size_label": format_file_size(stat.st_size),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "modified_ts": stat.st_mtime
        })

    entries.sort(key=lambda row: row["modified_ts"], reverse=True)
    for entry in entries:
        entry.pop("modified_ts", None)

    return entries

def handle_submission(template_name, group_by_subfolder=False, source_route="index", template_context=None):
    template_context = template_context or {}

    if request.method == "POST":
        api_key = request.form["api_key"]
        system_prompt = request.form["system_prompt"]
        model_custom = request.form.get("model_custom", "").strip()
        model_dropdown = request.form.get("model_dropdown", "google/gemini-3-flash-preview")
        model = model_custom if model_custom else model_dropdown
        file = request.files.get("zipfile")
        selected_existing_zip = request.form.get("existing_zip", "").strip()

        using_existing_zip = False
        existing_zip_path = None
        uploaded_filename = file.filename if file else ""
        if selected_existing_zip:
            original_name, existing_zip_path = resolve_existing_zip(selected_existing_zip)
            if not existing_zip_path:
                context = dict(template_context)
                context["error"] = "Selected ZIP file was not found in data/zips."
                return render_template(template_name, **context), 400
            using_existing_zip = True
        elif uploaded_filename:
            original_name = secure_filename(uploaded_filename)
            if not original_name:
                original_name = "upload.zip"
            elif not original_name.lower().endswith(".zip"):
                original_name = f"{original_name}.zip"
        else:
            context = dict(template_context)
            context["error"] = "Please upload a ZIP file or select one from data/zips."
            return render_template(template_name, **context), 400

        job_id = str(uuid.uuid4())
        job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
        os.makedirs(job_dir, exist_ok=True)

        input_zip_name = "input.zip"
        if source_route == "marc":
            if original_name.lower().startswith("inputs_"):
                input_zip_name = original_name
            else:
                input_zip_name = f"inputs_{original_name}"

        zip_path = os.path.join(job_dir, input_zip_name)
        if using_existing_zip:
            shutil.copy2(existing_zip_path, zip_path)
        else:
            file.save(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(os.path.join(job_dir, "input"))

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        include_inputs = "include_inputs" in request.form
        separate_outputs = "separate_outputs" in request.form
        include_metadata = "include_metadata" in request.form

        meta = {
            "api_key": api_key,
            "system_prompt": system_prompt,
            "model": model,
            "submitted_at": timestamp,
            "include_inputs": include_inputs,
            "group_by_subfolder": group_by_subfolder,
            "separate_outputs": separate_outputs,
            "include_metadata": include_metadata,
            "input_zip_name": input_zip_name,
            "input_source": "existing" if using_existing_zip else "uploaded",
            "source_route": source_route
        }

        meta_for_disk = dict(meta)
        meta_for_disk.pop("api_key", None)
        meta_for_disk["api_key_last8"] = api_key[-8:] if api_key else ""
        with open(os.path.join(job_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta_for_disk, f, indent=2, ensure_ascii=False)

        future = executor.submit(process_job, job_id, meta)
        jobs[job_id] = future
        metas[job_id] = meta

        return redirect(url_for("status", job_id=job_id))

    return render_template(template_name, **template_context)

@app.route("/", methods=["GET", "POST"])
def index():
    return handle_submission(
        "index.html",
        group_by_subfolder=True,
        source_route="index",
        template_context={"existing_zips": list_existing_zips()}
    )

@app.route("/marc", methods=["GET", "POST"])
def marc():
    return handle_submission("marc.html", group_by_subfolder=True, source_route="marc")

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

    source_route = meta.get("source_route")
    if not source_route and meta.get("group_by_subfolder"):
        source_route = "marc"

    is_marc = source_route == "marc"
    back_url = url_for("marc") if is_marc else url_for("index")
    back_label = "Back to MARC" if is_marc else "Back to home"

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
                include_inputs=meta.get("include_inputs", False),
                back_url=back_url,
                back_label=back_label
            )
        except Exception as e:
            return render_template(
                "status.html",
                job_id=job_id,
                status=f"Error: {e}",
                model=model,
                submitted_at=submitted_at,
                back_url=back_url,
                back_label=back_label
            )
    else:
        return render_template(
            "status.html",
            job_id=job_id,
            status="Running",
            model=model,
            submitted_at=submitted_at,
            include_inputs=meta.get("include_inputs", False),
            back_url=back_url,
            back_label=back_label
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

@app.route("/download-inputs/<job_id>")
def download_inputs(job_id):
    job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
    if not os.path.exists(job_dir):
        return f"Job {job_id} not found", 404

    input_zip_name = None
    meta_file = os.path.join(job_dir, "meta.json")
    if os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                meta = json.load(f)
            input_zip_name = meta.get("input_zip_name")
        except Exception:
            input_zip_name = None

    if input_zip_name:
        input_zip_path = os.path.join(job_dir, input_zip_name)
        if not os.path.exists(input_zip_path):
            input_zip_name = None

    if not input_zip_name:
        legacy_path = os.path.join(job_dir, "input.zip")
        if os.path.exists(legacy_path):
            input_zip_name = "input.zip"

    if not input_zip_name:
        return f"No inputs for job {job_id}", 404

    input_zip_path = os.path.join(job_dir, input_zip_name)
    if not os.path.exists(input_zip_path):
        return f"No inputs for job {job_id}", 404

    return send_file(input_zip_path, as_attachment=True)

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

@app.route("/jobs")
def jobs_archive():
    sort_by = request.args.get("sort_by", "submitted_at")
    sort_dir = request.args.get("sort_dir", "desc")

    allowed_sort_fields = {
        "submitted_at": "Submitted At",
        "model": "Model",
        "status": "Status",
        "route": "Route",
        "filename": "Filename",
        "elapsed_time": "Elapsed Time"
    }
    if sort_by not in allowed_sort_fields:
        sort_by = "submitted_at"
    if sort_dir not in ["asc", "desc"]:
        sort_dir = "desc"

    job_entries = []
    if os.path.exists(app.config["UPLOAD_FOLDER"]):
        for job_id in os.listdir(app.config["UPLOAD_FOLDER"]):
            job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
            if not os.path.isdir(job_dir):
                continue

            meta = {}
            meta_file = os.path.join(job_dir, "meta.json")
            if os.path.exists(meta_file):
                try:
                    with open(meta_file) as f:
                        meta = json.load(f)
                except Exception:
                    meta = {}

            zips = [
                f for f in os.listdir(job_dir)
                if f.startswith("results_") and f.endswith(".zip")
            ]
            zip_filename = max(zips) if zips else None

            status_text = "Unknown"
            if job_id in jobs:
                future = jobs[job_id]
                if future.done():
                    status_text = "Failed" if future.exception() else "Finished"
                else:
                    status_text = "Running"
            else:
                if meta.get("completed_at") or zip_filename:
                    status_text = "Finished"
                elif meta.get("submitted_at"):
                    status_text = "Running"

            source_route = meta.get("source_route")
            if not source_route and meta.get("group_by_subfolder"):
                source_route = "marc"
            route_label = "marc" if source_route == "marc" else "main"

            submitted_at = meta.get("submitted_at", "unknown")
            submitted_at_dt = None
            if submitted_at != "unknown":
                try:
                    submitted_at_dt = datetime.strptime(submitted_at, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    submitted_at_dt = None

            input_zip_name = meta.get("input_zip_name")
            input_zip_path = None
            if input_zip_name:
                input_zip_path = os.path.join(job_dir, input_zip_name)
                if not os.path.exists(input_zip_path):
                    input_zip_name = None
                    input_zip_path = None
            if not input_zip_name:
                legacy_input = os.path.join(job_dir, "input.zip")
                if os.path.exists(legacy_input):
                    input_zip_name = "input.zip"
                    input_zip_path = legacy_input

            job_entries.append({
                "job_id": job_id,
                "submitted_at": submitted_at,
                "submitted_at_dt": submitted_at_dt,
                "model": meta.get("model", "unknown"),
                "status": status_text,
                "route": route_label,
                "zip_filename": zip_filename,
                "elapsed_time": meta.get("elapsed_time", ""),
                "download_url": url_for("download", job_id=job_id)
                if zip_filename and status_text == "Finished"
                else None,
                "input_download_url": url_for("download_inputs", job_id=job_id)
                if input_zip_path
                else None,
                "mtime": os.path.getmtime(job_dir)
            })

    def parse_elapsed_seconds(value):
        if not value:
            return None
        try:
            days = 0
            rest = value
            if "day" in value:
                parts = value.split(", ")
                if len(parts) == 2:
                    day_part, rest = parts
                    days = int(day_part.split()[0])
            time_parts = rest.split(":")
            if len(time_parts) != 3:
                return None
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            seconds = float(time_parts[2])
            return days * 86400 + hours * 3600 + minutes * 60 + seconds
        except Exception:
            return None

    def sort_key(row):
        if sort_by == "submitted_at":
            return row["submitted_at_dt"] or datetime.fromtimestamp(row["mtime"])
        if sort_by == "model":
            value = row["model"] or ""
            return value if sort_dir == "desc" else (value or "~~~~")
        if sort_by == "status":
            value = row["status"] or ""
            return value if sort_dir == "desc" else (value or "~~~~")
        if sort_by == "route":
            value = row["route"] or ""
            return value if sort_dir == "desc" else (value or "~~~~")
        if sort_by == "filename":
            value = row["zip_filename"] or ""
            return value if sort_dir == "desc" else (value or "~~~~")
        if sort_by == "elapsed_time":
            value = parse_elapsed_seconds(row["elapsed_time"])
            if value is None:
                return float("inf") if sort_dir == "asc" else float("-inf")
            return value
        return row["submitted_at_dt"] or datetime.fromtimestamp(row["mtime"])

    job_entries.sort(key=sort_key, reverse=(sort_dir == "desc"))

    return render_template(
        "jobs.html",
        jobs=job_entries,
        sort_by=sort_by,
        sort_dir=sort_dir,
        sort_fields=allowed_sort_fields
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9513, debug=True)
