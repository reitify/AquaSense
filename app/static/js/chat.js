const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatTranscript = document.getElementById("chat-transcript");
const chatSend = document.getElementById("chat-send");
const chatHistory = [];

function addMessage(role, text, mode = null) {
  const message = document.createElement("article");
  message.className = `chat-message ${role === "user" ? "user-message" : "assistant-message"}`;

  if (role !== "user") {
    const avatar = document.createElement("span");
    avatar.className = "chat-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "A";
    message.append(avatar);
  }

  const body = document.createElement("div");
  body.className = "chat-message-body";
  const name = document.createElement("div");
  name.className = "chat-message-name";
  name.textContent = role === "user" ? "You" : mode === "online-model" ? "AquaSense · online AI" : mode === "local-model" ? "AquaSense · local AI" : "AquaSense · database analysis";
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  body.append(name, paragraph);
  message.append(body);
  chatTranscript.append(message);
  chatTranscript.scrollTop = chatTranscript.scrollHeight;
  return message;
}

async function sendMessage(text) {
  addMessage("user", text);
  chatHistory.push({ role: "user", content: text });
  chatInput.value = "";
  chatInput.focus();
  chatSend.disabled = true;
  chatSend.textContent = "…";

  const runtime = document.getElementById("chat-runtime");
  const provider = runtime.dataset.provider;
  const modelAvailable = runtime.dataset.available === "true";
  const pendingText = provider === "online" && modelAvailable
    ? "Getting an online AI response…"
    : modelAvailable
      ? "Thinking with the local model…"
      : "Checking local monitoring data…";
  const pendingMode = provider === "online" ? "online-model" : modelAvailable ? "local-model" : "local-data";
  const pending = addMessage("assistant", pendingText, pendingMode);
  pending.classList.add("is-pending");

  try {
    const response = await fetch("/chat/api/message", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": document.getElementById("chat-csrf-token").value,
      },
      body: JSON.stringify({ message: text, history: chatHistory.slice(0, -1).slice(-8) }),
      signal: AbortSignal.timeout(125000),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || "The assistant could not answer right now.");
    }

    pending.remove();
    addMessage("assistant", result.answer, result.mode);
    chatHistory.push({ role: "assistant", content: result.answer });

    const runtime = document.getElementById("chat-runtime");
    const runtimeMessage = document.getElementById("runtime-message");
    runtime.dataset.available = result.model_status.available ? "true" : "false";
    runtime.dataset.provider = result.model_status.provider || "local";
    runtime.classList.toggle("runtime-ready", result.model_status.available);
    runtime.classList.toggle("runtime-fallback", !result.model_status.available);
    runtimeMessage.textContent = result.model_status.available
      ? `${result.model_status.provider === "online" ? "Online AI ready" : "Local model ready"}: ${result.model_status.model}`
      : result.model_status.message;
  } catch (error) {
    pending.remove();
    addMessage("assistant", error.message, "local-data");
  } finally {
    chatSend.disabled = false;
    chatSend.textContent = "Send";
  }
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = chatInput.value.trim();
  if (question) sendMessage(question);
});

chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

document.querySelectorAll(".chat-suggestion").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.question));
});