const textarea = document.getElementById("text");
const MAX_MESSAGE_SIZE = 1024 * 1024; // 1 MiB
const encoder = new TextEncoder();
const charCount = document.getElementById("charCount");
const sizeError = document.getElementById("sizeError");
const disconnectError = document.getElementById("disconnectError");

let suppress = false;
let debounceTimer = null;
const debounceDelay = 100; // ms

const protocol = location.protocol === "https:" ? "wss://" : "ws://";
const ws = new WebSocket(protocol + location.host + "/ws");

const copyButton = document.getElementById("copyButton");
const copyStatus = document.getElementById("copyStatus");

copyButton.addEventListener("click", async () => {
    try {
        await navigator.clipboard.writeText(textarea.value);

        copyStatus.textContent = "Copied!";
        setTimeout(() => {
            copyStatus.textContent = "";
        }, 1500);
    } catch (err) {
        // Fallback for older browsers
        textarea.select();
        document.execCommand("copy");

        copyStatus.textContent = "Copied!";
        setTimeout(() => {
            copyStatus.textContent = "";
        }, 1500);
    }
});

function updateCount() {
    const bytes = encoder.encode(textarea.value).length;

    charCount.textContent = `${bytes.toLocaleString()} / ${MAX_MESSAGE_SIZE.toLocaleString()} characters`;

    if (bytes >= MAX_MESSAGE_SIZE) {
        charCount.style.color = "var(--error)";
        textarea.classList.add("limit-reached");
        sizeError.textContent = "Maximum document size reached.";
    } else {
        charCount.style.color = "var(--text-secondary)";
        textarea.classList.remove("limit-reached");
        sizeError.textContent = "";
    }
}

ws.onmessage = function (event) {
    suppress = true;

    // Preserve cursor position when possible
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;

    // avoid unnecessary DOM update when nothing changes
    if (textarea.value !== event.data) {
        textarea.value = event.data;
        updateCount();
    }

    textarea.setSelectionRange(
        Math.min(start, textarea.value.length),
        Math.min(end, textarea.value.length),
    );

    suppress = false;
};

function showDisconnected(message) {
    disconnectError.textContent = message;
    textarea.classList.add("disconnected");
}

ws.onerror = () => {
    showDisconnected("Unable to connect to server.");
};

ws.onclose = () => {
    showDisconnected("Lost connection to server.");
};

// prevent going over character limit
textarea.addEventListener("beforeinput", (e) => {
    if (
        e.inputType.startsWith("delete") ||
        e.inputType === "historyUndo" ||
        e.inputType === "historyRedo"
    ) {
        return;
    }

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;

    const newValue =
        textarea.value.slice(0, start) +
        (e.data ?? "") +
        textarea.value.slice(end);

    if (encoder.encode(newValue).length > MAX_MESSAGE_SIZE) {
        e.preventDefault();

        textarea.classList.add("limit-reached");
        sizeError.textContent = "Maximum document size reached.";

        return;
    }
});

textarea.addEventListener("input", () => {
    if (suppress) return;

    updateCount();

    // Delay sending to server until typing stops
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(textarea.value);
        }
    }, debounceDelay);
});

// update character count on page load
updateCount();
