# Intelligent Media Processing Pipeline

A lightweight FastAPI backend that accepts vehicle images, stores upload metadata, processes them asynchronously, and returns structured quality analysis results. The system demonstrates a practical, production-minded queue-based design without depending on heavy ML infrastructure.

## Architecture

### Service flow

1. Client uploads a file to `POST /api/v1/uploads`.
2. The API validates the file type and writes the bytes to the local upload directory.
3. A database row is created with a job ID, filename, content type, and file size.
4. The job is queued in an in-memory background worker.
5. The worker updates the status to `processing`, runs image heuristics, and stores analysis results in the DB.
6. The client polls `GET /api/v1/jobs/{job_id}/status` and `GET /api/v1/jobs/{job_id}/results`.

### Processing flow

The worker performs a small set of heuristic checks against the uploaded image:

- blur detection
- brightness / low-light detection
- duplicate image detection using content similarity against prior uploads
- screenshot heuristics
- photo-of-photo heuristics
- suspicious edit heuristics
- number plate format validation (lightweight pattern check)

These checks are intentionally heuristic and explainable. They are useful for triage and validation, even when they are not a full ML solution.

### Queue strategy

The project uses an in-memory queue backed by a background thread. This keeps the local system simple and easy to run while still respecting the async requirement.

Why this approach:

- minimal setup for local development
- no external broker dependency
- clear separation between API handling and processing
- easy to swap to RabbitMQ, Redis Queue, SQS, or BullMQ in production

### Major design decisions

- SQLite is used by default for local execution and easy setup.
- File storage occurs on disk, while metadata remains in the database.
- The status model keeps the job lifecycle explicit: `queued` -> `processing` -> `completed` or `failed`.
- Analysis results remain structured and easy to extend with more checks later.
- The implementation favors explainable heuristics over opaque black-box inference.

## Project structure

- `app/main.py` – API routes and job orchestration
- `app/queue.py` – in-memory queue and background worker
- `app/analysis.py` – image checks and heuristics
- `app/models.py` – SQLAlchemy database models
- `app/database.py` – DB engine and initialization
- `tests/test_api.py` – API and async processing checks

## AI usage disclosure

I used AI to help with a few parts of this assignment:

- scaffolding the FastAPI service structure
- drafting the database schema and API routes
- generating the image-check heuristics and status API design
- writing the README and sample request payloads

What AI helped with:

- quickly producing a clean project skeleton
- suggesting a realistic status model and queue architecture
- validating naming and module organization

Where AI output was wrong or incomplete:

- the initial model design had a reserved SQLAlchemy field name issue (`metadata`), which required manual debugging
- some early heuristics were too simplistic and needed calibration to match the actual tests
- the first version did not properly ensure SQLite tables existed before the upload endpoint inserted rows

How I validated AI-generated code:

- I ran the API test suite after each fix
- I verified the job lifecycle end-to-end across upload → queue → processing → results
- I checked the actual database behavior and corrected issues directly rather than trusting the generated code blindly

## Trade-offs

### Intentionally simplified

- in-memory queue instead of distributed broker
- heuristic-based checks instead of real OCR or deep CV models
- SQLite instead of Postgres for local execution
- a lightweight plate validation rather than a true vehicle-recognition system

### If more time were available

- replace the in-memory queue with RabbitMQ/Redis/BullMQ
- add real OCR with Tesseract or cloud vision
- add image hashing and stronger duplicate detection
- add retry policies and dead-letter handling
- add structured logging, metrics, and tracing
- add rate limiting and per-user quotas

### Scalability concerns

- the current queue is single-process and in-memory, so it will not scale across multiple app instances
- local disk storage is fine for demos but not for multi-node deployments
- duplicate detection is only approximate and is kept in a simple in-memory registry

### Failure handling concerns

- failures are surfaced through the `failed` status and `failure_reason`
- retries are not implemented yet
- processing errors are currently logged by the worker, but production-grade alerting would be needed

## Interactive / bonus capabilities

This project can be extended with several practical enhancements to make it more interactive and production-ready:

- Dashboard/UI: a simple web dashboard to upload images, display job status, and view results visually
- Analytics: trends for blur rate, duplicate rate, low-light rate, and other quality issues over time
- Confidence scoring: each image can carry a numeric confidence score summarizing the likelihood of a valid or suspicious upload
- Retry mechanisms: automatic retry for transient failures or queue processing errors
- Concurrency handling: worker pool support for multiple images being processed in parallel
- Automated tests: API-level validation and regression tests for upload, status, result, and duplicate detection behavior

These are optional enhancements that improve usability, operational visibility, and reliability beyond the core backend flow.

## Running instructions

### Direct local run (copy/paste)

From the project folder:

```bash
cd c:\Users\USER\OneDrive\Documents\assignment
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open the dashboard in a browser to use the upload UI:

```text
http://localhost:8000/dashboard
```

If you want to inspect the API directly, the docs are also available at:

```text
http://localhost:8000/docs
```

### Local Python setup

1. Create and activate a virtual environment
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. Test the API with sample requests using the endpoints below.

### Docker

A minimal Docker setup is also included:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
docker run -p 8000:8000 media-pipeline
```

or with Docker Compose:

```bash
docker compose up --build
```

After starting the app, open the dashboard at:

```text
http://localhost:8000/dashboard
```

This is the main web interface for uploading images and tracking job status. The API docs remain available at:

```text
http://localhost:8000/docs
```

## API examples

### Upload an image

```bash
curl -X POST "http://localhost:8000/api/v1/uploads" \
  -F "file=@/path/to/vehicle.jpg;type=image/jpeg"
```

Example response:

```json
{
  "processing_id": "b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f",
  "status": "queued",
  "message": "Upload accepted and queued for processing"
}
```

### Check job status

```bash
curl "http://localhost:8000/api/v1/jobs/b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f/status"
```

Example response:

```json
{
  "id": "b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f",
  "status": "completed",
  "filename": "vehicle.jpg",
  "failure_reason": null,
  "confidence_score": 0.73
}
```

### Fetch job results

```bash
curl "http://localhost:8000/api/v1/jobs/b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f/results"
```

Example response:

```json
{
  "job_id": "b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f",
  "status": "completed",
  "issues": ["blur", "low_light"],
  "checks": [
    {
      "name": "blur",
      "passed": false,
      "severity": "warning",
      "message": "Image appears blurry"
    }
  ],
  "summary": {
    "dimensions": {"width": 1200, "height": 800},
    "blur_score": 18.4,
    "brightness": 72.3
  }
}
```

### Fetch failure reason

```bash
curl "http://localhost:8000/api/v1/jobs/b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f/failure"
```

## Assumptions

- the system is designed for local and demo deployments first, not enterprise-scale throughput
- uploaded files are vehicle or field images, so the analysis focuses on document-style and scene-quality heuristics
- exact OCR or plate recognition is intentionally approximated because the assignment emphasizes engineering quality and system design over model accuracy

## Testing

The project includes a small automated test suite covering:

- upload acceptance
- async job completion
- result fetch behavior
- duplicate detection heuristics

Run tests with:

```bash
pytest -q
```
#   a s s i g n m e n t  
 