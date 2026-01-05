from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from language_service import translate_text

import os
import shutil
import json
import uuid
import threading
import time
from dotenv import load_dotenv
from pydub import AudioSegment
from typing import Set, Optional
from functools import lru_cache
import logging
from pathlib import Path

# ================= LOGGING SETUP =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= LOAD ENV =================
load_dotenv()

# ================= CONFIGURATION =================
class Config:
    # FFmpeg paths - use system PATH in production
    FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
    FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")
    
    # CORS origins - restrict in production
    ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
    
    # Directories
    BASE_DIR = Path(__file__).parent
    UPLOAD_DIR = BASE_DIR / "uploads"
    PROCESSED_DIR = BASE_DIR / "processed"
    TRANSCRIPTS_DIR = BASE_DIR / "transcripts"
    SUMMARIES_DIR = BASE_DIR / "summaries"
    PDFS_DIR = BASE_DIR / "pdfs"
    
    # Bluetooth directory - disable in production if not needed
    BLUETOOTH_DIR = os.getenv("BLUETOOTH_DIR", "")
    ENABLE_BLUETOOTH_WATCHER = os.getenv("ENABLE_BLUETOOTH_WATCHER", "false").lower() == "true"
    
    # Files
    STATUS_FILE = BASE_DIR / "status.json"
    PROCESSED_LOG = BASE_DIR / "processed_bluetooth.json"
    
    # Cache settings
    STATUS_CACHE_TTL = int(os.getenv("STATUS_CACHE_TTL", "2"))
    
    # File processing
    FILE_READY_TIMEOUT = int(os.getenv("FILE_READY_TIMEOUT", "20"))
    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
    
    # Rate limiting
    MAX_CONCURRENT_PROCESSING = int(os.getenv("MAX_CONCURRENT_PROCESSING", "3"))

config = Config()

# ================= FFMPEG SETUP =================
if config.FFMPEG_PATH != "ffmpeg":
    os.environ["PATH"] += os.pathsep + str(Path(config.FFMPEG_PATH).parent)
AudioSegment.converter = config.FFMPEG_PATH
AudioSegment.ffprobe = config.FFPROBE_PATH

# ================= SERVICES =================
from assembly_service import transcribe_audio
from groq_service import generate_summary
from pdf_service import generate_pdf

# ================= APP =================
app = FastAPI(
    title="Medical Audio Transcription API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= CREATE DIRECTORIES =================
for directory in [
    config.UPLOAD_DIR,
    config.PROCESSED_DIR,
    config.TRANSCRIPTS_DIR,
    config.SUMMARIES_DIR,
    config.PDFS_DIR
]:
    directory.mkdir(parents=True, exist_ok=True)

# ================= PROCESSING SEMAPHORE =================
PROCESSING_SEMAPHORE = threading.Semaphore(config.MAX_CONCURRENT_PROCESSING)

# ================= CACHED STATUS =================
_status_cache = {"data": None, "timestamp": 0}

def write_status(data: dict):
    """Write status with cache invalidation"""
    data["timestamp"] = int(time.time())
    try:
        with open(config.STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _status_cache["data"] = data
        _status_cache["timestamp"] = time.time()
    except Exception as e:
        logger.error(f"Failed to write status: {e}")

@app.get("/status")
def get_status():
    """Get current processing status"""
    try:
        if (_status_cache["data"] is not None and 
            time.time() - _status_cache["timestamp"] < config.STATUS_CACHE_TTL):
            return _status_cache["data"]
        
        if not config.STATUS_FILE.exists():
            status = {"stage": "idle", "message": "Ready", "progress": 0}
        else:
            with open(config.STATUS_FILE, encoding="utf-8") as f:
                status = json.load(f)
        
        _status_cache["data"] = status
        _status_cache["timestamp"] = time.time()
        
        return status
    except Exception as e:
        logger.error(f"Error reading status: {e}")
        return {"stage": "error", "message": "Status unavailable", "progress": 0}

# ================= PROCESSED LOG =================
def load_processed() -> Set[str]:
    """Load processed files log"""
    try:
        if not config.PROCESSED_LOG.exists():
            return set()
        with open(config.PROCESSED_LOG, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception as e:
        logger.error(f"Error loading processed log: {e}")
        return set()

def save_processed(processed_set: Set[str]):
    """Save processed files log"""
    try:
        with open(config.PROCESSED_LOG, "w", encoding="utf-8") as f:
            json.dump(sorted(list(processed_set)), f, indent=2)
    except Exception as e:
        logger.error(f"Error saving processed log: {e}")

# ================= FILE READY CHECK =================
def wait_until_ready(path: Path, timeout: int = None) -> bool:
    """Wait until file is ready for processing"""
    if timeout is None:
        timeout = config.FILE_READY_TIMEOUT
        
    last_size = -1
    start = time.time()
    stable_count = 0
    
    while time.time() - start < timeout:
        try:
            size = path.stat().st_size
            if size > 0 and size == last_size:
                stable_count += 1
                if stable_count >= 2:
                    return True
            else:
                stable_count = 0
            last_size = size
        except FileNotFoundError:
            pass
        time.sleep(0.5)
    return False

# ================= AUDIO PREPROCESS =================
def preprocess_audio(input_path: Path, output_wav: Path):
    """Preprocess audio file"""
    try:
        audio = AudioSegment.from_file(str(input_path))
        if audio.channels != 1 or audio.frame_rate != 16000:
            audio = audio.set_channels(1).set_frame_rate(16000)
        audio.export(str(output_wav), format="wav", parameters=["-ac", "1", "-ar", "16000"])
        del audio
        logger.info(f"Audio preprocessed: {output_wav.name}")
    except Exception as e:
        logger.error(f"Audio preprocessing failed: {e}")
        raise

# ================= ROLE-BASED FORMATTER =================
def format_role_based_text(utterances):
    """Format transcript with speaker roles"""
    if not utterances:
        return ""

    speaker_lengths = {}
    for u in utterances:
        speaker_lengths[u["speaker"]] = speaker_lengths.get(u["speaker"], 0) + len(u["text"])

    doctor_speaker = max(speaker_lengths, key=speaker_lengths.get) if speaker_lengths else None

    lines = [
        f"{'Doctor' if u['speaker'] == doctor_speaker else 'Patient'}: {u['text']}"
        for u in utterances
    ]

    return "\n".join(lines)

@lru_cache(maxsize=128)
def detect_language_from_text(text: str) -> str:
    """Detect language from text (cached)"""
    for ch in text[:500]:
        if "\u0900" <= ch <= "\u097F":
            return "hi"
    return "en"

# ================= CORE PIPELINE =================
def process_audio_pipeline(wav_path: Path, base_name: str, source: str) -> bool:
    """Main audio processing pipeline"""
    if not PROCESSING_SEMAPHORE.acquire(blocking=False):
        logger.warning(f"Max concurrent processing reached, queuing: {base_name}")
        PROCESSING_SEMAPHORE.acquire()  # Wait for slot
    
    try:
        logger.info(f"Starting pipeline for: {base_name} (source: {source})")
        
        # TRANSCRIPTION
        write_status({
            "source": source,
            "file": base_name,
            "stage": "transcribing",
            "message": "Transcribing audio...",
            "progress": 20
        })

        transcript = None
        for attempt in range(2):
            try:
                transcript = transcribe_audio(str(wav_path))
                if transcript and getattr(transcript, "text", None):
                    break
            except Exception as e:
                logger.warning(f"Transcription attempt {attempt + 1} failed: {e}")
                if attempt < 1:
                    time.sleep(2)

        if not transcript or not transcript.text or not transcript.text.strip():
            raise RuntimeError("Transcription failed or empty")

        language = detect_language_from_text(transcript.text)
        logger.info(f"Detected language: {language}")

        write_status({
            "source": source,
            "file": base_name,
            "stage": "transcribing",
            "message": "Processing transcript...",
            "progress": 40
        })

        utterances = [
            {
                "speaker": u.speaker,
                "text": u.text,
                "start_ms": u.start,
                "end_ms": u.end
            }
            for u in (getattr(transcript, "utterances", None) or [])
        ]

        role_based_text = format_role_based_text(utterances)

        transcript_json = {
            "audio_file": base_name,
            "language": language,
            "full_text": role_based_text,
            "utterances": utterances
        }

        tpath = config.TRANSCRIPTS_DIR / f"{base_name}.json"
        with open(tpath, "w", encoding="utf-8") as f:
            json.dump(transcript_json, f, indent=2, ensure_ascii=False)

        # SUMMARY
        write_status({
            "source": source,
            "file": base_name,
            "language": language,
            "stage": "summarizing",
            "message": "Generating summary...",
            "progress": 60
        })

        summary_en = generate_summary(transcript_json)
        if not summary_en:
            raise RuntimeError("Summary generation failed")

        write_status({
            "source": source,
            "file": base_name,
            "language": language,
            "stage": "summarizing",
            "message": "Translating summary..." if language != "en" else "Finalizing summary...",
            "progress": 75
        })

        if language != "en":
            summary_final = {
                k: [translate_text(i, language) for i in v]
                if isinstance(v, list)
                else translate_text(v, language)
                for k, v in summary_en.items()
            }
        else:
            summary_final = summary_en

        spath = config.SUMMARIES_DIR / f"{base_name}_summary.json"
        with open(spath, "w", encoding="utf-8") as f:
            json.dump(summary_final, f, indent=2, ensure_ascii=False)

        # PDF
        write_status({
            "source": source,
            "file": base_name,
            "language": language,
            "stage": "generating_pdf",
            "message": "Creating PDF report...",
            "progress": 90
        })

        generate_pdf(str(spath), language=language)

        write_status({
            "source": source,
            "file": base_name,
            "language": language,
            "stage": "completed",
            "message": "Processing complete!",
            "progress": 100
        })

        logger.info(f"Pipeline completed: {base_name}")
        return True

    except Exception as e:
        logger.error(f"Pipeline error for {base_name}: {e}", exc_info=True)
        write_status({
            "source": source,
            "file": base_name,
            "stage": "error",
            "message": f"Error: {str(e)}",
            "error": str(e),
            "progress": 0
        })
        return False
    finally:
        PROCESSING_SEMAPHORE.release()

# ================= BLUETOOTH WATCHER =================
def bluetooth_watcher():
    """Watch Bluetooth directory for new files"""
    logger.info("Bluetooth watcher started")
    processed = load_processed()
    last_check = 0

    while True:
        try:
            if time.time() - last_check < 3:
                time.sleep(0.5)
                continue
            
            last_check = time.time()

            bluetooth_path = Path(config.BLUETOOTH_DIR)
            if not bluetooth_path.exists():
                time.sleep(5)
                continue

            for file_path in bluetooth_path.iterdir():
                if not file_path.is_file():
                    continue
                    
                if file_path.name in processed:
                    continue

                if not file_path.suffix.lower() in [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".3gp"]:
                    continue

                try:
                    if file_path.stat().st_size == 0:
                        continue
                except:
                    continue

                if not wait_until_ready(file_path):
                    logger.warning(f"File not ready: {file_path.name}")
                    continue

                uid = uuid.uuid4().hex[:8]
                new_name = f"{uid}_{file_path.name}"
                upload_path = config.UPLOAD_DIR / new_name

                shutil.move(str(file_path), str(upload_path))
                logger.info(f"Moved from Bluetooth: {new_name}")

                base = upload_path.stem
                wav_path = config.PROCESSED_DIR / f"{base}.wav"

                preprocess_audio(upload_path, wav_path)

                if process_audio_pipeline(wav_path, base, "bluetooth"):
                    processed.add(file_path.name)
                    save_processed(processed)

        except Exception as e:
            logger.error(f"Bluetooth watcher error: {e}", exc_info=True)

        time.sleep(3)

# ================= WEB UPLOAD =================
@app.post("/upload-audio")
async def upload_audio(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Upload audio file for processing"""
    try:
        # Check file size
        file.file.seek(0, 2)
        size_mb = file.file.tell() / (1024 * 1024)
        file.file.seek(0)
        
        if size_mb > config.MAX_FILE_SIZE_MB:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max size: {config.MAX_FILE_SIZE_MB}MB"
            )
        
        # Validate file extension
        ext = Path(file.filename).suffix.lower()
        if ext not in [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".3gp"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid file format. Supported: wav, mp3, m4a, aac, ogg, 3gp"
            )
        
        uid = uuid.uuid4().hex[:8]
        safe_filename = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
        name = f"{uid}_{safe_filename}"
        raw = config.UPLOAD_DIR / name

        with open(raw, "wb") as f:
            while chunk := await file.read(8192):
                f.write(chunk)

        base = raw.stem
        wav = config.PROCESSED_DIR / f"{base}.wav"

        def process_task():
            try:
                preprocess_audio(raw, wav)
                process_audio_pipeline(wav, base, "web")
            except Exception as e:
                logger.error(f"Background processing failed: {e}", exc_info=True)

        background_tasks.add_task(process_task)
        
        logger.info(f"Upload received: {name}")
        return {"status": "processing", "audio_name": base}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Upload failed")

# ================= PDF DOWNLOAD =================
@app.get("/download-pdf/{audio_name}")
def download_pdf(audio_name: str):
    """Download generated PDF report"""
    # Sanitize filename
    safe_name = "".join(c for c in audio_name if c.isalnum() or c in "_-")
    path = config.PDFS_DIR / f"{safe_name}_summary.pdf"
    
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    
    return FileResponse(
        path, 
        media_type="application/pdf",
        filename=f"summary_{safe_name}.pdf"
    )

# ================= STARTUP =================
@app.on_event("startup")
def on_startup():
    """Initialize application on startup"""
    write_status({"stage": "idle", "message": "Ready", "progress": 0})
    logger.info("Application started")
    
    if config.ENABLE_BLUETOOTH_WATCHER and config.BLUETOOTH_DIR:
        logger.info("Starting Bluetooth watcher")
        threading.Thread(target=bluetooth_watcher, daemon=True).start()
    else:
        logger.info("Bluetooth watcher disabled")

# ================= SHUTDOWN =================
@app.on_event("shutdown")
def on_shutdown():
    """Cleanup on shutdown"""
    logger.info("Application shutting down")

# ================= HEALTH CHECK =================
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "version": "1.0.0",
        "bluetooth_watcher": config.ENABLE_BLUETOOTH_WATCHER
    }

# ================= ROOT =================
@app.get("/")
def root():
    """API root"""
    return {
        "message": "Medical Audio Transcription API",
        "version": "1.0.0",
        "docs": "/api/docs"
    }