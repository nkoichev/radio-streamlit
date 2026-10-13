# Радио

Онлайн радио на Streamlit: станции по жанрове, плаващ плейър, теми и „Какво свири?“ —
изпълнител и песен на живо (от ICY информацията на станцията или чрез Shazam).

| Файл | Какво прави |
|---|---|
| `streamlit_app.py` | Входна точка: тема, плейър, списък със станции |
| `radio.py` | Станциите, плаващият плейър (JS извън React дървото на Streamlit) и „Какво свири?“ |
| `themes.py` | Темите (Неон, Аврора, Винил, Океан, Залез, Минимал) |
| `shazam_recognize.py` | Разпознаване на последните ~10 s звук с shazamio (subprocess) |
| `packages.txt` | `ffmpeg` (apt пакет за Streamlit Cloud, нужен на pydub) |

Само HTTPS потоци: Streamlit Cloud е по https и браузърът блокира http:// звук.

## Локално

```bash
pip install -r requirements.txt      # + ffmpeg в PATH
streamlit run streamlit_app.py
```

## Хостинг

Streamlit Community Cloud: <https://share.streamlit.io> → Create app → това репо, branch `main`,
main file `streamlit_app.py`. Всеки `git push` към `main` обновява приложението.
