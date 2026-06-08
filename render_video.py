import os, sys, requests, json, subprocess, gc
from moviepy.editor import VideoFileClip, AudioFileClip, ColorClip

# --- SETTINGS ---
chat_id = os.environ.get('CHAT_ID')
pexels_key = os.environ.get('PEXELS_API_KEY')
scenes_data = json.loads(os.environ.get('SCENES_DATA', '[]'))
title = os.environ.get('TITLE', 'Deep Space Mystery')
description = os.environ.get('DESCRIPTION', 'Amazing space facts in Hindi.')
thumbnail_prompt = os.environ.get('THUMBNAIL_PROMPT', 'Cinematic space thumbnail')

# Normalize parameters for perfect sync
TARGET_W, TARGET_H = 1920, 1080
FFMPEG_PARAMS = ['-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '24']

rendered_videos = []
rendered_audios = []

# ==========================================
# PHASE 1: RENDER SCENES (Sync-Locked)
# ==========================================
for i, scene in enumerate(scenes_data):
    search_query = f"{scene.get('keyword', 'space')} {scene.get('text', '')[:40]}"
    text_line = scene.get('text', '').strip()
    if not text_line: continue
    
    audio_path = os.path.abspath(f"audio_{i}.wav")
    scene_filename = os.path.abspath(f"scene_{i}.mp4")
    
    try:
        # 1. Generate Audio
        temp_txt = f"temp_{i}.txt"
        with open(temp_txt, "w", encoding="utf-8") as f: f.write(text_line)
        subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', 'hi-IN-MadhurNeural', '--rate=+10%', '-f', temp_txt, '--write-media', f"temp_a_{i}.mp3"], check=True)
        subprocess.run(['ffmpeg', '-y', '-i', f"temp_a_{i}.mp3", '-ar', '44100', '-ac', '2', '-c:a', 'pcm_s16le', audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        dur = AudioFileClip(audio_path).duration
        
        # 2. Fetch Video
        res = requests.get(f"https://api.pexels.com/videos/search?query={search_query}&per_page=1&orientation=landscape", headers={"Authorization": pexels_key}, timeout=10).json()
        vid_url = res['videos'][0]['video_files'][0]['link'] if res.get('videos') else None
        
        if vid_url:
            vid_path = f"raw_{i}.mp4"
            with open(vid_path, "wb") as f: f.write(requests.get(vid_url, timeout=30).content)
            
            # Clip processing with strict FPS and resolution
            clip = VideoFileClip(vid_path).subclip(0, min(dur, VideoFileClip(vid_path).duration))
            if clip.duration < dur: clip = clip.loop(duration=dur)
            
            # Force Sync: Resize/Crop to 1080p and 24fps
            clip = clip.resize(height=TARGET_H).crop(x_center=clip.w/2, width=TARGET_W, height=TARGET_H)
            clip.write_videofile(scene_filename, fps=24, codec="libx264", audio=False, ffmpeg_params=FFMPEG_PARAMS, logger=None)
            clip.close()
        else:
            # Fallback
            ColorClip(size=(TARGET_W, TARGET_H), color=(5, 5, 10), duration=dur).write_videofile(scene_filename, fps=24, codec="libx264", audio=False, ffmpeg_params=FFMPEG_PARAMS, logger=None)
        
        rendered_videos.append(scene_filename)
        rendered_audios.append(audio_path)
        gc.collect()
            
    except Exception as e: print(f"Error scene {i}: {e}")

# ==========================================
# PHASE 2: MERGE (Precise Alignment)
# ==========================================
with open("vid_list.txt", "w") as f:
    for v in rendered_videos: f.write(f"file '{v}'\n")

# Use FFmpeg to merge video first
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'vid_list.txt', '-c', 'copy', 'merged_video.mp4'], check=True)

# Combine with Audio (Use filter_complex to ensure audio maps to merged video)
# We create a single audio file from all parts first to avoid gaps
with open("aud_list.txt", "w") as f:
    for a in rendered_audios: f.write(f"file '{a}'\n")
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'aud_list.txt', '-c', 'pcm_s16le', 'merged_audio.wav'], check=True)

# Final Render
subprocess.run(['ffmpeg', '-y', '-i', 'merged_video.mp4', '-i', 'merged_audio.wav', '-c:v', 'libx264', '-crf', '18', '-c:a', 'aac', '-b:a', '192k', 'final_video.mp4'], check=True)

# ==========================================
# PHASE 3: UPLOAD
# ==========================================
video_link = None
try:
    res = requests.post("https://uguu.se/upload.php", files={'files[]': open("final_video.mp4", 'rb')}, timeout=600)
    video_link = res.json()['files'][0]['url']
except: pass

BOT_TOKEN = "8908652813:AAFsVizGGidc-SwVGN2azUr2mgNqA9Civ34"
if video_link:
    msg = f"READY_TO_UPLOAD|{video_link}|{title.replace('|', '')}|{thumbnail_prompt.replace('|', '')}|{description.replace('|', '')}"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": msg[:3990]})
