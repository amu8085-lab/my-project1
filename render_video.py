import os, sys, requests, json, subprocess, socket, gc
import urllib3.util.connection as urllib3_cn
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip, CompositeVideoClip, ColorClip, afx, vfx

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

# --- RENDER LOGIC (No Text Overlays) ---
rendered_videos = []
rendered_audios = []
scene_durations = []

for i, scene in enumerate(scenes_data):
    keyword = scene.get('keyword', 'space')
    text_line = scene.get('text', '').strip()
    if not text_line: continue
    
    audio_path = f"audio_{i}.wav"
    temp_txt = f"temp_{i}.txt"
    with open(temp_txt, "w", encoding="utf-8") as f: f.write(text_line)
    
    # Generate Audio
    subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', 'hi-IN-MadhurNeural', '--rate=+10%', '-f', temp_txt, '--write-media', f"raw_a_{i}.mp3"], check=True)
    subprocess.run(['ffmpeg', '-y', '-i', f"raw_a_{i}.mp3", '-ss', '0.2', '-c:a', 'pcm_s16le', audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    dur = AudioFileClip(audio_path).duration
    scene_durations.append(dur)
    
    # Video Fetching
    try:
        res = requests.get(f"https://api.pexels.com/videos/search?query={keyword} space&per_page=1&orientation=landscape", headers={"Authorization": pexels_key}, timeout=10).json()
        vid_url = res['videos'][0]['video_files'][0]['link'] if res.get('videos') else None
        
        if vid_url:
            vid_path = f"raw_vid_{i}.mp4"
            with open(vid_path, "wb") as f: f.write(requests.get(vid_url, timeout=30).content)
            clip = VideoFileClip(vid_path).subclip(0, min(dur, VideoFileClip(vid_path).duration))
            if clip.duration < dur: clip = afx.vfx.loop(clip, duration=dur)
            
            # Pure Visual
            clip = clip.resize(height=1080).crop(x_center=clip.w/2, width=1920, height=1080)
            clip = clip.resize(lambda t: 1.0 + 0.03 * (t / dur)).set_position(('center', 'center'))
            final_scene = CompositeVideoClip([clip], size=(1920, 1080)).set_duration(dur)
            
            scene_filename = f"scene_{i}.mp4"
            final_scene.write_videofile(scene_filename, fps=24, codec="libx264", audio=False, logger=None)
            rendered_videos.append(os.path.abspath(scene_filename))
            rendered_audios.append(os.path.abspath(audio_path))
            
            final_scene.close(); clip.close(); gc.collect()
    except Exception as e: print(f"Scene {i} error: {e}")

# --- MERGE & UPLOAD ---
with open("vid_list.txt", "w") as f:
    for v in rendered_videos: f.write(f"file '{v}'\n")
with open("aud_list.txt", "w") as f:
    for a in rendered_audios: f.write(f"file '{a}'\n")

subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'vid_list.txt', '-c', 'copy', 'merged_video.mp4'], check=True)
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'aud_list.txt', '-c', 'pcm_s16le', 'merged_audio.wav'], check=True)

final_video = VideoFileClip("merged_video.mp4").set_audio(AudioFileClip("merged_audio.wav"))
final_video.write_videofile("final_video.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="2000k", preset="ultrafast")

# --- STRICT URL EXTRACTION ---
video_link = None
try:
    res = requests.post("https://uguu.se/upload.php", files={'files[]': open("final_video.mp4", 'rb')}, timeout=300)
    # Extract URL explicitly
    video_link = res.json()['files'][0]['url']
    print(f"✅ Upload Success: {video_link}")
except Exception as e:
    print(f"❌ Upload failed: {e}")

# --- TELEGRAM BRIDGE (URL FIXED) ---
BOT_TOKEN = "7707041789:AAFB0DUbGlypExkUjxm0qpJC60Cj5HFLd-E"
if video_link:
    msg = f"READY_TO_UPLOAD|{video_link}|{title[:50]}|{thumbnail_prompt[:100]}|{description[:100]}"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": msg[:3990]})
else:
    print("❌ Could not send Telegram alert: video_link is empty.")
