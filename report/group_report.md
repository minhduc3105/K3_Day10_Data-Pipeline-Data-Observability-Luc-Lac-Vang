# Báo cáo nhóm — Data Pipeline, Data Observability và RAG Chatbot

## 1. Thông tin nhóm

| Nội dung | Giá trị |
|---|---|
| Môn/lab | Day 10 — Data Pipeline & Data Observability |
| Tên hệ thống | Crossref Scholarly RAG |
| Nguồn dữ liệu | Crossref REST API — /works |
| LLM | OpenRouter — openai/gpt-4o-mini |
| Ngày đánh giá gần nhất | 2026-08-06 |

### Thành viên và phân công

| Thành viên | MSSV | Vai trò chính | Module/deliverable |
|---|---|---|---|
| Lã Minh Đức | 2A202601261 | Nhóm trưởng, tích hợp và orchestration | src/pipelines/phase1.py, src/pipelines/corruption_flow.py, review contract, chạy end-to-end |
| Hà Nhật Khánh Duy | 2A202602031 | Data ingestion và cleaning | src/ingestion/crossref.py, src/ingestion/cleaning.py, raw/clean artifacts |
| Hoàng Tuấn Trung | 2A202601807 | Embedding, chunking và vector retrieval | src/retrieval/embeddings.py, src/retrieval/index.py, ChromaDB manifest |
| Lâm Việt Hoàng | 2A202601067 | LLM provider và chatbot agent | src/retrieval/llm.py, src/retrieval/agent.py, src/retrieval/qa.py, OpenRouter fallback |
| Trần Huy Hoàng | 2A202601709 | Evaluation và frozen test set | src/evaluation/testset.py, src/evaluation/metrics.py, provenance/hash và scoring |
| Bùi Hữu Nghĩa | 2A202601880 | Observability, corruption và báo cáo | src/observability/quality.py, src/observability/reporting.py, src/ingestion/corruption.py, pytest |

Mỗi thành viên chịu trách nhiệm giải thích input, output, contract và cách kiểm chứng của module mình phụ trách. Nhóm trưởng chịu trách nhiệm tích hợp và kiểm tra kết quả cuối.

## 2. Mục tiêu và kiến trúc

Hệ thống biến bài báo khoa học từ Crossref thành chatbot hỏi đáp có evidence. Raw data được giữ để audit, còn các state baseline/corrupted/repaired dùng chung một frozen test set.

~~~text
Crossref API
  -> raw response + parsed records
  -> cleaning/data modeling
  -> MiniLM embeddings + ChromaDB chunks
  -> retrieval + OpenRouter agent
  -> baseline evaluation
  -> controlled corruption
  -> corrupted evaluation
  -> repair từ raw records
  -> repaired evaluation + comparison report
~~~

Index tách mỗi paper thành chunk paper, metadata và abstract. Search lấy candidate pool rộng, rerank semantic similarity kết hợp lexical overlap, sau đó gộp theo paper_id.

## 3. Dữ liệu và contract

Crossref ingestion có retry/backoff cho HTTP 429 và 503, lưu raw response và parsed records:

- data/raw/crossref_response.json
- data/raw/crossref_records.json

Cleaning gỡ XML/HTML, chuẩn hóa title/summary/authors/categories, tạo text_for_embedding, published và age_days:

- data/clean/papers_clean.csv
- data/clean/papers_clean.json

Baseline có 199 raw records và 197 clean records. Duplicate paper_id được giữ trong corrupted artifact để quality check phát hiện, không bị xóa âm thầm.

## 4. Cấu hình evaluation

| Thành phần | Cấu hình |
|---|---|
| Số câu hỏi | 10 |
| Phân bố | summary 3, authors 3, publication date 2, publisher 2 |
| Frozen hash | c0302193f620f9de2618a45b2fb24f8858f781482309b4b680286628182b54bb |
| Embedding | sentence-transformers/all-MiniLM-L6-v2 |
| Vector store | ChromaDB, cosine distance |
| Retrieval | top-k = 4 papers sau khi gộp chunk |
| Agent/LLM | OpenRouter openai/gpt-4o-mini |
| Agent answers | 10/10; fallback 0 |
| Test provenance | data/eval/test_set_provenance.json |

Ground truth và ground_truth_doc_ids được copy từ clean data. Mỗi câu hỏi được kiểm tra document ground truth xuất hiện trong top-k trước khi đóng băng. Điều này đảm bảo pipeline có khả năng retrieval, nhưng làm retrieval hit rate lạc quan hơn một held-out benchmark độc lập.

## 5. Kết quả thực tế

| State | Samples | Retrieval hit rate | Mean token F1 | Judge accuracy | Mean judge score |
|---|---:|---:|---:|---:|---:|
| Baseline | 10 | 1.0000 | 0.1515 | 0.9000 | 4.80/5 |
| Corrupted | 10 | 0.6000 | 0.1202 | 0.7000 | 3.80/5 |
| Repaired | 10 | 1.0000 | 0.1560 | 0.9000 | 4.80/5 |

**Latest evidence.** All three runs use frozen-set SHA-256 `c0302193f620f9de2618a45b2fb24f8858f781482309b4b680286628182b54bb`. Corrupting four frozen documents with blank summaries removes them from the index: retrieval drops by 0.4000, token F1 by 0.0313, and judge accuracy by 0.2000. Repair rebuilds from `data/raw/crossref_records.json`; retrieval and judge accuracy return exactly to baseline. The small F1 difference (+0.0045) is from LLM wording, not a different corpus or test set.

Bằng chứng nằm trong data/results/baseline_metrics.json, corrupted_metrics.json, repaired_metrics.json và data/reports/corruption_report.md.

### Phân tích

Retrieval đạt 1.0: 10/10 ground-truth documents đều ở top-k. Chunking và hybrid reranking đã xử lý tốt việc title/abstract/metadata cạnh tranh nhau. Tuy nhiên test set có retrieval validation trước khi frozen nên không nên xem đây là benchmark hoàn toàn độc lập.

Judge accuracy 0.9: 9/10 câu được judge chấp nhận; agent dùng OpenRouter thật cho cả 10 câu. Trường hợp lỗi chính là câu authors: agent liệt kê thêm tác giả từ paper liên quan dù paper đúng vẫn được retrieve. Đây là lỗi answer focus, không phải lỗi tìm tài liệu.

Token F1 0.1635 thấp hơn cảm nhận thực tế vì reference và answer khác format. Summary reference là abstract dài còn agent diễn giải ngắn; ngày trong reference là ISO còn agent viết tự nhiên; authors có thể được agent thêm context. Vì vậy token F1 phù hợp để so sánh tương đối giữa các state nhưng chưa đủ để kết luận factual answer sai.

Corruption làm F1 giảm từ 0.1635 xuống 0.1508, giảm 0.0127 tuyệt đối, khoảng 7.8%. Retrieval vẫn 1.0 vì các tài liệu bị hỏng còn nằm trong top-k. Nghĩa là corruption hiện ảnh hưởng nội dung evidence/answer nhiều hơn thứ hạng paper.

Repair khôi phục data quality: baseline và repaired đều 197 rows, 0 duplicate, Valid=True; corrupted có 198 rows, 1 duplicate, Valid=False. F1 repaired tăng lên 0.1538 nhưng chưa về baseline do agent/LLM có độ dao động và token F1 nhạy với wording. Repair vẫn đúng contract vì bắt đầu lại từ raw records.

### Quality và freshness

| State | Valid | Rows | Duplicate rows | Stale rows | Missing dates |
|---|---|---:|---:|---:|---:|
| Baseline | True | 197 | 0 | 172 | 6 |
| Corrupted | False | 198 | 1 | 173 | 6 |
| Repaired | True | 197 | 0 | 172 | 6 |

Các scenario: blank summary, stale date về 2000-01-01, duplicate ID và embedding noise. Corrupted quality fail đúng kỳ vọng; repair từ data/raw khôi phục uniqueness và schema.

Freshness baseline False vì 172 records cũ hơn threshold 180 ngày và 6 records thiếu ngày. Đây có thể là dữ liệu cũ hợp lệ trong Crossref, không nhất thiết là ingestion failure. Hệ thống cần tách old-but-valid khỏi late ingestion và stale do corruption.

## 6. Thực trạng và nguyên nhân

| Thực trạng | Nguyên nhân | Bằng chứng |
|---|---|---|
| Retrieval rất cao | Test set pre-validated; index có nhiều chunk và hybrid reranking | test_set_provenance.json, baseline_answers.json |
| Token F1 thấp | Metric đếm token, không hiểu paraphrase/format ngày | baseline_answers.json, q1/q3/q7 |
| Judge cao hơn F1 | Judge đánh giá ngữ nghĩa và material correctness | metrics và judge reasoning |
| Corrupted vẫn hit 100% | Corruption chưa đẩy document đúng ra khỏi top-k | corrupted_metrics.json |
| Repair quality pass | Repair đọc raw rồi chạy cleaning chuẩn | corruption_flow.py, repaired quality |
| Freshness fail | Nguồn có publication cũ/missing dates | data/quality/freshness_report.json |

## 7. Hướng xử lý về sau

1. **Field-aware scoring:** chuẩn hóa ngày về ISO; authors so sánh như set tên; publisher exact match sau normalize; summary dùng semantic similarity hoặc entailment, bổ sung ROUGE-L/BERTScore.
2. **Giới hạn agent vào đúng fact:** prompt yêu cầu chỉ trả field được hỏi, không liệt kê paper/tác giả ngoài ground-truth evidence, luôn trả paper_id và chunk evidence.
3. **Held-out evaluation:** giữ 10 câu frozen cho demo và thêm 20–30 câu độc lập không pre-validate để đo chất lượng không thiên lệch.
4. **Corruption mạnh hơn cho retrieval:** xóa title/abstract chunk hoặc thay embedding của tài liệu được hỏi, rồi đo top-k giảm.
5. **Freshness rõ nghĩa hơn:** phân nhóm old-but-valid, missing date, ingestion delay và corrupted stale.
6. **Tăng sample khi benchmark:** 10 câu phù hợp demo nhanh; khi kết luận chất lượng production nên dùng tối thiểu 30–50 câu.

## 8. Tái hiện

Không commit .env, API key hoặc Chroma binary cache. Cần cấu hình LLM_PROVIDER=openrouter, LLM_MODEL=openai/gpt-4o-mini và OPENROUTER_API_KEY trong môi trường local.

~~~powershell
uv run pytest -q
uv run python script/run_phase1.py --refresh-testset --provider openrouter --model openai/gpt-4o-mini
uv run python script/run_corruption_flow.py --provider openrouter --model openai/gpt-4o-mini
~~~

Artifacts chính: data/raw, data/clean, data/eval, data/results và data/reports.

## 9. Kết luận

Nhóm đã hoàn thành pipeline từ ingestion, cleaning, embedding, ChromaDB, OpenRouter agent, evaluation đến corruption/repair và observability. Với 10 câu hỏi đa dạng, baseline retrieve đúng 10/10 tài liệu và judge chấp nhận 9/10 câu. Corruption được phát hiện ở data quality và làm F1 giảm; repair khôi phục schema/uniqueness nhưng không thể bảo đảm LLM dùng cùng wording với baseline.

Kết luận phù hợp: **retrieval và data lineage đã đạt mức tốt cho demo; answer scoring và freshness vẫn cần cải thiện trước khi dùng như benchmark production.**
