import io
import os
import time

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_media_pipeline.db")
os.environ.setdefault("UPLOAD_DIR", "./test_storage")

from app.main import app

client = TestClient(app)


def create_test_image(width=1200, height=800, brightness=180, text="vehicle"):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, height), (brightness, brightness, brightness))
    draw = ImageDraw.Draw(image)
    for i in range(0, width, 80):
        draw.line((i, 0, i, height), fill=(20, 20, 20), width=2)
    for j in range(0, height, 80):
        draw.line((0, j, width, j), fill=(30, 30, 30), width=2)

    # add some contrast for realistic vehicle-like image
    draw.rectangle((200, 200, 1000, 600), fill=(60, 120, 200))
    draw.rectangle((350, 260, 850, 560), fill=(210, 220, 230))

    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default()

    draw.text((420, 310), text, font=font, fill=(10, 10, 10))

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def wait_for_job_completion(job_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status_response = client.get(f"/api/v1/jobs/{job_id}/status")
        if status_response.status_code == 200:
            payload = status_response.json()
            if payload["status"] in {"completed", "failed"}:
                return payload
        time.sleep(0.5)
    raise AssertionError(f"Job {job_id} did not finish in time")


def test_upload_returns_job_and_processes_image():
    payload = create_test_image(brightness=170, text="DL01AB1234")

    response = client.post(
        "/api/v1/uploads",
        files={"file": ("vehicle_front.jpg", payload, "image/jpeg")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "processing_id" in body
    job_id = body["processing_id"]

    status = wait_for_job_completion(job_id)
    assert status["status"] == "completed"

    result_response = client.get(f"/api/v1/jobs/{job_id}/results")
    assert result_response.status_code == 200, result_response.text
    result = result_response.json()
    assert result["status"] == "completed"
    assert "issues" in result
    assert "checks" in result
    assert isinstance(result["checks"], list)


def test_duplicate_detection_flags_repeated_image():
    payload = create_test_image(width=1200, height=800, brightness=140, text="MH12XY4567")
    response = client.post(
        "/api/v1/uploads",
        files={"file": ("duplicate_vehicle.jpg", payload, "image/jpeg")},
    )
    first_id = response.json()["processing_id"]
    wait_for_job_completion(first_id)

    response = client.post(
        "/api/v1/uploads",
        files={"file": ("duplicate_vehicle_copy.jpg", payload, "image/jpeg")},
    )
    second_id = response.json()["processing_id"]
    wait_for_job_completion(second_id)

    result_response = client.get(f"/api/v1/jobs/{second_id}/results")
    result = result_response.json()
    issue_names = {item["name"] for item in result["checks"]}
    assert "duplicate_image" in issue_names or "duplicate" in result["issues"]


def test_dashboard_page_renders():
    response = client.get("/dashboard")
    assert response.status_code == 200
    page = response.text.lower()
    assert "media processing dashboard" in page
    assert "upload image" in page
