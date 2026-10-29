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

3) Pick a model, then click Start:
     Large  - most accurate (about 1.7x the recording's length on 4 cores)
     Medium - faster, a little less accurate (about 1.4x)

   To get the transcript in English when people speak another language,
   tick "Translate non-English speech to English". It works with either
   model; Large gives the best translations.

4) Transcripts are saved to Documents\Whisper Offline. Click "Open" next to
   "Save transcripts to" to see them, or "Change..." to pick another folder.
   Your original audio files are left where they are (files from
   DropAudioHere are moved into the transcripts folder once done).

Supported file types: .mp3 .mp4 .mpeg .mpga .m4a .wav .webm

Transcript format:
  [00:01:12-00:01:18] SPEAKER_01: Example transcript line

For IT: to set a default save folder for all users, create a file named
output_path.txt next to WhisperOffline.exe containing one line with the
folder path, for example:  D:\Transcripts

Keep this folder on a local drive with a short path (C:\WhisperOffline is
ideal). If you move the folder, open WhisperOffline.exe from its new place
once and the shortcuts will update. The licenses folder lists the open-source
software and models included in the app.
