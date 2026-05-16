const APP_URL = "http://localhost:5173";

chrome.action.onClicked.addListener(() => {
  chrome.tabs.create({ url: APP_URL });
});
