'use strict';
// Timers cover headers AND body consumption. A response header alone is not success.
const HyTransport = (() => {
  async function requestJSON(url, options = {}, timeout = 10000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      const data = await response.json();
      if (!response.ok) {
        const error = new Error(data.error || `HTTP ${response.status}`);
        error.modelState = data.model_state;
        throw error;
      }
      return data;
    } catch (error) {
      if (controller.signal.aborted) throw new Error('Request timed out. Device completion is not confirmed.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function streamGuard(onTimeout, total, idle = 150000, opening = 10000) {
    let openTimer, idleTimer, totalTimer;
    const stop = () => { clearTimeout(openTimer); clearTimeout(idleTimer); clearTimeout(totalTimer); };
    const expire = () => { stop(); onTimeout(); };
    const touch = () => { clearTimeout(openTimer); clearTimeout(idleTimer); idleTimer = setTimeout(expire, idle); };
    openTimer = setTimeout(expire, opening);
    totalTimer = setTimeout(expire, total);
    return {touch, stop};
  }
  const exportText = (text, complete) => complete ? text : `[Incomplete translation — output may be truncated.]\n\n${text}`;
  return {requestJSON, streamGuard, exportText};
})();
if (typeof module !== 'undefined') module.exports = HyTransport;
