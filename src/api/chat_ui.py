# -*- coding: utf-8 -*-
"""팀 실험용 웹 UI — 브라우저에서 질의하고 근거까지 같이 본다.

평가용 `/answer` 와 같은 파이프라인을 쓰되, 화면과 접근 통제만 따로 둔다.
🔴 공개 URL 이므로 CHAT_TOKEN 없이는 열지 않는다. 토큰이 없으면 /chat 자체가 404 다.
"""

from __future__ import annotations

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>금융상품 Agent — 실험</title>
<style>
  :root { color-scheme: light dark; --bg:#fff; --fg:#1a1a1a; --mut:#666; --line:#e3e3e3; --acc:#0b5fff; }
  @media (prefers-color-scheme: dark) { :root { --bg:#161616; --fg:#eee; --mut:#999; --line:#333; --acc:#6ea8ff; } }
  * { box-sizing:border-box }
  body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.6 -apple-system,"Segoe UI",Roboto,"Noto Sans KR",sans-serif; }
  header { padding:14px 18px; border-bottom:1px solid var(--line); display:flex; gap:12px; align-items:baseline; }
  header b { font-size:15px } header span { color:var(--mut); font-size:13px }
  main { max-width:920px; margin:0 auto; padding:18px }
  form { display:flex; gap:8px; margin-bottom:18px }
  input[type=text] { flex:1; padding:11px 13px; border:1px solid var(--line); border-radius:8px; background:var(--bg); color:var(--fg); font-size:15px }
  button { padding:11px 18px; border:0; border-radius:8px; background:var(--acc); color:#fff; font-size:15px; cursor:pointer }
  button:disabled { opacity:.5; cursor:default }
  .qa { border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:14px }
  .q { font-weight:600; margin-bottom:8px }
  .a { white-space:pre-wrap; margin-bottom:10px }
  details { margin-top:8px } summary { cursor:pointer; color:var(--mut); font-size:13px }
  pre { overflow-x:auto; background:rgba(127,127,127,.09); padding:10px; border-radius:6px; font-size:12.5px; margin:6px 0 0 }
  .meta { color:var(--mut); font-size:12.5px }
  .err { color:#c00 }
</style>
<header><b>금융상품 Agent</b><span>실험용 · 데이터 기준일 2026-08-22 · 답변 → <b>실행 SQL</b> → think_trace → 근거문서 순으로 확인하세요</span></header>
<main>
  <form id="f"><input type="text" id="q" placeholder="예) 미래에셋자산운용이 운용하는 국내 ETF 5개만 알려줘" autofocus><button id="b">질문</button></form>
  <div id="log"></div>
</main>
<script>
const f=document.getElementById('f'), qi=document.getElementById('q'), b=document.getElementById('b'), log=document.getElementById('log');
const tok=new URLSearchParams(location.search).get('t')||'';
const esc=s=>(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
f.onsubmit=async e=>{
  e.preventDefault();
  const q=qi.value.trim(); if(!q) return;
  qi.value=''; b.disabled=true;
  const el=document.createElement('div'); el.className='qa';
  el.innerHTML=`<div class="q">${esc(q)}</div><div class="a meta">조회 중…</div>`;
  log.prepend(el);
  const t0=performance.now();
  try{
    const r=await fetch(`/chat/ask?question=${encodeURIComponent(q)}&t=${encodeURIComponent(tok)}`);
    const j=await r.json();
    const dt=((performance.now()-t0)/1000).toFixed(1);
    el.innerHTML=`<div class="q">${esc(q)}</div><div class="a">${esc(j.answer)}</div>`
      +`<div class="meta">${dt}s</div>`
      +(j.sql?`<details open><summary>실행 SQL — 조건식이 의도대로인지 보는 곳</summary><pre>${esc(j.sql)}</pre></details>`:'')
      +(j.retrieved_context?`<details><summary>retrieved_context</summary><pre>${esc(j.retrieved_context)}</pre></details>`:'')
      +`<details open><summary>think_trace</summary><pre>${esc(j.think_trace)}</pre></details>`
      +(j.grounding?`<details><summary>근거문서 — KG 매핑·yaml 규칙이 실제로 프롬프트에 실린 원문 (${j.grounding.length.toLocaleString()}자)</summary><pre>${esc(j.grounding)}</pre></details>`:'');
  }catch(err){
    el.querySelector('.a').className='a err'; el.querySelector('.a').textContent='요청 실패: '+err;
  }
  b.disabled=false; qi.focus();
};
</script>
"""
