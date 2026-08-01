/**
 * AgentBattleground — service worker.
 *
 * Deliberately thin. All the work (bridge HTTP, capture, insertion) happens in
 * the side panel, which is a real document and therefore survives longer than
 * a service worker's 30-second idle timeout — polling for the operator's
 * review from here would just get killed mid-wait.
 *
 * This file does the two things only the worker can: route the toolbar click
 * to the side panel, and keep a per-tab arena badge so you can see at a glance
 * that a tab has a live arena.
 */

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error('[AgentBattleground] side panel setup', err));
});

/**
 * The panel tells us when a tab gains or loses an arena; we mirror that on the
 * toolbar badge. `{ type: 'badge', tabId, text }` with an empty text clears it.
 */
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== 'badge') return false;
  const { tabId, text } = msg;
  chrome.action.setBadgeText({ tabId, text: text || '' });
  if (text) {
    chrome.action.setBadgeBackgroundColor({ tabId, color: '#b4341c' });
  }
  sendResponse({ ok: true });
  return true;
});
