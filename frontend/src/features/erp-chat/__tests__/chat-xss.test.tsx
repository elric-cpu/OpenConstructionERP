// OpenConstructionERP — chat XSS regression suite.
//
// Security audit 2026-05-24 finding #1: the chat surfaces
// (FloatingChatPanel + full-page MessageBubble) render assistant
// markdown into ``dangerouslySetInnerHTML``.  The hand-rolled
// ``renderMarkdown`` escapes raw HTML first then re-introduces a narrow
// set of tags via regex.  That's an XSS-by-edge-case pattern — a future
// edit to the regex pipeline could re-allow a script tag or an
// ``onerror`` attribute by accident.
//
// Fix: wrap the markdown output with ``DOMPurify.sanitize`` (with an
// explicit allow-list) before handing it to React.  This test pins the
// behaviour so the wrapper can never silently regress.
//
// Each payload covers one classic injection vector:
//   1. raw ``<script>``                — script element tag stripping
//   2. ``<img onerror>``               — event-handler attribute strip
//   3. ``[label](javascript:…)``       — javascript:-URL filter
//   4. ``<svg onload>``                — SVG-namespace event handler strip
//
// We exercise the full pipeline (renderMarkdown → DOMPurify.sanitize)
// using the same exported helpers the React components use, then parse
// the sanitised HTML and assert that the dangerous nodes are gone.

import { describe, expect, it } from 'vitest';
import DOMPurify from 'isomorphic-dompurify';
import {
  renderMarkdown,
  SANITIZE_CONFIG,
} from '../full-page/left/MessageBubble';

/** Run the production sanitise pipeline against an input string. */
function sanitiseChatMarkdown(input: string): string {
  return DOMPurify.sanitize(renderMarkdown(input), SANITIZE_CONFIG);
}

/** Parse the sanitised HTML into a DOM fragment for structural asserts. */
function parse(html: string): HTMLDivElement {
  const host = document.createElement('div');
  host.innerHTML = html;
  return host;
}

describe('chat markdown XSS hardening', () => {
  // For each payload we assert two things:
  //   1. The dangerous *element* never materialises in the parsed DOM
  //      (no live <script>/<img>/<svg> nodes, no live event handlers).
  //   2. No raw "<script", "<img", "<svg" markup appears in the output —
  //      anything resembling an HTML tag must be entity-escaped so the
  //      browser treats it as text, not as a tag waiting to execute.
  //
  // The literal text "onerror" / "onload" CAN appear in the output
  // because renderMarkdown HTML-escapes the angle brackets first, which
  // demotes the whole tag to inert text. That's the correct behaviour;
  // checking only that the angle brackets are escaped is enough to
  // prove the payload can't execute.
  it('strips raw <script> elements (payload 1)', () => {
    const out = sanitiseChatMarkdown('<script>alert(1)</script>hello');
    const frag = parse(out);
    expect(frag.querySelector('script')).toBeNull();
    expect(out.toLowerCase()).not.toContain('<script');
    expect(out).toContain('hello');
  });

  it('strips inline event handlers on <img> (payload 2)', () => {
    const out = sanitiseChatMarkdown('<img src=x onerror=alert(1)>');
    const frag = parse(out);
    // No live <img> element + no live onerror attribute anywhere.
    expect(frag.querySelector('img')).toBeNull();
    expect(out.toLowerCase()).not.toContain('<img');
    // Walk the DOM and assert no attribute name starts with "on" on any
    // surviving node — defence-in-depth against the sanitiser ever
    // letting an event handler through on an allow-listed tag.
    const all = frag.querySelectorAll('*');
    for (const el of all) {
      for (const attr of el.attributes) {
        expect(attr.name.toLowerCase().startsWith('on')).toBe(false);
      }
    }
  });

  it('rejects javascript: URLs inside [link](url) (payload 3)', () => {
    const out = sanitiseChatMarkdown('[click me](javascript:alert(1))');
    const frag = parse(out);
    const anchors = frag.querySelectorAll('a');
    for (const a of anchors) {
      const href = a.getAttribute('href') ?? '';
      expect(href.toLowerCase()).not.toContain('javascript:');
    }
    // No raw "javascript:" string anywhere in the rendered output.
    expect(out.toLowerCase()).not.toContain('javascript:');
    // The label text should still surface so the user sees *something*
    // (renderMarkdown wraps unknown-scheme labels in a plain <span>).
    expect(out).toContain('click me');
  });

  it('strips <svg onload> (payload 4)', () => {
    const out = sanitiseChatMarkdown('<svg onload=alert(1)></svg>');
    const frag = parse(out);
    expect(frag.querySelector('svg')).toBeNull();
    expect(out.toLowerCase()).not.toContain('<svg');
    // As with payload 2: no surviving "on*" event-handler attribute.
    const all = frag.querySelectorAll('*');
    for (const el of all) {
      for (const attr of el.attributes) {
        expect(attr.name.toLowerCase().startsWith('on')).toBe(false);
      }
    }
  });

  it('preserves safe markdown features (sanity)', () => {
    // Regression guard — the sanitiser must not strip legitimate output.
    const out = sanitiseChatMarkdown(
      '**bold** *italic* `code` [docs](https://example.com)',
    );
    const frag = parse(out);
    expect(frag.querySelector('strong')?.textContent).toBe('bold');
    expect(frag.querySelector('em')?.textContent).toBe('italic');
    expect(frag.querySelector('code')?.textContent).toBe('code');
    const link = frag.querySelector('a');
    expect(link).not.toBeNull();
    expect(link?.getAttribute('href')).toBe('https://example.com');
    expect(link?.getAttribute('rel') ?? '').toContain('noopener');
  });
});
