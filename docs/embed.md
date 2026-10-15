# Daily Illini embedding handoff

GitHub Pages URL: **https://illini-media-company.github.io/professor-guide/**. Use this HTML in a DI custom HTML block:

```html
<iframe
  src="https://illini-media-company.github.io/professor-guide/?embed=1"
  title="Professor Guide — UIUC courses and professors"
  width="100%"
  height="800"
  style="border: 0; display: block;"
  loading="lazy"
></iframe>
<p>
  <a href="https://illini-media-company.github.io/professor-guide/"
     target="_blank" rel="noopener">Open Professor Guide full page</a>
</p>
```

The title gives assistive technology an accessible frame label. The full-page link provides an alternative to nested scrolling. Keep 800px initially; the iframe has its own scrolling and a responsive document. No dynamic resize messages are sent or accepted.

Local test: `npm run build && npm run preview`, then open **http://localhost:4173/professor-guide/embed-test.html**. The public equivalent is **https://illini-media-company.github.io/professor-guide/embed-test.html**. The test page uses a same-site relative iframe so it works in local preview and at the repository base path.

Automated Chromium tests verify the shell at 320, 375, and 768 pixels, native keyboard access to the full-page link and section disclosures, no horizontal overflow, 200% CSS shell zoom, and query/hash navigation. Browser CSS zoom is an automated layout check; it does not certify every assistive-technology/browser combination. The frontend owner must keep these checks as the interface evolves.

Deployment verification checks the actual HTML, JS/CSS, embedding page, exact manifest revision, and every referenced JSON hash. See `docs/deployment.md` for the observed run and URL verification.

**DI staging verification remains external:** no DI staging URL, authenticated CMS session, or staging editing connection was supplied. Apply the exact snippet in staging and check the DI theme's content width, mobile layout, keyboard traversal into/out of the frame, full-page link, and editor retention of the iframe attributes before publishing on DI. No DI CMS content was changed by this repository work.
