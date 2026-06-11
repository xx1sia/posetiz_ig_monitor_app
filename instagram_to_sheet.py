import os
import json
import time
from datetime import datetime, timezone, timedelta

import requests
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound


# =========================
# 기본 설정
# =========================

SPREADSHEET_ID = "1mU2vaR3I38ftYo1vRRi-Ca2j_yzOTfOVnICAw8DqTTo"
SHEET_NAME = "일별 오가닉 지표"
SERVICE_ACCOUNT_FILE = "service_account.json"

TEAM_NAME = "1조"
GRAPH_VERSION = "v23.0"

MEDIA_LIMIT = 10
RECENT_DAYS = 30

STATE_FILE = "instagram_state.json"


# =========================
# secrets.toml 읽기
# =========================

def load_toml_secrets():
    possible_paths = [
        ".streamlit/secrets.toml",
        "secrets.toml"
    ]

    for path in possible_paths:
        if not os.path.exists(path):
            continue

        try:
            import tomllib
            with open(path, "rb") as f:
                return tomllib.load(f)
        except Exception:
            secrets = {}
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" not in line or line.startswith("#"):
                        continue
                    key, value = line.split("=", 1)
                    secrets[key.strip()] = value.strip().strip('"').strip("'")
            return secrets

    return {}


SECRETS = load_toml_secrets()


def get_secret(*names):
    for name in names:
        value = os.getenv(name)
        if value:
            return value

        value = SECRETS.get(name)
        if value:
            return value

    return None


IG_USER_ID = get_secret("IG_USER_ID", "INSTAGRAM_USER_ID")
ACCESS_TOKEN = get_secret(
    "IG_ACCESS_TOKEN",
    "INSTAGRAM_ACCESS_TOKEN",
    "ACCESS_TOKEN",
    "META_ACCESS_TOKEN"
)


# =========================
# 상태 저장
# =========================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# =========================
# 필수 설정 확인
# =========================

def require_settings():
    missing = []

    if not IG_USER_ID:
        missing.append("IG_USER_ID")

    if not ACCESS_TOKEN:
        missing.append("IG_ACCESS_TOKEN")

    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        missing.append("service_account.json")

    if missing:
        raise Exception(
            "필수 설정이 없습니다: "
            + ", ".join(missing)
            + "\n\n.streamlit/secrets.toml 예시:\n"
            + 'IG_USER_ID = "너의_인스타그램_USER_ID"\n'
            + 'IG_ACCESS_TOKEN = "너의_인스타그램_ACCESS_TOKEN"\n'
        )


# =========================
# Meta Graph API
# =========================

def graph_get(path, params=None, quiet=False):
    if params is None:
        params = {}

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{path}"
    params["access_token"] = ACCESS_TOKEN

    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        if quiet:
            return None

        raise Exception(
            f"Meta API 오류\n"
            f"URL: {url}\n"
            f"STATUS: {response.status_code}\n"
            f"RESPONSE: {response.text}"
        )

    return response.json()


def extract_insight_value(result, metric_name):
    if not result:
        return 0

    for item in result.get("data", []):
        if item.get("name") != metric_name:
            continue

        if "total_value" in item:
            total_value = item.get("total_value") or {}
            return total_value.get("value", 0) or 0

        values = item.get("values", [])
        if values:
            return values[-1].get("value", 0) or 0

    return 0


def get_media_metric(media_id, metric_candidates):
    for metric in metric_candidates:
        result = graph_get(
            f"{media_id}/insights",
            {"metric": metric},
            quiet=True
        )

        value = extract_insight_value(result, metric)

        if isinstance(value, dict):
            value = 0

        if value not in [None, "", 0]:
            return value

    return 0


def parse_instagram_time(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


# =========================
# 구글 시트 연결
# =========================

def get_worksheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=scopes
    )

    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        worksheet = spreadsheet.worksheet(SHEET_NAME)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=SHEET_NAME,
            rows=1000,
            cols=20
        )
        print(f"'{SHEET_NAME}' 탭이 없어서 새로 만들었습니다.")

    ensure_sheet_size(worksheet)

    return spreadsheet, worksheet


def ensure_sheet_size(worksheet):
    if worksheet.row_count < 1000:
        worksheet.add_rows(1000 - worksheet.row_count)

    if worksheet.col_count < 16:
        worksheet.add_cols(16 - worksheet.col_count)


# =========================
# 시트 디자인 세팅
# =========================

def setup_pretty_sheet(spreadsheet, worksheet):
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    title_row = [
        "POSETIZ_ 인스타그램 일별 오가닉 지표 자동수집",
        "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""
    ]

    info_row = [
        f"마지막 업데이트: {now_text} | 조: {TEAM_NAME} | 수집 기준: 최근 {RECENT_DAYS}일 / 최신 {MEDIA_LIMIT}개 콘텐츠",
        "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""
    ]

    blank_row = [""] * 16

    headers = [
        "날짜",
        "조",
        "콘텐츠 ID",
        "체크 시점",
        "조회수",
        "도달",
        "좋아요",
        "댓글",
        "저장",
        "공유",
        "평균 재생 시간(초)",
        "프로필 방문",
        "일별 팔로워 증가",
        "참여수",
        "참여율",
        "메모"
    ]

    worksheet.update(
        values=[title_row, info_row, blank_row, headers],
        range_name="A1:P4"
    )

    apply_sheet_style(spreadsheet, worksheet)


def apply_sheet_style(spreadsheet, worksheet):
    sheet_id = worksheet.id

    requests = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "frozenRowCount": 4
                    }
                },
                "fields": "gridProperties.frozenRowCount"
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 16
                },
                "mergeType": "MERGE_ALL"
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": 16
                },
                "mergeType": "MERGE_ALL"
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 16
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {
                            "red": 0.05,
                            "green": 0.16,
                            "blue": 0.35
                        },
                        "textFormat": {
                            "foregroundColor": {
                                "red": 1,
                                "green": 1,
                                "blue": 1
                            },
                            "bold": True,
                            "fontSize": 15
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": 16
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {
                            "red": 0.90,
                            "green": 0.94,
                            "blue": 1
                        },
                        "textFormat": {
                            "foregroundColor": {
                                "red": 0.10,
                                "green": 0.10,
                                "blue": 0.10
                            },
                            "bold": True,
                            "fontSize": 10
                        },
                        "horizontalAlignment": "LEFT",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 3,
                    "endRowIndex": 4,
                    "startColumnIndex": 0,
                    "endColumnIndex": 16
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {
                            "red": 0.13,
                            "green": 0.28,
                            "blue": 0.58
                        },
                        "textFormat": {
                            "foregroundColor": {
                                "red": 1,
                                "green": 1,
                                "blue": 1
                            },
                            "bold": True,
                            "fontSize": 10
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)"
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 4,
                    "startColumnIndex": 0,
                    "endColumnIndex": 16
                },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP"
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,wrapStrategy)"
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 4,
                    "startColumnIndex": 4,
                    "endColumnIndex": 14
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "NUMBER",
                            "pattern": "#,##0"
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat"
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 4,
                    "startColumnIndex": 14,
                    "endColumnIndex": 15
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "PERCENT",
                            "pattern": "0.00%"
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat"
            }
        },
        column_width_request(sheet_id, 0, 1, 100),
        column_width_request(sheet_id, 1, 2, 70),
        column_width_request(sheet_id, 2, 3, 210),
        column_width_request(sheet_id, 3, 4, 170),
        column_width_request(sheet_id, 4, 10, 95),
        column_width_request(sheet_id, 10, 13, 140),
        column_width_request(sheet_id, 13, 15, 95),
        column_width_request(sheet_id, 15, 16, 420),
    ]

    try:
        spreadsheet.batch_update({"requests": requests})
    except Exception:
        pass


def column_width_request(sheet_id, start_index, end_index, pixel_size):
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": start_index,
                "endIndex": end_index
            },
            "properties": {
                "pixelSize": pixel_size
            },
            "fields": "pixelSize"
        }
    }


def get_next_data_row(worksheet):
    col_values = worksheet.col_values(3)

    last_data_row = 4

    for index, value in enumerate(col_values, start=1):
        if index <= 4:
            continue

        if str(value).strip():
            last_data_row = index

    return last_data_row + 1


# =========================
# 인스타 데이터 수집
# =========================

def get_recent_media():
    result = graph_get(
        f"{IG_USER_ID}/media",
        {
            "fields": ",".join([
                "id",
                "caption",
                "media_type",
                "media_product_type",
                "timestamp",
                "permalink",
                "like_count",
                "comments_count"
            ]),
            "limit": MEDIA_LIMIT
        }
    )

    media_list = result.get("data", [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)

    filtered = []

    for media in media_list:
        posted_at = parse_instagram_time(media.get("timestamp"))

        if posted_at and posted_at < cutoff:
            continue

        filtered.append(media)

    return filtered


def get_profile_views():
    result = graph_get(
        f"{IG_USER_ID}/insights",
        {
            "metric": "profile_views",
            "period": "day",
            "metric_type": "total_value"
        },
        quiet=True
    )

    return extract_insight_value(result, "profile_views")


def get_current_followers():
    result = graph_get(
        IG_USER_ID,
        {
            "fields": "followers_count"
        },
        quiet=True
    )

    if not result:
        return 0

    return result.get("followers_count", 0) or 0


def get_daily_follower_growth(current_followers):
    today = datetime.now().strftime("%Y-%m-%d")
    state = load_state()

    saved_date = state.get("date")
    start_followers = state.get("start_followers")

    if saved_date != today or start_followers is None:
        state["date"] = today
        state["start_followers"] = current_followers
        save_state(state)
        return 0

    return current_followers - int(start_followers)


def get_media_metrics(media):
    media_id = media.get("id")

    views = get_media_metric(
        media_id,
        [
            "views",
            "plays",
            "video_views",
            "impressions"
        ]
    )

    reach = get_media_metric(
        media_id,
        [
            "reach"
        ]
    )

    saves = get_media_metric(
        media_id,
        [
            "saved",
            "saves"
        ]
    )

    shares = get_media_metric(
        media_id,
        [
            "shares"
        ]
    )

    avg_watch_time = get_media_metric(
        media_id,
        [
            "ig_reels_avg_watch_time",
            "average_watch_time",
            "avg_watch_time"
        ]
    )

    if isinstance(avg_watch_time, (int, float)) and avg_watch_time > 1000:
        avg_watch_time = round(avg_watch_time / 1000, 2)

    likes = media.get("like_count", 0) or 0
    comments = media.get("comments_count", 0) or 0

    return {
        "views": views,
        "reach": reach,
        "likes": likes,
        "comments": comments,
        "saves": saves,
        "shares": shares,
        "avg_watch_time": avg_watch_time
    }


# =========================
# 시트 입력
# =========================

def write_rows_to_sheet(worksheet, rows):
    if not rows:
        print("입력할 데이터가 없습니다.")
        return

    start_row = get_next_data_row(worksheet)
    end_row = start_row + len(rows) - 1
    update_range = f"A{start_row}:P{end_row}"

    worksheet.update(
        values=rows,
        range_name=update_range,
        value_input_option="USER_ENTERED"
    )

    print(f"시트 입력 위치: {update_range}")


# =========================
# 메인 실행
# =========================

def main():
    require_settings()

    spreadsheet, worksheet = get_worksheet()
    setup_pretty_sheet(spreadsheet, worksheet)

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    checked_at = now.strftime("%Y-%m-%d %H:%M:%S")

    print("인스타 데이터 수집 시작")
    print("체크 시점:", checked_at)
    print("입력 탭:", SHEET_NAME)

    profile_views = get_profile_views()
    current_followers = get_current_followers()
    daily_follower_growth = get_daily_follower_growth(current_followers)

    media_list = get_recent_media()

    rows = []

    for media in media_list:
        media_id = media.get("id")
        permalink = media.get("permalink", "")
        media_type = media.get("media_type", "")
        media_product_type = media.get("media_product_type", "")

        metrics = get_media_metrics(media)

        likes = metrics["likes"]
        comments = metrics["comments"]
        saves = metrics["saves"]
        shares = metrics["shares"]
        reach = metrics["reach"]

        engagement_count = likes + comments + saves + shares

        if reach and reach > 0:
            engagement_rate = engagement_count / reach
        else:
            engagement_rate = 0

        memo = f"{media_type}/{media_product_type} | {permalink}"

        row = [
            today,
            TEAM_NAME,
            media_id,
            checked_at,
            metrics["views"],
            reach,
            likes,
            comments,
            saves,
            shares,
            metrics["avg_watch_time"],
            profile_views,
            daily_follower_growth,
            engagement_count,
            engagement_rate,
            memo
        ]

        rows.append(row)
        time.sleep(0.3)

    write_rows_to_sheet(worksheet, rows)

    print("구글 시트 입력 성공!")
    print("입력 행 수:", len(rows))
    print("연결된 시트 URL:", spreadsheet.url)
    print("입력된 탭:", worksheet.title)


if __name__ == "__main__":
    main()