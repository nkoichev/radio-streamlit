"""App-wide skins (Неон, Аврора, Винил, Океан, Залез, Минимал), picked in the sidebar ("Тема").

Each skin is tied to a Streamlit base mode (Минимал = light): dark skins switch Streamlit to
Dark and light skins to Light (by clicking the ⋮ menu's theme item from JS — no reload, so a
password login survives), so native widgets, tables and charts stay readable. On top of that
the skin paints the page/sidebar background, the option_menu and the primary buttons, and
exposes --jb-* CSS variables that the Jukebox / Radio pages use for their cards.

The choice is remembered per browser (localStorage) and synced to Python through a CCv2
component, so option_menu colours and the injected CSS follow it.
"""
import streamlit as st

# key -> (label, base mode or None, CSS variables). "minimal" = plain Streamlit.
SKINS = {
    "neon": ("Неон", "dark", {
        "page": "radial-gradient(1100px 600px at 5% -10%, #3a1c71 0%, transparent 60%),"
                "radial-gradient(900px 500px at 105% 5%, #0f4c75 0%, transparent 60%),"
                "linear-gradient(160deg, #0b0b1a, #15112c 60%, #0b0b1a)",
        "sidebar": "#120f24", "accent": "#ff3cac", "accent2": "#2b86c5", "hover": "#3a2560",
        "card": "rgba(255,255,255,.05)", "border": "rgba(255,255,255,.10)", "btn": "rgba(255,255,255,.07)",
        "input": "rgba(255,255,255,.07)", "glow": "rgba(255,60,172,.45)",
        "text": "#f3f0ff", "muted": "rgba(243,240,255,.62)"}),
    "aurora": ("Аврора", "light", {
        "page": "linear-gradient(135deg, #e0c3fc 0%, #8ec5fc 35%, #c2f0e0 70%, #fbc2eb 100%)",
        "sidebar": "#f1ecfb", "accent": "#6a5cff", "accent2": "#ff6ec4", "hover": "#ddd6ff",
        "card": "rgba(255,255,255,.55)", "border": "rgba(255,255,255,.75)", "btn": "rgba(255,255,255,.65)",
        "input": "rgba(255,255,255,.75)", "glow": "rgba(106,92,255,.40)",
        "text": "#2a2540", "muted": "rgba(42,37,64,.62)"}),
    "vinyl": ("Винил", "dark", {
        "page": "radial-gradient(900px 500px at 85% -5%, rgba(255,138,61,.22), transparent 60%),"
                "linear-gradient(160deg, #1b1410, #2a1d15)",
        "sidebar": "#1f1712", "accent": "#ff8a3d", "accent2": "#ffd166", "hover": "#4a3222",
        "card": "rgba(255,236,210,.06)", "border": "rgba(255,200,150,.15)", "btn": "rgba(255,236,210,.08)",
        "input": "rgba(255,236,210,.08)", "glow": "rgba(255,138,61,.45)",
        "text": "#fbeee0", "muted": "rgba(251,238,224,.62)"}),
    "ocean": ("Океан", "dark", {
        "page": "radial-gradient(900px 600px at 0% 100%, rgba(0,224,198,.18), transparent 60%),"
                "linear-gradient(160deg, #021b2b, #03354a 55%, #04293a)",
        "sidebar": "#032131", "accent": "#00e0c6", "accent2": "#3a7bd5", "hover": "#0b4a5c",
        "card": "rgba(255,255,255,.05)", "border": "rgba(120,255,240,.16)", "btn": "rgba(255,255,255,.07)",
        "input": "rgba(255,255,255,.07)", "glow": "rgba(0,224,198,.40)",
        "text": "#e6fffb", "muted": "rgba(230,255,251,.62)"}),
    "sunset": ("Залез", "light", {
        "page": "linear-gradient(135deg, #fff1eb, #ffd6c9 45%, #ffc3d8)",
        "sidebar": "#fff0ea", "accent": "#ff5e62", "accent2": "#ff9966", "hover": "#ffd3c8",
        "card": "rgba(255,255,255,.6)", "border": "rgba(255,255,255,.85)", "btn": "rgba(255,255,255,.7)",
        "input": "rgba(255,255,255,.8)", "glow": "rgba(255,94,98,.40)",
        "text": "#3b2430", "muted": "rgba(59,36,48,.62)"}),
    "minimal": ("Минимал", "light", {}),  # always light (else it inherited the last Dark from the browser)
}
DEFAULT_SKIN = "aurora"
MINIMAL_ONLY_LOGINS = ()  # session_state keys that force Минимал (none in this app)
_KEY = "veas_theme"


def mode():
    return "dark" if st.context.theme.type == "dark" else "light"


def current():
    """(key, label, base mode, vars) of the active skin. The choice is mirrored in the URL
    (?skin=...), so a new session (the server dropped the idle one) keeps the skin from its
    first run - the picker's localStorage restore only works on a fresh page load."""
    if any(p in st.session_state for p in MINIMAL_ONLY_LOGINS):
        return ("minimal", *SKINS["minimal"])  # these logins have no "Тема" picker: plain Streamlit
    state = st.session_state.get(_KEY)
    key = state.get("skin") if isinstance(state, dict) else getattr(state, "skin", None)
    if key in SKINS:
        if st.query_params.get("skin") != key:
            st.query_params["skin"] = key
    else:
        key = st.query_params.get("skin")
        if key not in SKINS:
            key = DEFAULT_SKIN
    return (key, *SKINS[key])


def active():
    """CSS variables of the active skin, or None for Минимал."""
    return current()[3] or None


def menu_styles():
    """option_menu styles: the app's original colours for Минимал, the skin's otherwise."""
    v = active()
    dark = mode() == "dark"
    muted = "#9a9a9a" if dark else "#555555"
    if v is None:
        container, icon = ("#262730", "#555555") if dark else ("#F0F2F6", "#022fc4")
        hover, selected = ("#FF4B4B", "#FF4B4B") if dark else ("#b0dfff", "#027ed1")
    else:
        container, icon, hover = v["sidebar"], v["accent"], v["hover"]
        selected = v["accent"]
    return {
        "container": {"padding": "0!important", "background-color": container},
        "menu-title": {"font-size": "14px", "color": muted, "font-weight": "normal"},
        "menu-icon": {"font-size": "16px", "color": muted},
        "icon": {"color": icon, "font-size": "13px"},
        "nav-link": {"font-size": "13px", "text-align": "left", "margin": "0px", "--hover-color": hover},
        "nav-link-selected": {"background-color": selected},
    }


def apply_css():
    """Paint the active skin. No-op for Минимал. The style tag carries data-veas-skin so other
    pages' CSS can scope rules with html:has(style[data-veas-skin])."""
    v = active()
    if v is None:
        return
    props = ";".join(f"--jb-{k}:{val} !important" for k, val in v.items())
    head = f"linear-gradient(90deg,{v['accent']},{v['accent2']})"
    st.html(f"""<style data-veas-skin="{current()[0]}">
:root {{ {props}; --jb-head:{head} !important; }}
[data-testid="stApp"] {{ background: {v['page']} !important; background-attachment: fixed !important; }}
[data-testid="stMain"], [data-testid="stHeader"], [data-testid="stBottomBlockContainer"] {{ background: transparent !important; }}
[data-testid="stSidebar"], [data-testid="stSidebarContent"] {{ background: {v['sidebar']} !important; }}
button:is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]) {{
  background: linear-gradient(90deg, {v['accent']}, {v['accent2']}) !important; border: 0 !important; color: #fff !important;
}}
button:is([data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"]):hover {{ filter: brightness(1.08); }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{
  background: linear-gradient(90deg, {v['accent']}, {v['accent2']}) !important; color: #fff !important; border-color: transparent !important;
}}
</style>""")


_PICKER = st.components.v2.component(
    "veas_theme_picker",
    html="""
<div class="th">
  <button class="th-btn" type="button"><span class="th-dot"></span><span class="th-lbl"></span><span class="th-car">▾</span></button>
  <div class="th-grid"></div>
</div>
""",
    css="""
.th { font: 13px var(--st-font, "Source Sans Pro", sans-serif); color: var(--st-text-color); }
.th-btn { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 10px; cursor: pointer;
  border: 1px solid var(--st-border-color, rgba(128,128,128,.3)); border-radius: 10px;
  background: transparent; color: inherit; font: inherit; transition: transform .15s, box-shadow .2s; }
.th-btn:hover { border-color: var(--st-primary-color); transform: translateY(-1px); }
.th-dot { width: 14px; height: 14px; border-radius: 50%; flex: none; }
.th-lbl { flex: 1; text-align: left; }
.th-car { opacity: .6; }
.th-grid { display: none; grid-template-columns: repeat(2, 1fr); gap: 10px; padding: 10px 2px 2px; }
.th.open .th-grid { display: grid; }
.th-sw { display: flex; flex-direction: column; gap: 4px; cursor: pointer; border: 0; padding: 0;
  background: transparent; color: inherit; font: 600 11px inherit; transition: transform .15s; }
.th-sw:hover { transform: translateY(-2px); }
.th-sw b { display: block; height: 44px; border-radius: 9px; border: 1px solid rgba(128,128,128,.3);
  position: relative; overflow: hidden; }
.th-sw b::after { content: ""; position: absolute; left: 7px; right: 7px; bottom: 7px; height: 5px;
  border-radius: 3px; background: var(--g); }
.th-sw.on b { outline: 2px solid var(--st-primary-color); outline-offset: 2px; }
""",
    js="""
export default function ({ data, parentElement, setStateValue, setTriggerValue }) {
  const root = parentElement.querySelector(".th");
  const skins = data.skins;                         // [[key, label, mode, vars], ...]
  // always the latest data: the interval below outlives this call (Минимал's mode can change)
  const find = (k) => (root._data || data).skins.find((s) => s[0] === k);

  const isDark = () => {
    const c = getComputedStyle(root).getPropertyValue("--st-background-color").trim();
    let r, g, b;
    if (c.startsWith("#")) {
      const h = c.length === 4 ? c.slice(1).split("").map((x) => x + x).join("") : c.slice(1, 7);
      [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
    } else {
      const m = c.match(/\\d+(\\.\\d+)?/g); if (!m) return null;
      [r, g, b] = m.map(Number);
    }
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5;
  };
  // Switch Streamlit's Light/Dark through its own ⋮ menu (no page reload).
  const switchMode = async (want) => {
    const now = Date.now();
    if (root._switchAt && now - root._switchAt < 4000) return;
    root._switchAt = now;
    const btn = document.querySelector('[data-testid="stMainMenuButton"]');
    if (!btn) return;
    btn.click();
    for (let i = 0; i < 40; i++) {
      const it = document.querySelector('[data-testid="stMainMenuItem-theme-' + (want === "dark" ? "Dark" : "Light") + '"]');
      if (it) { it.click(); break; }
      await new Promise((r) => setTimeout(r, 25));
    }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  };

  // Keep Streamlit's mode in line with the skin, and rerun Python when the mode changed
  // (Streamlit itself doesn't rerun on a Light/Dark flip).
  root._data = data; root._trigger = setTriggerValue;
  if (!root._iv) {
    root._iv = setInterval(() => {
      const d = isDark(); if (d === null) return;
      const actual = d ? "dark" : "light";
      const skin = find(root._data.current);
      if (skin && skin[2] && skin[2] !== actual) { switchMode(skin[2]); return; }
      if (actual !== root._data.mode && root._asked !== actual) { root._asked = actual; root._trigger("mode", actual); }
      if (actual === root._data.mode) root._asked = null;
    }, 700);
  }

  // New session: restore this browser's choices into Python state.
  let saved = null;
  try { saved = localStorage.getItem("veasSkin"); } catch (e) {}
  if (!root.dataset.synced) {
    root.dataset.synced = "1";
    if (saved && saved !== data.current && find(saved)) setStateValue("skin", saved);
  }

  const cur = find(data.current) || skins[skins.length - 1];
  const grad = (v) => v.accent ? `linear-gradient(90deg, ${v.accent}, ${v.accent2})` : "var(--st-primary-color)";
  root.querySelector(".th-dot").style.background = grad(cur[3]);
  root.querySelector(".th-lbl").textContent = "Тема: " + cur[1];
  const grid = root.querySelector(".th-grid");
  grid.replaceChildren(...skins.map(([k, label, m, v]) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "th-sw" + (k === cur[0] ? " on" : ""); b.title = label;
    const sw = document.createElement("b");
    sw.style.background = v.page || "linear-gradient(135deg, #f0f2f6, #ffffff)";
    sw.style.setProperty("--g", grad(v));
    const t = document.createElement("span"); t.textContent = label;
    b.append(sw, t);
    b.onclick = () => {
      try { localStorage.setItem("veasSkin", k); } catch (e) {}
      root.classList.remove("open");
      if (m) switchMode(m);
      setStateValue("skin", k);
    };
    return b;
  }));
  root.querySelector(".th-btn").onclick = () => root.classList.toggle("open");
}
""",
)


def render_picker(hidden=False):
    """hidden=True: invisible, but still keeps Streamlit's Light/Dark in line with the skin
    (used for logins without a "Тема" picker, e.g. ВТ ДЗУ = always light Минимал)."""
    if hidden:
        st.html("<style>.st-key-veas_theme_hidden{display:none !important}</style>")
        with st.container(key="veas_theme_hidden"):
            return _mount_picker()
    return _mount_picker()


def _mount_picker():
    _PICKER(
        key=_KEY,
        data={
            "mode": mode(),
            "current": current()[0],
            "skins": [[k, label, m, v] for k, (label, m, v) in SKINS.items()],
        },
        default={"skin": None},
        on_skin_change=lambda: None,
        on_mode_change=lambda: None,  # trigger only exists to cause a rerun
    )
