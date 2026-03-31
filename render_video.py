import os, requests, json, subprocess, urllib.parse
import moviepy.editor as mpe
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip, CompositeVideoClip, TextClip, concatenate_videoclips, vfx, afx, ColorClip

HINDI_FONT_FILE = "Hindi.ttf" 

full_text = os.environ.get('FULL_TEXT', 'Ek baar ki baat hai.')
chat_id = os.environ.get('CHAT_ID')
webhook_url = os.environ.get('WEBHOOK_URL')
pexels_key = os.environ.get('PEXELS_API_KEY')
scenes_data = json.loads(os.environ.get('SCENES_DATA', '[]'))
thumbnail_prompt = os.environ.get('THUMBNAIL_PROMPT', 'Abstract mind blowing facts cinematic')
resume_url = os.environ.get('RESUME_URL')

print(f"Total Scenes to render: {len(scenes_data)}")

# 1. AI Voiceover
subprocess.run(['edge-tts', '--voice', 'hi-IN-MadhurNeural', '--text', full_text, '--write-media', 'voiceover.mp3'])
voiceover = AudioFileClip("voiceover.mp3")

total_chars = sum(len(s['text']) for s in scenes_data)
video_clips = []
audio_clips = [voiceover]
headers = {"Authorization": pexels_key}
current_time = 0.0

try:
    whoosh_sfx = AudioFileClip("whoosh.mp3").volumex(0.25)
    pop_sfx = AudioFileClip("pop.mp3").volumex(0.15)       
except:
    whoosh_sfx = pop_sfx = None

viral_colors = ['#FFD400', '#00FFFF', '#FFFFFF', '#39FF14'] 

# CHANGE: Landscape Resolution for Long Form Video
TARGET_W, TARGET_H = 1920, 1080

# 2. Process Each Scene
for i, scene in enumerate(scenes_data):
    keyword = scene.get('keyword', 'nature')
    text_line = scene.get('text', '')
    scene_duration = voiceover.duration * (len(text_line) / max(total_chars, 1))
    if scene_duration < 2.0: scene_duration = 2.0
    
    try:
        # CHANGE: orientation=landscape
        res = requests.get(f"https://api.pexels.com/videos/search?query={keyword}&per_page=1&orientation=landscape", headers=headers).json()
        video_url = res['videos'][0]['video_files'][0]['link']
        
        vid_path = f"vid_{i}.mp4"
        with open(vid_path, "wb") as f:
            f.write(requests.get(video_url).content)
            
        clip = VideoFileClip(vid_path).subclip(0, scene_duration)
        clip = clip.resize(height=TARGET_H)
        if clip.w < TARGET_W:
            clip = clip.resize(width=TARGET_W)
        clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=TARGET_W, height=TARGET_H)
        
        zoomed_clip = clip.resize(lambda t: 1.0 + 0.02 * (t / scene_duration)).set_position(('center', 'center'))
        dark_overlay = ColorClip(size=(TARGET_W, TARGET_H), color=(0,0,0)).set_opacity(0.40).set_position(('center', 'center')).set_duration(scene_duration)
        
        words = text_line.split(' ')
        chunk_size = 4 # Increased chunk size for landscape viewing
        chunks = [' '.join(words[j:j + chunk_size]) for j in range(0, len(words), chunk_size)]
        
        word_clips = []
        duration_per_chunk = scene_duration / len(chunks)
        
        for w_i, chunk in enumerate(chunks):
            current_color = viral_colors[w_i % len(viral_colors)]
            
            # CHANGE: Adjusted font size and width for horizontal layout
            bg_txt = TextClip(chunk, fontsize=90, color='black', font=HINDI_FONT_FILE, stroke_color='black', stroke_width=12, method='caption', size=(1500, None))
            bg_txt = bg_txt.set_position(('center', 'center')).set_duration(duration_per_chunk).set_start(w_i * duration_per_chunk)
            
            main_txt = TextClip(chunk, fontsize=90, color=current_color, font=HINDI_FONT_FILE, stroke_color='black', stroke_width=2, method='caption', size=(1500, None))
            main_txt = main_txt.set_position(('center', 'center')).set_duration(duration_per_chunk).set_start(w_i * duration_per_chunk)
            
            word_clips.extend([bg_txt, main_txt])
        
        final_scene = CompositeVideoClip([zoomed_clip, dark_overlay] + word_clips, size=(TARGET_W, TARGET_H)).set_duration(scene_duration)
        if i > 0: final_scene = final_scene.crossfadein(0.5)
            
        video_clips.append(final_scene)
        
        if whoosh_sfx: audio_clips.append(whoosh_sfx.set_start(current_time))
        if pop_sfx: audio_clips.append(pop_sfx.set_start(current_time + 0.1))
                
        current_time += scene_duration
        print(f"Scene {i+1} Ready: {keyword}")
    except Exception as e:
        print(f"Error on scene {i}: {e}")

final_video = concatenate_videoclips(video_clips, padding=-0.5, method="compose")

try:
    bgm = AudioFileClip("bgm.mp3").volumex(0.08)
    if bgm.duration < final_video.duration: bgm = afx.audio_loop(bgm, duration=final_video.duration)
    else: bgm = bgm.subclip(0, final_video.duration)
    audio_clips.append(bgm)
except: pass

final_audio = CompositeAudioClip(audio_clips)
final_video = final_video.set_audio(final_audio)

print("Rendering Final LONG Video...")
final_video.write_videofile("final_video.mp4", fps=24, codec="libx264", audio_codec="aac", threads=2)

# --- THUMBNAIL GENERATION ---
print("Generating AI Thumbnail...")
try:
    encoded_thumb = urllib.parse.quote(thumbnail_prompt + ", youtube thumbnail, vibrant, cinematic lighting, ultra high resolution")
    thumb_url = f"https://image.pollinations.ai/prompt/{encoded_thumb}?width=1920&height=1080&nologo=true"
    with open("thumbnail.jpg", "wb") as f:
        f.write(requests.get(thumb_url).content)
    
    files_thumb = {'reqtype': (None, 'fileupload'), 'fileToUpload': open('thumbnail.jpg', 'rb')}
    uploaded_thumb_link = requests.post("https://catbox.moe/user/api.php", files=files_thumb).text.strip()
except Exception as e:
    print(f"Thumbnail error: {e}")
    uploaded_thumb_link = "Failed"

# --- VIDEO UPLOAD ---
try:
    files = {'reqtype': (None, 'fileupload'), 'fileToUpload': open('final_video.mp4', 'rb')}
    video_link = requests.post("https://catbox.moe/user/api.php", files=files).text.strip()
except: 
    video_link = "Upload Failed"

payload = {
    "chat_id": chat_id, 
    "message": "👑 Bhai! Long Video Ready! 🔥", 
    "youtube_url": video_link,
    "thumbnail_url": uploaded_thumb_link
}

if resume_url:
    try:
        requests.post(resume_url, json={"body": payload}, timeout=15)
    except Exception as e:
        print(f"Warning: Failed to resume n8n. Error: {e}")
