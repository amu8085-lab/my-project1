import os, sys, requests, json, subprocess, gc
from moviepy.editor import VideoFileClip, AudioFileClip, ColorClip

# --- VARIABLES ---
scenes_data = json.loads(os.environ.get('SCENES_DATA', '[]'))
title = os.environ.get('TITLE', 'Deep Space Mystery')
description = os.environ.get('DESCRIPTION', 'Amazing space facts in Hindi.')
thumbnail_prompt = os.environ.get('THUMBNAIL_PROMPT', 'Cinematic space thumbnail')
pexels_key = os.environ.get('PEXELS_API_KEY')
chat_id = os.environ.get('CHAT_ID')

rendered_videos = []
rendered_audios = []

# ==========================================
# PHASE 1: RENDER SCENES
# ==========================================
for i, scene in enumerate(scenes_data):
    keyword = scene.get('keyword', 'space')
    text_line = scene.get('text', '').strip()
    if not text_line: continue
    
    audio_path = os.path.abspath(f"audio_{i}.wav")
    scene_filename = os.path.abspath(f"scene_{i}.mp4")
    
    try:
        # TTS Generate
        temp_txt = f"temp_{i}.txt"
        with open(temp_txt, "w", encoding="utf-8") as f: f.write(text_line)
        subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', 'hi-IN-MadhurNeural', '--rate=+10%', '-f', temp_txt, '--write-media', f"raw_a_{i}.mp3"], check=True)
        subprocess.run(['ffmpeg', '-y', '-i', f"raw_a_{i}.mp3", '-ss', '0.2', '-c:a', 'pcm_s16le', audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        dur = AudioFileClip(audio_path).duration
        
        # Fetch Video
        res = requests.get(f"https://api.pexels.com/videos/search?query={keyword} space&per_page=1&orientation=landscape", headers={"Authorization": pexels_key}, timeout=10).json()
        vid_url = res['videos'][0]['video_files'][0]['link'] if res.get('videos') else None
        
        if vid_url:
            vid_path = f"raw_vid_{i}.mp4"
            with open(vid_path, "wb") as f: f.write(requests.get(vid_url, timeout=30).content)
            clip = VideoFileClip(vid_path).subclip(0, min(dur, VideoFileClip(vid_path).duration))
            if clip.duration < dur: clip = clip.loop(duration=dur)
            clip = clip.resize(height=1080).crop(x_center=clip.w/2, width=1920, height=1080)
            clip.write_videofile(scene_filename, fps=24, codec="libx264", audio=False, logger=None)
            clip.close()
        else:
            ColorClip(size=(1920, 1080), color=(0,0,0), duration=dur).write_videofile(scene_filename, fps=24, codec="libx264", audio=False, logger=None)
        
        if os.path.exists(scene_filename):
            rendered_videos.append(scene_filename)
            rendered_audios.append(audio_path)
        
        gc.collect()
        if os.path.exists(temp_txt): os.remove(temp_txt)
            
    except Exception as e: print(f"Error scene {i}: {e}")

# ==========================================
# PHASE 2: MERGE
# ==========================================
if not rendered_videos:
    print("FATAL ERROR: No videos rendered.")
    sys.exit(1)

with open("vid_list.txt", "w") as f:
    for v in rendered_videos: f.write(f"file '{v}'\n")
with open("aud_list.txt", "w") as f:
    for a in rendered_audios: f.write(f"file '{a}'\n")

# Use standard flags correctly
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'vid_list.txt', '-c', 'copy', 'merged_video.mp4'], check=True)
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'aud_list.txt', '-c', 'pcm_s16le', 'merged_audio.wav'], check=True)

# Final Encoding - High Quality for YT
subprocess.run(['ffmpeg', '-y', '-i', 'merged_video.mp4', '-i', 'merged_audio.wav', '-c:v', 'libx264', '-crf', '18', '-c:a', 'aac', '-b:a', '192k', 'final_video.mp4'], check=True)

# ==========================================
# PHASE 3: UPLOAD
# ==========================================
video_link = None
try:
    res = requests.post("https://uguu.se/upload.php", files={'files[]': open("final_video.mp4", 'rb')}, timeout=600)
    video_link = res.json()['files'][0]['url']
except Exception as e: print(f"Upload failed: {e}")

BOT_TOKEN = "8908652813:AAFsVizGGidc-SwVGN2azUr2mgNqA9Civ34"
if video_link:
    msg = f"READY_TO_UPLOAD|{video_link}|{title.replace('|', '')}|{thumbnail_prompt.replace('|', '')}|{description.replace('|', '')}"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": msg[:3990]})
