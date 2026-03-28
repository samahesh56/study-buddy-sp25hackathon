let scrollCount = 0;
let clickCount = 0;
let keystrokeCount = 0;

function sendActivity() {
  if (scrollCount === 0 && clickCount === 0 && keystrokeCount === 0 && document.visibilityState === "visible") {
    return;
  }

  chrome.runtime.sendMessage(
    {
      type: "content-activity",
      payload: {
        scroll_count: scrollCount,
        click_count: clickCount,
        keystroke_count: keystrokeCount,
        page_visible: document.visibilityState === "visible"
      }
    },
    () => chrome.runtime.lastError
  );

  scrollCount = 0;
  clickCount = 0;
  keystrokeCount = 0;
}

window.addEventListener(
  "scroll",
  () => {
    scrollCount += 1;
  },
  { passive: true }
);

window.addEventListener("click", () => {
  clickCount += 1;
});

window.addEventListener("keydown", () => {
  keystrokeCount += 1;
});

document.addEventListener("visibilitychange", sendActivity);
window.addEventListener("beforeunload", sendActivity);
setInterval(sendActivity, 5000);
