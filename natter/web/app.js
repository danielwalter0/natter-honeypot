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
const voiceControls = document.getElementById("voice-controls");
const startCallButton = document.getElementById("start-call-button");
const stopCallButton = document.getElementById("stop-call-button");
const listeningBadge = document.getElementById("listening");
const heardText = document.getElementById("heard");
const voiceUnsupported = document.getElementById("voice-unsupported");

// ---- What the page remembers between turns
let mode = null; // "replay" or "live", asked from the server at start
let linesTotal = null; // replay only: how many scammer lines the recording has
let linesDone = 0; // replay only: how many have been played
let ended = false; // true once the call is over; only Reset works then
let currentAudio = null; // the ONE audio player for the whole page, made on first Play
let latestAudio = null; // the audio of the newest reply (null if it has none)

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

// ---- Stop the shared player and rewind it to the start (nothing to do before
// the first Play, when there is no player yet). Used by Play and by Reset.
function stopClip() {
  if (currentAudio === null) return;
  currentAudio.pause();
  currentAudio.currentTime = 0;
}

// ---- Play one Natter clip from the start, through the one shared player.
// Whatever is playing is stopped and rewound first, so clicking Play (on another
// bubble, or the same one again) never plays two copies over each other.
function playClip(audioUrl) {
  if (currentAudio === null) {
    currentAudio = new Audio(); // made once, the first time any Play is clicked
  }
  stopClip(); // the same bubble restarts from the start; another bubble cuts in
  if (currentAudio.src !== audioUrl) {
    currentAudio.src = audioUrl; // a different bubble: load its clip instead
  }
  // play() can fail (a browser sound rule, bad audio data): say so, don't stay silent.
  // The answer is true once the clip has started, false if it could not play, so the
  // voice call knows whether to wait for the clip before listening again.
  return currentAudio.play().then(() => true).catch(() => {
    statusText.textContent = "Could not play the audio.";
    return false;
  });
}

// ---- Wait until the shared player stops. "pause" fires when a clip reaches its end,
// and also when stopClip cuts it off (Reset, or Play on another bubble).
function clipStopped() {
  return new Promise((resolve) => {
    currentAudio.addEventListener("pause", resolve, { once: true });
  });
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
    play.addEventListener("click", () => playClip(audioUrl));
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
  latestAudio = frame.audio; // kept so a voice call can play the reply straight away
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
  startCallButton.disabled = off;
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
    // The recording has no lines left (e.g. the page was reloaded after the end):
    // treat it as the end of the call, so setBusy below switches Next turn off
    if (answer.data.detail === "replay finished") {
      ended = true;
      statusText.textContent = "Replay finished. Press Reset to play it again.";
      return false;
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
  if (await sendLine(line)) lineInput.value = "";
});

// ---- Reset: start a fresh call and clear everything on the page
resetButton.addEventListener("click", async () => {
  stopClip(); // the old call's voice stops at once
  stopCall(); // and the microphone stops listening
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

// ==== Voice input (live mode only) ====
// The browser listens to the microphone and turns speech into text for us.
// Chrome calls this webkitSpeechRecognition; some browsers have none at all.
const Recogniser = window.SpeechRecognition || window.webkitSpeechRecognition;
let recogniser = null; // made on the first Start call click
let callActive = false; // true between Start call and Stop call
let paused = false; // true while a turn runs or Natter's reply plays

// ---- Send one scammer line, heard or typed, through the one /api/say path,
// so every guard on typed lines also applies to heard ones. Listening is
// paused first, so the microphone cannot start a second turn meanwhile.
async function sendLine(line) {
  pauseListening();
  const turn = runTurn("/api/say", { line: line });
  // The turn has started but is not waited for yet, so a filler can play meanwhile
  const fillers = playFillers(turn);
  const ok = await turn;
  playReplyThenListen(ok, fillers); // not awaited: the typed box can be cleared at once
  return ok;
}

// ---- Latency filler: while the real reply is being made, Natter says a short
// stock line ("Oh, just a moment, dear.") so the caller does not hear silence.
// The fillers are only sound: they never become a bubble, a turn or a fact.
let fillerClips = []; // WAV data URLs from the server; stays empty if none were recorded
let lastFiller = -1; // which clip played last, so the next one is different

// ---- Pick a random filler clip, never the same one as last time
function pickFiller() {
  let i = Math.floor(Math.random() * fillerClips.length);
  if (fillerClips.length > 1 && i === lastFiller) {
    i = (i + 1) % fillerClips.length; // the same as last time: take the next one instead
  }
  lastFiller = i;
  return fillerClips[i];
}

// ---- Play filler while the turn runs: one straight away, and one more only if
// the reply is still not ready when the first one ends. Never more than two.
// With no filler clips this does nothing, so the page works as it did before.
async function playFillers(turn) {
  let replyReady = false;
  turn.then(() => {
    replyReady = true; // runTurn never fails outright, so this always happens
  });
  for (let played = 0; played < 2; played++) {
    if (fillerClips.length === 0 || (played > 0 && replyReady)) return;
    if (!(await playClip(pickFiller()))) return; // could not play: give up on filler
    await clipStopped();
  }
}

// ---- Play the new reply, for typed and heard lines alike, then listen again
// once it has finished, so the microphone does not hear Natter's own voice.
// The filler always finishes first, so the reply never cuts it off.
// startListening does nothing outside a voice call, so a typed line never turns
// the microphone on.
async function playReplyThenListen(ok, fillers) {
  await fillers;
  if (ok && latestAudio) {
    if (await playClip(latestAudio)) await clipStopped();
  }
  paused = false;
  if (ended) stopCall(); // the call is over: stop listening for good
  startListening();
}

// ---- Stop hearing for a while (a turn is running or a reply is playing).
// abort() throws away anything half heard.
function pauseListening() {
  paused = true;
  if (recogniser !== null) recogniser.abort();
}

// ---- Start hearing, but only during a call and when nothing else is happening
function startListening() {
  if (!callActive || paused || ended) return;
  try {
    recogniser.start();
  } catch (error) {
    // start() throws if it is already listening; that is fine, nothing to do
  }
}

// ---- Turn the microphone off and put the buttons back to "Start call"
function stopCall() {
  callActive = false;
  if (recogniser !== null) recogniser.abort();
  listeningBadge.hidden = true;
  heardText.textContent = "";
  startCallButton.hidden = false;
  stopCallButton.hidden = true;
}

// ---- Build the recogniser once and tell it what to do with what it hears
function makeRecogniser() {
  recogniser = new Recogniser();
  recogniser.lang = "en-GB";
  recogniser.interimResults = true; // send words as they are heard, not only at the end
  recogniser.continuous = false; // one line at a time: it stops after each final result
  // It has started listening: show the indicator
  recogniser.onstart = () => {
    listeningBadge.hidden = false;
  };
  // It has stopped (after a line, a silence, or abort): hide the indicator and,
  // if the call is still on and nothing is running, listen again
  recogniser.onend = () => {
    listeningBadge.hidden = true;
    startListening();
  };
  // New words heard. Words still being worked out are "interim" and are only shown;
  // a "final" result is a whole line, which is sent as the scammer's turn.
  recogniser.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) {
        heardText.textContent = "";
        const line = result[0].transcript.trim();
        if (line !== "") sendLine(line);
        return;
      }
      interim = interim + result[0].transcript;
    }
    heardText.textContent = interim; // plain text only, like everything else
  };
  // Something went wrong. Silence ("no-speech") and our own abort() ("aborted") are
  // normal, and onend listens again. Anything else (microphone blocked, no network,
  // no microphone) ends the voice call, and the typed box still works.
  recogniser.onerror = (event) => {
    if (event.error === "no-speech" || event.error === "aborted") return;
    statusText.textContent = "Voice input stopped (" + event.error + "). Type the line instead.";
    stopCall();
  };
}

// ---- Start call: this click is also what lets the browser play Natter's audio
// on its own later, because browsers only allow sound after the user clicks.
startCallButton.addEventListener("click", () => {
  if (recogniser === null) makeRecogniser();
  callActive = true;
  paused = false;
  startCallButton.hidden = true;
  stopCallButton.hidden = false;
  statusText.textContent = "";
  startListening();
});

// ---- Stop call: listening off. The typed box and Send keep working.
stopCallButton.addEventListener("click", stopCall);

// ---- No recogniser in this browser: hide the voice buttons and say why
if (!Recogniser) {
  voiceControls.hidden = true;
  voiceUnsupported.hidden = false;
}

// ---- Start: ask the server which mode it runs in, then set the page up
async function start() {
  try {
    const response = await fetch("/api/mode");
    const info = await response.json();
    mode = info.mode;
    linesTotal = info.lines_total;
    // Live mode sends the filler clips; replay sends none, so the list stays empty
    fillerClips = Array.isArray(info.filler) ? info.filler : [];
    showMode();
    setBusy(false);
  } catch (error) {
    statusText.textContent = "Could not reach the server.";
  }
}

start();
