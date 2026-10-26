// Alice Display & RGB Ring Controller Logic

document.addEventListener('DOMContentLoaded', () => {
  const statusBadge = document.getElementById('statusBadge');
  const statusText = document.getElementById('statusText');
  const statusDot = statusBadge.querySelector('.status-dot');
  const brightnessSlider = document.getElementById('brightnessSlider');
  const brightnessVal = document.getElementById('brightnessVal');
  const modeToggleBtn = document.getElementById('modeToggleBtn');
  const modeText = document.getElementById('modeText');
  const patternSelect = document.getElementById('patternSelect');
  const playPatternBtn = document.getElementById('playPatternBtn');
  const framesStrip = document.getElementById('framesStrip');
  const nativeColorPicker = document.getElementById('nativeColorPicker');
  const selectedLedBadge = document.getElementById('selectedLedBadge');

  let currentBrightness = 150;
  let isScreenLocked = true;
  let selectedSlot = 'all'; // 'all', '1', '2', '3', '4', '5', '6'
  let customFrames = [];

  // Helper hex to rgb
  function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
      r: parseInt(result[1], 16),
      g: parseInt(result[2], 16),
      b: parseInt(result[3], 16)
    } : { r: 0, g: 0, b: 0 };
  }

  function rgbToHex(r, g, b) {
    return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
  }

  // --- Initial Status Sync ---
  async function syncStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      if (data.connected) {
        statusDot.classList.remove('offline');
        statusText.textContent = `Подключено: ${data.target}`;
      } else {
        statusDot.classList.add('offline');
        statusText.textContent = `Ошибка подключения: ${data.target}`;
      }

      currentBrightness = data.brightness || 150;
      brightnessSlider.value = currentBrightness;
      brightnessVal.textContent = currentBrightness;

      // Update Screen Lock Mode
      isScreenLocked = data.screen_locked;
      updateModeUI();

      // Update Segments
      if (data.segments) {
        document.querySelectorAll('.segment').forEach(el => {
          const seg = el.getAttribute('data-seg');
          if (data.segments[seg] && data.segments[seg] > 0) {
            el.classList.add('lit');
          } else {
            el.classList.remove('lit');
          }
        });
      }

      // Update RGB Ring LEDs slots
      if (data.ring_leds && Array.isArray(data.ring_leds)) {
        data.ring_leds.forEach((c, idx) => {
          const ledEl = document.getElementById(`rled-${idx + 1}`);
          if (ledEl) {
            const hex = rgbToHex(c.r, c.g, c.b);
            ledEl.style.backgroundColor = hex;
            ledEl.style.boxShadow = (c.r === 0 && c.g === 0 && c.b === 0) ? 'none' : `0 0 10px ${hex}`;
          }
        });
      }
    } catch (e) {
      statusDot.classList.add('offline');
      statusText.textContent = 'Сервер недоступен';
    }
  }

  // --- Screen Lock Mode UI ---
  function updateModeUI() {
    if (isScreenLocked) {
      modeToggleBtn.classList.remove('inactive');
      modeToggleBtn.classList.add('active');
      modeToggleBtn.querySelector('.icon').textContent = '🔒';
      modeText.textContent = 'Защита экрана: ВКЛ (Часы не стирают)';
    } else {
      modeToggleBtn.classList.remove('active');
      modeToggleBtn.classList.add('inactive');
      modeToggleBtn.querySelector('.icon').textContent = '🕒';
      modeText.textContent = 'Режим: Часы Алисы активны';
    }
  }

  modeToggleBtn.addEventListener('click', async () => {
    isScreenLocked = !isScreenLocked;
    const mode = isScreenLocked ? 'custom' : 'alice';
    updateModeUI();
    await fetch('/api/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode })
    });
  });

  // --- Click on Screen Segments ---
  document.querySelectorAll('.segment').forEach(el => {
    el.addEventListener('click', async () => {
      const seg = el.getAttribute('data-seg');
      const willBeLit = !el.classList.contains('lit');
      el.classList.toggle('lit', willBeLit);

      // Auto ensure locked mode visually
      isScreenLocked = true;
      updateModeUI();

      try {
        const res = await fetch('/api/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ segment: seg })
        });
        const data = await res.json();
        el.classList.toggle('lit', data.value > 0);
      } catch (err) {
        console.error('Toggle error:', err);
      }
    });
  });

  // --- Brightness Slider ---
  brightnessSlider.addEventListener('input', (e) => {
    currentBrightness = e.target.value;
    brightnessVal.textContent = currentBrightness;
  });

  brightnessSlider.addEventListener('change', async (e) => {
    await fetch('/api/brightness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: e.target.value })
    });
  });

  // --- Quick Screen Buttons ---
  document.getElementById('clearBtn').addEventListener('click', async () => {
    document.querySelectorAll('.segment').forEach(el => el.classList.remove('lit'));
    await fetch('/api/clear', { method: 'POST' });
  });

  document.getElementById('allOnBtn').addEventListener('click', async () => {
    document.querySelectorAll('.segment').forEach(el => el.classList.add('lit'));
    await fetch('/api/all', { method: 'POST' });
  });

  document.getElementById('colonBtn').addEventListener('click', async () => {
    const p1 = document.getElementById('seg-PLUS1');
    const p2 = document.getElementById('seg-PLUS2');
    const newState = !p1.classList.contains('lit');
    p1.classList.toggle('lit', newState);
    p2.classList.toggle('lit', newState);

    const val = newState ? currentBrightness : 0;
    await fetch('/api/segment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segment: 'PLUS1', value: val })
    });
    await fetch('/api/segment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segment: 'PLUS2', value: val })
    });
  });

  document.getElementById('degreeBtn').addEventListener('click', async () => {
    const deg = document.getElementById('seg-DEGREE');
    const newState = !deg.classList.contains('lit');
    deg.classList.toggle('lit', newState);
    const val = newState ? currentBrightness : 0;
    await fetch('/api/segment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segment: 'DEGREE', value: val })
    });
  });

  // --- Text Input ---
  const textInput = document.getElementById('textInput');
  const sendTextBtn = document.getElementById('sendTextBtn');

  async function sendText() {
    const text = textInput.value.trim();
    if (!text) return;
    isScreenLocked = true;
    updateModeUI();
    const res = await fetch('/api/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    const data = await res.json();
    if (data.state) {
      document.querySelectorAll('.segment').forEach(el => {
        const seg = el.getAttribute('data-seg');
        el.classList.toggle('lit', data.state[seg] > 0);
      });
    }
  }

  sendTextBtn.addEventListener('click', sendText);
  textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendText();
  });

  // --- Scrolling Text ---
  const scrollInput = document.getElementById('scrollInput');
  document.getElementById('startScrollBtn').addEventListener('click', async () => {
    const text = scrollInput.value.trim();
    if (!text) return;
    isScreenLocked = true;
    updateModeUI();
    await fetch('/api/scroll', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, speed: 0.25 })
    });
  });

  document.getElementById('stopScrollBtn').addEventListener('click', async () => {
    await fetch('/api/stop', { method: 'POST' });
  });

  // --- Quick Presets ---
  const PRESETS = {
    like: ['A3', 'B3', 'C3', 'D3', 'G3', 'A4', 'B4', 'C4', 'D4', 'G4'],
    dislike: ['D1', 'E1', 'F1', 'G1', 'D2', 'E2', 'F2', 'G2'],
    pause: ['B2', 'C2', 'E3', 'F3'],
    play: ['E2', 'F2', 'A3', 'B3', 'C3', 'D3'],
    smile: ['G1', 'G2', 'PLUS1', 'PLUS2', 'G3', 'G4', 'D2', 'D3'],
    bell: ['A2', 'B2', 'F2', 'PLUS1', 'PLUS2', 'A3', 'C3', 'E3', 'D3'],
    time: () => {
      const now = new Date();
      const h = String(now.getHours()).padStart(2, '0');
      const m = String(now.getMinutes()).padStart(2, '0');
      return `${h}:${m}`;
    }
  };

  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const type = btn.getAttribute('data-preset');
      if (type === 'time') {
        textInput.value = PRESETS.time();
        sendText();
        return;
      }
      const segs = PRESETS[type];
      if (segs) {
        document.querySelectorAll('.segment').forEach(el => el.classList.remove('lit'));
        const cmds = {};
        segs.forEach(s => {
          const el = document.getElementById(`seg-${s}`);
          if (el) el.classList.add('lit');
          cmds[s] = currentBrightness;
        });
        await fetch('/api/clear', { method: 'POST' });
        for (const [s, v] of Object.entries(cmds)) {
          await fetch('/api/segment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ segment: s, value: v })
          });
        }
      }
    });
  });

  // --- Load Patterns ---
  async function loadPatterns() {
    try {
      const res = await fetch('/api/patterns');
      const data = await res.json();
      patternSelect.innerHTML = '';
      data.patterns.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p;
        opt.textContent = p;
        patternSelect.appendChild(opt);
      });
    } catch (e) {
      patternSelect.innerHTML = '<option value="">Ошибка</option>';
    }
  }

  playPatternBtn.addEventListener('click', async () => {
    const pat = patternSelect.value;
    if (!pat) return;
    await fetch('/api/play_pattern', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: pat, loops: 1 })
    });
  });

  // --- Individual RGB Ring Studio ---
  const ringSlots = document.querySelectorAll('.ring-slot');
  ringSlots.forEach(slot => {
    slot.addEventListener('click', () => {
      ringSlots.forEach(s => s.classList.remove('active-slot'));
      slot.classList.add('active-slot');
      selectedSlot = slot.getAttribute('data-slot');
      selectedLedBadge.textContent = selectedSlot === 'all' ? 'Выбран: Все' : `Выбран: Диод ${selectedSlot}`;
    });
  });

  async function applyColor(hex) {
    const rgb = hexToRgb(hex);

    if (selectedSlot === 'all') {
      // Apply to all slots
      for (let i = 1; i <= 6; i++) {
        const el = document.getElementById(`rled-${i}`);
        if (el) {
          el.style.backgroundColor = hex;
          el.style.boxShadow = hex === '#000000' ? 'none' : `0 0 10px ${hex}`;
        }
      }
      const leds = [];
      for (let i = 0; i < 6; i++) leds.push(rgb);
      await fetch('/api/ring/all_leds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ leds })
      });
    } else {
      // Apply to specific LED
      const ledIdx = parseInt(selectedSlot);
      const el = document.getElementById(`rled-${ledIdx}`);
      if (el) {
        el.style.backgroundColor = hex;
        el.style.boxShadow = hex === '#000000' ? 'none' : `0 0 10px ${hex}`;
      }
      await fetch('/api/ring/led', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ led: ledIdx, r: rgb.r, g: rgb.g, b: rgb.b })
      });
    }
  }

  nativeColorPicker.addEventListener('input', (e) => {
    applyColor(e.target.value);
  });

  document.querySelectorAll('.swatch').forEach(sw => {
    sw.addEventListener('click', () => {
      const hex = sw.getAttribute('data-hex');
      nativeColorPicker.value = hex === '#000000' ? '#000000' : hex;
      applyColor(hex);
    });
  });

  // --- Gradient Buttons ---
  document.querySelectorAll('.grad-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const gname = btn.getAttribute('data-grad');
      const res = await fetch('/api/ring/gradient', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: gname })
      });
      const data = await res.json();
      if (data.ring_leds) {
        data.ring_leds.forEach((c, idx) => {
          const el = document.getElementById(`rled-${idx + 1}`);
          if (el) {
            const hex = rgbToHex(c.r, c.g, c.b);
            el.style.backgroundColor = hex;
            el.style.boxShadow = `0 0 10px ${hex}`;
          }
        });
      }
    });
  });

  // --- Ring Dynamic Animations ---
  document.getElementById('spinRingBtn').addEventListener('click', async () => {
    await fetch('/api/ring/animate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'spin', speed: 0.12 })
    });
  });

  document.getElementById('pulseRingBtn').addEventListener('click', async () => {
    await fetch('/api/ring/animate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'pulse', speed: 0.08 })
    });
  });

  document.getElementById('cometRingBtn').addEventListener('click', async () => {
    await fetch('/api/ring/animate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'comet', speed: 0.10 })
    });
  });

  document.getElementById('stopRingBtn').addEventListener('click', async () => {
    await fetch('/api/ring/stop', { method: 'POST' });
  });

  // --- Frame Sequencer ---
  document.getElementById('captureFrameBtn').addEventListener('click', () => {
    const active = [];
    document.querySelectorAll('.segment.lit').forEach(el => {
      active.push(el.getAttribute('data-seg'));
    });
    customFrames.push(active);
    renderFrames();
  });

  document.getElementById('clearFramesBtn').addEventListener('click', () => {
    customFrames = [];
    renderFrames();
  });

  function renderFrames() {
    if (customFrames.length === 0) {
      framesStrip.innerHTML = '<div class="empty-frames-hint">Нарисуйте кадр на экране выше и нажмите «+ Сохранить текущий кадр»</div>';
      return;
    }
    framesStrip.innerHTML = '';
    customFrames.forEach((frame, idx) => {
      const item = document.createElement('div');
      item.className = 'frame-item';
      item.innerHTML = `Кадр ${idx + 1} (${frame.length})<span class="remove-frame" data-idx="${idx}">✕</span>`;
      item.addEventListener('click', (e) => {
        if (e.target.classList.contains('remove-frame')) return;
        document.querySelectorAll('.segment').forEach(el => {
          const s = el.getAttribute('data-seg');
          el.classList.toggle('lit', frame.includes(s));
        });
      });
      framesStrip.appendChild(item);
    });

    document.querySelectorAll('.remove-frame').forEach(rf => {
      rf.addEventListener('click', (e) => {
        e.stopPropagation();
        const i = parseInt(rf.getAttribute('data-idx'));
        customFrames.splice(i, 1);
        renderFrames();
      });
    });
  }

  document.getElementById('playFramesBtn').addEventListener('click', async () => {
    if (customFrames.length === 0) return;
    for (let frame of customFrames) {
      document.querySelectorAll('.segment').forEach(el => {
        const s = el.getAttribute('data-seg');
        el.classList.toggle('lit', frame.includes(s));
      });
      await fetch('/api/clear', { method: 'POST' });
      for (let s of frame) {
        await fetch('/api/segment', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ segment: s, value: currentBrightness })
        });
      }
      await new Promise(r => setTimeout(r, 250));
    }
  });

  // Init
  syncStatus();
  loadPatterns();
  setInterval(syncStatus, 3000);
});
