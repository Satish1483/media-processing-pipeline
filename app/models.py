from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text

from app.database import Base


class ImageJob(Base):
    __tablename__ = "image_jobs"

    id = Column(String, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    stored_path = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    status = Column(String, default="queued", nullable=False)
    failure_reason = Column(Text, nullable=True)
    analysis = Column(JSON, default=dict)
    job_metadata = Column(JSON, default=dict)
    issue_count = Column(Integer, default=0)
    confidence_score = Column(Float, default=0.0)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)


class ProcessedImage(Base):
    __tablename__ = "processed_images"

    id = Column(String, primary_key=True, index=True)
    job_id = Column(String, nullable=False, index=True)
    checksum = Column(String, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    blur_score = Column(Float, nullable=False)
    brightness = Column(Float, nullable=False)
    is_duplicate = Column(Boolean, default=False)
    duplicate_with = Column(String, nullable=True)
    extracted_text = Column(Text, nullable=True)
    has_suspicious_edit = Column(Boolean, default=False)
    likely_screenshot = Column(Boolean, default=False)
    likely_photo_of_photo = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    analysis_summary = Column(JSON, default=dict)
