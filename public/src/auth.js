const form = document.getElementById("authForm");
const input = document.getElementById("authToken");
const notice = document.getElementById("authNotice");
const desktopButton = document.getElementById("desktopUnlock");

async function unlock(token) {
  const response = await fetch("/api/auth/session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Coven-Intent": "ui-action",
    },
    body: JSON.stringify({ token }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Unable to start session.");
  window.location.assign("/");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  notice.textContent = "Checking token...";
  notice.dataset.tone = "info";
  try {
    await unlock(input.value);
  } catch (error) {
    notice.textContent = error.message;
    notice.dataset.tone = "error";
  }
});

if (desktopButton) {
  desktopButton.hidden = !(window.pywebview?.api?.start_session);
  desktopButton.addEventListener("click", async () => {
    notice.textContent = "Requesting desktop session...";
    notice.dataset.tone = "info";
    try {
      const token = await window.pywebview.api.start_session();
      if (!token) throw new Error("The desktop bootstrap token was already used.");
      await unlock(token);
    } catch (error) {
      notice.textContent = error.message;
      notice.dataset.tone = "error";
    }
  });
}
