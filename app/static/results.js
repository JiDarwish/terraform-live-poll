// Fills in the counts from /api/results every 2 s; the server renders everything else.
const main = document.querySelector("main");
const banner = document.querySelector(".banner");
const total = document.querySelector(".total-count");
// A Map, not CSS selectors: option text can contain quotes.
const rows = new Map([...document.querySelectorAll("li[data-option]")].map((li) => [li.dataset.option, li]));
// Split traffic across revisions can answer from either one: reload only once
// the change holds for this many ticks in a row.
const RELOAD_AFTER = 3;
let changedTicks = 0;

async function tick() {
  const started = Date.now();
  try {
    const r = await fetch("/api/results", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    const data = await r.json();
    banner.hidden = true;
    // A new poll or revision changes the question, options or footer: re-render it all.
    if (data.poll_id !== main.dataset.pollId || data.revision !== main.dataset.revision) {
      if (++changedTicks >= RELOAD_AFTER) {
        location.reload();
        return;
      }
    } else {
      changedTicks = 0;
    }
    for (const { option, count } of data.options) {
      const li = rows.get(option);
      if (!li) continue;
      li.querySelector(".count").textContent = count;
      li.querySelector(".bar").style.width = (count / Math.max(data.total, 1)) * 100 + "%";
    }
    total.textContent = data.total;
  } catch {
    banner.hidden = false; // keep the last counts on screen
  }
  // Time the next tick from this one's start, so request time doesn't stretch the 2 s cycle.
  setTimeout(tick, Math.max(0, 2000 - (Date.now() - started)));
}

tick();
