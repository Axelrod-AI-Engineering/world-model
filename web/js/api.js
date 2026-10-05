// REST and WebSocket client (§12). Every model result comes from the server.

export class ApiError extends Error {
  constructor(status, body) {
    super(typeof body?.detail === "string" ? body.detail : `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, opts);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

const get = (p) => request("GET", p);
const post = (p, b = {}) => request("POST", p, b);
const patch = (p, b = {}) => request("PATCH", p, b);
const q = (s) => encodeURIComponent(s);

export const api = {
  health: () => get("/health"),
  config: () => get("/config"),
  setReviewPolicy: (policy) => patch("/config/review", { policy }),
  state: (version) => get(version == null ? "/state" : `/state?version=${version}`),
  versions: () => get("/versions"),
  entity: (id) => get(`/entities/${q(id)}`),
  interaction: (id) => get(`/interactions/${q(id)}`),
  pattern: (id) => get(`/superentities/${q(id)}`),
  taxonomy: (kind) => get(`/taxonomies/${kind}`),
  memory: () => get("/memory"),
  frontier: () => get("/frontier"),
  frontierSeries: (id) => get(`/frontier/${q(id)}/series`),
  hypotheses: () => get("/hypotheses?sort=voi"),
  addHypothesis: (h) => post("/hypotheses", h),
  poseHypothesis: (id, baseThesisId) => post(`/hypotheses/${q(id)}/pose`, { base_thesis_id: baseThesisId ?? null }),
  setHypothesisStatus: (id, status) => post(`/hypotheses/${q(id)}/status`, { status }),
  marketEvent: (id) => get(`/market-events/${q(id)}`),
  submitMarketEvent: (ev) => post("/market-events", ev),
  submitGraphUpdate: (ev) => post("/graph-update-events", ev),
  proposals: (status) => get(status ? `/proposals?status=${status}` : "/proposals"),
  approve: (id, by = "human", note = null) => post(`/proposals/${q(id)}/approve`, { by, note }),
  reject: (id, note, by = "human") => post(`/proposals/${q(id)}/reject`, { by, note }),
  edit: (id, event, by = "human") => post(`/proposals/${q(id)}/edit`, { by, event }),
  defer: (id, by = "human") => post(`/proposals/${q(id)}/defer`, { by }),
  poseThesis: (thesis) => post("/theses", thesis),
  ask: (question, horizon_days) => post("/theses", horizon_days ? { question, horizon_days } : { question }),
  forecasts: () => get("/forecasts"),
  forecast: (id) => get(`/forecasts/${q(id)}`),
  explanation: (id) => get(`/explanations/${q(id)}`),
  consolidate: (day) => post("/consolidate", day ? { day } : {}),
  evaluate: (req) => post("/evaluate", req),
  decisions: () => get("/decisions"),
  recordDecision: (d) => post("/decisions", d),
  decisionTrace: (id) => get(`/decisions/${q(id)}/trace`),
  resolveDecision: (id) => post(`/decisions/${q(id)}/resolve`),
  scenarios: () => get("/scenarios"),
  layout: () => get("/layouts/figure1"),
  load: (scenario, interactive = true) => post("/sim/load", { scenario, interactive }),
  step: () => post("/sim/step"),
  play: (until_step) => post("/sim/play", until_step == null ? {} : { until_step }),
  pause: () => post("/sim/pause"),
  reset: () => post("/sim/reset"),
  status: () => get("/sim/status"),
  trace: (since_seq = 0, limit) => get(`/trace?since_seq=${since_seq}${limit ? `&limit=${limit}` : ""}`),
};

// The /ws stream (§12.3): {"type": "hello", "since_seq": n}, then trace and status messages.
export class Stream {
  constructor({ onTrace, onStatus, onOpen, onClose, sinceSeq }) {
    this.onTrace = onTrace;
    this.onStatus = onStatus;
    this.onOpen = onOpen;
    this.onClose = onClose;
    this.sinceSeq = sinceSeq;
    this.ws = null;
    this.retry = 500;
    this.closed = false;
  }

  connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 500;
      ws.send(JSON.stringify({ type: "hello", since_seq: this.sinceSeq() }));
      this.onOpen?.();
    };
    ws.onmessage = (m) => {
      let msg;
      try { msg = JSON.parse(m.data); } catch { return; }
      if (msg.type === "trace") this.onTrace(msg.event);
      else if (msg.type === "status") this.onStatus(msg.status);
    };
    ws.onclose = () => {
      this.onClose?.();
      if (this.closed) return;
      setTimeout(() => this.connect(), this.retry);
      this.retry = Math.min(this.retry * 2, 8000);
    };
  }

  close() {
    this.closed = true;
    this.ws?.close();
  }
}
