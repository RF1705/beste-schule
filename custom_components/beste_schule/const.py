"""Constants for the beste.schule integration."""

DOMAIN = "beste_schule"
DEFAULT_API_URL = "https://beste.schule/api"

CONF_TOKEN = "token"
CONF_SCHOOL_NAME = "school_name"
CONF_MIGRATE_STUDENT_IDS = "_migrate_student_ids"
CONF_ENABLE_TIMETABLE_CALENDAR = "enable_timetable_calendar"
CONF_ENABLE_ABSENCE_CALENDAR = "enable_absence_calendar"
CONF_ENABLE_HOMEWORK_CALENDAR = "enable_homework_calendar"
CONF_ENABLE_EXAM_CALENDAR = "enable_exam_calendar"
CONF_ENABLE_NOTICE_CALENDAR = "enable_notice_calendar"
CONF_ENABLE_HOMEWORK_TODO = "enable_homework_todo"
DEFAULT_NAME = "beste.schule"

PLATFORMS = ["sensor", "calendar", "binary_sensor", "todo"]

DEFAULT_OPTIONS = {
    CONF_ENABLE_TIMETABLE_CALENDAR: True,
    CONF_ENABLE_ABSENCE_CALENDAR: True,
    CONF_ENABLE_HOMEWORK_CALENDAR: True,
    CONF_ENABLE_EXAM_CALENDAR: True,
    CONF_ENABLE_NOTICE_CALENDAR: True,
    CONF_ENABLE_HOMEWORK_TODO: True,
}
