WHISPER OFFLINE - QUICK START
=============================

Whisper Offline transcribes audio on your own computer. It never uses the
internet: your recordings and transcripts never leave this machine.

1) Double-click "Start Whisper Offline.bat".
   The first time, it prepares the files (takes about a minute) and puts a
   "Whisper Offline" icon on your desktop. After that, use the desktop icon.

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

Keep this folder on a local drive and away from very long folder paths
(for example C:\WhisperOffline is ideal).
