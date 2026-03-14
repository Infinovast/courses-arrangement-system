# time_definition.py
from dataclasses import dataclass
from typing import List

# 标准周次
DOUBLE_WEEKS = list(range(2, 17, 2))
SINGLE_WEEKS = list(range(1, 17, 2))
SEMESTER_WEEKS = list(range(1, 17))
FINAL_REVIEW_WEEK = 17
ALL_WEEKS = SEMESTER_WEEKS + [FINAL_REVIEW_WEEK]

# 自定义周次
WEEKS_1_TO_14 = list(range(1, 15))
WEEKS_5_TO_15 = list(range(5, 16))  # 毕业班32学时课程前期
WEEKS_5_TO_16 = list(range(5, 17))
WEEKS_5_TO_17 = list(range(5, 18))
WEEKS_6_TO_17 = list(range(6, 18))
WEEKS_1_TO_8 = list(range(1, 9))
WEEKS_9_TO_16 = list(range(9, 17))
WEEKS_16_TO_17 = list(range(16, 18))

# 标准时间段
DAYS = list(range(1, 6))
PERIODS = list(range(1, 12))
MORNING_PERIODS = [1, 2, 3, 4]
AFTERNOOM_PERIODS = [5, 6, 7, 8]
EVENING_PERIODS = [9, 10, 11]

# GA与通用使用的合法开始节次（所有天数适用）
VALID_START_PERIODS_2_HOURS = {1, 3, 5, 7, 9}
VALID_START_PERIODS_3_HOURS = {1, 2, 5, 9}

@dataclass(frozen=True, eq=True, order=True)
class TimePoint:
    week: int
    day: int
    period: int
ALL_TIME_POINTS = [TimePoint(w, d, p) for w in ALL_WEEKS for d in DAYS for p in PERIODS]

class TimeSlot:
    def __init__(self, day, period, duration):
        self.day = day
        self.period = period
        self.duration = duration

    def __eq__(self, other):
        return self.day == other.day and self.period == other.period and self.duration == other.duration

    def __hash__(self):
        return hash((self.day, self.period, self.duration))

    def __repr__(self):
        return f"TimeSlot(D{self.day}, P{self.period}, Len{self.duration})"