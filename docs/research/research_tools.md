# Research: tooling for a Windows, offline, Arabic-first AI onboarding assistant

Scope: Python 3.13 FastAPI backend (onnxruntime + multilingual-e5-small + BM25), Vite + React + TypeScript + Tailwind CSS 4 frontend built to static files served by FastAPI, Windows 11.

**Version rule applied:** every pin is a release dated on or before **28 Oct 2026** (at least 14 days before 11 Nov 2026). Where a newer release exists it is noted as "too new".

**Date source:** PyPI release dates were read from pypi.org history pages. npm release dates were read from GitHub release timestamps (`api.github.com/repos/<owner>/<repo>/releases`), because npmjs.com returned HTTP 403 and the registry document was too large to read. GitHub tag dates can differ from npm publish dates by about a day. Confirm the dates with `npm view <pkg> time --json` before committing lockfiles.

**Verification gaps (flagged where they occur):** `@fontsource/*` release dates, camel-tools' PyPI version, `@tailwindcss/vite` version, and the `winget` ID for the VC++ redistributable were not verified against a primary source.

---

## Summary of pins (copy-ready)

| Package | Pin | Released | Licence | Note |
|---|---|---|---|---|
| fastapi | 0.162.0 | 2026-10-23 | MIT | 0.162.1+ are 7 Nov or later (too new) |
| uvicorn | 0.54.0 | 2026-09-25 | BSD-3-Clause | |
| httpx | 0.28.1 | 2024-12-06 | BSD-3-Clause | Latest stable on PyPI; 1.0 exists only as dev builds |
| numpy | 2.5.4 | 2026-10-10 | BSD-3-Clause | Requires Python >=3.12 |
| onnxruntime | 1.31.1 | 2026-10-26 | MIT | cp313 win_amd64 wheel listed; 1.31.0 is the fallback |
| tokenizers | 0.23.3 | 2026-10-09 | Apache-2.0 | cp310-abi3 Windows wheel covers 3.13 |
| pydantic | 2.14.1 | 2026-10-11 | MIT | 2.14.2 is 29 Oct (too new) |
| pytest | 9.2.0 | 2026-10-27 | MIT | |
| ruff | 0.17.3 | 2026-10-27 | MIT | 0.17.4 is 5 Nov (too new) |
| mypy | 2.4.0 | 2026-10-01 | MIT | 2.4.1 is exactly 28 Oct (qualifies, borderline) |
| bm25s | 0.3.15 | 2026-10-22 | MIT | 0.3.16 is 28 Oct (qualifies, borderline) |
| playwright (Python) | 1.64.1 | 2026-10-22 (PyPI) | Apache-2.0 | GitHub tag dates 14 Oct; both qualify |
| vite | 8.3.5 | 2026-10-21 | MIT | 8.3.6 is 5 Nov (too new) |
| react, react-dom | 19.3.1 | 2026-10-14 | MIT | |
| typescript | 7.0.2 | 2026-08-20 | Apache-2.0 | 7.1-beta is a prerelease (20 Oct), not stable |
| tailwindcss | 4.3.3 | 2026-07-16 | MIT | 4.3.4 is 2 Nov (too new) |
| @tailwindcss/vite | 4.3.3 | same release train as tailwindcss | MIT | Verify the version exists on npm |
| vitest | 5.0.5 | 2026-10-15 | MIT | 5.1.0 is 2 Nov (too new) |
| @playwright/test | 1.64.1 | 2026-10-14 (GitHub) | Apache-2.0 | |
| @fontsource/ibm-plex-sans-arabic | 5.3.0 | UNVERIFIED | OFL-1.1 | Check the date with `npm view` |
| @fontsource/noto-sans-arabic | 5.3.0 | UNVERIFIED | OFL-1.1 | Check the date with `npm view` |

**Python 3.13 interpreter:** 3.13.17 (released 2026-10-21). Embeddable zip: `python-3.13.17-embed-amd64.zip`. Winget ID: `Python.Python.3.13`.

Exact pins use `==` in `requirements.txt`, for example `fastapi==0.162.0`.

---

## 1. Python BM25 (18 documents)

**Recommendation: hand-roll BM25 (about 25 lines, no dependency).** For 18 short documents, the library adds more risk than value.

| Option | Version and date | Licence | Maintenance | Dependencies | Windows / Py3.13 |
|---|---|---|---|---|---|
| rank_bm25 | 0.2.2, 2022-02-16 | Apache2.0 (per PyPI and setup.py) | One maintainer. No release in about 4 years. | numpy | Pure-Python wheel (py3-none-any). Installs on 3.13. |
| bm25s | 0.3.15 (safe) / 0.3.16 (28 Oct) | MIT | Active: 8 releases between Aug and Oct 2026. Provenance attestations. | numpy (optional extras for stemming, numba, etc.) | Pure-Python wheel (py3-none-any). Installs on 3.13. |
| Hand-rolled | n/a | Yours | n/a | None | No binaries |

Reasons for hand-rolling:
- The corpus is 18 documents, so the tiny extra code is cheaper to audit than a dependency.
- Zero dependencies. No numpy import, which keeps startup and the offline bundle small.
- rank_bm25 has been dormant since 2022. bm25s is maintained but brings a larger API surface than you need.

Sketch (Lucene-style idf, which stays non-negative):

```python
import math
from collections import Counter

def bm25_scores(query: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    n = len(docs)
    avgdl = sum(map(len, docs)) / n
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for q in query:
            f = tf.get(q, 0)
            if not f:
                continue
            idf = math.log((n - df[q] + 0.5) / (df[q] + 0.5) + 1)
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / avgdl))
        scores.append(s)
    return scores
```

Pitfalls:
- Tokenise after the Arabic normaliser from topic 2, so that query and document tokens match.
- If you use bm25s later, pin `numpy` explicitly. Its wheels track the Python minor version.

Sources:
- https://pypi.org/project/rank-bm25/ and https://pypi.org/project/rank-bm25/0.2.2/
- https://github.com/dorianbrown/rank_bm25 (setup.py: `install_requires=['numpy']`, `license='Apache2.0'`)
- https://pypi.org/project/bm25s/ and https://pypi.org/project/bm25s/#history

---

## 2. Arabic normalisation and light stemming

**Recommendation: hand-rolled normaliser plus light prefix and suffix stripping.** Do not use camel-tools, Farasa, or the GPL libraries in a bundled product.

| Option | Licence | Install weight and Windows status | Verdict |
|---|---|---|---|
| Hand-rolled normaliser | Yours | None | **Use.** |
| NLTK ISRI stemmer (`nltk.stem.isri`) | Apache-2.0 | `nltk` 3.10.4 (2026-10-21), pure Python, no data download | Usable if you want a stemmer. Root-based and aggressive. |
| PyArabic | GPL (per PyPI) | Latest 0.6.15 (2022-06-18). PyPI metadata is inconsistent (0.6.12 vs 0.6.15). Abandoned. | Avoid. GPL plus abandoned. |
| Tashaphyne | GPL (per PyPI) | 0.3.6 (2022-01-29) | Avoid. GPL plus abandoned. |
| camel-tools | GPL-3.0 | Needs the Rust compiler, and on Windows a PyTorch wheel index (`-f https://download.pytorch.org/whl/torch_stable.html`). Data via `camel_data`. Dialect ID not on Windows. Python 3.11 to 3.14. | Avoid. Too heavy, GPL. |
| Farasa (farasapy 0.1.1) | MIT wrapper, but Farasa itself is research-use only | Needs Java on PATH. Downloads about 200 MB of binaries on first use. | Avoid. Java and a runtime download break the offline bundle. |

Hand-rolled normaliser (apply to both queries and documents):
- Alef variants: `أ` (U+0623), `إ` (U+0625), `آ` (U+0622) and `ٱ` (U+0671) become `ا` (U+0627).
- `ى` (U+0649) becomes `ي` (U+064A).
- `ة` (U+0629) becomes `ه` (U+0647). Retrieval only, not for display.
- `ؤ` (U+0624) becomes `و`, and `ئ` (U+0626) becomes `ي`.
- Remove tashkeel: U+064B to U+0652, plus U+0670 (superscript alef) and tanween.
- Remove tatweel: U+0640.
- Lowercase Latin text and fold Arabic-Indic digits (U+0660 to U+0669) to ASCII digits.

Light stemming (prefix and suffix stripping, only when the remaining stem has at least 3 letters):
- Prefixes: `وال`, `بال`, `كال`, `فال`, `لل`, `ال`, then single `و`, `ب`, `ل`, `ف`, `ك`, `س` (only when followed by a verb form you rely on).
- Suffixes: `ها`, `ات`, `ون`, `ين`, `ان`, `ه`, `ة` (already folded to `ه`), `ي`.

Jordanian dialect and Arabizi are out of scope for these rules. Handle Arabizi with a separate token map if needed.

Pitfalls:
- Keep the original text for display. Apply the normaliser only to retrieval tokens.
- Normalise the query and the document with the same function, or recall drops silently.

Sources:
- https://pypi.org/project/nltk/ and https://www.nltk.org/api/nltk.stem.isri.html
- https://github.com/linuxscout/pyarabic (GPL-3.0 per the project page)
- https://pypi.org/project/tashaphyne/
- https://pypi.org/project/camel-tools/ and https://camel-tools.readthedocs.io/en/latest/getting_started.html
- https://pypi.org/project/farasapy/

---

## 3. Arabic number words to digits

**Recommendation: hand-roll a small parser.** No suitable library was found.

- `num2words` (0.5.14, Dec 2024, LGPL) supports Arabic but only converts digits to words. It does not parse words to digits.
- `word2number` and `word2number-en` are English-only.
- `tafqit-python` converts digits to words in the opposite direction.
- A web search for a text2num-style Arabic parser returned nothing usable.

Words to cover (masculine forms, with the common variants):

Units and teens:
- 0 صفر
- 1 واحد / واحدة
- 2 اثنان / اثنين / اتنين / اثنتان
- 3 ثلاثة / ثلاث / تلاتة (Jordanian)
- 4 أربعة / أربع / اربعة
- 5 خمسة / خمس
- 6 ستة / ست
- 7 سبعة / سبع
- 8 ثمانية / ثماني / ثمان / تمانية (Jordanian)
- 9 تسعة / تسع
- 10 عشرة / عشر
- 11 أحد عشر / احد عشر
- 12 اثنا عشر / اثني عشر / اتناشر
- 13 to 19 are "[unit] عشر"

Tens:
- 20 عشرون / عشرين
- 30 ثلاثون / ثلاثين / تلاتين
- 40 أربعون / أربعين
- 50 خمسون / خمسين
- 60 ستون / ستين
- 70 سبعون / سبعين
- 80 ثمانون / ثمانين / تمانين
- 90 تسعون / تسعين

Hundreds and thousands:
- 100 مائة / مئة / ميت / ميّة / مية
- 200 مائتان / ميتين
- 300 to 900: [unit] مائة (for example, ثلاثمائة)
- 1000 ألف; 2000 ألفين; 3000 to 10000: [unit] آلاف

Ordinals (feminine forms take ة):
- 1st الأول / الاول / الأولى
- 2nd الثاني / الثانية
- 3rd الثالث / الثالثة
- 4th الرابع / الرابعة
- 5th الخامس, 6th السادس, 7th السابع, 8th الثامن, 9th التاسع, 10th العاشر

Algorithm: split on whitespace and `و` (conjunction), normalise per topic 2, map tokens to values, then combine with `total += value` for units and tens, `total *= value` for `مائة` and `ألف`, and `total = (total + value)` for 100 to 900 groups. Test with "ثلاثة وتسعين" (93) and "الثاني عشر" (12th).

Sources:
- https://pypi.org/project/num2words/
- https://pypi.org/project/word2number-en/
- https://pypi.org/project/PyArabic/0.6.2 (search result; not verified for this purpose)

---

## 4. Frontend: RTL, font, chat UI, and versions

**RTL with Tailwind CSS 4 (verified against tailwindcss.com):**
- The `rtl:` and `ltr:` variants match `:dir(rtl)`, `[dir="rtl"]`, or `[dir="rtl"] *`. Example: `class="ltr:ml-3 rtl:mr-3"`.
- Set `dir` on `<html>` from the detected language (`ar` gives `rtl`). For mixed content, add `dir="auto"` to each message bubble.
- Prefer logical utilities (`ms-`, `me-`, `ps-`, `pe-`, `start-`, `end-`, `text-start`, `text-end`). These are expected in Tailwind v4 but the page fetched did not confirm them, so check against the docs.
- Mixed Arabic and Latin in one bubble: add `[unicode-bidi:plaintext]` (arbitrary property) or use `dir="auto"`.

**Arabic font (@fontsource):**
- IBM Plex Sans Arabic: `@fontsource/ibm-plex-sans-arabic`, OFL-1.1 (per fontsource.org). Pin 5.3.0 (date unverified).
- Noto Sans Arabic: `@fontsource/noto-sans-arabic`, OFL-1.1. Pin 5.3.0 (date unverified).
- Recommendation: IBM Plex Sans Arabic. Import only weights you use, for example `import '@fontsource/ibm-plex-sans-arabic/400.css'` and `.../700.css`. Fontsource CSS uses `unicode-range`, so only the subsets needed are downloaded.
- Install: `npm install -E @fontsource/ibm-plex-sans-arabic@5.3.0`.
- The fontsource.org pages did not show the install command or versions. Confirm with `npm view @fontsource/ibm-plex-sans-arabic time --json`.

**Chat UI component libraries:**
- No library was verified to support Arabic RTL well and to be actively maintained under an MIT or Apache licence. Results were MazadLive Chat (auction-focused), chatscope `@chatscope/chat-ui-kit-react` (MIT, RTL not confirmed), react-chat-elements (MIT, RTL not confirmed), and Syncfusion or Telerik (commercial).
- **Recommendation: hand-build.** A chat UI needs a message list, bubbles, an input, and a typing indicator, which is about 150 to 250 lines of Tailwind. Set `dir="auto"` on bubbles and use logical utilities.

**Exact versions (see the summary table):** vite 8.3.5, react and react-dom 19.3.1, typescript 7.0.2, tailwindcss 4.3.3, @tailwindcss/vite 4.3.3 (verify), vitest 5.0.5, @playwright/test 1.64.1.

Install commands:
```
npm install -E -D vite@8.3.5 typescript@7.0.2 tailwindcss@4.3.3 @tailwindcss/vite@4.3.3 vitest@5.0.5 @playwright/test@1.64.1
npm install -E react@19.3.1 react-dom@19.3.1
npm install -E @fontsource/ibm-plex-sans-arabic@5.3.0
```

Pitfalls:
- Vite 8 and Vitest 5 may need compatible Node versions. Check `engines` with `npm view vite@8.3.5 engines`.
- TypeScript 7 is a native port. If a plugin does not support it, fall back to the latest 6.x.
- Do not use `@tailwindcss/vite` and `@tailwindcss/postcss` together.

Sources:
- https://tailwindcss.com/docs/hover-focus-and-other-states (RTL and LTR variants)
- https://fontsource.org/fonts/ibm-plex-sans-arabic and https://fontsource.org/fonts/noto-sans-arabic (OFL-1.1)
- https://www.npmjs.com/package/@chatscope/chat-ui-kit-react (not reachable: 403)
- https://github.com/vitejs/vite/releases, https://github.com/facebook/react/releases, https://github.com/microsoft/TypeScript/releases, https://github.com/tailwindlabs/tailwindcss/releases, https://github.com/vitest-dev/vitest/releases, https://github.com/microsoft/playwright/releases

---

## 5. Backend versions and SPA serving

**Versions (PyPI, dated on or before 28 Oct 2026):**
- fastapi 0.162.0 (2026-10-23), requires Python >=3.10, MIT. Newer 0.162.x are from 7 Nov.
- uvicorn 0.54.0 (2026-09-25), requires Python >=3.10, BSD-3-Clause.
- httpx 0.28.1 (2024-12-06), BSD-3-Clause. The 1.0 line is only in dev builds (1.0.dev1 to dev6).
- numpy 2.5.4 (2026-10-10), requires Python >=3.12, BSD-3-Clause. Do not use numpy 2.x releases that are newer than this.
- onnxruntime 1.31.1 (2026-10-26), requires Python >=3.11, MIT. The cp313 win_amd64 wheel (14.9 MB) is listed. Fallback 1.31.0 (2026-10-09). Use `onnxruntime` (CPU), not `onnxruntime-gpu`.
- tokenizers 0.23.3 (2026-10-09), requires Python >=3.10, Apache-2.0. The Windows x86-64 wheel is `cp310-abi3`, which installs on 3.13. A cp313-specific wheel was not listed.
- pydantic 2.14.1 (2026-10-11), MIT.
- pytest 9.2.0 (2026-10-27), requires Python >=3.10, MIT.
- ruff 0.17.3 (2026-10-27), MIT.
- mypy 2.4.0 (2026-10-01), MIT. 2.4.1 (2026-10-28) qualifies at exactly 14 days.

Install command (Python 3.13 venv):
```
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install fastapi==0.162.0 uvicorn==0.54.0 httpx==0.28.1 numpy==2.5.4 onnxruntime==1.31.1 tokenizers==0.23.3 pydantic==2.14.1
.venv\Scripts\python.exe -m pip install pytest==9.2.0 ruff==0.17.3 mypy==2.4.0 bm25s==0.3.15
```
(Omit bm25s if you hand-roll BM25, as recommended in topic 1.)

**Serving the SPA from FastAPI:**
- Build the frontend to `dist/`. Keep API routes under `/api`.
- The current FastAPI documentation says to use `app.frontend()` instead of `StaticFiles` for frontends. It serves files from `directory`, checks path operations first, and supports `fallback="index.html"`. The fallback applies only to `GET` and `HEAD` requests that accept HTML. Missing assets still return 404.
- The docs do not say which FastAPI version introduced `app.frontend()`. **Check that 0.162.0 has it** before relying on it, for example with `python -c "import fastapi; print(hasattr(fastapi.FastAPI, 'frontend'))"`.
- If `app.frontend()` is missing in 0.162.0, the fallback pattern is: mount `StaticFiles(directory="dist", html=True)` at `/` after all API routers so that API routes match first, and add an exception handler for 404 that returns `dist/index.html` for `GET` requests with `Accept: text/html`.
- Do not mount `StaticFiles` before the API routers, or it will swallow `/api` requests.

Pitfalls:
- `httpx` is required by `fastapi.testclient`, so keep it in dev requirements.
- If onnxruntime fails to import, see topic 6 (VC++ runtime).

Sources:
- https://pypi.org/project/fastapi/#history and https://fastapi.tiangolo.com/tutorial/static-files/
- https://fastapi.tiangolo.com/tutorial/frontend/ (`app.frontend()`, fallback rules)
- https://pypi.org/project/onnxruntime/ and https://onnxruntime.ai/docs/get-started/with-python.html (`pip install onnxruntime` for CPU; onnxruntime-gpu for CUDA)
- https://pypi.org/project/tokenizers/#history
- https://pypi.org/project/uvicorn/, https://pypi.org/project/httpx/, https://pypi.org/project/numpy/#history, https://pypi.org/project/pydantic/#history, https://pypi.org/project/pytest/#history, https://pypi.org/project/ruff/#history, https://pypi.org/project/mypy/#history

---

## 6. Windows one-command launcher

**Recommendation:**
- **Development and demo:** a venv in the project folder, started by `start.bat` that uses `%~dp0` so it works from any working directory.
- **Shipped portable bundle:** the Python 3.13.17 embeddable zip (`python-3.13.17-embed-amd64.zip`, released 2026-10-21) with dependencies installed into `Lib\site-packages` next to it.

Why a `.bat` rather than a `.ps1`: PowerShell's default execution policy on Windows 11 blocks unsigned `.ps1` files, so a double-click needs a policy change. A `.bat` does not.

Example `start.bat`:
```bat
@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv || goto :err
  .venv\Scripts\python.exe -m pip install -r requirements.txt || goto :err
)
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof
:err
echo Setup failed. See the messages above.
pause
```

Embeddable distribution notes (from docs.python.org):
- It is isolated from the user's system and includes no pip.
- `python313._pth` restricts the search path. Uncomment or add `import site` and add the package directory so `Lib\site-packages` is searched.
- Install packages with a full Python 3.13 into a target directory: `py -3.13 -m pip install --target <bundle>\Lib\site-packages -r requirements.txt`. Do this on the same architecture (win_amd64).

Winget:
- Python: `winget install -e --id Python.Python.3.13` (ID confirmed by a catalogue search). Use `winget search Python.Python` to confirm the current ID.
- VC++ runtime: `winget install -e --id Microsoft.VCRedist.2015+.x64` is the commonly used ID. This was not verified against winget's own listing, so run `winget search VCRedist` first.

Pitfalls:
- **Microsoft Store stub:** `python` can open the Store or give "command not found". Disable "Python (default)" under **Manage app execution aliases** or use `py -3.13`. Per python.org, the `py` launcher is superseded by the Python Install Manager from 3.14. The legacy launcher can shadow the new one; uninstall "Python launcher" if `py` gives a "can't open file" error.
- **Execution policy:** blocks `.ps1` by default. A `.bat` avoids it. If you need PowerShell, use `powershell -ExecutionPolicy Bypass -File start.ps1` from the `.bat`.
- **Long paths:** Windows limits paths to 260 characters by default. To lift the limit, set `LongPathsEnabled` to `1` under `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem` (admin and reboot required per python.org). Alternatively keep the project path short, for example `C:\CampusBot\`.
- **VC++ runtime:** onnxruntime on Windows can fail with `DLL load failed while importing onnxruntime_pybind11_state` when the Visual C++ runtime is missing. Install the x64 VC++ 2015–2022 redistributable and restart. Read the full error for a named missing DLL (for example a CUDA or cuDNN file) if it persists.
- **Venv is not relocatable:** the `.venv` contains absolute paths. Do not copy it to another machine. Use the embeddable bundle for distribution.
- Confirm `.venv\Scripts\python.exe -c "import onnxruntime"` succeeds before you rely on the launcher.

Sources:
- https://docs.python.org/3/using/windows.html (py launcher, Store alias, PATH, MAX_PATH; ._pth and embeddable section)
- https://www.python.org/downloads/windows/ (3.13.17, 2026-10-21, embeddable zip)
- https://learn.microsoft.com/windows/python (winget, Microsoft guidance)
- https://onnxruntime.ai/docs/get-started/with-python.html
- https://winstall.app/apps/Python.Python.3.13 (winget ID)

---

## 7. Python Playwright vs Node Playwright (screenshot smoke test)

**Recommendation: Python Playwright (`playwright==1.64.1`).** Reasons:
- The backend and the test run on the same Python 3.13 interpreter, so the smoke test does not need Node at runtime.
- The shipped bundle needs no Node. Node is only needed to build the frontend.
- Node Playwright (`@playwright/test@1.64.1`) is better if you want the built-in test runner and `expect` for many UI tests. For one screenshot smoke test, Python is simpler.

Install (Python):
```
.venv\Scripts\python.exe -m pip install playwright==1.64.1
.venv\Scripts\python.exe -m playwright install chromium
```

Example:
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto("http://127.0.0.1:8000/")
    page.screenshot(path="smoke.png", full_page=True)
    browser.close()
```

Facts verified:
- Python Playwright requires Python 3.10 or later. Windows 11 is supported.
- Browsers are stored at `%USERPROFILE%\AppData\Local\ms-playwright` by default. Change this with `PLAYWRIGHT_BROWSERS_PATH` before installing (PowerShell: `$Env:PLAYWRIGHT_BROWSERS_PATH="$Env:USERPROFILE\pw-browsers"`).
- `playwright install --with-deps` is documented for Linux. Do not rely on it on Windows.
- Node Playwright: Node 22, 24, or 26 required. Install with `npm init playwright@latest`; browsers with `npx playwright install`.

Pitfalls:
- The browser download is large. Install it once on the build machine if the bundle must be offline.
- For an offline smoke test, you can use the installed Microsoft Edge (Chromium) through `launch(channel="msedge")`. This is from Playwright's documented channels, not from a page fetched in this research, so test it.
- Pin the Playwright version to match the browser build. Mismatched versions fail with "Executable doesn't exist".

Sources:
- https://playwright.dev/python/docs/intro
- https://playwright.dev/python/docs/browsers
- https://playwright.dev/docs/intro (Node Playwright install and Node versions)
- https://pypi.org/project/playwright/#history (1.64.1 on 2026-10-22; Apache-2.0; Python >=3.10)

---

## Open items before committing

1. Confirm fontsource release dates with `npm view @fontsource/ibm-plex-sans-arabic time --json`.
2. Confirm `@tailwindcss/vite@4.3.3` exists on npm.
3. Confirm `app.frontend()` exists in fastapi 0.162.0.
4. Confirm the `winget` ID for the VC++ redistributable.
5. Run `npm view <pkg> time --json` for all npm pins, because GitHub tag dates can differ from publish dates by a day.
