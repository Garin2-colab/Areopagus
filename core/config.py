import os
from pathlib import Path

APP_NAME = "areopagus"
VOLUME_NAME = "areopagus-data"
DATA_DIR = Path("/data")
HISTORY_PATH = DATA_DIR / "history.json"
AGENTS_CONFIG_PATH = DATA_DIR / "agents_config.json"
STUDIO_STATUS_PATH = DATA_DIR / "status.json"
HEARTBEAT_PATH = DATA_DIR / "last_heartbeat.json"
IMAGE_DIR = DATA_DIR / "images"
PENDING_TASKS_PATH = DATA_DIR / "pending_tasks.json"

ROOT_PATH = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT_PATH / "example" / "exampleJson.json"
LOCAL_AGENTS_CONFIG_PATH = ROOT_PATH / "agents_config.json"

TURN_COUNT = 3
KEYWORD_COUNT = 5
RUNWAY_SAFETY_REPLACEMENTS = {
    "tribunal": "civic forum",
    "verdict": "annotation",
    "verdicts": "annotations",
    "judgment": "reflection",
    "judgement": "reflection",
    "punishment": "revision",
    "severe": "precise",
    "intense": "focused",
    "high consequence": "ceremonial",
    "nick knight": "editorial photography",
    "iris van herpen": "sculptural fashion",
    "dazed digital": "fashion publication",
    "vogue": "fashion magazine",
}

GEMINI_MODEL = "gemini-2.5-flash"
RUNWAY_MODEL = "gpt_image_2"
RUNWAY_GEMINI_IMAGE_MODEL = "gemini_image3_pro"
RUNWAY_ASPECT_RATIO = "1:1"
RUNWAY_RATIO_BY_MODEL = {
    "gpt_image_2": {
        "1:1": "1920:1920",
        "16:9": "1920:1088",
        "9:16": "1088:1920",
        "4:3": "1920:1440",
        "3:4": "1440:1920",
        "21:9": "2048:880",
        "2:3": "1280:1920",
        "3:2": "1920:1280",
        "4:5": "1536:1920",
        "5:4": "1920:1536",
    },
    "gemini_image3_pro": {
        "1:1": "1024:1024",
        "16:9": "1344:768",
        "9:16": "768:1344",
        "4:3": "1184:864",
        "3:4": "864:1184",
        "21:9": "1536:672",
        "2:3": "832:1248",
        "3:2": "1248:832",
        "4:5": "896:1152",
        "5:4": "1152:896",
    },
    "gen4_image": {
        "1:1": "1080:1080",
    },
    "gen4_image_turbo": {
        "1:1": "1080:1080",
    },
    "gemini_2.5_flash": {
        "1:1": "1024:1024",
        "16:9": "1344:768",
        "9:16": "768:1344",
        "4:3": "1184:864",
        "3:4": "864:1184",
        "21:9": "1536:672",
        "2:3": "832:1248",
        "3:2": "1248:832",
        "4:5": "896:1152",
        "5:4": "1152:896",
    },
}
RUNWAY_QUALITY = "high"
WEBP_QUALITY = 60
RUNWAY_API_BASE = "https://api.dev.runwayml.com"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
INTEREST_WINDOW = 3
DEFAULT_AGENT_ACTIONS = {"Initiate", "Critique", "Pivot"}
PULSE_JITTER_MIN_SECONDS = 60
PULSE_JITTER_MAX_SECONDS = 120
RUNWAY_POLLING_DELAY_SECONDS = 5
CATEGORY_OPTIONS = [
    "Fashion",
    "Illustration",
    "Graphic Design",
    "Architecture",
    "UX/UI",
    "Industrial Design",
]
