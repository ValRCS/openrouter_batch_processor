# OpenRouter Batch Processor

Minimal Flask application for batch-processing text files through OpenRouter.ai API.

## Features
- Upload ZIP of text files
- Provide API key, system prompt, and model
- Jobs run in background threads (ThreadPoolExecutor)
- Results packaged in timestamped ZIP containing selected output artifacts:
  - separate text files and/or `output.csv` and/or `output.json`
  - meta.json (with timestamps, model info)

## Running

```bash
pip install -r requirements.txt
python app.py
```

The app runs on http://localhost:9513 (or configured host).

## MARC shared-folder configuration

The MARC workflow defaults to `/mnt/mi_rek`, which is the deployment path on Ubuntu.
For local Windows use, override it with environment variables or command-line flags.

PowerShell session-only environment variable:

```powershell
$env:MARC_EXISTING_FOLDERS_ROOT = 'L:\'
python app.py
```

If only `MARC_EXISTING_FOLDERS_ROOT` or `MARC_ROOT` is set, MARC concatenated results default to `<root>\results`, so `L:\` becomes `L:\results`.
Override the results path separately when needed:

```powershell
$env:MARC_EXISTING_FOLDERS_ROOT = 'L:\'
$env:MARC_RESULTS_FOLDER = 'L:\results'
python app.py
```

Permanent user environment variables on Windows:

```powershell
[Environment]::SetEnvironmentVariable('MARC_EXISTING_FOLDERS_ROOT', 'L:\', 'User')
[Environment]::SetEnvironmentVariable('MARC_RESULTS_FOLDER', 'L:\results', 'User')
```

Restart PowerShell after setting permanent variables.

Command-line override:

```powershell
python app.py --marc-root 'L:\'
```

Available MARC settings, in precedence order: command-line flag, environment variable, default.

- `--marc-root`, `MARC_EXISTING_FOLDERS_ROOT`, or `MARC_ROOT`: existing-folder root. Default: `/mnt/mi_rek`.
- `--marc-results-folder` or `MARC_RESULTS_FOLDER`: concatenated results folder. Default: `/mnt/mi_rek/results`, or `<marc-root>\results` when the root is overridden.
- `--marc-existing-zips-folder` or `MARC_EXISTING_ZIPS_FOLDER`: MARC existing ZIP folder. Default: the MARC root.

## License
MIT
