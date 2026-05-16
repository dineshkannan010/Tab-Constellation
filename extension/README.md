# Tab Constellation — Extension

Manifest V3 Chrome extension. Clicking the toolbar icon opens the web app
at `http://localhost:5173` in a new tab.

## Load it unpacked

1. Open Chrome and go to `chrome://extensions`.
2. Toggle **Developer mode** on (top right).
3. Click **Load unpacked**.
4. Select this `extension/` folder.
5. The Tab Constellation icon appears in the toolbar.

## Reload after changes

After editing `manifest.json` or `background.js`, return to
`chrome://extensions` and click the reload icon on the Tab Constellation card.

## Files

- `manifest.json` — Manifest V3 declaration (permissions: `tabs`)
- `background.js` — service worker; opens the web app on icon click
- `icons/` — toolbar icons (16/32/48/128 px) plus the source `icon.svg`
