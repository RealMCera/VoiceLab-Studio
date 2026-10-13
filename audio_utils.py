from __future__ import annotations
import shutil, subprocess, sys, uuid, json, math, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.getenv("VOICELAB_DATA_DIR", str(ROOT)))
DATA_ROOT.mkdir(parents=True, exist_ok=True)
OUTPUTS = DATA_ROOT / "outputs"
UPLOADS = DATA_ROOT / "uploads"
OUTPUTS.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)

def require_binary(name: str):
    if not shutil.which(name): raise RuntimeError(f"{name} is required but was not found in PATH")

def run(cmd: list[str]):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0: raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "Command failed")
    return p

def save_upload(data: bytes, suffix: str) -> Path:
    path = UPLOADS / f"{uuid.uuid4().hex}{suffix}"; path.write_bytes(data); return path

def media_duration(src: Path) -> float:
    require_binary("ffprobe")
    p=run(["ffprobe","-v","quiet","-print_format","json","-show_format",str(src)])
    return float(json.loads(p.stdout).get("format",{}).get("duration") or 0)

def extract_audio(src: Path, fmt: str = "mp3") -> Path:
    require_binary("ffmpeg"); out = OUTPUTS / f"extract_{uuid.uuid4().hex}.{fmt}"
    codec = ["-codec:a", "libmp3lame", "-q:a", "2"] if fmt == "mp3" else ["-codec:a", "pcm_s16le"]
    run(["ffmpeg", "-y", "-i", str(src), "-vn", *codec, str(out)]); return out

def apply_audio_controls(src: Path, volume_db: float = 0, speed: float = 1.0) -> Path:
    require_binary("ffmpeg"); out = OUTPUTS / f"processed_{uuid.uuid4().hex}.mp3"; speed=max(0.5,min(2.0,speed))
    run(["ffmpeg","-y","-i",str(src),"-filter:a",f"volume={volume_db}dB,atempo={speed}","-codec:a","libmp3lame","-q:a","2",str(out)]); return out

def pitch_shift(src: Path, semitones: float = 0) -> Path:
    semitones=max(-12.0,min(12.0,float(semitones)))
    if abs(semitones)<0.001: return src
    require_binary("ffmpeg"); out=OUTPUTS/f"pitch_{uuid.uuid4().hex}.wav"; ratio=2**(semitones/12.0); tempo=1.0/ratio
    filt=f"aformat=sample_rates=44100,asetrate={44100*ratio:.6f},aresample=44100,atempo={tempo:.8f}"
    run(["ffmpeg","-y","-i",str(src),"-filter:a",filt,"-codec:a","pcm_s16le",str(out)]); return out

def edit_audio(src: Path, start_seconds: float = 0, end_seconds: float | None = None, gain_db: float = 0, fade_in: float = 0, fade_out: float = 0) -> Path:
    require_binary("ffmpeg"); total=media_duration(src); start=max(0.0,min(float(start_seconds),max(0,total-.05)))
    end=total if end_seconds is None else max(start+.05,min(float(end_seconds),total)); seg=max(.05,end-start)
    fade_in=max(0.0,min(float(fade_in),seg/2)); fade_out=max(0.0,min(float(fade_out),seg/2)); gain=max(-24,min(24,float(gain_db)))
    filters=[f"volume={gain}dB"]
    if fade_in>0: filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out>0: filters.append(f"afade=t=out:st={max(0,seg-fade_out)}:d={fade_out}")
    out=OUTPUTS/f"edit_{uuid.uuid4().hex}.mp3"
    run(["ffmpeg","-y","-ss",str(start),"-to",str(end),"-i",str(src),"-filter:a",",".join(filters),"-codec:a","libmp3lame","-q:a","2",str(out)]); return out

def demucs_two_stems(src: Path) -> tuple[Path, Path]:
    work = OUTPUTS / f"demucs_{uuid.uuid4().hex}"; work.mkdir(parents=True, exist_ok=True)
    run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-o", str(work), str(src)])
    stem_dir = work / "htdemucs" / src.stem; vocals=stem_dir/"vocals.wav"; inst=stem_dir/"no_vocals.wav"
    if not vocals.exists() or not inst.exists(): raise RuntimeError("Demucs finished but expected stems were not found")
    return vocals, inst

def mix_tracks(instrumental: Path, vocal: Path, instrumental_gain_db: float = 0, vocal_gain_db: float = 0) -> Path:
    require_binary("ffmpeg"); out=OUTPUTS/f"cover_{uuid.uuid4().hex}.mp3"; ig=max(-24,min(12,float(instrumental_gain_db))); vg=max(-24,min(12,float(vocal_gain_db)))
    run(["ffmpeg","-y","-i",str(instrumental),"-i",str(vocal),"-filter_complex",f"[0:a]volume={ig}dB[i];[1:a]volume={vg}dB[v];[i][v]amix=inputs=2:duration=longest:normalize=0[a]","-map","[a]","-codec:a","libmp3lame","-q:a","2",str(out)]); return out
