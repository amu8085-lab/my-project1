import os, sys, requests, json, subprocess, socket, gc
import urllib3.util.connection as urllib3_cn
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip, CompositeVideoClip, ColorClip, afx, vfx

# Force IPv4 to bypass strict server blocks
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

print(f"Total Scenes to render: {len(scenes_data)}")

TARGET_W, TARGET_H = 1920, 1080
headers = {"Authorization": pexels_key}

rendered_videos = []
rendered_audios = []
scene_durations = []

# ==========================================
# PHASE 1: GENERATE ASSETS (NO TEXT)
# ==========================================
for i, scene in enumerate(scenes_data):
    keyword = scene.get('keyword', 'space')
    text_line = scene.get('text', '').strip()
    if not text_line: continue
    
    audio_path = f"audio_{i}.wav"
    temp_txt = f"temp_{i}.txt"
    with open(temp_txt, "w", encoding="utf-8") as f: f.write(text_line)
    
    try:
        # TTS Generate (Madhur Voice)
        subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', 'hi-IN-MadhurNeural', '--rate=+10%', '-f', temp_txt, '--write-media', f"raw_a_{i}.mp3"], check=True)
        # Convert to WAV for perfect sync
        subprocess.run(['ffmpeg', '-y', '-i', f"raw_a_{i}.mp3", '-ss', '0.2', '-c:a', 'pcm_s16le', audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        dur = AudioFileClip(audio_path).duration
        scene_durations.append(dur)
        
        # Pexels Video Fetch
        res = requests.get(f"https://api.pexels.com/videos/search?query={keyword} space&per_page=1&orientation=landscape", headers=headers, timeout=15).json()
        vid_url = res['videos'][0]['video_files'][0]['link'] if res.get('videos') else None
        
        if vid_url:
            vid_path = f"raw_vid_{i}.mp4"
            with open(vid_path, "wb") as f: f.write(requests.get(vid_url, timeout=30).content)
            clip = VideoFileClip(vid_path).subclip(0, min(dur, VideoFileClip(vid_path).duration))
            if clip.duration < dur: clip = afx.vfx.loop(clip, duration=dur)
            
            # Pure Visual (No Text)
            clip = clip.resize(height=TARGET_H).crop(x_center=clip.w/2, width=TARGET_W, height=TARGET_H)
            zoomed = clip.resize(lambda t: 1.0 + 0.03 * (t / dur)).set_position(('center', 'center'))
            overlay = ColorClip(size=(TARGET_W, TARGET_H), color=(0,0,0)).set_opacity(0.15).set_duration(dur)
            final_scene = CompositeVideoClip([zoomed, overlay], size=(TARGET_W, TARGET_H)).set_duration(dur)
            
            scene_filename = f"scene_{i}.mp4"
            final_scene.write_videofile(scene_filename, fps=24, codec="libx264", audio=False, logger=None)
            rendered_videos.append(os.path.abspath(scene_filename))
            rendered_audios.append(os.path.abspath(audio_path))
            
            final_scene.close(); clip.close(); gc.collect()
            
    except Exception as e: print(f"Scene {i} error: {e}")
    if os.path.exists(temp_txt): os.remove(temp_txt)
    if os.path.exists(f"raw_a_{i}.mp3"): os.remove(f"raw_a_{i}.mp3")

# ==========================================
# PHASE 2: MERGE (Perfect Sync)
# ==========================================
with open("vid_list.txt", "w") as f:
    for v in rendered_videos: f.write(f"file '{v}'\n")
with open("aud_list.txt", "w") as f:
    for a in rendered_audios: f.write(f"file '{a}'\n")

subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'vid_list.txt', '-c', 'copy', 'merged_video.mp4'], check=True)
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'aud_list.txt', '-c', 'pcm_s16le', 'merged_audio.wav'], check=True)

final_video = VideoFileClip("merged_video.mp4").set_audio(AudioFileClip("merged_audio.wav"))

# Add BGM
try:
    bgm = AudioFileClip("bgm.mp3").volumex(0.10)
    if bgm.duration < final_video.duration: bgm = afx.audio_loop(bgm, duration=final_video.duration)
    else: bgm = bgm.subclip(0, final_video.duration)
    final_video = final_video.set_audio(CompositeAudioClip([final_video.audio, bgm]))
except: pass

final_video.write_videofile("final_video.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="2000k", preset="ultrafast")

# ==========================================
# PHASE 3: UPLOAD & TELEGRAM
# ==========================================
video_link = None
try:
    res = requests.post("https://uguu.se/upload.php", files={'files[]': open("final_video.mp4", 'rb')}, timeout=600)
    video_link = res.json()['files'][0]['url']
    print(f"✅ Upload Success: {video_link}")
except Exception as e: print(f"❌ Upload failed: {e}")

BOT_TOKEN = "8908652813:AAFsVizGGidc-SwVGN2azUr2mgNqA9Civ34"
if video_link:
    # URL extraction fix ensures this string is just the URL
    msg = f"READY_TO_UPLOAD|{video_link}|{title[:50]}|{thumbnail_prompt[:100]}|{description[:100]}"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": msg[:3990]})
