import os
import yt_dlp

ALLOWED_CHANNELS = {
    "UCQYMhOMi_Cdj1CEAU-fv80A",
    "UCqxz6u2LHg0bE2p7n7P2E6w",
}

def download_video(url, output_path, progress_callback=None):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ----- 1. Get metadata and validate channel -----
    info_opts = {
        "quiet": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    channel_id = info.get("channel_id")
    channel_name = info.get("channel")

    if channel_id not in ALLOWED_CHANNELS:
        raise ValueError(f"Not a Neso Academy Video! Channel: {channel_name}")

    # ----- 2. Progress hook for download tracking -----
    def progress_hook(d):
        if progress_callback and d['status'] == 'downloading':
            # Calculate percentage
            if 'total_bytes' in d:
                percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
            elif 'total_bytes_estimate' in d:
                percent = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
            else:
                percent = 0
            
            progress_callback(int(percent))

    # ----- 3. High-quality, optimized download -----
    ydl_opts = {
        # QUALITY + SPEED BALANCED
        "format": "best[height<=720][ext=mp4]/best[ext=mp4]",
        
        "outtmpl": output_path,
        "quiet": True,
        "ignoreerrors": True,
        "retries": 15,
        "nocheckcertificate": True,

        # HUGE SPEED BOOST (break throttling)
        "http_chunk_size": 8*1048576,   # 8 MB chunks

        "http_headers": {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        },
        
        # Progress hook
        "progress_hooks": [progress_hook] if progress_callback else [],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return output_path
