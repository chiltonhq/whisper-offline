# Build & Release Quickstart

A checklist for building Whisper Offline and publishing it as a GitHub Release. Run it on an **internet-connected Windows PC** with [Miniconda](https://docs.conda.io/en/latest/miniconda.html) installed. End users don't need any of this; they just download the release.

## 1) Open PowerShell in the project folder

Use a short path to stay clear of Windows' 260-character path limit:

```powershell
cd C:\dev\whisper-offline
```

## 2) Set your Hugging Face token (build machine only)

If you don't have one yet:
1. Sign in at <https://huggingface.co>
2. Create a **read** token at <https://huggingface.co/settings/tokens>
3. Accept the terms on:
   - <https://huggingface.co/pyannote/speaker-diarization-3.1>
   - <https://huggingface.co/pyannote/segmentation-3.0>

```powershell
$env:HF_TOKEN="hf_your_token_here"
```

## 3) Build

```powershell
.\build_offline_bundle_windows.bat
```

This creates or updates the Conda environment, runs preflight checks, downloads all six models, and builds the app into `dist\WhisperOffline`.

## 4) Smoke-test the build

1. Double-click `dist\WhisperOffline\WhisperOffline.exe` and check that "Whisper Offline" shortcuts appear on the desktop and in the Start menu
2. Add a short audio clip and click **Start** with each model quality
3. Click **Open** next to "Save transcripts to" and confirm a `*_transcription.txt` with speaker labels is in `Documents\Whisper Offline`
4. Confirm `dist\WhisperOffline\licenses\packages\conda` and `...\packages\pip` contain license folders (the build prints a warning if not)
5. Optional: disconnect from the internet and repeat, to confirm it works fully offline

## 5) Package the release

```powershell
powershell -ExecutionPolicy Bypass -File package_release.ps1 -Version v1.0
```

Output in `release\`:
- `WhisperOffline-v1.0.zip.001`, `.002`, ... (each under 2 GB)
- `Combine-WhisperOffline.bat` (joins the parts for downloaders)
- `SHA256SUMS.txt`

## 6) Publish on GitHub

1. On your repository page, go to **Releases** and choose **Draft a new release**.
2. Create the tag `v1.0`, and give the release a title and notes.
3. Drag **every file** from `release\` into the *Attach binaries* area and wait for all uploads to finish.
4. Click **Publish release**.

The README's download link (`../../releases/latest`) then points to it automatically.

## Notes

- End users don't need Hugging Face accounts or tokens. `HF_TOKEN` is only used here.
- Bump the version (for example `-Version v1.1`) and the `v1.0` label in `offline_transcribe_gui.py` together for each new release.
