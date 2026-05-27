const puppeteer = require('puppeteer');

(async () => {
  console.log("Launching browser...");
  const browser = await puppeteer.launch({
    headless: "new",
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();

  // Capture console logs
  page.on('console', msg => {
    console.log(`PAGE LOG [${msg.type()}]:`, msg.text());
  });

  // Capture page errors (uncaught exceptions)
  page.on('pageerror', err => {
    console.error('PAGE ERROR (uncaught exception):', err.stack || err.message);
  });

  // Capture request failures
  page.on('requestfailed', request => {
    const failure = request.failure();
    console.error(`REQUEST FAILED: ${request.url()} - ${failure ? failure.errorText : 'unknown'}`);
  });

  // Capture all responses
  page.on('response', response => {
    if (response.status() >= 400) {
      console.error(`HTTP ERROR ${response.status()}: ${response.url()}`);
    } else {
      console.log(`HTTP ${response.status()}: ${response.url()}`);
    }
  });

  try {
    console.log("Navigating to https://indus-ai-cloud-101.web.app ...");
    await page.goto('https://indus-ai-cloud-101.web.app', {
      waitUntil: 'load',
      timeout: 15000
    });

    console.log("Navigation complete. Waiting 3 seconds for dynamic JS execution...");
    await new Promise(resolve => setTimeout(resolve, 3000));

    const html = await page.content();
    console.log("------------------ PAGE CONTENT ------------------");
    console.log(html);
    console.log("--------------------------------------------------");
  } catch (err) {
    console.error("Navigation / execution failed:", err);
  } finally {
    await browser.close();
    console.log("Browser closed.");
  }
})();
