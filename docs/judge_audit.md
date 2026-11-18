# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | Confusion Matrix (`tp/fp/fn/tn`) | κ | Precision | Recall | Fail rate (obs -> RG) | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| `tone_ok` | 100 | `24 / 4 / 6 / 66` | `0.757` | `0.857` | `0.800` | `0.280 -> 0.300` | Đạt | dùng |
| `helpful` | 100 | `9 / 0 / 21 / 70` | `0.375` | `1.000` | `0.300` | `0.090 -> 0.300` | Không đạt (`κ < 0.6`, `R < 0.7`) | loại |

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Hành động sửa Rubric |
|---|---|---|---|---|---|
| 1 | `H-008` (`tone_ok`) | `PASS` | `FAIL` | Người đúng | `FN`: Câu trả lời xưng `"Em"` + đệm `"nha"` quá suồng sã, Judge nhầm là thân thiện. **Sửa Rubric**: Bắt buộc xưng `"LogiX"` – `"anh/chị"`, đánh `FAIL` mọi cách xưng `"em"`, `"bạn"` và trợ từ `"nha"`, `"nhé"`. |
| 2 | `H-017` (`tone_ok`) | `PASS` | `FAIL` | Người đúng | `FN`: Đầu câu có `"Dạ"` nhưng gọi khách là `"bạn ơi ... rồi nha"`. **Sửa Rubric**: Cấm gọi khách là `"bạn"` / `"bạn ơi"` dù có kính ngữ đầu câu. |
| 3 | `H-029` (`tone_ok`) | `PASS` | `FAIL` | Người đúng | `FN`: Judge chỉ nhìn `"Dạ, vui lòng chờ"` ở đầu nên bỏ sót mệnh lệnh cộc lốc `"không cần nhắn thêm"` ở cuối. **Sửa Rubric**: Chấm toàn bộ câu; đánh `FAIL` nếu có mệnh lệnh chặn khách phản hồi. |
| 4 | `H-042` (`tone_ok`) | `FAIL` | `PASS` | Người đúng | `FP`: Câu báo hoàn tiền ngắn gọn, đủ kính ngữ `"Dạ ... ạ"` và thời gian nhận tiền nhưng Judge phạt vì thiếu câu xin lỗi. **Sửa Rubric**: Xác nhận câu báo kết quả ngắn gọn, lịch sự là `PASS`, không ép buộc văn mẫu xin lỗi dài dòng (tránh `Verbosity Bias`). |
| 5 | `H-051` (`tone_ok`) | `FAIL` | `PASS` | Người đúng | `FP`: Judge phạt từ tiếng Anh `"refund"`. **Sửa Rubric**: Cho phép thuật ngữ nghiệp vụ `"refund"` trong danh sách từ vựng CSKH hợp lệ của LogiX. |
| 6 | `H-081` (`tone_ok`) | `FAIL` | `PASS` | Judge đúng | Nhiễu nhãn người: Người gán nhãn đọc nhầm ticket nên chấm `PASS` nhầm. **Hành động**: Chuẩn hóa lại nhãn chuẩn (`Gold Label Relabeling`) bằng đối chiếu chéo 2 người gán nhãn. |
| 7 | `HL-016` (`helpful`) | `PASS` | `FAIL` | Người đúng | `FN` nghiêm trọng: Văn mẫu xin lỗi rất dài và lễ phép nhưng báo hoàn `55.000đ` trong khi `ledger` chỉ ghi `35.000đ` (`FM-08`). **Hành động**: Cấm dùng `LLM Judge` chấm tiền bạc; chuyển sang `Code Grader` đọc trực tiếp `ledger` và `reply`. |
| 8 | `H-094` (`tone_ok`) | `PASS` | `FAIL` | Người đúng | `FN`: Văn bản tiếng Việt mất toàn bộ dấu (`"Da, LogiX da hoan..."`), Judge vẫn hiểu nghĩa nên cho qua. **Sửa Rubric**: Bắt buộc văn bản gửi khách phải có đầy đủ dấu tiếng Việt chuẩn, không hứa vượt quyền (`H-063`) và không dùng ký tự biểu cảm cợt nhả (`H-070`). |

## Kết luận

- **Tiêu chí bị loại và lý do**:
  - Loại bỏ hoàn toàn **`helpful`** (`judge_helpful_public.csv`) khỏi CI Gate. Ma trận nhầm lẫn `{tp: 9, fp: 0, fn: 21, tn: 70}` cho thấy `Recall = 0.300 < 0.70` và `Cohen's Kappa = 0.375 < 0.60`. Tỷ lệ lỗi quan sát của Judge này chỉ là `9%` (báo cáo ảo **91% PASS**), trong khi tỷ lệ lỗi thực tế sau hiệu chỉnh Rogan–Gladen là **`30%`**. Trong 21 ca bỏ lọt (`FN`), có 18 ca là lỗi **nói sai số tiền hoàn so với sổ cái (`FM-08`)** do Judge chỉ đọc câu chữ lễ phép (`Surface Fluency & Verbosity Bias`) mà không hề có quyền truy cập `refund_ledger`.
  - Tiêu chí **`tone_ok`** đạt cả 3 ngưỡng sàn (`κ = 0.757`, `P = 0.857`, `R = 0.800`), được phép dùng cho đánh giá giọng điệu giao tiếp sau khi cập nhật Rubric theo bảng audit và luôn báo cáo kèm tỷ lệ lỗi hiệu chỉnh Rogan–Gladen (`0.280 -> 0.300`).
- **Rủi ro còn lại**: Judge hiện chỉ được kiểm định trên dữ liệu replay đã công khai (`n = 100`); nếu sửa Rubric dựa trên chính 100 dòng này rồi chấm lại trên đó sẽ gây quá khớp (`Calibration Overfitting`). Cần thu thập và gán nhãn người độc lập trên mẫu mới để tạo tập kiểm định ẩn (`Held-out Set`) thực sự.
