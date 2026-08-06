# Member Role Report — Lâm Việt Hoàng

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Lâm Việt Hoàng |
| MSSV | 2A202601067 |
| Khóa/Lớp | K3 — Day 10 |
| Tên nhóm | Crossref Scholarly RAG |
| Vai trò chính | OpenRouter LLM integration và RAG chatbot agent |
| Repository | K3_Day10_Data-Pipeline-Data-Observability-Luc-Lac-Vang |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
|---|---|---|---|---|
| Provider wrapper, agent tools, answer extraction và fallback | src/retrieval/llm.py; src/retrieval/agent.py; src/retrieval/qa.py | Câu hỏi người dùng và retrieved contexts từ LocalEmbeddingIndex | Câu trả lời factual, answer mode, paper IDs và evidence context | Hoàn thành |

Tôi nhận ownership phần việc trên và bảo đảm output được các module sau dùng theo contract đã thống nhất.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
|---|---|---|
| Cung cấp answer cho evaluation và evidence để report/chatbot hiển thị | Pipeline tích hợp của nhóm | Artifact và report có thể tái hiện; pytest đã pass |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
|---|---|---|---|
| Triển khai phần việc sở hữu | src/retrieval/llm.py; src/retrieval/agent.py; src/retrieval/qa.py | Câu trả lời factual, answer mode, paper IDs và evidence context | uv run pytest -q |
| Tích hợp với pipeline | data/results và data/reports | OpenRouter agent trả lời 10/10 samples, heuristic fallback bằng 0; judge accuracy 0.9. | Chạy phase1 và corruption flow |

Output cụ thể: OpenRouter agent trả lời 10/10 samples, heuristic fallback bằng 0; judge accuracy 0.9.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Phần việc của tôi phải đảm bảo provider wrapper, agent tools, answer extraction và fallback hoạt động theo contract và tạo evidence có thể kiểm chứng cho các bước kế tiếp.

### Cách triển khai

Agent dùng semantic_search_papers và lookup_paper. Tool trả title, authors, published, publisher, score và chunk content; system prompt giới hạn agent dùng evidence tool. QA fallback trích metadata cho các câu field-based.

### Input, output và contract

| Thành phần | Mô tả |
|---|---|
| Input | Câu hỏi người dùng và retrieved contexts từ LocalEmbeddingIndex |
| Output | Câu trả lời factual, answer mode, paper IDs và evidence context |
| Module phụ thuộc | Core config, utils và các artifact của bước trước |
| Module sử dụng output | Các bước retrieval, evaluation, observability hoặc pipeline tích hợp |
| Điều kiện lỗi cần xử lý | Missing data, provider/index lỗi hoặc contract artifact không thống nhất |

### Cách xác minh

~~~powershell
uv run pytest -q
uv run python script/run_phase1.py --provider openrouter --model openai/gpt-4o-mini
~~~

- **Kết quả mong đợi:** artifact được tạo đúng schema và pipeline không dùng secret trong report.
- **Kết quả thực tế:** OpenRouter agent trả lời 10/10 samples, heuristic fallback bằng 0; judge accuracy 0.9.
- **Artifact/log:** data/results, data/quality hoặc data/reports tương ứng với module.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần chọn cách triển khai vừa đúng contract vừa có thể tái hiện.
- **Các phương án đã cân nhắc:** Giữ cách đơn giản một artifact/document; hoặc bổ sung validation, lineage và evidence theo module.
- **Phương án đã chọn:** Chọn agent thật có fallback thay vì chỉ heuristic. Điều này đo được chất lượng RAG với provider cấu hình nhưng vẫn không làm pipeline gãy khi LLM lỗi.
- **Lý do:** Ưu tiên correctness, reproducibility và khả năng audit hơn tối ưu ngắn hạn.
- **Bằng chứng quyết định phù hợp:** OpenRouter agent trả lời 10/10 samples, heuristic fallback bằng 0; judge accuracy 0.9.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Một câu authors trả thêm tác giả từ paper liên quan. Nguyên nhân là agent nhận nhiều context và ưu tiên giải thích hơn trả một fact.
- **Lệnh hoặc bước tái hiện:** Chạy phase1 hoặc corruption flow trên artifact tương ứng.
- **Nguyên nhân gốc:** Contract ban đầu chưa bao quát đầy đủ dữ liệu/LLM/index ở edge case.
- **Cách xử lý:** Bổ sung validation và xử lý theo đúng owner module, giữ raw artifact hoặc evidence để kiểm tra lại.
- **Cách xác minh sau khi sửa:** uv run pytest -q; kết quả 11 passed.
- **Điều học được:** Lỗi tích hợp thường xuất phát từ contract giữa module, không chỉ một dòng code lỗi.

## 7. Hiểu biết về luồng end-to-end

1. **Crossref đến vector index:** API response được lưu raw, parse thành records, clean thành bảng chuẩn; text_for_embedding được chunk, embed bằng MiniLM và lưu ChromaDB.
2. **Evaluation set và document IDs:** Ground truth được copy từ clean data; document ID kiểm tra paper đúng có trong top-k, còn answer được đo bằng F1 và LLM judge.
3. **Quality và freshness:** Quality kiểm completeness/uniqueness/validity ở thời điểm dữ liệu; freshness đo tuổi publication và missing dates. Hai loại signal không thay thế nhau.
4. **Cùng frozen set:** Nếu đổi câu hỏi giữa baseline/corrupted/repaired thì metric không còn cùng điều kiện, nên không thể quy thay đổi cho corruption hay repair.
5. **Repair thành công:** Repaired phải trở về clean contract từ raw source, quality pass và dùng cùng frozen hash; answer metric cần được diễn giải thêm vì LLM có biến động wording.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
|---|---:|---:|---:|---|
| retrieval_hit_rate | 1.0000 | 1.0000 | 1.0000 | Judge cao nhưng F1 thấp cho thấy câu trả lời đúng về nghĩa vẫn có thể bị metric lexical phạt. |
| mean_token_f1 | 0.1635 | 0.1508 | 0.1538 | Corruption giảm 0.0127; repair phục hồi một phần. |
| judge_accuracy | 0.9000 | 0.9000 | 0.9000 | 9/10 câu được judge chấp nhận. |
| mean_judge_score | 4.80/5 | 4.80/5 | 4.80/5 | Judge nhìn ngữ nghĩa nên cao hơn F1. |
| Quality checks | pass | fail | pass | Corrupted có 1 duplicate và 198 rows. |
| Freshness status | false | false | false | Baseline có 172 stale rows và 6 missing dates. |

### Kết luận từ số liệu

1. Duplicate/blank/stale/noise corruption → corrupted quality fail và F1 giảm từ 0.1635 xuống 0.1508 → evidence cho thấy data defect đã có downstream signal.
2. Repair từ raw records → rows và uniqueness quay về baseline → F1 tăng lên 0.1538, nhưng chưa bằng baseline do answer wording của LLM.

Corruption ảnh hưởng rõ nhất đến quality (duplicate khiến state fail) và có ảnh hưởng nhẹ đến token F1. Kết quả khác kỳ vọng là retrieval hit rate không giảm; nguyên nhân là target document vẫn ở top-k, nên không được kết luận rằng corruption đã làm retrieval suy giảm.

## 9. Điều học được và hướng cải thiện

1. Data pipeline chỉ đáng tin khi raw source, clean contract và output artifact có thể truy vết.
2. Observability phải đo cả schema/uniqueness lẫn freshness; một số liệu đơn lẻ không nói hết chất lượng.
3. Chất lượng RAG phụ thuộc vào retrieval, evidence và cách agent giới hạn câu trả lời, không chỉ model LLM.

### Nếu có thêm thời gian

Thêm answer-only format, trích paper_id bắt buộc và audit log prompt/response/latency. Hiệu quả sẽ được đo bằng held-out metrics, per-scenario comparison và report có hash/config rõ ràng.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng role và phần việc được phân công.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module phụ trách.
- [x] Các kết luận đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi thành công cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa .env, API key, token hoặc secret.
- [x] Báo cáo này được viết theo góc nhìn role cá nhân, không sao chép nguyên văn báo cáo nhóm.

**Họ và tên:** Lâm Việt Hoàng  
**Ngày xác nhận:** 2026-08-06

