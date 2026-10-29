# Third-Party Notices

Whisper Offline's own source code is MIT-licensed (see `LICENSE`). The packaged
Windows app also includes the third-party software and model weights below, each
distributed under its own license.

Full license texts are in the [`licenses/`](licenses/) folder, which is copied
into every build as `WhisperOffline\licenses\` (see `licenses/README.txt` for
which file covers which component). Built copies also get
`licenses\packages\`, which holds the license files of every Conda and pip
package in the build environment, including the smaller dependencies not
listed here.

## Models (bundled under `_internal\models\`)

| Model | License | Source |
|---|---|---|
| Whisper medium (CTranslate2 conversion) | MIT | https://huggingface.co/Systran/faster-whisper-medium (original: OpenAI, https://github.com/openai/whisper) |
| Whisper large-v3 (CTranslate2 conversion) | MIT | https://huggingface.co/Systran/faster-whisper-large-v3 (original: OpenAI) |
| pyannote speaker-diarization-3.1 | MIT | https://huggingface.co/pyannote/speaker-diarization-3.1 |
| pyannote segmentation-3.0 | MIT | https://huggingface.co/pyannote/segmentation-3.0 |
| WeSpeaker voxceleb-resnet34-LM | CC BY 4.0 | https://huggingface.co/pyannote/wespeaker-voxceleb-resnet34-LM (original: WeSpeaker, https://github.com/wenet-e2e/wespeaker) |
| SpeechBrain spkrec-ecapa-voxceleb | Apache 2.0 | https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb |

The pyannote models are "gated" on Hugging Face: downloading them requires
accepting their terms with a Hugging Face account. This gating is used to collect
user information; the models themselves are MIT-licensed and may be redistributed
with this notice.

## Software

| Component | License | Project |
|---|---|---|
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| pyannote.audio / pyannote.core / pyannote.pipeline | MIT | https://github.com/pyannote |
| SpeechBrain | Apache 2.0 | https://github.com/speechbrain/speechbrain |
| PyTorch | BSD-3-Clause | https://github.com/pytorch/pytorch |
| torchaudio | BSD-2-Clause | https://github.com/pytorch/audio |
| PyTorch Lightning | Apache 2.0 | https://github.com/Lightning-AI/pytorch-lightning |
| Hugging Face Hub client | Apache 2.0 | https://github.com/huggingface/huggingface_hub |
| tokenizers | Apache 2.0 | https://github.com/huggingface/tokenizers |
| PySide6 / Qt for Python | LGPL v3 | https://www.qt.io/qt-for-python |
| PyAV | BSD-3-Clause | https://github.com/PyAV-Org/PyAV |
| FFmpeg libraries (bundled inside PyAV) | LGPL v2.1+ | https://ffmpeg.org |
| NumPy | BSD-3-Clause | https://numpy.org |
| Intel OpenMP runtime (libiomp5md.dll) | Intel Simplified Software License | https://www.intel.com/content/www/us/en/developer/tools/oneapi/openmp.html |
| PyInstaller bootloader | GPL v2 with bootloader exception (does not apply to bundled apps) | https://pyinstaller.org |

### LGPL components

Qt/PySide6 and FFmpeg are LGPL-licensed. They are shipped as separate,
unmodified dynamic libraries (`.dll` / `.pyd` files under `_internal\`), so you
may replace them with your own compatible builds. Their source code is available
from the project pages above.

## Optional NVIDIA GPU add-on

The separate `WhisperOffline-GPU-addon` download (a `gpu` folder) is not part of
the main app. It contains:

| Component | License | Source |
|---|---|---|
| NVIDIA cuBLAS 12.4.5.8 (`cublas64_12.dll`, `cublasLt64_12.dll`) | NVIDIA proprietary (CUDA Toolkit EULA; redistributable runtime library) | https://pypi.org/project/nvidia-cublas-cu12/ |
| NVIDIA cuDNN 8.9.7.29 (`cudnn64_8.dll`, `cudnn_*_infer64_8.dll`) | NVIDIA proprietary (cuDNN Software License Agreement; redistributable runtime library) | https://pypi.org/project/nvidia-cudnn-cu12/ |
| zlib 1.3.2 (`zlibwapi.dll`, conda-forge `zlib-wapi` build) | zlib license | https://zlib.net, https://anaconda.org/conda-forge/zlib-wapi |

The add-on ships NVIDIA's license texts and the zlib license in `gpu\licenses\`.
The NVIDIA libraries are included unmodified, only as part of Whisper Offline.
