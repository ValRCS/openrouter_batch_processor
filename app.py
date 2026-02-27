from flask import Flask, request, render_template, redirect, url_for, send_file, jsonify
import os, uuid, zipfile, json, shutil, tempfile, hashlib, threading
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from config import UPLOAD_FOLDER, INPUT_ZIPS_FOLDER, ZIP_REGISTRY_PATH
from worker import process_job

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["EXISTING_ZIPS_FOLDER"] = INPUT_ZIPS_FOLDER
app.config["ZIP_REGISTRY_FILE"] = ZIP_REGISTRY_PATH
app.config["MARC_EXISTING_ZIPS_FOLDER"] = "/mnt/mi_rek"
app.config["MARC_EXISTING_FOLDERS_ROOT"] = "/mnt/mi_rek"
app.config["MARC_RESULTS_FOLDER"] = "/mnt/mi_rek/results"
app.config["MARC_HIDDEN_FOLDERS"] = {"results"}
os.makedirs(app.config["EXISTING_ZIPS_FOLDER"], exist_ok=True)

executor = ThreadPoolExecutor(max_workers=4)
jobs = {}
metas = {}
zip_registry_lock = threading.Lock()

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

def _file_sha256(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

def _normalize_rel_path(path):
    return path.replace("\\", "/").lstrip("./")

def _iter_directory_files_sorted(source_dir):
    files = []
    for root, _, filenames in os.walk(source_dir):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            rel_path = _normalize_rel_path(os.path.relpath(file_path, source_dir))
            files.append((rel_path, file_path))
    files.sort(key=lambda row: row[0])
    return files

def _content_sha256_for_directory(source_dir, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    for rel_path, file_path in _iter_directory_files_sorted(source_dir):
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()

def _content_sha256_for_zip(zip_path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = [info for info in zf.infolist() if not info.is_dir()]
        infos.sort(key=lambda info: _normalize_rel_path(info.filename))
        for info in infos:
            rel_path = _normalize_rel_path(info.filename)
            digest.update(rel_path.encode("utf-8"))
            digest.update(b"\0")
            with zf.open(info, "r") as src:
                while True:
                    chunk = src.read(chunk_size)
                    if not chunk:
                        break
                    digest.update(chunk)
            digest.update(b"\0")
    return digest.hexdigest()

def write_deterministic_zip_from_directory_contents(source_dir, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, file_path in _iter_directory_files_sorted(source_dir):
            info = zipfile.ZipInfo(filename=rel_path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            with zf.open(info, "w") as dst, open(file_path, "rb") as src:
                shutil.copyfileobj(src, dst, length=1024 * 1024)

def _load_zip_registry_unlocked():
    registry_path = app.config["ZIP_REGISTRY_FILE"]
    if not os.path.exists(registry_path):
        return {"version": 1, "entries": []}

    try:
        with open(registry_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"version": 1, "entries": []}

    if not isinstance(data, dict):
        return {"version": 1, "entries": []}

    entries = data.get("entries")
    if not isinstance(entries, list):
        data["entries"] = []

    if "version" not in data:
        data["version"] = 1

    return data

def _save_zip_registry_unlocked(registry):
    registry_path = app.config["ZIP_REGISTRY_FILE"]
    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    temp_path = f"{registry_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, registry_path)

def _prune_registry_entries_unlocked(registry, zips_folder):
    valid_entries = []
    for entry in registry.get("entries", []):
        zip_name = os.path.basename((entry.get("zip_name") or "").strip())
        if not zip_name:
            continue
        zip_path = os.path.join(zips_folder, zip_name)
        if os.path.isfile(zip_path):
            entry["zip_name"] = zip_name
            valid_entries.append(entry)
    registry["entries"] = valid_entries

def _find_registry_match_unlocked(registry, zips_folder, content_sha256=None, zip_sha256=None):
    for entry in registry.get("entries", []):
        zip_name = os.path.basename((entry.get("zip_name") or "").strip())
        if not zip_name:
            continue
        zip_path = os.path.join(zips_folder, zip_name)
        if not os.path.isfile(zip_path):
            continue
        if content_sha256 and entry.get("content_sha256") == content_sha256:
            return entry
        if zip_sha256 and entry.get("zip_sha256") == zip_sha256:
            return entry
    return None

def _build_storage_zip_name(original_name, content_sha256, zips_folder):
    safe_name = secure_filename(os.path.basename((original_name or "").strip()))
    if not safe_name:
        safe_name = "input.zip"
    if not safe_name.lower().endswith(".zip"):
        safe_name = f"{safe_name}.zip"
    stem, ext = os.path.splitext(safe_name)
    stem = stem[:80] or "input"
    suffix = content_sha256[:12]
    candidate = f"{stem}_{suffix}{ext}"
    final_path = os.path.join(zips_folder, candidate)
    if not os.path.exists(final_path):
        return candidate

    counter = 2
    while True:
        candidate = f"{stem}_{suffix}_{counter}{ext}"
        final_path = os.path.join(zips_folder, candidate)
        if not os.path.exists(final_path):
            return candidate
        counter += 1

def _build_registry_entry(zip_name, zip_sha256, content_sha256, source):
    zips_folder = app.config["EXISTING_ZIPS_FOLDER"]
    zip_path = os.path.join(zips_folder, zip_name)
    size_bytes = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
    return {
        "zip_name": zip_name,
        "zip_sha256": zip_sha256,
        "content_sha256": content_sha256,
        "size_bytes": size_bytes,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source
    }

def _find_matching_zip_file_on_disk(content_sha256=None, zip_sha256=None):
    zips_folder = app.config["EXISTING_ZIPS_FOLDER"]
    if not os.path.isdir(zips_folder):
        return None, None, None

    for filename in os.listdir(zips_folder):
        if not filename.lower().endswith(".zip"):
            continue
        zip_path = os.path.join(zips_folder, filename)
        if not os.path.isfile(zip_path):
            continue

        try:
            file_zip_sha256 = _file_sha256(zip_path) if zip_sha256 else None
        except Exception:
            continue

        if zip_sha256 and file_zip_sha256 == zip_sha256:
            return zip_path, file_zip_sha256, None

        if content_sha256:
            try:
                file_content_sha256 = _content_sha256_for_zip(zip_path)
            except Exception:
                continue
            if file_content_sha256 == content_sha256:
                if file_zip_sha256 is None:
                    file_zip_sha256 = _file_sha256(zip_path)
                return zip_path, file_zip_sha256, file_content_sha256

    return None, None, None

def _register_existing_zip_path(existing_zip_path, zip_sha256=None, content_sha256=None):
    zips_folder = app.config["EXISTING_ZIPS_FOLDER"]
    zip_name = os.path.basename(existing_zip_path)

    with zip_registry_lock:
        registry = _load_zip_registry_unlocked()
        _prune_registry_entries_unlocked(registry, zips_folder)
        for entry in registry.get("entries", []):
            if entry.get("zip_name") == zip_name:
                return entry, False

    if zip_sha256 is None:
        zip_sha256 = _file_sha256(existing_zip_path)
    if content_sha256 is None:
        content_sha256 = _content_sha256_for_zip(existing_zip_path)

    with zip_registry_lock:
        registry = _load_zip_registry_unlocked()
        _prune_registry_entries_unlocked(registry, zips_folder)
        existing_entry = _find_registry_match_unlocked(
            registry,
            zips_folder,
            content_sha256=content_sha256,
            zip_sha256=zip_sha256
        )
        if existing_entry:
            return existing_entry, False

        entry = _build_registry_entry(
            zip_name=zip_name,
            zip_sha256=zip_sha256,
            content_sha256=content_sha256,
            source="existing"
        )
        registry["entries"].append(entry)
        _save_zip_registry_unlocked(registry)
        return entry, True

def _register_uploaded_zip(candidate_zip_path, original_name):
    zips_folder = app.config["EXISTING_ZIPS_FOLDER"]
    zip_sha256 = _file_sha256(candidate_zip_path)
    content_sha256 = _content_sha256_for_zip(candidate_zip_path)

    with zip_registry_lock:
        registry = _load_zip_registry_unlocked()
        _prune_registry_entries_unlocked(registry, zips_folder)
        existing_entry = _find_registry_match_unlocked(
            registry,
            zips_folder,
            content_sha256=content_sha256,
            zip_sha256=zip_sha256
        )
        if existing_entry:
            if os.path.exists(candidate_zip_path):
                os.remove(candidate_zip_path)
            return existing_entry, False

    matched_path, matched_zip_sha256, matched_content_sha256 = _find_matching_zip_file_on_disk(
        content_sha256=content_sha256,
        zip_sha256=zip_sha256
    )
    if matched_path:
        existing_entry, _ = _register_existing_zip_path(
            matched_path,
            zip_sha256=matched_zip_sha256 or zip_sha256,
            content_sha256=matched_content_sha256 or content_sha256
        )
        if os.path.exists(candidate_zip_path):
            os.remove(candidate_zip_path)
        return existing_entry, False

    with zip_registry_lock:
        registry = _load_zip_registry_unlocked()
        _prune_registry_entries_unlocked(registry, zips_folder)
        existing_entry = _find_registry_match_unlocked(
            registry,
            zips_folder,
            content_sha256=content_sha256,
            zip_sha256=zip_sha256
        )
        if existing_entry:
            if os.path.exists(candidate_zip_path):
                os.remove(candidate_zip_path)
            return existing_entry, False

        zip_name = _build_storage_zip_name(original_name, content_sha256, zips_folder)
        final_path = os.path.join(zips_folder, zip_name)
        try:
            os.replace(candidate_zip_path, final_path)
        except OSError:
            shutil.move(candidate_zip_path, final_path)

        entry = _build_registry_entry(
            zip_name=zip_name,
            zip_sha256=zip_sha256,
            content_sha256=content_sha256,
            source="uploaded"
        )
        registry["entries"].append(entry)
        _save_zip_registry_unlocked(registry)
        return entry, True

def _register_folder_contents(folder_path, original_name):
    zips_folder = app.config["EXISTING_ZIPS_FOLDER"]
    content_sha256 = _content_sha256_for_directory(folder_path)

    with zip_registry_lock:
        registry = _load_zip_registry_unlocked()
        _prune_registry_entries_unlocked(registry, zips_folder)
        existing_entry = _find_registry_match_unlocked(
            registry,
            zips_folder,
            content_sha256=content_sha256
        )
        if existing_entry:
            return existing_entry, False

    matched_path, matched_zip_sha256, matched_content_sha256 = _find_matching_zip_file_on_disk(
        content_sha256=content_sha256
    )
    if matched_path:
        existing_entry, _ = _register_existing_zip_path(
            matched_path,
            zip_sha256=matched_zip_sha256,
            content_sha256=matched_content_sha256 or content_sha256
        )
        return existing_entry, False

    fd, temp_zip_path = tempfile.mkstemp(
        prefix="input_build_",
        suffix=".zip.tmp",
        dir=zips_folder
    )
    os.close(fd)
    try:
        write_deterministic_zip_from_directory_contents(folder_path, temp_zip_path)
        zip_sha256 = _file_sha256(temp_zip_path)

        with zip_registry_lock:
            registry = _load_zip_registry_unlocked()
            _prune_registry_entries_unlocked(registry, zips_folder)
            existing_entry = _find_registry_match_unlocked(
                registry,
                zips_folder,
                content_sha256=content_sha256,
                zip_sha256=zip_sha256
            )
            if existing_entry:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                return existing_entry, False

            zip_name = _build_storage_zip_name(original_name, content_sha256, zips_folder)
            final_path = os.path.join(zips_folder, zip_name)
            try:
                os.replace(temp_zip_path, final_path)
            except OSError:
                shutil.move(temp_zip_path, final_path)

            entry = _build_registry_entry(
                zip_name=zip_name,
                zip_sha256=zip_sha256,
                content_sha256=content_sha256,
                source="folder"
            )
            registry["entries"].append(entry)
            _save_zip_registry_unlocked(registry)
            return entry, True
    finally:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)

def persist_job_meta(job_dir, meta):
    meta_for_disk = dict(meta)
    api_key = meta_for_disk.get("api_key", "")
    meta_for_disk.pop("api_key", None)
    meta_for_disk["api_key_last8"] = api_key[-8:] if api_key else ""
    meta_path = os.path.join(job_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_for_disk, f, indent=2, ensure_ascii=False)
    return meta_path

def resolve_job_input_zip(job_dir, meta):
    shared_relpath = os.path.basename((meta.get("input_zip_relpath") or "").strip())
    if shared_relpath:
        _, shared_path = resolve_existing_zip(shared_relpath, app.config["EXISTING_ZIPS_FOLDER"])
        if shared_path:
            return shared_relpath, shared_path

    shared_name = os.path.basename((meta.get("input_zip_name") or "").strip())
    if shared_name:
        _, shared_path = resolve_existing_zip(shared_name, app.config["EXISTING_ZIPS_FOLDER"])
        if shared_path:
            return shared_name, shared_path

    if shared_name:
        local_path = os.path.join(job_dir, shared_name)
        if os.path.exists(local_path):
            return shared_name, local_path

    legacy_path = os.path.join(job_dir, "input.zip")
    if os.path.exists(legacy_path):
        return "input.zip", legacy_path

    return None, None

def resolve_existing_zip(zip_name, zips_folder):
    candidate_name = os.path.basename((zip_name or "").strip())
    if not candidate_name or not candidate_name.lower().endswith(".zip"):
        return None, None

    base_dir = os.path.abspath(zips_folder)
    zip_path = os.path.abspath(os.path.join(base_dir, candidate_name))
    if os.path.commonpath([base_dir, zip_path]) != base_dir:
        return None, None

    if not os.path.isfile(zip_path):
        return None, None

    return candidate_name, zip_path

def list_existing_zips(zips_dir):
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

def resolve_existing_folder(folder_name, folders_root, excluded_names=None):
    candidate_name = os.path.basename((folder_name or "").strip())
    if not candidate_name:
        return None, None
    if excluded_names and candidate_name in excluded_names:
        return None, None

    base_dir = os.path.abspath(folders_root)
    folder_path = os.path.abspath(os.path.join(base_dir, candidate_name))
    if os.path.commonpath([base_dir, folder_path]) != base_dir:
        return None, None

    if not os.path.isdir(folder_path):
        return None, None

    return candidate_name, folder_path

def list_existing_folders(folders_root, excluded_names=None):
    if not os.path.isdir(folders_root):
        return []

    excluded = set(excluded_names or [])
    entries = []
    for name in os.listdir(folders_root):
        if name in excluded:
            continue
        folder_path = os.path.join(folders_root, name)
        if not os.path.isdir(folder_path):
            continue

        stat = os.stat(folder_path)
        child_count = len(os.listdir(folder_path))
        entries.append({
            "name": name,
            "items_label": f"{child_count} item{'s' if child_count != 1 else ''}",
            "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "modified_ts": stat.st_mtime
        })

    entries.sort(key=lambda row: row["modified_ts"], reverse=True)
    for entry in entries:
        entry.pop("modified_ts", None)

    return entries

def extract_zip_to_directory(zip_path, target_dir):
    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)

def prepare_job_input(job_id, meta):
    job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
    input_source = meta.get("input_source")
    source_route = meta.get("source_route", "index")

    if input_source == "folder":
        folder_name = meta.get("input_folder_name", "")
        folder_root = meta.get("input_folder_root", app.config["MARC_EXISTING_FOLDERS_ROOT"])
        excluded_folders = app.config["MARC_HIDDEN_FOLDERS"] if source_route == "marc" else None
        resolved_name, folder_path = resolve_existing_folder(
            folder_name,
            folder_root,
            excluded_names=excluded_folders
        )
        if not folder_path:
            raise ValueError(f"Selected folder was not found in {folder_root}.")

        folder_stem = secure_filename(resolved_name) or "folder"
        suggested_name = f"inputs_{folder_stem}.zip" if source_route == "marc" else f"{folder_stem}.zip"
        entry, _ = _register_folder_contents(folder_path, suggested_name)
    elif input_source == "existing":
        selected_zip_name = meta.get("selected_existing_zip", "")
        _, existing_zip_path = resolve_existing_zip(selected_zip_name, app.config["EXISTING_ZIPS_FOLDER"])
        if not existing_zip_path:
            raise ValueError("Selected ZIP file was not found in data/zips.")
        entry, _ = _register_existing_zip_path(existing_zip_path)
    elif input_source == "uploaded":
        staging_name = os.path.basename((meta.get("staging_upload_name") or "").strip())
        if not staging_name:
            raise ValueError("Uploaded ZIP staging file is missing.")
        staging_path = os.path.join(job_dir, staging_name)
        if not os.path.isfile(staging_path):
            raise ValueError("Uploaded ZIP staging file was not found.")
        original_name = meta.get("uploaded_original_name") or "upload.zip"
        entry, _ = _register_uploaded_zip(staging_path, original_name)
    else:
        raise ValueError("Unknown input source.")

    shared_zip_name = entry["zip_name"]
    shared_zip_path = os.path.join(app.config["EXISTING_ZIPS_FOLDER"], shared_zip_name)
    if not os.path.isfile(shared_zip_path):
        raise ValueError("Shared input ZIP was not found after registration.")

    input_dir = os.path.join(job_dir, "input")
    extract_zip_to_directory(shared_zip_path, input_dir)

    meta["input_zip_name"] = shared_zip_name
    meta["input_zip_relpath"] = shared_zip_name
    meta["input_zip_hash"] = entry.get("zip_sha256", "")
    meta["input_content_hash"] = entry.get("content_sha256", "")
    meta["input_storage"] = "shared"
    meta["input_status"] = "ready"
    meta["input_prepared_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    persist_job_meta(job_dir, meta)

def cleanup_job_input_dir(job_id):
    job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
    input_dir = os.path.join(job_dir, "input")
    if os.path.isdir(input_dir):
        shutil.rmtree(input_dir, ignore_errors=True)

def cleanup_staged_upload(job_id, meta):
    staging_name = os.path.basename((meta.get("staging_upload_name") or "").strip())
    if not staging_name:
        return
    job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
    staging_path = os.path.join(job_dir, staging_name)
    if os.path.isfile(staging_path):
        os.remove(staging_path)

def run_job_pipeline(job_id, meta):
    job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
    try:
        meta["input_status"] = "preparing"
        persist_job_meta(job_dir, meta)
        prepare_job_input(job_id, meta)
        return process_job(job_id, meta)
    except Exception as e:
        meta["input_status"] = "error"
        meta["input_error"] = str(e)
        persist_job_meta(job_dir, meta)
        raise
    finally:
        cleanup_staged_upload(job_id, meta)
        cleanup_job_input_dir(job_id)

def handle_submission(
    template_name,
    group_by_subfolder=False,
    source_route="index",
    template_context=None,
    existing_zips_folder=None,
    existing_zips_label=None,
    allow_existing_folders=False,
    existing_folders_root=None,
    existing_folders_label=None
):
    template_context = template_context or {}
    if existing_zips_folder is None:
        existing_zips_folder = app.config["EXISTING_ZIPS_FOLDER"]
    if existing_zips_label is None:
        existing_zips_label = "data/zips"
    if existing_folders_root is None:
        existing_folders_root = app.config["MARC_EXISTING_FOLDERS_ROOT"]
    if existing_folders_label is None:
        existing_folders_label = existing_folders_root

    if request.method == "POST":
        api_key = request.form["api_key"]
        system_prompt = request.form["system_prompt"]
        username = request.form.get("username", "").strip()
        custom_footer = request.form.get("customFooter", "")
        model_custom = request.form.get("model_custom", "").strip()
        model_dropdown = request.form.get("model_dropdown", "google/gemini-3-flash-preview")
        model = model_custom if model_custom else model_dropdown
        file = request.files.get("zipfile")
        selected_existing_zip = request.form.get("existing_zip", "").strip()
        selected_existing_folder = request.form.get("existing_folder", "").strip()

        input_source = ""
        selected_folder_name = ""
        selected_zip_name = ""
        uploaded_original_name = ""
        staged_upload_name = ""
        uploaded_filename = file.filename if file else ""
        if allow_existing_folders and selected_existing_folder:
            selected_folder_name, existing_folder_path = resolve_existing_folder(
                selected_existing_folder,
                existing_folders_root,
                excluded_names=app.config["MARC_HIDDEN_FOLDERS"] if source_route == "marc" else None
            )
            if not existing_folder_path:
                context = dict(template_context)
                context["error"] = f"Selected folder was not found in {existing_folders_label}."
                return render_template(template_name, **context), 400
            input_source = "folder"
        elif selected_existing_zip:
            selected_zip_name, existing_zip_path = resolve_existing_zip(selected_existing_zip, existing_zips_folder)
            if not existing_zip_path:
                context = dict(template_context)
                context["error"] = f"Selected ZIP file was not found in {existing_zips_label}."
                return render_template(template_name, **context), 400
            input_source = "existing"
        elif uploaded_filename:
            uploaded_original_name = secure_filename(uploaded_filename)
            if not uploaded_original_name:
                uploaded_original_name = "upload.zip"
            elif not uploaded_original_name.lower().endswith(".zip"):
                uploaded_original_name = f"{uploaded_original_name}.zip"
            if source_route == "marc" and not uploaded_original_name.lower().startswith("inputs_"):
                uploaded_original_name = f"inputs_{uploaded_original_name}"
            input_source = "uploaded"
        else:
            context = dict(template_context)
            if allow_existing_folders:
                context["error"] = f"Please upload a ZIP file or select a folder from {existing_folders_label}."
            else:
                context["error"] = f"Please upload a ZIP file or select one from {existing_zips_label}."
            return render_template(template_name, **context), 400

        job_id = str(uuid.uuid4())
        job_dir = os.path.join(app.config["UPLOAD_FOLDER"], job_id)
        os.makedirs(job_dir, exist_ok=True)
        if input_source == "uploaded":
            staged_upload_name = "uploaded_input_staging.zip"
            staged_upload_path = os.path.join(job_dir, staged_upload_name)
            file.save(staged_upload_path)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        include_inputs = "include_inputs" in request.form
        separate_outputs = "separate_outputs" in request.form
        include_metadata = "include_metadata" in request.form
        save_concat_results = "save_concat_results" in request.form

        meta = {
            "api_key": api_key,
            "system_prompt": system_prompt,
            "username": username if source_route == "marc" else "",
            "custom_footer": custom_footer if source_route == "marc" else "",
            "model": model,
            "submitted_at": timestamp,
            "include_inputs": include_inputs,
            "group_by_subfolder": group_by_subfolder,
            "separate_outputs": separate_outputs,
            "include_metadata": include_metadata,
            "save_concat_results": save_concat_results if source_route == "marc" else False,
            "concat_results_dir": app.config["MARC_RESULTS_FOLDER"] if source_route == "marc" else "",
            "input_source": input_source,
            "selected_existing_zip": selected_zip_name,
            "uploaded_original_name": uploaded_original_name,
            "staging_upload_name": staged_upload_name,
            "input_folder_name": selected_folder_name if input_source == "folder" else "",
            "input_folder_root": existing_folders_root if input_source == "folder" else "",
            "input_zip_name": selected_zip_name if input_source == "existing" else "",
            "input_zip_relpath": selected_zip_name if input_source == "existing" else "",
            "input_zip_hash": "",
            "input_content_hash": "",
            "input_storage": "shared",
            "input_status": "pending",
            "source_route": source_route
        }
        persist_job_meta(job_dir, meta)

        future = executor.submit(run_job_pipeline, job_id, meta)
        jobs[job_id] = future
        metas[job_id] = meta

        return redirect(url_for("status", job_id=job_id))

    return render_template(template_name, **template_context)

@app.route("/", methods=["GET", "POST"])
def index():
    existing_zips_folder = app.config["EXISTING_ZIPS_FOLDER"]
    return handle_submission(
        "index.html",
        group_by_subfolder=True,
        source_route="index",
        template_context={
            "existing_zips": list_existing_zips(existing_zips_folder),
            "existing_zips_label": "data/zips"
        },
        existing_zips_folder=existing_zips_folder,
        existing_zips_label="data/zips"
    )

@app.route("/marc", methods=["GET", "POST"])
def marc():
    existing_zips_folder = app.config["EXISTING_ZIPS_FOLDER"]
    existing_folders_root = app.config["MARC_EXISTING_FOLDERS_ROOT"]
    hidden_folders = app.config["MARC_HIDDEN_FOLDERS"]
    return handle_submission(
        "marc.html",
        group_by_subfolder=True,
        source_route="marc",
        template_context={
            "existing_folders": list_existing_folders(existing_folders_root, excluded_names=hidden_folders),
            "existing_folders_label": existing_folders_root
        },
        existing_zips_folder=existing_zips_folder,
        existing_zips_label="data/zips",
        allow_existing_folders=True,
        existing_folders_root=existing_folders_root,
        existing_folders_label=existing_folders_root
    )

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

    meta = {}
    meta_file = os.path.join(job_dir, "meta.json")
    if os.path.exists(meta_file):
        try:
            with open(meta_file) as f:
                meta = json.load(f)
        except Exception:
            meta = {}

    input_zip_name, input_zip_path = resolve_job_input_zip(job_dir, meta)

    if not input_zip_name or not input_zip_path:
        return f"No inputs for job {job_id}", 404

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

            input_zip_name, input_zip_path = resolve_job_input_zip(job_dir, meta)

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
                "input_zip_name": input_zip_name,
                "input_zip_hash": meta.get("input_zip_hash", ""),
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
    app.run(host="0.0.0.0", port=9513, debug=True, threaded=True)
