# Whisper Offline — Architecture Overview

## 1. The problem 

Researchers, journalists, clinicians, lawyers and anyone else handling sensitive recordings (interviews, focus groups, lectures, meetings) often can't send audio to a cloud service, and many work on machines with **no internet access** at all. Cloud transcription services (OpenAI Whisper API, Otter, Rev) are off the table.

So the app has two unusual constraints:

1. **Runs fully offline.** No outbound HTTP at runtime, ever.
2. **Distributed as a single folder** to non-technical users — no Python install, no `pip`, no admin rights.

Everything else in the design follows from those two constraints.

---

## 2. The stack (and why each piece is here)

| Layer | Library | Why |
|---|---|---|
| Speech-to-text | **faster-whisper** (CTranslate2 backend) | OpenAI's Whisper, recompiled for fast CPU inference. ~4× faster than the reference implementation. |
| Speaker diarization | **pyannote.audio 3.1** | Open-source speaker turn detection + clustering. Identifies "who spoke when". |
| Audio decode | **PyAV** (FFmpeg bindings) | Reads m4a/mp4/webm — formats `libsndfile` can't handle. |
| GUI | **PySide6** (Qt for Python) | Native-feeling desktop UI, free for commercial use, single-file deployable. |
| Numerics | **PyTorch 2.3** + **NumPy** | Required by pyannote; CPU-only build (no CUDA needed for end users). |
| Packaging | **PyInstaller 6.14** | Bundles Python interpreter + all deps + assets into one folder. |
| Env mgmt | **Conda** + `environment_offline.yml` | Reproducible Python environment for the build machine. |

**Key insight for learners:** the whole stack is open-source MIT/Apache. The "expensive" part (model training) was already done by OpenAI / pyannote / SpeechBrain. We just glue, package, and run inference.

---

## 3. The transcription pipeline

Two passes plus a regrouping step:

```
audio file ──▶ faster-whisper (word_timestamps=True)  ──▶  segments + per-word
       │                                                    timestamps
       └─────▶ pyannote                                ──▶  speaker turns
                    │                                          │
                    ▼                                          │
            apply_speaker_labels                               │
                    │ ◀──────────────────────────────────────  │
                    │                                          │
                    │  for each Whisper segment:               │
                    │   1. classify each word by midpoint      │
                    │   2. revert <2-word "speaker blips"      │
                    │   3. snap boundaries to nearby           │
                    │      punctuation (±0.8 s)                │
                    │   4. group consecutive same-speaker      │
                    │      words; merge sub-0.3 s groups       │
                    ▼
              [HH:MM:SS-HH:MM:SS] SPEAKER_01: "..."
                    │
                    ▼
        Documents\Whisper Offline\*.txt
```

Two independent passes over the audio, then a merge step that assigns each transcription segment to whichever speaker was talking the most during that time window. See `apply_speaker_labels` in `offline_transcribe.py`.

The naive "majority overlap per Whisper segment" rule was correct but coarse:
when two speakers overlapped inside one Whisper segment, both got bundled
under one speaker label. Word-level timestamps plus a regrouping pass fix
that without re-running ASR.


---

## 4. Offline-by-construction (the interesting part)

The naive approach — "ship the app, hope it doesn't phone home" — fails immediately. pyannote's pipeline config (`config.yaml`) references model repos by HuggingFace ID:

```yaml
embedding: pyannote/wespeaker-voxceleb-resnet34-LM
segmentation: pyannote/segmentation-3.0
```

Those strings are interpreted as "go download this from huggingface.co" the first time the pipeline loads. On an offline machine, that's a hard fail.

**Three layers of defense** ensure no network call ever happens:

1. **Bundle the models physically.** The build script downloads all 6 models on the online builder and PyInstaller embeds them inside `dist\WhisperOffline\_internal\models\`.

2. **Rewrite the config in memory.** Before pyannote loads, `load_diarization_pipeline` reads `config.yaml`, swaps every repo ID for the local file path inside the bundle, writes it to a temp file, and points pyannote at that. The repo IDs never reach the network layer.

3. **Belt and suspenders: kill the network layer entirely.**
   ```python
   os.environ.setdefault("HF_HUB_OFFLINE", "1")
   os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
   ```
   Even if a config string slipped through, the HuggingFace client refuses to make HTTP calls.

**Lesson:** when offline-ness matters, design for it at multiple layers. Don't trust a single env var or a single config rewrite.

---

## 5. Packaging with PyInstaller

The `whisper_offline.spec` file is the recipe. Three things to know:

1. **`Analysis`** walks the import graph from `offline_transcribe_gui.py` and discovers what to include. ML libraries lie about their imports (lazy loading, dynamic plugins), so we explicitly call `collect_submodules("pyannote.audio")` and `collect_data_files("speechbrain", include_py_files=True)` to force-include things PyInstaller's static analysis would miss.

2. **`datas`** ships non-Python assets — including all 6 model directories under `models/`.

3. **`COLLECT`** assembles everything into `dist\WhisperOffline\`. The result is a ~6.8 GB folder that runs anywhere with no install.

**Lesson:** PyInstaller is mostly automatic, but ML stacks always need help. Be ready to add `hiddenimports` and `collect_data_files` calls when packaging anything torch- or transformers-adjacent.

---

## 6. The two-machine model

```
┌───────────────────────────┐                ┌─────────────────────────┐
│  ONLINE BUILDER (Windows) │                │   END-USER PC (offline) │
│                           │                │                         │
│  1. conda env update      │                │   1. Unzip bundle       │
│  2. download 6 models     │                │   2. Run the .exe       │
│  3. preflight checks      │ GitHub Release │   3. Drop audio in      │
│  4. PyInstaller package   │  ───────────▶  │      DropAudioHere/     │
│  5. package_release.ps1   │                │   4. Open transcripts   │
│                           │                │                         │
└───────────────────────────┘                └─────────────────────────┘
```

The builder machine needs internet, conda, an HF token, and ~12 GB free disk. The endpoint needs nothing. This separation is what makes the offline guarantee meaningful — the endpoint *cannot* be tricked into reaching the network because the network code paths are dead before the bundle is built.

---

## 7. Lessons / gotchas worth knowing

A short tour of bugs we hit. Each one is a generally-useful lesson:

- **Windows MAX_PATH is real.** The HuggingFace cache stores files under base64-hashed paths like `models\pyannote-wespeaker-voxceleb-resnet34-LM\.cache\huggingface\download\<long-hash>.incomplete`. Combined with a deep working directory, that easily exceeds 260 chars and `open()` fails. Fix: download to `C:\hfdl\wsp\` (a 17-char path) and copy the result.

- **Lazy imports can fail in surprising places.** SpeechBrain ≥1.0.3 marks `speechbrain.integrations.k2_fsa` as a `LazyModule`. Any attribute access on it triggers a real import — including `hasattr(mod, "__file__")` calls done by `inspect.stack()` deep inside pytorch-lightning. On Windows where `k2` has no wheels, this raises `ImportError` from a stack frame nobody expected. Fix: pin `speechbrain==1.0.2` *and* monkey-patch `LazyModule.__getattr__` to return `AttributeError` for dunder lookups.

- **Audio format support is not uniform.** pyannote loads audio via `libsndfile` (no m4a/mp4 support). faster-whisper loads via PyAV/FFmpeg (everything). We decode once with PyAV to a 16 kHz mono tensor and pass that to pyannote as `{"waveform": tensor, "sample_rate": 16000}`, bypassing libsndfile.

- **PyInstaller's `--clean` flag is not "clean enough".** Stale `models\*\.cache\` directories from prior HF downloads will trip the COLLECT step on MAX_PATH. The `.bat` strips them explicitly with `for /d %%D in (models\*) do if exist "%%D\.cache" rmdir /s /q "%%D\.cache"`.

- **Two OpenMP runtimes will fight at startup.** `ctranslate2` ships its own
  `libiomp5md.dll`, and PyInstaller's `hook-torch` collects PyTorch/MKL's copy to
  the bundle root. With both present, Intel's runtime aborts the instant a model
  loads — `OMP: Error #15: ... libiomp5md.dll already initialized` — which closes
  the app the moment the user clicks Start. The spec's `dedupe_openmp_runtime()`
  runs *after* `Analysis` and keeps a single copy at the bundle root, so `torch`
  and `ctranslate2` resolve to one shared runtime. The pre-`Analysis`
  `should_keep_binary()` filter can't fix it, because PyInstaller's hooks and
  binary-dependency scan re-add these DLLs after the filter runs. It stayed
  dormant for many builds and only appeared on a clean rebuild once the *unpinned*
  build tooling (`_pyinstaller_hooks_contrib`, MKL) drifted to a `hook-torch` that
  also bundles MKL's `libiomp5md.dll`. Unrelated to the bundled-FFmpeg/`av` pin.
  See README → Troubleshooting (OMP Error #15).

- **Whisper segment ≠ speaker turn.** A single Whisper "segment" is whatever
  the model decided to emit between its internal timestamp tokens, capped at
  ~30 s by Whisper's window. Two speakers can easily land in one segment.
  The fix is `word_timestamps=True` plus a regrouping pass that splits on
  speaker change, with hysteresis to suppress single-word blips and a
  snap-to-punctuation pass to keep splits at natural boundaries. Cost is
  ~30–50 % more inference time; quality gain on conversational audio is
  large.

- **Whisper locks one language per file by default.** With `language=None`,
  the model auto-detects once at the start and applies that language to the
  entire file — so mixed Chinese/English audio loses one language. faster-
  whisper's `multilingual=True` flag enables per-chunk language detection;
  we set it whenever the user hasn't pinned a specific language.

- **Mark-of-the-Web is a UX cliff.** Bundles copied across machines or run
  from network shares carry a `Zone.Identifier` ADS that triggers Windows'
  "Open File - Security Warning" dialog on every launch. Every zip downloaded
  from GitHub gets this mark, so on first launch `first_run.py` deletes the
  `Zone.Identifier` stream from every app file. Code-signing is
  the "real" fix but costs money for a certificate.

- **Hyper-Threading doesn't help Whisper.** faster-whisper defaults to 4 CPU
  threads. On a 4-core/8-thread Xeon, 8 threads ran large-v3 31% *slower*
  than 4 (186 s vs 142 s for a 2-minute clip). The app uses one thread per
  physical core, from PyTorch's core count.

- **Windows PowerShell zips use backslashes.** .NET Framework's `ZipFile`
  writes entry paths like `WhisperOffline\_internal\...` unless the
  `Switch.System.IO.Compression.ZipFile.UseBackslash` AppContext switch is
  turned off. Windows' own extractor tolerates backslashes; 7-Zip and other
  tools may not. `package_release.ps1` turns the switch off.

**Meta-lesson:** the last 10% of "make it work everywhere" is where you spend 50% of the time.

---

## 8. Security posture

- No telemetry, analytics, or update checks anywhere.
- No outbound HTTP at runtime (enforced at three layers — see §4).
- Audio and transcripts never leave the endpoint folder.
- Dependencies version-pinned in `environment_offline.yml`.
- Audio decode runs through PyAV's statically-bundled FFmpeg (no system `ffmpeg`); `av` is pinned to `17.1.0` (FFmpeg 8.1.1) to carry the June 2026 FFmpeg CVE fixes into the bundle. See README → Privacy.
- Every GitHub Release ships a `SHA256SUMS.txt` so downloads can be verified.

---

## 9. Source map

If you want to read the code in 10 minutes, in this order:

| File | Lines | What's there |
|---|---|---|
| `offline_transcribe_gui.py` | ~470 | Qt UI, file queue, worker thread, header layout, progress bar, output-path resolution |
| `offline_transcribe.py` | ~510 | Whisper transcription with word timestamps, diarization loading + config rewrite, speaker-change regrouping, output writer |
| `whisper_offline.spec` | ~125 | PyInstaller recipe (now also bundles `assets/app_icon.png` and embeds `app_icon.ico` into the .exe) |
| `build_offline_bundle_windows.bat` | ~90 | Build orchestration (copies `packaging/README_FIRST.txt`, the licenses and notices into each bundle) |
| `package_release.ps1` | ~130 | Zips the bundle and splits it into <2 GB parts for GitHub Releases |
| `assets/make_icon.py` | ~50 | One-shot generator for the waveform app icon (run once at dev time) |
| `environment_offline.yml` | ~20 | Pinned dependencies |

## 10. Runtime configuration

Settings the user (or IT) can change without rebuilding:

- **Output folder.** At launch the GUI picks the first usable folder, creating
  it with `mkdir(parents=True, exist_ok=True)`:
  1. the folder chosen with **Change…** in the main window, remembered via
     `QSettings` (stored under `HKCU\Software\WhisperOffline`)
  2. the path in **`output_path.txt`** next to the `.exe`, a single-line file
     for IT-managed installs (for example a network share). Not shipped by
     default.
  3. `Documents\Whisper Offline`, the default (Qt resolves Documents, so
     OneDrive-redirected folders work)
  4. a `processed\` folder inside the app folder, as a last resort

  Any candidate that can't be created is skipped, and the reason is shown in
  the progress log.

- **Audio files stay put.** Transcripts are written straight into the output
  folder. Audio the user adds with Add Files or Add Folder is never moved.
  Only audio queued from `DropAudioHere\` is moved into the output folder
  afterward, so it isn't queued again on the next launch. Name clashes get a
  ` (2)` suffix instead of overwriting.

  Failure mode worth knowing: resolution happens once, at startup. If the
  network share disconnects mid-session, in-flight transcriptions fail per
  file (caught by the existing per-file try/except) until the user
  restarts.

- **First-run setup** (`first_run.py`, runs inside `WhisperOffline.exe`)
  On first launch, in a background thread, it clears the Mark-of-the-Web flag
  from every file, hides `_internal\` so the app folder only shows what users
  need, and adds Desktop and Start menu shortcuts. A marker file
  (`_internal\.setup_done`) holds the exe path, so setup reruns only if the
  folder moves, and a shortcut the user deleted isn't re-created every launch.
  This replaced an earlier launcher `.bat`, which gave users two things to
  double-click and could be run by mistake from the source repo.

---

## TL;DR

1. Glue together best-in-class open-source ML libraries.
2. Make "offline" a property of the build, not a runtime flag.
3. Bundle aggressively, ship as one folder, publish checksums.
4. Expect the last mile (Windows path limits, lazy imports, format support) to take real work.
