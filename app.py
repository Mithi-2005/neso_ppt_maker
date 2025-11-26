from flask import Flask, render_template, request, send_file, jsonify
from concurrent.futures import ThreadPoolExecutor
import os
import uuid
import shutil
import time
from datetime import datetime

from utils.downloader import download_video
from utils.extractor import extract_slides
from utils.ppt_maker import generate_ppt


app = Flask(__name__)

# Background worker pool (Render-safe)
executor = ThreadPoolExecutor(max_workers=4)

JOBS_ROOT = "jobs"
os.makedirs(JOBS_ROOT, exist_ok=True)


def log_error(e):
    print("ERROR:", e)
    try:
        os.makedirs(JOBS_ROOT, exist_ok=True)
        with open(os.path.join(JOBS_ROOT, "log.txt"), "a", encoding="utf-8") as log:
            log.write(f"{datetime.utcnow().isoformat()} - {repr(e)}\n")
    except Exception as log_exc:
        print("Failed to write log:", log_exc)


def write_status(job_id, status, message=None):
    try:
        job_dir = os.path.join(JOBS_ROOT, job_id)
        os.makedirs(job_dir, exist_ok=True)
        status_path = os.path.join(job_dir, "status.txt")
        with open(status_path, "w", encoding="utf-8") as f:
            f.write(status)
            if message:
                f.write("\n" + message)
    except Exception as e:
        log_error(e)


def get_job_paths(job_id):
    job_dir = os.path.join(JOBS_ROOT, job_id)
    video_path = os.path.join(job_dir, "video.mp4")
    slides_dir = os.path.join(job_dir, "slides")
    ppt_path = os.path.join(job_dir, "output.pptx")
    return job_dir, video_path, slides_dir, ppt_path


def mark_job_completed(job_id):
    """Mark a job as completed (success or error) so it can be cleaned after TTL."""
    try:
        job_dir = os.path.join(JOBS_ROOT, job_id)
        os.makedirs(job_dir, exist_ok=True)
        flag_path = os.path.join(job_dir, "completed.flag")
        # store a timestamp (not strictly required, mtime is enough)
        with open(flag_path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception as e:
        log_error(e)


def run_extraction(url, job_id):
    job_dir, video_path, slides_dir, ppt_path = get_job_paths(job_id)
    try:
        os.makedirs(job_dir, exist_ok=True)
        write_status(job_id, "processing", "Downloading video…")

        # Step 1: Download video
        download_video(url, video_path)

        write_status(job_id, "processing", "Extracting slides…")

        # Step 2: Extract unique slides
        slide_paths = extract_slides(video_path, slides_dir)

        write_status(job_id, "processing", "Generating PPT…")

        # Step 3: Generate PPT
        generate_ppt(slide_paths, ppt_path)

        write_status(job_id, "done", "PPT generated")
        mark_job_completed(job_id)
    except Exception as e:
        log_error(e)
        error_path = os.path.join(job_dir, "error.txt")
        try:
            with open(error_path, "w", encoding="utf-8") as ef:
                ef.write(str(e))
        except Exception as ef_exc:
            log_error(ef_exc)
        write_status(job_id, "error", str(e))
        mark_job_completed(job_id)


def cleanup_jobs(max_age_minutes=30):
    """Delete completed job folders older than max_age_minutes.

    A job is considered completed if it has a completed.flag file. The mtime of this
    flag is used as the completion time, so jobs are removed ~30 minutes after they
    finish (success or error).
    """
    now = time.time()
    cutoff = now - max_age_minutes * 60

    try:
        os.makedirs(JOBS_ROOT, exist_ok=True)
        for name in os.listdir(JOBS_ROOT):
            path = os.path.join(JOBS_ROOT, name)
            if not os.path.isdir(path):
                continue

            flag_path = os.path.join(path, "completed.flag")
            if not os.path.exists(flag_path):
                # skip jobs that are not yet completed
                continue

            try:
                mtime = os.path.getmtime(flag_path)
            except OSError as e:
                log_error(e)
                continue

            if mtime < cutoff:
                try:
                    shutil.rmtree(path)
                except Exception as e:
                    log_error(e)
    except Exception as e:
        log_error(e)


@app.route("/", methods=["GET"])
def index():
    # Simple UI page; client-side JS can POST to /process and poll /status
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    # Accept JSON or form data
    url = request.json.get("yt_url") if request.is_json else request.form.get("yt_url")
    if not url:
        return jsonify({"error": "yt_url is required"}), 400

    job_id = str(uuid.uuid4())
    job_dir, _, _, _ = get_job_paths(job_id)
    os.makedirs(job_dir, exist_ok=True)

    write_status(job_id, "processing", "Queued…")
    executor.submit(run_extraction, url, job_id)

    return jsonify({"job_id": job_id, "status": "processing"})


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    # opportunistic cleanup of old completed jobs
    cleanup_jobs()

    job_dir, video_path, slides_dir, ppt_path = get_job_paths(job_id)
    if not os.path.exists(job_dir):
        return jsonify({"status": "not_found"}), 404

    error_path = os.path.join(job_dir, "error.txt")
    status_path = os.path.join(job_dir, "status.txt")

    if os.path.exists(error_path):
        try:
            with open(error_path, "r", encoding="utf-8") as f:
                msg = f.read().strip()
        except Exception:
            msg = "error"
        return jsonify({"status": "error", "message": msg})

    if os.path.exists(ppt_path):
        return jsonify({"status": "done"})

    # Fallback: if we see partial artifacts, still report processing
    if os.path.exists(video_path) or os.path.isdir(slides_dir):
        return jsonify({"status": "processing"})

    # Try to read last written status.txt
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            status_value = lines[0] if lines else "processing"
            message = lines[1] if len(lines) > 1 else None
        except Exception:
            status_value = "processing"
            message = None
        return jsonify({"status": status_value, "message": message})

    return jsonify({"status": "processing"})


@app.route("/download/<job_id>", methods=["GET"])
def download(job_id):
    # opportunistic cleanup of old completed jobs
    cleanup_jobs()
    _, _, slides_dir, ppt_path = get_job_paths(job_id)

    if not os.path.exists(ppt_path):
        return jsonify({"error": "PPT not ready"}), 404

    # Optionally provide ?type=slides to download slides as ZIP
    download_type = request.args.get("type", "pptx")

    if download_type == "slides":
        import tempfile
        import zipfile

        if not os.path.isdir(slides_dir):
            return jsonify({"error": "Slides not available"}), 404

        tmp_fd, tmp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(tmp_fd)

        try:
            with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for name in sorted(os.listdir(slides_dir)):
                    full = os.path.join(slides_dir, name)
                    if os.path.isfile(full):
                        zf.write(full, arcname=name)
            return send_file(tmp_zip_path, as_attachment=True, download_name=f"{job_id}_slides.zip")
        except Exception as e:
            log_error(e)
            return jsonify({"error": "Failed to create slides ZIP"}), 500
        finally:
            try:
                os.remove(tmp_zip_path)
            except OSError:
                pass

    # Default: return PPTX
    return send_file(ppt_path, as_attachment=True, download_name=f"{job_id}.pptx")


# Run cleanup once at startup
cleanup_jobs()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
