import os
import yt_dlp

ALLOWED_CHANNELS = {
    "UCQYMhOMi_Cdj1CEAU-fv80A",
    "UCqxz6u2LHg0bE2p7n7P2E6w",
}

def download_video(url, output_path):
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

    # ----- 2. High-quality, optimized download -----
    ydl_opts = {
        # QUALITY + SPEED BALANCED
        "format": "best[height<=720][ext=mp4]/best[ext=mp4]",
        
        "outtmpl": output_path,
        "quiet": True,
        "ignoreerrors": True,
        "retries": 15,
        "nocheckcertificate": True,

        # HUGE SPEED BOOST (break throttling)
        "http_chunk_size": 1048576,   # 1 MB chunks

        "http_headers": {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return output_path
