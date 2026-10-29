WHISPER OFFLINE - QUICK START
=============================

Whisper Offline transcribes audio on your own computer. It never uses the
internet: your recordings and transcripts never leave this machine.

1) Double-click WhisperOffline.exe.
   The first time, it adds a "Whisper Offline" icon to your desktop and
   Start menu. After that, launch it from either one.

   If Windows shows "Windows protected your PC", click "More info" and then
   "Run anyway". This only happens the first time.

2) Add audio with "Add Files" or "Add Folder", or put files in the
   DropAudioHere folder before you start the app.

3) Pick a model quality (large = more accurate, medium = faster), then
   click Start.

4) Transcripts appear in the "processed" folder ("Open Output Folder" button).
   The original audio files are moved there too.

Supported file types: .mp3 .mp4 .mpeg .mpga .m4a .wav .webm

Transcript format:
  [00:01:12-00:01:18] SPEAKER_01: Example transcript line

Optional: to save transcripts somewhere else, create a file named
output_path.txt next to WhisperOffline.exe containing one line with the
folder path, for example:  D:\Transcripts

Keep this folder on a local drive with a short path (C:\WhisperOffline is
ideal). If you move the folder, open WhisperOffline.exe from its new place
once and the shortcuts will update. The licenses folder lists the open-source
software and models included in the app.
