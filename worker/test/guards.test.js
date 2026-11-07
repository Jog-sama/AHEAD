import { test } from "node:test";
import assert from "node:assert/strict";
import { stripDistances, isCrossing, checkToken, speakable, describeCorridor, finish, NO_ANSWER, CROSSING } from "../src/index.js";

test("stripDistances removes numbers with length units and their hedges", () => {
  assert.equal(stripDistances("A low branch about 2 metres ahead, slightly left."), "A low branch, slightly left.");
  assert.equal(stripDistances("Pole at 1.5 m."), "Pole.");
  assert.equal(stripDistances("A sign roughly three feet away says Exit."), "A sign says Exit.");
  assert.equal(stripDistances("Two steps ahead there is an awning."), "there is an awning.");
  assert.equal(stripDistances("Door is 10 ft in front of you."), "Door.");
  assert.equal(stripDistances("Branch, 4 yards out, head height."), "Branch, head height.");
  assert.equal(stripDistances("Nothing in the path."), "Nothing in the path.");
  assert.equal(stripDistances("A man with a dog."), "A man with a dog.");
  assert.equal(stripDistances("The sign says Platform 2."), "The sign says Platform 2.");
});

test("isCrossing catches go, step and cross verdicts in questions and answers", () => {
  for (const t of [
    "Can I cross now?",
    "is it safe to cross",
    "Should I go?",
    "The path is clear, go ahead.",
    "You can step forward.",
    "The walk signal is on.",
    "A crosswalk ahead with a red man.",
    "Is the coast clear?",
  ]) assert.equal(isCrossing(t), true, t);
  for (const t of ["What does the sign say?", "A low branch at head height, slightly left.", "Two steps up to a door.", "A pole straight ahead.", null, ""])
    assert.equal(isCrossing(t), false, String(t));
});

test("checkToken accepts only the exact bearer token", () => {
  assert.equal(checkToken("Bearer s3cret", "s3cret"), true);
  assert.equal(checkToken("Bearer s3cret ", "s3cret"), true);
  assert.equal(checkToken("Bearer s3cre", "s3cret"), false);
  assert.equal(checkToken("Bearer s3cretx", "s3cret"), false);
  assert.equal(checkToken("s3cret", "s3cret"), false);
  assert.equal(checkToken("Basic s3cret", "s3cret"), false);
  assert.equal(checkToken(null, "s3cret"), false);
  assert.equal(checkToken("Bearer ", ""), false);
  assert.equal(checkToken("Bearer x", undefined), false);
});

test("speakable strips markdown and holds the word limit", () => {
  assert.equal(speakable("**Branch** ahead, `low`."), "Branch ahead, low.");
  const long = Array.from({ length: 40 }, (_, i) => `word${i}`).join(" ");
  assert.equal(speakable(long).split(" ").length, 25);
  assert.equal(speakable("A pole ahead. Then a very long second sentence that goes on and on and on past the limit of twenty five words in total, and then some more."), "A pole ahead.");
});

test("describeCorridor gives bearings and bands, never numbers", () => {
  const chest = [null, null, null, null, 0.8, null, null, null, null];
  const head = [3.1, 2.9, null, null, null, null, 1.6, null, null];
  const d = describeCorridor([chest, head]);
  assert.equal(d, "LiDAR: chest height: something very near, straight ahead; head height: something near, right.");
  assert.equal(describeCorridor(null), "No LiDAR reading.");
  assert.equal(describeCorridor([[null], [null]]), "LiDAR: nothing in the corridor.");
});

test("finish applies every guardrail to the model's output", () => {
  assert.deepEqual(finish({ answer: "A branch about 2 m ahead at head height.", abstain: false, reason: "" }, null), {
    answer: "A branch at head height.",
    abstain: false,
  });
  assert.deepEqual(finish({ answer: "Yes, it is safe to cross.", abstain: false, reason: "" }, null), CROSSING);
  assert.deepEqual(finish({ answer: "A pole ahead.", abstain: false, reason: "" }, "can I go?"), CROSSING);
  assert.deepEqual(finish({ answer: "", abstain: true, reason: "the photo is too dark, nothing visible" }, null), {
    answer: "Not sure.",
    abstain: true,
    reason: "the photo is too dark",
  });
  assert.deepEqual(finish({ answer: "3 m.", abstain: false, reason: "" }, null), NO_ANSWER);
  assert.deepEqual(finish(null, null), NO_ANSWER);
});
