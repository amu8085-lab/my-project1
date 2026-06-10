import os, sys, json, subprocess, time, random, asyncio
import aiohttp
import edge_tts

# --- VARIABLES ---
scenes_data = json.loads(os.environ.get('SCENES_DATA', '[]'))
title = os.environ.get('TITLE', 'Deep Space Mystery')
description = os.environ.get('DESCRIPTION', 'Amazing space facts in Hindi.')
thumbnail_prompt = os.environ.get('THUMBNAIL_PROMPT', 'Cinematic space thumbnail')
pexels_key = os.environ.get('PEXELS_API_KEY')
chat_id = os.environ.get('CHAT_ID')
telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')

print(f"DEBUG: Processing {len(scenes_data)} scenes async...")

FALLBACK_KEYWORDS = ["deep space universe", "galaxy stars", "milky way night sky", "nebula animation"]

# Use Linux RAM Disk if available for extreme speed, else use current dir
TEMP_DIR = "/dev/shm" if os.path.exists("/dev/shm") else os.getcwd()

async def fetch_pexels_video(session, keyword):
    queries_to_try = [f"{keyword} space"] + FALLBACK_KEYWORDS
    for query in queries_to_try:
        for attempt in range(2):
            try:
                await asyncio.sleep(random.uniform(0.1, 0.5))
                random_page = random.randint(1, 5) 
                url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&page={random_page}&orientation=landscape&size=medium"
                
                async with session.get(url, headers={"Authorization": pexels_key}, timeout=10) as response:
                    if response.status == 200:
                        res = await response.json()
                        if res.get('videos') and len(res['videos']) > 0:
                            return random.choice(res['videos'])['video_files'][0]['link']
                    elif response.status == 429:
                        print("WARNING: Pexels API Rate Limit Hit (429)!")
            except Exception:
                continue
    return None

async def get_audio_duration(file_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except:
        return 5.0 

# ==========================================
# PHASE 1: ASYNC SCENE GENERATION
# ==========================================
async def process_scene(session, i, scene):
    keyword = scene.get('keyword', 'space')
    text_line = scene.get('text', '').strip()
    if not text_line: return None
    
    scene_filename = os.path.join(TEMP_DIR, f"scene_{i}.mp4")
    raw_mp3 = os.path.join(TEMP_DIR, f"raw_a_{i}.mp3")
    vid_path = os.path.join(TEMP_DIR, f"raw_vid_{i}.mp4")
    
    try:
        communicate = edge_tts.Communicate(text_line, "hi-IN-MadhurNeural", rate="+10%")
        await communicate.save(raw_mp3)
        
        raw_dur = await get_audio_duration(raw_mp3)
        dur = max(1.0, raw_dur - 0.2) 
        fade_out = max(0, dur - 0.5)
        
        vid_url = await fetch_pexels_video(session, keyword)
        if vid_url:
            async with session.get(vid_url) as resp:
                if resp.status == 200:
                    with open(vid_path, "wb") as f:
                        f.write(await resp.read())
                        
            # FIX: Added -fflags +genpts to fix video freezing/black screens during loop
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-stream_loop', '-1', '-fflags', '+genpts', '-i', vid_path, '-ss', '0.2', '-i', raw_mp3,
                '-filter_complex', f'[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fade=t=in:st=0:d=0.5,fade=t=out:st={fade_out}:d=0.5[v]',
                '-map', '[v]', '-map', '1:a',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '32', 
                '-c:a', 'aac', '-b:a', '96k', '-pix_fmt', 'yuv420p',
                '-t', str(dur), scene_filename
            ]
        else:
            # Fallback color changed slightly to indicate Pexels API failed
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c=#1a1a2e:s=1920x1080:d={dur}', '-ss', '0.2', '-i', raw_mp3,
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '32',
                '-c:a', 'aac', '-b:a', '96k', '-pix_fmt', 'yuv420p',
                '-t', str(dur), scene_filename
            ]
            
        proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await proc.communicate()
        
        return {"vid": scene_filename, "aud": raw_mp3, "index": i}
        
    except Exception as e: 
        print(f"Error in scene {i}: {str(e)}")
        return None
    finally:
        if os.path.exists(vid_path): os.remove(vid_path)

async def main_pipeline():
    async with aiohttp.ClientSession() as session:
        tasks = [process_scene(session, i, scene) for i, scene in enumerate(scenes_data)]
        results = await asyncio.gather(*tasks)
        
        results = sorted([r for r in results if r], key=lambda x: x['index'])

        vid_list_path = os.path.join(TEMP_DIR, "vid_list.txt")
        aud_list_path = os.path.join(TEMP_DIR, "aud_list.txt")
        
        with open(vid_list_path, "w") as f:
            for r in results: f.write(f"file '{r['vid']}'\n")
        with open(aud_list_path, "w") as f:
            for r in results: f.write(f"file '{r['aud']}'\n")

        raw_merged = os.path.join(TEMP_DIR, 'raw_merged.mp4')
        merged_audio = os.path.join(TEMP_DIR, 'merged_audio.aac')
        final_video = 'final_video.mp4' 
        
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', vid_list_path, '-c', 'copy', raw_merged], check=True)
        subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', aud_list_path, '-c:a', 'aac', '-b:a', '96k', merged_audio], check=True)

        cmd = ['ffmpeg', '-y', '-i', raw_merged, '-i', merged_audio]
        if os.path.exists("bgm.mp3"):
            cmd += ['-stream_loop', '-1', '-i', 'bgm.mp3', '-filter_complex', '[0:v]eq=contrast=1.1:saturation=1.25,drawtext=text=\'Deep Space Hindi\':fontcolor=white@0.5:fontsize=48:x=w-tw-50:y=h-th-50[vout];[1:a]loudnorm=I=-14:TP=-2:LRA=11[norm_voice];[2:a]volume=0.08[bgm];[norm_voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]', '-map', '[vout]', '-map', '[aout]']
        else:
            cmd += ['-filter_complex', '[0:v]eq=contrast=1.1:saturation=1.25,drawtext=text=\'Deep Space Hindi\':fontcolor=white@0.5:fontsize=48:x=w-tw-50:y=h-th-50[vout];[1:a]loudnorm=I=-14:TP=-2:LRA=11[aout]', '-map', '[vout]', '-map', '[aout]']

        cmd += ['-c:v', 'libx264', '-crf', '32', '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k', '-shortest', final_video]
        subprocess.run(cmd, check=True)

        for f in [vid_list_path, aud_list_path, raw_merged, merged_audio] + [r['vid'] for r in results] + [r['aud'] for r in results]:
            if os.path.exists(f): os.remove(f)

        # ==========================================
        # PHASE 3: HYPER-RESILIENT MULTI-SERVER UPLOAD
        # ==========================================
        video_link = None
        
        if not video_link:
            try:
                with open(final_video, 'rb') as f:
                    async with session.put("https://transfer.sh/final_video.mp4", data=f, timeout=600) as resp:
                        if resp.status == 200:
                            text_resp = await resp.text()
                            if text_resp.startswith("http"):
                                video_link = text_resp.strip()
            except Exception as e:
                print(f"Transfer.sh upload failed: {str(e)}")

        if not video_link:
            try:
                with open(final_video, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('file', f, filename='final_video.mp4')
                    async with session.post("https://tmpfiles.org/api/v1/upload", data=data, timeout=600) as resp:
                        if resp.status == 200:
                            try:
                                js = await resp.json()
                                if js.get('status') == 'success':
                                    video_link = js['data']['url'].replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                            except Exception:
                                print("Tmpfiles returned invalid JSON.")
            except Exception as e:
                print(f"Tmpfiles upload failed: {str(e)}")

        if not video_link:
            try:
                with open(final_video, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('reqtype', 'fileupload')
                    data.add_field('time', '12h')
                    data.add_field('fileToUpload', f, filename='final_video.mp4')
                    async with session.post("https://litterbox.catbox.moe/resources/internals/api.php", data=data, timeout=600) as resp:
                        if resp.status == 200:
                            text_resp = await resp.text()
                            if text_resp.startswith("http"):
                                video_link = text_resp.strip()
            except Exception as e:
                print(f"Catbox upload failed: {str(e)}")

        # ==========================================
        # PHASE 4: TELEGRAM NOTIFICATION
        # ==========================================
        if telegram_token:
            if video_link:
                payload = {"chat_id": chat_id, "text": f"READY_TO_UPLOAD|{video_link}|{title.replace('|', '')}|{thumbnail_prompt.replace('|', '')}|{description.replace('|', '')}"}
            else:
                payload = {"chat_id": chat_id, "text": f"⚠️ ERROR: Upload fail hua, GitHub Actions check karein."}
            
            try:
                async with session.post(f"https://api.telegram.org/bot{telegram_token}/sendMessage", json=payload) as resp:
                    resp_text = await resp.text()
                    print(f"\n--- TELEGRAM DEBUG ---")
                    print(f"Status Code: {resp.status}")
                    print(f"Response: {resp_text}")
                    print(f"----------------------\n")
            except Exception as e:
                print(f"CRITICAL: Telegram API error - {str(e)}")
        else:
            print("CRITICAL WARNING: Telegram token missing. Cannot send notification.")

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_pipeline())
