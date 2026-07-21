const form = document.querySelector("#uploadForm");
const fileInput = document.querySelector("#audioFile");
const fileName = document.querySelector("#fileName");
const uploadButton = document.querySelector("#uploadButton");
const statusText = document.querySelector("#statusText");
const statusDot = document.querySelector("#statusDot");
const errorBox = document.querySelector("#errorBox");
const results = document.querySelector("#results");
const healthBadge = document.querySelector("#healthBadge");

const statusLabels = {
  queued: "排队中",
  running: "正在分离",
  succeeded: "已完成",
  failed: "失败",
};

const trackNames = {
  vocals: "人声",
  drums: "鼓",
  bass: "贝斯",
  other: "其他",
};

let pollTimer = null;
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  fileName.textContent = file ? file.name : "支持 MP3、WAV、FLAC";
  clearError();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  results.replaceChildren();

  const file = fileInput.files[0];
  if (!file) {
    showError("请选择一个音频文件。");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  setBusy(true);
  setStatus("queued");

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "上传失败。");
    }
    setStatus(payload.status);
    startPolling(payload.job_id);
  } catch (error) {
    stopPolling();
    setBusy(false);
    setStatus("failed");
    showError(error.message || "上传失败。");
  }
});

checkHealth();

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const payload = await response.json();
    healthBadge.textContent = payload.status === "ok" ? "就绪" : "异常";
  } catch {
    healthBadge.textContent = "离线";
  }
}

function startPolling(jobId) {
  stopPolling();
  pollTimer = window.setInterval(() => pollJob(jobId), 1200);
  pollJob(jobId);
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function pollJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "查询失败。");
    }

    setStatus(payload.status);

    if (payload.status === "succeeded") {
      stopPolling();
      setBusy(false);
      renderTracks(payload.job_id, payload.outputs || {});
      return;
    }

    if (payload.status === "failed") {
      stopPolling();
      setBusy(false);
      showError(payload.error || "分离失败。");
    }
  } catch (error) {
    stopPolling();
    setBusy(false);
    setStatus("failed");
    showError(error.message || "查询失败。");
  }
}

function renderTracks(jobId, outputs) {
  results.replaceChildren();
  renderMixControls(jobId);
  Object.keys(trackNames).forEach((stem) => {
    const url = outputs[stem];
    if (!url) {
      return;
    }

    const card = document.createElement("article");
    card.className = "track-card";

    const title = document.createElement("h2");
    title.textContent = trackNames[stem];

    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = url;

    const link = document.createElement("a");
    link.className = "download-link";
    link.href = url;
    link.download = `${stem}.wav`;
    link.textContent = "下载";

    card.append(title, audio, link);
    results.append(card);
  });
}

function renderMixControls(jobId) {
  const panel = document.createElement("section");
  panel.className = "mix-panel";

  const header = document.createElement("div");
  header.className = "mix-header";

  const title = document.createElement("h2");
  title.textContent = "合并音轨";

  const button = document.createElement("button");
  button.className = "primary-button mix-button";
  button.type = "button";
  button.textContent = "生成合并音轨";

  header.append(title, button);

  const options = document.createElement("div");
  options.className = "mix-options";
  Object.keys(trackNames).forEach((stem) => {
    const label = document.createElement("label");
    label.className = "mix-option";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = stem;
    checkbox.checked = true;

    const text = document.createElement("span");
    text.textContent = trackNames[stem];

    label.append(checkbox, text);
    options.append(label);
  });

  const message = document.createElement("p");
  message.className = "mix-message";
  message.hidden = true;

  const output = document.createElement("div");
  output.className = "mix-output";
  output.hidden = true;

  const audio = document.createElement("audio");
  audio.controls = true;

  const link = document.createElement("a");
  link.className = "download-link";
  link.textContent = "下载合并音轨";

  output.append(audio, link);
  panel.append(header, options, message, output);
  results.append(panel);

  button.addEventListener("click", () => createMix(jobId, panel));
}

async function createMix(jobId, panel) {
  const button = panel.querySelector(".mix-button");
  const message = panel.querySelector(".mix-message");
  const output = panel.querySelector(".mix-output");
  const audio = output.querySelector("audio");
  const link = output.querySelector("a");
  const stems = Array.from(panel.querySelectorAll(".mix-option input:checked")).map((input) => input.value);

  if (stems.length === 0) {
    showMixMessage(message, "请至少选择一个音轨。");
    return;
  }

  button.disabled = true;
  showMixMessage(message, "正在生成合并音轨……");

  try {
    const response = await fetch(`/api/jobs/${jobId}/mixes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stems }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "生成合并音轨失败。");
    }

    audio.src = payload.play_url;
    audio.load();
    link.href = payload.download_url;
    link.download = `mix-${payload.stems.join("-")}.wav`;
    output.hidden = false;

    try {
      await audio.play();
      showMixMessage(message, "合并音轨已生成。");
    } catch {
      showMixMessage(message, "已生成，请点击播放器开始播放。");
    }
  } catch (error) {
    output.hidden = true;
    showMixMessage(message, error.message || "生成合并音轨失败。");
  } finally {
    button.disabled = false;
  }
}

function showMixMessage(message, text) {
  message.textContent = text;
  message.hidden = false;
}

function setBusy(isBusy) {
  uploadButton.disabled = isBusy;
  fileInput.disabled = isBusy;
}

function setStatus(status) {
  statusText.textContent = statusLabels[status] || "等待上传";
  statusDot.className = "status-dot";
  if (status === "succeeded") {
    statusDot.classList.add("done");
  } else if (status === "failed") {
    statusDot.classList.add("error");
  } else if (status === "queued" || status === "running") {
    statusDot.classList.add("active");
  } else {
    statusDot.classList.add("idle");
  }
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function clearError() {
  errorBox.textContent = "";
  errorBox.hidden = true;
}
