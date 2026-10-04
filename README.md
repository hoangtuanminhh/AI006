# Lotus Fin AI006 — Repayment & Stress Simulation

## Tổng quan
Module **AI006** chịu trách nhiệm tính toán lịch trả nợ tất định (Deterministic Repayment Schedule) và kiểm tra sức chịu đựng tài chính (Stress Test) cho các khoản vay SME.

Tuân thủ nghiêm ngặt chính sách kiến trúc:
- **Tất định (Deterministic):** Mọi tính toán tài chính sử dụng `Decimal` chuẩn xác, không dùng float để tránh sai số.
- **Mô phỏng (Simulation):** Tất cả đầu ra luôn được gắn cờ `data_mode = 'simulation'`. Không ghi đè hay tạo trực tiếp bút toán tài chính trên Frappe ERPNext.
- **AI Grounding:** AI chỉ đóng vai trò phân tích, giải thích kết quả tính toán tất định, không "bịa" số liệu.

## Cấu trúc thư mục
- `models.py`: Định nghĩa các cấu trúc dữ liệu, enum (LoanTerms, StressScenarioParams, ...).
- `engine.py`: Bộ máy tính toán lịch trả nợ (PMT, Dư nợ giảm dần, Lãi phẳng, Bullet).
- `stress.py`: Bộ máy Stress Test tạo các kịch bản so sánh (Shock lãi suất, Trả trước hạn, Kéo dài kỳ hạn).
- `ai_advisor.py`: Sinh giải thích ngôn ngữ tự nhiên từ kết quả tất định.
- `service.py`: Các Frappe API endpoint (`@frappe.whitelist()`) để frontend/chatbot gọi.
- `test_ai006.py`: Unit test.

## Hướng dẫn sử dụng
Có thể gọi trực tiếp thông qua Frappe API hoặc Python.

### Python API
```python
from decimal import Decimal
from lotus_fin.AI006 import LoanTerms, RepaymentEngine, AmortizationMethod

terms = LoanTerms(
    principal=Decimal("1000000000"),
    annual_rate=Decimal("0.10"),
    term_months=12,
    amortization_method=AmortizationMethod.EQUAL_INSTALLMENT
)
engine = RepaymentEngine()
result = engine.calculate_schedule(terms)
```

### Frappe REST API
- `lotus_fin.AI006.service.calculate_repayment_schedule`
- `lotus_fin.AI006.service.run_stress_test`
