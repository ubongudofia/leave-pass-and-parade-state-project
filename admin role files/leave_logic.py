from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Any
from dataclasses import dataclass

# Data structure for staff balances (current year or relevant period)
@dataclass
class LeaveBalances:
    annual_remaining: int = 0
    compassionate_used: int = 0
    casual_calendar_days: int = 0      # Total calendar days used for casual in current year
    sick_this_year: int = 0            # Non-hospitalized sick working days this calendar year
    sick_rolling_12m: int = 0          # Non-hospitalized sick working days in rolling 12 months
    terminal_granted: bool = False     # Terminal leave already granted on retirement

# Helpers
def is_low_grade(grade: int) -> bool:
    return 2 <= grade <= 6

def get_annual_entitlement(grade: int) -> int:
    return 21 if is_low_grade(grade) else 30

def get_terminal_entitlement(grade: int) -> int:
    return 42 if is_low_grade(grade) else 90

def working_days_between(
    start_date: datetime,
    end_date: datetime,
    public_holidays: List[datetime] = None
) -> int:
    if public_holidays is None:
        public_holidays = []
    if start_date > end_date:
        return 0
    current = start_date
    count = 0
    while current <= end_date:
        if current.weekday() < 5 and current not in public_holidays:
            count += 1
        current += timedelta(days=1)
    return count

def calendar_days_between(start_date: datetime, end_date: datetime) -> int:
    if start_date > end_date:
        return 0
    return (end_date - start_date).days + 1

def is_hospitalized_period(
    start_date: datetime,
    end_date: datetime,
    hospitalization_records: List[Tuple[datetime, datetime]] = None
) -> bool:
    if not hospitalization_records:
        return False
    for hosp_start, hosp_end in hospitalization_records:
        if not (end_date < hosp_start or start_date > hosp_end):
            return True
    return False

# ──────────────────────────────────────────────────────────────
# MAIN VALIDATION FUNCTION
# ──────────────────────────────────────────────────────────────
def validate_leave_request(
    request_data: dict,
    staff: Any,                           # should have .grade and .has_cdsa_international_permission
    current_year_balances: LeaveBalances,
    public_holidays: List[datetime] = None,
    hospitalization_records: List[Tuple[datetime, datetime]] = None
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    Validates a leave request according to TACOS Chapter 8 rules.
    Returns (is_valid: bool, message: str or None, metadata: dict or None)
    """
    if public_holidays is None:
        public_holidays = []
    if hospitalization_records is None:
        hospitalization_records = []

    leave_type = request_data.get('type')
    if not leave_type:
        return False, "Leave type is required", None

    days = request_data.get('working_days_requested', 0)
    start_date = request_data.get('start_date')
    end_date = request_data.get('end_date')
    has_dates = start_date and end_date

    # Common metadata
    metadata = {
        'requires_approval': True,  # All leaves are discretionary
        'deduct_from_annual': 0,
        'triggers_medical_board': False,
        'notes': ["All leave is subject to CDSA / director discretion"]
    }

    # ──────────────────────────────────────────────
    # GLOBAL CHECK: International travel
    # ──────────────────────────────────────────────
    if request_data.get('outside_nigeria', False):
        if not getattr(staff, 'has_cdsa_international_permission', False):
            return False, "CDSA permission required for leave/travel outside Nigeria", None
        metadata['notes'].append("International travel permission confirmed")

    # ──────────────────────────────────────────────
    # ANNUAL LEAVE
    # ──────────────────────────────────────────────
    if leave_type == 'annual':
        if not has_dates:
            return False, "Start and end dates required for annual leave", None
        calculated = working_days_between(start_date, end_date, public_holidays)
        if calculated != days:
            days = calculated
            metadata['notes'].append(f"Adjusted to {days} working days")
        if current_year_balances.annual_remaining < days:
            return False, f"Insufficient annual leave ({current_year_balances.annual_remaining} days remaining)", None
        metadata['deduct_from_annual'] = days
        return True, "Annual leave request valid", metadata

    # ──────────────────────────────────────────────
    # CASUAL LEAVE / PASS
    # ──────────────────────────────────────────────
    elif leave_type == 'casual':
        if not has_dates:
            return False, "Start and end dates required for casual leave", None

        req_calendar = calendar_days_between(start_date, end_date)
        req_working = working_days_between(start_date, end_date, public_holidays)

        if req_calendar <= 0:
            return False, "Invalid date range for casual leave", None

        total_calendar_after = current_year_balances.casual_calendar_days + req_calendar

        if total_calendar_after <= 7:
            metadata['notes'].append(f"Within remaining {7 - current_year_balances.casual_calendar_days} calendar day(s) free allowance")
            return True, "Casual leave approved (no deduction)", metadata

        # Excess → deduct full working days of this request
        deduct = req_working

        if current_year_balances.annual_remaining < deduct:
            return False, (
                f"Excess casual leave requires {deduct} working days from annual leave "
                f"(only {current_year_balances.annual_remaining} remaining)"
            ), None

        metadata['deduct_from_annual'] = deduct
        metadata['notes'].append(f"{deduct} working day(s) will be deducted from annual leave")
        metadata['notes'].append(f"Total casual calendar days this year will become {total_calendar_after}")
        return True, "Casual leave approved with annual deduction", metadata

    # ──────────────────────────────────────────────
    # COMPASSIONATE LEAVE
    # ──────────────────────────────────────────────
    elif leave_type == 'compassionate':
        if not has_dates:
            return False, "Start and end dates required", None
        calculated = working_days_between(start_date, end_date, public_holidays)
        if calculated != days:
            days = calculated
            metadata['notes'].append(f"Adjusted to {days} working days")
        if current_year_balances.compassionate_used + days > 10:
            return False, f"Maximum 10 working days compassionate leave per year (used: {current_year_balances.compassionate_used})", None
        metadata['notes'].append("Pending director recommendation & CDSA approval")
        return True, "Compassionate leave request valid", metadata

    # ──────────────────────────────────────────────
    # SICK LEAVE
    # ──────────────────────────────────────────────
    elif leave_type == 'sick':
        if not request_data.get('has_medical_certificate', False):
            return False, "Government medical officer certificate required", None
        if not has_dates:
            return False, "Start and end dates required", None

        calculated = working_days_between(start_date, end_date, public_holidays)
        if calculated != days:
            days = calculated
            metadata['notes'].append(f"Adjusted to {days} working days")

        hospitalized = is_hospitalized_period(start_date, end_date, hospitalization_records)

        if hospitalized:
            calendar_days = calendar_days_between(start_date, end_date)
            if request_data.get('first_hospitalization', False) and calendar_days > 90:
                return False, "First hospitalization limited to approximately 3 months (~90 calendar days)", None
            metadata['notes'].append("Hospitalization period – does not count against sick leave quota")
            return True, "Hospital sick leave approved", metadata

                # NON-HOSPITALIZED SICK LEAVE
        if days > 21:
            metadata['notes'].append(
                f"Warning: requested sick leave ({days} working days) exceeds the normal 21-day guideline. "
                "This may require additional medical justification and/or Medical Board consideration."
            )
            metadata['notes'].append(
                "Approval is still possible at the discretion of the approving authority."
            )

        # Rolling 12-month aggregate check (still strict)
        if current_year_balances.sick_rolling_12m + days > 42:
            return False, (
                f"Exceeds maximum 6 weeks (42 working days) in rolling 12 months "
                f"(current rolling total: {current_year_balances.sick_rolling_12m})"
            ), None

        # Calendar year threshold → Medical Board required
        if current_year_balances.sick_this_year + days > 21:
            metadata['triggers_medical_board'] = True
            metadata['notes'].append(
                "Note: total sick leave this calendar year will exceed 21 days → "
                "Medical Board proceedings must be initiated after approval"
            )

        return True, "Non-hospitalized sick leave request valid (subject to approval)", metadata
    # ──────────────────────────────────────────────
    # MATERNITY LEAVE
    # ──────────────────────────────────────────────
    elif leave_type == 'maternity':
        if not has_dates:
            return False, "Start and end dates required for maternity leave", None
        edd = request_data.get('expected_delivery_date')
        if not edd:
            return False, "Expected delivery date (EDD) is required for maternity leave", None

        if start_date > edd:
            return False, "Leave start date cannot be after expected delivery date", None

        calculated = working_days_between(start_date, end_date, public_holidays)
        if calculated != 112:
            return False, f"Maternity leave must be exactly 112 working days (calculated: {calculated})", None

        days_before_edd = working_days_between(start_date, edd, public_holidays)
        if days_before_edd > 28:
            return False, f"Maternity leave must start within 28 working days before EDD (currently {days_before_edd})", None

        metadata['notes'].append("Maternity leave – 112 working days continuous block")
        metadata['notes'].append("Follows Public Service Rules provisions")
        return True, "Maternity leave request valid", metadata

    # ──────────────────────────────────────────────
    # PATERNITY LEAVE
    # ──────────────────────────────────────────────
    elif leave_type == 'paternity':
        if not has_dates:
            return False, "Start and end dates required for paternity leave", None

        calculated = working_days_between(start_date, end_date, public_holidays)
        if calculated != 14:
            return False, f"Paternity leave must be exactly 14 working days (calculated: {calculated})", None

        metadata['notes'].append("Paternity leave – 14 working days (per PSR 2021)")
        return True, "Paternity leave request valid", metadata

    # ──────────────────────────────────────────────
    # DISEMBARKATION LEAVE
    # ──────────────────────────────────────────────
    elif leave_type == 'disembarkation':
        months = request_data.get('attachment_months', 0)
        if months < 3:
            return False, "Attachment must be at least 3 continuous months", None
        if not has_dates:
            return False, "Start and end dates required for disembarkation leave", None

        expected_days = 14 if months > 6 else 7

        calculated = working_days_between(start_date, end_date, public_holidays)
        if calculated != expected_days:
            return False, f"Disembarkation leave should be {expected_days} working days for {months} months attachment (calculated: {calculated})", None

        metadata['notes'].append(f"Disembarkation leave for {months} months course/operational attachment")
        return True, f"Disembarkation leave approved – {expected_days} working days", metadata

    # ──────────────────────────────────────────────
    # TERMINAL LEAVE
    # ──────────────────────────────────────────────
    elif leave_type == 'terminal':
        if current_year_balances.terminal_granted:
            return False, "Terminal leave has already been granted", None
        if not has_dates:
            return False, "Start and end dates required for terminal leave", None

        expected_days = get_terminal_entitlement(staff.grade)

        calculated = working_days_between(start_date, end_date, public_holidays)
        if calculated != expected_days:
            return False, f"Terminal leave should be {expected_days} working days for grade {staff.grade} (calculated: {calculated})", None

        metadata['notes'].append(f"Terminal leave on retirement – {expected_days} working days")
        metadata['notes'].append("Final leave – non-extendable")
        return True, f"Terminal leave request valid", metadata

    # ──────────────────────────────────────────────
    # Unknown type
    # ──────────────────────────────────────────────
    return False, f"Unsupported leave type: {leave_type}", None