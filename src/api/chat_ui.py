# -*- coding: utf-8 -*-
"""팀 실험용 웹 UI — 브라우저에서 질의하고 근거까지 같이 본다.

평가용 `/answer` 와 같은 파이프라인을 쓰되, 화면과 접근 통제만 따로 둔다.
🔴 공개 URL 이므로 CHAT_TOKEN 없이는 열지 않는다. 토큰이 없으면 /chat 자체가 404 다.

화면 (2026-09-06 개편 — 표현만 바뀌었고 호출·응답 필드는 그대로다):
  · 채팅형 배치 — 대화는 위에서 아래로 쌓이고 입력창은 하단 고정.
  · 색은 CI 규정을 따른다: 오렌지(#FF6600)는 CTA·강조에만, 바탕은 무채색.
    말풍선 배경만 틴트(#FFF4EC), 나머지 면은 흰색/회색 — 오래 봐도 눈이 편하도록.
  · 검토 패널은 말풍선 **아래** 흰 카드로 뺀다: 실행 SQL → think_trace(기본 펼침)
    → retrieved_context → 근거문서(기본 접힘). 순서·필드는 개편 전과 같다.
  · 다크모드는 잡지 않는다 — CI 팔레트가 라이트 기준이라 색이 규정대로 나오게 고정한다.
"""

from __future__ import annotations

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>금융상품 Agent — 실험</title>
<style>
  /* ── CI 팔레트 ────────────────────────────────────────────
     오렌지는 CTA·강조 전용. 면적을 차지하는 색은 전부 무채색이다. */
  :root {
    color-scheme: light;
    --primary:#ff6600;      /* 로고 마크, 전송 버튼, 강조 */
    --primary-dark:#e55a00; /* 호버·눌림 */
    --tint:#fff4ec;         /* 챗봇 말풍선, 추천질문 칩 */
    --ink:#1a1a1a;          /* 제목·본문 */
    --sub:#666;             /* 부가설명·타임스탬프 */
    --line:#e5e5e5;         /* 구분선·카드 테두리 */
    --bg:#f7f7f8;           /* 페이지 배경 */
    --up:#e8322d;           /* 수익률 + */
    --down:#1b64da;         /* 수익률 − */
    --card:#fff;
  }
  * { box-sizing:border-box }
  html, body { height:100% }
  body {
    margin:0; background:var(--bg); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Pretendard Variable",Pretendard,
                "Apple SD Gothic Neo","Segoe UI","Malgun Gothic",Roboto,"Noto Sans KR",sans-serif;
    font-size:15px; line-height:1.7; letter-spacing:-.2px;
    -webkit-font-smoothing:antialiased;
  }
  .app { display:flex; flex-direction:column; height:100dvh }

  /* ── 헤더 — 흰 바탕에 얇은 선 하나. 브랜드색은 마크에만 ── */
  header {
    flex:0 0 auto; background:var(--card); border-bottom:1px solid var(--line);
    padding:0 20px; height:58px; display:flex; align-items:center; gap:10px;
  }
  .mark {
    width:26px; height:26px; border-radius:7px; flex:0 0 auto;
    background:var(--primary); display:grid; place-items:center;
  }
  .mark i { width:9px; height:9px; border-radius:50%; background:#fff; display:block }
  .brand { font-size:15.5px; font-weight:700; letter-spacing:-.4px }
  .asof {
    margin-left:auto; flex:0 0 auto; color:var(--sub); font-size:12.5px;
    border:1px solid var(--line); border-radius:999px; padding:3px 11px; white-space:nowrap;
  }
  /* 팀명 — 기준일 옆 구석. 선 하나로만 끊고 색은 보조 텍스트다 */
  .team {
    flex:0 0 auto; color:var(--sub); font-size:12.5px; white-space:nowrap;
    padding-left:11px; margin-left:11px; border-left:1px solid var(--line);
  }
  .team b { color:var(--ink); font-weight:600 }

  /* ── 대화 영역 ──────────────────────────────────────────── */
  .log { flex:1 1 auto; overflow-y:auto; overscroll-behavior:contain; padding:24px 20px 12px }
  .inner { max-width:820px; margin:0 auto; display:flex; flex-direction:column; gap:22px }

  /* 첫 화면 */
  .intro { padding:52px 0 12px; text-align:center }
  .intro .ic {
    width:46px; height:46px; border-radius:14px; background:var(--tint);
    display:grid; place-items:center; margin:0 auto 16px;
  }
  .intro .ic span { width:14px; height:14px; border-radius:50%; background:var(--primary) }
  .intro h1 { margin:0 0 8px; font-size:21px; font-weight:700; letter-spacing:-.5px }
  .intro p { margin:0; color:var(--sub); font-size:14.5px; line-height:1.6 }
  .chips { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; margin-top:22px }
  .chip {
    border:0; background:var(--tint); color:#8a4a12;
    border-radius:999px; padding:9px 15px; font-size:14px; font-family:inherit;
    cursor:pointer; letter-spacing:-.2px;
  }
  .chip:hover { background:#ffe9d9 }

  /* 말풍선 */
  .turn { display:flex; flex-direction:column; gap:14px }
  .row { display:flex; gap:10px; align-items:flex-start }
  .row.me { justify-content:flex-end }
  .avatar {
    width:30px; height:30px; border-radius:50%; flex:0 0 auto; margin-top:2px;
    background:var(--tint); display:grid; place-items:center;
  }
  .avatar i { width:9px; height:9px; border-radius:50%; background:var(--primary); display:block }
  .col { flex:1 1 auto; min-width:0 }

  .bubble { padding:13px 16px; word-break:break-word; white-space:pre-wrap }
  .bubble.me {
    max-width:min(76%,560px); background:var(--primary); color:#fff;
    border-radius:18px 18px 6px 18px;
  }
  .bubble.bot { background:var(--tint); color:var(--ink); border-radius:6px 18px 18px 18px }
  .bubble.bot.err { background:#fff1f1; color:#c0322d }
  .up { color:var(--up); font-weight:600 }
  .down { color:var(--down); font-weight:600 }
  .stamp { color:var(--sub); font-size:11.5px; margin:6px 0 0 4px }

  /* 응답 대기 */
  .dots { display:inline-flex; gap:5px; align-items:center; height:22px }
  .dots i { width:6px; height:6px; border-radius:50%; background:#c9a48b; animation:bl 1.2s infinite ease-in-out }
  .dots i:nth-child(2) { animation-delay:.18s }
  .dots i:nth-child(3) { animation-delay:.36s }
  @keyframes bl { 0%,80%,100% { opacity:.3 } 40% { opacity:1 } }

  /* ── 검토 패널 — 말풍선 아래 흰 카드 ─────────────────────── */
  .panels { margin:10px 0 0; border:1px solid var(--line); border-radius:14px; background:var(--card); overflow:hidden }
  details + details { border-top:1px solid var(--line) }
  summary {
    cursor:pointer; list-style:none; padding:11px 15px;
    font-size:13px; color:var(--ink); display:flex; align-items:center; gap:8px;
  }
  summary::-webkit-details-marker { display:none }
  summary::after {
    content:""; margin-left:auto; width:7px; height:7px; flex:0 0 auto;
    border-right:1.6px solid #b3b3b3; border-bottom:1.6px solid #b3b3b3;
    transform:rotate(45deg) translate(-2px,-2px); transition:transform .15s;
  }
  details[open] summary::after { transform:rotate(-135deg) translate(-2px,-2px) }
  summary:hover { background:#fafafa }
  summary b { font-weight:600 }
  summary .hint { color:var(--sub); font-size:12px; font-weight:400 }
  .wrap { position:relative; padding:0 15px 14px }
  pre {
    margin:0; max-height:300px; overflow:auto;
    background:var(--bg); color:#333; border:1px solid var(--line);
    padding:12px 13px; border-radius:10px;
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"D2Coding",monospace;
    font-size:12.5px; line-height:1.65; letter-spacing:0;
    white-space:pre-wrap; word-break:break-word;
  }
  .sqlwrap pre { border-left:3px solid var(--primary) }
  .copy {
    position:absolute; top:-30px; right:15px;
    border:1px solid var(--line); background:var(--card); color:var(--sub);
    border-radius:7px; padding:3px 9px; font-size:11.5px; font-family:inherit; cursor:pointer;
  }
  .copy:hover { color:var(--ink); border-color:#d5d5d5 }

  /* ── 입력창 ────────────────────────────────────────────── */
  .composer {
    flex:0 0 auto; background:var(--card); border-top:1px solid var(--line);
    padding:14px 20px calc(14px + env(safe-area-inset-bottom));
  }
  .cbox { max-width:820px; margin:0 auto; display:flex; gap:10px; align-items:flex-end }
  textarea {
    flex:1; resize:none; min-height:48px; max-height:150px;
    padding:13px 16px; border:1px solid var(--line); border-radius:14px;
    background:var(--card); color:var(--ink);
    font-family:inherit; font-size:15px; line-height:1.5; letter-spacing:-.2px;
  }
  textarea::placeholder { color:#a5a5a5 }
  textarea:focus { outline:none; border-color:var(--primary); box-shadow:0 0 0 3px rgba(255,102,0,.12) }
  .send {
    flex:0 0 auto; height:48px; padding:0 22px; border:0; border-radius:14px;
    background:var(--primary); color:#fff; font-family:inherit; font-size:15px; font-weight:600;
    letter-spacing:-.2px; cursor:pointer; transition:background .12s;
  }
  .send:hover:not(:disabled) { background:var(--primary-dark) }
  .send:disabled { background:#ededee; color:#b0b0b0; cursor:default }
  .tip { max-width:820px; margin:8px auto 0; color:var(--sub); font-size:11.5px }

  @media (max-width:560px) {
    /* 헤더 오른쪽에 기준일 + 팀명이 같이 서므로 좁은 화면에서는 눈금을 줄인다 */
    header { padding:0 14px; gap:8px }
    .brand { font-size:14.5px }
    .asof, .team { font-size:11.5px }
    .asof { padding:2px 8px }
    .team { padding-left:8px; margin-left:8px }
    .log { padding:18px 14px 10px }
    .composer { padding:12px 14px calc(12px + env(safe-area-inset-bottom)) }
    .bubble.me { max-width:86% }
    .tip { display:none }
  }
</style>

<div class="app">
  <header>
    <div class="mark"><i></i></div>
    <div class="brand">금융상품 Agent</div>
    <div class="asof">데이터 기준일 2026-08-24</div>
    <div class="team">팀 <b>트리플에이치</b></div>
  </header>

  <div class="log" id="log">
    <div class="inner" id="inner">
      <div class="intro" id="intro">
        <div class="ic"><span></span></div>
        <h1>무엇을 찾아드릴까요?</h1>
        <p>국내·해외 ETF, 채권, 공모펀드를 조건으로 물어보세요.<br>답변 아래에서 실행된 SQL 과 판단 과정을 함께 확인할 수 있습니다.</p>
        <div class="chips" id="chips">
          <button class="chip" type="button">미래에셋자산운용이 운용하는 국내 ETF 5개만 알려줘</button>
          <button class="chip" type="button">신용등급 AA 이상인 회사채 알려줘</button>
          <button class="chip" type="button">미국 나스닥100 을 추종하는 ETF 알려줘</button>
        </div>
      </div>
    </div>
  </div>

  <form class="composer" id="f">
    <div class="cbox">
      <textarea id="q" rows="1" placeholder="궁금한 상품 조건을 입력해 주세요" autofocus></textarea>
      <button class="send" id="b" type="submit" disabled>전송</button>
    </div>
    <div class="tip">Enter 전송 · Shift+Enter 줄바꿈 · 팀 실험용 화면입니다</div>
  </form>
</div>

<script>
const f=document.getElementById('f'), qi=document.getElementById('q'), b=document.getElementById('b');
const logEl=document.getElementById('log'), inner=document.getElementById('inner');
const intro=document.getElementById('intro'), chips=document.getElementById('chips');
const tok=new URLSearchParams(location.search).get('t')||'';
const esc=s=>(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const bottom=()=>{ logEl.scrollTop=logEl.scrollHeight; };

// 부호 붙은 등락률만 국내 관례색으로 — +는 빨강, −는 파랑. (표시 전용, 원문은 그대로다)
const rate=s=>s.replace(/([+＋])(\\d[\\d,]*(?:\\.\\d+)?%)/g,'<span class="up">$1$2</span>')
               .replace(/([-−－])(\\d[\\d,]*(?:\\.\\d+)?%)/g,'<span class="down">$1$2</span>');

// 입력창 높이를 내용에 맞춘다 + 빈 입력이면 전송 버튼을 잠근다
const grow=()=>{
  qi.style.height='auto'; qi.style.height=Math.min(qi.scrollHeight,150)+'px';
  b.disabled = qi.value.trim()==='';
};
qi.addEventListener('input',grow);
qi.addEventListener('keydown',e=>{
  if(e.key==='Enter' && !e.shiftKey && !e.isComposing){ e.preventDefault(); f.requestSubmit(); }
});

// 추천질문 칩 — 입력창을 채워 주기만 한다 (바로 보내지 않는다)
if(chips) chips.addEventListener('click',e=>{
  const c=e.target.closest('.chip'); if(!c) return;
  qi.value=c.textContent.trim(); grow(); qi.focus();
});

// 검토 패널 — 순서·기본 펼침 여부는 개편 전과 같다
const panel=(title,hint,body,open,cls)=>body
  ? `<details${open?' open':''}><summary><b>${title}</b>${hint?`<span class="hint">${hint}</span>`:''}</summary>`
    +`<div class="wrap ${cls||''}"><button class="copy" type="button">복사</button><pre>${esc(body)}</pre></div></details>`
  : '';

f.onsubmit=async e=>{
  e.preventDefault();
  const q=qi.value.trim(); if(!q) return;
  qi.value=''; grow();
  if(intro && intro.isConnected) intro.remove();

  const el=document.createElement('div'); el.className='turn';
  el.innerHTML=`<div class="row me"><div class="bubble me">${esc(q)}</div></div>`
    +`<div class="row"><div class="avatar"><i></i></div><div class="col">`
    +`<div class="bubble bot"><span class="dots"><i></i><i></i><i></i></span></div></div></div>`;
  inner.appendChild(el); bottom();
  const col=el.querySelector('.col');

  const t0=performance.now();
  try{
    const r=await fetch(`/chat/ask?question=${encodeURIComponent(q)}&t=${encodeURIComponent(tok)}`);
    const j=await r.json();
    const dt=((performance.now()-t0)/1000).toFixed(1);
    col.innerHTML=
       `<div class="bubble bot">${rate(esc(j.answer))}</div>`
      +`<div class="stamp">${dt}초</div>`
      +`<div class="panels">`
      + panel('실행 SQL','조건식이 의도대로인지 보는 곳',j.sql,true,'sqlwrap')
      + panel('think_trace','',j.think_trace,true)
      + panel('retrieved_context','',j.retrieved_context,false)
      + panel('근거문서', j.grounding ? `프롬프트에 실린 KG·규칙 원문 ${j.grounding.length.toLocaleString()}자` : '', j.grounding, false)
      +`</div>`;
  }catch(err){
    col.innerHTML=`<div class="bubble bot err">요청 실패: ${esc(String(err))}</div>`;
  }
  bottom(); qi.focus();
};

// pre 내용 복사
inner.addEventListener('click',e=>{
  const btn=e.target.closest('.copy'); if(!btn) return;
  const pre=btn.parentElement.querySelector('pre'); if(!pre) return;
  const done=t=>{ btn.textContent=t; setTimeout(()=>{ btn.textContent='복사'; },1200); };
  navigator.clipboard.writeText(pre.textContent).then(()=>done('복사됨')).catch(()=>done('실패'));
});
</script>
"""
