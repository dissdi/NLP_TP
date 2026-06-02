/* ──────────────────────────────────────────────────────────────────
   충남대 RAG 챗봇 — client logic
   - POST /api/chat 호출
   - markdown-it 으로 답변 렌더
   - Enter 전송 / Shift+Enter 줄바꿈 / textarea 자동 확장
   - 출처는 접을 수 있는 토글
   ────────────────────────────────────────────────────────────────── */

const md = window.markdownit({
  html: false,
  linkify: true,
  breaks: true,
});

const $messages   = document.getElementById('messages');
const $input      = document.getElementById('user-input');
const $sendBtn    = document.getElementById('send-btn');
const $newChat    = document.getElementById('new-chat-btn');
const $statusDot  = document.getElementById('status-dot');
const $statusTxt  = document.getElementById('status-text');

let isSending = false;

const WELCOME_HTML = `
  <div class="welcome">
    <p>안녕하세요! <strong>충남대학교 학내 정보 RAG 챗봇</strong>입니다. 🎓</p>
    <p>다음 영역의 질문에 답할 수 있어요:</p>
    <ul>
      <li>📜 <strong>졸업요건</strong> — 졸업학점, 전공·교양 요건</li>
      <li>📢 <strong>학교 공지사항</strong> — 백마광장·학사공지</li>
      <li>📅 <strong>학사일정</strong> — 수강신청·정정·시험·방학</li>
      <li>🍽 <strong>식단</strong> — 학생식당·기숙사 식당 메뉴</li>
      <li>🚌 <strong>통학·셔틀버스</strong> — 시간표·노선·운휴</li>
    </ul>
    <p style="color: var(--text-dim); font-size: 13px;">
      검색된 출처 context만 사용해 답변하며, 모르면 거절합니다.
    </p>
  </div>
`;

// ── utilities ──────────────────────────────────────────────────────
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

function escapeHtml(s) {
  return String(s ?? '')
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

// ── rendering ──────────────────────────────────────────────────────
function renderUserMessage(text) {
  const row = el('div', 'msg user');
  const bubble = el('div', 'bubble');
  bubble.innerHTML = md.render(text);
  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
}

function renderAssistantWelcome() {
  const row = el('div', 'msg assistant');
  const bubble = el('div', 'bubble');
  bubble.innerHTML = WELCOME_HTML;
  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
}

function renderTypingPlaceholder() {
  const row = el('div', 'msg assistant typing-row');
  const bubble = el('div', 'bubble');
  bubble.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
  return row;
}

function renderAssistantAnswer(data) {
  const row = el('div', 'msg assistant');
  const bubble = el('div', 'bubble');

  // body
  const body = el('div');
  body.innerHTML = md.render(data.answer || '');
  bubble.appendChild(body);

  // meta chips
  const meta = el('div', 'meta');
  if (data.fallback) {
    meta.appendChild(el('span', 'chip fb', '🛑 정보 부족'));
  } else {
    meta.appendChild(el('span', 'chip ok', '✅ 답변'));
  }
  if (data.category) {
    meta.appendChild(el('span', 'chip',
      `📂 ${escapeHtml(data.category)} (${(data.confidence || 0).toFixed(2)})`));
  }
  if (data.tool) {
    meta.appendChild(el('span', 'chip tool', `🛠 ${escapeHtml(data.tool)}`));
  }
  if (typeof data.elapsed === 'number') {
    meta.appendChild(el('span', 'chip', `⏱ ${data.elapsed.toFixed(1)}s`));
  }
  bubble.appendChild(meta);

  // sources (collapsible)
  const srcs = data.sources || [];
  if (srcs.length) {
    const wrap = el('div', 'sources');
    const toggle = el('button', 'sources-toggle');
    toggle.type = 'button';
    toggle.innerHTML = `<span class="caret">▸</span>출처 ${srcs.length}건 펼치기`;
    const list = el('div', 'sources-list');
    list.innerHTML = srcs.map((s, i) => {
      const score = (typeof s.rerank_score === 'number')
        ? s.rerank_score.toFixed(2)
        : '0.00';
      const title = escapeHtml((s.title || '').slice(0, 120));
      const url = s.source_url || '';
      const link = url
        ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">열기 ↗</a>`
        : '';
      return `<div class="src-item">
        <span class="score">${score}</span>
        <span class="title">${i + 1}. ${title}</span>
        ${link}
      </div>`;
    }).join('');
    toggle.addEventListener('click', () => {
      const open = wrap.classList.toggle('open');
      toggle.querySelector('.caret').textContent = open ? '▾' : '▸';
      toggle.lastChild.textContent = open
        ? `출처 ${srcs.length}건 접기`
        : `출처 ${srcs.length}건 펼치기`;
    });
    wrap.appendChild(toggle);
    wrap.appendChild(list);
    bubble.appendChild(wrap);
  }

  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
}

function renderError(msg) {
  const row = el('div', 'msg assistant');
  const bubble = el('div', 'bubble');
  bubble.innerHTML = `<div style="color: var(--danger)">⚠ ${escapeHtml(msg)}</div>`;
  row.appendChild(bubble);
  $messages.appendChild(row);
  scrollToBottom();
}

// ── send ──────────────────────────────────────────────────────────
async function send() {
  if (isSending) return;
  const text = $input.value.trim();
  if (!text) return;

  isSending = true;
  $sendBtn.disabled = true;
  $input.value = '';
  autoresize();

  renderUserMessage(text);
  const typing = renderTypingPlaceholder();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    typing.remove();
    if (!res.ok) {
      renderError(`HTTP ${res.status}`);
    } else {
      const data = await res.json();
      renderAssistantAnswer(data);
    }
  } catch (e) {
    typing.remove();
    renderError(`요청 실패: ${e.message || e}`);
  } finally {
    isSending = false;
    $sendBtn.disabled = false;
    $input.focus();
  }
}

async function resetChat() {
  try { await fetch('/api/reset', { method: 'POST' }); } catch {}
  $messages.innerHTML = '';
  renderAssistantWelcome();
  $input.value = '';
  autoresize();
  $input.focus();
}

// ── health polling ────────────────────────────────────────────────
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
  } catch {
    $statusDot.className = 'dot err';
    $statusTxt.textContent = '연결 끊김';
  }
  return false;
}

// ── events ────────────────────────────────────────────────────────
$input.addEventListener('input', autoresize);
$input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
});
$sendBtn.addEventListener('click', send);
$newChat.addEventListener('click', resetChat);

// ── boot ──────────────────────────────────────────────────────────
renderAssistantWelcome();
autoresize();
$input.focus();

(async function healthLoop() {
  const ready = await pollHealth();
  if (!ready) setTimeout(healthLoop, 1500);
})();
