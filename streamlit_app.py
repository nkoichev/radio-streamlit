"""Радио: онлайн радио с „Какво свири?“ (ICY метаданни / Shazam), за Streamlit Community Cloud."""
import streamlit as st

import radio
import themes

st.set_page_config(page_title="Радио", page_icon="📻", layout="wide")

themes.apply_css()  # palette chosen in the sidebar "Тема" picker
with st.sidebar:
    themes.render_picker()
    radio.render_player()  # floating player, injected on every run so it survives reruns

st.title("📻 Радио")
radio.render_station_picker()
