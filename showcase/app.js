const facts = {
  atlas: { question: "When does Atlas launch?", source: "#engineering · Dana, Rahul, Priya", answer: "Atlas is scheduled to launch on 20 October.", owner: "Dana", confidential: true },
  salary: { question: "What is the senior salary band?", source: "#leadership · Dana, Sam", answer: "The new senior engineering band is $155k–$185k base, plus 0.15–0.35% equity.", owner: "Sam", confidential: true },
  priya: { question: "Is Priya leaving?", source: "#leadership · Dana, Sam", answer: "Priya is resigning on Friday.", owner: "Sam", confidential: true }
};

const venues = {
  general: { title: "general", members: 4, audience: "Dana, Sam, Rahul, Priya", allowed: [], icon: "#" },
  engineering: { title: "engineering", members: 3, audience: "Dana, Rahul, Priya", allowed: ["atlas"], icon: "#" },
  leadership: { title: "leadership", members: 2, audience: "Dana, Sam", allowed: ["salary"], icon: "#" },
  dm: { title: "dana · sam", members: 2, audience: "Dana, Sam", allowed: [], icon: "◉" }
};

let venueKey = "general";
let factKey = "atlas";
const messages = document.querySelector("#messages");
const trace = document.querySelector("#trace");

function addMessage(person, text, kind = "human") {
  const el = document.createElement("article");
  el.className = `message ${kind}`;
  const initials = person === "Need to Know" ? "N" : "D";
  el.innerHTML = `<span class="avatar ${kind}">${initials}</span><div><b>${person}</b><small>${kind === "human" ? "just now" : "agent"}</small><p>${text}</p></div>`;
  messages.append(el);
  messages.scrollTop = messages.scrollHeight;
}

function decisionCard(kind, title, text, detail) {
  const el = document.createElement("article");
  el.className = `decision-card ${kind}`;
  el.innerHTML = `<div class="decision-icon">${kind === "allow" ? "✓" : "⌁"}</div><div><b>${title}</b><p>${text}</p><small>${detail}</small></div>`;
  messages.append(el);
}

function updateTrace(fact, venue, allowed) {
  document.querySelector("#trace-empty").hidden = true;
  trace.hidden = false;
  document.querySelector("#trace-source").textContent = fact.source;
  const hard = document.querySelector("#hard-step");
  const soft = document.querySelector("#soft-step");
  const hardText = document.querySelector("#trace-hard");
  const softText = document.querySelector("#trace-soft");
  const result = document.querySelector("#trace-result");
  const hardPass = allowed || factKey === "priya" && venueKey === "dm";
  hard.className = `trace-step ${hardPass ? "pass" : "hold"}`;
  hardText.textContent = hardPass ? "Audience is compatible" : "Audience mismatch found";
  soft.className = `trace-step ${hardPass && fact.confidential ? "hold" : "pass"}`;
  softText.textContent = hardPass && fact.confidential ? "Confidentiality marker detected" : "No additional hold needed";
  const action = allowed ? "ALLOW" : "HOLD";
  result.className = `trace-result ${allowed ? "pass" : "hold"}`;
  result.innerHTML = `<span>${allowed ? "✓" : "🔒"}</span><div><small>FINAL DECISION</small><b>${action}</b></div>`;
}

function ask() {
  const fact = facts[factKey];
  const venue = venues[venueKey];
  const allowed = venue.allowed.includes(factKey);
  addMessage("Dana", `@need-to-know ${fact.question}`);
  setTimeout(() => {
    if (allowed) {
      addMessage("Need to Know", fact.answer, "agent");
      decisionCard("allow", "Safe to share", "This fact is verified for the current audience.", `Source: ${fact.source}`);
    } else {
      const isSoftHold = venueKey === "dm" && factKey === "priya";
      addMessage("Need to Know", isSoftHold ? "This disclosure needs Sam’s approval." : "I’m holding this until the fact owner decides.", "agent");
      decisionCard("hold", isSoftHold ? "Permission needed" : "Disclosure held", isSoftHold ? "The audience can see the source, but it was marked confidential." : "Someone in this channel was not part of the source conversation.", `Asking ${fact.owner}, who said it first.`);
    }
    updateTrace(fact, venue, allowed);
  }, 300);
}

document.querySelectorAll(".channel").forEach((button) => button.addEventListener("click", () => {
  venueKey = button.dataset.venue;
  document.querySelectorAll(".channel").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  const venue = venues[venueKey];
  document.querySelector("#venue-title").textContent = venue.title;
  document.querySelector("#venue-members").textContent = `${venue.members} members · ${venue.audience}`;
  document.querySelector(".channel-icon").textContent = venue.icon;
  messages.querySelectorAll(".message, .decision-card").forEach((element) => element.remove());
  trace.hidden = true; document.querySelector("#trace-empty").hidden = false;
}));

document.querySelectorAll(".question").forEach((button) => button.addEventListener("click", () => {
  factKey = button.dataset.question;
  document.querySelectorAll(".question").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  document.querySelector("#typed-question").textContent = facts[factKey].question;
}));
document.querySelector("#ask-button").addEventListener("click", ask);
