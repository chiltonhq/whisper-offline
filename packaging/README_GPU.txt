WHISPER OFFLINE - NVIDIA GPU ADD-ON
===================================

This add-on lets Whisper Offline transcribe on an NVIDIA graphics card, which
is usually several times faster than the CPU. It is optional: without it the
app works exactly the same, just on the CPU.

Requirements
  - An NVIDIA graphics card (GeForce GTX 900 series or newer, or an NVIDIA
    workstation card from the same era or newer)
  - An NVIDIA graphics driver, version 527 or newer (the latest driver is
    recommended). Get it from https://www.nvidia.com/drivers or through
    Windows Update.
  - You do not need to install CUDA; everything it needs is in this folder.

Install
  1) Close Whisper Offline.
  2) Move this "gpu" folder into your WhisperOffline folder, next to
     WhisperOffline.exe:

       WhisperOffline\
         WhisperOffline.exe
         gpu\              <- this folder
         ...

  3) Start Whisper Offline. The top right of the window should say
     "Runs on: NVIDIA GPU".

If it still says "Runs on: CPU", click Start on a file and read the first
lines of the progress log: they explain why the GPU isn't being used (for
example, no NVIDIA driver found). The app always falls back to the CPU, so
nothing breaks.

Notes
  - The GPU speeds up the speech-to-text step. Speaker detection still runs
    on the CPU.
  - To remove the add-on, delete the gpu folder.
  - Works fully offline, like the rest of the app.

The licenses folder contains NVIDIA's license terms for cuBLAS and cuDNN
and the zlib license for zlibwapi.dll.
