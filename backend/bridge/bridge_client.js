// Wird von backend/bridge/web_bridge.py vor jeder Seite eingefügt (nach qwebchannel.js).
// - Legt für jede Python-Funktion eine gleichnamige JS-Funktion an, die ein Promise
//   mit dem Rückgabewert liefert. __PYTHON_FUNCTIONS__ setzt Python davor.
// - Stellt onPythonEvent(name, handler) bereit: Ereignisse, die das Backend von sich
//   aus schickt (backend/events.py).
(function () {
  let bridge = null;
  let nextCallId = 0;
  const pendingCalls = new Map();    // callId -> {resolve, reject}
  const eventHandlers = new Map();   // Ereignisname -> [handler]

  function getBridge() {
    // Erst bei Bedarf verbinden - dann ist qt.webChannelTransport sicher da.
    if (bridge === null) {
      bridge = new Promise(resolve =>
        new QWebChannel(qt.webChannelTransport, channel => {
          const b = channel.objects.bridge;
          b.finished.connect(onFinished);
          b.event.connect(onEvent);
          resolve(b);
        }));
    }
    return bridge;
  }

  // Python ist mit einem Aufruf fertig (läuft dort im Hintergrund-Thread).
  function onFinished(callId, raw) {
    const pending = pendingCalls.get(callId);
    if (!pending) return;
    pendingCalls.delete(callId);
    const response = JSON.parse(raw);
    response.ok ? pending.resolve(response.result) : pending.reject(new Error(response.error));
  }

  function onEvent(name, raw) {
    const payload = JSON.parse(raw);
    for (const handler of eventHandlers.get(name) || []) handler(payload);
  }

  function callPython(name, args) {
    return getBridge().then(b => new Promise((resolve, reject) => {
      const callId = ++nextCallId;
      pendingCalls.set(callId, {resolve, reject});
      b.call(callId, name, JSON.stringify(args));
    }));
  }

  window.onPythonEvent = (name, handler) => {
    if (!eventHandlers.has(name)) eventHandlers.set(name, []);
    eventHandlers.get(name).push(handler);
    getBridge();   // verbinden, damit Ereignisse auch ohne vorherigen Aufruf ankommen
  };

  for (const name of __PYTHON_FUNCTIONS__) {
    window[name] = (...args) => callPython(name, args);
  }
})();
