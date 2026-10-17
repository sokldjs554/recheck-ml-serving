import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ConsistencyReview, FailureReview, SustainedReview } from './MeasuredReview';

it.each([SustainedReview, FailureReview, ConsistencyReview])('opens original evidence separately so inspecting it cannot destroy an active case', (Review) => {
  const html = renderToStaticMarkup(<Review />);
  const links = html.match(/<a\b[^>]*href="https:\/\/github\.com[^>]*>/g) || [];
  expect(links.length).toBeGreaterThan(0);
  for (const link of links) {
    expect(link).toContain('target="_blank"');
    expect(link).toContain('rel="noreferrer"');
  }
});

it('shows outcome counts at the selected load phase instead of treating every HTTP completion as useful', () => {
  const html = renderToStaticMarkup(<SustainedReview />);
  expect(html).toContain('data-testid="outcome-breakdown"');
  expect(html).toContain('유효 응답');
  expect(html).toContain('1,477');
  expect(html).toContain('91');
  expect(html).toContain('저장 후 응답 실패 1건');
});

it('puts the chosen request and its trace before secondary recovery explanations', () => {
  const html = renderToStaticMarkup(<FailureReview />);
  expect(html).toContain('data-testid="request-verdict"');
  expect(html.indexOf('data-testid="trace-explorer"')).toBeLessThan(html.indexOf('별도 kind 실험'));
  expect(html).toContain('공통 시간축');
});
