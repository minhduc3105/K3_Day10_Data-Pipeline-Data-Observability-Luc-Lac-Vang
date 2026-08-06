# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                                            |
| ----------------- | ----------------------------------------------------------------------------------- |
| Họ và tên        | Trần Huy Hoàng                                                                     |
| MSSV              | 2A202601709                                                                  |
| Khóa/Lớp         | K3                                                                                    |
| Tên nhóm         | Lúc Lắc Vàng                                                                       |
| Vai trò chính     | Source & data-model owner (ingestion, cleaning, evaluation set)                       |
| Repository        | https://github.com/minhduc3105/K3_Day10_Data-Pipeline-Data-Observability-Luc-Lac-Vang |
| Nhánh làm việc   | `tranhuyhoang`                                                                        |
| Ngày hoàn thành  | 2026-08-06 (phần việc cá nhân; pipeline chung chưa đóng)                         |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable       | File/hàm phụ trách                                                                  | Input nhận vào                                | Output bàn giao                                                        | Trạng thái   |
| ------------------------ | ------------------------------------------------------------------------------------ | ----------------------------------------------- | ------------------------------------------------------------------------ | ------------- |
| Raw ingestion (Crossref) | `src/ingestion/crossref.py` — `fetch_source_records`, `parse_crossref_payload`, `load_raw_records` | `Settings` (query, filter, `max_results=24`)     | `data/raw/crossref_response.json`, `data/raw/crossref_records.json`       | Hoàn thành  |
| Cleaning & data modeling | `src/ingestion/cleaning.py` — `strip_markup`, `_parse_published`, `build_clean_dataframe`, `save_clean_dataframe` | `list[PaperRecord]` + `run_date`                 | `data/clean/papers_clean.csv`, `data/clean/papers_clean.json` (24 dòng, 14 cột) | Hoàn thành  |
| Evaluation set           | `src/evaluation/testset.py` — `build_test_set`, `_ground_truth`, `_select_indices`   | Cleaned dataframe                                | `data/eval/test_set.json` (9 câu hỏi)                                    | Hoàn thành  |

Ba khối này nằm liền nhau trong luồng dữ liệu: `crossref.py` định nghĩa raw schema (`PaperRecord`), `cleaning.py` biến raw schema thành clean schema + `text_for_embedding`, `testset.py` sinh evaluation set từ chính clean schema đó. Các thành viên phụ thuộc vào output của tôi: owner của `quality.py` (đọc `summary_chars`, `age_days`, `published`), owner của `phase1.py` (gọi cả ba hàm), owner của `corruption.py` (corrupt trên clean schema và repair lại từ `data/raw/crossref_records.json` qua `load_raw_records`).

**Không thuộc phạm vi của tôi:** `quality.py`, `reporting.py`, `phase1.py`, `corruption.py`, `corruption_flow.py`. Tính đến thời điểm nộp bản này, các file đó vẫn còn `NotImplementedError`.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                                  | Thành viên/module được hỗ trợ | Kết quả                                                                                                                |
| ------------------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Cố định contract `paper_id` = DOI          | `corruption.py`, `quality.py`   | Document identity giữ nguyên giữa raw → clean → Chroma, nên repair từ raw không làm lệch `ground_truth_doc_ids`     |
| Bổ sung cột phái sinh cho observability   | `quality.py`                    | `summary_chars` và `age_days` được tính sẵn trong `build_clean_dataframe` để quality/freshness check không phải tự parse |
| Giữ `load_raw_records` như đường repair    | `corruption_flow.py`            | Repair có thể đọc lại raw records mà không cần gọi lại Crossref (nguồn sống, gọi lại sẽ ra dữ liệu khác)         |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện                                        | File/hàm/artifact liên quan                                 | Kết quả bàn giao                                                | Cách xác minh                                                                 |
| ----------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| Fetch Crossref có retry/backoff, lưu cả raw response lẫn raw records | `fetch_source_records`                                        | `crossref_response.json` (245 KB), `crossref_records.json` (60 KB) | Đọc file: 24 item trong `message.items`, 24 record sau parse                   |
| Parse payload Crossref sang `PaperRecord`                          | `parse_crossref_payload`                                      | 24/24 item được giữ                                              | So khớp `len(payload["message"]["items"])` với `len(records)`                  |
| Làm sạch JATS markup, chuẩn hóa ngày, dedupe                    | `strip_markup`, `_parse_published`, `build_clean_dataframe`   | 24 dòng, 14 cột, `paper_id` unique 24/24                        | `pandas` đọc CSV: `summary_chars` min 826 / mean 1727 / max 2610, không NaN     |
| Sinh evaluation set frozen, deterministic                          | `build_test_set`                                              | `data/eval/test_set.json`, 9 câu hỏi                             | Chạy lại hàm cho ra đúng 9 câu giống hệt, cùng `ground_truth_doc_ids`      |

Một output cụ thể do phần việc của tôi tạo ra:

`data/clean/papers_clean.csv` — 24 bài báo Crossref đã sạch markup, có cột `text_for_embedding` dạng `Title: ... | Authors: ... | Summary: ...`. Chính cột này được embed bằng `all-MiniLM-L6-v2` và nạp vào Chroma: kiểm tra `data/chroma/chroma.sqlite3` thấy collection `papers-baseline` với đúng 24 vector, khớp 1-1 với số dòng clean. Đây là bằng chứng schema tôi bàn giao dùng được cho bước index mà không cần sửa thêm.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Phần của tôi là đầu nguồn của toàn bộ pipeline. Crossref là nguồn sống, trả về dữ liệu bẩn và không đồng nhất: abstract nhúng thẻ JATS (`<jats:p>`, `<jats:italic>`) và HTML entity; ngày tháng ở dạng `date-parts` khuyết tháng/ngày; nhiều item không có abstract hoặc không có `subject`; DOI có thể trùng. Nếu để nguyên, rác sẽ đi thẳng vào embedding và làm hỏng retrieval — mà lúc đó rất khó phân biệt "retrieval kém do model" với "retrieval kém do dữ liệu bẩn". Ngoài ra evaluation set phải **đóng băng**, vì baseline/corrupted/repaired bắt buộc đo trên cùng một bộ câu hỏi.

### Cách triển khai

**Ingestion.** Gọi `https://api.crossref.org/works` với `query`, `filter=from-pub-date:<today-180d>,has-abstract:true`, `rows=24` và tham số `mailto` để vào polite pool. Retry tối đa 5 lần với exponential backoff `1 * 2^attempt` giây, xử lý riêng 429/503 và `RequestException`. Ghi **raw response nguyên vẹn trước khi parse** để bước repair sau này có thể tái tạo dữ liệu mà không gọi lại API. Khi parse, bỏ item thiếu DOI, thiếu title hoặc thiếu abstract; ghép `given + family` thành tên tác giả; `date-parts` khuyết được đệm mặc định về tháng 1/ngày 1 rồi format `YYYY-MM-DD`.

**Cleaning.** `strip_markup` xóa tag bằng regex `<[^>]+>` rồi `html.unescape` và chuẩn hóa whitespace — thứ tự này quan trọng, unescape trước sẽ biến `&lt;b&gt;` thành tag thật và tag đó lại lọt lưới. Quy tắc loại bỏ: title rỗng, abstract dưới `MIN_SUMMARY_CHARS = 100`, hoặc `published` không parse được. Dedupe theo `paper_id` giữ bản đầu, sắp xếp `published` giảm dần rồi `paper_id` tăng dần để thứ tự dòng ổn định giữa các lần chạy. Sinh thêm ba cột phái sinh: `summary_chars` và `age_days` cho observability, `text_for_embedding` cho retrieval.

**Evaluation set.** Bốn template câu hỏi (authors / date / summary / categories), mỗi loại lấy 3 bài. `_select_indices` chọn vị trí **cách đều** `step = total / count` cộng `offset = type_index` để mỗi loại câu hỏi rơi vào bài khác nhau, mở rộng độ phủ document mà vẫn deterministic — không dùng `random`. Ground truth lấy trực tiếp từ cột clean tương ứng, riêng loại `summary` dùng `first_sentence`. Câu nào không có ground truth thì bỏ.

### Input, output và contract

| Thành phần                  | Mô tả                                                                                                                     |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Input                        | `Settings` từ `core.config` (query, filter, `max_results`, các path); không hard-code path nào                            |
| Output                       | Raw: JSON list của `PaperRecord`. Clean: DataFrame 14 cột + CSV/JSON. Eval: list dict `{id, question_type, question, ground_truth, ground_truth_doc_ids}` |
| Module phụ thuộc            | `core.config` (paths), `core.utils` (`normalize_whitespace`, `compact_join`, `first_sentence`, `write_csv`, `write_json`)   |
| Module sử dụng output       | `retrieval/embeddings.py` + `index.py` (đọc `text_for_embedding`), `evaluation/metrics.py` (đọc test set), `observability/quality.py`, `ingestion/corruption.py`, `pipelines/phase1.py` |
| Điều kiện lỗi cần xử lý | Crossref 429/503 và timeout → retry/backoff; item thiếu DOI/title/abstract → bỏ; `date-parts` khuyết → đệm mặc định; abstract quá ngắn → loại; DOI trùng → dedupe; corpus dưới 5 document → raise `ValueError` thay vì tạo test set vô nghĩa |

### Cách xác minh

```bash
python -c "import pandas as pd, json; df=pd.read_csv('data/clean/papers_clean.csv'); print(len(df), df.paper_id.nunique(), df.summary_chars.min())"
python -c "import json; print(len(json.load(open('data/eval/test_set.json', encoding='utf-8'))))"
python -c "import sqlite3; c=sqlite3.connect('data/chroma/chroma.sqlite3'); print(c.execute('select name from collections').fetchall(), c.execute('select count(*) from embeddings').fetchone())"
```

- **Kết quả mong đợi:** clean dataset không trùng `paper_id`, mọi `summary_chars >= 100`, test set có ít nhất 5 câu, số vector trong Chroma bằng số dòng clean.
- **Kết quả thực tế:** 24 dòng / 24 `paper_id` unique / `summary_chars` nhỏ nhất 826; test set 9 câu; collection `papers-baseline` có đúng 24 vector. Không còn chuỗi `<jats:` nào trong cột `summary`.
- **Artifact/log:** `data/raw/`, `data/clean/`, `data/eval/test_set.json`, `data/embeddings/papers_embeddings.json`, `data/chroma/chroma.sqlite3`. Không có secret; `.env` nằm trong `.gitignore`.

**Ghi rõ giới hạn:** tôi xác minh phần việc của mình bằng cách đọc artifact và chạy lại từng hàm, **không phải** bằng `python script/run_phase1.py` chạy trót lọt. Lệnh đó hiện vẫn dừng ở `NotImplementedError` trong `src/pipelines/phase1.py` vì các module downstream chưa xong.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Chọn 12 câu hỏi từ 24 bài cho evaluation set. Bộ này phải dùng lại y hệt cho baseline, corrupted và repaired.
- **Các phương án đã cân nhắc:** (1) `random.sample` với seed cố định; (2) lấy N bài đầu bảng sau khi sort; (3) chọn vị trí cách đều `total / count` kèm `offset` xoay theo loại câu hỏi.
- **Phương án đã chọn:** phương án (3), cài trong `_select_indices`.
- **Lý do:** Phương án (1) deterministic nhưng phụ thuộc seed và implementation của RNG, và khi số dòng clean đổi thì tập chọn nhảy lung tung — so sánh giữa các lần chạy mất ý nghĩa. Phương án (2) tập trung toàn bộ câu hỏi vào nhóm bài mới nhất, nên nếu corruption đánh vào bài cũ thì test set không phát hiện được gì. Phương án (3) trải câu hỏi đều khắp corpus đã sort, và `offset = type_index` khiến 4 loại câu hỏi rơi vào 4 nhóm bài khác nhau — độ phủ document rộng hơn mà vẫn tái lập được 100%, không cần seed.
- **Bằng chứng quyết định phù hợp:** 9 câu hỏi cuối cùng trải trên 9 `paper_id` phân biệt (mỗi câu một document khác nhau) trong tổng số 24 bài — tức 37,5% corpus được phủ trực tiếp bởi ground truth. Chạy lại `build_test_set` trên cùng clean dataset cho ra file byte-identical.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Test set sinh ra chỉ có **9 câu thay vì 12** như thiết kế (4 loại × 3 bài). Kiểm tra `Counter` trên `question_type` thấy toàn bộ 3 câu loại `categories` biến mất.
- **Lệnh tái hiện:**
  ```bash
  python -c "import json; from collections import Counter; ts=json.load(open('data/eval/test_set.json', encoding='utf-8')); print(len(ts), Counter(q['question_type'] for q in ts))"
  ```
- **Nguyên nhân gốc:** Crossref **không trả trường `subject`** cho phần lớn record trong query này (khác arXiv luôn có category). Vì vậy `categories` là list rỗng → `categories_joined` là chuỗi rỗng → `_ground_truth` trả về `""`. Đây không phải lỗi code mà là đặc tính của nguồn dữ liệu; `primary_category` khi đó rơi về `"Unknown"`.
- **Cách xử lý:** Giữ nguyên guard `if not ground_truth: continue` trong `build_test_set` thay vì bịa ground truth. Sinh câu hỏi có đáp án rỗng sẽ khiến `token_f1` luôn bằng 0 và kéo tụt metric baseline một cách giả tạo, làm hỏng phép so sánh với corrupted. Đồng thời hạ ngưỡng chấp nhận về `MIN_DOCUMENTS = 5` để pipeline vẫn chạy khi nguồn thiếu trường.
- **Cách xác minh sau khi sửa:** Test set còn 9 câu, tất cả đều có `ground_truth` khác rỗng, phủ 9 document phân biệt — đủ trên ngưỡng 5.
- **Điều học được:** Test set phải phản ánh đúng thứ corpus thật sự trả lời được. Một câu hỏi không có đáp án trong corpus không đo được chất lượng agent, nó chỉ thêm nhiễu vào metric.

Một guard liên quan cũng đã xử lý cùng lúc: `build_test_set` lọc bỏ bài có dấu nháy đơn ASCII trong title (`~df["title"].str.contains("'")`), vì template bọc title trong `'...'` và dấu nháy lồng nhau sẽ phá regex exact-lookup ở `retrieval/qa.py`.

### Phần chưa hoàn thành (ngoài phạm vi sở hữu của tôi)

- **Phạm vi bị ảnh hưởng:** `src/observability/quality.py`, `src/observability/reporting.py`, `src/pipelines/phase1.py`, `src/ingestion/corruption.py`, `src/pipelines/corruption_flow.py` — cả 5 file còn `NotImplementedError`. Hệ quả: `data/results/`, `data/quality/`, `data/reports/` hiện chỉ có `.gitkeep`, chưa có `baseline_metrics.json`, `freshness_report.json`, `phase1_report.md`, `corruption_log.json` hay `corruption_report.md`.
- **Những gì đã loại trừ:** Không phải lỗi môi trường hay schema. Ingestion → cleaning → test set → embedding → Chroma đã thông (24 vector trong `papers-baseline`), nên phần chặn nằm ở orchestration và observability chưa được viết, không phải ở dữ liệu.
- **Bước tiếp theo:** Hoàn thành `quality.py` + `reporting.py` → ghép `phase1.py` → chạy `python script/run_phase1.py` để có `baseline_metrics.json` → mới làm `corruption.py` và `corruption_flow.py`.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. **Crossref → vector index.** `fetch_source_records` gọi Crossref REST API với filter ngày và `has-abstract:true`, lưu nguyên response vào `data/raw/crossref_response.json` rồi parse thành `PaperRecord` lưu ở `crossref_records.json`. `build_clean_dataframe` gỡ markup, chuẩn hóa ngày, loại record rác, dedupe theo DOI và ghép cột `text_for_embedding`. `retrieval/embeddings.py` encode cột đó bằng `all-MiniLM-L6-v2`, `retrieval/index.py` upsert vào Chroma collection `papers-baseline` với `paper_id` làm document ID. Truy vấn đi ngược lại: câu hỏi được encode cùng model, Chroma trả `top_k=4` document gần nhất, agent đọc các document đó để trả lời.

2. **Evaluation set và ground-truth document IDs.** Mỗi mẫu mang hai loại đáp án: `ground_truth` là chuỗi đáp án đúng, `ground_truth_doc_ids` là DOI của bài chứa đáp án. Hai thứ đo hai tầng khác nhau. `retrieval_hit_rate` kiểm tra DOI kỳ vọng có nằm trong top-k Chroma trả về hay không — đo tầng retrieval. `mean_token_f1`, `judge_accuracy`, `mean_judge_score` so câu trả lời sinh ra với `ground_truth` — đo tầng answer. Tách hai tầng cho phép chẩn đoán: hit rate tụt là lỗi retrieval/index; hit rate giữ nguyên mà token F1 tụt là lỗi ở nội dung document hoặc ở bước sinh câu trả lời.

3. **Quality checks khác freshness monitoring.** Quality check soi **tính đúng đắn nội tại** của một snapshot: thiếu field, summary rỗng, `summary_chars` dưới ngưỡng, `paper_id` trùng, số dòng hụt so với kỳ vọng — dữ liệu tự nó có hỏng không. Freshness soi **quan hệ giữa dữ liệu và thời gian**: `age_days` so với `freshness_threshold_days = 180`. Một dataset có thể sạch tuyệt đối mà vẫn cũ mèm — quality pass nhưng freshness fail. Trong corpus hiện tại `age_days` chạy từ 5 đến 175 ngày (published 2026-02-12 → 2026-08-01), tức mọi bài vẫn dưới ngưỡng 180.

4. **Vì sao dùng cùng test set cho cả ba trạng thái.** Vì chỉ khi câu hỏi và ground truth được giữ cố định thì chênh lệch metric mới quy được về **một biến duy nhất là chất lượng dữ liệu**. Đổi test set giữa các lần chạy thì không biết metric tụt do corruption hay do bộ câu hỏi mới khó hơn. Đó chính là lý do `build_test_set` phải deterministic và test set phải được đóng băng ở `data/eval/test_set.json` trước khi corruption chạy.

5. **Repair thành công dựa trên gì.** Ba điều kiện đồng thời: (a) quality checks quay về pass và freshness về lại trạng thái trước corruption; (b) `retrieval_hit_rate` và `mean_token_f1` của repaired hồi về xấp xỉ baseline, không chỉ nhỉnh hơn corrupted; (c) số dòng và tập `paper_id` của repaired dataset khớp baseline — chứng minh repair khôi phục từ `data/raw/crossref_records.json` chứ không phải fetch mới ra corpus khác. `data/reports/corruption_report.md` phải trình bày cả ba trạng thái trên cùng một bảng để đối chiếu.

## 8. Phân tích kết quả

### Metrics chính

Chưa có số liệu để điền. `data/results/` chỉ có `.gitkeep` — `baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json` đều chưa được sinh vì `phase1.py` và `corruption_flow.py` chưa implement.

| Metric/signal        | Baseline | Corrupted | Repaired | Nhận xét của cá nhân                                     |
| -------------------- | -------: | --------: | -------: | ----------------------------------------------------------- |
| `retrieval_hit_rate` |  chưa có |   chưa có |  chưa có | Chờ `phase1.py`                                            |
| `mean_token_f1`      |  chưa có |   chưa có |  chưa có | Chờ `phase1.py`                                            |
| `judge_accuracy`     |  chưa có |   chưa có |  chưa có | Chờ `phase1.py`                                            |
| `mean_judge_score`   |  chưa có |   chưa có |  chưa có | Chờ `phase1.py`                                            |
| Quality checks       |  chưa có |   chưa có |  chưa có | Chờ `quality.py`                                           |
| Freshness status     |  chưa có |   chưa có |  chưa có | Dữ liệu thô cho thấy `age_days` 5-175 < ngưỡng 180 |

### Số liệu đã xác minh được ở tầng dữ liệu

Đây là các con số tôi đo trực tiếp từ artifact, không phải metric của agent:

| Chỉ số                            | Giá trị          | Nguồn                        |
| ----------------------------------- | ------------------- | ------------------------------ |
| Item Crossref trả về               | 24                  | `crossref_response.json`       |
| Record sau parse                    | 24 (giữ 100%)      | `crossref_records.json`        |
| Dòng sau cleaning                  | 24, `paper_id` unique 24 | `papers_clean.csv`        |
| Độ dài summary (min/mean/max)     | 826 / 1727 / 2610 ký tự | `papers_clean.csv`        |
| `age_days` (min/max)                | 5 / 175             | `papers_clean.csv`             |
| Khoảng `published`                 | 2026-02-12 → 2026-08-01 | `papers_clean.csv`         |
| Câu hỏi trong test set            | 9 (thiết kế 12, rớt 3 loại `categories`) | `test_set.json` |
| Vector trong Chroma                 | 24, collection `papers-baseline` | `chroma.sqlite3`      |

### Kết luận từ số liệu

Hai chuỗi nguyên nhân–bằng chứng dưới đây là **giả thuyết đã đặt trước khi đo**, chưa được số liệu agent xác nhận:

1. Corruption xóa/làm rỗng `summary` → `summary_chars` tụt dưới ngưỡng và quality check fail → `text_for_embedding` mất phần nội dung chính nên vector lệch → `retrieval_hit_rate` giảm, kéo theo `mean_token_f1` giảm.
2. Repair đọc lại `data/raw/crossref_records.json` và chạy lại `build_clean_dataframe` → `summary_chars` và `age_days` về đúng phân bố baseline, quality check pass lại → `retrieval_hit_rate` và `mean_token_f1` hồi về mức baseline.

Dự đoán corruption ảnh hưởng mạnh nhất: **làm rỗng summary**, vì `text_for_embedding` gồm ba phần title/authors/summary mà summary chiếm gần như toàn bộ độ dài (trung bình 1727 ký tự so với title chỉ vài chục). Mất summary là mất gần hết tín hiệu ngữ nghĩa của vector. Ngược lại, corruption kiểu "ngày cũ" nhiều khả năng **không** làm giảm `retrieval_hit_rate` chút nào — MiniLM không đọc trường `published` — nhưng sẽ bị freshness monitoring bắt. Đây chính là ví dụ cho thấy vì sao cần cả hai loại signal thay vì chỉ nhìn metric của agent.

Một kết quả đã khác kỳ vọng ban đầu ngay ở tầng dữ liệu: tôi dự tính cleaning sẽ loại bớt vài record, nhưng cả 24/24 đều sống sót. Kiểm tra lại thì nguyên nhân là filter `has-abstract:true` đã lọc sẵn ở phía Crossref, cộng với việc `parse_crossref_payload` đã bỏ item thiếu abstract trước đó — nên tới bước cleaning thì mọi record đều có summary dài trên 800 ký tự, vượt xa ngưỡng 100. Điều này có nghĩa ngưỡng `MIN_SUMMARY_CHARS` hiện chưa từng kích hoạt trên dữ liệu sạch, và nó sẽ chỉ thật sự có tác dụng khi corruption flow bắt đầu làm rỗng summary.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Lưu raw response nguyên vẹn trước khi parse không phải thủ tục thừa — nó là điều kiện để repair được. Crossref là nguồn sống, gọi lại API sau vài ngày sẽ ra corpus khác, và lúc đó "repaired" không còn so sánh được với "baseline" nữa. Reproducibility đến từ artifact đã lưu, không đến từ việc chạy lại lệnh.
2. **Về data quality/observability:** Quality và freshness bắt hai lớp lỗi tách rời nhau, và một dataset có thể pass lớp này trong khi fail lớp kia. Tôi đã tính sẵn `summary_chars` với `age_days` ngay trong cleaning để hai loại check này có cột chuẩn để đọc thay vì mỗi module tự parse lại — contract rõ thì downstream đỡ lệch.
3. **Về ảnh hưởng của dữ liệu đến RAG agent:** Chất lượng dữ liệu tác động qua đúng con đường `text_for_embedding`. Trường nào không nằm trong chuỗi đó thì corruption lên nó sẽ vô hình với retrieval nhưng vẫn nguy hiểm với người dùng — ví dụ ngày tháng sai. Đó là lý do không thể chỉ dựa vào metric của agent để kết luận dữ liệu ổn.

### Nếu có thêm thời gian

Tôi sẽ thêm một schema validation chạy ngay sau `build_clean_dataframe`, kiểm tra kiểu dữ liệu từng cột, ràng buộc `summary_chars >= MIN_SUMMARY_CHARS`, `paper_id` unique và `published` parse được — rồi ghi kết quả ra `data/quality/` như một artifact riêng. Hiện các ràng buộc này nằm rải rác dạng `continue` bên trong vòng lặp: record xấu bị loại im lặng, không để lại dấu vết. Đo cải thiện bằng cách chạy validation trên corrupted dataset: nếu nó chỉ ra đúng số dòng và đúng cột bị hỏng khớp với `corruption_log.json`, tức là pipeline đã tự phát hiện được lỗi trước khi người dùng nhận câu trả lời sai.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu; phần chưa có số liệu tôi ghi rõ là "chưa có".
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng — cụ thể, `script/run_phase1.py` chưa chạy trọn vẹn và tôi đã nêu rõ ở mục 4 và mục 6.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Huy Hoàng
**Ngày xác nhận:** 2026-08-06
