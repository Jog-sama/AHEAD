// Runs the page's thumb cue (the block between the <thumb-cue> markers in ios/Ahead/index.html) on cases read from
// stdin, for tests/test_thumb_cue.py. Input: [{frames: [{corridor, t, tracking}], cal?}], tracking
// defaulting to normal. Output per case: each frame's
// undebounced decision, the gated cue and the angle written.
const fs = require('fs'), path = require('path'), vm = require('vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'ios', 'Ahead', 'index.html'), 'utf8');
const block = html.match(/\/\/ <thumb-cue>[\s\S]*?\/\/ <\/thumb-cue>/);
if (!block) throw new Error('no <thumb-cue> block in the page');
const ctx = vm.createContext({});
vm.runInContext(block[0] + '\nthis.api={thumbDecide,thumbGate,thumbAngle};', ctx);
const { thumbDecide, thumbGate, thumbAngle } = ctx.api;
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = cases.map(({ frames, cal = { left: 80, right: 100 } }) => {
  const gate = thumbGate();
  return frames.map(({ corridor, t = 0, tracking = 'normal' }) => {
    const d = thumbDecide(corridor, tracking), cue = gate.frame(d, t);
    return { decision: d.direction, stop: d.stop, cue, angle: thumbAngle(cue, cal) };
  });
});
process.stdout.write(JSON.stringify(out));
