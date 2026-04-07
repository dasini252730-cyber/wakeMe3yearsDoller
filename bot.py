import os
import logging
from datetime import datetime, timedelta

import pytz
import yfinance as yf
import schedule
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Seoul")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_usd_krw_rate() -> float | None:
    """오늘의 USD/KRW 환율 조회"""
    try:
        ticker = yf.Ticker("USDKRW=X")
        data = ticker.history(period="5d")
        if data.empty:
            return None
        return float(data["Close"].iloc[-1])
    except Exception as e:
        logger.error(f"환율 조회 실패: {e}")
        return None


def get_3year_average() -> float | None:
    """최근 3년간 USD/KRW 평균 환율 계산"""
    try:
        end = datetime.now()
        start = end - timedelta(days=365 * 3)
        ticker = yf.Ticker("USDKRW=X")
        data = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        if data.empty:
            return None
        return float(data["Close"].mean())
    except Exception as e:
        logger.error(f"3년 평균 환율 조회 실패: {e}")
        return None


def send_telegram_message(text: str) -> bool:
    """텔레그램으로 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("메시지 전송 완료")
        return True
    except Exception as e:
        logger.error(f"메시지 전송 실패: {e}")
        return False


def build_message(today_rate: float, avg_rate: float) -> str:
    diff = today_rate - avg_rate
    diff_pct = (diff / avg_rate) * 100
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%Y년 %m월 %d일")

    if diff > 0:
        status = "📈 <b>3년 평균보다 높음</b>"
        arrow = "▲"
    else:
        status = "📉 <b>3년 평균보다 낮음</b>"
        arrow = "▼"

    return (
        f"💵 <b>오늘의 달러 환율 리포트</b> ({now})\n\n"
        f"현재 환율: <b>{today_rate:,.2f} 원</b>\n"
        f"3년 평균:  <b>{avg_rate:,.2f} 원</b>\n\n"
        f"상태: {status}\n"
        f"차이: {arrow} {abs(diff):,.2f} 원 ({abs(diff_pct):.2f}%)\n\n"
        f"{'달러가 비쌉니다. 환전은 신중하게!' if diff > 0 else '달러가 저렴합니다. 환전 적기일 수 있어요!'}"
    )


def daily_job():
    logger.info("일일 환율 리포트 실행")
    today_rate = get_usd_krw_rate()
    avg_rate = get_3year_average()

    if today_rate is None or avg_rate is None:
        send_telegram_message("⚠️ 오늘 환율 데이터를 가져오지 못했습니다. 잠시 후 다시 시도합니다.")
        return

    message = build_message(today_rate, avg_rate)
    send_telegram_message(message)


def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN 또는 CHAT_ID가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return

    tz = pytz.timezone(TIMEZONE)
    logger.info(f"봇 시작 - 매일 09:00 ({TIMEZONE}) 전송 예정")

    # 매일 9시에 실행 (서버 로컬 시간 기준 스케줄, KST 서버 권장)
    schedule.every().day.at("09:00").do(daily_job)

    # 시작 시 즉시 한 번 실행하려면 아래 주석 해제
    # daily_job()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
