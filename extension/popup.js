function send(message) {
  return chrome.runtime.sendMessage(message);
}

async function refresh() {
  const state = await send({ type: "popup:get-state" });
  document.getElementById("backend-url").value = state.backendBaseUrl || "";
  document.getElementById("status").textContent = JSON.stringify(state, null, 2);
}

async function runAction(action) {
  const result = await action();
  if (!result?.ok && result?.error) {
    alert(result.error);
  }
  await refresh();
}

document.getElementById("save-config").addEventListener("click", async () => {
  const backendBaseUrl = document.getElementById("backend-url").value.trim();
  await runAction(() => send({ type: "popup:set-backend-url", backendBaseUrl }));
});

document.getElementById("sync-session").addEventListener("click", async () => {
  await runAction(() => send({ type: "popup:sync-session" }));
});

document.getElementById("start-session").addEventListener("click", async () => {
  const userId = document.getElementById("user-id").value.trim();
  await runAction(() => send({ type: "popup:start-session", userId }));
});

document.getElementById("stop-session").addEventListener("click", async () => {
  await runAction(() => send({ type: "popup:stop-session" }));
});

document.getElementById("flush-queue").addEventListener("click", async () => {
  await runAction(() => send({ type: "popup:flush-queue" }));
});

document.getElementById("import-canvas").addEventListener("click", async () => {
  const userId = document.getElementById("user-id").value.trim();
  await runAction(() => send({ type: "popup:import-canvas-courses", userId }));
});

refresh();
