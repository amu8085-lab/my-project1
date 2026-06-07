import os, sys, requests, json, subprocess, socket, gc
import urllib3.util.connection as urllib3_cn
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip, CompositeVideoClip, ColorClip, afx, vfx

# Force IPv4
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

print(f"Total Scenes: {len(scenes_data)}")

TARGET_W, TARGET_H = 1920, 1080
headers = {"Authorization": pexels_key}

rendered_videos = []
rendered_audios = []
scene_durations = []

# ==========================================
# PHASE 1: GENERATE ASSETS WITHOUT TEXT
# ==========================================
for i, scene in enumerate(scenes_data):
    keyword = scene.get('keyword', 'space')
    text_line = scene.get('text', '').strip()
    if not text_line: continue
    
    # Generate Madhur Voice (No overlap fix: WAV format)
    audio_path = f"audio_{i}.wav"
    temp_txt = f"temp_{i}.txt"
    with open(temp_txt, "w", encoding="utf-8") as f: f.write(text_line)
    
    subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', 'hi-IN-MadhurNeural', '--rate=+10%', '-f', temp_txt, '--write-media', audio_path], check=True)
    
    # Get exact duration of audio
    clip_audio = AudioFileClip(audio_path)
    dur = clip_audio.duration
    clip_audio.close()
    scene_durations.append(dur)
    
    # Pexels Video
    try:
        res = requests.get(f"https://api.pexels.com/videos/search?query={keyword} space&per_page=1&orientation=landscape", headers=headers, timeout=10).json()
        vid_url = res['videos'][0]['video_files'][0]['link'] if res.get('videos') else "https://www.pexels.com/" 
        # (Add fallback logic if needed)
        
        vid_path = f"raw_vid_{i}.mp4"
        with open(vid_path, "wb") as f: f.write(requests.get(vid_url).content)
        
        clip = VideoFileClip(vid_path).subclip(0, min(dur, VideoFileClip(vid_path).duration))
        if clip.duration < dur: clip = afx.vfx.loop(clip, duration=dur)
        
        # Pure Visual (No Text)
        clip = clip.resize(height=TARGET_H).crop(x_center=clip.w/2, width=TARGET_W, height=TARGET_H)
        clip = clip.resize(lambda t: 1.0 + 0.02 * (t / dur)) # Subtle zoom
        
        scene_filename = f"scene_{i}.mp4"
        clip.write_videofile(scene_filename, fps=24, codec="libx264", audio=False, logger=None)
        
        rendered_videos.append(scene_filename)
        rendered_audios.append(audio_path)
        
        clip.close()
        gc.collect()
    except Exception as e: print(f"Scene {i} error: {e}")
    if os.path.exists(temp_txt): os.remove(temp_txt)

# ==========================================
# PHASE 2: SAMPLE-ACCURATE CONCATENATION
# ==========================================
with open("vid_list.txt", "w") as f:
    for v in rendered_videos: f.write(f"file '{v}'\n")
with open("aud_list.txt", "w") as f:
    for a in rendered_audios: f.write(f"file '{a}'\n")

# Merge using FFmpeg (No Sync Drift)
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'vid_list.txt', '-c', 'copy', 'merged_video.mp4'])
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'aud_list.txt', '-c', 'pcm_s16le', 'merged_audio.wav'])

final_video = VideoFileClip("merged_video.mp4")
final_audio = AudioFileClip("merged_audio.wav")

# Add BGM
try:
    bgm = AudioFileClip("bgm.mp3").volumex(0.08)
    if bgm.duration < final_video.duration: bgm = afx.audio_loop(bgm, duration=final_video.duration)
    else: bgm = bgm.subclip(0, final_video.duration)
    final_audio = CompositeAudioClip([final_audio, bgm])
except: pass

final_video = final_video.set_audio(final_audio)
final_video.write_videofile("final_video.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="2000k", preset="ultrafast")

# ==========================================
# UPLOAD & TELEGRAM
# ==========================================
# (Keep your existing Upload Logic from previous script here)
# ... [Upload Logic Same as previous] ...

# TELEGRAM BRIDGE (Fixed Message Length)
BOT_TOKEN = "7707041789:AAFB0DUbGlypExkUjxm0qpJC60Cj5HFLd-E"
message_text = f"READY_TO_UPLOAD|{video_link}|{title[:50]}|{thumbnail_prompt[:100]}|{description[:100]}"
requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": message_text})
