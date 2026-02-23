import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "data", "jobs")
INPUT_ZIPS_FOLDER = os.path.join(BASE_DIR, "data", "zips")
ZIP_REGISTRY_PATH = os.path.join(INPUT_ZIPS_FOLDER, "index.json")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INPUT_ZIPS_FOLDER, exist_ok=True)
