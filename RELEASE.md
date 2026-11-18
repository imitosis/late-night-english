# Neue Version veröffentlichen

Bei jeder Änderung an `index.html` zwei Zahlen gemeinsam hochzählen, sonst sehen Handys mit der App auf dem Home-Bildschirm das Update nicht:

1. `version.json` → `{"v":"22"}`
2. `index.html` → `const BUILD='22'`
3. `sw.js` → `const V='lne-v22'`

Die App prüft beim Öffnen, ob es eine neue Version gibt, und zeigt dann oben „New version available · Tap to update".
