// The chat window (addition, a mock-up). DECISION: the user asked for a way to ask follow-up questions
// about a forecast brief by highlighting its text; answering them is not built yet, so the window
// quotes what was selected, takes a question, and says plainly that chat is not implemented yet.
import { esc } from "../util.js";

export function initChat() {
  const box = document.createElement("section");
  box.id = "chat";
  box.className = "chat hidden";
  box.setAttribute("role", "dialog");
  box.setAttribute("aria-label", "Ask about this brief");
  document.getElementById("stage").appendChild(box);
  let thread = [];
  let context = "";

  function render() {
    box.innerHTML = `
      <header><b>Ask about this</b><span class="faint small">${esc(context)}</span><span class="spacer"></span>
        <button class="close" aria-label="Close the chat">✕</button></header>
      <div class="msgs">${thread.map((m) => `<div class="msg ${m.who}">${m.quote ? `<blockquote>${esc(m.quote)}</blockquote>` : ""}${m.text ? `<div>${esc(m.text)}</div>` : ""}</div>`).join("")}</div>
      <form class="ask"><input type="text" placeholder="Ask a follow-up question…" aria-label="Your question"><button class="primary" type="submit">Send</button></form>`;
    box.querySelector(".close").addEventListener("click", close);
    box.querySelector("form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const input = box.querySelector("input");
      const text = input.value.trim();
      if (!text) return;
      thread.push({ who: "me", text });
      thread.push({ who: "bot", text: "Not implemented yet: answering questions about a brief is part of the proposed stack (see Methods)." });
      render();
    });
    const msgs = box.querySelector(".msgs");
    msgs.scrollTop = msgs.scrollHeight;
    box.querySelector("input").focus();
  }

  function open({ quote = "", source = "" } = {}) {
    context = source;
    thread = [{ who: "me", quote }, { who: "bot", text: "Chat is not implemented yet. This window is a mock-up of asking follow-up questions about a forecast brief." }];
    box.classList.remove("hidden");
    render();
  }

  function close() {
    box.classList.add("hidden");
  }

  return { open, close, isOpen: () => !box.classList.contains("hidden") };
}
