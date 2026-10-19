def finish_case(page):
    """Explicitly acknowledge the blocked and recorded outcomes, without timed UI delays."""
    while True:
        page.wait_for_function('''() => {
          const c = document.querySelector('[data-testid=case-study]');
          const b = document.querySelector('[data-testid=case-run-top]');
          return c && (c.dataset.step === '6' || (b && !b.disabled && Number(c.dataset.step) > 0));
        }''', timeout=110000)
        if page.get_by_test_id('case-study').get_attribute('data-step') == '6':
            page.wait_for_function('document.querySelector("[data-testid=server-records]").getAttribute("aria-busy") === "false"')
            return
        page.get_by_test_id('case-run-top').click()
