import os, sys, json, subprocess, time, random, asyncio, re
import aiohttp
import edge_tts

# --- VARIABLES ---
scenes_data = json.loads(os.environ.get('SCENES_DATA', '[]'))
title = os.environ.get('TITLE', 'Universal Video')
description = os.environ.get('DESCRIPTION', 'Amazing facts.')
thumbnail_prompt = os.environ.get('THUMBNAIL_PROMPT', 'Cinematic thumbnail')
pexels_key = os.environ.get('PEXELS_API_KEY')
chat_id = os.environ.get('CHAT_ID')
telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')

# 👇 YAHAN CHANNEL NAME UPDATE KAR DIYA GAYA HAI 👇
channel_name = "Deep Space" 

print(f"DEBUG: Processing {len(scenes_data)} scenes async...")

# Universal fallbacks
FALLBACK_KEYWORDS = ["abstract motion background", "technology concept", "smartphone interface", "digital data animation", "smooth gradient"]

TEMP_DIR = "/dev/shm" if os.path.exists("/dev/shm") else os.getcwd()

async def fetch_pexels_video(session, keyword):
    queries_to_try = [keyword] + FALLBACK_KEYWORDS
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

async def process_scene(session, i, scene):
    keyword = scene.get('keyword', 'abstract')
    text_line = scene.get('text', '').strip()
    if not text_line: return None
    
    scene_filename = os.path.join(TEMP_DIR, f"scene_{i}.mp4")
    raw_mp3 = os.path.join(TEMP_DIR, f"raw_a_{i}.mp3")
    vid_path = os.path.join(TEMP_DIR, f"raw_vid_{i}.mp4")
    
    try:
        tts_success = False
        for attempt in range(3):
            try:
                communicate = edge_tts.Communicate(text_line, "hi-IN-MadhurNeural", rate="+10%")
                await asyncio.wait_for(communicate.save(raw_mp3), timeout=15.0)
                tts_success = True
                break
            except asyncio.TimeoutError:
                print(f"TTS Timeout on attempt {attempt+1} for scene {i}. Retrying...")
            except Exception as e:
                print(f"TTS Attempt {attempt+1} failed for scene {i}: {str(e)}")
                await asyncio.sleep(2)
                
        if not tts_success:
            print(f"Skipping scene {i} due to continuous TTS failure.")
            return None
            
        raw_dur = await get_audio_duration(raw_mp3)
        dur = max(1.0, raw_dur - 0.2) 
        fade_out = max(0, dur - 0.5)
        
        vid_url = await fetch_pexels_video(session, keyword)
        is_valid_video = False
        
        if vid_url:
            try:
                async with session.get(vid_url, timeout=15) as resp:
                    if resp.status == 200:
                        vid_bytes = await resp.read()
                        if len(vid_bytes) > 50000: 
                            with open(vid_path, "wb") as f:
                                f.write(vid_bytes)
                            is_valid_video = True
            except Exception as e:
                print(f"Failed to download video for scene {i}: {str(e)}")

        if is_valid_video:
            filter_str = f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,format=yuv420p,fps=24,eq=contrast=1.1:saturation=1.25,drawtext=text='{channel_name}':fontcolor=white@0.5:fontsize=48:x=w-tw-50:y=h-th-50,fade=t=in:st=0:d=0.5,fade=t=out:st={fade_out}:d=0.5[v]"
            ffmpeg_cmd = [
                'ffmpeg', '-y', 
                '-ignore_editlist', '1', 
                '-stream_loop', '-1', 
                '-fflags', '+genpts', 
                '-i', vid_path, 
                '-ss', '0.2', 
                '-i', raw_mp3,
                '-filter_complex', filter_str,
                '-map', '[v]', '-map', '1:a',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '32', 
                '-c:a', 'aac', '-b:a', '96k', '-pix_fmt', 'yuv420p',
                '-t', str(dur), scene_filename
            ]
        else:
            filter_str = f"[0:v]drawtext=text='{channel_name}':fontcolor=white@0.5:fontsize=48:x=w-tw-50:y=h-th-50,fade=t=in:st=0:d=0.5,fade=t=out:st={fade_out}:d=0.5[v]"
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-f', 'lavfi', '-i', f'color=c=#151525:s=1920x1080:d={dur}', '-ss', '0.2', '-i', raw_mp3,
                '-filter_complex', filter_str,
                '-map', '[v]', '-map', '1:a',
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

async def run_ffmpeg_async(cmd):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await proc.communicate()

async def main_pipeline():
    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(4)
        
        async def safe_process(session, i, scene):
            async with sem:
                return await process_scene(session, i, scene)

        tasks = [safe_process(session, i, scene) for i, scene in enumerate(scenes_data)]
        results = await asyncio.gather(*tasks)
        
        results = sorted([r for r in results if r], key=lambda x: x['index'])

        vid_list_path = os.path.join(TEMP_DIR, "vid_list.txt")
        aud_list_path = os.path.join(TEMP_DIR, "aud_list.txt")
        
        with open(vid_list_path, "w") as f:
            for r in results: f.write(f"file '{r['vid']}'\n")
        with open(aud_list_path, "w") as f:
            for r in results: f.write(f"file '{r['aud']}'\n")

        raw_video = os.path.join(TEMP_DIR, 'raw_video.mp4')
        raw_voice = os.path.join(TEMP_DIR, 'raw_voice.aac')
        final_audio = os.path.join(TEMP_DIR, 'final_audio.aac')
        final_video = 'final_video.mp4' 
        
        # ==========================================
        # PHASE 2: "ZERO-RENDER" MUXING
        # ==========================================
        await run_ffmpeg_async(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', vid_list_path, '-c', 'copy', raw_video])
        await run_ffmpeg_async(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', aud_list_path, '-c:a', 'aac', '-b:a', '96k', raw_voice])

        if os.path.exists("bgm.mp3"):
            bgm_cmd = [
                'ffmpeg', '-y', '-i', raw_voice, '-stream_loop', '-1', '-i', 'bgm.mp3',
                '-filter_complex', '[0:a]loudnorm=I=-14:TP=-2:LRA=11[norm_voice];[1:a]volume=0.08[bgm];[norm_voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]',
                '-map', '[aout]', '-c:a', 'aac', '-b:a', '96k', final_audio
            ]
        else:
            bgm_cmd = [
                'ffmpeg', '-y', '-i', raw_voice,
                '-filter_complex', '[0:a]loudnorm=I=-14:TP=-2:LRA=11[aout]',
                '-map', '[aout]', '-c:a', 'aac', '-b:a', '96k', final_audio
            ]
        await run_ffmpeg_async(bgm_cmd)

        await run_ffmpeg_async(['ffmpeg', '-y', '-i', raw_video, '-i', final_audio, '-c:v', 'copy', '-c:a', 'copy', '-shortest', final_video])

        for f in [vid_list_path, aud_list_path, raw_video, raw_voice, final_audio] + [r['vid'] for r in results] + [r['aud'] for r in results]:
            if os.path.exists(f): os.remove(f)

        # ==========================================
        # PHASE 3: THE "ANTI-BLOCK" cURL UPLOAD
        # ==========================================
        video_link = None
        
        if not video_link:
            try:
                print("Trying Catbox.moe...")
                proc = await asyncio.create_subprocess_exec(
                    'curl', '-s', '-F', 'reqtype=fileupload', '-F', f'fileToUpload=@{final_video}', 'https://catbox.moe/user/api.php',
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                out_text = stdout.decode().strip()
                
                if out_text.startswith("http"):
                    video_link = out_text
                else:
                    print(f"Catbox API Error/Rejected: {out_text}")
            except Exception as e:
                print(f"Catbox error: {str(e)}")

        if not video_link:
            try:
                print("Trying Litterbox...")
                proc = await asyncio.create_subprocess_exec(
                    'curl', '-s', '-F', 'reqtype=fileupload', '-F', 'time=12h', '-F', f'fileToUpload=@{final_video}', 'https://litterbox.catbox.moe/resources/internals/api.php',
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                out_text = stdout.decode().strip()
                
                if out_text.startswith("http"):
                    video_link = out_text
                else:
                    print(f"Litterbox API Error/Rejected: {out_text}")
            except Exception as e:
                print(f"Litterbox error: {str(e)}")

        if not video_link:
            try:
                print("Trying tmpfiles.org...")
                proc = await asyncio.create_subprocess_exec(
                    'curl', '-s', '-F', f'file=@{final_video}', 'https://tmpfiles.org/api/v1/upload',
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                out_text = stdout.decode().strip()
                
                try:
                    js = json.loads(out_text)
                    if js.get('status') == 'success':
                        video_link = js['data']['url'].replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                    else:
                        print(f"Tmpfiles API Error: {out_text}")
                except Exception:
                    print(f"Tmpfiles invalid response (Cloudflare block?): {out_text}")
            except Exception as e:
                print(f"Tmpfiles error: {str(e)}")

        # ==========================================
        # PHASE 4: TELEGRAM NOTIFICATION
        # ==========================================
        if telegram_token:
            if video_link:
                payload = {"chat_id": chat_id, "text": f"READY_TO_UPLOAD|{video_link}|{title.replace('|', '')}|{thumbnail_prompt.replace('|', '')}|{description.replace('|', '')}"}
            else:
                payload = {"chat_id": chat_id, "text": f"⚠️ ERROR: Upload fail hua. Sabhi file hosts ne IP block kar di hai."}
            
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
