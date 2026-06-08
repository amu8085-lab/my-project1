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

# Helper to fetch video with fallback
def get_video_url(keyword, headers):
    keywords_to_try = [f"{keyword} space", "deep space galaxy", "stars universe"]
    for k in keywords_to_try:
        try:
            res = requests.get(f"https://api.pexels.com/videos/search?query={k}&per_page=1&orientation=landscape", headers=headers, timeout=10).json()
            if res.get('videos'):
                return res['videos'][0]['video_files'][0]['link']
        except: continue
    return None

TARGET_W, TARGET_H = 1920, 1080
headers = {"Authorization": pexels_key}

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
    
    try:
        subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', 'hi-IN-MadhurNeural', '--rate=+10%', '-f', temp_txt, '--write-media', f"raw_a_{i}.mp3"], check=True)
        subprocess.run(['ffmpeg', '-y', '-i', f"raw_a_{i}.mp3", '-ss', '0.2', '-c:a', 'pcm_s16le', audio_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        dur = AudioFileClip(audio_path).duration
        scene_durations.append(dur)
        
        vid_url = get_video_url(keyword, headers)
        
        if vid_url:
            vid_path = f"raw_vid_{i}.mp4"
            with open(vid_path, "wb") as f: f.write(requests.get(vid_url, timeout=30).content)
            
            # IMPROVED RESIZING: Ensure no black bars
            clip = VideoFileClip(vid_path).subclip(0, min(dur, VideoFileClip(vid_path).duration))
            if clip.duration < dur: clip = clip.loop(duration=dur)
            
            # Resize cover mode
            clip = clip.resize(height=TARGET_H)
            if clip.w < TARGET_W: clip = clip.resize(width=TARGET_W)
            clip = clip.crop(x_center=clip.w/2, width=TARGET_W, height=TARGET_H)
            
            zoomed = clip.resize(lambda t: 1.0 + 0.05 * (t / dur)).set_position(('center', 'center'))
            final_scene = CompositeVideoClip([zoomed], size=(TARGET_W, TARGET_H)).set_duration(dur)
            
            scene_filename = f"scene_{i}.mp4"
            final_scene.write_videofile(scene_filename, fps=24, codec="libx264", audio=False, logger=None)
            rendered_videos.append(os.path.abspath(scene_filename))
            final_scene.close(); clip.close()
        else:
            # If still no video found, skip this scene to avoid black screen, but keep audio
            print(f"Skipping video for scene {i}, using audio only.")
            # We create a dummy silent video clip to keep sync
            dummy = ColorClip(size=(TARGET_W, TARGET_H), color=(0,0,0)).set_duration(dur)
            dummy.write_videofile(f"scene_{i}.mp4", fps=24, codec="libx264", audio=False, logger=None)
            rendered_videos.append(os.path.abspath(f"scene_{i}.mp4"))

        rendered_audios.append(os.path.abspath(audio_path))
        gc.collect()
            
    except Exception as e: print(f"Error on scene {i}: {e}")

# ... (Rest of your concatenation and upload code remains same)
