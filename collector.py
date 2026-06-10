from datetime import datetime
import requests
import streamlit as st

from db import init_db, insert_media_snapshot, insert_account_snapshot


def get_config():
    return {
        "ig_user_id": st.secrets["IG_USER_ID"],
        "access_token": st.secrets["ACCESS_TOKEN"],
        "version": st.secrets.get("GRAPH_API_VERSION", "v23.0"),
    }


def graph_get(endpoint, params=None):
    config = get_config()

    if params is None:
        params = {}

    params["access_token"] = config["access_token"]

    url = f"https://graph.facebook.com/{config['version']}/{endpoint}"
    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        raise Exception(f"API 오류: {response.status_code} / {response.text}")

    return response.json()


def fetch_account_info():
    config = get_config()

    data = graph_get(
        config["ig_user_id"],
        params={
            "fields": "followers_count,media_count"
        }
    )

    return {
        "followers_count": data.get("followers_count", 0),
        "media_count": data.get("media_count", 0)
    }


def fetch_recent_media(limit=25):
    config = get_config()

    data = graph_get(
        f"{config['ig_user_id']}/media",
        params={
            "fields": "id,caption,media_type,permalink,timestamp,like_count,comments_count",
            "limit": limit
        }
    )

    return data.get("data", [])


def fetch_media_insights(media_id):
    """
    핵심:
    - views: 조회수 계열
    - saved: 저장수
    - shares: 공유수

    계정 권한/미디어 타입에 따라 일부 지표가 안 나올 수 있음.
    안 나오면 0으로 처리.
    """

    metrics = "views,saved,shares"

    try:
        data = graph_get(
            f"{media_id}/insights",
            params={
                "metric": metrics
            }
        )
    except Exception:
        return {
            "views": 0,
            "saved": 0,
            "shares": 0
        }

    result = {
        "views": 0,
        "saved": 0,
        "shares": 0
    }

    for item in data.get("data", []):
        name = item.get("name")
        values = item.get("values", [])

        if not values:
            continue

        value = values[0].get("value", 0)

        if name in result:
            result[name] = value

    return result


def collect_once(limit=25):
    init_db()

    collected_at = datetime.now().isoformat(timespec="seconds")

    account = fetch_account_info()
    insert_account_snapshot(
        followers_count=account["followers_count"],
        media_count=account["media_count"]
    )

    media_list = fetch_recent_media(limit=limit)

    rows = []

    for media in media_list:
        media_id = media.get("id")
        insights = fetch_media_insights(media_id)

        rows.append({
            "collected_at": collected_at,
            "media_id": media_id,
            "media_type": media.get("media_type", ""),
            "caption": media.get("caption", ""),
            "permalink": media.get("permalink", ""),
            "timestamp": media.get("timestamp", ""),
            "like_count": media.get("like_count", 0),
            "comments_count": media.get("comments_count", 0),
            "views": insights.get("views", 0),
            "saved": insights.get("saved", 0),
            "shares": insights.get("shares", 0),
        })

    insert_media_snapshot(rows)

    return {
        "collected_at": collected_at,
        "media_count": len(rows),
        "followers_count": account["followers_count"]
    }