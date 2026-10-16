/* Плеер для выпусков из episodes.json. Без зависимостей, работает со static-хостинга. */
(() => {
  "use strict";

  const STORE_KEY = "lorielee-player-v1";
  const $ = (id) => document.getElementById(id);

  const audio = $("audio");
  const player = $("player");
  const episodeList = $("episode-list");
  const episodeNote = $("episodes-note");
  const episodeSub = $("episode-sub");
  const chapterList = $("chapter-list");
  const nowEpisode = $("now-episode");
  const nowChapter = $("now-chapter");
  const scrub = $("scrub");
  const timeCur = $("time-cur");
  const timeDur = $("time-dur");
  const toggleBtn = $("toggle");
  const speedBtn = $("speed");

  const SPEEDS = [1, 1.25, 1.5, 1.75, 2, 0.75];

  let episodes = [];
  let current = null; // выбранный выпуск
  let state = load();

  function load() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
      return {
        episodeId: typeof raw.episodeId === "string" ? raw.episodeId : null,
        position: Number.isFinite(raw.position) ? raw.position : 0,
        speed: SPEEDS.includes(raw.speed) ? raw.speed : 1,
      };
    } catch {
      return { episodeId: null, position: 0, speed: 1 };
    }
  }

  function save() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(state));
    } catch { /* приватный режим — просто не запоминаем */ }
  }

  const fmt = (s) => {
    if (!Number.isFinite(s) || s < 0) s = 0;
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ":" + String(sec).padStart(2, "0");
  };

  const statusLabel = {
    ready: "готов",
    planned: "записывается",
    partial: "частично",
  };

  function playable(ep) {
    return ep.status === "ready" || ep.status === "partial";
  }

  function renderEpisodes() {
    episodeList.textContent = "";
    const available = episodes.filter(playable);
    for (const ep of episodes) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "episode";
      btn.disabled = !playable(ep);
      btn.dataset.id = ep.id;

      const title = document.createElement("span");
      title.className = "episode-title";
      title.textContent = ep.title;

      const sub = document.createElement("span");
      sub.className = "episode-sub";
      const chapters = ep.chapters ? ep.chapters.length : 0;
      sub.textContent = [fmt(ep.duration || 0), chapters + " гл."].join(" · ");

      const badge = document.createElement("span");
      badge.className = "badge " + (playable(ep) ? "ready" : "planned");
      badge.textContent = statusLabel[ep.status] || ep.status;

      btn.append(title, sub, badge);
      btn.addEventListener("click", () => selectEpisode(ep.id));
      li.appendChild(btn);
      episodeList.appendChild(li);
    }
    const hidden = episodes.length - available.length;
    episodeNote.textContent = hidden
      ? hidden + " выпуск(а) ещё записываются и появятся здесь же, как только будет готово аудио."
      : "";
    if (current) {
      const active = episodeList.querySelector('[data-id="' + current.id + '"]');
      if (active) active.setAttribute("aria-current", "true");
    }
  }

  function renderChapters() {
    chapterList.textContent = "";
    if (!current) return;
    episodeSub.textContent = current.description || "";
    const chapters = current.chapters || [];
    if (!chapters.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "Главы появятся после записи.";
      chapterList.appendChild(li);
      return;
    }
    for (const ch of chapters) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chapter";
      btn.dataset.start = String(ch.start);

      const num = document.createElement("span");
      num.className = "chapter-num";
      num.textContent = ch.number;

      const title = document.createElement("span");
      title.className = "chapter-title";
      title.textContent = ch.title;

      const dur = document.createElement("span");
      dur.className = "chapter-dur";
      dur.textContent = fmt(ch.duration) + (ch.note ? " · " + ch.note : "");

      const play = document.createElement("span");
      play.className = "chapter-play";
      play.textContent = "▶";

      btn.append(num, title, dur, play);
      btn.addEventListener("click", () => playAt(ch.start, ch.title));
      li.appendChild(btn);
      chapterList.appendChild(li);
    }
  }

  function selectEpisode(id, autoplay) {
    const ep = episodes.find((e) => e.id === id && playable(e));
    if (!ep) return;
    const switching = !current || current.id !== ep.id;
    current = ep;
    state.episodeId = ep.id;
    if (switching) state.position = 0;
    save();
    renderEpisodes();
    renderChapters();
    nowEpisode.textContent = ep.title;
    loadSource();
    if (autoplay) playAt(state.position || 0, null);
  }

  function loadSource() {
    if (!current) return;
    if (audio.dataset.episode !== current.id) {
      audio.src = current.audio;
      audio.dataset.episode = current.id;
    }
    audio.playbackRate = state.speed;
    timeDur.textContent = fmt(current.duration);
    scrub.max = "1000";
  }

  function playAt(seconds, chapterTitle) {
    if (!current) return;
    player.hidden = false;
    loadSource();
    const start = Math.max(0, Math.min(seconds || 0, current.duration || seconds || 0));
    const go = () => {
      audio.currentTime = start;
      audio.play().catch(() => { /* автозапуск может быть заблокирован до первого клика */ });
    };
    if (audio.readyState >= 1) go();
    else audio.addEventListener("loadedmetadata", go, { once: true });
    state.position = start;
    if (chapterTitle) nowChapter.textContent = chapterTitle;
    save();
  }

  function chapterAt(time) {
    const chapters = (current && current.chapters) || [];
    let found = null;
    for (const ch of chapters) if (time + 0.25 >= ch.start) found = ch;
    return found;
  }

  function highlight(time) {
    const ch = chapterAt(time);
    nowChapter.textContent = ch ? "Глава " + ch.number + ". " + ch.title : (current ? current.title : "");
    for (const node of chapterList.querySelectorAll(".chapter")) {
      node.setAttribute("aria-current", String(!!ch && Number(node.dataset.start) === ch.start));
    }
  }

  function setSpeed(next) {
    state.speed = next;
    audio.playbackRate = next;
    speedBtn.textContent = (next === 1 ? "1" : String(next).replace(".", ",")) + "×";
    save();
  }

  // --- события плеера ---
  audio.addEventListener("timeupdate", () => {
    if (!current) return;
    const t = audio.currentTime;
    const dur = audio.duration || current.duration || 0;
    timeCur.textContent = fmt(t);
    if (dur) timeDur.textContent = fmt(dur);
    scrub.value = String(dur ? Math.round((t / dur) * 1000) : 0);
    highlight(t);
    state.position = t;
  });

  let saveTimer = 0;
  audio.addEventListener("timeupdate", () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 2000);
  });

  audio.addEventListener("play", () => { toggleBtn.textContent = "❚❚"; });
  audio.addEventListener("pause", () => { toggleBtn.textContent = "▶"; save(); });
  audio.addEventListener("ended", () => { toggleBtn.textContent = "▶"; state.position = 0; save(); });
  audio.addEventListener("error", () => {
    nowChapter.textContent = "Не удалось загрузить аудио";
  });

  toggleBtn.addEventListener("click", () => {
    if (!current) return;
    if (audio.paused) {
      if (!audio.src) loadSource();
      if (audio.readyState >= 1 && !state.position) audio.currentTime = state.position;
      audio.play().catch(() => {});
    } else {
      audio.pause();
    }
  });

  $("back").addEventListener("click", () => { audio.currentTime = Math.max(0, audio.currentTime - 15); });
  $("fwd").addEventListener("click", () => { audio.currentTime = audio.currentTime + 30; });
  speedBtn.addEventListener("click", () => {
    const i = SPEEDS.indexOf(state.speed);
    setSpeed(SPEEDS[(i + 1) % SPEEDS.length]);
  });

  let scrubbing = false;
  scrub.addEventListener("input", () => {
    scrubbing = true;
    const dur = audio.duration || (current && current.duration) || 0;
    timeCur.textContent = fmt((Number(scrub.value) / 1000) * dur);
  });
  scrub.addEventListener("change", () => {
    const dur = audio.duration || (current && current.duration) || 0;
    audio.currentTime = (Number(scrub.value) / 1000) * dur;
    scrubbing = false;
  });

  document.addEventListener("keydown", (e) => {
    if (e.target instanceof HTMLInputElement) return;
    if (e.code === "Space") { e.preventDefault(); toggleBtn.click(); }
    else if (e.code === "ArrowRight") audio.currentTime += 10;
    else if (e.code === "ArrowLeft") audio.currentTime = Math.max(0, audio.currentTime - 10);
  });

  window.addEventListener("beforeunload", save);

  speedBtn.textContent = "1×";

  fetch("episodes.json", { cache: "no-store" })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      episodes = Array.isArray(data) ? data : data.episodes || [];
      const preferred =
        episodes.find((e) => e.id === state.episodeId && playable(e)) ||
        episodes.find(playable);
      renderEpisodes();
      if (preferred) {
        current = preferred;
        renderChapters();
        nowEpisode.textContent = preferred.title;
        loadSource();
        player.hidden = false;
        state.position = state.episodeId === preferred.id ? state.position : 0;
        highlight(state.position || 0);
        timeCur.textContent = fmt(state.position || 0);
      } else {
        episodeSub.textContent = "Пока нет готовых выпусков.";
      }
    })
    .catch((err) => {
      episodeNote.textContent = "Не удалось прочитать episodes.json: " + err.message;
    });
})();
