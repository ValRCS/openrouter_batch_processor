import os, requests, pandas as pd, time, json, zipfile
import base64
import mimetypes
from datetime import datetime
from config import UPLOAD_FOLDER

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

TEXT_EXTENSIONS = {".txt", ".md"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

def _normalize_rel(path, base_dir):
    return os.path.relpath(path, base_dir).replace(os.sep, "/")

def _list_files_sorted(base_dir):
    files = []
    for root, _, filenames in os.walk(base_dir):
        for fname in filenames:
            files.append(os.path.join(root, fname))
    files.sort(key=lambda p: _normalize_rel(p, base_dir))
    return files

def _build_groups(input_dir, group_by_subfolder):
    groups = []
    entries = sorted(os.listdir(input_dir))

    if group_by_subfolder:
        for entry in entries:
            full = os.path.join(input_dir, entry)
            if os.path.isdir(full):
                files = _list_files_sorted(full)
                group_id = f"{_normalize_rel(full, input_dir)}/"
                groups.append({"id": group_id, "files": files, "is_folder": True})
            elif os.path.isfile(full):
                groups.append({
                    "id": _normalize_rel(full, input_dir),
                    "files": [full],
                    "is_folder": False
                })
    else:
        for entry in entries:
            full = os.path.join(input_dir, entry)
            if os.path.isfile(full):
                groups.append({
                    "id": _normalize_rel(full, input_dir),
                    "files": [full],
                    "is_folder": False
                })

    return groups

def _collect_input_rows(input_dir):
    input_rows = []
    for root, _, filenames in os.walk(input_dir):
        for fname in filenames:
            fpath = os.path.join(root, fname)
            rel = _normalize_rel(fpath, input_dir)
            ext = os.path.splitext(fname)[1].lower()
            size = os.path.getsize(fpath)
            input_rows.append({
                "file_name": fname,
                "full_path": f"input/{rel}",
                "file_type": ext if ext else "unknown",
                "file_size": size
            })
    input_rows.sort(key=lambda row: row["full_path"])
    return input_rows

def _build_user_content(file_paths, input_dir, label_files):
    user_content = []
    supported = 0

    for fpath in file_paths:
        rel = _normalize_rel(fpath, input_dir)
        ext = os.path.splitext(fpath)[1].lower()

        if ext in TEXT_EXTENSIONS:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            if label_files:
                text = f"File: {rel}\n{text}"
            user_content.append({"type": "text", "text": text})
            supported += 1
        elif ext in IMAGE_EXTENSIONS:
            mime, _ = mimetypes.guess_type(fpath)
            if mime is None:
                mime = "image/png"
            with open(fpath, "rb") as img_file:
                img_b64 = base64.b64encode(img_file.read()).decode("utf-8")
            label = rel if label_files else os.path.basename(rel)
            user_content.append({"type": "text", "text": f"Please analyze image: {label}"})
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{img_b64}"}
            })
            supported += 1

    return user_content, supported

def _write_meta(job_dir, meta):
    meta_for_disk = dict(meta)
    api_key = meta_for_disk.get("api_key", "")
    meta_for_disk.pop("api_key", None)
    meta_for_disk["api_key_last8"] = api_key[-8:] if api_key else ""
    meta_file = os.path.join(job_dir, "meta.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta_for_disk, f, indent=2, ensure_ascii=False)
    return meta_file

def _output_filename(group_id, is_folder):
    normalized = group_id.rstrip("/")
    base = os.path.basename(normalized) if normalized else "output"
    if is_folder:
        return f"{base}_folder_output.txt"
    stem, _ = os.path.splitext(base)
    return f"{stem}_output.txt"

def process_job(job_id, meta):
    job_dir = os.path.join(UPLOAD_FOLDER, job_id)
    input_dir = os.path.join(job_dir, "input")
    output_path = os.path.join(job_dir, "output.csv")
    input_csv_path = os.path.join(job_dir, "input.csv")   # <-- new file

    # Generate timestamped ZIP name
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    zip_filename = f"results_{timestamp}.zip"
    zip_path = os.path.join(job_dir, zip_filename)

    system_prompt = meta["system_prompt"]
    api_key = meta["api_key"]
    model = meta.get("model", "google/gemini-2.5-flash")
    group_by_subfolder = meta.get("group_by_subfolder", False)
    separate_outputs = meta.get("separate_outputs", False)
    include_metadata = meta.get("include_metadata", False)

    # for progress tracking
    groups = _build_groups(input_dir, group_by_subfolder)
    total = len(groups)
    group_is_folder = {group["id"]: group["is_folder"] for group in groups}
    meta["total_files"] = total
    meta["processed_files"] = 0

    rows = []
    input_rows = _collect_input_rows(input_dir)   # <-- for input.csv

    for idx, group in enumerate(groups, start=1):
        group_id = group["id"]
        file_paths = group["files"]

        if not file_paths:
            rows.append({"file": group_id, "output": "Empty folder"})
            meta["processed_files"] = idx
            _write_meta(job_dir, meta)
            time.sleep(0.2)
            continue

        label_files = group["is_folder"] or len(file_paths) > 1
        user_content, supported = _build_user_content(file_paths, input_dir, label_files)

        if supported == 0:
            rows.append({"file": group_id, "output": "Unsupported file type"})
        else:
            payload = {
                "model": meta.get("model", "google/gemini-2.5-flash"),
                "messages": [
                    {"role": "system", "content": meta["system_prompt"]},
                    {"role": "user", "content": user_content}
                ]
            }

            headers = {"Authorization": f"Bearer {meta['api_key']}"}

            try:
                r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
                r.raise_for_status()
                data = r.json()
                reply = data["choices"][0]["message"]["content"]
            except Exception as e:
                reply = f"ERROR: {e}"

            rows.append({"file": group_id, "output": reply})

        # Update progress
        meta["processed_files"] = idx
        _write_meta(job_dir, meta)

        time.sleep(0.2)

    # Save CSV
    pd.DataFrame(rows).to_csv(output_path, index=False)
    # sort input.csv rows alphabetically by full_path
    df_input = pd.DataFrame(input_rows).sort_values(by="full_path")
    df_input.to_csv(input_csv_path, index=False)   # <-- save input.csv

    output_text_files = []
    if separate_outputs:
        output_text_dir = os.path.join(job_dir, "output_texts")
        os.makedirs(output_text_dir, exist_ok=True)
        for row in rows:
            group_id = row["file"]
            is_folder = group_is_folder.get(group_id, False)
            filename = _output_filename(group_id, is_folder)
            fpath = os.path.join(output_text_dir, filename)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(row["output"])
            output_text_files.append((fpath, filename))

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

    meta_file = _write_meta(job_dir, meta)

    # Create results.zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if separate_outputs:
            for fpath, filename in output_text_files:
                zf.write(fpath, arcname=filename)
            if include_metadata and os.path.exists(meta_file):
                zf.write(meta_file, arcname="meta.json")
        else:
            zf.write(output_path, arcname="output.csv")
            zf.write(input_csv_path, arcname="input.csv")   # <-- include in zip
            if include_metadata and os.path.exists(meta_file):
                zf.write(meta_file, arcname="meta.json")
        # Only include inputs if requested
        if meta.get("include_inputs", False):
            for fpath in _list_files_sorted(input_dir):
                rel = _normalize_rel(fpath, input_dir)
                zf.write(fpath, arcname=f"input/{rel}")

    return zip_path
