// Natter page script. Python does all the real work; this file only draws the
// "frame" the server sends back after each turn.
//
// Safety rule for this whole file: scammer and model text is untrusted, so it is
// only ever put on the page with textContent, which shows it as plain text.
// Nothing here turns text into HTML or code.
"use strict";

// ---- Find the page elements once, by their id in index.html
const modeBadge = document.getElementById("mode-badge");
const statusText = document.getElementById("status");
const resetButton = document.getElementById("reset-button");
const whyList = document.getElementById("why-list");
const bubbles = document.getElementById("bubbles");
const replayControls = document.getElementById("replay-controls");
const nextButton = document.getElementById("next-button");
const replayProgress = document.getElementById("replay-progress");
const liveForm = document.getElementById("live-form");
const lineInput = document.getElementById("line-input");
const sendButton = document.getElementById("send-button");
const factsList = document.getElementById("facts");
const refusedList = document.getElementById("refused");
const goalText = document.getElementById("goal");
const notesList = document.getElementById("notes");
const speechLabel = document.getElementById("speech-label");
const speechMeter = document.getElementById("speech-meter");

// ---- What the page remembers between turns
let mode = null; // "replay" or "live", asked from the server at start
let linesTotal = null; // replay only: how many scammer lines the recording has
let linesDone = 0; // replay only: how many have been played
let ended = false; // true once the call is over; only Reset works then

// ---- The owner's block: ONE dossier fact as one list item.
// It must: create a list item with document.createElement("li"), set its text
// with textContent (never put HTML into the page), and return the item.
// The fields on `fact` are:
//   fact.field       e.g. "stage" or "identifiers[0]"
//   fact.value       ready to show, e.g. "phone: 07700 900482"
//   fact.turn        the scammer turn number the quote comes from (null for caller_type)
//   fact.quote       the exact words the scammer said (null for caller_type)
//   fact.confidence  a number from 0 to 1
//   fact.note        caller_type's reason, otherwise null
function renderFactRow(fact) {
  // 1. Make an empty list item.
  const li = document.createElement("li");

  // 2. Start with "field: value", for example "stage: payment_ask".
  let text = fact.field + ": " + fact.value;

  // 3. Most facts have a turn number and an exact quote. caller_type has neither,
  //    so it shows its note instead.
  if (fact.turn !== null) {
    text = text + " | turn " + fact.turn + ' | "' + fact.quote + '"';
  } else {
    text = text + " | " + fact.note;
  }

  // 4. Add the confidence with two decimals, for example 0.90.
  text = text + " | " + fact.confidence.toFixed(2);

  // 5. Put it in as plain text only. Never as HTML.
  li.textContent = text;
  return li;
}

// ---- Make a list item holding plain text (used for refused facts, notes, why lines)
function textItem(text) {
  const item = document.createElement("li");
  item.textContent = text;
  return item;
}

// ---- Add one chat bubble. A Natter bubble with audio gets a Play button,
// because browsers do not let a page start sound on its own.
function addBubble(bubble, audioUrl) {
  const item = document.createElement("li");
  item.className = "bubble " + bubble.speaker; // "scammer" or "persona" picks the colour
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = (bubble.speaker === "scammer" ? "Scammer" : "Natter") + " · turn " + bubble.turn;
  const words = document.createElement("p");
  words.textContent = bubble.text;
  item.append(who, words);
  if (bubble.speaker === "persona" && audioUrl) {
    const play = document.createElement("button");
    play.type = "button";
    play.textContent = "▶ Play";
    play.addEventListener("click", () => new Audio(audioUrl).play());
    item.append(play);
  }
  bubbles.append(item);
}

// ---- Swap the contents of a list for new items
function fillList(list, items) {
  list.replaceChildren(...items);
}

// ---- Draw one frame from the server: bubbles, dossier, refusals, goal, notes, budget
function render(frame) {
  // New bubbles: the audio belongs to Natter's bubble in this step
  for (const bubble of frame.new_turns) {
    addBubble(bubble, frame.audio);
  }
  // Scroll the call panel to the bottom, so the newest bubble is in view
  bubbles.scrollTop = bubbles.scrollHeight;
  // The whole dossier and every refusal so far are sent each time, so redraw them
  fillList(factsList, frame.facts.map(renderFactRow));
  fillList(refusedList, frame.refused.map(
    (r) => textItem(r.field + ": " + r.reason + " (turn " + r.turn + ")")));
  goalText.textContent = "Goal: " + (frame.goal || "none") + ". " + frame.why_goal;
  fillList(notesList, frame.notes.map(textItem));
  fillList(whyList, frame.why.map(textItem));
  // Speech meter: live mode has a budget, replay plays recorded audio
  if (frame.speech_cap !== null) {
    speechMeter.hidden = false;
    speechMeter.max = frame.speech_cap;
    speechMeter.value = frame.speech_used;
    speechLabel.textContent = frame.speech_used + " of " + frame.speech_cap + " speech requests used";
  }
  if (frame.ended) {
    ended = true;
    statusText.textContent = "Call ended.";
  }
}

// ---- Turn the controls off while a turn runs (so a double click cannot start
// a second, paid turn), and back on afterwards unless the call is over
function setBusy(busy) {
  const off = busy || ended;
  nextButton.disabled = off;
  sendButton.disabled = off;
  lineInput.disabled = off;
  resetButton.disabled = busy; // Reset only waits for the running turn
  if (busy) statusText.textContent = "Working…";
}

// ---- Send a POST to our own server and read the JSON answer
async function post(path, body) {
  const options = { method: "POST", headers: { "Content-Type": "application/json" } };
  if (body !== undefined) options.body = JSON.stringify(body);
  const response = await fetch(path, options);
  const data = await response.json();
  return { ok: response.ok, data: data };
}

// ---- Run one turn: lock the controls, ask the server, draw the answer, unlock
async function runTurn(path, body) {
  setBusy(true);
  try {
    const answer = await post(path, body);
    if (answer.ok) {
      statusText.textContent = "";
      render(answer.data);
      return true;
    }
    statusText.textContent = "Refused by server: " + answer.data.detail; // short text we wrote
    return false;
  } catch (error) {
    statusText.textContent = "Could not reach the server.";
    return false;
  } finally {
    setBusy(false);
  }
}

// ---- Replay: the Next turn button plays the next recorded scammer line
nextButton.addEventListener("click", async () => {
  if (await runTurn("/api/step")) {
    linesDone += 1;
    replayProgress.textContent = linesDone + " of " + linesTotal + " lines";
  }
});

// ---- Live: the form sends the typed line, and clears the box if it was accepted
liveForm.addEventListener("submit", async (event) => {
  event.preventDefault(); // stay on the page instead of reloading it
  const line = lineInput.value.trim();
  if (line === "") return;
  if (await runTurn("/api/say", { line: line })) lineInput.value = "";
});

// ---- Reset: start a fresh call and clear everything on the page
resetButton.addEventListener("click", async () => {
  setBusy(true);
  try {
    const answer = await post("/api/reset");
    if (!answer.ok) {
      statusText.textContent = "Refused by server: " + answer.data.detail;
      return;
    }
    ended = false;
    linesDone = 0;
    bubbles.replaceChildren();
    fillList(factsList, []);
    fillList(refusedList, []);
    fillList(notesList, []);
    fillList(whyList, [textItem("Start the call to see each decision.")]);
    goalText.textContent = "No reply yet.";
    speechMeter.value = 0;
    showMode();
    statusText.textContent = "Reset.";
  } catch (error) {
    statusText.textContent = "Could not reach the server.";
  } finally {
    setBusy(false);
  }
});

// ---- Show the controls and labels that belong to this mode
function showMode() {
  modeBadge.textContent = mode === "live" ? "live" : "replay";
  replayControls.hidden = mode !== "replay";
  liveForm.hidden = mode !== "live";
  replayProgress.textContent = mode === "replay" ? "0 of " + linesTotal + " lines" : "";
  speechLabel.textContent = mode === "live"
    ? "0 speech requests used" : "Recorded audio: no budget used.";
}

// ---- Start: ask the server which mode it runs in, then set the page up
async function start() {
  try {
    const response = await fetch("/api/mode");
    const info = await response.json();
    mode = info.mode;
    linesTotal = info.lines_total;
    showMode();
    setBusy(false);
  } catch (error) {
    statusText.textContent = "Could not reach the server.";
  }
}

start();
