import os, sys, requests, json, subprocess, time, random
import concurrent.futures

# --- VARIABLES ---
scenes_data = json.loads(os.environ.get('SCENES_DATA', '[]'))
title = os.environ.get('TITLE', 'Deep Space Mystery')
description = os.environ.get('DESCRIPTION', 'Amazing space facts in Hindi.')
thumbnail_prompt = os.environ.get('THUMBNAIL_PROMPT', 'Cinematic space thumbnail')
pexels_key = os.environ.get('PEXELS_API_KEY')
chat_id = os.environ.get('CHAT_ID')
telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')

print(f"DEBUG: Processing {len(scenes_data)} scenes.")

FALLBACK_KEYWORDS = ["deep space universe", "galaxy stars", "milky way night sky", "nebula animation"]

def fetch_pexels_video(keyword):
    queries_to_try = [f"{keyword} space"] + FALLBACK_KEYWORDS
    for query in queries_to_try:
        for attempt in range(3):
            try:
                time.sleep(random.uniform(0.5, 1.5))
                random_page = random.randint(1, 5) 
                # OPTIMIZATION 1: Added &size=medium to stop fetching massive 4K raw files
                url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&page={random_page}&orientation=landscape&size=medium"
                res = requests.get(url, headers={"Authorization": pexels_key}, timeout=10).json()
                
                if res.get('videos') and len(res['videos']) > 0:
                    return random.choice(res['videos'])['video_files'][0]['link']
            except requests.RequestException: 
                continue
    return None

def get_audio_duration(file_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
    try:
        return float(subprocess.check_output(cmd).decode().strip())
    except:
        return 5.0 

# ==========================================
# PHASE 1: RENDER SCENES (STREAMLINED I/O)
# ==========================================
def process_scene(i, scene):
    keyword = scene.get('keyword', 'space')
    text_line = scene.get('text', '').strip()
    if not text_line: 
        return None
    
    scene_filename = os.path.abspath(f"scene_{i}.mp4")
    raw_mp3 = f"raw_a_{i}.mp3"
    temp_txt = f"temp_{i}.txt"
    vid_path = f"raw_vid_{i}.mp4"
    
    try:
        # Generate Text-to-Speech MP3
        with open(temp_txt, "w", encoding="utf-8") as f: 
            f.write(text_line)
        subprocess.run([sys.executable, '-m', 'edge_tts', '--voice', 'hi-IN-MadhurNeural', '--rate=+10%', '-f', temp_txt, '--write-media', raw_mp3], check=True)
        
        # OPTIMIZATION 2: Removed intermediate .wav conversion. Reading duration directly from MP3.
        # Edge-TTS adds a slight delay at the start, we account for 0.2s clipping.
        raw_dur = get_audio_duration(raw_mp3)
        dur = max(1.0, raw_dur - 0.2) 
        fade_out = max(0, dur - 0.5)
        
        vid_url = fetch_pexels_video(keyword)
        
        if vid_url:
            with open(vid_path, "wb") as f: 
                f.write(requests.get(vid_url, timeout=30).content)
                
            # Feed raw MP3 directly into FFmpeg and trim 0.2s on the fly
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-stream_loop', '-1', '-i', vid_path, '-ss', '0.2', '-i', raw_mp3,
                '-filter_complex', f'[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fade=t=in:st=0:d=0.5,fade=t=out:st={fade_out}:d=0.5[v]',
                '-map', '[v]', '-map', '1:a',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', 
                '-c:a', 'aac', '-b:a', '128k', '-pix_fmt', 'yuv420p',
                '-t', str(dur), scene_filename
            ]
        else:
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c=#05050f:s=1920x1080:d={dur}', '-ss', '0.2', '-i', raw_mp3,
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                '-c:a', 'aac', '-b:a', '128k', '-pix_fmt', 'yuv420p',
                '-t', str(dur), scene_filename
            ]
            
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"vid": scene_filename, "aud": raw_mp3, "index": i}
        
    except Exception as e: 
        print(f"Error in scene {i}: {str(e)}")
        return None
        
    finally:
        # Cleanup
        for f in [temp_txt, vid_path]: # raw_mp3 is kept for final merge, deleted later
            if os.path.exists(f): 
                os.remove(f)

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    futures = [executor.submit(process_scene, i, scene) for i, scene in enumerate(scenes_data)]
    for future in concurrent.futures.as_completed(futures):
        res = future.result()
        if res: results.append(res)

results = sorted(results, key=lambda x: x['index'])

with open("vid_list.txt", "w") as f:
    for r in results: f.write(f"file '{r['vid']}'\n")
with open("aud_list.txt", "w") as f:
    for r in results: f.write(f"file '{r['aud']}'\n")

# ==========================================
# PHASE 2: MERGE & BGM
# ==========================================
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'vid_list.txt', '-c', 'copy', 'raw_merged.mp4'], check=True)
# Directly concat MP3s into final audio format
subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', 'aud_list.txt', '-c:a', 'aac', '-b:a', '128k', 'merged_audio.aac'], check=True)

cmd = ['ffmpeg', '-y', '-i', 'raw_merged.mp4', '-i', 'merged_audio.aac']
if os.path.exists("bgm.mp3"):
    cmd += ['-stream_loop', '-1', '-i', 'bgm.mp3', '-filter_complex', '[0:v]eq=contrast=1.1:saturation=1.25,drawtext=text=\'Deep Space Hindi\':fontcolor=white@0.5:fontsize=48:x=w-tw-50:y=h-th-50[vout];[1:a]loudnorm=I=-14:TP=-2:LRA=11[norm_voice];[2:a]volume=0.08[bgm];[norm_voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]', '-map', '[vout]', '-map', '[aout]']
else:
    cmd += ['-filter_complex', '[0:v]eq=contrast=1.1:saturation=1.25,drawtext=text=\'Deep Space Hindi\':fontcolor=white@0.5:fontsize=48:x=w-tw-50:y=h-th-50[vout];[1:a]loudnorm=I=-14:TP=-2:LRA=11[aout]', '-map', '[vout]', '-map', '[aout]']

cmd += ['-c:v', 'libx264', '-crf', '28', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-shortest', 'final_video.mp4']
subprocess.run(cmd, check=True)

# Final MP3 cleanup
for r in results:
    if os.path.exists(r['aud']): os.remove(r['aud'])

# ==========================================
# PHASE 3: MULTI-SERVER UPLOAD 
# ==========================================
video_link = None
for url in ["https://tmpfiles.org/api/v1/upload", "https://litterbox.catbox.moe/resources/internals/api.php"]:
    try:
        files = {'fileToUpload' if "litterbox" in url else 'file': open("final_video.mp4", 'rb')}
        data = {'reqtype': 'fileupload', 'time': '12h'} if "litterbox" in url else None
        res = requests.post(url, files=files, data=data, timeout=600)
        
        if "litterbox" in url and res.status_code == 200 and res.text.startswith("http"): 
            video_link = res.text.strip()
        elif "tmpfiles" in url and res.json().get('status') == 'success': 
            video_link = res.json()['data']['url'].replace('tmpfiles.org/', 'tmpfiles.org/dl/')
            
        if video_link: break
    except Exception as e: 
        print(f"Upload failed for {url}: {str(e)}")
        continue

# ==========================================
# PHASE 4: TELEGRAM NOTIFICATION
# ==========================================
if telegram_token:
    if video_link:
        requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", json={"chat_id": chat_id, "text": f"READY_TO_UPLOAD|{video_link}|{title.replace('|', '')}|{thumbnail_prompt.replace('|', '')}|{description.replace('|', '')}"})
    else:
        requests.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", json={"chat_id": chat_id, "text": f"⚠️ ERROR: Upload fail hua, GitHub Actions check karein."})
else:
    print("CRITICAL WARNING: Telegram token missing. Cannot send notification.")
