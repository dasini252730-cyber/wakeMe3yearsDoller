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
EXIM_API_KEY = os.getenv("EXIM_API_KEY")  # 한국수출입은행 API 키 (선택)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_usd_krw_exim() -> float | None:
    """한국수출입은행 공식 고시환율 조회 (매매기준율)"""
    try:
        tz = pytz.timezone(TIMEZONE)
        today = datetime.now(tz).strftime("%Y%m%d")
        url = "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"
        params = {"authkey": EXIM_API_KEY, "searchdate": today, "data": "AP01"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for item in data:
            if item.get("cur_unit") == "USD":
                rate = float(item["deal_bas_r"].replace(",", ""))
                logger.info(f"수출입은행 환율: {rate}")
                return rate
        return None
    except Exception as e:
        logger.error(f"수출입은행 환율 조회 실패: {e}")
        return None


def get_usd_krw_yahoo() -> float | None:
    """Yahoo Finance USD/KRW 환율 조회 (fallback)"""
    try:
        ticker = yf.Ticker("USDKRW=X")
        data = ticker.history(period="5d")
        if data.empty:
            return None
        rate = float(data["Close"].iloc[-1])
        logger.info(f"Yahoo Finance 환율: {rate}")
        return rate
    except Exception as e:
        logger.error(f"Yahoo Finance 환율 조회 실패: {e}")
        return None


def get_today_rate() -> tuple[float | None, str]:
    """오늘 환율 조회 - 수출입은행 우선, 실패 시 Yahoo Finance"""
    if EXIM_API_KEY:
        rate = get_usd_krw_exim()
        if rate:
            return rate, "한국수출입은행"
    rate = get_usd_krw_yahoo()
    return rate, "Yahoo Finance"


def get_3year_average() -> float | None:
    """최근 3년간 USD/KRW 평균 환율 계산 (Yahoo Finance)"""
    try:
        end = datetime.now()
        start = end - timedelta(days=365 * 3)
        ticker = yf.Ticker("USDKRW=X")
        data = ticker.history(
            start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d")
        )
        if data.empty:
            return None
        avg = float(data["Close"].mean())
        logger.info(f"3년 평균 환율: {avg:.2f}")
        return avg
    except Exception as e:
        logger.error(f"3년 평균 환율 조회 실패: {e}")
        return None


def send_telegram_message(text: str) -> bool:
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


def build_message(today_rate: float, avg_rate: float, source: str) -> str:
    diff = today_rate - avg_rate
    diff_pct = (diff / avg_rate) * 100
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz).strftime("%Y년 %m월 %d일")

    if diff > 0:
        status = "📈 <b>3년 평균보다 높음</b>"
        arrow = "▲"
        comment = "달러가 비쌉니다. 환전은 신중하게!"
    else:
        status = "📉 <b>3년 평균보다 낮음</b>"
        arrow = "▼"
        comment = "달러가 저렴합니다. 환전 적기일 수 있어요!"

    return (
        f"💵 <b>오늘의 달러 환율 리포트</b> ({now})\n\n"
        f"현재 환율: <b>{today_rate:,.2f} 원</b>  <i>({source})</i>\n"
        f"3년 평균:  <b>{avg_rate:,.2f} 원</b>\n\n"
        f"상태: {status}\n"
        f"차이: {arrow} {abs(diff):,.2f} 원 ({abs(diff_pct):.2f}%)\n\n"
        f"{comment}"
    )


def daily_job():
    logger.info("일일 환율 리포트 실행")
    today_rate, source = get_today_rate()
    avg_rate = get_3year_average()

    if today_rate is None or avg_rate is None:
        send_telegram_message("⚠️ 오늘 환율 데이터를 가져오지 못했습니다. 잠시 후 다시 시도합니다.")
        return

    message = build_message(today_rate, avg_rate, source)
    send_telegram_message(message)


def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN 또는 CHAT_ID가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return

    logger.info(f"봇 시작 - 매일 09:00 ({TIMEZONE}) 전송 예정")
    schedule.every().day.at("09:00").do(daily_job)

    # 시작 시 즉시 한 번 실행하려면 아래 주석 해제
    # daily_job()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
