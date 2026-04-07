import os
import logging
from datetime import datetime, timedelta

import pytz
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Seoul")
EXIM_API_KEY = os.getenv("EXIM_API_KEY")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_usd_krw_exim() -> float | None:
    """한국수출입은행 공식 고시환율 조회"""
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


def get_usd_krw_frankfurter() -> float | None:
    """Frankfurter API (ECB 기반) 오늘 USD/KRW 환율 조회"""
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=KRW", timeout=10
        )
        resp.raise_for_status()
        rate = float(resp.json()["rates"]["KRW"])
        logger.info(f"Frankfurter 환율: {rate}")
        return rate
    except Exception as e:
        logger.error(f"Frankfurter 환율 조회 실패: {e}")
        return None


def get_today_rate() -> tuple[float | None, str]:
    if EXIM_API_KEY:
        rate = get_usd_krw_exim()
        if rate:
            return rate, "한국수출입은행"
    rate = get_usd_krw_frankfurter()
    return rate, "Frankfurter (ECB)"


def get_3year_average() -> float | None:
    """최근 3년간 USD/KRW 평균 환율 (Frankfurter API)"""
    try:
        tz = pytz.timezone(TIMEZONE)
        end = datetime.now(tz)
        start = end - timedelta(days=365 * 3)
        url = (
            f"https://api.frankfurter.app/{start.strftime('%Y-%m-%d')}"
            f"..{end.strftime('%Y-%m-%d')}?from=USD&to=KRW"
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        rates = [v["KRW"] for v in resp.json()["rates"].values()]
        avg = sum(rates) / len(rates)
        logger.info(f"3년 평균 환율: {avg:.2f} ({len(rates)}일 기준)")
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
        status = "📉 <b>3년 평균보다 낙음</b>"
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


def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_TOKEN 또는 CHAT_ID가 설정되지 않았습니다.")
        raise SystemExit(1)

    today_rate, source = get_today_rate()
    avg_rate = get_3year_average()

    if today_rate is None or avg_rate is None:
        send_telegram_message("⚠️ 오늘 환율 데이터를 가져오지 못했습니다.")
        raise SystemExit(1)

    message = build_message(today_rate, avg_rate, source)
    send_telegram_message(message)


if __name__ == "__main__":
    main()
