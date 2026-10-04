"""
Lotus Fin AI006 — Deterministic Repayment Schedule Engine.
Implements 4 amortization methods with strict Decimal arithmetic.
Supports grace period, fee calculation, and cashflow impact projection.

Supported methods:
1. EQUAL_INSTALLMENT (PMT / Trả góp đều)
2. EQUAL_PRINCIPAL (Gốc đều, lãi giảm dần)
3. FLAT_RATE (Lãi phẳng trên gốc ban đầu)
4. BULLET (Trả lãi hàng kỳ, gốc cuối kỳ)
"""

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Tuple
import copy

from .models import (
    LoanTerms,
    PaymentRecord,
    RepaymentScheduleResult,
    AmortizationMethod,
    PaymentFrequency
)

# Constant for monetary rounding
MONEY = Decimal("0.01")
RATE_PREC = Decimal("0.00000001")


def _add_months(base_date: datetime, months: int) -> datetime:
    """Cộng thêm N tháng vào ngày gốc, xử lý tràn ngày cuối tháng."""
    month = base_date.month - 1 + months
    year = base_date.year + month // 12
    month = month % 12 + 1
    day = min(base_date.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                               31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return datetime(year, month, day)


class RepaymentEngine:
    """
    Bộ máy tính toán lịch trả nợ tất định (Deterministic Repayment Schedule Engine).
    Tất cả phép tính sử dụng Decimal với ROUND_HALF_UP.
    """

    def calculate_schedule(self, loan_terms: LoanTerms) -> RepaymentScheduleResult:
        """
        Điểm vào chính: Tính toán lịch trả nợ hoàn chỉnh dựa trên LoanTerms.
        Tự động chọn phương pháp phân bổ phù hợp.
        """
        method = loan_terms.amortization_method
        principal = loan_terms.principal
        annual_rate = loan_terms.annual_rate
        term = loan_terms.term_months
        grace = loan_terms.grace_period_months
        start_date = datetime.strptime(loan_terms.start_date, "%Y-%m-%d")

        # Tính lãi suất theo kỳ thanh toán
        if loan_terms.payment_frequency == PaymentFrequency.QUARTERLY:
            periods_per_year = 4
            period_rate = (annual_rate / Decimal("4")).quantize(RATE_PREC, rounding=ROUND_HALF_UP)
            total_periods = term // 3
        else:
            periods_per_year = 12
            period_rate = (annual_rate / Decimal("12")).quantize(RATE_PREC, rounding=ROUND_HALF_UP)
            total_periods = term

        # Tính toán lịch theo phương pháp
        if method == AmortizationMethod.EQUAL_INSTALLMENT:
            schedule = self._calc_equal_installment(principal, period_rate, total_periods, start_date, loan_terms.payment_frequency, grace)
        elif method == AmortizationMethod.EQUAL_PRINCIPAL:
            schedule = self._calc_equal_principal(principal, period_rate, total_periods, start_date, loan_terms.payment_frequency, grace)
        elif method == AmortizationMethod.FLAT_RATE:
            schedule = self._calc_flat_rate(principal, annual_rate, total_periods, start_date, loan_terms.payment_frequency, periods_per_year, grace)
        elif method == AmortizationMethod.BULLET:
            schedule = self._calc_bullet(principal, period_rate, total_periods, start_date, loan_terms.payment_frequency)
        else:
            schedule = self._calc_equal_installment(principal, period_rate, total_periods, start_date, loan_terms.payment_frequency, grace)

        # Tính phí
        fees = self._calculate_fees(loan_terms)

        # Tổng hợp summary
        summary = self._build_summary(schedule, fees, loan_terms, total_periods)

        # Tạo cashflow impact
        cashflow_impact = self._build_cashflow_impact(schedule, fees, loan_terms)

        # Assumptions & limitations
        assumptions = [
            f"Phương pháp phân bổ: {method.value}.",
            f"Lãi suất cố định {float(annual_rate * 100):.2f}%/năm trong suốt kỳ vay.",
            f"Tần suất thanh toán: {loan_terms.payment_frequency.value}.",
            "Không có sự kiện vỡ nợ (default) hoặc tái cấu trúc nợ trong kịch bản cơ sở."
        ]
        if grace > 0:
            assumptions.append(f"Ân hạn gốc {grace} tháng đầu: chỉ trả lãi, chưa trả gốc.")

        limitations = [
            "Lịch trả nợ mang cờ data_mode = 'simulation' và không phải cam kết hợp đồng.",
            "Lãi suất thả nổi (FLOATING) được giả lập bằng lãi suất cố định tại thời điểm tính toán."
        ]

        return RepaymentScheduleResult(
            schedule_id=f"sched_{loan_terms.scenario_id or 'base'}",
            scenario_id=loan_terms.scenario_id,
            data_mode="simulation",
            loan_terms={
                "principal": float(principal),
                "currency": loan_terms.currency,
                "annual_rate": float(annual_rate),
                "rate_type": loan_terms.rate_type,
                "term_months": loan_terms.term_months,
                "amortization_method": method.value,
                "payment_frequency": loan_terms.payment_frequency.value,
                "grace_period_months": grace,
                "start_date": loan_terms.start_date
            },
            payment_schedule=[self._record_to_dict(r) for r in schedule],
            summary=summary,
            cashflow_impact=cashflow_impact,
            fees=fees,
            assumptions=assumptions,
            limitations=limitations
        )

    # ------------------------------------------------------------------
    # PHƯƠNG PHÁP 1: TRẢ GÓP ĐỀU (EQUAL INSTALLMENT / PMT)
    # ------------------------------------------------------------------
    def _calc_equal_installment(
        self, principal: Decimal, period_rate: Decimal, total_periods: int,
        start_date: datetime, freq: PaymentFrequency, grace: int = 0
    ) -> List[PaymentRecord]:
        """
        Công thức PMT: payment = P × r(1+r)^n / [(1+r)^n − 1]
        Trong kỳ ân hạn: chỉ trả lãi, gốc lùi lại.
        """
        records: List[PaymentRecord] = []
        balance = principal
        cum_principal = Decimal("0")
        cum_interest = Decimal("0")
        months_per_period = 3 if freq == PaymentFrequency.QUARTERLY else 1

        # Tính số kỳ trả gốc thực tế (sau ân hạn)
        grace_periods = grace // months_per_period if grace > 0 else 0
        repayment_periods = total_periods - grace_periods

        # PMT cho phần trả gốc sau ân hạn
        if period_rate > Decimal("0") and repayment_periods > 0:
            r = period_rate
            n = repayment_periods
            pmt = (principal * r * (Decimal("1") + r) ** n / ((Decimal("1") + r) ** n - Decimal("1"))).quantize(MONEY, rounding=ROUND_HALF_UP)
        elif repayment_periods > 0:
            pmt = (principal / Decimal(str(repayment_periods))).quantize(MONEY, rounding=ROUND_HALF_UP)
        else:
            pmt = Decimal("0")

        for period in range(1, total_periods + 1):
            pmt_date = _add_months(start_date, period * months_per_period)
            interest = (balance * period_rate).quantize(MONEY, rounding=ROUND_HALF_UP)

            if period <= grace_periods:
                # Kỳ ân hạn: chỉ trả lãi
                prin_pay = Decimal("0")
                total_pay = interest
            elif period == total_periods:
                # Kỳ cuối: trả hết dư nợ còn lại
                prin_pay = balance
                total_pay = (prin_pay + interest).quantize(MONEY, rounding=ROUND_HALF_UP)
            else:
                prin_pay = (pmt - interest).quantize(MONEY, rounding=ROUND_HALF_UP)
                prin_pay = min(prin_pay, balance)  # Không trả quá dư nợ
                total_pay = (prin_pay + interest).quantize(MONEY, rounding=ROUND_HALF_UP)

            new_balance = (balance - prin_pay).quantize(MONEY, rounding=ROUND_HALF_UP)
            cum_principal += prin_pay
            cum_interest += interest

            records.append(PaymentRecord(
                period=period,
                payment_date=pmt_date.strftime("%Y-%m-%d"),
                opening_balance=float(balance.quantize(MONEY)),
                principal_payment=float(prin_pay.quantize(MONEY)),
                interest_payment=float(interest.quantize(MONEY)),
                total_payment=float(total_pay.quantize(MONEY)),
                closing_balance=float(new_balance.quantize(MONEY)),
                cumulative_principal=float(cum_principal.quantize(MONEY)),
                cumulative_interest=float(cum_interest.quantize(MONEY))
            ))
            balance = new_balance

        return records

    # ------------------------------------------------------------------
    # PHƯƠNG PHÁP 2: GỐC ĐỀU, LÃI GIẢM DẦN (EQUAL PRINCIPAL)
    # ------------------------------------------------------------------
    def _calc_equal_principal(
        self, principal: Decimal, period_rate: Decimal, total_periods: int,
        start_date: datetime, freq: PaymentFrequency, grace: int = 0
    ) -> List[PaymentRecord]:
        """Trả gốc đều mỗi kỳ = P / n_repayment. Lãi tính trên dư nợ giảm dần."""
        records: List[PaymentRecord] = []
        balance = principal
        cum_principal = Decimal("0")
        cum_interest = Decimal("0")
        months_per_period = 3 if freq == PaymentFrequency.QUARTERLY else 1
        grace_periods = grace // months_per_period if grace > 0 else 0
        repayment_periods = total_periods - grace_periods
        fixed_principal = (principal / Decimal(str(repayment_periods))).quantize(MONEY, rounding=ROUND_HALF_UP) if repayment_periods > 0 else Decimal("0")

        for period in range(1, total_periods + 1):
            pmt_date = _add_months(start_date, period * months_per_period)
            interest = (balance * period_rate).quantize(MONEY, rounding=ROUND_HALF_UP)

            if period <= grace_periods:
                prin_pay = Decimal("0")
            elif period == total_periods:
                prin_pay = balance  # Kỳ cuối trả hết
            else:
                prin_pay = min(fixed_principal, balance)

            total_pay = (prin_pay + interest).quantize(MONEY, rounding=ROUND_HALF_UP)
            new_balance = (balance - prin_pay).quantize(MONEY, rounding=ROUND_HALF_UP)
            cum_principal += prin_pay
            cum_interest += interest

            records.append(PaymentRecord(
                period=period,
                payment_date=pmt_date.strftime("%Y-%m-%d"),
                opening_balance=float(balance.quantize(MONEY)),
                principal_payment=float(prin_pay.quantize(MONEY)),
                interest_payment=float(interest.quantize(MONEY)),
                total_payment=float(total_pay.quantize(MONEY)),
                closing_balance=float(new_balance.quantize(MONEY)),
                cumulative_principal=float(cum_principal.quantize(MONEY)),
                cumulative_interest=float(cum_interest.quantize(MONEY))
            ))
            balance = new_balance

        return records

    # ------------------------------------------------------------------
    # PHƯƠNG PHÁP 3: LÃI PHẲNG (FLAT RATE)
    # ------------------------------------------------------------------
    def _calc_flat_rate(
        self, principal: Decimal, annual_rate: Decimal, total_periods: int,
        start_date: datetime, freq: PaymentFrequency, periods_per_year: int, grace: int = 0
    ) -> List[PaymentRecord]:
        """
        Lãi phẳng: Lãi mỗi kỳ = Principal × AnnualRate / PeriodsPerYear (cố định).
        Gốc mỗi kỳ = Principal / TotalRepaymentPeriods.
        ⚠️ Chi phí thực tế cao hơn lãi suất danh nghĩa vì lãi tính trên gốc ban đầu.
        """
        records: List[PaymentRecord] = []
        balance = principal
        cum_principal = Decimal("0")
        cum_interest = Decimal("0")
        months_per_period = 3 if freq == PaymentFrequency.QUARTERLY else 1
        grace_periods = grace // months_per_period if grace > 0 else 0
        repayment_periods = total_periods - grace_periods

        flat_interest = (principal * annual_rate / Decimal(str(periods_per_year))).quantize(MONEY, rounding=ROUND_HALF_UP)
        fixed_principal = (principal / Decimal(str(repayment_periods))).quantize(MONEY, rounding=ROUND_HALF_UP) if repayment_periods > 0 else Decimal("0")

        for period in range(1, total_periods + 1):
            pmt_date = _add_months(start_date, period * months_per_period)

            if period <= grace_periods:
                prin_pay = Decimal("0")
            elif period == total_periods:
                prin_pay = balance
            else:
                prin_pay = min(fixed_principal, balance)

            total_pay = (prin_pay + flat_interest).quantize(MONEY, rounding=ROUND_HALF_UP)
            new_balance = (balance - prin_pay).quantize(MONEY, rounding=ROUND_HALF_UP)
            cum_principal += prin_pay
            cum_interest += flat_interest

            records.append(PaymentRecord(
                period=period,
                payment_date=pmt_date.strftime("%Y-%m-%d"),
                opening_balance=float(balance.quantize(MONEY)),
                principal_payment=float(prin_pay.quantize(MONEY)),
                interest_payment=float(flat_interest.quantize(MONEY)),
                total_payment=float(total_pay.quantize(MONEY)),
                closing_balance=float(new_balance.quantize(MONEY)),
                cumulative_principal=float(cum_principal.quantize(MONEY)),
                cumulative_interest=float(cum_interest.quantize(MONEY))
            ))
            balance = new_balance

        return records

    # ------------------------------------------------------------------
    # PHƯƠNG PHÁP 4: BULLET (TRẢ GỐC CUỐI KỲ)
    # ------------------------------------------------------------------
    def _calc_bullet(
        self, principal: Decimal, period_rate: Decimal, total_periods: int,
        start_date: datetime, freq: PaymentFrequency
    ) -> List[PaymentRecord]:
        """Trả lãi hàng kỳ, trả toàn bộ gốc vào kỳ cuối cùng."""
        records: List[PaymentRecord] = []
        balance = principal
        cum_principal = Decimal("0")
        cum_interest = Decimal("0")
        months_per_period = 3 if freq == PaymentFrequency.QUARTERLY else 1

        for period in range(1, total_periods + 1):
            pmt_date = _add_months(start_date, period * months_per_period)
            interest = (balance * period_rate).quantize(MONEY, rounding=ROUND_HALF_UP)

            if period == total_periods:
                prin_pay = balance
            else:
                prin_pay = Decimal("0")

            total_pay = (prin_pay + interest).quantize(MONEY, rounding=ROUND_HALF_UP)
            new_balance = (balance - prin_pay).quantize(MONEY, rounding=ROUND_HALF_UP)
            cum_principal += prin_pay
            cum_interest += interest

            records.append(PaymentRecord(
                period=period,
                payment_date=pmt_date.strftime("%Y-%m-%d"),
                opening_balance=float(balance.quantize(MONEY)),
                principal_payment=float(prin_pay.quantize(MONEY)),
                interest_payment=float(interest.quantize(MONEY)),
                total_payment=float(total_pay.quantize(MONEY)),
                closing_balance=float(new_balance.quantize(MONEY)),
                cumulative_principal=float(cum_principal.quantize(MONEY)),
                cumulative_interest=float(cum_interest.quantize(MONEY))
            ))
            balance = new_balance

        return records

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def _calculate_fees(self, lt: LoanTerms) -> Dict[str, Any]:
        """Tính phí xử lý hồ sơ và phí bảo hiểm."""
        processing_fee = (lt.principal * lt.processing_fee_pct).quantize(MONEY, rounding=ROUND_HALF_UP)
        insurance_fee = (lt.principal * lt.insurance_fee_pct).quantize(MONEY, rounding=ROUND_HALF_UP)
        total_fees = (processing_fee + insurance_fee).quantize(MONEY, rounding=ROUND_HALF_UP)
        return {
            "processing_fee": float(processing_fee),
            "insurance_fee": float(insurance_fee),
            "total_fees": float(total_fees),
            "fee_timing": lt.fee_timing
        }

    def _build_summary(self, schedule: List[PaymentRecord], fees: Dict, lt: LoanTerms, total_periods: int) -> Dict[str, Any]:
        """Tổng hợp chỉ số tổng quan từ lịch trả nợ."""
        if not schedule:
            return {}
        total_interest = Decimal(str(schedule[-1].cumulative_interest))
        total_principal = Decimal(str(lt.principal))
        total_fees_dec = Decimal(str(fees["total_fees"]))
        total_repayment = (total_principal + total_interest + total_fees_dec).quantize(MONEY, rounding=ROUND_HALF_UP)

        payments = [Decimal(str(r.total_payment)) for r in schedule]
        avg_payment = (sum(payments) / Decimal(str(len(payments)))).quantize(MONEY, rounding=ROUND_HALF_UP)
        interest_to_principal = (total_interest / total_principal).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if total_principal > 0 else Decimal("0")

        return {
            "principal": float(total_principal),
            "total_interest": float(total_interest),
            "total_fees": float(total_fees_dec),
            "total_repayment": float(total_repayment),
            "total_periods": total_periods,
            "average_monthly_payment": float(avg_payment),
            "first_payment": float(payments[0]) if payments else 0.0,
            "last_payment": float(payments[-1]) if payments else 0.0,
            "interest_to_principal_ratio": float(interest_to_principal),
            "currency": lt.currency
        }

    def _build_cashflow_impact(self, schedule: List[PaymentRecord], fees: Dict, lt: LoanTerms) -> List[Dict[str, Any]]:
        """Chuyển đổi lịch trả nợ thành chuỗi tác động dòng tiền để tích hợp với AI-F002/F004."""
        impact = []
        # Phí thu trước (nếu UPFRONT)
        if lt.fee_timing == "UPFRONT" and fees["total_fees"] > 0:
            impact.append({
                "period": 0,
                "date": lt.start_date,
                "type": "FEE_OUTFLOW",
                "amount": -fees["total_fees"],
                "description": "Phí xử lý hồ sơ + Bảo hiểm tín dụng (thu trước)"
            })
        # Tiền giải ngân nhận vào
        impact.append({
            "period": 0,
            "date": lt.start_date,
            "type": "LOAN_INFLOW",
            "amount": float(lt.principal),
            "description": "Nhận giải ngân khoản vay"
        })
        # Các kỳ trả nợ
        for r in schedule:
            impact.append({
                "period": r.period,
                "date": r.payment_date,
                "type": "REPAYMENT_OUTFLOW",
                "amount": -r.total_payment,
                "principal_portion": -r.principal_payment,
                "interest_portion": -r.interest_payment,
                "description": f"Kỳ {r.period}: Trả gốc {r.principal_payment:,.0f} + Lãi {r.interest_payment:,.0f}"
            })
        return impact

    def _record_to_dict(self, r: PaymentRecord) -> Dict[str, Any]:
        return {
            "period": r.period,
            "payment_date": r.payment_date,
            "opening_balance": r.opening_balance,
            "principal_payment": r.principal_payment,
            "interest_payment": r.interest_payment,
            "total_payment": r.total_payment,
            "closing_balance": r.closing_balance,
            "cumulative_principal": r.cumulative_principal,
            "cumulative_interest": r.cumulative_interest
        }
