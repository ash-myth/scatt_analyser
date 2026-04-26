const { chromium } = require("playwright");

const APP_URL = process.env.STREAMLIT_APP_URL;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  console.log(`Visiting ${APP_URL}`);
  await page.goto(APP_URL, { waitUntil: "networkidle", timeout: 60000 });

  // Check if the "Get this app back up" button exists
  const wakeButton = page.getByRole("button", { name: /get this app back up/i });
  const isVisible = await wakeButton.isVisible().catch(() => false);

  if (isVisible) {
    console.log("App is sleeping. Clicking wake button...");
    await wakeButton.click();
    await page.waitForTimeout(15000); // wait for app to boot
    console.log("Done. App should be waking up.");
  } else {
    console.log("App is already awake. Nothing to do.");
  }

  await browser.close();
})();
