# TT Monitor
1. backend/projects.json: put each project's real URL (optional "path": "/health", "expect": "text that must appear").
2. cp backend/.env.example backend/.env and fill it in (DASH_PASSWORD, MYSQL_URL, SECRET_KEY).
3. Backend: cd backend && pip install -r requirements.txt && python app.py   (port 5000)
4. Frontend (dev): cd frontend && npm install && npm run dev -> http://localhost:5173
5. Deploy: npm run build in frontend; Flask then serves frontend/dist. Start command: gunicorn app:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT
   Keep --workers 1 so only one background checker runs.

## Usage tracking (visitors, clicks, downloads, installs)
Websites: add this one line before </body> (use the project key from projects.json):
  <script src="https://YOUR-MONITOR-URL/t.js" data-project="skynnews" defer></script>
It counts page views, unique visitors and clicks on links/buttons automatically.
Add data-track="Label" to a link to name it, and data-download to count a download link
(links ending in .apk .ipa .exe .dmg .zip .pdf are counted as downloads automatically).

Counted download links: list them in projects.json, e.g. "downloads": {"android": "https://play.google.com/..."},
then share https://YOUR-MONITOR-URL/d/ttmemory/android - each click is counted, then redirects to the store.

Mobile apps: call this on app open (type "view") and first launch (type "install"):
  POST https://YOUR-MONITOR-URL/api/track   body: {"project":"orepay","type":"install","vid":"<random id saved on the device>"}
