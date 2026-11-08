"use strict";
const desk = document.querySelector("#desk"),
  dialog = document.querySelector("#reader");
const tabs = {
  review: "지침 검토",
  wiki: "팀 위키",
  sources: "원문 보관함",
  history: "결정 기록",
};
const saved = new Map();
let view = "wiki",
  data = null,
  busy = false;
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const marked = (s) =>
  esc(s).replace(/(\d+(?:[~–-]\d+)?\s*(?:일|시간|자|%))/g, "<mark>$1</mark>");
const badge = (s) =>
  `<span class="badge ${s === "adopted" ? "ok" : ""}">${{ open: "검토 대기", review_again: "재검토 필요", adopted: "결정 완료", held: "판단 보류" }[s]}</span>`;
const key = (t) => `${t.name}\u0000${t.generation}`;
async function api(url, body) {
  const res = await fetch(
    url,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {},
  );
  const value = await res.json();
  if (!res.ok) throw Error(value.error || "요청을 처리할 수 없습니다.");
  return value;
}
let toastTimer;
function toast(txt) {
  const e = document.querySelector("#toast");
  e.textContent = txt;
  e.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (e.hidden = true), 4200);
}
const sourceBtn = (item, label = "원문 보기") =>
  `<button type="button" class="link" data-path="${esc(item.path)}" data-version="${esc(item.version)}" data-line="${item.start || 1}">${esc(label)}</button>`;
function historyRow(d) {
  const selected = d.evidence.find((c) => c.id === d.selection);
  return `<div class="decision"><strong>${esc(d.topic)} · ${selected ? "채택" : d.selection === "hold" ? "보류" : "철회"}</strong><p>${selected ? esc(d.excerpt?.quote ?? selected.quote) : d.selection === "hold" ? "판단을 보류했습니다." : "안내를 철회했습니다."}</p><p class="muted">${esc(d.actor)} · ${esc(d.note)}</p><small>${esc(new Date(d.created).toLocaleString("ko-KR"))}</small><details><summary>결정 당시 원문 ${d.evidence.length}개</summary>${d.evidence.map((x) => `<div>${sourceBtn(x, x.path)} <small>${x.start}–${x.end}행</small></div>`).join("")}</details></div>`;
}
function changes({before, after, reason}) {
  function side(item, title, message) {
    if (!item) return `<section class="quote"><h3>${title}</h3><p>${message}</p></section>`;
    const refs = Object.entries(item.links).map(([name, url]) =>
      `<div><b>${esc(name)}</b><br><code>${esc(url)}</code></div>`).join("");
    return `<section class="quote"><h3>${title}</h3><small>${sourceBtn(item, item.path)} · ${item.start}~${item.end}행</small><p>${marked(item.quote)}</p>${refs}</section>`;
  }
  return `<div class="revision"><div class="compare">
    ${side(before, "채택 당시", "")}
    ${side(after, "현재 원문", reason === "ambiguous" ? "같은 문장이 여러 곳에 있어 위치를 확인해야 합니다." : "현재 원문에서 채택한 문장을 찾을 수 없습니다.")}
  </div>${reason === "alignment" ? "<small>대응하는 문장이 여러 줄로 바뀌었습니다. 현재 원문에서 범위를 확인하세요.</small>" : ""}</div>`;
}
function candidate(x, t, draft, adopted) {
  const active = t.status === "adopted";
  const scope = active ? "" : `<label class="scope">채택 범위<select name="unit-${x.id}" aria-label="${esc(x.path)} 채택 범위">
    <option value="choose">문장을 선택하세요</option>${x.units.map((u,i) => `<option value="${i}" ${(draft["unit-"+x.id] ?? (x.units.length === 1 ? "0" : "choose")) === String(i) ? "selected" : ""}>${u.start}행 · ${esc(u.quote)}</option>`).join("")}<option value="" ${draft["unit-"+x.id] === "" ? "selected" : ""}>이 절 전체</option></select></label>`;
  return `<section class="quote"><small>${active && adopted?.path === x.path ? "채택한 원문" : "원문"} ${x.start}~${x.end}행</small><h3>${sourceBtn(x, x.path)}</h3><p>${marked(x.quote)}</p>
    ${active ? "" : `<label class="pick"><input type="radio" name="selection" value="${x.id}" ${draft.selection === x.id ? "checked" : ""}> 이 원문 채택</label>${scope}`}</section>`;
}
function review(t, idx) {
  const draft = saved.get(key(t)) || {},
    past = data.decisions.filter((d) => d.topic === t.name);
  const adopted = past[0]?.evidence.find(c => c.id === past[0].selection);
  return `<article class="panel" data-index="${idx}"><div class="cardhead"><h2>${esc(t.name)}</h2>${badge(t.status)}</div>
 ${t.comparison ? changes(t.comparison) : ""}
 <form><div class="compare">${t.candidates.map(x => candidate(x, t, draft, adopted)).join("") || "<p>현재 이 항목을 뒷받침하는 원문이 없습니다.</p>"}</div>
 ${t.status !== "adopted" ? `<div class="reviewForm"><div class="fields"><label>담당자<input name="actor" maxlength="80" required value="${esc(draft.actor || "")}" placeholder="이름"></label><label>결정 이유<textarea name="note" maxlength="2000" rows="1" required placeholder="어느 기준을 적용할지 기록하세요">${esc(draft.note || "")}</textarea></label></div><div class="actions"><button class="primary" type="submit">결정 기록</button><label><input type="radio" name="selection" value="hold" ${draft.selection === "hold" ? "checked" : ""}> 판단 보류</label><label><input type="radio" name="selection" value="withdraw" ${draft.selection === "withdraw" ? "checked" : ""}> 안내 철회</label></div></div>` : ""}
 </form>${data.jev && t.candidates.length === 2 && t.status !== "adopted" ? `<details><summary>Jev 검토 의견</summary><small>선택하면 두 원문을 TypeSafe에 보냅니다.</small> <button class="quiet" data-advice="${idx}">공개 원문으로 의견 받기</button><p class="advice" ${draft.advice ? "" : "hidden"}>${esc(draft.advice || "")}</p></details>` : ""}
 ${past.length ? `<details><summary>이 항목의 결정 ${past.length}건</summary>${past.map(historyRow).join("")}</details>` : ""}</article>`;
}
function wikiBody(content, pages) {
  function inline(line) {
    return esc(line)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\[\[([^\]]+)\]\]/g, (_, value) => {
        const [target, label] = value.split("|");
        const index = pages.findIndex(page => esc(page.slug) === target || esc(page.title) === target);
        return index < 0 ? label || target : '<a href="#draft-' + index + '">' + (label || target) + '</a>';
      });
  }
  return String(content || "").split(/\r?\n/).map(line => {
    if (!line.trim()) return "";
    if (/^#{1,6}\s/.test(line)) return "<h4>" + inline(line.replace(/^#{1,6}\s+/, "")) + "</h4>";
    if (/^[-*]\s/.test(line)) return "<p>" + inline(line.replace(/^[-*]\s+/, "• ")) + "</p>";
    return "<p>" + inline(line) + "</p>";
  }).join("");
}
function render() {
  if (!data) return;
  document.querySelector("#space").textContent = data.folder;
  document.querySelector("#crumb").textContent = tabs[view];
  document.title = "Folio Wiki · " + tabs[view];
  document
    .querySelectorAll("nav button")
    .forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  const statuses = {
    ready: "WeKnora 초안 준비됨",
    building: "WeKnora 초안 작성 중",
    pending: "WeKnora 연결 중",
    waiting: "WeKnora 연결 대기",
    empty: "자료 대기",
  };
  document.querySelector("#engine").textContent =
    data.demo ? "로컬 검토 데모" : statuses[data.engine] || data.engine;
  const waiting = data.topics.filter((t) => t.status !== "adopted").length;
  const subtitle = {
    review: `원문 ${Object.keys(data.files).length}개에서 확인한 항목 중 ${waiting}건이 결정을 기다립니다.`,
    wiki: data.demo ? "담당자가 현재 자료에 채택한 안내를 읽습니다." : "담당자가 채택한 안내와 WeKnora가 작성한 초안을 읽습니다.",
    sources: "가져온 문서의 원문과 절별 위치를 확인합니다.",
    history: "누가 어떤 원문을 채택했는지 당시 버전과 함께 확인합니다.",
  }[view];
  let html = `<div class="intro"><h1>${tabs[view]}</h1><p>${subtitle}</p></div>`;
  if (data.sync_error) html += `<p class="notice">${esc(data.sync_error)}</p>`;
  if (view === "review")
    html +=
      data.topics.map(review).join("") ||
      "<p>같은 제목의 절에서 비교할 내용이 발견되지 않았습니다.</p>";
  if (view === "sources")
    html +=
      Object.entries(data.files)
        .map(
          ([path, version]) =>
            `<div class="listitem"><h3>${sourceBtn({ path, version }, path)}</h3><small>원문 버전 ${version.slice(0, 12)}</small></div>`,
        )
        .join("") || "<p>공개 폴더가 비어 있습니다.</p>";
  if (view === "history")
    html +=
      data.decisions.map(historyRow).join("") ||
      "<p>기록한 결정이 아직 없습니다.</p>";
  if (view === "wiki") {
    const adopted = data.topics.filter(topic => topic.status === "adopted")
      .map(topic => data.decisions.find(d => d.topic === topic.name))
      .filter(d => d && d.selection !== "withdraw");
    const order = ["summary","concept","entity","index"];
    const labels = {summary:"요약",concept:"개념",entity:"항목",index:"목차"};
    const pages = [...data.pages].sort((a,b) => order.indexOf(a.page_type)-order.indexOf(b.page_type));
    if(waiting) html += `<button class="quiet" data-review-jump>검토할 지침 ${waiting}건 보기</button>`;
    html += `<section class="panel"><h2>채택한 안내</h2>
      ${adopted.map(historyRow).join("") || '<p class="muted">현재 버전에서 채택한 안내가 없습니다.</p>'}</section>`;
    if (!data.demo) html += `<section class="panel"><div class="cardhead"><h2>WeKnora 초안</h2><small>${esc(statuses[data.engine] || "")}</small></div>
      <details><summary>초안에 사용한 원문 ${Object.keys(data.files).length}개</summary>
      ${Object.entries(data.files).map(([path,version]) => `<div>${sourceBtn({path,version},path)}</div>`).join("")}</details>
      ${data.detail ? `<p class="notice">${esc(data.detail)}</p>` : ""}
      ${pages.map((page,index) => {
        const title=page.page_type==="summary"?"폴더 자료 요약":page.page_type==="index"?"위키 목차":page.title;
        return `<article class="page" id="draft-${index}"><small>${esc(labels[page.page_type] || page.page_type)} · v${esc(page.version)}</small>
          <h3>${esc(title)}</h3><div class="wiki-prose">${wikiBody(page.content,pages)}</div></article>`;
      }).join("")}</section>`;
  }
  desk.innerHTML = html;
}
async function load(force = false) {
  const next = await api("/api/view"),
    changed = JSON.stringify(next) !== JSON.stringify(data);
  if (!data && next.demo) view = "review";
  data = next;
  if (force || changed) render();
}
document.querySelector("nav").onclick = (e) => {
  const b = e.target.closest("[data-view]");
  if (b) {
    view = b.dataset.view;
    render();
  }
};
document.querySelector("#sync").onclick = async () => {
  try {
    await api("/api/sync", {});
    await load(true);
    toast("현재 폴더를 다시 읽었습니다.");
  } catch (err) {
    toast(err.message);
  }
};
document.querySelector("#close").onclick = () => dialog.close();
desk.oninput = (e) => {
  const f = e.target.closest("form");
  if (f) {
    const t = data.topics[+f.closest("[data-index]").dataset.index];
    saved.set(key(t), {
      ...saved.get(key(t)),
      ...Object.fromEntries(new FormData(f)),
    });
  }
};
desk.onsubmit = async (e) => {
  e.preventDefault();
  if (busy) return;
  const t = data.topics[+e.target.closest("[data-index]").dataset.index];
  const form = Object.fromEntries(new FormData(e.target));
  if (!form.selection) {
    toast("채택할 원문, 보류 또는 철회를 선택해 주세요.");
    return;
  }
  if (form["unit-" + form.selection] === "choose") {
    toast("채택할 문장 또는 이 절 전체를 선택해 주세요.");
    return;
  }
  busy = true;
  try {
    await api("/api/decide", {
      actor: form.actor,
      note: form.note,
      selection: form.selection,
      unit: form["unit-" + form.selection] ? Number(form["unit-" + form.selection]) : null,
      topic: t.name,
      generation: t.generation,
    });
    await load(true);
    toast("결정을 기록했습니다.");
  } catch (err) {
    toast(err.message);
    await load(true);
  } finally {
    busy = false;
  }
};
desk.onclick = async (e) => {
  if(e.target.closest("[data-review-jump]")){view="review";render();return;}
  const src = e.target.closest("[data-path]");
  if (src) {
    try {
      const d = await api(
        "/api/source?" +
          new URLSearchParams({
            path: src.dataset.path,
            version: src.dataset.version,
          }),
      );
      const line = Number(src.dataset.line),
        paper = document.querySelector("#paper");
      paper.innerHTML = `<h3>${esc(d.path)}</h3><small>원문 버전 ${esc(d.version.slice(0, 12))}</small>${d.outline.provider === "PageIndex" ? `<p>PageIndex 목차</p><div class="outline">${d.outline.nodes.map((n) => `<button class="link" data-jump="${n.line}">${esc(n.title)}</button>`).join("")}</div>` : ""}${d.body
        .split(/\r?\n/)
        .map(
          (s, i) =>
            `<pre data-n="${i + 1}" class="${i + 1 === line ? "focus" : ""}"><small>${i + 1}  </small>${esc(s)}</pre>`,
        )
        .join("")}`;
      paper.onclick = (ev) => {
        const j = ev.target.closest("[data-jump]");
        if (j)
          paper
            .querySelector(`[data-n="${Number(j.dataset.jump)}"]`)
            ?.scrollIntoView({ block: "center" });
      };
      dialog.showModal();
      paper.querySelector(".focus")?.scrollIntoView({ block: "nearest" });
    } catch (err) {
      toast(err.message);
    }
    return;
  }
  const btn = e.target.closest("[data-advice]");
  if (!btn) return;
  const t = data.topics[+btn.dataset.advice];
  btn.disabled = true;
  try {
    const a = await api("/api/advice", {
      topic: t.name,
      generation: t.generation,
      ids: t.candidates.map((x) => x.id),
    });
    const text = `${a.model} · ${{ review: "검토 필요", compatible: "함께 적용 가능", insufficient: "근거 부족" }[a.choice]} (${Math.round(100 * a.probabilities[a.choice])}%)`;
    saved.set(key(t), { ...saved.get(key(t)), advice: text });
    const out = btn.parentElement.querySelector(".advice");
    out.textContent = text;
    out.hidden = false;
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
  }
};
load(true).catch((e) => toast(e.message));
setInterval(() => load().catch((e) => toast(e.message)), 4500);
