import os
import random
import shutil
import subprocess

import yt_dlp

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def download_video(url: str, output_path: str):
    common = {
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 20,
        "concurrent_fragment_downloads": 4,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
    }

    # без ffmpeg качаем сразу mp4
    if not FFMPEG_AVAILABLE:
        ydl_opts = {**common, "format": "best[ext=mp4]/best"}
    else:
        ydl_opts = {**common, "format": "bestvideo+bestaudio/best", "merge_output_format": "mp4"}

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_file = ydl.prepare_filename(info)

    if downloaded_file != output_path:
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(downloaded_file, output_path)


def make_unique(input_path: str, output_path: str):
    if not FFMPEG_AVAILABLE:
        raise RuntimeError("ffmpeg not found")

    # умеренно "сильная" уникализация
    do_flip = random.random() < 0.7
    do_crop = random.random() < 0.65
    do_rotate = random.random() < 0.4
    do_color = random.random() < 0.75
    do_fps = random.random() < 0.55

    crop_px = random.randint(8, 22)
    rot = random.uniform(-1.0, 1.0)
    contrast = random.uniform(0.98, 1.08)
    brightness = random.uniform(-0.03, 0.03)
    saturation = random.uniform(0.98, 1.10)
    noise = random.randint(3, 10)
    fps = random.choice([29.97, 30, 30.5, 31])

    vf_parts = []
    if do_flip:
        vf_parts.append("hflip")
    if do_crop:
        vf_parts.append(f"crop=iw-{crop_px}:ih-{crop_px}")
        vf_parts.append("scale=iw:ih:flags=bicubic")
    if do_rotate:
        vf_parts.append(f"rotate={rot}*PI/180:fillcolor=black@0")
    if do_color:
        vf_parts.append(f"eq=contrast={contrast}:brightness={brightness}:saturation={saturation}")

    vf_parts.append(f"noise=alls={noise}:allf=t+u")
    if do_fps:
        vf_parts.append(f"fps={fps}")

    vf = ",".join(vf_parts)

    atempo = random.choice([0.995, 1.0, 1.005])
    af = f"atempo={atempo}"

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264", "-crf", "19", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
