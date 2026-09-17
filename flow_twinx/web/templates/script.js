const audio = document.getElementById("audioPlayer");
const playBtn = document.getElementById("playBtn");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const shuffleBtn = document.getElementById("shuffleBtn");
const repeatBtn = document.getElementById("repeatBtn");
const progressFill = document.getElementById("progressFill");
const progressBar = document.getElementById("progressBar");
const currentTime = document.getElementById("currentTime");
const totalTime = document.getElementById("totalTime");
const volumeSlider = document.getElementById("volumeSlider");
const playerArt = document.getElementById("playerArt");
const playerBarBg = document.getElementById("playerBarBg");
const playerTitle = document.getElementById("playerTitle");
const playerArtist = document.getElementById("playerArtist");
const searchInput = document.getElementById("searchInput");
const resultsContainer = document.getElementById("resultsContainer");
const srcYt = document.getElementById("srcYt");
const srcLocal = document.getElementById("srcLocal");
const clearQueueBtn = document.getElementById("clearQueueBtn");
const queueContainer = document.getElementById("queueContainer");
const scanLocalBtn = document.getElementById("scanLocalBtn");
const localShuffleBtn = document.getElementById("localShuffleBtn");
const albumsGrid = document.getElementById("albumsGrid");
const albumSongs = document.getElementById("albumSongs");
const localSongsContainer = document.getElementById("localSongs");
const autoPlayToggle = document.getElementById("autoPlayToggle");
const downloadBtn = document.getElementById("downloadBtn");
const likeBtn = document.getElementById("likeBtn");
const toastEl = document.getElementById("toast");
const settingsModal = document.getElementById("settingsModal");
const settingsBtn = document.getElementById("settingsBtn");
const closeSettings = document.getElementById("closeSettings");
const saveSettings = document.getElementById("saveSettings");
const resetSettingsBtn = document.getElementById("resetSettings");
const refreshLikedBtn = document.getElementById("refreshLikedBtn");
const newPlaylistBtn = document.getElementById("newPlaylistBtn");
const playlistDetailContent = document.getElementById("playlistDetailContent");
const playlistModal = document.getElementById("playlistModal");
const closePlaylistModal = document.getElementById("closePlaylistModal");
const playlistModalTitle = document.getElementById("playlistModalTitle");
const playlistNameInput = document.getElementById("playlistNameInput");
const savePlaylistBtn = document.getElementById("savePlaylistBtn");
const playlistExistsModal = document.getElementById("playlistExistsModal");
const closeExistsModal = document.getElementById("closeExistsModal");
const existsMsg = document.getElementById("existsMsg");
const existsAppendBtn = document.getElementById("existsAppendBtn");
const existsOverwriteBtn = document.getElementById("existsOverwriteBtn");
const sidebarPlaylists = document.getElementById("sidebarPlaylists");
const speedDialGrid = document.getElementById("speedDialGrid");
const lastPlayedSection = document.getElementById("lastPlayedSection");

let queue = [];
let queueIndex = -1;
let playHistory = [];
let nowPlayingTrack = null;
let isPlaying = false;
let isShuffled = false;
let repeatMode = 0;
let autoPlay = true;
let searchSource = "youtube";
let activePanel = "home";
let localTracks = [];
let currentTrackType = null;
let downloadedIds = new Set();
let speedDialIds = new Set();
let librarySongs = {};
let currentDownloaded = false;
let playlistsCache = [];
let currentPlaylistName = null;
let pendingPlaylist = null;
let pendingSong = null;
let playlistModalMode = "saveQueue";
let playbackRetries = 0;

let settings = {
  theme: "dark",
  bgBlur: 0,
  bgDim: 80,
  defaultVolume: 80,
  miniOnBlur: false,
  defaultSource: "youtube",
  format: "webm",
};

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

let searchTimer = null;

function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => doSearch(), 1000);
}

searchInput.addEventListener("focus", () => setPanel("search"));
searchInput.addEventListener("input", debounceSearch);
searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    clearTimeout(searchTimer);
    doSearch();
  }
});

function doSearch() {
  const q = searchInput.value.trim();
  if (q.length < 2) {
    resultsContainer.innerHTML = "";
    return;
  }
  if (searchSource === "youtube") {
    searchYouTube(q);
  } else {
    searchLocal(q);
  }
}

srcYt.addEventListener("click", () => setSearchSource("youtube"));
srcLocal.addEventListener("click", () => setSearchSource("local"));

function setSearchSource(source) {
  searchSource = source;
  srcYt.classList.toggle("active", source === "youtube");
  srcLocal.classList.toggle("active", source === "local");
  doSearch();
}

playBtn.addEventListener("click", togglePlay);
prevBtn.addEventListener("click", prevTrack);
nextBtn.addEventListener("click", nextTrack);
shuffleBtn.addEventListener("click", toggleShuffle);
localShuffleBtn.addEventListener("click", localShufflePlay);
repeatBtn.addEventListener("click", toggleRepeat);
volumeSlider.addEventListener("input", (e) => {
  audio.volume = e.target.value / 100;
});

audio.addEventListener("timeupdate", updateProgress);
audio.addEventListener("loadedmetadata", () => {
  updateTotalTime();
  if (nowPlayingTrack) reportNowPlaying(nowPlayingTrack, !audio.paused);
});
audio.addEventListener("ended", handleEnd);
audio.addEventListener("play", () => {
  playbackRetries = 0;
  updatePlayBtn(true);
  reportNowPlaying(queue[queueIndex], true);
});
audio.addEventListener("pause", () => {
  updatePlayBtn(false);
  reportNowPlaying(queue[queueIndex], false);
});
audio.addEventListener("error", () => {
  handlePlaybackFailure(queue[queueIndex]);
});

let _sponsorSkipSegments = [];
const _sponsorSkipDone = new Set();

function setupSponsorSkip(segments) {
  _sponsorSkipSegments = segments || [];
  _sponsorSkipDone.clear();
}

function sponsorSkipTick() {
  if (!_sponsorSkipSegments.length) return;
  if (audio.paused || !isFinite(audio.currentTime)) return;
  const t = audio.currentTime;
  for (let i = 0; i < _sponsorSkipSegments.length; i++) {
    if (_sponsorSkipDone.has(i)) continue;
    const seg = _sponsorSkipSegments[i];
    if (t >= seg.start_time && t < seg.end_time) {
      _sponsorSkipDone.add(i);
      audio.currentTime = seg.end_time;
      break;
    }
  }
}

audio.addEventListener("timeupdate", sponsorSkipTick);

progressBar.addEventListener("click", (e) => {
  const rect = progressBar.getBoundingClientRect();
  const pct = (e.clientX - rect.left) / rect.width;
  audio.currentTime = pct * audio.duration;
});

clearQueueBtn.addEventListener("click", clearQueue);
document
  .getElementById("saveQueueBtn")
  .addEventListener("click", openSavePlaylistModal);
scanLocalBtn.addEventListener("click", scanLocal);
refreshLikedBtn.addEventListener("click", loadLiked);
newPlaylistBtn.addEventListener("click", openNewPlaylistModal);

settingsBtn.addEventListener("click", () =>
  settingsModal.classList.add("open"),
);
closeSettings.addEventListener("click", () =>
  settingsModal.classList.remove("open"),
);
settingsModal.addEventListener("click", (e) => {
  if (e.target === settingsModal) settingsModal.classList.remove("open");
});
saveSettings.addEventListener("click", saveSettingsToAPI);
resetSettingsBtn.addEventListener("click", resetSettings);

playlistModal.addEventListener("click", (e) => {
  if (e.target === playlistModal) playlistModal.classList.remove("open");
});
closePlaylistModal.addEventListener("click", () =>
  playlistModal.classList.remove("open"),
);
playlistNameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitPlaylistModal();
});
savePlaylistBtn.addEventListener("click", submitPlaylistModal);

playlistExistsModal.addEventListener("click", (e) => {
  if (e.target === playlistExistsModal)
    playlistExistsModal.classList.remove("open");
});
closeExistsModal.addEventListener("click", () =>
  playlistExistsModal.classList.remove("open"),
);
existsAppendBtn.addEventListener("click", () => {
  if (pendingPlaylist) {
    doSavePlaylist(pendingPlaylist.name, pendingPlaylist.songs, "append");
  }
  playlistExistsModal.classList.remove("open");
});
existsOverwriteBtn.addEventListener("click", () => {
  if (pendingPlaylist) {
    doSavePlaylist(pendingPlaylist.name, pendingPlaylist.songs, "overwrite");
  }
  playlistExistsModal.classList.remove("open");
});

autoPlayToggle.addEventListener("change", (e) => {
  autoPlay = e.target.checked;
  if (!autoPlay) {
    if (queueIndex >= 0 && queue[queueIndex]) {
      const currentTrack = queue[queueIndex];
      queue = queue.filter(
        (song, idx) => idx === queueIndex || !song._autoAdded,
      );
      queueIndex = queue.indexOf(currentTrack);
    } else {
      queue = queue.filter((song) => !song._autoAdded);
      if (queueIndex >= queue.length) queueIndex = queue.length - 1;
    }
    renderQueue();
  }
});

function panelPath(panel) {
  if (panel === "search") return "/search";
  if (panel === "home") return "/";
  if (panel === "playlistDetail") return null;
  return "/" + panel;
}

function panelFromPath() {
  switch (window.location.pathname) {
    case "/search":
      return "search";
    case "/local":
      return "local";
    case "/liked":
      return "liked";
    case "/queue":
      return "queue";
    default:
      return "home";
  }
}

function setPanel(panel, noPush) {
  activePanel = panel;
  document
    .querySelectorAll(".sidebar-nav .nav-item")
    .forEach((n) => n.classList.toggle("active", n.dataset.panel === panel));
  document.querySelectorAll("#mainContent .panel").forEach((p) => {
    p.classList.toggle(
      "active",
      p.id === "panel" + panel.charAt(0).toUpperCase() + panel.slice(1),
    );
  });
  const path = panelPath(panel);
  if (!noPush && path && window.location.pathname !== path) {
    history.pushState({ panel }, "", path);
  }
}

window.addEventListener("popstate", () => {
  setPanel(panelFromPath(), true);
  if (panelFromPath() === "search") doSearch();
});

document.querySelectorAll(".sidebar-nav .nav-item").forEach((item) => {
  if (item.dataset.panel) {
    item.addEventListener("click", () => setPanel(item.dataset.panel));
  }
});

function togglePlay() {
  if (audio.paused) {
    if (audio.src && audio.src !== "") {
      audio.play();
    } else if (queue.length > 0 && queueIndex >= 0) {
      loadAndPlay(queue[queueIndex]);
    } else if (queue.length > 0) {
      queueIndex = 0;
      loadAndPlay(queue[0]);
    }
  } else {
    audio.pause();
  }
}

function updatePlayBtn(playing) {
  isPlaying = playing;
  playBtn.querySelector("i").className = playing
    ? "bi bi-pause-fill"
    : "bi bi-play-fill";
}

function reportNowPlaying(track, playing) {
  if (!track) return;
  let dur = track.duration || 0;
  if (isFinite(audio.duration) && audio.duration > 0)
    dur = Math.round(audio.duration);
  fetch("/api/now-playing", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: track.title || "Unknown",
      duration: dur,
      playing: playing,
      thumbnail: track.thumbnail || "",
    }),
  }).catch(() => {});
}

function handlePlaybackFailure(track) {
  if (!track || track !== queue[queueIndex]) {
    playbackRetries = 0;
    return;
  }
  const isYt = track.video_id && currentTrackType !== "local";
  if (isYt && playbackRetries < 3) {
    playbackRetries++;
    track.stream_url = "";
    loadAndPlay(track, true);
    return;
  }
  playbackRetries = 0;
  nextTrack();
}

function loadAndPlay(track, isRetry) {
  if (!track) return;
  if (!isRetry) playbackRetries = 0;
  setupSponsorSkip(track.segments || []);
  nowPlayingTrack = track;
  currentTrackType = track.source || "yt";
  setDisplayInfo(track);
  updateActiveCard(track);
  updateQueueBarTab();
  checkLiked(track.video_id);
  checkDownload(track.video_id);
  reportNowPlaying(track, true);
  setTimeout(() => reportNowPlaying(nowPlayingTrack, !audio.paused), 800);
  refreshLastPlayed();

  if (currentTrackType === "local") {
    let filePath = track.path || track.url || "";
    let encodedPath = encodeURI(filePath);
    let src =
      "/local" +
      (encodedPath.startsWith("/") ? encodedPath : "/" + encodedPath);
    track.thumbnail = track.thumbnail || "";
    track.channel = track.channel || track.album || "Local Music";
    audio.src = src;
    audio.play().catch(() => {});
  } else if (track.stream_url) {
    audio.src = track.stream_url;
    audio.play().catch(() => {});
  } else if (track.video_id) {
    const fresh = isRetry ? "&fresh=1" : "";
    const segPromise = fetch(`/api/segments?video_id=${track.video_id}`)
      .then((r) => r.json())
      .then((d) => d.segments || [])
      .catch(() => []);
    const playPromise = fetch(`/play?video_id=${track.video_id}${fresh}`)
      .then((r) => r.json())
      .catch(() => null);
    Promise.all([segPromise, playPromise]).then(([segs, data]) => {
      if (!data || !data.stream_url) {
        handlePlaybackFailure(track);
        return;
      }
      track.stream_url = data.stream_url;
      track.segments = segs;
      setupSponsorSkip(segs);
      audio.src = data.stream_url;
      audio.play().catch(() => {});
    });
  }

  if (autoPlay && currentTrackType !== "local" && track.video_id) {
    autoLoadRecommendations(track.video_id);
  }
  prewarmNextTrack();
}

function prewarmNextTrack() {
  if (!autoPlay) return;
  let nextIdx;
  if (isShuffled && queue.length > 0) {
    do {
      nextIdx = Math.floor(Math.random() * queue.length);
    } while (nextIdx === queueIndex && queue.length > 1);
  } else if (queueIndex < queue.length - 1) {
    nextIdx = queueIndex + 1;
  } else if (repeatMode === 2) {
    nextIdx = 0;
  } else {
    return;
  }
  const next = queue[nextIdx];
  if (!next || next.source === "local" || !next.video_id) return;
  if (next.stream_url) return;
  fetch(`/play?video_id=${next.video_id}`).catch(() => {});
}

const artFrame = "/static/Frame%201.jpg";

function effectiveThumb(track) {
  const id = track && track.video_id;
  if (id && librarySongs[id] && librarySongs[id].thumbnail) {
    return "/thumb/" + id;
  }
  return track ? track.thumbnail || "" : "";
}

function applyArt(img, url, track) {
  url = track ? effectiveThumb(track) : url;
  if (!url || !url.trim()) {
    img.onerror = null;
    img.src = artFrame;
    return;
  }
  img.onerror = () => {
    const cur = img.src;
    img.onerror = null;
    if (cur.includes("maxresdefault.jpg")) {
      img.src = cur.replace("maxresdefault.jpg", "hqdefault.jpg");
    } else {
      img.src = artFrame;
    }
  };
  img.src = url;
}

function artImgTag(url, track) {
  url = track ? effectiveThumb(track) : url;
  if (!url || !url.trim()) {
    return `<img src="${artFrame}" alt="" loading="lazy">`;
  }
  const onerr =
    "this.onerror=null;if(this.src.includes('maxresdefault.jpg')){this.src=this.src.replace('maxresdefault.jpg','hqdefault.jpg')}else{this.src='/static/Frame%201.jpg'}";
  return `<img src="${url}" onerror="${onerr}" alt="" loading="lazy">`;
}

function setDisplayInfo(track) {
  playerTitle.textContent = track.title || "Unknown";
  playerArtist.textContent = track.channel || track.artist || "";
  applyArt(playerArt, track.thumbnail, track);
  setPlayerBarBg(track);
}

function setPlayerBarBg(track) {
  if (!playerBarBg) return;
  const url = track ? effectiveThumb(track) : "";
  if (!url || !url.trim()) {
    playerBarBg.style.backgroundImage = "none";
    playerBarBg.style.opacity = "0";
    return;
  }
  const probe = new Image();
  probe.onload = () => {
    playerBarBg.style.backgroundImage = `url("${url}")`;
    playerBarBg.style.opacity = "0.9";
  };
  probe.onerror = () => {
    if (url.includes("maxresdefault.jpg")) {
      playerBarBg.style.backgroundImage = `url("${url.replace("maxresdefault.jpg", "hqdefault.jpg")}")`;
      playerBarBg.style.opacity = "0.9";
    } else {
      playerBarBg.style.backgroundImage = "none";
      playerBarBg.style.opacity = "0";
    }
  };
  probe.src = url;
}

function updateActiveCard(track) {
  document
    .querySelectorAll(".song-card")
    .forEach((c) => c.classList.remove("active"));
  document.querySelectorAll(".song-card").forEach((c) => {
    const t = c.dataset.title;
    const id = c.dataset.videoId || c.dataset.path;
    if (t === track.title && id === (track.video_id || track.path)) {
      c.classList.add("active");
    }
  });
}

function updateProgress() {
  if (!audio.duration) return;
  const pct = (audio.currentTime / audio.duration) * 100;
  progressFill.style.width = pct + "%";
  currentTime.textContent = formatTime(audio.currentTime);
}

function updateTotalTime() {
  totalTime.textContent = formatTime(audio.duration);
}

function formatTime(s) {
  if (isNaN(s) || !isFinite(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

let lastRecommendationId = null;
let recommendationLoading = false;

function autoLoadRecommendations(videoId) {
  if (!videoId || recommendationLoading) return;
  const songsRemaining = queue.length - queueIndex - 1;
  if (songsRemaining >= 5) return;
  if (videoId === lastRecommendationId) return;
  lastRecommendationId = videoId;
  recommendationLoading = true;
  fetch(`/recommend?video_id=${encodeURIComponent(videoId)}&limit=20`)
    .then((r) => r.json())
    .then((data) => {
      const results = data.results || [];
      const existingIds = new Set(queue.map((t) => t.video_id));
      let added = 0;
      results.forEach((item) => {
        if (!item.video_id || existingIds.has(item.video_id)) return;
        queue.push({ ...item, source: "yt", _autoAdded: true });
        existingIds.add(item.video_id);
        added++;
      });
      if (added > 0) renderQueue();
      recommendationLoading = false;
    })
    .catch(() => {
      recommendationLoading = false;
    });
}

function handleEnd() {
  if (repeatMode === 1) {
    audio.play();
    return;
  }
  if (!autoPlay && repeatMode !== 2) {
    updatePlayBtn(false);
    audio.currentTime = 0;
    return;
  }
  if (queueIndex < queue.length - 1 || repeatMode === 2) {
    nextTrack();
  } else {
    updatePlayBtn(false);
    audio.currentTime = 0;
  }
}

function prevTrack() {
  if (audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }
  if (playHistory.length > 0) {
    const prev = playHistory.pop();
    if (prev) {
      loadAndPlay(prev);
      return;
    }
  }
  if (queueIndex > 0) {
    queueIndex--;
    loadAndPlay(queue[queueIndex]);
  }
}

function nextTrack() {
  const prev = queue[queueIndex];
  if (isShuffled && queue.length > 0) {
    let nextIdx;
    do {
      nextIdx = Math.floor(Math.random() * queue.length);
    } while (nextIdx === queueIndex && queue.length > 1);
    queueIndex = nextIdx;
  } else {
    if (queueIndex < queue.length - 1) {
      queueIndex++;
    } else if (repeatMode === 2) {
      queueIndex = 0;
    } else {
      return;
    }
  }
  if (prev) {
    playHistory.push(prev);
    if (playHistory.length > 50) playHistory.shift();
  }
  loadAndPlay(queue[queueIndex]);
}

function toggleShuffle() {
  isShuffled = !isShuffled;
  shuffleBtn.classList.toggle("active", isShuffled);
  if (localShuffleBtn) localShuffleBtn.classList.toggle("active", isShuffled);
}

function localShufflePlay() {
  if (localTracks.length === 0) {
    showToast("No local music to shuffle");
    return;
  }
  if (!isShuffled) toggleShuffle();
  const randomIdx = Math.floor(Math.random() * localTracks.length);
  playLocal(localTracks[randomIdx], localTracks);
}

function toggleRepeat() {
  repeatMode = (repeatMode + 1) % 3;
  const icons = ["bi bi-repeat", "bi bi-repeat", "bi bi-repeat"];
  const titles = ["Repeat off", "Repeat one", "Repeat all"];
  repeatBtn.querySelector("i").className = icons[repeatMode];
  repeatBtn.title = titles[repeatMode];
  repeatBtn.classList.toggle("active", repeatMode > 0);
}

function clearQueue() {
  queue = [];
  queueIndex = -1;
  audio.pause();
  audio.src = "";
  updatePlayBtn(false);
  renderQueue();
}

function searchYouTube(query) {
  const limit = 15;
  resultsContainer.innerHTML =
    '<div class="loading-dots"><span></span><span></span><span></span></div>';
  fetch(`/search?q=${encodeURIComponent(query)}&limit=${limit}`)
    .then((r) => r.json())
    .then((data) => {
      const res = data.results || [];
      resultsContainer.innerHTML = "";
      if (res.length === 0) {
        resultsContainer.innerHTML =
          '<div class="empty-state">No results found</div>';
        return;
      }
      res.forEach((item) => {
        const card = createSongCard(item, "yt");
        card.addEventListener("click", () => playTrack(item));
        resultsContainer.appendChild(card);
      });
    })
    .catch(() => {
      resultsContainer.innerHTML =
        '<div class="empty-state">Search failed</div>';
    });
}

function searchLocal(query) {
  resultsContainer.innerHTML =
    '<div class="loading-dots"><span></span><span></span><span></span></div>';
  fetch(`/api/local-search?q=${encodeURIComponent(query)}`)
    .then((r) => r.json())
    .then((data) => {
      const res = data.results || [];
      resultsContainer.innerHTML = "";
      if (res.length === 0) {
        resultsContainer.innerHTML =
          '<div class="empty-state">No local results</div>';
        return;
      }
      res.forEach((item) => {
        const card = createSongCard(
          { ...item, thumbnail: "", channel: "Local Music", duration: 0 },
          "local",
        );
        card.addEventListener("click", () => playLocal(item, [item]));
        resultsContainer.appendChild(card);
      });
    })
    .catch(() => {
      resultsContainer.innerHTML =
        '<div class="empty-state">Search failed</div>';
    });
}

function createSongCard(data, type) {
  const card = document.createElement("div");
  card.className = "song-card";
  card.dataset.title = data.title;
  card.dataset.videoId = data.video_id || "";
  card.dataset.path = data.path || "";
  card.innerHTML = `
        ${artImgTag(data.thumbnail, data)}
        <div class="song-info">
            <div class="song-title">${data.title || "Unknown"}</div>
            <div class="song-artist">${data.channel || data.artist || "Unknown"}</div>
        </div>
        ${data.duration ? `<span class="song-duration">${formatTime(data.duration)}</span>` : ""}
        <div class="song-actions">
            <button class="song-menu-btn" title="Options"><i class="bi bi-three-dots-vertical"></i></button>
        </div>
    `;
  card.querySelector(".song-menu-btn").addEventListener("click", (e) => {
    e.stopPropagation();
    showSongMenu(e.currentTarget, data, type);
  });
  return card;
}

function showSongMenu(btn, track, type) {
  closeSongMenu();
  const menu = document.createElement("div");
  menu.className = "song-menu";

  const isDownloaded = track.video_id && downloadedIds.has(track.video_id);
  const isLocal = type === "local" || track.source === "local";
  const isSpeedDial = track.video_id && speedDialIds.has(track.video_id);

  const items = [
    {
      icon: "bi bi-play-fill",
      label: "Play",
      action: () => {
        if (isLocal) playLocal(track, [track]);
        else playTrack(track);
      },
    },
    {
      icon: "bi bi-skip-end-fill",
      label: "Play next",
      action: () => playNextTrack(track, type),
    },
    {
      icon: "bi bi-plus-lg",
      label: "Add to queue",
      action: () => addToQueue(isLocal ? { ...track, source: "local" } : track),
    },
  ];

  if (track.video_id) {
    items.push({
      icon: isSpeedDial ? "bi bi-star-fill" : "bi bi-star",
      label: isSpeedDial ? "Remove from Speed Dial" : "Add to Speed Dial",
      action: () => toggleSpeedDial(track),
    });
  }

  if (isLocal && track.video_id) {
    items.push({
      icon: "bi bi-trash",
      label: "Remove download",
      action: () => deleteDownloadById(track.video_id, track.path || ""),
    });
  } else if (!isLocal && track.video_id) {
    items.push({
      icon: isDownloaded ? "bi bi-trash" : "bi bi-download",
      label: isDownloaded ? "Remove download" : "Download",
      action: () => {
        if (isDownloaded) deleteDownloadById(track.video_id, track.path || "");
        else downloadTrackById(track);
      },
    });
  }

  items.push({
    icon: "bi bi-list-ul",
    label: "Add to playlist",
    action: () => openPlaylistMenu(btn, track),
  });

  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.innerHTML = `<i class="${item.icon}"></i> ${item.label}`;
    button.addEventListener("click", (e) => {
      e.stopPropagation();
      closeSongMenu();
      item.action();
    });
    menu.appendChild(button);
  });

  document.body.appendChild(menu);
  const rect = btn.getBoundingClientRect();
  let left = rect.left;
  if (left + 180 > window.innerWidth - 8) left = window.innerWidth - 188;
  menu.style.left = left + "px";
  menu.style.top = rect.bottom + 4 + "px";
  setTimeout(() => {
    document.addEventListener("click", closeSongMenu, { once: true });
  }, 0);
}

function closeSongMenu() {
  document.querySelectorAll(".song-menu").forEach((m) => m.remove());
}

function playNextTrack(track, type) {
  const entry = { ...track, source: type === "local" ? "local" : "yt" };
  if (queueIndex >= 0 && queueIndex < queue.length - 1) {
    queue.splice(queueIndex + 1, 0, entry);
  } else {
    queue.push(entry);
  }
  if (queueIndex === -1) queueIndex = 0;
  renderQueue();
  showToast("Playing next");
}

function downloadTrackById(track) {
  const vid = track.video_id;
  if (!vid) return;
  const saveDir = settings.downloadPath || "~/.flow/downloads";
  showToast("Downloading...");
  fetch("/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_id: vid,
      save_dir: saveDir,
      format: settings.format,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.success) {
        downloadedIds.add(vid);
        if (librarySongs[vid]) {
          librarySongs[vid].downloaded = true;
          if (data.thumbnail) librarySongs[vid].thumbnail = data.thumbnail;
        } else {
          librarySongs[vid] = {
            video_id: vid,
            title: data.title || track.title || "",
            liked: false,
            downloaded: true,
            thumbnail: data.thumbnail || "",
          };
        }
        showToast("Downloaded: " + (data.title || track.title));
      } else {
        showToast("Failed: " + (data.error || "Unknown error"));
      }
    })
    .catch(() => showToast("Download failed"));
}

function deleteDownloadById(videoId, filePath) {
  if (!videoId && !filePath) return;
  fetch("/api/delete-download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId || "", path: filePath || "" }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.success) {
        downloadedIds.delete(videoId);
        if (librarySongs[videoId]) librarySongs[videoId].downloaded = false;
        showToast("Removed download");
        scanLocal();
      } else {
        showToast("Failed: " + (data.error || "Not downloaded"));
      }
    })
    .catch(() => showToast("Failed to remove download"));
}

function toggleSpeedDial(track) {
  const vid = track.video_id;
  if (!vid) return;
  const enabled = !speedDialIds.has(vid);
  fetch("/api/speed-dial", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_id: vid,
      title: track.title || "Unknown",
      enabled,
      path: track.path || (track.source === "local" && track.url) || "",
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.success) {
        if (enabled) {
          speedDialIds.add(vid);
          if (librarySongs[vid]) librarySongs[vid].speed_dial = true;
          else
            librarySongs[vid] = {
              video_id: vid,
              speed_dial: true,
              title: track.title || "",
              liked: false,
              downloaded: false,
              thumbnail: "",
            };
          showToast("Added to Speed Dial");
        } else {
          speedDialIds.delete(vid);
          if (librarySongs[vid]) librarySongs[vid].speed_dial = false;
          showToast("Removed from Speed Dial");
        }
        if (activePanel === "home") loadHome();
      } else {
        showToast("Failed: " + (data.error || "Unknown error"));
      }
    })
    .catch(() => showToast("Speed Dial update failed"));
}

function loadHome() {
  fetch("/api/home")
    .then((r) => r.json())
    .then((data) => {
      renderLastPlayed(data.last_played);
      renderSpeedDial(data.speed_dial || []);
    })
    .catch(() => {});
}

function refreshLastPlayed() {
  fetch("/api/home")
    .then((r) => r.json())
    .then((data) => {
      renderLastPlayed(data.last_played);
    })
    .catch(() => {});
}

function renderLastPlayed(last) {
  lastPlayedSection.innerHTML = "";
  if (!last) {
    lastPlayedSection.innerHTML =
      '<div class="home-last-empty">Nothing played yet</div>';
    return;
  }
  const hero = document.createElement("div");
  hero.className = "home-last";
  const imgUrl =
    last.thumbnail && last.thumbnail.trim() ? last.thumbnail : artFrame;
  hero.innerHTML = `
        <img src="${imgUrl}" onerror="this.onerror=null;this.src='${artFrame}';" alt="">
        <div class="home-last-info">
            <span class="home-last-tag">${last.playing ? "Now Playing" : "Last Played"}</span>
            <span class="home-last-title">${last.title || "Unknown"}</span>
            <span class="home-last-meta">${formatTime(last.duration || 0)}</span>
        </div>
        <button class="home-last-play" title="Play"><i class="bi bi-play-fill"></i></button>
    `;
  hero.addEventListener("click", () => playLastPlayed(last));
  lastPlayedSection.appendChild(hero);
}

function isLocalPath(thumb) {
  if (!thumb || !thumb.trim()) return false;
  if (/^https?:\/\//i.test(thumb)) return false;
  if (thumb.startsWith("//")) return false;
  return true;
}

function extractLocalVideoId(thumb) {
  if (!thumb) return "";
  let m = thumb.match(/(?:^|\/)thumb\/([^/?]+)/i);
  if (m) return m[1];
  m = thumb.match(/\.cache\/([^/?]+)\.[A-Za-z0-9]{2,4}$/i);
  if (m) return m[1];
  return "";
}

function findLocalByTitle(title) {
  if (!title) return null;
  const t = title.toLowerCase().trim();
  return (
    localTracks.find((x) => x.title && x.title.toLowerCase().trim() === t) ||
    localTracks.find((x) => x.title && x.title.toLowerCase().includes(t))
  );
}

function playLastPlayed(last) {
  if (!last) return;
  const thumb = last.thumbnail || "";
  if (isLocalPath(thumb)) {
    const vid = extractLocalVideoId(thumb);
    if (vid && librarySongs[vid] && librarySongs[vid].song) {
      const entry = {
        title: last.title || librarySongs[vid].title || vid,
        path: librarySongs[vid].song,
        source: "local",
        channel: "Last Played",
        thumbnail: thumb.includes(".cache/") ? "/thumb/" + vid : "",
      };
      playLocal(entry, [entry]);
      return;
    }
    const found = findLocalByTitle(last.title);
    if (found) {
      playLocal(found, localTracks);
      return;
    }
    showToast("Offline track not found locally");
    return;
  }
  if (!thumb) {
    const found = findLocalByTitle(last.title);
    if (found) {
      playLocal(found, localTracks);
      return;
    }
  }
  playByTitle(last.title);
}

function playByTitle(title) {
  if (!title) return;
  fetch(`/search?q=${encodeURIComponent(title)}&limit=1`)
    .then((r) => r.json())
    .then((data) => {
      const res = data.results || [];
      if (res.length) playTrack(res[0]);
      else showToast("No match found");
    })
    .catch(() => showToast("Search failed"));
}

function renderSpeedDial(entries) {
  speedDialGrid.innerHTML = "";
  if (!entries.length) {
    speedDialGrid.innerHTML =
      '<div class="empty-state">No Speed Dial songs yet</div>';
    return;
  }
  entries.forEach((entry) => {
    const track = {
      ...entry,
      source: "yt",
      channel: "Speed Dial",
      duration: 0,
    };
    const card = document.createElement("div");
    card.className = "sd-card";
    card.innerHTML = `
            ${artImgTag(entry.thumbnail, track)}
            <span>${entry.title || entry.video_id}</span>
        `;
    card.addEventListener("click", () => {
      const lib = librarySongs[entry.video_id];
      if (lib && lib.song) {
        const localEntry = {
          ...track,
          path: lib.song,
          source: "local",
          channel: "Speed Dial",
        };
        playLocal(localEntry, [localEntry]);
      } else {
        playTrack(track);
      }
    });
    const menuBtn = document.createElement("button");
    menuBtn.className = "sd-menu-btn";
    menuBtn.title = "Options";
    menuBtn.innerHTML = '<i class="bi bi-three-dots-vertical"></i>';
    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      showSongMenu(menuBtn, track, "yt");
    });
    card.appendChild(menuBtn);
    speedDialGrid.appendChild(card);
  });
}

function playTrack(item, list) {
  const src = list && list.length ? list : [item];
  const tracks = src.map((t) => ({ ...t, source: "yt" }));
  addHistory();
  queue = tracks;
  queueIndex = Math.max(
    0,
    queue.findIndex((e) => e.video_id === item.video_id),
  );
  loadAndPlay(queue[queueIndex]);
  renderQueue();
}

function playLocal(item, list) {
  const src =
    list && list.length ? list : localTracks.length ? localTracks : [item];
  const tracks = src.map((t) => ({
    ...t,
    source: "local",
    channel: t.channel || t.album || "Local Music",
  }));
  addHistory();
  queue = tracks;
  queueIndex = Math.max(
    0,
    queue.findIndex((e) => e.path === item.path),
  );
  loadAndPlay(queue[queueIndex]);
  renderQueue();
}

function addHistory() {
  if (queueIndex >= 0 && queue[queueIndex]) {
    playHistory.push(queue[queueIndex]);
    if (playHistory.length > 50) playHistory.shift();
  }
}

function addToQueue(item, doRender = true) {
  if (item.source === "local") item.channel = item.channel || "Local Music";
  queue.push(item);
  if (queueIndex === -1) queueIndex = 0;
  if (doRender) renderQueue();
}

function renderQueue() {
  queueContainer.innerHTML =
    queue.length === 0 ? '<div class="empty-state">Queue is empty</div>' : "";
  queue.forEach((item, idx) => {
    const card = document.createElement("div");
    card.className = "song-card" + (idx === queueIndex ? " active" : "");
    card.dataset.title = item.title;
    card.dataset.videoId = item.video_id || "";
    card.dataset.path = item.path || "";
    const dur = item.duration || "";
    card.innerHTML = `
            ${artImgTag(item.thumbnail, item)}
            <div class="song-info">
                <div class="song-title">${item.title}</div>
                <div class="song-artist">${item.channel || item.artist || "Unknown"}</div>
            </div>
            ${dur ? `<span class="song-duration">${formatTime(dur)}</span>` : ""}
            <div class="song-actions" style="opacity:1">
                <button class="queue-remove" data-idx="${idx}" title="Remove"><i class="bi bi-x-lg"></i></button>
                <button class="song-menu-btn" title="Options"><i class="bi bi-three-dots-vertical"></i></button>
            </div>
        `;
    card.addEventListener("click", () => {
      addHistory();
      queueIndex = idx;
      loadAndPlay(item);
      renderQueue();
    });
    card.querySelector(".queue-remove").addEventListener("click", (e) => {
      e.stopPropagation();
      removeFromQueue(parseInt(e.currentTarget.dataset.idx));
    });
    card.querySelector(".song-menu-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      showSongMenu(e.currentTarget, item, item.source || "yt");
    });
    queueContainer.appendChild(card);
  });
  updateQueueBarTab();
}

function updateQueueBarTab() {
  const toolbar = document.querySelector("#panelQueue .panel-toolbar");
  if (!toolbar) return;
  const remaining = queue.length - queueIndex - 1;
  const count =
    queue.length > 0
      ? remaining > 0
        ? `${queue.length} songs, ${remaining} next`
        : `${queue.length} song${queue.length !== 1 ? "s" : ""}`
      : "";
  let label = toolbar.querySelector(".queue-count-label");
  if (!label) {
    label = document.createElement("span");
    label.className = "queue-count-label";
    label.style.cssText = "font-size:11px;color:var(--text3);margin-left:auto;";
    toolbar.appendChild(label);
  }
  label.textContent = count;
}

function removeFromQueue(idx) {
  const wasPlaying = idx === queueIndex;
  queue.splice(idx, 1);
  if (wasPlaying) {
    if (queue.length === 0) {
      queueIndex = -1;
      audio.pause();
      audio.src = "";
      updatePlayBtn(false);
    } else {
      queueIndex = idx >= queue.length ? queue.length - 1 : idx;
      loadAndPlay(queue[queueIndex]);
    }
  } else if (idx < queueIndex) {
    queueIndex--;
  }
  renderQueue();
}

function scanLocal() {
  fetch("/offline")
    .then((r) => r.json())
    .then((data) => {
      localTracks = (data.results || []).map((t) => ({
        ...t,
        source: "local",
        channel: "Local Files",
      }));
      loadLocalTracks();
    })
    .catch(() => {});
  fetch("/api/albums")
    .then((r) => r.json())
    .then((data) => {
      albumsGrid.innerHTML = "";
      (data.albums || []).forEach((album) => {
        const card = document.createElement("div");
        card.className = "album-card";
        card.innerHTML = `<i class="bi bi-folder2-open"></i><span>${album}</span>`;
        card.addEventListener("click", () => showAlbumSongs(album));
        albumsGrid.appendChild(card);
      });
    })
    .catch(() => {});
}

function showAlbumSongs(album) {
  fetch(`/api/album/${encodeURIComponent(album)}`)
    .then((r) => r.json())
    .then((data) => {
      const songs = data.results || [];
      albumSongs.innerHTML = `<div class="album-header"><button id="albumBackBtn"><i class="bi bi-arrow-left"></i></button> ${album}</div>`;
      document.getElementById("albumBackBtn").addEventListener("click", () => {
        albumSongs.innerHTML = "";
      });
      songs.forEach((item) => {
        const entry = {
          title: item.title,
          path: item.path,
          source: "local",
          channel: album,
          thumbnail: "",
        };
        const card = createSongCard(entry, "local");
        card.addEventListener("click", () => playLocal(entry, songs));
        albumSongs.appendChild(card);
      });
    })
    .catch(() => {});
}

function loadLocalTracks() {
  if (localTracks.length === 0) {
    localSongsContainer.innerHTML =
      '<div class="empty-state">No local music. Scan to load.</div>';
    return;
  }
  localSongsContainer.innerHTML = "";
  localTracks.forEach((t) => {
    const card = createSongCard(t, "local");
    card.addEventListener("click", () => playLocal(t, localTracks));
    localSongsContainer.appendChild(card);
  });
}

function toPlaylistSong(track) {
  const song = { title: (track.title || "Unknown").trim() };
  if (track.video_id) {
    song.video_id = track.video_id;
    song.url = `https://www.youtube.com/watch?v=${track.video_id}`;
  } else if (track.path) {
    song.url = track.path;
  }
  return song;
}

function openSavePlaylistModal() {
  const songs = queue.filter((t) => !t._autoAdded);
  if (songs.length === 0) {
    showToast("Queue is empty");
    return;
  }
  playlistModalMode = "saveQueue";
  playlistModalTitle.innerHTML =
    '<i class="bi bi-list-ul"></i> Save as Playlist';
  playlistNameInput.value = "";
  playlistModal.classList.add("open");
  setTimeout(() => playlistNameInput.focus(), 50);
}

function openNewPlaylistModal() {
  playlistModalMode = "create";
  playlistModalTitle.innerHTML = '<i class="bi bi-plus-lg"></i> New Playlist';
  playlistNameInput.value = "";
  playlistModal.classList.add("open");
  setTimeout(() => playlistNameInput.focus(), 50);
}

function submitPlaylistModal() {
  const name = playlistNameInput.value.trim();
  if (!name) {
    showToast("Enter a playlist name");
    return;
  }
  if (playlistModalMode === "create") {
    createPlaylist(name).then((ok) => {
      if (ok) playlistModal.classList.remove("open");
    });
    return;
  }
  if (playlistModalMode === "song") {
    if (pendingSong) addSongToPlaylist(name, pendingSong);
    playlistModal.classList.remove("open");
    pendingSong = null;
    return;
  }
  const songs = queue.filter((t) => !t._autoAdded).map(toPlaylistSong);
  if (songs.length === 0) {
    showToast("No playable tracks in queue");
    return;
  }
  pendingPlaylist = { name, songs };
  fetch("/api/playlists")
    .then((r) => r.json())
    .then((data) => {
      const exists = (data.playlists || []).some((p) => p.name === name);
      if (exists) {
        openExistsDialog(name, songs);
        playlistModal.classList.remove("open");
      } else {
        doSavePlaylist(name, songs, "append");
      }
    });
}

function doSavePlaylist(name, songs, mode) {
  fetch("/api/playlists/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, songs, mode }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.success) {
        playlistModal.classList.remove("open");
        showToast(
          `Saved ${data.count} song${data.count !== 1 ? "s" : ""} to "${name}"`,
        );
        loadPlaylists();
      } else {
        showToast("Failed: " + (data.error || "Unknown error"));
      }
    })
    .catch(() => showToast("Save failed"));
}

function openExistsDialog(name, songs) {
  pendingPlaylist = { name, songs };
  existsMsg.textContent = `Playlist "${name}" already exists. Append or overwrite?`;
  playlistExistsModal.classList.add("open");
}

function loadPlaylists() {
  fetch("/api/playlists")
    .then((r) => r.json())
    .then((data) => {
      playlistsCache = data.playlists || [];
      renderSidebarPlaylists();
    })
    .catch(() => {});
}

function fmtTotalDur(secs) {
  if (!secs || secs < 60) return "";
  const m = Math.floor(secs / 60);
  return ` \u00b7 ${m}m`;
}

function renderSidebarPlaylists() {
  sidebarPlaylists.innerHTML = "";
  if (playlistsCache.length === 0) {
    sidebarPlaylists.innerHTML =
      '<div class="sidebar-empty">No playlists yet</div>';
    return;
  }
  playlistsCache.forEach((p) => {
    const item = document.createElement("div");
    item.className =
      "sidebar-playlist-item" +
      (currentPlaylistName === p.name ? " active" : "");
    const sub = [
      `${p.count} song${p.count !== 1 ? "s" : ""}`,
      fmtTotalDur(p.duration),
    ]
      .filter(Boolean)
      .join("");
    item.innerHTML = `<i class="bi bi-list-ul"></i><span>${p.name}</span>`;
    item.title = sub || p.name;
    item.addEventListener("click", () => openPlaylist(p.name));
    sidebarPlaylists.appendChild(item);
  });
}

function openPlaylist(name) {
  currentPlaylistName = name;
  renderSidebarPlaylists();
  fetch(`/api/playlist?name=${encodeURIComponent(name)}`)
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        showToast(data.error);
        return;
      }
      renderPlaylistDetail(data.name, data.songs || [], data.description || "");
      setPanel("playlistDetail");
    })
    .catch(() => {});
}

function renderPlaylistDetail(name, songs, description) {
  playlistDetailContent.innerHTML = `<div class="album-header">
        <button id="plBackBtn" title="Back"><i class="bi bi-arrow-left"></i></button>
        <span>${name}</span>
        <button id="plPlayBtn" title="Play"><i class="bi bi-play-fill"></i></button>
        <button id="plRenameBtn" title="Rename"><i class="bi bi-pencil"></i></button>
        <button id="plExportBtn" title="Export M3U"><i class="bi bi-file-earmark-arrow-down"></i></button>
        <button id="plDedupeBtn" title="Remove duplicates"><i class="bi bi-files"></i></button>
        <button id="plDeleteBtn" title="Delete"><i class="bi bi-trash"></i></button>
    </div>`;
  if (description) {
    playlistDetailContent.insertAdjacentHTML(
      "beforeend",
      `<div style="color:var(--text3);font-size:11px;padding:0 4px 6px;">${description}</div>`,
    );
  }
  document.getElementById("plBackBtn").addEventListener("click", () => {
    playlistDetailContent.innerHTML = "";
    setPanel("home");
  });
  document
    .getElementById("plPlayBtn")
    .addEventListener("click", () => playPlaylist(songs));
  document
    .getElementById("plDeleteBtn")
    .addEventListener("click", () => deletePlaylist(name));
  document.getElementById("plRenameBtn").addEventListener("click", () => {
    const newName = window.prompt("New playlist name:", name);
    if (!newName || newName.trim() === name) return;
    fetch("/api/playlists/rename", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old: name, new: newName.trim() }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.success) {
          showToast(`Renamed to "${data.name}"`);
          loadPlaylists();
          openPlaylist(data.name);
        } else {
          showToast("Failed: " + (data.error || "Unknown error"));
        }
      })
      .catch(() => showToast("Rename failed"));
  });
  document.getElementById("plExportBtn").addEventListener("click", () => {
    window.location.href = `/api/playlist/export?name=${encodeURIComponent(name)}`;
  });
  document.getElementById("plDedupeBtn").addEventListener("click", () => {
    fetch("/api/playlist/dedupe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    })
      .then((r) => r.json())
      .then((data) => {
        showToast(
          data.removed
            ? `Removed ${data.removed} duplicate${data.removed !== 1 ? "s" : ""}`
            : "No duplicates found",
        );
        loadPlaylists();
        openPlaylist(name);
      })
      .catch(() => showToast("Dedupe failed"));
  });
  const dragOrder = (fromIdx, toIdx) => {
    const order = songs.map((s) => s.video_id);
    const [moved] = order.splice(fromIdx, 1);
    order.splice(toIdx, 0, moved);
    fetch("/api/playlist/reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, order }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.success) openPlaylist(name);
        else showToast("Failed: " + (data.error || "Reorder rejected"));
      })
      .catch(() => showToast("Reorder failed"));
  };
  if (songs.length === 0) {
    playlistDetailContent.insertAdjacentHTML(
      "beforeend",
      '<div class="empty-state">Playlist is empty</div>',
    );
    return;
  }
  let dragIdx = null;
  songs.forEach((item, idx) => {
    const entry = {
      ...item,
      source: item.video_id ? "yt" : "local",
      channel: item.channel || "Playlist",
      duration: item.duration || 0,
    };
    const card = createSongCard(entry, entry.source);
    card.addEventListener("click", () => playPlaylist(songs, idx));
    if (item.local) {
      card.insertAdjacentHTML(
        "beforeend",
        '<span class="song-duration" title="Available on device" style="color:var(--text);"><i class="bi bi-hdd"></i></span>',
      );
    }
    card.draggable = true;
    card.style.cursor = "grab";
    card.addEventListener("dragstart", () => {
      dragIdx = idx;
      card.style.opacity = "0.4";
    });
    card.addEventListener("dragend", () => {
      card.style.opacity = "";
      dragIdx = null;
    });
    card.addEventListener("dragover", (e) => e.preventDefault());
    card.addEventListener("drop", (e) => {
      e.preventDefault();
      if (dragIdx === null || dragIdx === idx) return;
      dragOrder(dragIdx, idx);
    });
    const removeBtn = document.createElement("button");
    removeBtn.title = "Remove from playlist";
    removeBtn.innerHTML = '<i class="bi bi-x-lg"></i>';
    removeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      removeFromPlaylist(name, idx);
    });
    card.querySelector(".song-actions").appendChild(removeBtn);
    playlistDetailContent.appendChild(card);
  });
}

function playPlaylist(songs, startIdx) {
  if (!songs.length) return;
  startIdx = startIdx || 0;
  const entries = songs.map((s) => ({
    ...s,
    source: s.video_id ? "yt" : "local",
    channel: s.channel || "Playlist",
    duration: s.duration || 0,
  }));
  addHistory();
  queue = entries;
  queueIndex = Math.min(startIdx, entries.length - 1);
  loadAndPlay(queue[queueIndex]);
  renderQueue();
}

function deletePlaylist(name) {
  if (!window.confirm(`Delete playlist "${name}"?`)) return;
  fetch("/api/playlists/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.success) {
        showToast(`Deleted "${name}"`);
        playlistDetailContent.innerHTML = "";
        currentPlaylistName = null;
        loadPlaylists();
        setPanel("home");
      } else {
        showToast("Failed: " + (data.error || "Unknown error"));
      }
    })
    .catch(() => showToast("Delete failed"));
}

function removeFromPlaylist(name, index) {
  fetch("/api/playlist/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, index }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.success) {
        showToast("Removed from playlist");
        loadPlaylists();
        openPlaylist(name);
      } else {
        showToast("Failed: " + (data.error || "Unknown error"));
      }
    })
    .catch(() => showToast("Remove failed"));
}

function createPlaylist(name) {
  return fetch("/api/playlists/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.success) {
        showToast(`Created "${name}"`);
        loadPlaylists();
        return true;
      }
      showToast("Failed: " + (data.error || "Unknown error"));
      return false;
    })
    .catch(() => {
      showToast("Create failed");
      return false;
    });
}

function addSongToPlaylist(name, track) {
  const song = toPlaylistSong(track);
  fetch("/api/playlist/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, song }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.success) {
        showToast(`Added to "${name}"`);
        loadPlaylists();
      } else {
        showToast("Failed: " + (data.error || "Unknown error"));
      }
    })
    .catch(() => showToast("Add failed"));
}

function openPlaylistMenu(btn, track) {
  closePlaylistMenu();
  const menu = document.createElement("div");
  menu.className = "pl-menu";
  if (!playlistsCache.length) {
    const empty = document.createElement("div");
    empty.className = "pl-menu-empty";
    empty.textContent = "No playlists yet";
    menu.appendChild(empty);
  }
  playlistsCache.forEach((p) => {
    const item = document.createElement("button");
    item.type = "button";
    item.textContent = p.name;
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      closePlaylistMenu();
      addSongToPlaylist(p.name, track);
    });
    menu.appendChild(item);
  });
  const newItem = document.createElement("button");
  newItem.type = "button";
  newItem.className = "pl-menu-new";
  newItem.innerHTML = '<i class="bi bi-plus-lg"></i> New playlist';
  newItem.addEventListener("click", (e) => {
    e.stopPropagation();
    closePlaylistMenu();
    pendingSong = track;
    playlistModalMode = "song";
    playlistModalTitle.innerHTML =
      '<i class="bi bi-plus-lg"></i> Save to Playlist';
    playlistNameInput.value = "";
    playlistModal.classList.add("open");
    setTimeout(() => playlistNameInput.focus(), 50);
  });
  menu.appendChild(newItem);
  document.body.appendChild(menu);
  const rect = btn.getBoundingClientRect();
  const mw = 180;
  let left = rect.left;
  if (left + mw > window.innerWidth - 8) left = window.innerWidth - mw - 8;
  menu.style.left = left + "px";
  menu.style.top = rect.bottom + 4 + "px";
  setTimeout(() => {
    document.addEventListener("click", closePlaylistMenu, { once: true });
  }, 0);
}

function closePlaylistMenu() {
  document.querySelectorAll(".pl-menu").forEach((m) => m.remove());
}

function loadLiked() {
  fetch("/api/liked")
    .then((r) => r.json())
    .then((data) => {
      const songs = data.results || [];
      const ids = data.liked_ids || [];
      const container = document.getElementById("likedSongs");
      if (!container) return;
      if (songs.length === 0 && ids.length === 0) {
        container.innerHTML =
          '<div class="empty-state">No liked songs yet</div>';
        return;
      }
      container.innerHTML = "";
      songs.forEach((item) => {
        const entry = {
          ...item,
          source: "local",
          channel: "Liked Songs",
          thumbnail: "",
        };
        const card = createSongCard(entry, "local");
        card.addEventListener("click", () => playLocal(entry, songs));
        container.appendChild(card);
      });
      const entries = data.liked_entries || [];
      if (entries.length > 0 && songs.length === 0) {
        entries.forEach((entry) => {
          const item = {
            video_id: entry.video_id,
            title: entry.title || entry.video_id,
            source: "yt",
            channel: "Liked",
            thumbnail: "",
            duration: 0,
          };
          const card = createSongCard(item, "yt");
          card.addEventListener("click", () => playTrack(item));
          container.appendChild(card);
        });
      }
    })
    .catch(() => {});
}

function loadSettings() {
  fetch("/api/settings")
    .then((r) => r.json())
    .then((data) => {
      if (data && Object.keys(data).length > 0) {
        Object.assign(settings, data);
        applySettings();
        updateSettingsUI();
      }
    });
}

function applySettings() {
  document.documentElement.setAttribute("data-theme", settings.theme || "dark");
  volumeSlider.value = settings.defaultVolume || 80;
  audio.volume = (settings.defaultVolume || 80) / 100;
  if (settings.defaultSource) setSearchSource(settings.defaultSource);
}

function updateSettingsUI() {
  document.getElementById("setTheme").value = settings.theme || "dark";
  document.getElementById("setBgBlur").value = settings.bgBlur || 0;
  document.getElementById("setBgDim").value = settings.bgDim || 80;
  document.getElementById("setVolume").value = settings.defaultVolume || 80;
  document.getElementById("setMiniOnBlur").checked =
    settings.miniOnBlur || false;
  document.getElementById("setDefaultSource").value =
    settings.defaultSource || "youtube";
  document.getElementById("setDownloadPath").value =
    settings.downloadPath || "~/.flow/downloads";
  document.getElementById("setDownloadFormat").value =
    settings.format || "webm";
}

function saveSettingsToAPI() {
  const newSettings = {
    theme: document.getElementById("setTheme").value,
    bgBlur: parseInt(document.getElementById("setBgBlur").value),
    bgDim: parseInt(document.getElementById("setBgDim").value),
    defaultVolume: parseInt(document.getElementById("setVolume").value),
    miniOnBlur: document.getElementById("setMiniOnBlur").checked,
    defaultSource: document.getElementById("setDefaultSource").value,
    downloadPath:
      document.getElementById("setDownloadPath").value || "~/.flow/downloads",
    format: document.getElementById("setDownloadFormat").value || "webm",
  };
  fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(newSettings),
  })
    .then((r) => r.json())
    .then((data) => {
      Object.assign(settings, data.settings || newSettings);
      applySettings();
      settingsModal.classList.remove("open");
      showToast("Settings saved");
    });
}

function resetSettings() {
  settings = {
    theme: "dark",
    bgBlur: 0,
    bgDim: 80,
    defaultVolume: 80,
    miniOnBlur: false,
    defaultSource: "youtube",
    downloadPath: "~/.flow/downloads",
    format: "webm",
  };
  applySettings();
  updateSettingsUI();
  fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

function showToast(msg, duration) {
  duration = duration || 3000;
  toastEl.textContent = msg;
  toastEl.classList.add("show");
  setTimeout(() => toastEl.classList.remove("show"), duration);
}

function loadLibrary() {
  fetch("/api/library")
    .then((r) => r.json())
    .then((data) => {
      librarySongs = {};
      downloadedIds = new Set();
      (data.songs || []).forEach((s) => {
        librarySongs[s.video_id] = s;
        if (s.downloaded) downloadedIds.add(s.video_id);
      });
    })
    .catch(() => {});
}

function setDownloadBtnState(downloaded) {
  currentDownloaded = downloaded;
  downloadBtn.classList.toggle("downloaded", downloaded);
  downloadBtn.querySelector("i").className = downloaded
    ? "bi bi-check-circle"
    : "bi bi-download";
  downloadBtn.title = downloaded ? "Downloaded - click to remove" : "Download";
}

function checkDownload(videoId) {
  if (!videoId) {
    setDownloadBtnState(false);
    return;
  }
  if (downloadedIds.has(videoId)) {
    setDownloadBtnState(true);
    return;
  }
  fetch("/api/library")
    .then((r) => r.json())
    .then((data) => {
      librarySongs = {};
      downloadedIds = new Set();
      (data.songs || []).forEach((s) => {
        librarySongs[s.video_id] = s;
        if (s.downloaded) downloadedIds.add(s.video_id);
      });
      setDownloadBtnState(downloadedIds.has(videoId));
    })
    .catch(() => {});
}

function deleteDownload() {
  if (queueIndex < 0 || !queue[queueIndex]) return;
  const track = queue[queueIndex];
  const vid = track.video_id;
  if (!vid) return;
  if (!window.confirm("Remove this download from your library?")) return;
  fetch("/api/delete-download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: vid }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.success) {
        downloadedIds.delete(vid);
        if (librarySongs[vid]) {
          librarySongs[vid].downloaded = false;
          librarySongs[vid].thumbnail = "";
        }
        setDownloadBtnState(false);
        showToast("Removed download");
      } else {
        showToast("Failed: " + (data.error || "Not downloaded"));
      }
    })
    .catch(() => showToast("Failed to remove download"));
}

function downloadTrack() {
  if (queueIndex < 0 || !queue[queueIndex]) {
    showToast("No track selected");
    return;
  }
  const track = queue[queueIndex];
  const vid = track.video_id;
  if (!vid) {
    showToast("Cannot download local tracks");
    return;
  }
  if (currentDownloaded) {
    deleteDownload();
    return;
  }
  const saveDir = settings.downloadPath || "~/.flow/downloads";
  downloadBtn.classList.add("downloading");
  showToast("Downloading...");
  fetch("/download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_id: vid,
      save_dir: saveDir,
      format: settings.format,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      downloadBtn.classList.remove("downloading");
      if (data.success) {
        downloadedIds.add(vid);
        if (librarySongs[vid]) {
          librarySongs[vid].downloaded = true;
          if (data.thumbnail) librarySongs[vid].thumbnail = data.thumbnail;
        } else {
          librarySongs[vid] = {
            video_id: vid,
            title: data.title || track.title || "",
            liked: false,
            downloaded: true,
            thumbnail: data.thumbnail || "",
          };
        }
        setDownloadBtnState(true);
        showToast("Downloaded: " + (data.title || track.title));
      } else {
        showToast("Failed: " + (data.error || "Unknown error"));
      }
    })
    .catch(() => {
      downloadBtn.classList.remove("downloading");
      showToast("Download failed");
    });
}

downloadBtn.addEventListener("click", downloadTrack);

let currentLiked = false;

function checkLiked(videoId) {
  if (!videoId) {
    currentLiked = false;
    likeBtn.querySelector("i").className = "bi bi-heart";
    return;
  }
  const entry = librarySongs[videoId];
  if (entry) {
    currentLiked = entry.liked || false;
    likeBtn.querySelector("i").className = currentLiked
      ? "bi bi-heart-fill"
      : "bi bi-heart";
    likeBtn.classList.toggle("active", currentLiked);
    return;
  }
  fetch("/api/library")
    .then((r) => r.json())
    .then((data) => {
      librarySongs = {};
      downloadedIds = new Set();
      (data.songs || []).forEach((s) => {
        librarySongs[s.video_id] = s;
        if (s.downloaded) downloadedIds.add(s.video_id);
      });
      const e = librarySongs[videoId];
      currentLiked = (e && e.liked) || false;
      likeBtn.querySelector("i").className = currentLiked
        ? "bi bi-heart-fill"
        : "bi bi-heart";
      likeBtn.classList.toggle("active", currentLiked);
    })
    .catch(() => {});
}

function toggleLike() {
  if (queueIndex < 0 || !queue[queueIndex]) return;
  const track = queue[queueIndex];
  const vid = track.video_id;
  if (!vid) {
    showToast("Cannot like local tracks");
    return;
  }
  fetch("/api/like", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_id: vid,
      title: track.title || "Unknown",
      save_dir: settings.downloadPath || "~/.flow/downloads",
      format: settings.format,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      currentLiked = data.liked;
      likeBtn.querySelector("i").className = currentLiked
        ? "bi bi-heart-fill"
        : "bi bi-heart";
      likeBtn.classList.toggle("active", currentLiked);
      if (librarySongs[vid]) librarySongs[vid].liked = currentLiked;
      else
        librarySongs[vid] = {
          video_id: vid,
          liked: currentLiked,
          downloaded: false,
          thumbnail: "",
        };
      if (currentLiked) {
        showToast("Liked - downloading...");
        pollLikeDownload(vid);
      } else {
        showToast("Removed from liked");
      }
    });
}

function pollLikeDownload(vid) {
  let tries = 0;
  const iv = setInterval(() => {
    tries++;
    if (tries > 60) {
      clearInterval(iv);
      return;
    }
    fetch("/api/library")
      .then((r) => r.json())
      .then((data) => {
        (data.songs || []).forEach((s) => {
          librarySongs[s.video_id] = s;
          if (s.downloaded) downloadedIds.add(s.video_id);
        });
        if (librarySongs[vid] && librarySongs[vid].downloaded) {
          clearInterval(iv);
          setDownloadBtnState(true);
          if (queue[queueIndex] && queue[queueIndex].video_id === vid) {
            applyArt(playerArt, queue[queueIndex].thumbnail, queue[queueIndex]);
            setPlayerBarBg(queue[queueIndex]);
          }
          showToast("Liked - downloaded");
        }
      })
      .catch(() => {});
  }, 2000);
}

likeBtn.addEventListener("click", toggleLike);

document.addEventListener("keydown", (e) => {
  if (e.target === searchInput) return;
  switch (e.key) {
    case " ":
    case "k":
      e.preventDefault();
      togglePlay();
      break;
    case "ArrowLeft":
      e.preventDefault();
      audio.currentTime = Math.max(0, audio.currentTime - 5);
      break;
    case "ArrowRight":
      e.preventDefault();
      audio.currentTime = Math.min(audio.duration, audio.currentTime + 5);
      break;
    case "ArrowUp":
      e.preventDefault();
      audio.volume = Math.min(1, audio.volume + 0.1);
      volumeSlider.value = audio.volume * 100;
      break;
    case "ArrowDown":
      e.preventDefault();
      audio.volume = Math.max(0, audio.volume - 0.1);
      volumeSlider.value = audio.volume * 100;
      break;
    case "n":
      nextTrack();
      break;
    case "p":
      prevTrack();
      break;
  }
});

function pollControls() {
  fetch("/api/control/poll")
    .then((r) => r.json())
    .then((data) => {
      const cmd = data.command;
      if (cmd === "next") nextTrack();
      else if (cmd === "previous") prevTrack();
      else if (cmd === "stop" && audio.src) togglePlay();
      else if ((cmd === "seek" || cmd === "seekb") && audio.src) {
        const d = Number(data.delta) || 0;
        const end = audio.duration || audio.currentTime;
        audio.currentTime = Math.max(0, Math.min(end, audio.currentTime + d));
      }
    })
    .catch(() => {});
}

loadSettings();
setPanel(panelFromPath());
scanLocal();
loadLiked();
loadLibrary();
loadPlaylists();
loadHome();
if (activePanel === "search") doSearch();
fetch("/api/speed-dial")
  .then((r) => r.json())
  .then((data) => {
    speedDialIds = new Set((data.results || []).map((e) => e.video_id));
  })
  .catch(() => {});
setInterval(pollControls, 1000);
