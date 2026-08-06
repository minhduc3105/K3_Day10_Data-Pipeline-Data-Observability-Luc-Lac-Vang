const fallbackMetrics = {
  baseline: { samples: 10, retrieval_hit_rate: 1, mean_token_f1: 0.1515045116252853, mean_judge_score: 4.8, judge_accuracy: 0.9 },
  corrupted: { samples: 10, retrieval_hit_rate: 0.6, mean_token_f1: 0.12023774155145564, mean_judge_score: 3.8, judge_accuracy: 0.7 },
  repaired: { samples: 10, retrieval_hit_rate: 1, mean_token_f1: 0.1560087725297113, mean_judge_score: 4.8, judge_accuracy: 0.9 }
};
const metricPaths = {
  baseline: "../data/results/baseline_metrics.json",
  corrupted: "../data/results/corrupted_metrics.json",
  repaired: "../data/results/repaired_metrics.json"
};
const answerPaths = {
  baseline: "../data/results/baseline_answers.json",
  corrupted: "../data/results/corrupted_answers.json",
  repaired: "../data/results/repaired_answers.json"
};
const caseInfo = {
  q1: {
    updatedReading: "The blank summary removes the ground-truth paper from the corrupted index: retrieval changes from hit to miss. Repair rebuilds the paper from raw records and restores the hit.",
    tag: "Data corruption · blank summary",
    reading: "Blank summary làm F1 giảm 0.119 → 0.075 ở state corrupted. Tuy vậy paper đúng vẫn nằm trong top-k và judge vẫn chấp nhận câu trả lời; đây là evidence corruption tác động answer wording trước khi làm retrieval fail."
  },
  q2: {
    tag: "Agent edge case · answer over-generation",
    reading: "Retriever tìm được đúng Classic Machine Learning Methods, nhưng agent trả thêm authors từ các paper lân cận. Judge chấm 3/5 và không correct: lỗi nằm ở answer focus, không phải document recall."
  },
  q3: {
    tag: "Metric edge case · date normalization",
    reading: "Cả ba state trả đúng ngày April 1, 2023, nhưng token F1 = 0 vì ground truth lưu ISO 2023-04-01. Case này cho thấy cần field-aware date scoring thay vì chỉ token overlap."
  }
};
const fallbackAnswers = {
  baseline: [
    { id: "q1", question: "What unique challenges arise in the development and operation of machine learning software, as discussed in the context of MLOps, that require expertise in both statistical methods and software engineering?", ground_truth: "Abstract Machine learning software is fundamentally different from most other software in one important respect: it is tightly linked with data.", ground_truth_doc_ids: ["10.1002/9781118445112.stat08455"], answer: "Machine learning software is tightly linked with data, so MLOps needs both statistical and software-engineering expertise.", token_f1: 0.1194, judge: { score: 5, correct: true }, retrieved_doc_ids: ["10.1002/9781118445112.stat08455"] },
    { id: "q2", question: "Who are the authors that discuss classic machine learning techniques, including supervised methods for classification and regression, as well as strategies to address overfitting?", ground_truth: "Johann Faouzi, Olivier Colliot", ground_truth_doc_ids: ["10.1007/978-1-0716-3195-9_2"], answer: "Johann Faouzi and Olivier Colliot, plus unrelated authors from other retrieved papers.", token_f1: 0, judge: { score: 3, correct: false }, retrieved_doc_ids: ["10.1093/oso/9780198828044.003.0003", "10.1007/978-1-0716-3195-9_2"] },
    { id: "q3", question: "What is the publication date of the paper that discusses Naive AutoML?", ground_truth: "2023-04-01", ground_truth_doc_ids: ["10.1007/s10994-022-06200-0"], answer: "The paper was published on April 1, 2023.", token_f1: 0, judge: { score: 5, correct: true }, retrieved_doc_ids: ["10.1007/s10994-022-06200-0"] }
  ],
  corrupted: [],
  repaired: []
};
fallbackAnswers.corrupted = fallbackAnswers.baseline.map(item => ({ ...item, token_f1: item.id === "q1" ? 0.0755 : item.token_f1 }));
fallbackAnswers.repaired = fallbackAnswers.baseline.map(item => ({ ...item, token_f1: item.id === "q1" ? 0.1094 : item.token_f1 }));

const states = { ...fallbackMetrics };
const answersByState = { ...fallbackAnswers };
let frozenQuestions = fallbackAnswers.baseline;
let selectedCase = "q1";

async function loadJson(path, fallback) {
  try {
    const response = await fetch(path, { cache: "no-store" });
    if (response.ok) return await response.json();
  } catch (_) {
    // Direct file previews keep a compact local snapshot.
  }
  return fallback;
}

async function refreshData() {
  const metricEntries = await Promise.all(Object.entries(metricPaths).map(async entry => [entry[0], await loadJson(entry[1], fallbackMetrics[entry[0]])]));
  metricEntries.forEach(entry => { states[entry[0]] = entry[1]; });
  const answerEntries = await Promise.all(Object.entries(answerPaths).map(async entry => [entry[0], await loadJson(entry[1], fallbackAnswers[entry[0]])]));
  answerEntries.forEach(entry => { answersByState[entry[0]] = entry[1]; });
  frozenQuestions = await loadJson("../data/eval/test_set.json", frozenQuestions);
  document.querySelector("#frozen-count").textContent = frozenQuestions.length;
  updateMetrics("baseline");
  renderCase(selectedCase);
}

function verdict(item) {
  if (!item) return "No output";
  return "Judge " + (item.judge?.score ?? "—") + "/5 · " + (item.judge?.correct ? "đúng" : "cần xem lại");
}

function renderCase(id) {
  selectedCase = id;
  const baseline = answersByState.baseline.find(item => item.id === id);
  if (!baseline) return;
  const info = caseInfo[id];
  document.querySelector("#case-tag").textContent = info.tag;
  document.querySelector("#case-question").textContent = baseline.question;
  document.querySelector("#case-truth").textContent = baseline.ground_truth;
  document.querySelector("#case-source").href = "https://doi.org/" + (baseline.ground_truth_doc_ids?.[0] || "");
  document.querySelector("#case-reading").textContent = info.updatedReading || info.reading;

  ["baseline", "corrupted", "repaired"].forEach(state => {
    const item = answersByState[state].find(answer => answer.id === id);
    document.querySelector("#" + state + "-answer").textContent = item?.answer || "Không có output cho state này.";
    document.querySelector("#" + state + "-verdict").textContent = verdict(item);
    document.querySelector("#" + state + "-f1").textContent = "Token F1 " + Number(item?.token_f1 ?? 0).toFixed(3);
    const topDoc = item?.retrieved_doc_ids?.[0] || "—";
    document.querySelector("#" + state + "-docs").textContent = "Top evidence " + topDoc;
  });

  document.querySelectorAll(".case-switch button").forEach(button => {
    const active = button.dataset.caseId === id;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
}

function showQuestion(item) {
  const doi = item.ground_truth_doc_ids?.[0] || "";
  document.querySelector("#question-id").textContent = item.id + " · " + item.question_type;
  document.querySelector("#frozen-question").textContent = item.question;
  document.querySelector("#ground-truth").textContent = item.ground_truth;
  document.querySelector("#ground-doc").href = "https://doi.org/" + doi;
}

function updateMetrics(state) {
  const item = states[state];
  const hit = item.retrieval_hit_rate * 100;
  document.querySelector("#hit-rate").innerHTML = hit.toFixed(1) + "<span>%</span>";
  document.querySelector("#hit-bar").style.width = hit + "%";
  document.querySelector("#token-f1").textContent = Number(item.mean_token_f1).toFixed(3);
  document.querySelector("#judge-score").innerHTML = Number(item.mean_judge_score).toFixed(2) + "<span>/5</span>";
  document.querySelector("#sample-count").innerHTML = item.samples + "<span>/" + item.samples + "</span>";
  document.querySelectorAll(".metric-switch button").forEach(button => {
    const active = button.dataset.state === state;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  Object.entries(states).forEach(entry => {
    const name = entry[0];
    const metric = entry[1];
    const chart = document.querySelector('[data-chart-state="' + name + '"]');
    if (!chart) return;
    chart.querySelector(".bar").style.setProperty("--height", (Number(metric.mean_judge_score) * 20) + "%");
    chart.querySelector("b").textContent = Number(metric.mean_judge_score).toFixed(2);
  });
}

document.querySelectorAll(".metric-switch button").forEach(button => button.addEventListener("click", () => updateMetrics(button.dataset.state)));
document.querySelectorAll(".case-switch button").forEach(button => button.addEventListener("click", () => renderCase(button.dataset.caseId)));

const observer = new IntersectionObserver(entries => entries.forEach(entry => {
  if (entry.isIntersecting) {
    entry.target.classList.add("visible");
    observer.unobserve(entry.target);
  }
}), { threshold: .12 });
document.querySelectorAll(".reveal").forEach(element => observer.observe(element));

const dialog = document.querySelector("#why-dialog");
document.querySelector("[data-open-modal]").addEventListener("click", () => dialog.showModal());
document.querySelectorAll("[data-close-modal]").forEach(button => button.addEventListener("click", () => dialog.close()));
dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
document.querySelector("#random-question").addEventListener("click", () => {
  const next = frozenQuestions[Math.floor(Math.random() * frozenQuestions.length)];
  showQuestion(next);
});

refreshData();
