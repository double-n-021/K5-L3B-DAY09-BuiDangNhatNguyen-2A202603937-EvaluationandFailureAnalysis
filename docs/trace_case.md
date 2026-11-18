# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11
python -m lab9.trace_case --shape fixed --claim C-014 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case phân tích chi tiết: `seeded_regression C-014@11`

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11` (trên eval set `v1`, đối chiếu cùng điều kiện với `fixed C-014@11`) |
| Triệu chứng | `lab8 grader` báo `FAIL (proposal_mismatch)` (và `RefundAmountCorrect` + `ReplyMatchesLedger` ở M3 đều báo `FAIL`): Event `6` `reply` nói `"Dạ, LogiX đã hoàn 120.000đ cho đơn O-515."`, nhưng sổ cái `refund_ledger` thực tế chỉ ghi nhận `refund_vnd = 90000` (thấp hơn nhãn chuẩn `label.refund_vnd = 120000` đúng `30.000đ`). |
| Bước sai đầu tiên | Event `5` · `proposal` · `{"amount_vnd": 120000}` |
| Vì sao là bước *đầu tiên* | Event `1` (`handoff`: uỷ quyền đúng `owner_order_only`), Event `2` (`investigator`: đọc đúng đơn `O-515` trễ 5 ngày, `damage_verified=true`), Event `3` (`quote`: tính đúng tổng mức bồi thường tối đa `amount_vnd=150000` từ `max(30000, 150000)`), và Event `4` (`refund_history`: chỉ đọc lịch sử `refunded_vnd=30000` mà chưa làm sai trạng thái — giống `honest_refactor`) đều đúng sự thật. Đúng tại Event `5`, Agent tự lấy `150000 - 30000 = 120000` trước khi gọi `issue_refund`, khiến Host trừ `30000` lần thứ hai còn `90000`. |
| Failure mode | `FM-05` (`pre_deducted` — trừ trước khi được duyệt), kéo theo hệ quả `FM-08` (`misreport` ở Event `6` do báo khách `120.000đ` trong khi ledger chỉ chi `90.000đ`). |
| Đối chứng | Trên `fixed C-014@11`: sau Event `3` (`quote: {"amount_vnd": 150000}`), Agent không tự trừ lịch sử mà gửi nguyên `proposal = 150000` sang `issue_refund`; Host trừ lịch sử `30000` đúng một lần nên `ledger.refund_vnd = 120000` khớp `label`, và Event `4` (`reply`) báo chuẩn xác `"Dạ, LogiX đã hoàn 120.000đ cho đơn O-515."`. |
| Regression test | `tests/test_lab9_trace_case.py::test_c014_no_double_deduction` — kiểm tra trực tiếp trên `lab9.trace_case.investigate`: fail trên biến thể lỗi `seeded_regression` (`snapshot["refund_vnd"] == 90000 != 120000`, xuất hiện event `proposal: {"amount_vnd": 120000}`) và pass hoàn toàn trên `fixed` (`snapshot["refund_vnd"] == 120000`, `lab8_pass is True`). |
| Chưa chắc chắn | Chỉ đọc riêng một trace `C-014@11` thì xác định được hành vi tự trừ trước tại Event `5`, nhưng chưa thể kết luận lỗi do prompt hướng dẫn Agent hiểu sai hợp đồng của tool `issue_refund` hay do phép trừ viết cứng trong code điều phối nếu chưa kiểm tra chéo sang các đơn có `prior_refunds` khác (`C-013`, `C-105`, `C-106`) hoặc đọc mã nguồn Agent. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai (`C-014@11` nói hoàn `120.000đ` nhưng thực chi chỉ `90.000đ`; `C-008@11` nói hoàn `35.000đ` nhưng thực chi `20.000đ`).
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: đã thêm tại `src/tests/test_lab9_trace_case.py`.
