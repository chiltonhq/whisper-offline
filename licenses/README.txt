LICENSES
========

Full license texts for the software and AI models bundled in Whisper Offline.
Whisper Offline's own code is MIT-licensed (see LICENSE.txt in this folder).

File                         Applies to
---------------------------  ----------------------------------------------------
MIT-OpenAI-Whisper.txt       Whisper model weights (medium, large-v3) by OpenAI
MIT-faster-whisper.txt       faster-whisper library, and SYSTRAN's CTranslate2
                             conversions of the Whisper models
                             (Systran/faster-whisper-medium, -large-v3)
MIT-CTranslate2.txt          CTranslate2 inference engine
MIT-pyannote-audio.txt       pyannote.audio, pyannote.core, pyannote.pipeline
MIT-pyannote-models.txt      pyannote/speaker-diarization-3.1 and
                             pyannote/segmentation-3.0 models
CC-BY-4.0.txt                pyannote/wespeaker-voxceleb-resnet34-LM model
                             (speaker embeddings, originally from WeSpeaker:
                             https://github.com/wenet-e2e/wespeaker; converted
                             for pyannote by Herve Bredin; used unmodified)
Apache-2.0.txt               SpeechBrain library and the
                             speechbrain/spkrec-ecapa-voxceleb model;
                             PyTorch Lightning; huggingface_hub; tokenizers
BSD-PyTorch.txt              PyTorch
BSD-torchaudio.txt           torchaudio
BSD-PyAV.txt                 PyAV (audio decoding)
BSD-NumPy.txt                NumPy
LGPL-3.0.txt + GPL-3.0.txt   Qt and PySide6 (Qt for Python). The LGPL v3 is a
                             set of additional permissions on top of the GPL v3,
                             so both texts are included.
LGPL-2.1.txt                 FFmpeg libraries (libav*), bundled inside PyAV

packages\                    License files copied from every package in the build
                             environment, including smaller dependencies not
                             listed above, one folder per package:
                               packages\conda\  native libraries (Qt, FFmpeg,
                                                MKL, Intel OpenMP, ...)
                               packages\pip\    Python packages
                             Only present in built copies of the app.

Also bundled: the Intel OpenMP runtime (libiomp5md.dll) from the intel-openmp
package, under the Intel Simplified Software License. Its text is in
packages\conda\intel-openmp-*\ in built copies of the app; see also
https://www.intel.com/content/www/us/en/developer/articles/license/end-user-license-agreement.html

Qt/PySide6 and FFmpeg are shipped as separate, unmodified dynamic libraries
(.dll / .pyd files under _internal\), so you may replace them with your own
compatible builds. Their source code is available at https://www.qt.io and
https://ffmpeg.org.
