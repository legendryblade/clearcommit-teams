/* ClearCommit Teams — runtime configuration.
 *
 * This file is the only thing a deployment needs to change. Leave the value
 * empty for local use; the client falls back to http://127.0.0.1:8770.
 *
 * A hosted build sets it to the public API origin, for example:
 *   window.CLEARCOMMIT_API_BASE = "https://api.example.com";
 *
 * Never put a secret, a service-role key, or a token here: this file is
 * served to the browser.
 */
window.CLEARCOMMIT_API_BASE = "https://clearcommit-teams-api.onrender.com";
