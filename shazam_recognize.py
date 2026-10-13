"""Recognise the song currently playing on an internet-radio stream with Shazam.

Called by radio.py as a subprocess (keeps shazamio's asyncio loop out of Streamlit's process):

    python shazam_recognize.py <stream_url> [seconds]
    python shazam_recognize.py --file <audio_bytes_file>   (already captured audio)

Prints one JSON object: {"title", "artist", "cover", "url"} or {"error": "..."}.
"""
import asyncio
import json
import sys
import time
from urllib.parse import urljoin

import requests

# ffmpeg (needed by pydub for MP3/AAC/HLS) comes from packages.txt on Streamlit Cloud.

UA = {"User-Agent": "Mozilla/5.0"}


def grab_stream(url, seconds):
    """Raw audio bytes from a plain (Icecast/Shoutcast/HTTP) stream."""
    buf, t0 = bytearray(), time.time()
    with requests.get(url, headers=UA, stream=True, timeout=10) as r:
        r.raise_for_status()
        for chunk in r.iter_content(16384):
            buf += chunk
            if time.time() - t0 >= seconds or len(buf) > 2_000_000:
                break
    return bytes(buf)


def grab_hls(url, seconds):
    """Last few segments of an HLS (.m3u8) live stream."""
    text = requests.get(url, headers=UA, timeout=10).text
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    variants = [l for l in lines if not l.startswith("#")]
    if any(l.startswith("#EXT-X-STREAM-INF") for l in lines) and variants:  # master playlist
        url = urljoin(url, variants[0])
        text = requests.get(url, headers=UA, timeout=10).text
        lines = [l.strip() for l in text.splitlines() if l.strip()]
    segs = [urljoin(url, l) for l in lines if not l.startswith("#")]
    buf = bytearray()
    for seg in segs[-max(2, int(seconds // 4) + 1):]:
        buf += requests.get(seg, headers=UA, timeout=10).content
    return bytes(buf)


WINDOW = 10      # seconds of audio per Shazam attempt
STEP = 8         # offset between attempts (windows overlap a little)


async def recognize(data):
    """Decode the raw stream to audio first (Shazam on raw MP3/AAC stream bytes misses a lot),
    then try successive 10 s windows until one is recognised (talk/jingles fail, music hits)."""
    import io
    from pydub import AudioSegment
    from shazamio import Shazam
    audio = AudioSegment.from_file(io.BytesIO(data))
    shazam = Shazam()
    last = max(0, len(audio) // 1000 - WINDOW)
    for start in range(last, -1, -STEP):  # newest audio first: a song that just started wins
        buf = io.BytesIO()
        audio[start * 1000:(start + WINDOW) * 1000].export(buf, format="wav")
        track = (await shazam.recognize(buf.getvalue())).get("track") or {}
        if track:
            images = track.get("images") or {}
            return {
                "title": track.get("title", ""),
                "artist": track.get("subtitle", ""),
                "cover": images.get("coverart", ""),
                "url": track.get("url", ""),
            }
    return {"error": "not found"}


def main():
    try:
        if sys.argv[1] == "--file":
            data = open(sys.argv[2], "rb").read()
        else:
            url = sys.argv[1]
            seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 20
            data = grab_hls(url, seconds) if ".m3u8" in url.lower() else grab_stream(url, seconds)
        res = asyncio.run(recognize(data))
    except Exception as e:  # report, don't crash the caller
        res = {"error": f"{type(e).__name__}: {e}"[:300]}
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
