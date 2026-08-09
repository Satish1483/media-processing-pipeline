from pathlib import Path
import sqlite3
import shutil

root = Path(r"C:\Users\USER\OneDrive\Documents\assignment")
uploads_dir = root / "uploads"

if uploads_dir.exists():
    for item in uploads_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

for db_name in ["media_pipeline.db", "test_media_pipeline.db"]:
    db_path = root / db_name
    if not db_path.exists():
        continue

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    for table_name in ["image_jobs", "processed_images"]:
        try:
            cur.execute(f"DELETE FROM {table_name}")
        except Exception:
            pass

    conn.commit()

    for table_name in ["image_jobs", "processed_images"]:
        try:
            count = cur.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            print(f"{db_name}:{table_name}={count}")
        except Exception:
            print(f"{db_name}:{table_name}=missing")

    conn.close()

print(f"uploads_dir_exists={uploads_dir.exists()}")
print(f"uploads_dir_contents={sorted([x.name for x in uploads_dir.iterdir()]) if uploads_dir.exists() else []}")
print("History cleared.")
