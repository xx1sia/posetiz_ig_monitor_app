import time
import schedule

from collector import collect_once


def job():
    print("인스타그램 데이터 수집 시작")
    result = collect_once(limit=25)
    print("수집 완료:", result)


schedule.every(1).hours.do(job)

print("POSETIZ Instagram Monitor 자동 수집 시작")
print("1시간마다 데이터를 수집합니다.")

job()

while True:
    schedule.run_pending()
    time.sleep(60)