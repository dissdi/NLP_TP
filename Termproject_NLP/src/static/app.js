/* ──────────────────────────────────────────────────────────────────
   충남대 RAG 챗봇 — client logic
   - 사이드바: 세션 목록 (새 채팅으로 누적, 클릭 시 전환, X로 삭제)
   - localStorage persist (한 브라우저 내 영구)
   - POST /api/chat → 답변 / 출처 / 메타 칩
   - Enter 전송 · Shift+Enter 줄바꿈 · textarea 자동 확장
   ────────────────────────────────────────────────────────────────── */

const md = window.markdownit({ html: false, linkify: true, breaks: true });

const $messages    = document.getElementById('messages');
const $input       = document.getElementById('user-input');
const $sendBtn     = document.getElementById('send-btn');
const $newChat     = document.getElementById('new-chat-btn');
const $statusDot   = document.getElementById('status-dot');
const $statusTxt   = document.getElementById('status-text');
const $sessionList = document.getElementById('session-list');

let isSending = false;

const WELCOME_HTML = `
  <div class="welcome">
    <p>안녕하세요! <strong>충남대학교 학내 정보 RAG 챗봇</strong>입니다. 🎓</p>
    <p>다음과 같은 질문에 잘 답할 수 있어요:</p>
    <ul>
      <li>📜 <strong>졸업요건</strong> — 졸업학점, 전공·교양 이수요건</li>
      <li>📢 <strong>학교 공지사항</strong> — 백마광장·학사공지 최근 게시물</li>
      <li>📅 <strong>학사일정</strong> — 수강신청·정정·등록금·방학·개강·성적발표 일정</li>
      <li>🍽 <strong>학생식당 메뉴</strong> — 오늘 점심·저녁, 5개 식당</li>
      <li>🚌 <strong>셔틀버스 시간표</strong> — 교내순환·캠퍼스 순환 노선</li>
    </ul>
    <p style="color: var(--text-dim); font-size: 12.5px; margin-top: 10px;">
      ※ 시험 기간, 기숙사 식당 실시간 메뉴, 셔틀 운휴일 등은 공식 자료가 부족해 답하기 어려울 수 있어요.<br>
      검색된 출처만 사용해 답변하며, 모르면 거절합니다.
    </p>
  </div>
`;

// ── State / persist ────────────────────────────────────────────────
const STORE_KEY = 'cnu_rag_sessions_v1';
const state = {
  sessions: [],
  activeId: null,
};

function saveState() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); }
  catch (e) { console.warn('localStorage save fail', e); }
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && Array.isArray(parsed.sessions)) {
        state.sessions = parsed.sessions;
        state.activeId = parsed.activeId || null;
      }
    }
  } catch (e) { console.warn('localStorage load fail', e); }
  if (!state.sessions.length || !activeSession()) {
    createSession(false);
  }
}

function activeSession() {
  return state.sessions.find(s => s.id === state.activeId) || null;
}

function createSession(rerender) {
  const id = 's_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
  const s = { id: id, title: '새 채팅', messages: [], updatedAt: Date.now() };
  state.sessions.unshift(s);
  state.activeId = id;
  saveState();
  if (rerender) {
    renderSessionList();
    renderMessages();
    $input.value = '';
    autoresize();
    $input.focus();
  }
}

function selectSession(id) {
  if (id === state.activeId) return;
  state.activeId = id;
  saveState();
  renderSessionList();
  renderMessages();
  $input.focus();
}

function deleteSession(id) {
  const i = state.sessions.findIndex(s => s.id === id);
  if (i === -1) return;
  state.sessions.splice(i, 1);
  if (state.activeId === id) {
    state.activeId = state.sessions[0] ? state.sessions[0].id : null;
  }
  if (!state.sessions.length) {
    createSession(false);
  }
  saveState();
  renderSessionList();
  renderMessages();
}

// ── utilities ──────────────────────────────────────────────────────
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function scrollToBottom() {
  $messages.scrollTop = $messages.scrollHeight;
}

function autoresize() {
  $input.style.height = 'auto';
  $input.style.height = Math.min($input.scrollHeight, 200) + 'px';
}

// ── sidebar render ─────────────────────────────────────────────────
function renderSessionList() {
  $sessionList.innerHTML = '';
  if (!state.sessions.length) {
    const empty = el('button', 'session disabled', '(대화 없음)');
    empty.disabled = true;
    $sessionList.appendChild(empty);
    return;
  }
  state.sessions.forEach(function (s) {
    const btn = el('button', 'session' + (s.id === state.activeId ? ' active' : ''));
    btn.type = 'button';
    btn.dataset.id = s.id;
    btn.innerHTML =
      '<span class="label">' + escapeHtml(s.title || '새 채팅') + '</span>' +
      '<span class="del" title="삭제" data-del="' + s.id + '">✕</span>';
    btn.addEventListener('click', function (e) {
      const tgt = e.target;
      if (tgt.dataset && tgt.dataset.del) {
        e.stopPropagation();
        deleteSession(tgt.dataset.del);
        return;
      }
      selectSession(s.id);
    });
    $sessionList.appendChild(btn);
  });
}

// ── message render ────────────────────────────────────────────────
function appendUserBubble(text) {
  const row = el('div', 'msg user');
  const bubble = el('div', 'bubble');
  bubble.innerHTML = md.render(text);
  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
}

function appendWelcomeBubble() {
  const row = el('div', 'msg assistant');
  const bubble = el('div', 'bubble');
  bubble.innerHTML = WELCOME_HTML;
  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
}

function appendTypingBubble() {
  const row = el('div', 'msg assistant typing-row');
  const bubble = el('div', 'bubble');
  bubble.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
  return row;
}

function appendAssistantAnswer(data) {
  const row = el('div', 'msg assistant');
  const bubble = el('div', 'bubble');

  const body = el('div');
  body.innerHTML = md.render(data.answer || '');
  bubble.appendChild(body);

  const meta = el('div', 'meta');
  if (data.fallback) {
    meta.appendChild(el('span', 'chip fb', '🛑 정보 부족'));
  } else {
    meta.appendChild(el('span', 'chip ok', '✅ 답변'));
  }
  if (data.category) {
    meta.appendChild(el('span', 'chip',
      '📂 ' + escapeHtml(data.category) + ' (' + (data.confidence || 0).toFixed(2) + ')'));
  }
  if (data.tool) {
    meta.appendChild(el('span', 'chip tool', '🛠 ' + escapeHtml(data.tool)));
  }
  if (typeof data.elapsed === 'number') {
    meta.appendChild(el('span', 'chip', '⏱ ' + data.elapsed.toFixed(1) + 's'));
  }
  bubble.appendChild(meta);

  const srcs = data.sources || [];
  if (srcs.length) {
    const wrap = el('div', 'sources');
    const toggle = el('button', 'sources-toggle');
    toggle.type = 'button';
    toggle.innerHTML = '<span class="caret">▸</span>출처 ' + srcs.length + '건 펼치기';
    const list = el('div', 'sources-list');
    list.innerHTML = srcs.map(function (s, i) {
      const score = (typeof s.rerank_score === 'number')
        ? s.rerank_score.toFixed(2) : '0.00';
      const title = escapeHtml((s.title || '').slice(0, 120));
      const url = s.source_url || '';
      const link = url
        ? '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">열기 ↗</a>'
        : '';
      return '<div class="src-item">' +
        '<span class="score">' + score + '</span>' +
        '<span class="title">' + (i + 1) + '. ' + title + '</span>' +
        link +
        '</div>';
    }).join('');
    toggle.addEventListener('click', function () {
      const open = wrap.classList.toggle('open');
      toggle.querySelector('.caret').textContent = open ? '▾' : '▸';
      toggle.lastChild.textContent = open
        ? '출처 ' + srcs.length + '건 접기'
        : '출처 ' + srcs.length + '건 펼치기';
    });
    wrap.appendChild(toggle);
    wrap.appendChild(list);
    bubble.appendChild(wrap);
  }

  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
}

function appendError(msg) {
  const row = el('div', 'msg assistant');
  const bubble = el('div', 'bubble');
  bubble.innerHTML = '<div style="color: var(--danger)">⚠ ' + escapeHtml(msg) + '</div>';
  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
}

function renderMessages() {
  $messages.innerHTML = '';
  const s = activeSession();
  if (!s || !s.messages.length) {
    appendWelcomeBubble();
    return;
  }
  for (const m of s.messages) {
    if (m.role === 'user') appendUserBubble(m.text);
    else if (m.role === 'assistant') {
      if (m.data) appendAssistantAnswer(m.data);
      else if (m.error) appendError(m.error);
    }
  }
}

// ── send ──────────────────────────────────────────────────────────
async function send() {
  if (isSending) return;
  const text = $input.value.trim();
  if (!text) return;

  let s = activeSession();
  if (!s) { createSession(false); s = activeSession(); }

  isSending = true;
  $sendBtn.disabled = true;
  $input.value = '';
  autoresize();

  s.messages.push({ role: 'user', text: text });
  s.updatedAt = Date.now();
  if (!s.title || s.title === '새 채팅') {
    s.title = text.length > 30 ? text.slice(0, 30) + '…' : text;
    renderSessionList();
  }
  saveState();
  appendUserBubble(text);

  const typing = appendTypingBubble();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    typing.remove();
    if (!res.ok) {
      const msg = 'HTTP ' + res.status;
      s.messages.push({ role: 'assistant', error: msg });
      saveState();
      appendError(msg);
    } else {
      const data = await res.json();
      s.messages.push({ role: 'assistant', data: data });
      s.updatedAt = Date.now();
      saveState();
      appendAssistantAnswer(data);
    }
  } catch (e) {
    typing.remove();
    const msg = '요청 실패: ' + (e.message || e);
    s.messages.push({ role: 'assistant', error: msg });
    saveState();
    appendError(msg);
  } finally {
    isSending = false;
    $sendBtn.disabled = false;
    $input.focus();
  }
}

function onNewChat() {
  const s = activeSession();
  if (s && !s.messages.length) {
    $input.focus();
    return;
  }
  createSession(true);
}

async function pollHealth() {
  try {
    const res = await fetch('/api/health');
    const j = await res.json();
    if (j.ready) {
      $statusDot.className = 'dot ok';
      $statusTxt.textContent = '준비됨';
      return true;
    } else if (j.error) {
      $statusDot.className = 'dot err';
      $statusTxt.textContent = '오류';
      return true;
    }
    $statusDot.className = 'dot loading';
    $statusTxt.textContent = '모델 로딩 중…';
  } catch (e) {
    $statusDot.className = 'dot err';
    $statusTxt.textContent = '연결 끊김';
  }
  return false;
}

$input.addEventListener('input', autoresize);
$input.addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
});
$sendBtn.addEventListener('click', send);
$newChat.addEventListener('click', onNewChat);

loadState();
renderSessionList();
renderMessages();
autoresize();
$input.focus();

(async function healthLoop() {
  const ready = await pollHealth();
  if (!ready) setTimeout(healthLoop, 1500);
})();
