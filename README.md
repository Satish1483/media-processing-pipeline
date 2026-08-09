# Intelligent Media Processing Pipeline

A lightweight **FastAPI backend** that accepts vehicle images, stores upload metadata, processes them asynchronously, and returns structured image-quality analysis results.

The system demonstrates a practical, production-minded, queue-based architecture without depending on heavy ML infrastructure.

---

## Architecture

### Service Flow

1. Client uploads a file to `POST /api/v1/uploads`.
2. The API validates the file type and writes the file to the local upload directory.
3. A database row is created with a job ID, filename, content type, and file size.
4. The job is added to an in-memory background queue.
5. The worker updates the status to `processing`, runs image heuristics, and stores the analysis results in the database.
6. The client polls the job status and results using:

   * `GET /api/v1/jobs/{job_id}/status`
   * `GET /api/v1/jobs/{job_id}/results`

### Processing Flow

The worker performs a set of lightweight and explainable heuristic checks against the uploaded image:

* Blur detection
* Brightness / low-light detection
* Duplicate image detection using content similarity
* Screenshot detection heuristics
* Photo-of-photo detection heuristics
* Suspicious edit detection heuristics
* Number plate format validation using a lightweight pattern check

These checks are intentionally heuristic and explainable. They are useful for image triage and validation, although they are not intended to replace a full ML-based computer vision solution.

---

## Queue Strategy

The project uses an **in-memory queue backed by a background thread**.

This keeps the local system simple while still satisfying the asynchronous processing requirement.

### Why This Approach?

* Minimal setup for local development
* No external broker dependency
* Clear separation between API handling and processing
* Easy to replace with RabbitMQ, Redis Queue, AWS SQS, or BullMQ in production

---

## Major Design Decisions

* **SQLite** is used by default for simple local execution.
* Image files are stored on disk, while metadata is stored in the database.
* The job lifecycle is explicitly maintained using:

  * `queued`
  * `processing`
  * `completed`
  * `failed`
* Analysis results are stored in a structured format that can be extended with additional checks.
* The implementation favors explainable heuristics instead of opaque black-box inference.

---

## Project Structure

```text
media-processing-pipeline/
│
├── app/
│   ├── __init__.py
│   ├── analysis.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── queue.py
│   └── registry.py
│
├── tests/
│   └── test_api.py
│
├── test_storage/
│   └── sample vehicle images
│
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── reset_upload_history.py
└── README.md
```

### Important Files

| File                | Description                           |
| ------------------- | ------------------------------------- |
| `app/main.py`       | API routes and job orchestration      |
| `app/queue.py`      | In-memory queue and background worker |
| `app/analysis.py`   | Image checks and heuristics           |
| `app/models.py`     | SQLAlchemy database models            |
| `app/database.py`   | Database engine and initialization    |
| `app/registry.py`   | Duplicate detection registry          |
| `tests/test_api.py` | API and asynchronous processing tests |

---

## AI Usage Disclosure

AI was used to assist with selected parts of this assignment.

### What AI Helped With

* Scaffolding the FastAPI service structure
* Drafting the database schema and API routes
* Generating initial image-check heuristics
* Designing the job status API
* Writing the README and sample request payloads

### How AI Helped

AI assistance was mainly used to:

* Quickly produce a clean project skeleton
* Suggest a realistic status model and queue architecture
* Improve naming and module organization
* Generate initial implementation ideas

### Where AI Output Was Wrong or Incomplete

The generated code required manual debugging and validation.

Some issues included:

* The initial SQLAlchemy model used a reserved field name, `metadata`, which required correction.
* Some early image heuristics were too simplistic and needed calibration against the actual tests.
* The first version did not properly ensure that SQLite tables existed before the upload endpoint attempted to insert records.

### How I Validated the AI-Generated Code

I did not rely on AI-generated code without testing it.

I validated the implementation by:

* Running the API test suite after each major fix
* Testing the complete upload-to-processing workflow
* Verifying the job lifecycle:
  `upload → queue → processing → results`
* Checking the actual database behavior
* Debugging and correcting issues manually

---

## Trade-offs

### Intentionally Simplified

The following components were intentionally kept lightweight:

| Component        | Current Implementation    | Production Alternative          |
| ---------------- | ------------------------- | ------------------------------- |
| Queue            | In-memory queue           | RabbitMQ / Redis / SQS / BullMQ |
| Image Analysis   | Heuristic checks          | ML / Computer Vision models     |
| Database         | SQLite                    | PostgreSQL                      |
| Plate Validation | Lightweight pattern check | OCR / ANPR                      |
| Storage          | Local disk                | Cloud object storage            |

### If More Time Were Available

The following improvements could be implemented:

* Replace the in-memory queue with RabbitMQ, Redis, or BullMQ
* Add real OCR using Tesseract or cloud vision services
* Add stronger image hashing and duplicate detection
* Implement retry policies
* Add dead-letter queue handling
* Add structured logging
* Add metrics and distributed tracing
* Add API rate limiting
* Add per-user upload quotas

---

## Scalability Considerations

The current implementation is designed primarily for local and demo deployments.

Potential scalability limitations include:

* The queue is single-process and stored in memory.
* The queue cannot be shared between multiple application instances.
* Local disk storage is not suitable for multi-node deployments.
* Duplicate detection is approximate and currently uses a simple registry.

For production deployment, the queue could be moved to a distributed message broker and uploaded files could be stored in object storage such as Amazon S3 or equivalent services.

---

## Failure Handling

Processing failures are represented using the `failed` job status.

The system stores:

* Processing status
* Failure reason
* Processing results

Currently:

* Automatic retries are not implemented.
* Processing errors are logged by the worker.
* Production deployments would require structured logging and monitoring.
* Alerting would be required for persistent processing failures.

---

## Interactive / Bonus Capabilities

The project can be extended with several practical enhancements.

### Dashboard / UI

A web dashboard could allow users to:

* Upload vehicle images
* View processing status
* View analysis results
* Track previous uploads

### Analytics

The system could provide analytics for:

* Blur rate
* Duplicate rate
* Low-light rate
* Suspicious image rate
* Processing success/failure rate

### Confidence Scoring

Each image can be assigned a numeric confidence score representing the likelihood of being a valid or suspicious upload.

### Retry Mechanisms

Automatic retries could be added for temporary processing failures.

### Concurrency

A worker pool could be introduced to process multiple images simultaneously.

### Automated Testing

The test suite can be expanded to include:

* Upload validation
* Job status
* Result retrieval
* Duplicate detection
* Failure handling
* Invalid file types
* Large file handling

---

# Running the Project

## Prerequisites

Make sure you have:

* Python 3.10+
* pip
* Git
* Docker *(optional)*

---

## Option 1: Run Locally with Python

### 1. Clone the Repository

```bash
git clone https://github.com/Satish1483/media-processing-pipeline.git
cd media-processing-pipeline
```

### 2. Create a Virtual Environment

#### Windows

```powershell
python -m venv .venv
```

### 3. Activate the Virtual Environment

```powershell
.venv\Scripts\Activate.ps1
```

### 4. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 5. Start the Application

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Open the Dashboard

Open your browser and visit:

```text
http://localhost:8000/dashboard
```

### 7. Open API Documentation

FastAPI automatically provides interactive API documentation at:

```text
http://localhost:8000/docs
```

---

# Running with Docker

A minimal Docker setup is included in the project.

### Build the Docker Image

```bash
docker build -t media-pipeline .
```

### Run the Container

```bash
docker run -p 8000:8000 media-pipeline
```

Alternatively, use Docker Compose:

```bash
docker compose up --build
```

After starting the application:

**Dashboard**

```text
http://localhost:8000/dashboard
```

**API Documentation**

```text
http://localhost:8000/docs
```

---

# API Documentation

## 1. Upload an Image

### Endpoint

```http
POST /api/v1/uploads
```

### Example

```bash
curl -X POST "http://localhost:8000/api/v1/uploads" \
  -F "file=@/path/to/vehicle.jpg;type=image/jpeg"
```

### Example Response

```json
{
  "processing_id": "b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f",
  "status": "queued",
  "message": "Upload accepted and queued for processing"
}
```

---

## 2. Check Job Status

### Endpoint

```http
GET /api/v1/jobs/{job_id}/status
```

### Example

```bash
curl "http://localhost:8000/api/v1/jobs/b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f/status"
```

### Example Response

```json
{
  "id": "b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f",
  "status": "completed",
  "filename": "vehicle.jpg",
  "failure_reason": null,
  "confidence_score": 0.73
}
```

---

## 3. Fetch Job Results

### Endpoint

```http
GET /api/v1/jobs/{job_id}/results
```

### Example

```bash
curl "http://localhost:8000/api/v1/jobs/b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f/results"
```

### Example Response

```json
{
  "job_id": "b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f",
  "status": "completed",
  "issues": [
    "blur",
    "low_light"
  ],
  "checks": [
    {
      "name": "blur",
      "passed": false,
      "severity": "warning",
      "message": "Image appears blurry"
    }
  ],
  "summary": {
    "dimensions": {
      "width": 1200,
      "height": 800
    },
    "blur_score": 18.4,
    "brightness": 72.3
  }
}
```

---

## 4. Fetch Failure Reason

### Endpoint

```http
GET /api/v1/jobs/{job_id}/failure
```

### Example

```bash
curl "http://localhost:8000/api/v1/jobs/b45e4d7c-0c4f-4f68-8c20-c0f4009dfe3f/failure"
```

---

# Assumptions

The system is designed primarily for local and demo deployments rather than enterprise-scale throughput.

The main assumptions are:

* Uploaded files are vehicle or field images.
* Image analysis focuses on quality and validation heuristics.
* Exact OCR and number-plate recognition are intentionally approximated.
* The assignment emphasizes engineering quality and system design rather than ML model accuracy.
* SQLite and local storage are sufficient for the demonstration environment.

---

# Testing

The project includes an automated test suite covering:

* Upload acceptance
* Asynchronous job completion
* Result retrieval
* Duplicate detection heuristics

Run the tests using:

```bash
pytest -q
```

---

# Future Improvements

Potential future improvements include:

1. Distributed background processing
2. Cloud-based file storage
3. PostgreSQL database
4. Production-grade OCR / ANPR
5. Stronger duplicate detection
6. Retry and dead-letter mechanisms
7. Worker pool and concurrency support
8. Authentication and authorization
9. API rate limiting
10. Monitoring and observability
11. CI/CD integration
12. Production deployment using containers

---

## License

This project was developed as part of a technical case study and is intended for educational and demonstration purposes.
