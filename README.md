# OpenRouter Batch Processor

Minimal Flask application for batch-processing text files through OpenRouter.ai API.

## Features
- Upload ZIP of text files
- Provide API key, system prompt, and model
- Jobs run in background threads (ThreadPoolExecutor)
- Results packaged in timestamped ZIP containing:
  - output.csv
  - meta.json (with timestamps, model info)
  - original input files

## Running

```bash
pip install -r requirements.txt
python app.py
```

The app runs on http://localhost:9513 (or configured host).

## License
MIT
