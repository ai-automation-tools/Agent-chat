/**
 * AgentBattleground — background (service worker on Chrome, event page on
 * Firefox).
 *
 * Deliberately thin. All the work (bridge HTTP, capture, insertion) happens in
 * the side panel, which is a real document and therefore survives longer than
 * a service worker's 30-second idle timeout — polling for the operator's
 * review from here would just get killed mid-wait.
 *
 * This file does the two things only the background can: route the toolbar
 * click to the panel, and keep a per-tab arena badge so you can see at a
 * glance that a tab has a live arena.
 *
 * It loads as a module on Chrome and as a classic script on Firefox, so it
 * must stay import-free. The panel surface differs per browser — Chrome's
 * `chrome.sidePanel` versus Firefox's `sidebarAction` — and that fork lives
 * here rather than leaking into the panel itself.
 */

/* global browser */
const ext = typeof browser !== 'undefined' ? browser : chrome;

const hasSidePanel = Boolean(ext.sidePanel);
const hasSidebarAction = Boolean(ext.sidebarAction);

ext.runtime.onInstalled.addListener(() => {
  if (!hasSidePanel) return;
  ext.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error('[AgentBattleground] side panel setup', err));
});

// Firefox has no `openPanelOnActionClick`, so the toolbar click has to open
// the sidebar itself. `onClicked` is a user gesture, which is what
// `sidebarAction.open()` requires.
if (!hasSidePanel && hasSidebarAction) {
  ext.action.onClicked.addListener(() => {
    try {
      ext.sidebarAction.open();
    } catch (err) {
      console.error('[AgentBattleground] sidebar open', err);
    }
  });
}

/**
 * The panel tells us when a tab gains or loses an arena; we mirror that on the
 * toolbar badge. `{ type: 'badge', tabId, text }` with an empty text clears it.
 */
ext.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== 'badge') return false;
  const { tabId, text } = msg;
  ext.action.setBadgeText({ tabId, text: text || '' });
  if (text) {
    ext.action.setBadgeBackgroundColor({ tabId, color: '#b4341c' });
  }
  sendResponse({ ok: true });
  return true;
});
