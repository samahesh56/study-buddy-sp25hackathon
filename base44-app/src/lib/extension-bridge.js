const REQUEST_SOURCE = "studyclaw-app";
const RESPONSE_SOURCE = "studyclaw-extension";

export function callExtension(type, payload = {}, timeoutMs = 10000) {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
            window.removeEventListener("message", onMessage);
            reject(new Error("Timed out waiting for StudyClaw extension response"));
        }, timeoutMs);

        function onMessage(event) {
            if (event.source !== window) return;
            const data = event.data;
            if (!data || data.source !== RESPONSE_SOURCE || data.requestId !== requestId) return;

            clearTimeout(timeout);
            window.removeEventListener("message", onMessage);

            if (data.ok) {
                resolve(data.payload);
            } else {
                reject(new Error(data.error || "StudyClaw extension request failed"));
            }
        }

        window.addEventListener("message", onMessage);
        window.postMessage(
            {
                source: REQUEST_SOURCE,
                requestId,
                type,
                payload,
            },
            "*"
        );
    });
}
