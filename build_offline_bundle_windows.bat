@echo off
setlocal EnableExtensions

cd /d "%~dp0"
set "ENV_NAME=whisper-offline-build"

where conda >nul 2>&1
if errorlevel 1 (
  echo Conda not found. Install Miniconda or Anaconda first.
  exit /b 1
)

call conda env update -n "%ENV_NAME%" -f environment_offline.yml --prune
if errorlevel 1 exit /b 1

echo Running preflight import checks...
call conda run -n "%ENV_NAME%" python -c "import ctranslate2, faster_whisper, PySide6.QtCore; import offline_transcribe; print('Preflight imports OK.')"
if errorlevel 1 (
  echo Preflight failed: core imports did not load cleanly.
  echo Fix environment issues before packaging.
  exit /b 1
)

call conda run -n "%ENV_NAME%" python -c "from pyannote.audio import Pipeline; import pyannote.audio.pipelines; print('Diarization imports OK.')"
if errorlevel 1 (
  echo Preflight failed: pyannote diarization imports failed.
  echo Fix diarization dependencies before packaging.
  exit /b 1
)

if "%HF_TOKEN%"=="" (
  echo HF_TOKEN environment variable is required to download pyannote diarization model.
  echo PowerShell example: $env:HF_TOKEN="hf_xxx"
  exit /b 1
)

call conda run -n "%ENV_NAME%" python -c "from huggingface_hub import snapshot_download; from pathlib import Path; models=[('Systran/faster-whisper-medium','faster-whisper-medium'),('Systran/faster-whisper-large-v3','faster-whisper-large-v3')]; [snapshot_download(repo_id=repo, local_dir=str((Path('models')/name).resolve()), local_dir_use_symlinks=False) for repo,name in models]; print('Whisper models ready.')"
if errorlevel 1 exit /b 1

call conda run -n "%ENV_NAME%" python -c "from huggingface_hub import snapshot_download; from pathlib import Path; import os; model_dir=(Path('models')/'pyannote-speaker-diarization-3.1').resolve(); model_dir.mkdir(parents=True, exist_ok=True); snapshot_download(repo_id='pyannote/speaker-diarization-3.1', local_dir=str(model_dir), local_dir_use_symlinks=False, token=os.environ['HF_TOKEN']); print('Diarization model ready.')"
if errorlevel 1 exit /b 1

call conda run -n "%ENV_NAME%" python -c "from huggingface_hub import snapshot_download; from pathlib import Path; import os; model_dir=(Path('models')/'pyannote-segmentation-3.0').resolve(); model_dir.mkdir(parents=True, exist_ok=True); snapshot_download(repo_id='pyannote/segmentation-3.0', local_dir=str(model_dir), local_dir_use_symlinks=False, token=os.environ['HF_TOKEN']); print('Segmentation model ready.')"
if errorlevel 1 exit /b 1

call conda run -n "%ENV_NAME%" python -c "from huggingface_hub import snapshot_download; from pathlib import Path; model_dir=(Path('models')/'speechbrain-spkrec-ecapa-voxceleb').resolve(); model_dir.mkdir(parents=True, exist_ok=True); snapshot_download(repo_id='speechbrain/spkrec-ecapa-voxceleb', local_dir=str(model_dir), local_dir_use_symlinks=False); print('Embedding model ready.')"
if errorlevel 1 exit /b 1

rem Wespeaker download uses a short temp path because this repo contains
rem filenames whose full local-dir .cache path exceeds Windows MAX_PATH
rem when combined with the project's working directory.
call conda run -n "%ENV_NAME%" python -c "from huggingface_hub import snapshot_download; from pathlib import Path; import os, shutil; tmp=Path(r'C:\hfdl\wsp'); tmp.mkdir(parents=True, exist_ok=True); snapshot_download(repo_id='pyannote/wespeaker-voxceleb-resnet34-LM', local_dir=str(tmp), token=os.environ['HF_TOKEN']); dest=(Path('models')/'pyannote-wespeaker-voxceleb-resnet34-LM').resolve(); shutil.rmtree(dest, ignore_errors=True); shutil.copytree(str(tmp), str(dest), ignore=shutil.ignore_patterns('.cache')); print('Wespeaker embedding model ready.')"
if errorlevel 1 exit /b 1

call conda run -n "%ENV_NAME%" python -c "from pathlib import Path; import offline_transcribe; offline_transcribe.load_diarization_pipeline((Path('models')/'pyannote-speaker-diarization-3.1').resolve()); print('Diarization local model load OK.')"
if errorlevel 1 (
  echo Preflight failed: local diarization model load failed.
  exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

rem Strip HuggingFace download-bookkeeping caches from bundled model dirs.
rem Their deeply nested paths exceed Windows MAX_PATH once prefixed with the
rem dist\WhisperOffline\_internal\models\... output path, which breaks
rem PyInstaller's COLLECT step. They are not needed at runtime.
for /d %%D in (models\*) do (
  if exist "%%D\.cache" rmdir /s /q "%%D\.cache"
)

call conda run -n "%ENV_NAME%" pyinstaller --noconfirm --clean whisper_offline.spec
if errorlevel 1 exit /b 1

set "APP=dist\WhisperOffline"
mkdir "%APP%\DropAudioHere" 2>nul
mkdir "%APP%\processed" 2>nul
copy /y "launcher\Start Whisper Offline.bat" "%APP%\" >nul
copy /y "launcher\README_FIRST.txt" "%APP%\" >nul
copy /y LICENSE "%APP%\LICENSE.txt" >nul
copy /y THIRD_PARTY_NOTICES.md "%APP%\THIRD_PARTY_NOTICES.txt" >nul
xcopy /e /i /y /q licenses "%APP%\licenses" >nul
call conda run -n "%ENV_NAME%" python collect_licenses.py "%APP%\licenses\packages"
if errorlevel 1 (
  echo WARNING: could not collect package license files into %APP%\licenses\packages.
  echo Fix this before publishing a release.
)

echo.
echo Build complete.
echo Bundled models: medium + large + pyannote/speaker-diarization-3.1 + pyannote/segmentation-3.0 + pyannote/wespeaker-voxceleb-resnet34-LM + speechbrain/spkrec-ecapa-voxceleb
echo App folder:
echo   %APP%
echo.
echo To turn it into GitHub release files, run:
echo   powershell -ExecutionPolicy Bypass -File package_release.ps1
