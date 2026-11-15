"""Live lookup: build any sky position on request and serve it in the data/ layout.

Run locally from the repo root:
    python -m uvicorn server.app:app --port 8000

Endpoints
    GET /api/lookup?q=<name or coordinates>&size=51   start (or find) a build; returns its status
    GET /api/status/<key>                             status of one field
    GET /data/<key>/...                               the field's files, same layout as data/<key>/

Each field is built twice: a quick preview from a limited number of frames spread over every
visit and detector, then the full build. The site can show the preview while the full build runs;
the files switch over only when the full build is complete. Builds run one at a time, each in its
own process, so a build that runs out of memory can't take the server down with it.
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from spx.field import parse_coordinates  # noqa: E402

WORK = Path(os.environ.get("SPX_WORK_DIR", REPO / "server_work")).resolve()
DATA = WORK / "data"
STAGING = WORK / "staging"
SIZES = tuple(int(s) for s in os.environ.get("SPX_SIZES", "51").split(","))
PREVIEW_FRAMES = int(os.environ.get("SPX_PREVIEW_FRAMES", "120"))
FULL_FRAMES = int(os.environ.get("SPX_FULL_FRAMES", "0")) or None  # 0 = every frame
CACHE_CAP_BYTES = float(os.environ.get("SPX_CACHE_CAP_GB", "5")) * 1e9
MAX_QUEUE = int(os.environ.get("SPX_MAX_QUEUE", "20"))
BUILD_TIMEOUT_S = int(os.environ.get("SPX_BUILD_TIMEOUT_MIN", "60")) * 60
# A build nobody has asked about for this long pauses (downloads kept) and resumes on the next request. 0 = off
ABANDON_S = float(os.environ.get("SPX_ABANDON_MIN", "0")) * 60
LEAVE_GRACE_S = 15  # after /api/leave, how long another viewer has to show they are still watching

for folder in (DATA, STAGING):
    folder.mkdir(parents=True, exist_ok=True)


@dataclass
class Job:
    key: str
    query: str
    args: list  # how build_target.py is told where the field is
    size: int
    state: str = "queued"  # queued, running, preview, done, failed, paused
    stage: str = "waiting"
    done: int = 0
    total: int = 0
    phase: str = "preview"  # which build is running or next: preview, then full
    error: str | None = None
    frames_found: int | None = None
    updated: float = dataclass_field(default_factory=time.time)
    last_seen: float = dataclass_field(default_factory=time.time)  # last lookup or status request
    left_at: float | None = None  # when a viewer called /api/leave
    paused: bool = False
    pause_requested: bool = False
    process: subprocess.Popen | None = None  # the running build


jobs: dict[str, Job] = {}
queue: list[tuple[int, float, str]] = []  # (priority, time queued, key); previews before full builds
lock = threading.Condition()


def field_key(query):
    """A folder name for the request, and the build_target.py arguments that locate it."""
    try:
        center = parse_coordinates(query)
    except ValueError:
        if re.fullmatch(r"\s*[+-]?[\d.]+[\s,]+[+-]?[\d.]+\s*", query):
            raise  # numbers out of range: say so, don't look them up as a name
        center = None
    if center is not None:
        # Rounded to 0.36": the same typed position always reuses the same build
        ra, dec = round(center.ra.deg, 4), round(center.dec.deg, 4)
        key = "c_" + f"{ra:.4f}_{dec:+.4f}".replace(".", "p").replace("+", "").replace("-", "m")
        return key, ["--coords", f"{ra:.4f} {dec:+.4f}", "--label", query.strip()]
    if not re.fullmatch(r"[\w .+\-'*()]{2,60}", query.strip()):
        raise ValueError("Type an object name or coordinates, e.g. 'Barnard's Star' or '269.45 4.77'")
    slug = re.sub(r"[^a-z0-9]+", "_", query.strip().lower()).strip("_")
    return "n_" + slug, ["--name", query.strip()]


def status(job):
    with lock:
        position = next((i + 1 for i, (_, _, k) in enumerate(sorted(queue)) if k == job.key), None)
    files_ready = (DATA / job.key / "fields.json").exists()
    return {"key": job.key, "query": job.query, "state": job.state, "stage": job.stage,
            "progress": {"done": job.done, "total": job.total}, "build": job.phase,
            "queue_position": position, "frames_found": job.frames_found, "error": job.error,
            "files_ready": files_ready, "files": f"/data/{job.key}" if files_ready else None}


def enqueue(job, phase):
    job.phase = phase
    with lock:
        queue.append((0 if phase == "preview" else 1, time.time(), job.key))
        lock.notify()


def touch(job):
    """Someone asked about this field: keep it alive, and resume it if it was paused."""
    with lock:  # the pause thread checks and pauses under the same lock
        job.last_seen, job.left_at = time.time(), None
        if job.paused:
            resume(job)


def resume(job):
    job.paused, job.stage = False, "waiting"
    if job.state == "paused":
        job.state = "queued"
    enqueue(job, job.phase)


def mark_paused(job):
    """A preview already built stays served; only the pending build waits."""
    job.paused, job.stage = True, "paused"
    if job.state != "preview":
        job.state = "paused"


def abandoned(job, now):
    if job.left_at is not None and now - job.left_at >= LEAVE_GRACE_S:
        return True
    return now - job.last_seen >= ABANDON_S


def pause_abandoned():
    """Every few seconds, pause the queued and running builds nobody is waiting for.

    Downloads are cached as they arrive, so a resumed build only redoes the processing.
    """
    while True:
        time.sleep(5)
        now = time.time()
        with lock:
            for entry in list(queue):
                job = jobs[entry[2]]
                if abandoned(job, now):
                    queue.remove(entry)
                    mark_paused(job)
            running = next((job for job in jobs.values() if job.process is not None), None)
        if running is not None and not running.pause_requested and abandoned(running, now):
            running.pause_requested = True
            running.process.kill()


def worker():
    while True:
        with lock:
            while not queue:
                lock.wait()
            queue.sort()
            _, _, key = queue.pop(0)
        job = jobs[key]
        try:
            run_build(job)
        except Exception as error:  # the worker must keep running whatever one build does
            job.state, job.error = "failed", f"server error: {error}"
        job.updated = time.time()
        evict_old_fields(keep=key)


def run_build(job):
    budget = PREVIEW_FRAMES if job.phase == "preview" else FULL_FRAMES
    stage_root = STAGING / f"{job.key}_{job.phase}"
    shutil.rmtree(stage_root, ignore_errors=True)
    command = [sys.executable, "-u", str(REPO / "scripts" / "build_target.py"), job.key, *job.args,
               "--sizes", *map(str, SIZES)]
    if budget:
        command += ["--budget", str(budget)]
    environment = {**os.environ, "SPX_DATA_DIR": str(stage_root / "data"),
                   "SPX_RESULTS_DIR": str(stage_root / "results"), "PYTHONWARNINGS": "ignore"}
    job.state = "running" if job.state != "preview" else "preview"
    job.stage, job.done, job.total, job.error = "finding images", 0, 0, None
    process = subprocess.Popen(command, cwd=WORK, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, bufsize=1)
    job.process = process
    timed_out = threading.Event()
    timer = threading.Timer(BUILD_TIMEOUT_S, lambda: (timed_out.set(), process.kill()))
    timer.start()
    tail = []
    log_path = WORK / "logs" / f"{job.key}_{job.phase}.log"
    log_path.parent.mkdir(exist_ok=True)
    log = log_path.open("w", encoding="utf-8", buffering=1)
    for line in process.stdout:
        log.write(line)
        line = line.rstrip()
        if line and "WARNING" not in line:
            tail = (tail + [line])[-15:]
        read_progress(job, line, budget)
    process.wait()
    job.process = None
    timer.cancel()
    log.close()

    built = stage_root / "data" / job.key
    paused, job.pause_requested = job.pause_requested, False
    if process.returncode == 0 and (built / "fields.json").exists():
        swap_in(built, DATA / job.key)
        shutil.rmtree(stage_root, ignore_errors=True)
        complete = job.phase == "full" or (job.frames_found is not None and job.frames_found <= (budget or 0))
        job.state, job.stage = ("done", "done") if complete else ("preview", "preview ready")
        job.done = job.total
        if not complete:
            enqueue(job, "full")
        return
    shutil.rmtree(stage_root, ignore_errors=True)
    if paused:
        with lock:
            mark_paused(job)
            if not abandoned(job, time.time()):  # someone asked again while the build was stopping
                resume(job)
        return
    if job.frames_found == 0:
        message = "SPHEREx has no images of this position yet."
    elif any("Unable to find coordinates" in line or "NameResolveError" in line for line in tail):
        message = "That name wasn't found. Try coordinates instead, e.g. '269.45 4.77'."
    elif timed_out.is_set():
        message = f"The build took longer than {BUILD_TIMEOUT_S // 60} minutes and was stopped."
    elif process.returncode < 0:
        message = "The build was stopped (most likely out of memory)."
    else:
        message = next((line for line in reversed(tail) if "Error" in line or "error" in line), "build failed")
    if (DATA / job.key / "fields.json").exists():
        # The preview is still there and usable; only the full build failed
        job.state, job.stage, job.error = "preview", "full build failed", message
    else:
        job.state, job.stage, job.error = "failed", "failed", message


def read_progress(job, line, budget):
    """Turn build_target.py's printed lines into a progress status."""
    if match := re.match(r"(\d+) frames \(", line):
        job.frames_found = int(match.group(1))
        job.stage, job.done = "downloading images", 0
        job.total = min(job.frames_found, budget) if budget else job.frames_found
    elif match := re.match(r"\s+downloaded (\d+)", line):
        job.done = int(match.group(1))
    elif match := re.match(r"(\d+) cutouts, (\d+) failed", line):
        job.stage, job.done, job.total = "measuring", 0, int(match.group(1))
    elif match := re.match(r"\s+measured (\d+)", line):
        job.done = int(match.group(1))
    elif line.startswith("Single frames can't constrain"):
        job.stage = "fitting the PSF per visit"
    job.updated = time.time()


def swap_in(new, target):
    """Replace target with new in two renames, so readers never see a half-written folder."""
    old = target.with_name(target.name + "_old")
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    shutil.move(str(new), str(target))
    shutil.rmtree(old, ignore_errors=True)


def folder_bytes(path):
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def evict_old_fields(keep):
    """Delete the least recently built fields until the cache is under its cap.

    Downloads (cache/fields) and web files (data) are capped together. Wavelength tables, PSFs
    and name resolutions are small and reused, so they stay.
    """
    with lock:
        busy = {k for _, _, k in queue} | {keep}
    entries = [p for p in (WORK / "cache" / "fields").glob("*") if p.is_dir()]
    entries += [p for p in DATA.glob("*") if p.is_dir() and p.name not in busy]
    sizes = {p: folder_bytes(p) for p in entries}
    total = sum(sizes.values())
    recent = time.time() - 30 * 60
    for path in sorted(entries, key=lambda p: p.stat().st_mtime):
        if total <= CACHE_CAP_BYTES:
            break
        if path.stat().st_mtime > recent:
            continue  # may belong to a build that is still being used
        shutil.rmtree(path, ignore_errors=True)
        total -= sizes[path]
        if path.parent == DATA and path.name in jobs:
            jobs.pop(path.name)


def restore_jobs():
    """After a restart, fields already on disk are served as finished."""
    for folder in DATA.glob("*"):
        if (folder / "fields.json").exists():
            jobs[folder.name] = Job(folder.name, folder.name, [], SIZES[0], state="done", stage="done", phase="full")


app = FastAPI(title="SPHEREx live lookup")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.get("/api/health")
def health():
    with lock:
        waiting = len(queue)
    running = [k for k, j in jobs.items() if j.stage not in ("waiting", "done", "failed", "preview ready",
                                                             "full build failed", "paused")]
    return {"ok": True, "queued": waiting, "running": running, "sizes_px": list(SIZES)}


@app.get("/api/lookup")
def lookup(q: str = Query(..., max_length=100), size: int = Query(SIZES[0])):
    if size not in SIZES:
        raise HTTPException(400, f"Field size must be one of {list(SIZES)} px")
    try:
        key, args = field_key(q)
    except ValueError as error:
        raise HTTPException(400, str(error))
    job = jobs.get(key)
    files_gone = job is not None and job.state in ("done", "preview") and not (DATA / key / "fields.json").exists()
    if job is None or job.state == "failed" or files_gone:
        with lock:
            if len(queue) >= MAX_QUEUE:
                raise HTTPException(503, "The server is busy. Try again in a few minutes.")
        job = Job(key, q.strip(), args, size)
        jobs[key] = job
        enqueue(job, "preview")
    else:
        touch(job)
    return status(job)


@app.get("/api/status/{key}")
def get_status(key: str):
    if key not in jobs:
        raise HTTPException(404, "No such field. Start it with /api/lookup?q=...")
    touch(jobs[key])
    return status(jobs[key])


@app.get("/api/leave/{key}")
def leave(key: str):
    """A viewer moved on: the build pauses unless someone else asks for it within LEAVE_GRACE_S."""
    if key in jobs and ABANDON_S > 0:
        jobs[key].left_at = time.time()
    return {"ok": True}


restore_jobs()
threading.Thread(target=worker, daemon=True).start()
if ABANDON_S > 0:
    threading.Thread(target=pause_abandoned, daemon=True).start()
app.mount("/data", StaticFiles(directory=DATA), name="data")
