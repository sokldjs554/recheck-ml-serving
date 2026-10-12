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
