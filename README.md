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

Agent thật dùng Ollama đã cài và model có khả năng tool calling:

```bash
ollama pull qwen2.5:7b
ollama list
python agent.py --mode ollama --model qwen2.5:7b --prompt-version v2 --log logs/live.jsonl
```

Sau khi cài Ollama theo hướng dẫn chính thức, bảo đảm dịch vụ đang chạy và `ollama list` hiển thị model vừa tải. Nếu server chưa chạy, mở một terminal riêng chạy `ollama serve` rồi trở lại terminal mã nguồn.

Nhánh này chưa được chạy với model thật trong môi trường biên soạn. Test nhánh này dùng phản hồi model giả lập; không chứng minh model thật tự chọn tool. Xem [API Ollama](https://docs.ollama.com/api/chat) và [tool calling](https://docs.ollama.com/capabilities/tool-calling). Cài/chạy Ollama theo hướng dẫn chính thức, kiểm tra endpoint mặc định `http://127.0.0.1:11434`. Có thể dùng `--base-url` hoặc `LLM_BASE_URL`, `--model` hoặc `LLM_MODEL`. Không kế thừa cơ chế `.env` của #48.

Model đề xuất `read_document`; Python kiểm tra tên và đối số rỗng, thực thi tool với file `--source`, rồi gửi nội dung về model. Giới hạn 4 lượt model, timeout 60 giây mỗi request. Một model_end success chỉ xác nhận đã nhận message từ API, không xác nhận tool hợp lệ hay output đúng. Model không gọi tool, gọi tool lạ, không có output hoặc hết lượt đều làm run lỗi. Thành công kỹ thuật không bảo đảm tóm tắt đúng nghĩa hoặc đúng ba ý; hãy đối chiếu nguồn. Dữ liệu nguồn được gửi đến endpoint bạn chọn.

Bộ test hiện tại có 29 test; bao gồm lỗi tool/model ngoài dự kiến, lỗi ghi log tạm thời, schema thiếu trường, metadata bị ghi đè và phản hồi HTTP giả lập. Toàn bộ phần model dùng giả lập.

Giới hạn: logger cho tiến trình tuần tự, chưa có khóa liên tiến trình, xoay vòng, retry, bảo đảm sau crash hay báo động. Run chỉ có `run_start` có thể bị ngắt, chưa thể gọi là thành công. Lỗi ghi log được đưa ra ngoài thay vì âm thầm thành công. Logger chỉ cho thêm tool, step, duration_ms, error_code và không cho ghi đè metadata. Nội dung bí mật vẫn có thể nằm trong giá trị metadata do người gọi tự cung cấp; dùng nhãn không riêng tư; không cam kết che mọi bí mật khi mở rộng schema. Prompt version là nhãn của PROMPTS trong code; khi sửa prompt hãy đổi nhãn và quản lý commit.

Repository: https://github.com/nguyenhoangtrungg/aiguru_agent_logging_demo. Chạy `git pull --ff-only` trong thư mục repository để cập nhật mã. Không ghi đè log cũ; chọn tên mới khi chạy lại demo.

## Log chạy mẫu để đối chiếu

[examples/five-runs.jsonl](examples/five-runs.jsonl) là log từ một lần thực thi demo: 5 UUID, 20 sự kiện, 3 success, 2 error. [examples/errors.jsonl](examples/errors.jsonl) là stdout của script lọc trên log đó. UUID và thời lượng thay đổi khi tự chạy; đối chiếu cấu trúc và số trạng thái.

```bash
python filter_errors.py examples/five-runs.jsonl
```
