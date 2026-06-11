from collector import collect_once

print("POSETIZ Instagram Monitor GitHub 자동 실행 시작")

try:
    result = collect_once(limit=25)
    print("수집 완료:", result)
except Exception as e:
    print("수집 실패:", e)
    raise