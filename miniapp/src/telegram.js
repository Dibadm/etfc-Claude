// Thin wrapper around the Telegram WebApp SDK (loaded globally via the
// <script> tag in index.html). Falls back gracefully to a fake/dev mode
// when opened in a plain browser (e.g. `npm run dev`) so the app is
// still viewable outside Telegram during development.

const tg = typeof window !== "undefined" ? window.Telegram?.WebApp : null;

const DEV_FAKE_INIT_DATA_WARNING =
  "Running outside Telegram — using dev fallback. The real app requires a valid Telegram session.";

export function initTelegram() {
  if (tg) {
    tg.ready();
    tg.expand();
    // Match the app's own dark theme rather than the client's default,
    // so there's no flash of a mismatched Telegram chrome color.
    tg.setHeaderColor?.("#16130F");
    tg.setBackgroundColor?.("#16130F");
  } else {
    console.warn(DEV_FAKE_INIT_DATA_WARNING);
  }
}

export function getInitData() {
  return tg?.initData || "";
}

export function isInTelegram() {
  return Boolean(tg && tg.initData);
}

export function hapticSuccess() {
  tg?.HapticFeedback?.notificationOccurred?.("success");
}

export function hapticError() {
  tg?.HapticFeedback?.notificationOccurred?.("error");
}

export function hapticTap() {
  tg?.HapticFeedback?.impactOccurred?.("light");
}

export function showMainButton(text, onClick) {
  if (!tg) return;
  tg.MainButton.setText(text);
  tg.MainButton.onClick(onClick);
  tg.MainButton.show();
}

export function hideMainButton() {
  tg?.MainButton?.hide();
}

export function closeApp() {
  tg?.close();
}
