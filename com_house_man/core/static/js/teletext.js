function pad(value) {
  return String(value).padStart(2, "0");
}

function updateClock() {
  const el = document.getElementById("tt-clock");
  if (!el) return;

  const now = new Date();
  const days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
  el.textContent = `${days[now.getDay()]} ${pad(now.getDate())} ${months[now.getMonth()]} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function renderSyncBar(data) {
  const bar = document.getElementById("tt-sync-bar");
  const percent = document.getElementById("tt-sync-percent");
  const synced = document.getElementById("tt-sync-synced");
  const pending = document.getElementById("tt-sync-pending");
  const failed = document.getElementById("tt-sync-failed");
  const count = document.getElementById("tt-company-count");

  if (!bar || !data) return;

  const blocks = 30;
  const filled = Math.round((data.percent / 100) * blocks);
  const failedBlocks = data.total ? Math.round((data.failed / data.total) * blocks) : 0;

  bar.innerHTML = "";
  for (let i = 0; i < blocks; i += 1) {
    const block = document.createElement("div");
    block.className = "tt-sync-block";
    if (i < filled) {
      block.classList.add("filled");
    } else if (i < filled + failedBlocks) {
      block.classList.add("failed");
    }
    bar.appendChild(block);
  }

  if (percent) percent.textContent = `${data.percent}%`;
  if (synced) synced.textContent = data.synced;
  if (pending) pending.textContent = data.pending;
  if (failed) failed.textContent = data.failed;
  if (count) count.textContent = data.total;
}

async function pollSyncStatus() {
  try {
    const response = await fetch("/api/sync-status/");
    if (!response.ok) return;
    const data = await response.json();
    renderSyncBar(data);
  } catch (_error) {
    // Keep last rendered values if polling fails.
  }
}

updateClock();
setInterval(updateClock, 30000);
pollSyncStatus();
setInterval(pollSyncStatus, 10000);

function initSicListFilter() {
  const filter = document.getElementById("sic-filter");
  const sicInput = document.getElementById("sic");
  const items = document.querySelectorAll(".tt-sic-item");
  if (!filter || !items.length) return;

  filter.addEventListener("input", () => {
    const query = filter.value.trim().toLowerCase();
    items.forEach((item) => {
      const haystack = (item.dataset.search || "").toLowerCase();
      item.hidden = Boolean(query && !haystack.includes(query));
    });
  });

  if (sicInput) {
    sicInput.addEventListener("input", () => {
      filter.value = sicInput.value;
      filter.dispatchEvent(new Event("input"));
    });
  }

  const active = document.querySelector(".tt-sic-item.active");
  if (active) {
    active.scrollIntoView({ block: "nearest" });
  }
}

document.addEventListener("DOMContentLoaded", initSicListFilter);
