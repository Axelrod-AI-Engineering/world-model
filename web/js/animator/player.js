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
  }

  setSpeed(s) {
    this.speed = Math.max(0.25, Math.min(4, +s || 1));
  }

  push(ev) {
    this.queue.push(ev);
    if (!this.running) this.pump();
  }

  // Events of the same kind in the same phase and step play together.
  takeBatch() {
    const first = this.queue.shift();
    const batch = [first];
    if (BATCHABLE.has(first.kind)) {
      while (this.queue.length && this.queue[0].kind === first.kind && this.queue[0].phase === first.phase
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
        const fresh = batch.filter((ev) => applyTrace(ev));
        if (!fresh.length) continue;
        const behind = this.queue.length;
        if (behind > MAX_BEHIND) {
          if (!this.skipping) { this.skipping = true; emit("player", { skipping: true, behind }); }
          continue;
        }
        if (this.skipping) { this.skipping = false; emit("player", { skipping: false }); }
        try {
          await play(fresh, { ...this.ctx, speed: this.speed, reduced: store.settings.reducedMotion,
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
