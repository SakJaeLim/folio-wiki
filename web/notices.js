"use strict";
let noticeInput = "", noticeData = null, noticeList = [], noticeBusy = false, noticeError = "";
async function refreshNotices() {
  try {
    noticeList = await api("/api/notices");
    if (view === "notices" && !desk.querySelector("#notice-url:focus")) renderNotices();
  } catch (err) { toast(err.message); }
}
async function openNotice(id) {
  noticeData = await api("/api/notice?id=" + encodeURIComponent(id));
  noticeInput = noticeData.url;
  noticeError = "";
  if (view === "notices") renderNotices();
}
async function noticeAction(fn) {
  if (noticeBusy) return;
  noticeBusy = true;
  noticeError = "";
  renderNotices();
  try { await fn(); }
  catch (err) { noticeError = err.message; }
  finally { noticeBusy = false; if (view === "notices") renderNotices(); }
}
async function importNotice(form) {
  const url = new FormData(form).get("url");
  await noticeAction(async () => {
    noticeData = await api("/api/notice/import", {url});
    noticeInput = noticeData.url;
    noticeList = await api("/api/notices");
  });
}
function originalLink(f, location) {
  if (!f?.raw_sha256) return "";
  const page = /^PDF (\d+)쪽$/.exec(location || "");
  const params = new URLSearchParams({id:noticeData.id, sha:f.raw_sha256});
  return '<a target="_blank" rel="noopener" href="/api/notice/original?' + esc(params) +
    (page ? "#page=" + page[1] : "") + '">' + esc(location || "원본 열기") + '</a>';
}
function noticeTopic(t, i, root) {
  const d = noticeData, terms = d.rule_terms[t.name] || [];
  const status = {open:"확인 대기", adopted:"확인 완료", review_again:"재검토 필요"};
  const left = '<section class="quote"><small>공고 본문　' + originalLink(root,d.locations[t.name]) +
    '</small><h3>' + esc(t.name) + '</h3><p>' + esc(t.quote || "현재 본문에서 찾을 수 없음") + '</p></section>';
  const right = t.matches.map(m => {
    const f = d.files.find(x => x.path === m.path);
    return '<section class="quote"><small>' + esc(f?.role || "첨부") + '　' + originalLink(f,m.section) +
      '</small><p>' + esc(m.quote) + '</p><small>' + esc(f?.name) + '</small></section>';
  }).join("");
  const diff = t.comparison?.exceptions;
  const previous = diff?.removed?.map(m => '<p>' + esc(m.quote) + '</p>').join("") || "";
  return '<article class="panel"><div class="cardhead"><h2>' + esc(t.name) + '</h2><span class="badge">' +
    esc(status[t.status] || t.status) + '</span></div><div class="compare">' + left + '<div>' +
    (right || '<p>현재 연결된 첨부 문구가 없습니다.</p>') + '</div></div>' +
    (previous ? '<details><summary>이전에 확인한 첨부 문구</summary>' + previous + '</details>' : "") +
    '<div class="notice-actions"><small>' + (terms.length ? '양쪽에 있는 표현　' + esc(terms.join(", ")) : "") +
    '</small>' + (t.status === "adopted" ? '<small>확인 기록　' + esc(t.last_confirmed) + '</small>' :
      (t.matches.length || t.status === "review_again" ? '<button data-notice-confirm="' + i + '"' + (noticeBusy ? " disabled" : "") + '>' + (t.matches.length ? "이 연결 확인" : "연결 해제 확인") + '</button>' : "")) +
    '</div></article>';
}
function noticeDecisions(entries, tabName) {
  const shown = tabName === "wiki" ? entries.filter(d => d.latest && d.status === "adopted" && d.selection !== "withdraw") : entries;
  if (!shown.length) return "";
  return '<section class="panel"><h2>공고에서 확인한 기준</h2>' +
    shown.map(d => '<div class="decision"><strong>' + esc(d.topic) + '</strong><p>' +
      esc(d.selection === "withdraw" ? "연결 해제" : "연결 확인") + '　' + esc(d.created) +
      '</p><button class="link" data-notice-open="' + esc(d.notice) + '">' + esc(d.title) +
      '</button></div>').join("") + '</section>';
}
function renderNotices() {
  const d = noticeData;
  let html = '<div class="intro"><h1>공고 가져오기</h1><p>기업마당 공고 주소를 넣으면 본문 기준과 첨부의 예외 문구를 함께 볼 수 있습니다.</p></div>' +
    '<form class="panel notice-form"><label for="notice-url">공식 공고 URL</label><div><input id="notice-url" type="url" name="url" required maxlength="2048" placeholder="https://www.bizinfo.go.kr/…" value="' +
    esc(noticeInput) + '"><button' + (noticeBusy ? " disabled" : "") + '>' + (noticeBusy ? "처리 중…" : "가져오기") + '</button></div></form>';
  if (noticeError) html += '<p class="notice" role="alert">' + esc(noticeError) + '</p>';
  if (noticeList.length) html += '<details class="notice-past"><summary>가져온 공고 ' + noticeList.length + '건</summary>' +
    noticeList.map(x => '<button class="link" data-notice-open="' + esc(x.id) + '">' + esc(x.title) + '</button>').join("") + '</details>';
  if (d) {
    const root = d.files.find(f => f.role === "본문");
    html += '<section class="panel"><h2>' + esc(d.title) + '</h2><p><a target="_blank" rel="noopener" href="' +
      esc(d.url) + '">기업마당 공고 보기</a></p><details><summary>공식 파일 목록 ' + d.files.length + '개</summary>' +
      d.files.map(f => '<div class="listitem"><strong>' + esc(f.name) + '</strong><br><small>' + esc(f.role + "　" + f.status) +
        '　' + originalLink(f) + '</small></div>').join("") + '</details></section>' +
      '<h2>연결 후보 ' + d.topics.length + '건</h2>' +
      (d.topics.map((t,i) => noticeTopic(t,i,root)).join("") ||
       '<p>지원하는 형식과 표현에서 연결 후보를 찾지 못했습니다. 공식 파일 목록을 확인해 주세요.</p>');
  }
  desk.innerHTML = html;
}
async function noticeClick(e) {
  const prev = e.target.closest("[data-notice-open]");
  if (prev) return noticeAction(() => openNotice(prev.dataset.noticeOpen));
  const btn = e.target.closest("[data-notice-confirm]");
  if (!btn) return;
  const d = noticeData, t = d.topics[Number(btn.dataset.noticeConfirm)];
  await noticeAction(async () => {
    noticeData = await api("/api/notice/confirm", {id:d.id, revision:d.revision,
      topic:t.name, generation:t.generation});
    toast("확인한 원문과 첨부 근거를 기록했습니다.");
  });
}
