"""Minimal internet-radio player that keeps playing across menu switches.

The <audio> element and the floating mini-player are created once directly in
the browser document (outside Streamlit's React tree) by a small idempotent
script, so Streamlit reruns and menu changes don't touch them.

- render_station_picker(): station list shown in Home -> Radio.
- render_player(): must be called on every run (any menu); injects/updates the
  floating player and forwards the last station chosen in Home.
"""
import hashlib
import importlib.util
import html
import json
import re
import collections
import os
import subprocess
import tempfile
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote, quote_plus, urljoin

import requests

import streamlit as st

import themes

# Streams verified 2026-10-07 (groups added 2026-10-13) (HTTP 200 + audio content-type).
# HTTPS only: Streamlit Community Cloud serves the page over https, so the browser blocks
# http:// audio (mixed content). HTTP-only stations (Z-Rock, Tangra, Radio 1 Rock, ...) are left out.
# .m3u8 (HLS) streams play natively or via hls.js loaded on demand in the player.
STATIONS = {
    "Български": [
        ("Радио 1", "https://play.global.audio/radio1128"),
        ("Magic FM", "https://bss1.neterra.tv/magicfm/magicfm.m3u8"),
        ("BG Estrada", "https://play.global.audio/bgestrada"),
        ("Energy 90s", "https://play.global.audio/energy-90s"),
        ("Jazz FM", "https://cdn.bweb.bg/radio/jazz-fm.mp3"),
        ("Radioplay Cafe", "https://play.global.audio/cafehi.aac"),
        ("БНР Хоризонт", "https://play.global.audio/testbhi.aac"),
        ("Дарик", "https://a12.asurahosting.com/listen/darik_radio/radio.mp3"),
    ],
    "Световни хитове": [
        ("Radio Paradise", "https://stream.radioparadise.com/mp3-192"),
        ("KEXP Seattle", "https://kexp-mp3-128.streamguys1.com/kexp128.mp3"),
        ("Capital UK", "https://media-ssl.musicradio.com/CapitalMP3"),
        ("Heart UK", "https://media-ssl.musicradio.com/HeartUKMP3"),
        ("Radio Swiss Pop", "https://stream.srg-ssr.ch/m/rsp/mp3_128"),
        ("SWR3", "https://liveradio.swr.de/sw282p3/swr3/play.mp3"),
        ("LOS40 España", "https://playerservices.streamtheworld.com/api/livestream-redirect/Los40.mp3"),
        ("NTS Radio", "https://stream-relay-geo.ntslive.net/stream"),
        ("FIP", "https://icecast.radiofrance.fr/fip-midfi.mp3"),
        ("FIP Pop", "https://icecast.radiofrance.fr/fippop-midfi.mp3"),
    ],
    "Рок": [
        ("Badrock Classic Rock", "https://streams.badrockradio.net/classic-rock"),
        ("0N Classic Rock", "https://0n-classicrock.radionetz.de/0n-classicrock.mp3"),
        ("Arrow Classic Rock", "https://stream.player.arrow.nl/arrowcr"),
        ("Zeppelin 106.7", "https://radiostreaming.ert.gr/ert-zeppelin"),
        ("Radio Paradise Rock", "https://stream.radioparadise.com/rock-192"),
    ],
    "Хард рок / метъл": [
        ("Badrock Hard & Heavy", "https://streams.badrockradio.net/hard-heavy"),
        ("Best of Rock Hard Rock", "https://bestofrockfm.stream.vip/hardrock/mp3-256/bestofrock.fm/"),
        ("181.fm 80s Hairband", "https://listen.181fm.com/181-hairband_128k.mp3"),
        ("Exclusively Iron Maiden", "https://streaming.exclusive.radio/er/ironmaiden/icecast.audio"),
        ("Exclusively Led Zeppelin", "https://streaming.exclusive.radio/er-app/ledzeppelin/icecast.audio"),
        ("FIP Metal", "https://icecast.radiofrance.fr/fipmetal-midfi.mp3"),
    ],
    "Алтернативен рок": [
        ("Best of Rock Alternative", "https://bestofrockfm.stream.vip/altrock/mp3-256/bestofrock.fm/"),
        ("TMM 1 (ex NME 1)", "https://listen-msmn.sharp-stream.com/nme1.mp3"),
        ("Exclusively Nirvana", "https://streaming.exclusive.radio/er/nirvana/icecast.audio"),
    ],
    "60-те": [
        ("0N 60s", "https://0n-60s.radionetz.de/0n-60s.mp3"),
        ("Splash 60s", "https://c4.auracast.net/radio/8020/radio.mp3"),
        ("laut.fm 60er", "https://60er.stream.laut.fm/60er"),
        ("laut.fm Sixties", "https://sixties.stream.laut.fm/sixties"),
        ("Chante France 60's", "https://chantefrance60s.ice.infomaniak.ch/chantefrance60s-128.mp3"),
        ("Radio Italia Anni 60", "https://ice10.fluidstream.net/anni60tn.aac"),
        ("Exclusively Beatles", "https://streaming.exclusive.radio/er/beatles/icecast.audio"),
        ("Exclusively Rolling Stones", "https://streaming.exclusive.radio/er/rollingstones/icecast.audio"),
    ],
    "Ретро": [
        ("0N 70s", "https://0n-70s.radionetz.de/0n-70s.mp3"),
        ("0N 80s", "https://0n-80s.radionetz.de/0n-80s.mp3"),
        ("Classic Vinyl HD", "https://icecast.walmradio.com:8443/classic"),
    ],
    "Джаз": [
        ("Radio Swiss Jazz", "https://stream.srg-ssr.ch/m/rsj/mp3_128"),
        ("FIP Jazz", "https://icecast.radiofrance.fr/fipjazz-midfi.mp3"),
        ("Adroit Jazz Underground", "https://icecast.walmradio.com:8443/jazz"),
        ("SmoothJazz.com", "https://smoothjazz.cdnstream1.com/2585_128.mp3"),
    ],
    "Кънтри": [
        ("181.fm Kickin' Country", "https://listen.181fm.com/181-kickincountry_128k.mp3"),
        ("181.fm Real Country", "https://listen.181fm.com/181-realcountry_128k.mp3"),
        ("181.fm Highway", "https://listen.181fm.com/181-highway_128k.mp3"),
        ("Radio Country Live NY", "https://streaming.radiostreamlive.com/radiocountrylive_devices"),
        ("America's Country", "https://ais-sa2.cdnstream1.com/1976_128.mp3"),
        ("0N Country", "https://0n-country.radionetz.de/0n-country.mp3"),
        ("Bluegrass Country", "https://ice24.securenetsystems.net/WAMU"),
        ("Exclusively Eagles", "https://streaming.exclusive.radio/er/eagles/icecast.audio"),
    ],
    "Соул / фънк / блус": [
        ("Funky Radio 60s-70s", "https://funkyradio.streamingmedia.it/play.mp3"),
        ("Disco Funk Soul Boogie", "https://discofunk.streamingmedia.it/usa"),
        ("Funky Corner Radio", "https://ais-sa2.cdnstream1.com/2447_192.mp3"),
        ("181.fm Soul", "https://listen.181fm.com/181-soul_128k.mp3"),
        ("0N Disco", "https://0n-disco.radionetz.de/0n-disco.mp3"),
        ("Pinguin Blues", "https://samcloud.spacial.com/api/listen?sid=93462&m=sc&rid=168006"),
        ("Exclusively Dire Straits", "https://2.mystreaming.net/er/direstraits/icecast.audio"),
    ],
    "Чил аут": [
        ("Café del Mar", "https://streams.radio.co/se1a320b47/listen"),
        ("Radio Paradise Mellow", "https://stream.radioparadise.com/mellow-192"),
        ("Chillout Ibiza FM", "https://edge3.peta.live365.net/b05055_128mp3"),
        ("Smooth Chill", "https://media-ssl.musicradio.com/ChillMP3"),
        ("0N Chillout", "https://0n-chillout.radionetz.de/0n-chillout.mp3"),
        ("Lounge.FM", "https://s35.derstream.net/100austria.mp3"),
        ("Chillhop (FluxFM)", "https://streams.fluxfm.de/Chillhop/mp3-128/streams.fluxfm.de/"),
        ("Brokenbeats", "https://stream.brokenbeats.net/tune"),
        ("Smooth Jazz Lounge", "https://radio4.vip-radios.fm:18060/stream-128kmp3-SmoothJazzLounge"),
        ("Reggae Chill Cafe", "https://maggie.torontocast.com:2020/stream/reggaechillcafe"),
        ("FIP Groove", "https://icecast.radiofrance.fr/fipgroove-midfi.mp3"),
    ],
    "Електронна / денс": [
        ("Sunshine Live", "https://stream.sunshine-live.de/live/mp3-192"),
        ("Intense Radio", "https://secure.live-streams.nl/main"),
        ("Dance Wave!", "https://dancewave.online/dance.mp3"),
        ("Dance Wave Retro", "https://dancewave.online/retrodance.mp3"),
        ("EuroDance 90", "https://stream-eurodance90.fr/radio/8000/128.mp3"),
        ("Trance (rautemusik)", "https://trance-high.rautemusik.fm/"),
        ("Pure Ibiza Radio", "https://pureibizaradio.clubbingradios.com:9518/PureIbizaRadio"),
        ("FIP Electro", "https://icecast.radiofrance.fr/fipelectro-midfi.mp3"),
    ],
    "Реге / латино / свят": [
        ("181.fm Reggae Roots", "https://listen.181fm.com/181-reggae_128k.mp3"),
        ("FIP Reggae", "https://icecast.radiofrance.fr/fipreggae-midfi.mp3"),
        ("Café Romántico Radio", "https://panel.retrolandigital.com/radio/8110/listen"),
        ("Cumbias Inmortales", "https://panel.retrolandigital.com/listen/cumbias_inmortales_radio/listen"),
        ("Radio Paradise World", "https://stream.radioparadise.com/world-etc-192"),
        ("FIP Monde", "https://icecast.radiofrance.fr/fipworld-midfi.mp3"),
    ],
    "Класика": [
        ("Classic FM UK", "https://media-ssl.musicradio.com/ClassicFMMP3"),
        ("Radio Swiss Classic", "https://stream.srg-ssr.ch/m/rsc_de/mp3_128"),
        ("Venice Classic Radio", "https://uk2.streamingpulse.com/ssl/vcr1"),
        ("WALM 2 HD", "https://icecast.walmradio.com:8443/walm2"),
        ("France Musique", "https://icecast.radiofrance.fr/francemusique-midfi.mp3"),
    ],
}

_CMD_KEY = "radio_cmd"


def _choose(name, url):
    st.session_state[_CMD_KEY] = {"name": name, "url": url, "nonce": str(time.time_ns())}


# Faint broadcast-tower + radio-waves backdrop (bottom right) and equalizer bars (bottom left).
_BG_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1000" preserveAspectRatio="xMaxYMax slice">'
    '<g fill="none" stroke="#027ed1" stroke-width="2">'
    + "".join(
        f'<circle cx="1380" cy="760" r="{r}" stroke-opacity="{0.10 - i * 0.011:.3f}"/>'
        for i, r in enumerate(range(90, 900, 110))
    )
    + '<path d="M1380 760 L1335 1000 M1380 760 L1425 1000 M1352 900 L1408 900 M1344 950 L1416 950 '
    'M1362 840 L1398 840" stroke-opacity=".12" stroke-width="3"/>'
    '</g><circle cx="1380" cy="752" r="9" fill="#027ed1" fill-opacity=".14"/>'
    '<g fill="#027ed1" fill-opacity=".05">'
    + "".join(
        f'<rect x="{40 + i * 26}" y="{1000 - h}" width="16" height="{h}" rx="3"/>'
        for i, h in enumerate([60, 110, 80, 150, 120, 190, 140, 90, 170, 110, 70, 130, 95, 55, 85, 40])
    )
    + "</g></svg>"
)

# Muted page tints for the Radio view: (key, label, background, accent for the waves/tower).
# Page tints for the Radio view: key -> (label, background, accent for the waves/tower).
# Light mode offers BG_LIGHT + BG_DEEP; dark mode (Streamlit dark theme) offers BG_DARK.
BG_LIGHT = {
    "white": ("Бяло", "#ffffff", "#027ed1"),
    "mist": ("Мъгла", "#edf1f5", "#4a6fa5"),
    "sky": ("Небе", "#e9f1f8", "#2f78b7"),
    "sage": ("Градински чай", "#ecf1ea", "#5b8a6b"),
    "sand": ("Пясък", "#f4efe5", "#a07a45"),
    "peach": ("Праскова", "#f7ece6", "#c0705a"),
    "lavender": ("Лавандула", "#f0edf6", "#7a64a8"),
    "stone": ("Камък", "#e9e9eb", "#5a6170"),
}
BG_DEEP = {
    "slate": ("Шисти", "#d5dde7", "#2f5a8f"),
    "ocean": ("Океан", "#cddbea", "#245e99"),
    "teal": ("Тюркоаз", "#cfe0df", "#2d6f6c"),
    "moss": ("Мъх", "#d3dfd0", "#3f6e4f"),
    "clay": ("Глина", "#e2d3bd", "#8a6331"),
    "rose": ("Пепел от роза", "#e5d0c7", "#a2523d"),
    "heather": ("Пирен", "#d8d0e6", "#5e4a8c"),
    "steel": ("Стомана", "#d0d3d9", "#454c5a"),
}
BG_DARK = {
    "night": ("Нощ", "#0e1117", "#4f8fd6"),
    "navy": ("Нощно синьо", "#121b2b", "#5b9be0"),
    "teal_d": ("Тъмен тюркоаз", "#0f1e1f", "#4fb3ad"),
    "forest": ("Гора", "#111c17", "#5fae86"),
    "coffee": ("Кафе", "#1d1714", "#c89b6d"),
    "wine": ("Вино", "#1f1216", "#d06a7f"),
    "plum": ("Слива", "#1a1422", "#a587d6"),
    "graphite": ("Графит", "#17191d", "#8a94a6"),
}

# Colours for elements drawn on top of the tint, per Streamlit base theme.
_MODE_COLORS = {
    "light": {"card": "rgba(255,255,255,.72)", "fg": "rgba(49,51,63,.6)", "text": "#31333f",
              "btn": "rgba(255,255,255,.7)", "pop": "#ffffff", "border": "rgba(49,51,63,.2)"},
    "dark": {"card": "rgba(14,17,23,.72)", "fg": "rgba(250,250,250,.6)", "text": "#fafafa",
             "btn": "rgba(14,17,23,.6)", "pop": "#1b1d24", "border": "rgba(250,250,250,.2)"},
}

# The SVG is used as a mask, so the waves take the colour of --vr-accent.
_BG_CSS = f"""<style>
[data-testid="stMain"], [data-testid="stHeader"] {{ background: var(--vr-bg, #ffffff); transition: background .3s; }}
[data-testid="stMain"]::before {{
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background: var(--vr-accent, #027ed1); transition: background .3s;
  -webkit-mask: url("data:image/svg+xml,{quote(_BG_SVG)}") right bottom / cover no-repeat;
          mask: url("data:image/svg+xml,{quote(_BG_SVG)}") right bottom / cover no-repeat;
}}
[data-testid="stMainBlockContainer"] {{ position: relative; z-index: 1; }}
[class*="st-key-radio_grp_"] {{ background: var(--vr-card); backdrop-filter: blur(2px); }}
</style>"""

# Header row: caption + "Фон" palette button. Runs client-side only (instant, saved in localStorage).
_HEAD_HTML = """
<style>
.vr-head{display:flex;align-items:center;justify-content:space-between;gap:12px;font:14px "Source Sans Pro",sans-serif}
.vr-cap{color:var(--vr-fg)}
.vr-pal{position:relative}
.vr-pal-btn{display:flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid var(--vr-border);
  border-radius:8px;background:var(--vr-btn);color:var(--vr-text);cursor:pointer;font:inherit}
.vr-pal-btn:hover{border-color:#027ed1}
.vr-dot{width:14px;height:14px;border-radius:50%;border:1px solid rgba(0,0,0,.15)}
.vr-pal-pop{position:absolute;right:0;top:calc(100% + 6px);z-index:50;display:none;padding:10px 12px 12px;
  background:var(--vr-pop);color:var(--vr-text);border:1px solid var(--vr-border);border-radius:10px;
  box-shadow:0 6px 18px rgba(0,0,0,.18)}
.vr-pal.open .vr-pal-pop{display:block}
.vr-grp{font-size:11px;color:var(--vr-fg);margin:2px 0 6px}
.vr-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:8px}
.vr-sw{width:30px;height:30px;border-radius:50%;cursor:pointer;border:1px solid rgba(0,0,0,.15);padding:0;
  display:flex;align-items:center;justify-content:center}
.vr-sw span{width:10px;height:10px;border-radius:50%}
.vr-sw.on{outline:2px solid var(--vr-text);outline-offset:2px}
</style>
<div class="vr-head" id="vr-head">
  <span class="vr-cap">Изберете станция.</span>
  <div class="vr-pal"><button class="vr-pal-btn" title="Цвят на фона"><span class="vr-dot"></span>Фон</button>
    <div class="vr-pal-pop"></div></div>
</div>
<script>
(function () {
  const cfg = __THEMES__;                      // {store, colors, groups: [[label, [[k,label,bg,acc],...]], ...]}
  const themes = cfg.groups.flatMap((g) => g[1]);
  const root = document.getElementById("vr-head");
  if (!root) return;
  const pal = root.querySelector(".vr-pal"), pop = root.querySelector(".vr-pal-pop"), dot = root.querySelector(".vr-dot");
  const de = document.documentElement.style;
  Object.entries(cfg.colors).forEach(([k, v]) => de.setProperty("--vr-" + k, v));
  let cur; try { cur = localStorage.getItem(cfg.store); } catch (e) {}
  const apply = (k) => {
    const t = themes.find((x) => x[0] === k) || themes[0];
    cur = t[0];
    de.setProperty("--vr-bg", t[2]); de.setProperty("--vr-accent", t[3]);
    dot.style.background = t[2]; dot.style.borderColor = t[3];
    pop.querySelectorAll(".vr-sw").forEach((b) => b.classList.toggle("on", b.dataset.k === cur));
    try { localStorage.setItem(cfg.store, cur); } catch (e) {}
  };
  cfg.groups.forEach(([title, list]) => {
    const h = document.createElement("div"); h.className = "vr-grp"; h.textContent = title;
    const grid = document.createElement("div"); grid.className = "vr-grid";
    list.forEach(([k, label, bg, acc]) => {
      const b = document.createElement("button");
      b.className = "vr-sw"; b.dataset.k = k; b.title = label; b.setAttribute("aria-label", label);
      b.style.background = bg;
      const i = document.createElement("span"); i.style.background = acc; b.appendChild(i);
      b.addEventListener("click", (e) => { e.stopPropagation(); apply(k); });
      grid.appendChild(b);
    });
    pop.append(h, grid);
  });
  pop.addEventListener("click", (e) => e.stopPropagation());
  root.querySelector(".vr-pal-btn").addEventListener("click", (e) => { e.stopPropagation(); pal.classList.toggle("open"); });
  const close = () => { if (!root.isConnected) document.removeEventListener("click", close); else pal.classList.remove("open"); };
  document.addEventListener("click", close);
  apply(cur);
})();
</script>
"""


def render_station_picker():
    """Home -> Radio: station buttons grouped by genre."""
    st.html(_BG_CSS)  # only present while this view is rendered
    skin = themes.active()
    if skin:
        # an app-wide skin is active: the page follows it (no own "Фон" picker)
        mc = _MODE_COLORS[themes.mode()]
        st.html(f"""<style>:root {{ --vr-bg: transparent !important; --vr-accent: {skin['accent']} !important;
  --vr-card: {skin['card']} !important; --vr-fg: {mc['fg']} !important; }}</style>""")
        st.caption("Изберете станция. Фонът следва темата („Тема“ в страничната лента).")
    else:
        _bg_picker()
    _now_playing_toggle()
    current = (st.session_state.get(_CMD_KEY) or {}).get("url")
    for i, (genre, stations) in enumerate(STATIONS.items()):
        with st.container(border=True, key=f"radio_grp_{i}"):
            st.markdown(f"**{genre}**")
            with st.container(horizontal=True):
                for name, url in stations:
                    st.button(
                        name,
                        key=f"radio_{url}",
                        type="primary" if url == current else "secondary",
                        icon=":material/graphic_eq:" if url == current else None,
                        on_click=_choose,
                        args=(name, url),
                    )


# ---------------------------------------------------------------- "Какво свири?"
# 1) ICY stream metadata (StreamTitle) — instant, most foreign stations send it;
# 2) otherwise Shazam: shazam_recognize.py (shazamio-core + ffmpeg from packages.txt) recognises the
#    last ~10 s of the stream in a subprocess. That takes ~15 s, so it runs in a background
#    thread and the card polls for the result.

SHAZAM_PY = Path(sys.executable)
SHAZAM_SCRIPT = Path(__file__).with_name("shazam_recognize.py")
SHAZAM_OK = importlib.util.find_spec("shazamio_core") is not None


# Live follow while the card is open: one reader thread per station keeps the stream open,
# picks up ICY title changes the moment the station sends them, and keeps the last few
# seconds of audio so Shazam can recognise the newest audio without waiting for a new capture.
LIVE_IDLE = 30        # s without a card poll -> the reader stops and closes the stream
AUDIO_KEEP = 16       # s of recent audio kept for Shazam
SHAZAM_EVERY = 15     # s between Shazam runs while the card is open (stations without ICY titles)
ICY_GRACE = 5         # s to wait for an ICY title before falling back to Shazam
MISSES_TO_CLEAR = 2   # consecutive Shazam misses after which the last song is no longer shown as live
UA = {"User-Agent": "Mozilla/5.0"}


def _shazam_bytes(data):
    """Recognise captured audio bytes with the shazam env (subprocess, see shazam_recognize.py)."""
    fd, path = tempfile.mkstemp(suffix=".audio")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        out = subprocess.run([str(SHAZAM_PY), "-W", "ignore", str(SHAZAM_SCRIPT), "--file", path],
                             capture_output=True, text=True, encoding="utf-8", timeout=60,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        line = (out.stdout or "").strip().splitlines()[-1:] or ["{}"]
        return json.loads(line[0])
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:200]}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


class _Live:
    def __init__(self, url):
        self.url = url
        self.lock = threading.Lock()
        self.started = self.seen = time.time()
        self.alive = True
        self.icy, self.icy_at = None, 0          # latest non-empty ICY title
        self.chunks = collections.deque()        # (time, audio bytes)
        self.res, self.res_at = None, 0          # latest Shazam hit
        self.busy, self.force, self.last_run, self.last_miss = False, 0, 0, 0
        self.misses = 0                          # consecutive Shazam misses (ads/talk)
        self.run_forced = False                  # current run was requested with "Разпознай пак"
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._recognise_loop, daemon=True).start()

    def wanted(self):
        return time.time() - self.seen < LIVE_IDLE

    def _push(self, data):
        now = time.time()
        with self.lock:
            self.chunks.append((now, data))
            while self.chunks and now - self.chunks[0][0] > AUDIO_KEEP:
                self.chunks.popleft()

    def _read(self):
        try:
            (self._read_hls if ".m3u8" in self.url.lower() else self._read_icy)()
        except Exception:
            pass
        finally:
            self.alive = False

    def _read_icy(self):
        with requests.get(self.url, headers={**UA, "Icy-MetaData": "1"}, stream=True, timeout=10) as r:
            metaint = int(r.headers.get("icy-metaint") or 0)
            raw = r.raw
            while self.wanted():
                data = raw.read(metaint or 16384)
                if not data:
                    break
                self._push(data)
                if not metaint:
                    continue
                n = raw.read(1)
                if not n:
                    break
                if n[0]:
                    meta = raw.read(n[0] * 16).decode("utf-8", "replace")
                    m = re.search(r"StreamTitle='(.*?)';", meta)
                    title = m.group(1).strip(" -") if m else ""
                    if title:
                        with self.lock:
                            if title != self.icy:
                                # icy_at = when the song changed; 0 for the one already playing on connect
                                self.icy, self.icy_at = title, (time.time() if self.icy is not None else 0)

    def _read_hls(self):
        media, done = self.url, set()
        while self.wanted():
            lines = [l.strip() for l in requests.get(media, headers=UA, timeout=10).text.splitlines() if l.strip()]
            uris = [l for l in lines if not l.startswith("#")]
            if any(l.startswith("#EXT-X-STREAM-INF") for l in lines) and uris:   # master playlist
                media = urljoin(media, uris[0])
                continue
            segs = [urljoin(media, u) for u in uris]
            new = [x for x in segs if x not in done]
            if not done:
                new = new[-2:]                       # start at the live edge
            for seg in new:
                self._push(requests.get(seg, headers=UA, timeout=10).content)
                done.add(seg)
            time.sleep(3)

    def _recognise_loop(self):
        while self.alive and self.wanted():
            time.sleep(1)
            if self.icy is not None or time.time() - self.started < ICY_GRACE or not SHAZAM_OK:
                continue
            if time.time() - self.last_run < SHAZAM_EVERY and self.force <= self.last_run:
                continue
            with self.lock:
                data = b"".join(c for _, c in self.chunks)
            if len(data) < 30_000:
                continue
            self.run_forced = self.force > self.last_run
            self.busy, self.last_run = True, time.time()
            res = _shazam_bytes(data)
            with self.lock:
                if res.get("title"):
                    self.misses = 0
                    if not (self.res and self.res.get("title") == res["title"]):
                        self.res, self.res_at = res, time.time()
                else:
                    self.misses += 1
                    self.last_miss = time.time()
            self.busy = self.run_forced = False

    def snapshot(self, force_after=0):
        self.seen = time.time()
        if force_after > self.force:
            self.force = force_after
        with self.lock:
            return {"icy": self.icy, "icy_at": self.icy_at, "res": self.res, "res_at": self.res_at,
                    "busy": self.busy or (self.icy is None and self.res is None and self.last_miss == 0),
                    "miss": self.last_miss > self.res_at, "misses": self.misses, "shazam": self.icy is None,
                    # "Разпознай пак" pressed: requested or running right now -> show "listening"
                    "checking": (self.busy and self.run_forced) or self.force > self.last_run}


@st.cache_resource
def _lives():
    return {"lock": threading.Lock(), "by_url": {}}


def live_status(url, force_after=0):
    """Current song info for `url`, starting (or restarting) the live reader as needed."""
    pool = _lives()
    with pool["lock"]:
        live = pool["by_url"].get(url)
        # type(live) is not _Live: a reader created by an older version of this module (Streamlit
        # reloads radio.py on edit, but the cached pool keeps old objects) -> replace it
        if live is None or not live.alive or type(live) is not _Live:
            live = pool["by_url"][url] = _Live(url)
    return live.snapshot(force_after)


def _np_flip():
    on = not st.session_state.get("radio_np_show", False)
    st.session_state["radio_np_show"] = on
    if on:
        st.session_state["radio_np_since"] = time.time()  # ask Shazam once for a fresh result


def _np_again():
    st.session_state["radio_np_since"] = time.time()


def _now_playing_toggle():
    on = st.session_state.get("radio_np_show", False)
    st.button("Скрий „Какво свири?“" if on else "Какво свири?", key="radio_np_btn",
              icon=":material/music_off:" if on else ":material/music_note:",
              type="primary" if on else "secondary", on_click=_np_flip)
    if on:
        _now_playing_card()


_NP_CSS = """<style>
@keyframes npIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }
@keyframes npEq { 0%,100%{transform:scaleY(.25)} 50%{transform:scaleY(1)} }
@keyframes npRing { from{transform:scale(.8);opacity:.7} to{transform:scale(1.7);opacity:0} }
@keyframes npDots { 0%{content:""} 25%{content:"."} 50%{content:".."} 75%{content:"..."} }
@keyframes npTilt { 0%,100%{transform:rotate(-6deg)} 50%{transform:rotate(6deg)} }
.np{display:flex;gap:16px;align-items:center;padding:14px 18px;border-radius:18px;font-family:"Source Sans Pro",sans-serif;
  background:var(--jb-card,rgba(128,128,128,.07));border:1px solid var(--jb-border,rgba(128,128,128,.2));animation:npIn .4s both}
.np-art{width:68px;height:68px;border-radius:14px;object-fit:cover;flex:none;box-shadow:0 8px 20px -10px rgba(0,0,0,.6)}
.np-ico{position:relative;width:68px;height:68px;border-radius:14px;flex:none;display:grid;place-items:center;font-size:30px;
  background:linear-gradient(135deg,var(--jb-accent,#027ed1),var(--jb-accent2,#7a5cff))}
.np-ico.listen::before,.np-ico.listen::after{content:"";position:absolute;inset:0;border-radius:14px;
  border:2px solid var(--jb-accent,#027ed1);animation:npRing 1.6s ease-out infinite}
.np-ico.listen::after{animation-delay:.8s}
.np-ico.quiet span{display:inline-block;animation:npTilt 2.4s ease-in-out infinite}
.np-body{min-width:0;flex:1}
.np-kick{font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;font-weight:700;display:flex;align-items:center;gap:8px;
  background:linear-gradient(90deg,var(--jb-accent,#027ed1),var(--jb-accent2,#7a5cff));-webkit-background-clip:text;color:transparent}
.np-eq{display:inline-flex;gap:2px;align-items:flex-end;height:11px}
.np-eq i{width:3px;height:100%;border-radius:2px;background:var(--jb-accent,#027ed1);transform-origin:bottom;animation:npEq .9s ease-in-out infinite}
.np-eq i:nth-child(2){animation-delay:-.3s}.np-eq i:nth-child(3){animation-delay:-.6s}.np-eq i:nth-child(4){animation-delay:-.15s}
.np-title{font-size:1.2rem;font-weight:800;line-height:1.2;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.np-sub{font-size:.9rem;opacity:.75;margin-top:1px}
.np-src{font-size:.72rem;opacity:.55;margin-top:6px}
.np-dots::after{content:"";animation:npDots 1.2s steps(4) infinite}
.np-links{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.np-links a{display:inline-flex;align-items:center;gap:5px;padding:3px 11px;border-radius:999px;font-size:.75rem;font-weight:700;
  text-decoration:none;color:#fff !important;transition:transform .15s,filter .2s}
.np-links a:hover{transform:translateY(-2px);filter:brightness(1.1)}
.np-links a.sz{background:#0088ff}.np-links a.yt{background:#ff0033}.np-links a.sp{background:#1db954}
@media (prefers-reduced-motion: reduce){.np *,.np{animation:none !important}}
</style>"""


def _np_card(icon, kicker, title, sub="", extra="", art=None, icon_cls=""):
    e = html.escape
    left = (f'<img class="np-art" src="{e(art)}" alt="">' if art
            else f'<div class="np-ico {icon_cls}"><span>{icon}</span></div>')
    st.html(f'{_NP_CSS}<div class="np">{left}<div class="np-body">'
            f'<div class="np-kick">{kicker}</div><div class="np-title">{e(title)}</div>'
            f'{f"<div class=np-sub>{sub}</div>" if sub else ""}{extra}</div></div>')


@st.fragment(run_every="3s")  # only exists while the card is shown; reads in-memory state only
def _now_playing_card():
    e = html.escape
    cmd = st.session_state.get(_CMD_KEY)
    if not cmd:
        _np_card("📻", "Какво свири?", "Пусни някоя станция",
                 "…и ще ти кажа коя е песента и кой я изпълнява 🎧")
        return
    name, url = cmd["name"], cmd["url"]
    live = live_status(url, force_after=st.session_state.get("radio_np_since", 0))
    icy, res, busy = live["icy"], live["res"], live["busy"]

    # Shazam stations: two misses in a row (~30 s of ads/talk) -> stop showing the last song as live
    gone = not icy and res and live.get("misses", 0) >= MISSES_TO_CLEAR
    if icy or (res and res.get("title") and not gone):
        if icy:
            artist, _, song = icy.partition(" - ")
            if not song:  # no "Artist - Title" split: show the whole string
                artist, song = "", icy
            source, art, link = "по данни на станцията", None, None
        else:
            artist, song = res.get("artist", ""), res["title"]
            source, art, link = "разпознато от Shazam", res.get("cover"), res.get("url")
        full = f"{artist} {song}".strip()
        chips = ""
        if link:
            chips += f'<a class="sz" href="{e(link)}" target="_blank">Shazam</a>'
        chips += (f'<a class="yt" href="https://www.youtube.com/results?search_query={quote_plus(full)}" '
                  f'target="_blank">▶ YouTube</a>'
                  f'<a class="sp" href="https://open.spotify.com/search/{quote(full)}" target="_blank">Spotify</a>')
        # No clocks / "listening…" hints here: the HTML only changes when the song changes, so
        # the 3 s fragment rerun doesn't redraw (and re-animate) the card. Work runs in _Live.
        _np_card("🎵", f'Сега в ефир · {e(name)}<span class="np-eq"><i></i><i></i><i></i><i></i></span>',
                 song, e(artist),
                 f'<div class="np-links">{chips}</div><div class="np-src">{source}</div>', art=art)

    elif not icy and live.get("checking"):
        again = live["miss"] or bool(res)
        _np_card("🎧", f"Shazam слуша · {e(name)}", "Проверявам отново" if again else "Разпознавам песента",
                 '<span class="np-dots">Около 10 секунди</span>', icon_cls="listen")
    elif busy and not live["miss"]:  # only until the first Shazam attempt finishes
        _np_card("🎧", f"Shazam слуша · {e(name)}", "Разпознавам песента",
                 '<span class="np-dots">Около 10–15 секунди</span>', icon_cls="listen")
    elif not SHAZAM_OK:
        _np_card("📡", e(name), "Станцията не казва какво свири",
                 "А Shazam още не е инсталиран на сървъра.")
    else:
        last = (f'<div class="np-src">Последна песен: {e(res.get("artist", ""))} – {e(res["title"])}</div>'
                if res and res.get("title") else "")
        _np_card("🎙️", e(name), "Сега май се говори в ефир",
                 "Shazam не чу песен — може да е разговор или реклама.", last, icon_cls="quiet")
        st.button("Разпознай пак", icon=":material/refresh:", key="radio_np_again", on_click=_np_again)


def _bg_picker():
    """Caption + own "Фон" tint picker (only with the Минимал app skin)."""
    dark = st.context.theme.type == "dark"
    as_list = lambda d: [[k, *v] for k, v in d.items()]
    cfg = {
        "store": "veasRadioBg-dark" if dark else "veasRadioBg",
        "colors": _MODE_COLORS["dark" if dark else "light"],
        "groups": [["Тъмни", as_list(BG_DARK)]] if dark
                  else [["Светли", as_list(BG_LIGHT)], ["По-тъмни", as_list(BG_DEEP)]],
    }
    head = _HEAD_HTML.replace("__THEMES__", json.dumps(cfg, ensure_ascii=False))
    # Same DOMPurify "<" workaround as the player: escape "<" inside the script only.
    pre, rest = head.split("<script>", 1)
    body, post = rest.split("</script>", 1)
    st.html(pre + "<script>" + body.replace("<", "\\x3c") + "</script>" + post, unsafe_allow_javascript=True)


_PLAYER_JS = r"""
(function () {
  const cfg = __CFG__;
  const doc = document;
  const VER = "__VER__";
  const old = window.__veasRadio;
  let R = old && old.ver === VER ? old : null;
  if (!R) {
    // New code version (or first load): rebuild the UI but keep the playing <audio>.
    const was = old ? { station: old.station, playing: !!old.wantPlay } : null;
    if (old) { old.wantPlay = false; clearTimeout(old.retry); }
    doc.querySelectorAll("#veas-radio, style[data-veas-radio]").forEach((el) => el.remove());
    doc.querySelectorAll("style").forEach((el) => { if (el.textContent.includes("#veas-radio{")) el.remove(); });

    const css = doc.createElement("style");
    css.textContent = `
      /* colours: --vrp-* set from Python (cfg.theme) = the app skin, or Streamlit light/dark for Минимал */
      #veas-radio{position:fixed;right:16px;bottom:16px;z-index:999999;display:none;align-items:center;gap:8px;
        padding:6px 10px 6px 6px;border-radius:999px;background:var(--vrp-bg,#fff);color:var(--vrp-fg,#31333f);
        border:1px solid var(--vrp-border,#d6dbe4);box-shadow:0 8px 24px -8px var(--vrp-glow,rgba(0,0,0,.25));
        font:13px "Source Sans Pro",sans-serif;max-width:360px;cursor:grab;user-select:none;touch-action:none;
        backdrop-filter:blur(10px);transition:background .3s,color .3s,border-color .3s,box-shadow .3s}
      #veas-radio .vr-grip{color:var(--vrp-muted,#9aa0ad);font-size:18px;padding:0 2px 0 6px;line-height:1;opacity:.75}
      #veas-radio:hover .vr-grip{opacity:1}
      #veas-radio.vr-drag{cursor:grabbing;box-shadow:0 12px 30px -8px var(--vrp-glow,rgba(0,0,0,.3))}
      #veas-radio button{border:0;background:transparent;cursor:pointer;color:inherit;padding:0;line-height:0}
      #veas-radio .vr-play{width:30px;height:30px;border-radius:50%;color:#fff;display:flex;align-items:center;
        justify-content:center;background:linear-gradient(135deg,var(--vrp-accent,#027ed1),var(--vrp-accent2,#027ed1));
        box-shadow:0 4px 12px -4px var(--vrp-glow,rgba(2,126,209,.5));transition:transform .15s,filter .2s}
      #veas-radio .vr-play:hover{transform:scale(1.08);filter:brightness(1.08)}
      #veas-radio .vr-play svg{width:16px;height:16px;fill:currentColor}
      #veas-radio .vr-txt{display:flex;flex-direction:column;min-width:0;max-width:170px}
      #veas-radio .vr-name{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      #veas-radio .vr-st{font-size:11px;color:var(--vrp-muted,#808495)}
      #veas-radio input[type=range]{width:70px;height:16px;margin:0;background:transparent;cursor:pointer;
        -webkit-appearance:none;appearance:none}
      #veas-radio input[type=range]::-webkit-slider-runnable-track{height:4px;border-radius:2px;
        background:linear-gradient(90deg,var(--vrp-accent,#027ed1),var(--vrp-accent2,#027ed1)) 0/var(--fill,60%) 100% no-repeat,
        var(--vrp-track,rgba(128,128,128,.3))}
      #veas-radio input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:12px;height:12px;margin-top:-4px;
        border-radius:50%;background:var(--vrp-accent2,#027ed1);border:2px solid var(--vrp-bg,#fff);
        box-shadow:0 0 0 1px var(--vrp-accent,#027ed1)}
      #veas-radio input[type=range]::-moz-range-track{height:4px;border-radius:2px;background:var(--vrp-track,rgba(128,128,128,.3))}
      #veas-radio input[type=range]::-moz-range-progress{height:4px;border-radius:2px;
        background:linear-gradient(90deg,var(--vrp-accent,#027ed1),var(--vrp-accent2,#027ed1))}
      #veas-radio input[type=range]::-moz-range-thumb{width:10px;height:10px;border-radius:50%;
        background:var(--vrp-accent2,#027ed1);border:2px solid var(--vrp-bg,#fff)}
      #veas-radio .vr-x{font-size:16px;color:var(--vrp-muted,#808495);padding:0 2px}
      #veas-radio .vr-x:hover{color:var(--vrp-fg,#31333f)}`;
    css.setAttribute("data-veas-radio", "");
    doc.head.appendChild(css);

    const box = doc.createElement("div");
    box.id = "veas-radio";
    box.innerHTML = `
      <span class="vr-grip" title="Влачете за преместване">⠿</span>
      <button class="vr-play" title="Пусни / пауза" aria-label="Пусни / пауза"></button>
      <div class="vr-txt"><span class="vr-name"></span><span class="vr-st"></span></div>
      <input type="range" min="0" max="1" step="0.05" title="Сила на звука" aria-label="Сила на звука">
      <button class="vr-x" title="Спри и скрий" aria-label="Спри и скрий">&times;</button>`;
    doc.body.appendChild(box);

    const audio = old ? old.audio : new Audio();
    audio.preload = "none";
    const $ = (s) => box.querySelector(s);
    const ICON_PLAY = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
    const ICON_PAUSE = '<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>';
    const store = {
      get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } },
      set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
    };

    R = window.__veasRadio = { ver: VER, audio, station: null, wantPlay: false,
                               lastNonce: old ? old.lastNonce : null, retry: null,
                               hls: old ? old.hls : null, hlsLoad: old ? old.hlsLoad : null };
    const status = (t) => { $(".vr-st").textContent = t; };
    const icon = () => { $(".vr-play").innerHTML = R.wantPlay ? ICON_PAUSE : ICON_PLAY; };

    const retryLater = () => {
      status("Грешка – нов опит…");
      clearTimeout(R.retry);
      R.retry = setTimeout(() => { if (R.wantPlay) R.start(); }, 5000);
    };
    // HLS (.m3u8): native where supported, otherwise hls.js loaded on first use.
    const isHls = (u) => /\.m3u8(\?|$)/i.test(u);
    const loadHls = () => window.Hls ? Promise.resolve(window.Hls) : (R.hlsLoad ||= new Promise((ok, ko) => {
      const sc = doc.createElement("script");
      sc.src = "https://cdn.jsdelivr.net/npm/hls.js@1/dist/hls.min.js";
      sc.onload = () => ok(window.Hls);
      sc.onerror = () => { R.hlsLoad = null; ko(new Error("hls.js")); };
      doc.head.appendChild(sc);
    }));
    const dropHls = () => { if (R.hls) { R.hls.destroy(); R.hls = null; } };
    const play = () => audio.play().catch((e) => {
      if (e && e.name === "NotAllowedError") { R.wantPlay = false; icon(); status("Натиснете ▶"); }
    });

    R.start = function () {
      if (!R.station) return;
      clearTimeout(R.retry); dropHls();
      R.wantPlay = true; icon(); status("Свързване…");
      const url = R.station.url;
      if (isHls(url) && !audio.canPlayType("application/vnd.apple.mpegurl")) {
        loadHls().then((Hls) => {
          if (!R.wantPlay || !R.station || R.station.url !== url) return;
          const h = R.hls = new Hls({ liveSyncDurationCount: 3 });
          h.on(Hls.Events.ERROR, (_, d) => { if (d.fatal && R.hls === h) { dropHls(); retryLater(); } });
          h.loadSource(url); h.attachMedia(audio); play();
        }).catch(retryLater);
        return;
      }
      audio.src = url;               // fresh src = live edge, not stale buffer
      play();
    };
    R.stop = function (msg) {
      clearTimeout(R.retry); dropHls();
      R.wantPlay = false; icon();
      audio.pause(); audio.removeAttribute("src"); audio.load();   // stop downloading
      status(msg || "Пауза");
    };
    R.select = function (st, autoplay) {
      R.station = { name: st.name, url: st.url };
      store.set("veasRadioStation", R.station);
      $(".vr-name").textContent = st.name; $(".vr-name").title = st.name;
      box.style.display = "flex"; R.place();
      if (autoplay) R.start(); else R.stop("Готово");
    };

    audio.addEventListener("playing", () => status("На живо"));
    audio.addEventListener("waiting", () => { if (R.wantPlay) status("Буфериране…"); });
    audio.addEventListener("error", () => {
      if (!R.wantPlay || R.hls || !audio.getAttribute("src")) return;
      retryLater();
    });
    $(".vr-play").addEventListener("click", () => (R.wantPlay ? R.stop() : R.start()));
    $(".vr-x").addEventListener("click", () => { R.stop(); box.style.display = "none"; });
    const vol = $("input");
    const fill = () => vol.style.setProperty("--fill", (+vol.value * 100) + "%");  // coloured part of the track
    vol.value = audio.volume = store.get("veasRadioVolume") ?? 0.6;
    fill();
    vol.addEventListener("input", () => { audio.volume = +vol.value; store.set("veasRadioVolume", +vol.value); fill(); });

    // Drag anywhere except the controls; position persists in localStorage.
    const place = (x, y) => {
      const r = box.getBoundingClientRect();
      x = Math.max(4, Math.min(x, innerWidth - r.width - 4));
      y = Math.max(4, Math.min(y, innerHeight - r.height - 4));
      Object.assign(box.style, { left: x + "px", top: y + "px", right: "auto", bottom: "auto" });
      return { x, y };
    };
    // Until the user drags it: next to the "Какво свири?" button (under it when there's no room),
    // following the button while the page scrolls; bottom-right when the button isn't there.
    // Under the button (phones) its container gets a bottom margin, so the player doesn't cover the list.
    const gap = (px) => { const c = doc.querySelector(".st-key-radio_np_btn"); if (c) c.style.marginBottom = px; };
    R.place = () => {
      const p = store.get("veasRadioPos");
      if (p) { gap(""); return place(p.x, p.y); }
      const a = doc.querySelector(".st-key-radio_np_btn button");
      if (!a) { Object.assign(box.style, { left: "auto", top: "auto", right: "16px", bottom: "16px" }); return; }
      const ar = a.getBoundingClientRect(), r = box.getBoundingClientRect();
      if (innerWidth - 4 >= ar.right + 34 + r.width) { gap(""); place(ar.right + 34, ar.top + (ar.height - r.height) / 2); }
      else { gap(r.height + 12 + "px"); place(ar.left, ar.bottom + 8); }
    };
    const follow = setInterval(() => {
      if (!box.isConnected) return clearInterval(follow);   // replaced by a newer player version
      if (box.style.display === "none") gap("");
      else if (!store.get("veasRadioPos")) R.place();
    }, 250);
    box.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest("button, input")) return;
      const r = box.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
      box.setPointerCapture(e.pointerId); box.classList.add("vr-drag");
      const move = (ev) => place(ev.clientX - dx, ev.clientY - dy);
      const up = (ev) => {
        box.releasePointerCapture(ev.pointerId); box.classList.remove("vr-drag");
        box.removeEventListener("pointermove", move); box.removeEventListener("pointerup", up);
        store.set("veasRadioPos", place(ev.clientX - dx, ev.clientY - dy));
      };
      box.addEventListener("pointermove", move); box.addEventListener("pointerup", up);
    });
    window.addEventListener("resize", () => { if (box.style.display !== "none") R.place(); });

    icon();
    if (was && was.station) {
      R.station = was.station;
      $(".vr-name").textContent = was.station.name; $(".vr-name").title = was.station.name;
      box.style.display = "flex"; R.place();
      R.wantPlay = was.playing; icon();
      status(was.playing ? (audio.paused ? "Буфериране…" : "На живо") : "Пауза");
    } else {
      const last = store.get("veasRadioStation");
      if (last && last.url) R.select(last, false);
    }
  }
  // follow the app skin / light-dark mode (cfg changes -> this script re-runs)
  const pbox = doc.getElementById("veas-radio");
  if (pbox && cfg.theme) Object.entries(cfg.theme).forEach(([k, v]) => pbox.style.setProperty("--vrp-" + k, v));
  if (cfg.cmd && cfg.cmd.nonce !== R.lastNonce) {
    R.lastNonce = cfg.cmd.nonce;
    R.select(cfg.cmd, true);
  }
})();
"""


_PLAYER_VER = hashlib.md5(_PLAYER_JS.encode()).hexdigest()[:8]


def _player_colors():
    """Floating-player colours: the active skin's, or Streamlit's own light/dark for Минимал."""
    v = themes.active()
    if v:
        return {"bg": v["sidebar"], "fg": v["text"], "muted": v["muted"], "border": v["border"],
                "accent": v["accent"], "accent2": v["accent2"], "glow": v["glow"], "track": v["btn"]}
    if themes.mode() == "dark":
        return {"bg": "#262730", "fg": "#fafafa", "muted": "#a3a8b8", "border": "rgba(250,250,250,.16)",
                "accent": "#ff4b4b", "accent2": "#ff7a59", "glow": "rgba(0,0,0,.6)", "track": "rgba(250,250,250,.18)"}
    return {"bg": "#ffffff", "fg": "#31333f", "muted": "#808495", "border": "#d6dbe4",
            "accent": "#027ed1", "accent2": "#027ed1", "glow": "rgba(0,0,0,.25)", "track": "rgba(49,51,63,.15)"}


def render_player():
    """Inject/refresh the persistent floating player. Call on every run."""
    cfg = {"cmd": st.session_state.get(_CMD_KEY), "theme": _player_colors()}
    js = _PLAYER_JS.replace("__CFG__", json.dumps(cfg)).replace("__VER__", _PLAYER_VER)
    # DOMPurify drops a <script> whose text contains tag-like "<x" sequences (mXSS guard),
    # so escape every "<" — the script only uses "<" inside string literals.
    st.html("<script>" + js.replace("<", "\\x3c") + "</script>", unsafe_allow_javascript=True)
