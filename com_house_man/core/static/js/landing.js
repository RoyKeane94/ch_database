const screenEl = document.getElementById("screen");
const staticEl = document.getElementById("static");
const config = window.COFAX || {};
const URLS = config.urls || {};
const LIVE_ENDPOINT = config.live_endpoint || "/api/cofax/live/";

const FALLBACK = {
  weather: {
    text: "RICHMOND 18C — SUNNY INTERVALS",
    page: "401",
    url: "https://www.bbc.co.uk/weather/2647428",
  },
  headline: {
    text: "AWAITING SIGNAL FROM BBC",
    page: "201",
    url: "https://www.bbc.co.uk/news",
  },
  ftse: { value: "8,412", change: 0.4, page: "220" },
  tfl_lines: [
    {
      tag: "DISTRICT",
      text: "SORRY, WE'RE NOT QUITE SURE. LET US SPEAK TO SADIQ",
      page: "430",
      url: "https://tfl.gov.uk/tube/status/#district-line",
    },
    { tag: "OVERGROUND", text: "OVERGROUND LINE: GOOD SERVICE", page: "431", url: "https://tfl.gov.uk/tube/status/#overground-line" },
    { tag: "PICCADILLY", text: "PICCADILLY LINE: GOOD SERVICE", page: "432", url: "https://tfl.gov.uk/tube/status/#piccadilly-line" },
    { tag: "CENTRAL", text: "CENTRAL LINE: GOOD SERVICE", page: "433", url: "https://tfl.gov.uk/tube/status/#central-line" },
    { tag: "NORTHERN", text: "NORTHERN LINE: GOOD SERVICE", page: "434", url: "https://tfl.gov.uk/tube/status/#northern-line" },
    { tag: "JUBILEE", text: "JUBILEE LINE: GOOD SERVICE", page: "435", url: "https://tfl.gov.uk/tube/status/#jubilee-line" },
  ],
  currency: { text: "£1 = $1.27 / €1.17", page: "240" },
  football: {
    text: "AWAITING FOOTBALL HEADLINES",
    page: "302",
    url: "https://www.bbc.co.uk/sport/football",
  },
  on_this_day: {
    text: "1986: M25 COMPLETED",
    page: "455",
    url: "https://en.wikipedia.org/wiki/On_this_day",
  },
  stats: { total: "0", active: "0", new_this_week: "0" },
  ticker: "KEY 101 TO SEARCH THE REGISTER +++ UPLOAD CSV ON PAGE 103 +++",
};

let live = { ...FALLBACK };

function pad(n) {
  return String(n).padStart(2, "0");
}

function clock() {
  const n = new Date();
  const d = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return {
    top: `${d[n.getDay()]}${n.getDate()} ${m[n.getMonth()]}`,
    time: `${pad(n.getHours())}${pad(n.getMinutes())}:${pad(n.getSeconds())}`,
  };
}

function esc(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function ftseRow(f) {
  const up = f.change >= 0;
  const arrow = up ? "▲" : "▼";
  const cls = up ? "up" : "dn";
  const sign = up ? "+" : "";
  return `${esc(f.value)} <span class="${cls}">${arrow} ${sign}${f.change}%</span>`;
}

function liveVal(item, fallback) {
  const row = item || fallback;
  const text = esc(row.text);
  if (row.url) {
    return `<a class="lr-link" href="${esc(row.url)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  }
  return text;
}

function liveRow(tag, item, fallback) {
  const row = item || fallback;
  return `
  <div class="live-row">
    <span class="lr-tag">${esc(tag)}</span>
    <span class="lr-val">${liveVal(row, fallback)}</span>
    <span class="lr-pg">${esc(row.page)}</span>
  </div>`;
}

function tflRows() {
  const lines = live.tfl_lines || FALLBACK.tfl_lines;
  return lines
    .map((line) => liveRow(line.tag || "TUBE", line, FALLBACK.tfl_lines[0]))
    .join("");
}

function landingHTML() {
  const c = clock();
  const stats = live.stats || FALLBACK.stats;
  const newCount = stats.new_this_week || "0";

  return `
  <div class="hdr">
    <span class="hw">P100</span><span class="hw">COFAX 100</span>
    <span class="hw">${c.top}</span><span class="hy">CH</span>
    <span class="hy" id="hdr-time">${c.time}</span>
  </div>
  <div class="mast" aria-hidden="true">
    <div class="mast-block mb-red">CH</div>
    <div class="mast-block mb-grn">COFAX</div>
    <div class="mast-block mb-red">CH</div>
  </div>
  <div class="dotbar"><div class="dotbar-inner"></div></div>
  <div class="headline">${esc(newCount)} new incorporations this week <a href="${esc(URLS.newest || "#")}">140</a></div>
  <div class="dotbar"><div class="dotbar-inner"></div></div>
  <nav class="idx" aria-label="Page index">
    <a class="idx-row" href="${esc(URLS.search || "#")}"><span class="il">SEARCH</span><span class="id">.........</span><span class="in">101</span></a>
    <a class="idx-row" href="${esc(URLS.active || "#")}"><span class="il">ACTIVE COS</span><span class="id">....</span><span class="in">120</span></a>
    <a class="idx-row" href="${esc(URLS.by_status || "#")}"><span class="il">BY STATUS</span><span class="id">......</span><span class="in">102</span></a>
    <a class="idx-row" href="${esc(URLS.dissolved || "#")}"><span class="il">DISSOLVED</span><span class="id">.....</span><span class="in">130</span></a>
    <a class="idx-row" href="${esc(URLS.upload || "#")}"><span class="il">UPLOAD CSV</span><span class="id">.....</span><span class="in">103</span></a>
    <a class="idx-row" href="${esc(URLS.newest || "#")}"><span class="il">NEW THIS WK</span><span class="id">...</span><span class="in">140</span></a>
    <a class="idx-row" href="${esc(URLS.account_type || "#")}"><span class="il">BY ACCT TYPE</span><span class="id">...</span><span class="in">104</span></a>
    <a class="idx-row" href="${esc(URLS.stats || "#")}"><span class="il">CHRG HOLDERS</span><span class="id">...</span><span class="in">150</span></a>
    <a class="idx-row" href="${esc(URLS.incorporated || "#")}"><span class="il">BY DATE INC</span><span class="id">....</span><span class="in">105</span></a>
    <a class="idx-row" href="${esc(URLS.directors || "#")}"><span class="il">DIRECTORS</span><span class="id">.....</span><span class="in">160</span></a>
    <a class="idx-row" href="${esc(URLS.with_charges || "#")}"><span class="il">WITH CHARGES</span><span class="id">...</span><span class="in">171</span></a>
  </nav>
  <div class="az">CHARGE HOLDERS . <a href="${esc(URLS.index || "#")}"><span>150</span></a></div>
  <div class="live-hdr"><div class="dseg"></div><span class="lt">LIVE FROM THE BBC:</span><div class="dseg"></div></div>
  ${liveRow("WEATHER", live.weather, FALLBACK.weather)}
  ${liveRow("TOP STORY", live.headline, FALLBACK.headline)}
  <div class="live-row"><span class="lr-tag">FTSE 100</span><span class="lr-val">${ftseRow(live.ftse || FALLBACK.ftse)}</span><span class="lr-pg">${esc((live.ftse || FALLBACK.ftse).page)}</span></div>
  <div class="live-hdr"><div class="dseg"></div><span class="lt">LONDON &amp; BEYOND:</span><div class="dseg"></div></div>
  ${tflRows()}
  ${liveRow("CURRENCY", live.currency, FALLBACK.currency)}
  ${liveRow("FOOTBALL", live.football, FALLBACK.football)}
  ${liveRow("ON THIS DAY", live.on_this_day, FALLBACK.on_this_day)}
  <div class="dotbar"><div class="dotbar-inner"></div></div>
  <div class="tick-wrap"><div class="tick">${esc(live.ticker || FALLBACK.ticker)}</div></div>
  <button class="advert" type="button" onclick="location.href='${esc(URLS.holidays || "#")}'">
    <span class="ad-a">MALAGA 7 NTS £150</span>
    <span class="ad-b">WITH SUN VOUCHERS!</span>
    <span class="ad-c">see p175</span>
  </button>
  <div class="fastwords">
    <a class="fw fw-r" href="${esc(URLS.search || "#")}">Search</a>
    <a class="fw fw-g" href="${esc(URLS.upload || "#")}">Upload</a>
    <a class="fw fw-y" href="${esc(URLS.bbc_news || "https://www.bbc.co.uk/news")}" target="_blank" rel="noopener noreferrer">News</a>
    <a class="fw fw-c" href="${esc(URLS.bbc_weather || "https://www.bbc.co.uk/weather/2647428")}" target="_blank" rel="noopener noreferrer">Weather</a>
  </div>`;
}

function boot() {
  screenEl.innerHTML = "";
  staticEl.classList.add("on");
  setTimeout(() => {
    staticEl.classList.remove("on");
    huntPages();
  }, 700);
}

function huntPages() {
  let p = 347;
  const c = clock();
  screenEl.innerHTML = `
    <div class="hdr"><span class="hw" id="hunt-num">P347</span><span class="hw">COFAX</span><span class="hy">${c.time}</span></div>
    <div class="hunt-stage">
      <div class="row"><span class="g dh">SEARCHING FOR PAGE 100</span></div>
      <div class="row" style="margin-top:10px"><span class="c" id="hunt-big" style="font-size:64px">P347</span></div>
      <div class="row" style="margin-top:10px"><span class="y blink">PLEASE WAIT — PAGE IS IN THE CAROUSEL</span></div>
      <div class="row" style="margin-top:30px"><span class="k">TIP: PAGES ROTATE EVERY 25 SECONDS.</span></div>
      <div class="row"><span class="k">IN 1986 YOU JUST HAD TO SIT THERE.</span></div>
    </div>`;
  const big = document.getElementById("hunt-big");
  const small = document.getElementById("hunt-num");
  const iv = setInterval(() => {
    p -= Math.floor(Math.random() * 18) + 9;
    if (p <= 100) {
      p = 100;
      big.textContent = "P100";
      small.textContent = "P100";
      clearInterval(iv);
      setTimeout(rowReveal, 350);
    } else {
      big.textContent = `P${p}`;
      small.textContent = `P${p}`;
    }
  }, 120);
}

function rowReveal() {
  screenEl.innerHTML = landingHTML();
  const rows = Array.from(screenEl.children);
  rows.forEach((r) => r.classList.add("hidden-row"));
  let i = 0;
  const iv = setInterval(() => {
    if (i >= rows.length) {
      clearInterval(iv);
      return;
    }
    rows[i].classList.remove("hidden-row");
    i += 1;
  }, 85);
}

setInterval(() => {
  const t = document.getElementById("hdr-time");
  if (t) {
    t.textContent = clock().time;
  }
}, 1000);

async function loadLive() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const response = await fetch(LIVE_ENDPOINT, { signal: controller.signal });
    clearTimeout(timeout);
    if (response.ok) {
      const data = await response.json();
      live = { ...FALLBACK, ...data };
      if (!live.stats) {
        live.stats = FALLBACK.stats;
      }
    }
  } catch (_error) {
    // Broadcast continues on fallback data.
  }
  boot();
}

loadLive();

setInterval(async () => {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const response = await fetch(LIVE_ENDPOINT, { signal: controller.signal });
    clearTimeout(timeout);
    if (response.ok) {
      live = { ...FALLBACK, ...(await response.json()) };
      if (document.querySelector(".live-row")) {
        screenEl.innerHTML = landingHTML();
      }
    }
  } catch (_error) {
    // Keep last broadcast.
  }
}, 600000);
