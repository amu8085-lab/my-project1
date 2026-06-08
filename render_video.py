import os, sys, requests, json, subprocess, socket, gc
import urllib3.util.connection as urllib3_cn
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip, CompositeVideoClip, ColorClip

def allowed_gai_family():
    return socket.AF_INET
urllib3_cn.allowed_gai_family = allowed_gai_family

# --- VARIABLES ---
chat_id = os.environ.get('CHAT_ID')
pexels_key = os.environ.get('PEXELS_API_KEY')
scenes_data = json.loads(os.environ.get('SCENES_DATA', '[]'))
title = os.environ.get('TITLE', 'Deep Space Mystery')
description = os.environ.get('DESCRIPTION', 'Amazing space facts in Hindi.')
thumbnail_prompt = os.environ.get('THUMBNAIL_PROMPT', 'Cinematic space thumbnail')

TARGET_W, TARGET_H = 1920, 1080
headers = {"Authorization": pexels_key}

rendered_videos = []
rendered_audios = []

# ==========================================
# PHASE 1: SMART-MATCH RENDERING
# ==========================================
for i, scene in enumerate(scenes_data):
    # Dynamic Search Query: Keyword + first 30 chars of text for better match
    search_query = f"{scene.get('keyword', 'space')} {scene.get('text', '')[:30]}"
    text_line = scene.get('text', '').strip()
    if not text_line: continue
    
    audio_path = f"audio_{i}.wav"
    temp_txt = f"temp_{i}.txt"
    with open(temp_txt, "w", encoding="utf-8") as f: f.write(text_line)
    
    try:
        # TTS Generate
        subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', 'hi-IN-MadhurNeural', '--rate=+10%', '-f', temp_txt, '--write-media', f"raw_a_{i}.mp3"], check=True)
        subprocess.run(['ffmpeg', '-y', '-i', f"raw_a_{i}.mp3", '-ss', '0.2', '-c:a', 'pcm_s16le', audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        dur = AudioFileClip(audio_path).duration
        
        # Pexels Fetch with Smart Query
        res = requests.get(f"https://api.pexels.com/videos/search?query={search_query}&per_page=1&orientation=landscape", headers=headers, timeout=10).json()
        vid_url = res['videos'][0]['video_files'][0]['link'] if res.get('videos') else None
        
        scene_filename = f"scene_{i}.mp4"
        
        if vid_url:
            vid_path = f"raw_vid_{i}.mp4"
            with open(vid_path, "wb") as f: f.write(requests.get(vid_url, timeout=30).content)
            clip = VideoFileClip(vid_path).subclip(0, min(dur, VideoFileClip(vid_path).duration))
            if clip.duration < dur: clip = clip.loop(duration=dur)
            clip = clip.resize(height=TARGET_H).crop(x_center=clip.w/2, width=TARGET_W, height=TARGET_H)
            
            # Use CRF 18 for visually lossless quality
            clip.write_videofile(scene_filename, fps=24, codec="libx264", audio=False, ffmpeg_params=['-crf', '18'], logger=None)
            clip.close()
        else:
            ColorClip(size=(TARGET_W, TARGET_H), color=(10, 5, 20), duration=dur).write_videofile(scene_filename, fps=24, codec="libx264", audio=False, logger=None)
        
        rendered_videos.append(os.path.abspath(scene_filename))
        rendered_audios.append(os.path.abspath(audio_path))
        gc.collect()
            
    except Exception as e: print(f"Error scene {i}: {e}")

# ==========================================
# PHASE 2: HIGH-BITRATE MERGE
# ==========================================
with open("vid_list.txt", "w") as f:
    for v in rendered_videos: f.write(f"file '{v}'\n")
with open("aud_list.txt", "w") as f:
    for a in rendered_audios: f.write(f"file '{a}'\n")

# Use FFmpeg to merge with high quality settings
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'vid_list.txt', '-c', 'copy', 'merged_video.mp4'], check=True)
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'aud_list.txt', '-c', 'pcm_s16le', 'merged_audio.wav'], check=True)

# Final Encoding with 5000k bitrate
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
