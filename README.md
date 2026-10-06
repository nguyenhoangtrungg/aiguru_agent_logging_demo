# Ghi log đầy đủ cho một AI Agent - bài #49

Mã nguồn chuẩn của bài; dùng thư viện chuẩn Python, không cần key hay monitoring service để học phần log. Đã thử Ubuntu 20.04.6, Bash, Python 3.12.9. Lấy mã từ GitHub và tạo môi trường chạy theo các lệnh sau.

```bash
git clone https://github.com/nguyenhoangtrungg/aiguru_agent_logging_demo.git
cd aiguru_agent_logging_demo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python demo.py --log logs/five-runs.jsonl
python filter_errors.py logs/five-runs.jsonl
python -m unittest discover -s tests -v
```

Demo tạo file mới với 5 run giả lập (3 success, 2 error), không gọi LLM và không đánh giá prompt. Nếu file đã tồn tại, chọn tên mới bằng `--log`. Script lọc chỉ in `run_end` lỗi, tránh đếm cả `tool_end` và `run_end` cho cùng lỗi. CLI demo thoát 0 khi chạy hết kịch bản, dù kịch bản có hai lỗi có chủ đích. CLI agent thoát 1 khi ghi được run_end lỗi; lỗi cấu hình CLI dùng mã 2. Lỗi ghi log đưa LogWriteError ra ngoài với mã thoát khác 0 và có thể thiếu run_end; script lọc thoát 2 khi file hỏng/không đọc được.

Script lọc kiểm tra schema từng dòng (metadata, UUID, UTC, sequence, event/status, thời lượng, mã lỗi); chưa kiểm tra toàn bộ vòng đời như run_end lặp hoặc seq gián đoạn.

Mỗi dòng JSONL có `schema_version`, `run_id` UUID, `seq`, thời gian UTC, `mode`, `model`, `prompt_version`, `case`, `event`, `status`. Sự kiện kết thúc có `duration_ms`, `error_code`; sự kiện tool có `tool`. `duration_ms` của run bao gồm ghi log và xử lý; thời lượng tool/model cũng bao gồm chi phí ghi mốc bắt đầu, không gồm chi phí ghi mốc kết thúc; không cộng các khoảng lồng nhau. Không lưu nội dung nguồn, prompt, output hoặc exception thô vào log. Kết quả tóm tắt được in ra stdout ở CLI agent; hãy dùng dữ liệu không riêng tư.

Chạy riêng một lần (ghi nối tiếp, UUID mới):

```bash
python agent.py --source samples/source.txt --log logs/manual.jsonl --prompt-version v2
```

Agent dùng OpenRouter: tạo `.env` riêng (Git bỏ qua file này) với `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` và tùy chọn `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`. Dùng model hỗ trợ tool calling. Có thể đọc cấu hình sẵn có bằng `--env-file /path/to/.env` mà không sao chép key.

```bash
python agent.py --mode openrouter --env-file .env --prompt-version v2 --log logs/live.jsonl
echo $?
python read_run.py logs/live.jsonl
python filter_errors.py logs/live.jsonl
```

CLI ưu tiên --model/--base-url, sau đó biến môi trường, sau đó giá trị từ file env. File env là các dòng KEY=value, không thực thi shell. Ứng dụng dùng thư viện chuẩn; không cần SDK. Nội dung nguồn được gửi đến OpenRouter và nhà cung cấp model. Xem [tool calling](https://openrouter.ai/docs/guides/features/tool-calling).

Model đề xuất read_document; Python giải mã arguments JSON, yêu cầu đối số rỗng và call ID hợp lệ, chạy tool rồi gửi kết quả kèm tool_call_id. Tối đa 4 lượt model, timeout 60 giây mỗi request. Request sử dụng Authorization Bearer và endpoint /chat/completions. Key không được ghi vào log. Thành công kỹ thuật không bảo đảm tóm tắt đúng nghĩa; đối chiếu đầu ra với nguồn. Run có một tool và hai lượt model có 8 sự kiện; demo giả lập có 4 sự kiện mỗi run.

Bộ test hiện tại có 29 test; bao gồm lỗi tool/model ngoài dự kiến, lỗi ghi log tạm thời, schema thiếu trường, metadata bị ghi đè và phản hồi HTTP giả lập. Toàn bộ phần model dùng giả lập.

Giới hạn: logger cho tiến trình tuần tự, chưa có khóa liên tiến trình, xoay vòng, retry, bảo đảm sau crash hay báo động. Run chỉ có `run_start` có thể bị ngắt, chưa thể gọi là thành công. Lỗi ghi log được đưa ra ngoài thay vì âm thầm thành công. Logger chỉ cho thêm tool, step, duration_ms, error_code và không cho ghi đè metadata. Nội dung bí mật vẫn có thể nằm trong giá trị metadata do người gọi tự cung cấp; dùng nhãn không riêng tư; không cam kết che mọi bí mật khi mở rộng schema. Prompt version là nhãn của PROMPTS trong code; khi sửa prompt hãy đổi nhãn và quản lý commit.

Repository: https://github.com/nguyenhoangtrungg/aiguru_agent_logging_demo. Chạy `git pull --ff-only` trong thư mục repository để cập nhật mã. Không ghi đè log cũ; chọn tên mới khi chạy lại demo.

## Log chạy mẫu để đối chiếu

[examples/five-runs.jsonl](examples/five-runs.jsonl) là log từ một lần thực thi demo: 5 UUID, 20 sự kiện, 3 success, 2 error. [examples/errors.jsonl](examples/errors.jsonl) là stdout của script lọc trên log đó. UUID và thời lượng thay đổi khi tự chạy; đối chiếu cấu trúc và số trạng thái.

```bash
python filter_errors.py examples/five-runs.jsonl
```

## Đọc các sự kiện thuộc một run

```bash
python read_run.py examples/five-runs.jsonl
```

Script in seq, event và status của run đầu: run_start, tool_start, tool_end, run_end. Có thể chọn UUID khác bằng `--run-id`.
