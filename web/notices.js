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
  const download = /\.hwpx?$/i.test(f.name) ? ' download="' + esc(f.name) + '"' : '';
  return '<a target="_blank" rel="noopener"' + download + ' href="/api/notice/original?' + esc(params) +
    (page ? "#page=" + page[1] : "") + '">' + esc(location || "원본 열기") + '</a>';
}
function proofText(quote, attachment) {
  const lines = quote.split("\n");
  const detail = lines.find(s => s.startsWith("[붙임 ") && s.includes(" · HWP 표 "));
  const lead = attachment ? (detail ? detail.replace(/^\[[^\]]+\]\s*-?\s*/, "") : lines[1]) :
    quote.split(/\n(?:[-*※▖]|《)/)[0];
  if (!lead || lead === quote) return '<p>' + esc(quote) + '</p>';
  return '<p>' + esc(lead) + '</p><details><summary>' +
    (attachment ? '표 행과 붙임 원문' : '본문 전체') + '</summary><p>' + esc(quote) + '</p></details>';
}
const stageLabels = {application:"신청할 때", after:"서류평가 통과 후", uncertain:"시점 확인 필요"};
function conditionText(item) {
  const c = item.submission;
  if (!c) return "";
  let html = '<p><strong>제출 시점　' + esc(stageLabels[c.stage] || stageLabels.uncertain) + '</strong></p>';
  const windows = [...new Set(c.timing.flatMap(t => t.window || []))];
  if (windows.length) html += '<p>' + esc(windows.join(", ")) + '</p>';
  for (const a of c.alternatives || []) html += '<p><small>' + esc(a.location) + '</small><br>' + esc(a.quote) + '</p>';
  return html;
}
function noticeTopic(t, i, root) {
  const d = noticeData, terms = d.rule_terms[t.name] || [];
  const proof = (d.proof_topics || []).includes(t.name);
  const status = {open:"확인 대기", adopted:"확인 완료", review_again:"재검토 필요"};
  const left = '<section class="quote"><small>공고 본문　' + originalLink(root,d.locations[t.name]) +
    '</small>' + (proof ? proofText(t.quote, false) : '<h3>' + esc(t.name) + '</h3><p>' + esc(t.quote || "현재 본문에서 찾을 수 없음") + '</p>') + '</section>';
  const right = t.matches.map(m => {
    const f = d.files.find(x => x.path === m.path);
    return '<section class="quote"><small>' + esc(proof ? "제출 서류" : f?.role || "첨부") + '　' + originalLink(f,m.section) +
      '</small>' + (proof ? proofText(m.quote, true) + conditionText(m) : '<p>' + esc(m.quote) + '</p>') + '<small>' + esc(f?.name) + '</small></section>';
  }).join("");
  const diff = t.comparison?.exceptions;
  const previous = diff?.removed?.map(m => '<p>' + esc(m.quote) + '</p>' + conditionText(m)).join("") || "";
  return '<article id="notice-rule-' + i + '" class="panel' + (proof ? ' proof-card' : '') + '"><div class="cardhead"><h2>' + esc(t.name) + '</h2><span class="badge">' +
    esc(status[t.status] || t.status) + '</span></div><div class="compare">' + left + '<div>' +
    (right || '<p>현재 연결된 첨부 문구가 없습니다.</p>') + '</div></div>' +
    (previous ? '<details open><summary>이전에 확인한 첨부 근거</summary>' + previous + '</details>' : "") +
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
function submissionGuide(d, root) {
  const rows = d.submissions || [];
  if (!rows.some(r => r.timing.length)) return "";
  return Object.entries(stageLabels).map(([stage, label]) => {
    const items = rows.filter(r => r.stage === stage);
    const forms = stage === "application" ? (d.application_forms || []) : [];
    if (!items.length && !forms.length) return "";
    const formRows = forms.map(r => '<li><strong>' + esc(r.document) + '</strong>　' +
      esc(r.method) + '　' + originalLink(root,r.location) + '</li>').join("");
    const documents = items.map(r => {
      const idx = d.topics.findIndex(t => t.name === r.topic);
      const file = d.files.find(f => f.path === r.path);
      const ref = idx >= 0 ? '<a href="#notice-rule-' + idx + '">요건 원문 보기</a>' : '개별 요건 미연결';
      const citations = r.timing.map(c => '<p>' + esc(c.quote) + '　' + originalLink(file,c.location) + '</p>').join("");
      const alt = r.alternatives.map(a => '<p>' + esc(a.quote) + '　' + originalLink(file,a.location) + '</p>').join("");
      return '<li><strong>' + esc(r.document) + '</strong><small>' + esc(r.category) + '　' + ref + '</small>' +
        (citations || alt ? '<details><summary>시점과 대체 서류 근거</summary>' + citations + alt + '</details>' : '') + '</li>';
    }).join("");
    const rootTopics = stage === "after" ? new Set(items.filter(r => r.location.startsWith("HWP 제출 안내") && r.topic).map(r => r.topic)) : [];
    const passages = [...rootTopics].map(name => {
      const topic = d.topics.find(t => t.name === name);
      return topic ? '<details><summary>통과 후 제출 안내와 본문에 나온 서류 예시</summary><p>' +
        esc(topic.quote) + '　' + originalLink(root, d.locations[name]) + '</p></details>' : "";
    }).join("");
    return '<section class="panel submission-guide"><h2>' + label + '</h2><ul>' + formRows + documents + '</ul>' + passages + '</section>';
  }).join("");
}
function noticeGroups(d, root) {
  const proof = new Set(d.proof_topics || []);
  const ordered = d.proof_topics || [];
  const cards = (isProof) => (isProof ? ordered : d.topics.map(t => t.name).filter(n => !proof.has(n)))
    .map(name => {
      const index = d.topics.findIndex(t => t.name === name);
      return index >= 0 ? noticeTopic(d.topics[index], index, root) : "";
    }).join("");
  let html = submissionGuide(d, root);
  if (proof.size) {
    html += '<h3>신청 요건별 제출 서류</h3>';
    html += (d.proof_notes || []).map(n => '<details><summary>첨부의 제출 시점과 유의사항</summary><p>' + esc(n.text) +
      '　' + originalLink(d.files.find(f => f.path === n.path),n.location) + '</p></details>').join("");
    html += cards(true);
  }
  const other = cards(false);
  if (other) html += (proof.size ? '<h3>그 밖의 연결</h3>' : "") + other;
  return html || '<p>본문에 대응하는 첨부 문구를 찾지 못했습니다. 공식 파일 목록을 확인해 주세요.</p>';
}
function renderNotices() {
  const d = noticeData;
  let html = '<div class="intro"><h1>공고 가져오기</h1><p>기업마당 공고 주소를 넣으면 신청 요건에 필요한 서류와 첨부의 예외 문구를 확인할 수 있습니다.</p></div>' +
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
      noticeGroups(d, root);
    if (d.proof_unresolved?.length) html += '<details class="panel"><summary>본문 요건을 특정하지 못한 서류 ' +
      d.proof_unresolved.length + '건</summary>' + d.proof_unresolved.map(row => '<p><strong>' + esc(row.category) +
      '</strong>　' + originalLink(d.files.find(f => f.path === row.path), row.location) + '<br>' + esc(row.text) +
      '<br><small>' + esc(row.reason) + '</small></p>').join("") + '</details>';
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
