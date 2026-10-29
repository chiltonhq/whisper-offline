#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, Iterable

# Force Hugging Face libraries into offline mode before anything imports
# huggingface_hub (faster_whisper does, at import time). All models are
# bundled locally, so the network is never needed at runtime.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from faster_whisper import WhisperModel

SUPPORTED_EXTS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"}
MODEL_BY_QUALITY = {
    "large": "faster-whisper-large-v3",
    "medium": "faster-whisper-medium",
}
DIARIZATION_MODEL_NAME = "pyannote-speaker-diarization-3.1"
DIARIZATION_DEPENDENCY_DIRS = {
    "pyannote/segmentation-3.0": "pyannote-segmentation-3.0",
    "pyannote/wespeaker-voxceleb-resnet34-LM": "pyannote-wespeaker-voxceleb-resnet34-LM",
    "speechbrain/spkrec-ecapa-voxceleb": "speechbrain-spkrec-ecapa-voxceleb",
}
MODEL_CANDIDATES = tuple(MODEL_BY_QUALITY.values())
Logger = Callable[[str], None]


def runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_model_dir() -> Path | None:
    candidates: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        for model_name in MODEL_CANDIDATES:
            candidates.append(Path(meipass) / "models" / model_name)

    for model_name in MODEL_CANDIDATES:
        candidates.append(runtime_base_dir() / "models" / model_name)

    for path in candidates:
        if path.exists():
            return path.resolve()
    return None


def model_dir_for_quality(quality: str) -> Path | None:
    model_name = MODEL_BY_QUALITY.get(quality.lower())
    if not model_name:
        return None

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "models" / model_name)
    candidates.append(runtime_base_dir() / "models" / model_name)

    for path in candidates:
        if path.exists():
            return path.resolve()
    return None


def diarization_model_dir() -> Path | None:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "models" / DIARIZATION_MODEL_NAME)
    candidates.append(runtime_base_dir() / "models" / DIARIZATION_MODEL_NAME)

    for path in candidates:
        if path.exists():
            return path.resolve()
    return None


def list_supported_audio_files(input_dir: Path) -> list[Path]:
    return [
        p
        for p in sorted(input_dir.iterdir())
        if p.is_file() and p.suffix.lower().lstrip(".") in SUPPORTED_EXTS
    ]


def default_cpu_threads() -> int:
    """Number of physical CPU cores, as detected by PyTorch.

    faster-whisper defaults to 4 threads, which leaves bigger machines idle.
    Counting hyper-threads as cores backfires: on a 4-core/8-thread CPU,
    8 threads ran Whisper ~30% slower than 4.
    """
    import torch

    return max(1, torch.get_num_threads())


def load_model(model_dir: Path, compute_type: str = "int8", cpu_threads: int | None = None) -> WhisperModel:
    return WhisperModel(
        str(model_dir),
        device="cpu",
        compute_type=compute_type,
        cpu_threads=cpu_threads or default_cpu_threads(),
    )


_SEGMENTATION_WEIGHT_CANDIDATES = (
    "pytorch_model.bin",
    "pytorch_model.safetensors",
    "model.bin",
    "model.safetensors",
)


def _resolve_segmentation_checkpoint(local_dir: Path) -> Path:
    """Return a file path inside a pyannote/segmentation snapshot directory.

    pyannote.audio's `Model.from_pretrained` treats a local argument as a
    checkpoint file (or, failing that, as a Hugging Face repo id that it will
    try to download). Pointing it at the directory directly leaves it to fall
    through to the Hub, which fails on an offline machine. Resolve to the real
    weight file inside the snapshot so the load stays fully local.
    """
    for candidate in _SEGMENTATION_WEIGHT_CANDIDATES:
        candidate_path = local_dir / candidate
        if candidate_path.exists():
            return candidate_path
    # Fall back to the directory; a few pyannote builds accept a folder and
    # look inside for pytorch_model.bin automatically.
    return local_dir


def load_diarization_pipeline(model_dir: Path):
    import os
    import torch
    import yaml
    from pyannote.audio import Pipeline

    # Force Hugging Face libraries into offline mode so that any residual
    # lookups (e.g., for segmentation/embedding dependencies) never reach the
    # network. Without this, a bundled build can silently try to download and
    # fail on the end-user's offline machine.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    # speechbrain >=1.0.3 exposes `speechbrain.integrations.k2_fsa` as a
    # LazyModule whose __getattr__ raises ImportError on any attribute access,
    # including dunders. pytorch-lightning's load_from_checkpoint triggers
    # inspect.stack(), which calls hasattr(mod, "__file__") on every entry in
    # sys.modules -- that crashes the pipeline load on systems without k2.
    try:
        from speechbrain.utils import importutils as _sb_importutils
        _LazyModule = _sb_importutils.LazyModule
        if not getattr(_LazyModule, "_whisper_offline_dunder_patched", False):
            _orig_getattr = _LazyModule.__getattr__
            def _safe_getattr(self, attr, _orig=_orig_getattr):
                if attr.startswith("__") and attr.endswith("__"):
                    raise AttributeError(attr)
                return _orig(self, attr)
            _LazyModule.__getattr__ = _safe_getattr
            _LazyModule._whisper_offline_dunder_patched = True
    except Exception:
        pass

    config_path = model_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Diarization config not found: {config_path}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    params = config.get("pipeline", {}).get("params", {})
    models_root = model_dir.parent

    for key in ("segmentation", "embedding"):
        value = params.get(key)
        if not isinstance(value, str):
            continue
        repo_id = value.split("@", 1)[0]
        local_dir_name = DIARIZATION_DEPENDENCY_DIRS.get(repo_id)
        if not local_dir_name:
            continue
        local_dir = models_root / local_dir_name
        if not local_dir.exists():
            continue

        if key == "segmentation":
            # pyannote.audio expects a checkpoint *file* for local loads.
            resolved = _resolve_segmentation_checkpoint(local_dir)
            params[key] = str(resolved)
        elif repo_id == "pyannote/wespeaker-voxceleb-resnet34-LM":
            # The wespeaker embedding loads via pyannote's Model.from_pretrained,
            # same as segmentation, so it needs a checkpoint file path.
            resolved = _resolve_segmentation_checkpoint(local_dir)
            params[key] = str(resolved)
        else:
            # speechbrain/spkrec-ecapa-voxceleb is loaded through
            # `EncoderClassifier.from_hparams(source=<dir>)`, which accepts a
            # local directory. The directory name must contain "speechbrain"
            # so pyannote dispatches to the speechbrain backend.
            params[key] = str(local_dir)

    temp_config = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    try:
        yaml.safe_dump(config, temp_config, sort_keys=False)
        temp_config_path = Path(temp_config.name)
    finally:
        temp_config.close()

    try:
        pipeline = Pipeline.from_pretrained(str(temp_config_path))
    finally:
        temp_config_path.unlink(missing_ok=True)

    if pipeline is None:
        missing = [DIARIZATION_MODEL_NAME, *DIARIZATION_DEPENDENCY_DIRS.values()]
        raise RuntimeError(
            "Diarization pipeline failed to load from the local bundle. "
            "Confirm these folders are present under 'models/' next to the executable: "
            + ", ".join(missing)
        )

    pipeline.to(torch.device("cpu"))
    return pipeline


MIN_TURN_SECONDS = 0.3
MIN_HOLD_WORDS = 2
SNAP_WINDOW_SECONDS = 0.8
PUNCTUATION_END = (".", "?", "!", ",", ":", ";", "。", "？", "！", "，", "：", "；")


def apply_speaker_labels(
    audio_path: Path,
    seg_rows: list[dict],
    diarization_pipeline,
    logger: Logger = print,
) -> list[dict]:
    if not seg_rows:
        return seg_rows

    if diarization_pipeline is None:
        for seg in seg_rows:
            seg["speaker"] = "SPEAKER_00"
            seg.pop("words", None)
        return seg_rows

    logger("  Running speaker diarization...")
    try:
        # pyannote's default loader uses soundfile/libsndfile, which cannot
        # read m4a/mp4/webm. Decode via faster_whisper's av-based loader
        # (ffmpeg) to a mono 16kHz tensor and hand that to the pipeline.
        import torch
        from faster_whisper.audio import decode_audio

        waveform = decode_audio(str(audio_path), sampling_rate=16000)
        tensor = torch.from_numpy(waveform).unsqueeze(0)
        diarization = diarization_pipeline(
            {"waveform": tensor, "sample_rate": 16000}
        )
    except Exception as exc:
        logger(f"  Warning: diarization failed ({exc}). Falling back to SPEAKER_00.")
        for seg in seg_rows:
            seg["speaker"] = "SPEAKER_00"
            seg.pop("words", None)
        return seg_rows

    turns: list[dict] = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append(
            {
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": str(speaker),
            }
        )

    if not turns:
        logger("  Warning: diarization returned no turns. Falling back to SPEAKER_00.")
        for seg in seg_rows:
            seg["speaker"] = "SPEAKER_00"
            seg.pop("words", None)
        return seg_rows

    speaker_map: dict[str, str] = {}

    def map_label(raw: str) -> str:
        if raw not in speaker_map:
            speaker_map[raw] = f"SPEAKER_{len(speaker_map):02d}"
        return speaker_map[raw]

    def speaker_at(t: float) -> str:
        for turn in turns:
            if turn["start"] <= t <= turn["end"]:
                return turn["speaker"]
        # No turn covers this instant — pick nearest by midpoint.
        best = turns[0]["speaker"]
        best_dist = float("inf")
        for turn in turns:
            mid = (turn["start"] + turn["end"]) / 2.0
            d = abs(t - mid)
            if d < best_dist:
                best_dist = d
                best = turn["speaker"]
        return best

    def segment_majority(seg_start: float, seg_end: float, fallback: str) -> str:
        best_overlap = 0.0
        best_label = fallback
        for turn in turns:
            overlap = min(seg_end, turn["end"]) - max(seg_start, turn["start"])
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = turn["speaker"]
        return best_label

    out: list[dict] = []

    for seg in seg_rows:
        words = seg.get("words") or []
        seg_start = float(seg["start"])
        seg_end = float(seg["end"])

        if not words:
            label = segment_majority(seg_start, seg_end, turns[0]["speaker"])
            out.append(
                {
                    "start": round(seg_start, 3),
                    "end": round(seg_end, 3),
                    "text": str(seg.get("text", "")).strip(),
                    "speaker": map_label(label),
                }
            )
            continue

        # Step 1: classify each word's speaker by its midpoint.
        n = len(words)
        speakers: list[str] = [
            speaker_at((float(w["start"]) + float(w["end"])) / 2.0) for w in words
        ]

        # Step 2: hysteresis. If a different speaker holds the floor for fewer
        # than MIN_HOLD_WORDS consecutive words AND is sandwiched between the
        # same speaker on both sides, treat it as overlap noise and revert.
        if n > 2:
            i = 1
            while i < n:
                j = i
                while j < n and speakers[j] == speakers[i]:
                    j += 1
                run_len = j - i
                if (
                    run_len < MIN_HOLD_WORDS
                    and speakers[i - 1] != speakers[i]
                    and j < n
                    and speakers[j] == speakers[i - 1]
                ):
                    for k in range(i, j):
                        speakers[k] = speakers[i - 1]
                i = j

        # Step 3: snap-to-punctuation. At each speaker boundary, if the word
        # just before doesn't end in punctuation, scan nearby words for one
        # that does and shift the boundary there.
        def ends_in_punct(idx: int) -> bool:
            return words[idx]["word"].rstrip().endswith(PUNCTUATION_END)

        i = 1
        while i < n:
            if speakers[i] != speakers[i - 1] and not ends_in_punct(i - 1):
                boundary_time = (
                    float(words[i - 1]["end"]) + float(words[i]["start"])
                ) / 2.0
                best_c = -1
                best_dist = float("inf")
                # Look at candidate split points up to ~3 words on either side.
                for c in range(max(0, i - 3), min(n - 1, i + 2)):
                    if c == i - 1:
                        continue
                    if not ends_in_punct(c):
                        continue
                    if speakers[c] != speakers[i - 1] and speakers[c] != speakers[i]:
                        continue
                    w_end = float(words[c]["end"])
                    if abs(w_end - boundary_time) > SNAP_WINDOW_SECONDS:
                        continue
                    d = abs(w_end - boundary_time)
                    if d < best_dist:
                        best_dist = d
                        best_c = c
                if best_c >= 0:
                    left_spk = speakers[i - 1]
                    right_spk = speakers[i]
                    if best_c < i - 1:
                        for k in range(best_c + 1, i):
                            speakers[k] = right_spk
                    else:
                        for k in range(i, best_c + 1):
                            speakers[k] = left_spk
                    i = max(i, best_c) + 1
                    continue
            i += 1

        # Step 4: group consecutive same-speaker words.
        groups: list[dict] = []
        for idx, w in enumerate(words):
            spk = speakers[idx]
            w_start = float(w["start"])
            w_end = float(w["end"])
            if groups and groups[-1]["speaker"] == spk:
                groups[-1]["end"] = w_end
                groups[-1]["words"].append(w["word"])
            else:
                groups.append(
                    {
                        "start": w_start,
                        "end": w_end,
                        "speaker": spk,
                        "words": [w["word"]],
                    }
                )

        # Merge sub-MIN_TURN groups into the previous group to suppress
        # spurious speaker flips on short utterances ("yeah", "uh-huh").
        if len(groups) > 1:
            merged: list[dict] = []
            for g in groups:
                dur = g["end"] - g["start"]
                if dur < MIN_TURN_SECONDS and merged:
                    merged[-1]["end"] = g["end"]
                    merged[-1]["words"].extend(g["words"])
                else:
                    merged.append(g)
            groups = merged

        for g in groups:
            text = "".join(g["words"]).strip()
            if not text:
                continue
            out.append(
                {
                    "start": round(g["start"], 3),
                    "end": round(g["end"], 3),
                    "text": text,
                    "speaker": map_label(g["speaker"]),
                }
            )

    logger(
        f"  Speaker diarization complete ({len(speaker_map)} speakers, {len(out)} segments)."
    )
    return out


def format_hhmmss(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_timestamped_transcript(seg_rows: list[dict]) -> str:
    lines: list[str] = []
    for seg in seg_rows:
        content = str(seg.get("text", "")).strip()
        if not content:
            continue
        start = format_hhmmss(float(seg.get("start", 0.0)))
        end = format_hhmmss(float(seg.get("end", 0.0)))
        speaker = str(seg.get("speaker", "SPEAKER_00"))
        lines.append(f"[{start}-{end}] {speaker}: {content}")
    return "\n".join(lines).strip()


def transcribe_one(
    model: WhisperModel,
    audio_path: Path,
    language: str | None,
    diarization_pipeline,
    logger: Logger = print,
    task: str = "transcribe",
) -> str:
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        task=task,
        vad_filter=True,
        multilingual=(language is None),
        word_timestamps=True,
    )
    seg_rows: list[dict] = []
    duration = float(getattr(info, "duration", 0.0) or 0.0)
    last_printed_pct = -1

    for s in segments:
        content = s.text.strip()
        words = []
        for w in (getattr(s, "words", None) or []):
            words.append({"start": float(w.start), "end": float(w.end), "word": w.word})
        seg_rows.append(
            {
                "start": round(s.start, 3),
                "end": round(s.end, 3),
                "text": content,
                "words": words,
            }
        )
        if duration > 0:
            pct = int(min(100, (s.end / duration) * 100))
            if pct >= last_printed_pct + 5:
                logger(f"  Progress: {pct}% ({s.end:.0f}s/{duration:.0f}s)")
                last_printed_pct = pct

    if duration > 0 and last_printed_pct < 100:
        logger(f"  Progress: 100% ({duration:.0f}s/{duration:.0f}s)")

    seg_rows = apply_speaker_labels(audio_path, seg_rows, diarization_pipeline, logger=logger)
    return build_timestamped_transcript(seg_rows)


def _unique_path(path: Path) -> Path:
    """Return path, or "name (2).ext", "name (3).ext"... if it already exists."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def process_audio_files(
    model: WhisperModel,
    audio_files: Iterable[Path],
    processed_dir: Path,
    language: str | None,
    logger: Logger = print,
    task: str = "transcribe",
    move_audio: Callable[[Path], bool] | None = None,
) -> int:
    """Transcribe each file and write its transcript into processed_dir.

    move_audio decides, per file, whether the audio is moved into
    processed_dir once transcribed (so a watched input folder doesn't queue it
    again). By default every file is moved, which is what the CLI expects.
    """
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_count = 0

    diarization_pipeline = None
    d_model_dir = diarization_model_dir()
    if d_model_dir is None:
        logger(
            f"Warning: diarization model not found ({DIARIZATION_MODEL_NAME}). "
            "Falling back to SPEAKER_00."
        )
    else:
        try:
            logger(f"Loading diarization model from: {d_model_dir}")
            diarization_pipeline = load_diarization_pipeline(d_model_dir)
        except Exception as exc:
            logger(f"Warning: could not load diarization model ({exc}). Falling back to SPEAKER_00.")

    for audio_path in audio_files:
        logger(f"Transcribing: {audio_path.name}")
        try:
            text = transcribe_one(
                model,
                audio_path,
                language,
                diarization_pipeline=diarization_pipeline,
                logger=logger,
                task=task,
            )

            txt_path = _unique_path(processed_dir / f"{audio_path.name}_transcription.txt")
            txt_path.write_text(text, encoding="utf-8")

            if move_audio is None or move_audio(audio_path):
                shutil.move(str(audio_path), str(_unique_path(processed_dir / audio_path.name)))

            logger(f"Saved: {txt_path.name}")
            logger(f"Finished: {audio_path.name}")
            processed_count += 1
        except Exception as exc:
            logger(f"Failed on {audio_path.name}: {exc}")

    logger(f"Done. Results are in: {processed_dir}")
    return processed_count


def main() -> int:
    base = runtime_base_dir()

    parser = argparse.ArgumentParser(description="Offline local Whisper transcription")
    parser.add_argument("--input-dir", default=str(base), help="Folder containing audio files")
    parser.add_argument("--processed-dir", default=str(base / "processed"), help="Folder for moved audio + outputs")
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Local CTranslate2 Whisper model directory (optional; auto-detected if omitted)",
    )
    parser.add_argument("--quality", choices=["medium", "large"], default="large", help="Model quality")
    parser.add_argument("--language", default=None, help="Optional language code, e.g. en")
    parser.add_argument("--compute-type", default="int8", help="faster-whisper compute type, e.g. int8, float16")

    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    processed_dir = Path(args.processed_dir).resolve()

    if not input_dir.exists():
        print(f"Input folder not found: {input_dir}")
        return 1

    model_dir: Path | None
    if args.model_dir:
        model_dir = Path(args.model_dir).resolve()
    else:
        model_dir = model_dir_for_quality(args.quality) or default_model_dir()

    if model_dir is None or not model_dir.exists():
        print("Model folder not found.")
        print("Bundle a local model first. See README.md")
        return 1

    print(f"Loading model from: {model_dir}")
    model = load_model(model_dir, compute_type=args.compute_type)

    audio_files = list_supported_audio_files(input_dir)
    if not audio_files:
        print(f"No supported audio files found in: {input_dir}")
        return 0

    process_audio_files(
        model=model,
        audio_files=audio_files,
        processed_dir=processed_dir,
        language=args.language,
        logger=print,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
