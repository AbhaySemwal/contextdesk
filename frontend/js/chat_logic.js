document.addEventListener("DOMContentLoaded", () => {
    const chatContainer = document.getElementById("chat-container");
    const chatForm = document.getElementById("chat-form");
    const messageInput = document.getElementById("message-input");
    const sendButton = document.getElementById("send-button");
    const loadingIndicator = document.getElementById("loading-indicator");

    // Detect if we are running locally (localhost, 127.0.0.1, 0.0.0.0, or file protocol)
    const isLocal = ["localhost", "127.0.0.1", "0.0.0.0", ""].includes(window.location.hostname) || window.location.protocol === "file:";
    const API_URL = isLocal 
        ? "http://127.0.0.1:8000/api/chat" 
        : "/api/chat";

    let chatHistory = [];

    // Scroll to the bottom of the chat area
    function scrollToBottom() {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    // Append message elements to the chat log
    function appendMessage(sender, text, toolUsed = null, isError = false) {
        const messageDiv = document.createElement("div");
        messageDiv.classList.add("flex", "items-start", "gap-3", "max-w-[85%]", "message-bubble");

        if (sender === "user") {
            messageDiv.classList.add("ml-auto", "flex-row-reverse");
            messageDiv.innerHTML = `
                <div class="w-8 h-8 rounded-full bg-slate-800 text-white flex items-center justify-center font-bold text-sm flex-shrink-0 shadow-sm">
                    U
                </div>
                <div class="bg-indigo-600 text-white rounded-2xl rounded-tr-none px-4 py-3 shadow-sm text-sm leading-relaxed">
                    ${escapeHtml(text)}
                </div>
            `;
        } else {
            const avatarBg = isError ? "bg-red-500" : "bg-indigo-600";
            const avatarText = isError ? "!" : "CD";
            const bubbleBg = isError ? "bg-red-50" : "bg-white";
            const borderCol = isError ? "border-red-200" : "border-slate-200";
            const textCol = isError ? "text-red-800" : "text-slate-800";

            let toolBadge = "";
            if (toolUsed) {
                toolBadge = `
                    <div class="mt-2 flex items-center gap-1.5 text-[10px] font-semibold bg-indigo-50 border border-indigo-100 text-indigo-700 px-2 py-0.5 rounded-md w-fit">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                            <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <span>MCP Tool: ${escapeHtml(toolUsed)}</span>
                    </div>
                `;
            }

            messageDiv.innerHTML = `
                <div class="w-8 h-8 rounded-full ${avatarBg} text-white flex items-center justify-center font-bold text-sm flex-shrink-0 shadow-sm">
                    ${avatarText}
                </div>
                <div class="${bubbleBg} border ${borderCol} ${textCol} rounded-2xl rounded-tl-none px-4 py-3 shadow-sm text-sm leading-relaxed">
                    <div class="whitespace-pre-line">${escapeHtml(text)}</div>
                    ${toolBadge}
                </div>
            `;
        }

        chatContainer.appendChild(messageDiv);
        scrollToBottom();
    }

    // Helper to escape HTML characters
    function escapeHtml(str) {
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Toggle loader status and button configurations
    function setLoading(isLoading) {
        if (isLoading) {
            loadingIndicator.classList.remove("hidden");
            sendButton.disabled = true;
            messageInput.disabled = true;
            scrollToBottom();
        } else {
            loadingIndicator.classList.add("hidden");
            sendButton.disabled = false;
            messageInput.disabled = false;
            messageInput.focus();
        }
    }

    // Dispatch message to the backend API
    async function sendMessage(text) {
        if (!text.trim()) return;

        appendMessage("user", text);
        messageInput.value = "";

        setLoading(true);

        try {
            const payload = {
                message: text,
                history: chatHistory
            };

            const response = await fetch(API_URL, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            appendMessage("assistant", data.response, data.tool_used);

            // Record conversation turn
            chatHistory.push({ role: "user", content: text });
            chatHistory.push({ role: "assistant", content: data.response });

        } catch (error) {
            console.error("API Connection Error:", error);
            appendMessage(
                "assistant",
                `Failed to communicate with ContextDesk backend.\n\nDetail: ${error.message}\n\nPlease check that the FastAPI server is running at http://127.0.0.1:8000.`,
                null,
                true
            );
        } finally {
            setLoading(false);
        }
    }

    // Listen to form submit
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = messageInput.value;
        sendMessage(text);
    });

    // Listen to quick suggestion triggers
    document.querySelectorAll(".quick-suggestion").forEach(button => {
        button.addEventListener("click", () => {
            const query = button.textContent.trim();
            sendMessage(query);
        });
    });
});
