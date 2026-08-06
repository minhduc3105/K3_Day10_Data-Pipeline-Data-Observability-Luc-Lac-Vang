const fallback = {
  baseline: { samples: 42, retrieval_hit_rate: 0.14285714285714285, mean_token_f1: 0.053664296865925304, mean_judge_score: 2.761904761904762, frozen_test_set_hash: "db85afe199ac6a51bbb5abd0ce4c1cbdcc542bf39cebafbc660e67ffe29cc377" },
  corrupted: { samples: 42, retrieval_hit_rate: 0.14285714285714285, mean_token_f1: 0.05891164336768675, mean_judge_score: 2.9523809523809526, frozen_test_set_hash: "db85afe199ac6a51bbb5abd0ce4c1cbdcc542bf39cebafbc660e67ffe29cc377" },
  repaired: { samples: 42, retrieval_hit_rate: 0.14285714285714285, mean_token_f1: 0.06037731328326092, mean_judge_score: 2.880952380952381, frozen_test_set_hash: "db85afe199ac6a51bbb5abd0ce4c1cbdcc542bf39cebafbc660e67ffe29cc377" }
};
const metricPaths = { baseline: "../data/results/baseline_metrics.json", corrupted: "../data/results/corrupted_metrics.json", repaired: "../data/results/repaired_metrics.json" };
const states = { ...fallback };
let frozenQuestions = [{
  id: "q1", question_type: "factual",
  question: "Vấn đề chính mà phần mềm học máy phải đối mặt là gì và tại sao nó khác biệt so với phần mềm thông thường?",
  ground_truth: "Abstract Machine learning software is fundamentally different from most other software in one important respect: it is tightly linked with data.",
  ground_truth_doc_ids: ["10.1002/9781118445112.stat08455"]
}];

async function refreshMetrics() {
  await Promise.all(Object.entries(metricPaths).map(async ([name, path]) => {
    try { const res = await fetch(path, { cache: "no-store" }); if (res.ok) states[name] = await res.json(); } catch (_) { /* File-preview mode uses the intentionally embedded snapshot. */ }
  }));
  updateMetrics("baseline");
}
async function refreshFrozenQuestions() {
  try {
    const response = await fetch("../data/eval/test_set.json", { cache: "no-store" });
    if (response.ok) frozenQuestions = await response.json();
  } catch (_) { /* Direct file previews retain the representative embedded sample. */ }
  document.querySelector("#frozen-count").textContent = frozenQuestions.length;
}
function showQuestion(item) {
  const doi = item.ground_truth_doc_ids?.[0] || "";
  document.querySelector("#question-id").textContent = `${item.id} · ${item.question_type}`;
  document.querySelector("#frozen-question").textContent = item.question;
  document.querySelector("#ground-truth").textContent = item.ground_truth;
  document.querySelector("#ground-doc").href = `https://doi.org/${doi}`;
}
function updateMetrics(name) {
  const item = states[name];
  const hit = item.retrieval_hit_rate * 100;
  document.querySelector("#hit-rate").innerHTML = `${hit.toFixed(1)}<span>%</span>`;
  document.querySelector("#hit-bar").style.width = `${hit}%`;
  document.querySelector("#token-f1").textContent = Number(item.mean_token_f1).toFixed(3);
  document.querySelector("#judge-score").innerHTML = `${Number(item.mean_judge_score).toFixed(2)}<span>/5</span>`;
  document.querySelector("#sample-count").innerHTML = `${item.samples}<span>/${item.samples}</span>`;
  document.querySelectorAll(".metric-switch button").forEach(button => {
    const active = button.dataset.state === name;
    button.classList.toggle("active", active); button.setAttribute("aria-selected", String(active));
  });
}
document.querySelectorAll(".metric-switch button").forEach(button => button.addEventListener("click", () => updateMetrics(button.dataset.state)));

const observer = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.add("visible"); observer.unobserve(entry.target); } }), { threshold: .12 });
document.querySelectorAll(".reveal").forEach(element => observer.observe(element));

const dialog = document.querySelector("#why-dialog");
document.querySelector("[data-open-modal]").addEventListener("click", () => dialog.showModal());
document.querySelectorAll("[data-close-modal]").forEach(button => button.addEventListener("click", () => dialog.close()));
dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
document.querySelector("#random-question").addEventListener("click", () => {
  const next = frozenQuestions[Math.floor(Math.random() * frozenQuestions.length)];
  showQuestion(next);
});
refreshMetrics();
refreshFrozenQuestions();
