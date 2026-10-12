(() => {
  const TOTAL_SECONDS = 2868.3;
  const STORAGE_KEY = "lorielee-player-position-v1";
  const descriptions = [
    "Деревня, переполненный дом и детство, из которого начинается эта дорога.",
    "Скрипка, первая работа и выбор, которому ещё только предстоит стать судьбой.",
    "Первые мили пешком, дождь, Лондон и дорога, которая не похожа на открытку.",
    "Испания до войны — страна встреч, открытий и чужих историй.",
    "Возвращение через горы и попытка найти дорогу обратно к себе.",
    "Близость, обещания и чувства, для которых не бывает простого финала.",
    "Лори ищет слова для своей жизни и подходит к главной книге.",
    "Как появилась книга о детстве, которую узнали читатели по всему миру.",
    "Новая жизнь рядом со старым домом и перемены в любимой долине.",
    "Здоровье, воспоминания и поздняя книга о коротком времени в Испании.",
    "Поэт, музыкант, брат и сын — всё, что не помещается на обложке.",
    "Последний поворот дороги и возвращение в место, с которого всё началось."
  ];
  const fallbackChapters = [
    ["Дом под дорогой", 0],
    ["Скрипка и контора", 257.48],
    ["Первый дождь", 525.53],
    ["Испания до войны", 747.5],
    ["Возвращение через горы", 970.41],
    ["Любовь без удобного конца", 1209.85],
    ["До главной книги", 1458.85],
    ["Книга, которую узнали все", 1704.51],
    ["Новая жизнь в старой долине", 1948.098],
    ["Старые записи", 2195.874],
    ["То, что осталось между книгами", 2419.134],
    ["Дорога домой", 2663.39]
  ].map(([title, start_seconds], index) => ({ number: index + 1, title, start_seconds }));

  const audio = document.querySelector("#audio");
  const playButton = document.querySelector("#playPause");
  const heroPlayButton = document.querySelector("#heroPlay");
  const seek = document.querySelector("#seek");
  const elapsed = document.querySelector("#elapsed");
  const remaining = document.querySelector("#remaining");
  const volume = document.querySelector("#volume");
  const speedButton = document.querySelector("#speedButton");
  const chapterList = document.querySelector("#chapterList");
  const playerStatus = document.querySelector("#playerStatus");
  const resumeMessage = document.querySelector("#resumeMessage");
  const toast = document.querySelector("#toast");

  let chapters = fallbackChapters;
  let activeChapterIndex = -1;
  let isSeeking = false;
  let savedPosition = readSavedPosition();
  let lastSavedAt = 0;
  let toastTimer;

  function formatTime(seconds) {
    const safeSeconds = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const remainder = safeSeconds % 60;
    return hours > 0
      ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
      : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  }

  function readSavedPosition() {
    try {
      const value = Number(window.localStorage.getItem(STORAGE_KEY));
      return Number.isFinite(value) && value > 5 ? value : 0;
    } catch {
      return 0;
    }
  }

  function savePosition(force = false) {
    const now = Date.now();
    if (!force && now - lastSavedAt < 3000) return;
    lastSavedAt = now;
    try {
      if (audio.currentTime > 5 && !audio.ended) {
        window.localStorage.setItem(STORAGE_KEY, String(audio.currentTime));
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Playback remains available when storage is disabled.
    }
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2600);
  }

  function setPlayState(isPlaying) {
    document.body.classList.toggle("is-playing", isPlaying);
    playButton.setAttribute("aria-label", isPlaying ? "Поставить на паузу" : "Воспроизвести");
    playButton.title = isPlaying ? "Пауза" : "Воспроизвести";
    playerStatus.textContent = isPlaying ? "Сейчас играет" : (audio.currentTime > 0 ? "На паузе" : "Готов к прослушиванию");
  }

  function playAudio() {
    const result = audio.play();
    if (result && typeof result.catch === "function") {
      result.catch(() => {
        playerStatus.textContent = "Не удалось запустить аудио — попробуйте ещё раз";
      });
    }
  }

  function togglePlayback() {
    if (audio.paused) playAudio();
    else audio.pause();
  }

  function getDuration() {
    return Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : TOTAL_SECONDS;
  }

  function updateTimeline(position = audio.currentTime) {
    const duration = getDuration();
    const percentage = Math.min(100, Math.max(0, (position / duration) * 100));
    seek.value = String(percentage);
    seek.style.setProperty("--range-progress", `${percentage}%`);
    elapsed.textContent = formatTime(position);
    remaining.textContent = `−${formatTime(Math.max(0, duration - position))}`;
    seek.setAttribute("aria-valuetext", `${formatTime(position)} из ${formatTime(duration)}`);
  }

  function chapterForTime(time) {
    let index = 0;
    for (let i = 1; i < chapters.length; i += 1) {
      if (time >= chapters[i].start_seconds) index = i;
      else break;
    }
    return index;
  }

  function updateActiveChapter(force = false) {
    if (!chapters.length) return;
    const index = chapterForTime(audio.currentTime || 0);
    if (!force && index === activeChapterIndex) return;
    activeChapterIndex = index;
    const chapter = chapters[index];
    const number = String(index + 1).padStart(2, "0");

    document.querySelector("#nowChapterLabel").textContent = `СЕЙЧАС · ГЛАВА ${number}`;
    document.querySelector("#nowChapterTitle").textContent = chapter.title;
    document.querySelector("#nowChapterDescription").textContent = descriptions[index] || "Продолжение истории Лори Ли.";
    document.querySelector("#currentChapterNumber").textContent = number;

    chapterList.querySelectorAll(".chapter-button").forEach((button, buttonIndex) => {
      const isCurrent = buttonIndex === index;
      button.classList.toggle("is-current", isCurrent);
      if (isCurrent) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    });
  }

  function createChapterButton(chapter, index) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chapter-button";
    button.setAttribute("aria-label", `Перейти к главе ${String(index + 1).padStart(2, "0")}: ${chapter.title}, ${formatTime(chapter.start_seconds)}`);
    button.addEventListener("click", () => {
      const duration = getDuration();
      audio.currentTime = Math.min(chapter.start_seconds, duration);
      updateTimeline(audio.currentTime);
      updateActiveChapter(true);
      playAudio();
      document.querySelector("#listen").scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" });
    });

    const number = document.createElement("span");
    number.className = "chapter-number";
    number.textContent = String(index + 1).padStart(2, "0");

    const text = document.createElement("span");
    text.className = "chapter-text";
    const title = document.createElement("span");
    title.className = "chapter-title";
    title.textContent = chapter.title;
    const subtitle = document.createElement("span");
    subtitle.className = "chapter-subtitle";
    const end = chapters[index + 1]?.start_seconds ?? TOTAL_SECONDS;
    const minutes = Math.max(1, Math.round((end - chapter.start_seconds) / 60));
    subtitle.textContent = `ГЛАВА ${String(index + 1).padStart(2, "0")} · около ${minutes} мин`;
    text.append(title, subtitle);

    const time = document.createElement("span");
    time.className = "chapter-time";
    time.textContent = formatTime(chapter.start_seconds);

    const mark = document.createElement("span");
    mark.className = "chapter-playing-mark";
    mark.setAttribute("aria-hidden", "true");
    for (let bar = 0; bar < 3; bar += 1) mark.append(document.createElement("i"));

    button.append(number, text, time, mark);
    return button;
  }

  function renderChapters() {
    chapterList.replaceChildren(...chapters.map(createChapterButton));
    updateActiveChapter(true);
  }

  function reducedMotion() {
    return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  }

  async function loadChapters() {
    try {
      const response = await fetch("podcast_revoice/chapters.json", { cache: "no-cache" });
      if (!response.ok) throw new Error("Chapter file not found");
      const data = await response.json();
      if (Array.isArray(data) && data.length > 0 && data.every((chapter) => typeof chapter.title === "string" && Number.isFinite(chapter.start_seconds))) {
        chapters = data;
      }
    } catch {
      // Use the built-in chapter list when opened offline or directly from disk.
    }
    renderChapters();
    updateActiveChapter(true);
  }

  playButton.addEventListener("click", togglePlayback);
  heroPlayButton.addEventListener("click", () => {
    document.querySelector("#listen").scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "center" });
    if (audio.paused) playAudio();
  });

  document.querySelector("#skipBack").addEventListener("click", () => {
    audio.currentTime = Math.max(0, audio.currentTime - 15);
    updateTimeline(audio.currentTime);
    updateActiveChapter();
  });
  document.querySelector("#skipForward").addEventListener("click", () => {
    audio.currentTime = Math.min(getDuration(), audio.currentTime + 15);
    updateTimeline(audio.currentTime);
    updateActiveChapter();
  });

  seek.addEventListener("input", () => {
    isSeeking = true;
    const previewPosition = (Number(seek.value) / 100) * getDuration();
    updateTimeline(previewPosition);
  });
  seek.addEventListener("change", () => {
    audio.currentTime = (Number(seek.value) / 100) * getDuration();
    isSeeking = false;
    updateTimeline(audio.currentTime);
    updateActiveChapter();
    savePosition(true);
  });
  seek.addEventListener("pointerup", () => { isSeeking = false; });

  volume.addEventListener("input", () => {
    audio.volume = Number(volume.value);
    volume.style.setProperty("--range-progress", `${Number(volume.value) * 100}%`);
  });
  audio.volume = Number(volume.value);
  volume.style.setProperty("--range-progress", `${Number(volume.value) * 100}%`);

  const playbackRates = [1, 1.25, 1.5, 1.75, 2, 0.75];
  let rateIndex = 0;
  speedButton.addEventListener("click", () => {
    rateIndex = (rateIndex + 1) % playbackRates.length;
    const rate = playbackRates[rateIndex];
    audio.playbackRate = rate;
    const label = `${rate}×`;
    speedButton.textContent = label;
    speedButton.setAttribute("aria-label", `Скорость воспроизведения ${label}`);
    showToast(`Скорость: ${label}`);
  });

  audio.addEventListener("play", () => {
    setPlayState(true);
    resumeMessage.hidden = true;
  });
  audio.addEventListener("pause", () => setPlayState(false));
  audio.addEventListener("loadedmetadata", () => {
    updateTimeline();
    if (savedPosition > 0 && savedPosition < audio.duration - 10) {
      document.querySelector("#resumeTime").textContent = formatTime(savedPosition);
      resumeMessage.hidden = false;
    } else if (savedPosition > 0) {
      try { window.localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
      savedPosition = 0;
    }
    updateActiveChapter(true);
  });
  audio.addEventListener("durationchange", () => updateTimeline());
  audio.addEventListener("timeupdate", () => {
    if (!isSeeking) updateTimeline();
    updateActiveChapter();
    savePosition();
  });
  audio.addEventListener("ended", () => {
    setPlayState(false);
    playerStatus.textContent = "Выпуск завершён";
    try { window.localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
    savedPosition = 0;
  });
  audio.addEventListener("error", () => {
    playerStatus.textContent = "Не удалось загрузить аудиофайл";
  });

  document.querySelector("#resumeButton").addEventListener("click", () => {
    audio.currentTime = savedPosition;
    updateTimeline(audio.currentTime);
    playAudio();
  });
  document.querySelector("#dismissResume").addEventListener("click", () => {
    resumeMessage.hidden = true;
  });

  document.querySelector("#shareButton").addEventListener("click", async () => {
    const shareData = { title: document.title, text: "Лори Ли. Дорога домой — русскоязычная аудиоистория.", url: window.location.href.split("#")[0] };
    if (navigator.share) {
      try {
        await navigator.share(shareData);
        return;
      } catch (error) {
        if (error.name === "AbortError") return;
      }
    }
    try {
      await navigator.clipboard.writeText(shareData.url);
      showToast("Ссылка на выпуск скопирована");
    } catch {
      showToast("Скопируйте адрес страницы, чтобы поделиться выпуском");
    }
  });

  window.addEventListener("beforeunload", () => savePosition(true));

  updateTimeline(0);
  loadChapters();
})();
