// The player (§13.7) keeps a queue of trace events. In live mode it consumes the WebSocket stream;
// if it falls more than 200 events behind, it skips animations to catch up. In replay mode it reads
// from GET /api/trace?since_seq= or a saved trace file.
import { api } from "../api.js";
import { applyTrace, emit, store } from "../store.js";
import { BATCHABLE, play } from "./effects.js";

const MAX_BEHIND = 200;

export class Player {
  constructor(ctx) {
    this.ctx = ctx;              // {renderer, ...}
    this.queue = [];
    this.running = false;
    this.mode = "live";
    this.speed = 1;
    this.skipping = false;
    this.frameCount = new Map();
  }

  setSpeed(s) {
    this.speed = Math.max(0.25, Math.min(4, +s || 1));
  }

  // DECISION: propagation runs emit up to 60 frames each, and a forecast runs ten networks; queueing
  // all of them made the player fall behind and skip the whole show. Frames are thinned on arrival
  // (every 3rd for an expectation, every 6th for a network, every 4th for the coupled run); the rest
  // still reach the store, so walkthroughs keep every day.
  push(ev) {
    if (ev.kind === "propagation.frame" && !store.walkthrough) {
      const rid = String(ev.payload?.run_id ?? "");
      const every = rid.startsWith("predict:") ? 6 : rid.startsWith("couple:") ? 4 : 3;
      const k = this.frameCount.get(rid) ?? 0;
      this.frameCount.set(rid, k + 1);
      if (this.frameCount.size > 400) this.frameCount.clear();
      // a thinned frame stays in the queue, in order, but is only applied (applying it early would move
      // the store's cursor past the events still waiting, and they would be dropped as stale)
      if (k % every !== 0) ev = { ...ev, silent: true };
    }
    this.queue.push(ev);
    if (!this.running) this.pump();
  }

  // Events of the same kind in the same phase and step play together.
  takeBatch() {
    const first = this.queue.shift();
    const batch = [first];
    if (BATCHABLE.has(first.kind) && !first.silent) {
      while (this.queue.length && this.queue[0].kind === first.kind && this.queue[0].phase === first.phase && !this.queue[0].silent
             && this.queue[0].sim_time === first.sim_time && batch.length < 400) {
        batch.push(this.queue.shift());
      }
    }
    return batch;
  }

  async pump() {
    this.running = true;
    try {
      while (this.queue.length) {
        const batch = this.takeBatch();
        if (batch[0].silent) { applyTrace(batch[0]); continue; }
        const fresh = batch.filter((ev) => applyTrace(ev));
        if (!fresh.length) continue;
        const behind = this.queue.length;
        // a forecast (or anything the guide narrates) is never skipped: it is bounded, and it is the show
        const keep = /^T-/.test(fresh[0].scope ?? "") || !!this.ctx.guide?.run;
        if (behind > MAX_BEHIND && !keep) {
          if (!this.skipping) { this.skipping = true; emit("player", { skipping: true, behind }); }
          continue;
        }
        if (this.skipping) { this.skipping = false; emit("player", { skipping: false }); }
        // while a walkthrough is open it owns the canvas: live events update the model, not the picture
        if (store.walkthrough) continue;
        try {
          // DECISION: the player speeds up with its backlog (up to 8x), so a long update sweeps through
          // its routine days and slows to full detail when it catches up with the live run
          // a forecast plays at a readable pace (at full speed while the guide narrates it)
          const forecast = /^T-/.test(fresh[0].scope ?? "");
          const catchUp = this.ctx.guide?.run ? 1 : forecast ? Math.min(2, 1 + behind / 60) : Math.min(8, 1 + behind / 30);
          await play(fresh, { ...this.ctx, speed: this.speed * catchUp, reduced: store.settings.reducedMotion,
                              interactive: store.status?.state === "awaiting_review" });
        } catch (err) {
          console.warn("effect failed", fresh[0]?.kind, err);
        }
      }
    } finally {
      this.running = false;
      emit("player", { idle: true });
    }
  }

  // Replay mode: fetch the recorded events after `sinceSeq` and play them.
  async replay(sinceSeq = 0, limit = 5000) {
    this.mode = "replay";
    const evs = await api.trace(sinceSeq, limit);
    for (const ev of evs) this.push(ev);
    this.mode = "live";
  }

  // Replay from a saved trace file (JSON lines, as written by `axelrod export-trace`).
  async replayFile(file) {
    const text = await file.text();
    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      try { this.push(JSON.parse(line)); } catch { /* skip */ }
    }
  }
}
