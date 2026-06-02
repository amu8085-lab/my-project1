import os, requests, json, subprocess, socket, time, gc
import moviepy.editor as mpe
import urllib3.util.connection as urllib3_cn
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip, CompositeVideoClip, TextClip, vfx, afx, ColorClip

# 🛡️ HACKER TRICK: Disabled IPv4 override to allow natural Hostinger routing (IPv6/IPv4)
# def allowed_gai_family():
#     return socket.AF_INET
# urllib3_cn.allowed_gai_family = allowed_gai_family

# Font is no longer strictly needed since text is removed, but kept to avoid breaking missing variables
HINDI_FONT_FILE = "Hindi.ttf" 

full_text = os.environ.get('FULL_TEXT', 'Ek baar ki baat hai.')
chat_id = os.environ.get('CHAT_ID')
webhook_url = os.environ.get('WEBHOOK_URL')
pexels_key = os.environ.get('PEXELS_API_KEY')
scenes_data = json.loads(os.environ.get('SCENES_DATA', '[]'))
resume_url = os.environ.get('RESUME_URL')

print(f"Total Scenes to render: {len(scenes_data)}")

# Generate Voiceover
subprocess.run(['edge-tts', '--voice', 'hi-IN-MadhurNeural', '--text', full_text, '--write-media', 'voiceover.mp3'])

# --- FIX START: Audio Sync Problem Fix ---
raw_voiceover = AudioFileClip("voiceover.mp3")
if raw_voiceover.duration > 1.0:
    voiceover = raw_voiceover.subclip(0.3)
else:
    voiceover = raw_voiceover
# --- FIX END ---

total_chars = sum(len(s['text']) for s in scenes_data)
audio_clips = [voiceover]
headers = {"Authorization": pexels_key}
current_time = 0.0

try:
    whoosh_sfx = AudioFileClip("whoosh.mp3").volumex(0.25)
    pop_sfx = AudioFileClip("pop.mp3").volumex(0.15)       
except:
    whoosh_sfx = pop_sfx = None

TARGET_W, TARGET_H = 1920, 1080

rendered_scene_files = []
raw_downloads = []

# ==========================================
# PHASE 1: RENDER INDIVIDUAL SCENES TO DISK
# ==========================================
for i, scene in enumerate(scenes_data):
    keyword = scene.get('keyword', 'nature')
    text_line = scene.get('text', '')
    scene_duration = voiceover.duration * (len(text_line) / max(total_chars, 1))
    if scene_duration < 1.0: scene_duration = 1.0
    
    try:
        # FIX 1: Add a delay to prevent Pexels API rate limits (429 Too Many Requests)
        time.sleep(1.5)
        
        # Fetch Pexels Video safely
        res_data = requests.get(f"https://api.pexels.com/videos/search?query={keyword}&per_page=1&orientation=landscape", headers=headers)
        
        # FIX 2: Safely handle missing videos or API blocks so audio doesn't desync
        if res_data.status_code != 200:
            print(f"Pexels API Error for '{keyword}': {res_data.status_code}. Using fallback background.")
            clip = ColorClip(size=(TARGET_W, TARGET_H), color=(20, 20, 30)).set_duration(scene_duration)
        else:
            res = res_data.json()
            if not res.get('videos'):
                print(f"No videos found for keyword: {keyword}. Using fallback background.")
                clip = ColorClip(size=(TARGET_W, TARGET_H), color=(20, 20, 30)).set_duration(scene_duration)
            else:
                video_url = res['videos'][0]['video_files'][0]['link']
                vid_path = f"raw_vid_{i}.mp4"
                
                with open(vid_path, "wb") as f:
                    f.write(requests.get(video_url).content)
                raw_downloads.append(vid_path)
                    
                clip = VideoFileClip(vid_path).subclip(0, scene_duration)
                clip = clip.resize(height=TARGET_H)
                if clip.w < TARGET_W:
                    clip = clip.resize(width=TARGET_W)
                clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=TARGET_W, height=TARGET_H)
        
        # Static Zoom to save memory
        zoomed_clip = clip.resize(1.04).set_position(('center', 'center'))
        
        # REMOVED: TextClip generation and dark_overlay code are completely removed here.
        # Now we only render the zoomed background clip.
        final_scene = CompositeVideoClip([zoomed_clip], size=(TARGET_W, TARGET_H)).set_duration(scene_duration)
        
        # Save to disk immediately
        scene_filename = f"rendered_scene_{i}.mp4"
        final_scene.write_videofile(scene_filename, fps=24, codec="libx264", audio_codec="aac", preset="ultrafast", logger=None)
        rendered_scene_files.append(scene_filename)
        
        # Free Memory to prevent GitHub Actions OOM crash
        final_scene.close()
        zoomed_clip.close()
        clip.close()
            
        # FIX 3: Force garbage collection after every single scene
        gc.collect()
        
        # Collect Audio Timing
        if whoosh_sfx: audio_clips.append(whoosh_sfx.set_start(current_time))
        if pop_sfx: audio_clips.append(pop_sfx.set_start(current_time + 0.1))
                
        current_time += scene_duration
        print(f"Scene {i+1} Rendered to Disk: {keyword}")
        
    except Exception as e:
        print(f"Error on scene {i}: {e}")
        # Ensure audio timeline keeps advancing even if a chunk critically fails
        current_time += scene_duration

# ==========================================
# PHASE 2: INSTANT FFMPEG CONCATENATION
# ==========================================
print("Stitching all scenes instantly using FFmpeg Stream Copy...")
with open("concat_list.txt", "w") as f:
    for file in rendered_scene_files:
        f.write(f"file '{os.path.abspath(file)}'\n")

# This merges all MP4 chunks in seconds without re-encoding
subprocess.run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat_list.txt",
    "-c", "copy", "raw_final.mp4"
], check=True)

# ==========================================
# PHASE 3: FINAL TOUCHES (PROGRESS BAR & AUDIO)
# ==========================================
print("Adding Progress Bar and Final Audio Mix...")
final_video = VideoFileClip("raw_final.mp4")

final_duration = final_video.duration
progress_bar = ColorClip(size=(TARGET_W, 15), color=(255, 0, 0))
progress_bar = progress_bar.set_position(lambda t: (-TARGET_W + int(TARGET_W * (t / max(final_duration, 1))), 'bottom'))
progress_bar = progress_bar.set_duration(final_duration)
final_video = CompositeVideoClip([final_video, progress_bar])

try:
    bgm = AudioFileClip("bgm.mp3").volumex(0.10)
    if bgm.duration < final_video.duration: bgm = afx.audio_loop(bgm, duration=final_video.duration)
    else: bgm = bgm.subclip(0, final_video.duration)
    audio_clips.append(bgm)
except: pass

final_audio = CompositeAudioClip(audio_clips)
final_video = final_video.set_audio(final_audio)

print("Rendering Final Outpost Video...")
final_video.write_videofile("final_video.mp4", fps=24, codec="libx264", audio_codec="aac", threads=2, bitrate="1000k", preset="ultrafast")

# Cleanup
for f in rendered_scene_files + raw_downloads + ["concat_list.txt", "raw_final.mp4"]:
    try:
        os.remove(f)
    except: pass

# ==========================================
# PHASE 4: MULTI-LAYER UPLOAD SYSTEM
# ==========================================
print("Starting 5-Layer Indestructible Upload System...")
video_link = "Upload Failed"

if not video_link.startswith("http"):
    try:
        print("Trying 0x0.st API...")
        res = requests.post("https://0x0.st", files={'file': open('final_video.mp4', 'rb')}, timeout=600)
        if res.text.startswith("http"): video_link = res.text.strip()
    except Exception as e: print(f"0x0.st failed: {e}")

if not video_link.startswith("http"):
    try:
        print("Trying Uguu.se API...")
        res = requests.post("https://uguu.se/upload.php", files={'files[]': open('final_video.mp4', 'rb')}, timeout=600)
        if res.status_code == 200: video_link = res.json()['files'][0]['url']
    except Exception as e: print(f"Uguu.se failed: {e}")

if not video_link.startswith("http"):
    try:
        print("Trying Tmpfiles API...")
        res = requests.post("https://tmpfiles.org/api/v1/upload", files={'file': open('final_video.mp4', 'rb')}, timeout=600)
        if res.status_code == 200: video_link = res.json()['data']['url'].replace('tmpfiles.org/', 'tmpfiles.org/dl/')
    except Exception as e: print(f"Tmpfiles failed: {e}")

if not video_link.startswith("http"):
    try:
        print("Trying Catbox API...")
        res = requests.post("https://catbox.moe/user/api.php", data={'reqtype': 'fileupload'}, files={'fileToUpload': open('final_video.mp4', 'rb')}, timeout=600)
        if res.text.startswith("http"): video_link = res.text.strip()
    except Exception as e: print(f"Catbox failed: {e}")

print(f"🔥 FINAL YOUTUBE LINK: {video_link} 🔥")

payload = {
    "chat_id": chat_id, 
    "message": "👑 Bhai! 100M+ Views Long Video Ready! 🔥", 
    "youtube_url": video_link
}

safe_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

if resume_url:
    print(f"Resuming n8n workflow at: {resume_url}")
    try:
        response = requests.post(resume_url, json={"body": payload}, headers=safe_headers, timeout=60)
        print(f"n8n Resume Response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Warning: Failed to resume n8n. Error: {e}")
else:
    print("No RESUME_URL provided by n8n.")
