#!/usr/bin/env python3
"""Reproduce RECHECK's browser acceptance checks and capture honest evidence.

Requires Python Playwright (`python -m pip install playwright`) and Chromium.
Example: python scripts/check_browser.py --base http://127.0.0.1:5173 --api http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:5173", help="Frontend origin")
    parser.add_argument("--api", help="Optional live gateway origin; omit for browser-only checks")
    parser.add_argument("--browser-executable", default="/usr/bin/chromium")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "docs/evidence")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "frontend": args.base,
        "api": args.api,
        "browser_executable": args.browser_executable,
        "checks": [],
        "page_errors": [],
        "notes": [
            "Browser mode is a synthetic local state machine, not Python inference or a backend benchmark.",
            "Live checks use actual HTTP requests only when --api is supplied.",
            "Acceptance duration is test runtime, not model or serving performance.",
        ],
    }

    def passed(name: str, **details: object) -> None:
        report["checks"].append({"name": name, "passed": True, **details})
        print(f"PASS {name}", flush=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=args.browser_executable,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.set_default_timeout(10000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))

        def click(name: str) -> None:
            page.get_by_role("button", name=name, exact=True).click()

        def clear_request() -> None:
            click("판단 요청 실행")
            page.get_by_role("heading", name="현재 확인된 주의 신호가 없어요", exact=True).wait_for()

        def validate(valid: bool) -> None:
            click("현재 판단 사용 검증")
            page.get_by_role("status").filter(has_text="사용 가능" if valid else "사용 거절").wait_for()

        try:
            page.goto(args.base, wait_until="networkidle")
            page.locator(".mode-label").filter(has_text="브라우저 시뮬레이션").wait_for()
            clear_request()
            validate(True)
            click("수취인 정보 변경")
            page.get_by_role("heading", name="정보가 바뀌어 다시 확인이 필요해요", exact=True).wait_for()
            validate(False)
            passed("browser valid receipt then feature change refuses use")

            for mutation in ("정책 갱신", "모델 교체"):
                click("초기화")
                clear_request()
                click(mutation)
                validate(False)
                passed(f"browser {mutation} refuses stale receipt")

            click("초기화")
            click("추론 중 변경 재현")
            page.get_by_text("이전 결과 무효", exact=True).wait_for()
            passed("protected inference race invalidates stale result")

            click("초기화")
            page.get_by_role("switch", name="판단 최신성 보호").click()
            click("추론 중 변경 재현")
            page.get_by_role("heading", name="오래된 답이 통과했어요", exact=True).wait_for()
            validate(False)
            click("판단 JSON")
            page.get_by_role("dialog", name="판단의 근거를 열어 봅니다.").wait_for()
            with page.expect_download() as download:
                click("JSON 다운로드")
            receipt_name = download.value.suggested_filename
            assert receipt_name.endswith(".json")
            page.keyboard.press("Escape")
            page.get_by_role("dialog").wait_for(state="hidden")
            passed("unsafe baseline is visible but validation refuses; JSON download and Escape", downloaded=receipt_name)

            for fault, reason in (("시간 초과", "300ms 시간 예산을 초과했습니다."), ("응답 불가", "모델 서버가 응답할 수 없습니다.")):
                click("초기화")
                click(fault)
                click("판단 요청 실행")
                page.locator(".phone-result p").filter(has_text=reason).wait_for()
                passed(f"browser fault {fault} produces explicit review reason")

            click("서버 설계")
            page.get_by_role("heading", name="연산은 분리하고, 검증은 짧게.", exact=True).wait_for()
            page.get_by_text("공개 데모: SQLite", exact=False).wait_for()
            click("지원자의 관점")
            page.get_by_role("heading", name=re.compile("AI가 만든 답을")).wait_for()
            click("판단 기록")
            page.get_by_role("table", name="판단 기록").wait_for()
            click("인터랙티브 데모")
            click("90초 체험 시작")
            for name in ("이 단계 실행", "이 단계 실행", "이 단계 실행", "보호 장치 전후 비교"):
                click(name)
                page.wait_for_timeout(600)
            page.get_by_text("보호 장치 전후 비교 완료", exact=True).wait_for()
            passed("architecture, authentic applicant story, receipts, and successful guided comparison")

            click("초기화")
            clear_request()
            validate(True)
            page.wait_for_timeout(21000)
            page.get_by_role("status").filter(has_text="사용 거절").wait_for()
            page.get_by_role("status").filter(has_text="유효기간이 만료").wait_for()
            passed("a previous successful browser validation becomes refusal after actual expiry", waited_ms=21000)

            click("초기화")
            clear_request()
            validate(True)
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(args.output / "demo-desktop.png"), full_page=True)
            for width in (390, 768, 1024):
                page.set_viewport_size({"width": width, "height": 844})
                page.evaluate("window.scrollTo(0,0)")
                page.wait_for_timeout(150)
                assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth"), f"Horizontal overflow at {width}px"
                if width == 390:
                    page.screenshot(path=str(args.output / "demo-mobile.png"), full_page=True)
                    assert page.get_by_role("button", name="지원자의 관점", exact=True).is_visible()
                passed("responsive layout without horizontal overflow", width=width)
            page.set_viewport_size({"width": 1440, "height": 1050})

            if args.api:
                click("실제 Python 서버 연결")
                page.get_by_label("API 주소", exact=False).fill(args.api)
                click("연결 확인")
                page.get_by_text("HTTP API와 독립 모델 서버의 실제 응답을 표시합니다.", exact=True).wait_for()
                clear_request()
                validate(True)
                click("수취인 정보 변경")
                validate(False)
                passed("live Python HTTP mode validates clear result and refuses feature-stale use")

            assert not report["page_errors"], report["page_errors"]
            passed("no browser page errors")
            report["passed"] = True
            report["screenshots"] = ["demo-desktop.png", "demo-mobile.png"]
        except Exception as error:
            report["passed"] = False
            report["failure"] = str(error)
            raise
        finally:
            report["test_duration_seconds"] = round(time.perf_counter() - started, 3)
            (args.output / "browser-checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            browser.close()


if __name__ == "__main__":
    main()
