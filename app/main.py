from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from app.analysis import run_image_checks
from app.database import Base, engine, get_db, initialize_database
from app.models import ImageJob, ProcessedImage
from app.queue import queue
from app.registry import IMAGE_REGISTRY

initialize_database()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Intelligent Media Processing Pipeline")


@app.on_event("startup")
def startup():
    initialize_database()
    IMAGE_REGISTRY.clear()


def _job_response(job: ImageJob) -> Dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "filename": job.original_filename,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "failure_reason": job.failure_reason,
        "confidence_score": job.confidence_score,
    }


def _enqueue_job(job_id: str, file_path: str, file_bytes: bytes):
    def process_image() -> None:
        from sqlalchemy.orm import Session

        with get_db() as db:
            job = db.query(ImageJob).filter(ImageJob.id == job_id).first()
            if not job:
                return
            job.status = "processing"
            job.processing_started_at = datetime.utcnow()
            db.add(job)
            db.commit()

            try:
                result = run_image_checks(file_bytes)
                record = ProcessedImage(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    checksum=job.id,
                    width=result["summary"]["dimensions"]["width"],
                    height=result["summary"]["dimensions"]["height"],
                    blur_score=result["summary"]["blur_score"],
                    brightness=result["summary"]["brightness"],
                    is_duplicate=bool([check for check in result["checks"] if check["name"] == "duplicate_image" and not check["passed"]]),
                    extracted_text=result.get("extracted_text"),
                    has_suspicious_edit=bool([check for check in result["checks"] if check["name"] == "tampered" and not check["passed"]]),
                    likely_screenshot=bool([check for check in result["checks"] if check["name"] == "screenshot" and not check["passed"]]),
                    likely_photo_of_photo=bool([check for check in result["checks"] if check["name"] == "photo_of_photo" and not check["passed"]]),
                    analysis_summary={"checks": result["checks"], "issues": result["issues"]},
                )
                db.add(record)
                job.analysis = {
                    "checks": result["checks"],
                    "issues": result["issues"],
                    "summary": result["summary"],
                    "confidence_score": result["confidence_score"],
                    "extracted_text": result.get("extracted_text"),
                }
                job.issue_count = len(result["issues"])
                job.confidence_score = result["confidence_score"]
                job.status = "completed"
                job.processing_completed_at = datetime.utcnow()
                job.updated_at = datetime.utcnow()
                db.add(job)
                db.commit()
                IMAGE_REGISTRY[job.id] = file_bytes
            except Exception as exc:
                job.status = "failed"
                job.failure_reason = str(exc)
                job.processing_completed_at = datetime.utcnow()
                job.updated_at = datetime.utcnow()
                db.add(job)
                db.commit()
                raise

    queue.enqueue(process_image)


@app.post("/api/v1/uploads")
async def upload_image(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    file_bytes = await file.read()
    job_id = str(uuid.uuid4())
    storage_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    storage_path.write_bytes(file_bytes)

    with get_db() as db:
        job = ImageJob(
            id=job_id,
            original_filename=file.filename,
            stored_path=str(storage_path),
            content_type=file.content_type,
            file_size=len(file_bytes),
            status="queued",
            job_metadata={"mime_type": file.content_type, "saved_path": str(storage_path)},
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    _enqueue_job(job_id, str(storage_path), file_bytes)
    return {"processing_id": job_id, "status": "queued", "message": "Upload accepted and queued for processing"}


@app.get("/api/v1/jobs")
def list_jobs():
    with get_db() as db:
        jobs = db.query(ImageJob).order_by(ImageJob.created_at.desc()).limit(25).all()
        return [{
            **_job_response(job),
            "status": job.status,
            "analysis": job.analysis or {},
        } for job in jobs]


@app.get("/api/v1/jobs/{job_id}/status")
def get_job_status(job_id: str):
    with get_db() as db:
        job = db.query(ImageJob).filter(ImageJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        payload = _job_response(job)
        payload["status"] = job.status
        return payload


@app.get("/api/v1/jobs/{job_id}/results")
def get_job_results(job_id: str):
    with get_db() as db:
        job = db.query(ImageJob).filter(ImageJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status != "completed":
            return {"job_id": job_id, "status": job.status, "issues": [], "checks": [], "summary": {}, "message": "Job has not completed yet"}
        analysis = job.analysis or {}
        return {
            "job_id": job_id,
            "status": job.status,
            "issues": analysis.get("issues", []),
            "checks": analysis.get("checks", []),
            "summary": analysis.get("summary", {}),
            "confidence_score": analysis.get("confidence_score", 0.0),
            "extracted_text": analysis.get("extracted_text"),
        }


@app.get("/api/v1/jobs/{job_id}/failure")
def get_job_failure(job_id: str):
    with get_db() as db:
        job = db.query(ImageJob).filter(ImageJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"job_id": job_id, "status": job.status, "failure_reason": job.failure_reason}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Vehicle Vision Dashboard</title>
        <style>
            :root {
                --bg: #07111f;
                --panel: #101c2f;
                --panel-2: #15263f;
                --muted: #9fb2c8;
                --text: #edf4ff;
                --primary: #5eead4;
                --primary-2: #38bdf8;
                --accent: #a78bfa;
                --success: #22c55e;
                --warning: #f59e0b;
                --danger: #ef4444;
                --border: rgba(159, 178, 200, 0.18);
            }

            * { box-sizing: border-box; }

            html, body {
                margin: 0;
                min-height: 100%;
                font-family: Inter, Arial, sans-serif;
                background: radial-gradient(circle at top, #10213d 0%, var(--bg) 45%);
                color: var(--text);
            }

            body {
                min-height: 100vh;
                padding: 24px;
            }

            .container {
                max-width: 1400px;
                margin: 0 auto;
            }

            .topbar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 16px;
                margin-bottom: 20px;
                padding-bottom: 18px;
                border-bottom: 1px solid var(--border);
            }

            .brand {
                display: flex;
                align-items: center;
                gap: 14px;
            }

            .brand-mark {
                width: 42px;
                height: 42px;
                border-radius: 12px;
                display: grid;
                place-items: center;
                background: linear-gradient(135deg, var(--primary), var(--primary-2));
                color: #06263f;
                font-weight: 800;
                box-shadow: 0 12px 22px rgba(56, 189, 248, 0.35);
            }

            h1 {
                margin: 0;
                font-size: clamp(1.8rem, 3vw, 2.8rem);
            }

            .subtitle {
                margin-top: 6px;
                color: var(--muted);
                font-size: 0.96rem;
            }

            .header-status {
                display: inline-flex;
                align-items: center;
                gap: 10px;
                padding: 9px 14px;
                border: 1px solid var(--border);
                border-radius: 999px;
                background: rgba(16, 28, 47, 0.7);
                color: var(--muted);
                font-size: 0.8rem;
            }

            .status-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: var(--success);
                box-shadow: 0 0 16px rgba(34, 197, 94, 0.8);
            }

            .stats-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(180px, 1fr));
                gap: 18px;
                margin-bottom: 22px;
            }

            .stat-card,
            .card {
                background: rgba(16, 28, 47, 0.88);
                border: 1px solid var(--border);
                border-radius: 18px;
                box-shadow: 0 18px 42px rgba(0, 0, 0, 0.2);
            }

            .stat-card {
                padding: 18px 20px;
            }

            .stat-label {
                display: flex;
                justify-content: space-between;
                color: var(--muted);
                font-size: 0.82rem;
                margin-bottom: 10px;
            }

            .stat-value {
                font-size: clamp(1.8rem, 2vw, 2.4rem);
                font-weight: 800;
                letter-spacing: -0.04em;
            }

            .stat-foot {
                margin-top: 8px;
                color: var(--muted);
                font-size: 0.75rem;
            }

            .dashboard-grid {
                display: grid;
                grid-template-columns: 1.1fr 1.6fr;
                gap: 22px;
            }

            .card {
                padding: 20px;
            }

            .card-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 18px;
            }

            .card h2 {
                margin: 0;
                font-size: 1.15rem;
            }

            form {
                display: flex;
                flex-direction: column;
                gap: 14px;
            }

            .drop-zone {
                border: 1.2px dashed rgba(94, 234, 212, 0.5);
                background: rgba(94, 234, 212, 0.04);
                border-radius: 16px;
                padding: 18px;
                text-align: center;
                color: var(--muted);
            }

            input[type="file"] {
                width: 100%;
                padding: 12px;
                background: rgba(21, 38, 63, 0.8);
                border: 1px solid var(--border);
                border-radius: 12px;
                color: var(--text);
            }

            button {
                border: 0;
                border-radius: 12px;
                padding: 12px 18px;
                font-weight: 700;
                cursor: pointer;
                color: #07111f;
                background: linear-gradient(135deg, var(--primary), var(--primary-2));
                transition: transform 0.2s ease, box-shadow 0.2s ease;
                box-shadow: 0 12px 20px rgba(94, 234, 212, 0.2);
            }

            button:hover { transform: translateY(-1px); }
            button:disabled { opacity: 0.6; cursor: not-allowed; }

            .message {
                min-height: 24px;
                color: #ffd7d7;
                font-size: 0.9rem;
                margin-top: 8px;
            }

            .jobs-list {
                display: flex;
                flex-direction: column;
                gap: 12px;
                margin-top: 8px;
            }

            .job-item {
                border: 1px solid var(--border);
                border-radius: 14px;
                padding: 14px;
                background: rgba(21, 38, 63, 0.7);
                cursor: pointer;
                transition: border-color 0.2s ease, transform 0.2s ease;
            }

            .job-item:hover {
                border-color: rgba(94, 234, 212, 0.45);
                transform: translateY(-1px);
            }

            .job-item.active {
                border-color: rgba(94, 234, 212, 0.85);
                box-shadow: inset 0 0 0 1px rgba(94, 234, 212, 0.35);
            }

            .job-row {
                display: flex;
                justify-content: space-between;
                gap: 12px;
                align-items: center;
                margin-bottom: 8px;
            }

            .job-name {
                font-weight: 700;
                word-break: break-word;
            }

            .status-badge {
                display: inline-block;
                padding: 6px 10px;
                border-radius: 999px;
                font-size: 0.68rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                white-space: nowrap;
            }

            .queued { background: rgba(59, 130, 246, 0.14); color: #93c5fd; }
            .processing { background: rgba(245, 158, 11, 0.14); color: #fbbf24; }
            .completed { background: rgba(34, 197, 94, 0.14); color: #86efac; }
            .failed { background: rgba(239, 68, 68, 0.16); color: #fca5a5; }

            .job-meta {
                color: var(--muted);
                font-size: 0.78rem;
                line-height: 1.6;
            }

            .chip-row {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 10px;
            }

            .chip {
                background: rgba(167, 139, 250, 0.12);
                color: #d9d1ff;
                border: 1px solid rgba(167, 139, 250, 0.22);
                padding: 5px 9px;
                border-radius: 999px;
                font-size: 0.7rem;
            }

            .empty {
                color: var(--muted);
                padding: 16px 0;
            }

            .detail-wrap {
                display: none;
            }

            .detail-wrap.visible {
                display: block;
            }

            .detail-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(160px, 1fr));
                gap: 14px;
                margin-top: 18px;
            }

            .detail-box {
                background: rgba(21, 38, 63, 0.74);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 14px;
            }

            .detail-label {
                display: block;
                color: var(--muted);
                font-size: 0.72rem;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }

            .detail-value {
                font-size: 1rem;
                font-weight: 700;
                word-break: break-word;
            }

            .issue-list {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 12px;
            }

            .issue-badge {
                padding: 6px 10px;
                border-radius: 999px;
                font-size: 0.72rem;
                color: #fff;
                background: rgba(239, 68, 68, 0.15);
                border: 1px solid rgba(239, 68, 68, 0.35);
            }

            .check-list {
                display: flex;
                flex-direction: column;
                gap: 10px;
                margin-top: 16px;
            }

            .check-item {
                background: rgba(21, 38, 63, 0.7);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 12px 14px;
            }

            .check-head {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 10px;
                margin-bottom: 6px;
            }

            .check-name {
                font-weight: 700;
            }

            .check-pass {
                font-size: 0.68rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                padding: 4px 8px;
                border-radius: 999px;
                background: rgba(34, 197, 94, 0.12);
                color: #86efac;
            }

            .check-fail {
                background: rgba(239, 68, 68, 0.12);
                color: #fca5a5;
            }

            .check-message {
                color: var(--muted);
                font-size: 0.82rem;
                line-height: 1.55;
            }

            @media (max-width: 980px) {
                .stats-grid {
                    grid-template-columns: repeat(2, minmax(180px, 1fr));
                }

                .dashboard-grid {
                    grid-template-columns: 1fr;
                }
            }

            @media (max-width: 620px) {
                body { padding: 16px; }
                .stats-grid { grid-template-columns: 1fr; }
                .topbar { flex-direction: column; align-items: flex-start; }
                .detail-grid { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="topbar">
                <div class="brand">
                    <div class="brand-mark">V</div>
                    <div>
                        <h1>Media Processing Dashboard</h1>
                        <div class="subtitle">AI-assisted vehicle image analysis and upload monitoring</div>
                    </div>
                </div>
                <div class="header-status">
                    <span class="status-dot"></span>
                    system online
                </div>
            </div>

            <div class="stats-grid" id="statsGrid">
                <div class="stat-card">
                    <div class="stat-label"><span>Total jobs</span><span>📦</span></div>
                    <div class="stat-value" id="totalJobs">0</div>
                    <div class="stat-foot">all uploaded images</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label"><span>Completed</span><span>✅</span></div>
                    <div class="stat-value" id="completedJobs">0</div>
                    <div class="stat-foot">fully analyzed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label"><span>Processing</span><span>⏳</span></div>
                    <div class="stat-value" id="processingJobs">0</div>
                    <div class="stat-foot">active queue items</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label"><span>Failures</span><span>⚠️</span></div>
                    <div class="stat-value" id="failedJobs">0</div>
                    <div class="stat-foot">job-level errors</div>
                </div>
            </div>

            <div class="dashboard-grid">
                <div class="card">
                    <div class="card-header">
                        <h2>Upload image</h2>
                    </div>

                    <form id="uploadForm">
                        <div class="drop-zone">
                            <div>Drag and drop or choose a JPG, PNG, or WEBP image.</div>
                        </div>
                        <input id="fileInput" type="file" accept="image/jpeg,image/png,image/webp" required />
                        <button id="uploadBtn" type="submit">Upload for analysis</button>
                    </form>
                    <div class="message" id="message"></div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <h2>Recent jobs</h2>
                    </div>
                    <div id="jobsList" class="jobs-list">
                        <div class="empty">Loading jobs…</div>
                    </div>
                </div>
            </div>

            <div class="card" id="detailsCard" style="margin-top: 22px;">
                <div class="card-header">
                    <h2>Selected job details</h2>
                </div>
                <div id="jobDetail" class="detail-wrap">
                    <div class="detail-grid">
                        <div class="detail-box">
                            <span class="detail-label">File name</span>
                            <div id="detailName" class="detail-value">—</div>
                        </div>
                        <div class="detail-box">
                            <span class="detail-label">Status</span>
                            <div id="detailStatus" class="detail-value">—</div>
                        </div>
                        <div class="detail-box">
                            <span class="detail-label">Job ID</span>
                            <div id="detailId" class="detail-value">—</div>
                        </div>
                        <div class="detail-box">
                            <span class="detail-label">Confidence</span>
                            <div id="detailConfidence" class="detail-value">—</div>
                        </div>
                    </div>

                    <div style="margin-top: 18px;">
                        <div class="detail-label">Detected issues</div>
                        <div id="issueList" class="issue-list"></div>
                    </div>

                    <div style="margin-top: 20px;">
                        <div class="detail-label">Check results</div>
                        <div id="checkList" class="check-list"></div>
                    </div>
                </div>
                <div id="emptyDetail" class="empty">No job selected yet.</div>
            </div>
        </div>

        <script>
            const jobsList = document.getElementById('jobsList');
            const uploadForm = document.getElementById('uploadForm');
            const fileInput = document.getElementById('fileInput');
            const messageBox = document.getElementById('message');
            const uploadBtn = document.getElementById('uploadBtn');
            const detailPanel = document.getElementById('jobDetail');
            const emptyDetail = document.getElementById('emptyDetail');
            const issueList = document.getElementById('issueList');
            const checkList = document.getElementById('checkList');
            const detailName = document.getElementById('detailName');
            const detailStatus = document.getElementById('detailStatus');
            const detailId = document.getElementById('detailId');
            const detailConfidence = document.getElementById('detailConfidence');
            let selectedJobId = null;
            let allJobs = [];

            function statusClass(status) {
                return (status || 'queued').toLowerCase();
            }

            function formatTimestamp(value) {
                if (!value) return 'n/a';
                const date = new Date(value);
                if (Number.isNaN(date.getTime())) return value;
                return date.toLocaleString();
            }

            function renderStats(jobs) {
                const total = jobs.length;
                const completed = jobs.filter(job => job.status === 'completed').length;
                const processing = jobs.filter(job => job.status === 'processing').length;
                const failed = jobs.filter(job => job.status === 'failed').length;

                document.getElementById('totalJobs').textContent = String(total);
                document.getElementById('completedJobs').textContent = String(completed);
                document.getElementById('processingJobs').textContent = String(processing);
                document.getElementById('failedJobs').textContent = String(failed);
            }

            function renderJobList(jobs) {
                if (!jobs || jobs.length === 0) {
                    jobsList.innerHTML = '<div class="empty">No uploads yet. Start by adding a new image.</div>';
                    return;
                }

                jobsList.innerHTML = jobs.map(job => {
                    const analysis = job.analysis || {};
                    const issues = Array.isArray(analysis.issues) ? analysis.issues : [];
                    const confidence = typeof job.confidence_score === 'number' ? job.confidence_score.toFixed(2) : '0.00';
                    return `
                        <div class="job-item ${job.id === selectedJobId ? 'active' : ''}" data-job-id="${job.id}">
                            <div class="job-row">
                                <div class="job-name">${job.filename || 'unknown upload'}</div>
                                <span class="status-badge ${statusClass(job.status)}">${job.status}</span>
                            </div>
                            <div class="job-meta">
                                ID: ${job.id}<br/>
                                Updated: ${formatTimestamp(job.updated_at || job.created_at)}<br/>
                                Confidence: ${confidence}
                            </div>
                            <div class="chip-row">
                                ${issues.length ? issues.slice(0, 3).map(issue => `<span class="chip">${issue}</span>`).join('') : '<span class="chip">No issues</span>'}
                            </div>
                        </div>
                    `;
                }).join('');

                document.querySelectorAll('.job-item').forEach(item => {
                    item.addEventListener('click', () => {
                        selectedJobId = item.dataset.jobId;
                        renderJobList(allJobs);
                        renderJobDetail(allJobs.find(job => job.id === selectedJobId));
                    });
                });
            }

            function renderJobDetail(job) {
                if (!job) {
                    detailPanel.classList.remove('visible');
                    emptyDetail.style.display = 'block';
                    return;
                }

                emptyDetail.style.display = 'none';
                detailPanel.classList.add('visible');

                const analysis = job.analysis || {};
                const checks = Array.isArray(analysis.checks) ? analysis.checks : [];
                const issues = Array.isArray(analysis.issues) ? analysis.issues : [];
                const confidence = typeof job.confidence_score === 'number' ? `${job.confidence_score.toFixed(2)}` : '0.00';

                detailName.textContent = job.filename || 'unknown';
                detailStatus.textContent = job.status || 'queued';
                detailStatus.className = `detail-value status-badge ${statusClass(job.status)}`;
                detailId.textContent = job.id || 'n/a';
                detailConfidence.textContent = `${confidence} / 1.00`;

                issueList.innerHTML = issues.length
                    ? issues.map(issue => `<span class="issue-badge">${issue}</span>`).join('')
                    : '<span class="chip">No issues detected</span>';

                checkList.innerHTML = checks.length
                    ? checks.map(check => {
                        const passed = Boolean(check.passed);
                        return `
                            <div class="check-item">
                                <div class="check-head">
                                    <span class="check-name">${check.name}</span>
                                    <span class="check-pass ${passed ? '' : 'check-fail'}">${passed ? 'passed' : 'flagged'}</span>
                                </div>
                                <div class="check-message">${check.message || 'No detailed message.'}</div>
                            </div>
                        `;
                    }).join('')
                    : '<div class="check-item"><div class="check-message">This job has not produced analysis checks yet.</div></div>';
            }

            async function loadJobs() {
                try {
                    const response = await fetch('/api/v1/jobs');
                    if (!response.ok) {
                        throw new Error('Unable to load jobs');
                    }
                    const jobs = await response.json();
                    allJobs = jobs;
                    renderStats(jobs);
                    renderJobList(jobs);

                    if (!selectedJobId && jobs.length > 0) {
                        selectedJobId = jobs[0].id;
                    }

                    const selected = jobs.find(job => job.id === selectedJobId);
                    renderJobDetail(selected || jobs[0] || null);
                } catch (error) {
                    jobsList.innerHTML = '<div class="empty">Unable to load jobs right now.</div>';
                }
            }

            uploadForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                const file = fileInput.files[0];
                if (!file) {
                    messageBox.textContent = 'Please choose an image file first.';
                    return;
                }

                uploadBtn.disabled = true;
                messageBox.textContent = 'Uploading and queueing image…';

                const formData = new FormData();
                formData.append('file', file);

                try {
                    const response = await fetch('/api/v1/uploads', {
                        method: 'POST',
                        body: formData,
                    });
                    const body = await response.json();
                    if (!response.ok) {
                        throw new Error(body.detail || 'Upload failed');
                    }

                    messageBox.textContent = `Upload accepted. Job ${body.processing_id} is now processing.`;
                    fileInput.value = '';
                    selectedJobId = body.processing_id;
                    await loadJobs();
                    setTimeout(loadJobs, 1500);
                } catch (error) {
                    messageBox.textContent = error.message || 'Upload failed';
                } finally {
                    uploadBtn.disabled = false;
                }
            });

            loadJobs();
            setInterval(loadJobs, 3000);
        </script>
    </body>
    </html>
    """


@app.get("/health")
def health_check():
    return {"status": "ok"}
