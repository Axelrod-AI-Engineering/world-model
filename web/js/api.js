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
const del = (p) => request("DELETE", p);
const q = (s) => encodeURIComponent(s);

export const api = {
  health: () => get("/health"),
  config: () => get("/config"),
  setReviewPolicy: (policy, approvePending = false) => patch("/config/review", { policy, approve_pending: approvePending }),
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
  hypothesisEvidence: (id) => get(`/hypotheses/${q(id)}/evidence`),
  addHypothesis: (h) => post("/hypotheses", h),
  poseHypothesis: (id, baseThesisId) => post(`/hypotheses/${q(id)}/pose`, { base_thesis_id: baseThesisId ?? null }),
  setHypothesisStatus: (id, status) => post(`/hypotheses/${q(id)}/status`, { status }),
  marketEvent: (id) => get(`/market-events/${q(id)}`),
  marketEvents: (updateId) => get(updateId ? `/market-events?update_id=${q(updateId)}` : "/market-events"),
  submitGraphUpdate: (ev) => post("/graph-update-events", ev),
  // update runs (§7.8): the only way news and data enter the model
  requestUpdate: (body) => post("/updates", body ?? {}),
  updates: () => get("/updates"),
  update: (id) => get(`/updates/${q(id)}`),
  continueUpdate: (id) => post(`/updates/${q(id)}/continue`),
  cancelUpdate: (id) => post(`/updates/${q(id)}/cancel`),
  proposals: (status) => get(status ? `/proposals?status=${status}` : "/proposals"),
  // the reviewer's selection (`keep`) and confidences (Oct 8): `confidence` for the article, `opConfidence` {index: c};
  // `ripple` {subentity id: p}, the probability each value's ripple arrives (Oct 9)
  approve: (id, by = "human", note = null, keep = null, confidence = null, opConfidence = null, ripple = null) =>
    post(`/proposals/${q(id)}/approve`, { by, note, ...(keep ? { keep } : {}), ...(confidence != null ? { confidence } : {}),
                                          ...(opConfidence && Object.keys(opConfidence).length ? { op_confidence: opConfidence } : {}),
                                          ...(ripple && Object.keys(ripple).length ? { ripple } : {}) }),
  // the staged review: the proposal's learning on a copy of the model, with only the `keep` operations
  stage: (id, keep = null, confidence = null, opConfidence = null, ripple = null) => {
    const qs = [keep ? `keep=${keep.join(",")}` : "", confidence != null ? `conf=${confidence}` : "",
                opConfidence && Object.keys(opConfidence).length ? `opconf=${Object.entries(opConfidence).map(([i, c]) => `${i}:${c ?? ""}`).join(",")}` : "",
                ripple && Object.keys(ripple).length ? `ripple=${encodeURIComponent(Object.entries(ripple).map(([s, p]) => `${s}:${p ?? ""}`).join(","))}` : ""]
      .filter(Boolean).join("&");
    return get(`/proposals/${q(id)}/stage${qs ? `?${qs}` : ""}`);
  },
  checks: () => get("/checks"),
  // the transmission grid (Oct 11): one way of isolating what matters (method), for a staged proposal or a forecast
  pathsProposal: (id, method, { keep = null, conf = null, ripple = null } = {}) => {
    const qs = [`method=${q(method)}`, keep ? `keep=${keep.join(",")}` : "", conf != null ? `conf=${conf}` : "",
                ripple && Object.keys(ripple).length ? `ripple=${encodeURIComponent(Object.entries(ripple).map(([s, p]) => `${s}:${p ?? ""}`).join(","))}` : ""]
      .filter(Boolean).join("&");
    return get(`/paths/proposal/${q(id)}?${qs}`);
  },
  pathsForecast: (id, method) => get(`/paths/forecast/${q(id)}?method=${q(method)}`),
  find: (q) => get(`/find?q=${encodeURIComponent(q)}`),
  reject: (id, note, by = "human") => post(`/proposals/${q(id)}/reject`, { by, note }),
  edit: (id, event, by = "human") => post(`/proposals/${q(id)}/edit`, { by, event }),
  defer: (id, by = "human") => post(`/proposals/${q(id)}/defer`, { by }),
  poseThesis: (thesis) => post("/theses", thesis),
  scenarioTheses: () => get("/scenario-theses"),
  learningTasks: () => get("/learning-tasks"),
  poseStoredThesis: (id) => post(`/theses/${q(id)}/pose`, {}),
  session: () => get("/session"),
  ask: (question, horizon_days) => post("/theses", horizon_days ? { question, horizon_days } : { question }),
  forecasts: () => get("/forecasts"),
  forecast: (id) => get(`/forecasts/${q(id)}`),
  explanation: (id) => get(`/explanations/${q(id)}`),
  evaluate: (req) => post("/evaluate", req),
  decisions: () => get("/decisions"),
  recordDecision: (d) => post("/decisions", d),
  decisionTrace: (id) => get(`/decisions/${q(id)}/trace`),
  resolveDecision: (id) => post(`/decisions/${q(id)}/resolve`),
  scenarios: () => get("/scenarios"),
  layout: () => get("/layouts/figure1"),
  load: (scenario, interactive = true) => post("/sim/load", { scenario, interactive }),
  // the top bar's demo menu: the demos, and a switch to one (built in the background on first use)
  demos: () => get("/demos"),
  switchDemo: (id) => post(`/demos/${q(id)}`),
  step: () => post("/sim/step"),
  script: () => get("/sim/script"),
  brief: (id) => get(`/forecasts/${q(id)}/brief`),
  // the world model as context for a client's agents, in their v4.1.4 format (Oct 15)
  contextV4: (forecastId) => get(`/context/v4${forecastId ? `?forecast=${q(forecastId)}` : ""}`),
  // readers' notes on a brief (Oct 14): logged, never learned; and posing a forecast's thesis again
  annotations: (id) => get(`/forecasts/${q(id)}/annotations`),
  annotate: (id, anchor, text) => post(`/forecasts/${q(id)}/annotations`, { anchor, text }),
  removeAnnotation: (id, aid) => del(`/forecasts/${q(id)}/annotations/${q(aid)}`),
  rerun: (id) => post(`/forecasts/${q(id)}/rerun`, {}),
  thesis: (id) => get(`/theses/${q(id)}`),
  play: (until_step) => post("/sim/play", until_step == null ? {} : { until_step }),
  pause: () => post("/sim/pause"),
  reset: () => post("/sim/reset"),
  status: () => get("/sim/status"),
  trace: (since_seq = 0, limit) => get(`/trace?since_seq=${since_seq}${limit ? `&limit=${limit}` : ""}`),
  traceScope: (scope) => get(`/trace?since_seq=0&scope=${q(scope)}`),
  // the flowchart, contracts, the commit log, structure edits, and the tutorial
  flows: () => get("/flows"),
  flowSvg: async (id, bare = false) => {
    const res = await fetch(`/api/flows/${q(id)}/svg${bare ? "?bare=true" : ""}`);
    if (!res.ok) throw new ApiError(res.status, { detail: await res.text() });
    return res.text();
  },
  contracts: () => get("/contracts"),
  repoLog: ({ limit = 60, before = null, process = [], memory = null } = {}) =>
    get(`/repo/log?limit=${limit}${before != null ? `&before=${before}` : ""}${process.map((p) => `&process=${q(p)}`).join("")}${memory ? `&memory=${q(memory)}` : ""}`),
  repoShow: (version) => get(`/repo/commits/${version}`),
  repoDiff: (from, to) => get(`/repo/diff?from=${from}${to != null ? `&to=${to}` : ""}`),
  repoProcesses: () => get("/repo/processes"),
  group: (body) => post("/structure/group", body),
  dissolve: (pattern_id, reason, by = "human") => post("/structure/dissolve", { pattern_id, reason, by }),
  retire: (body) => post("/structure/retire", body),
  examples: () => get("/examples"),
  runExample: (id, manual = null) => post(`/examples/${q(id)}`, manual ? { manual } : undefined),
  prepareExample: (id) => post(`/examples/${q(id)}/prepare`),
  manual: (spec, by = "backend user") => post("/manual", { manual: spec, by }),
  vocabulary: () => get("/vocabulary"),
  runLibrary: (id) => post(`/library/${q(id)}`),
  importLocalList: () => get("/import/local"),
  importLocal: (name) => get(`/import/local/${q(name)}`),
  importPreview: (bundle) => post("/import/preview", { bundle }),
  importRun: (bundle, ids = null) => post("/import", { bundle, ids }),
};

// The /ws stream (§12.3): {"type": "hello", "since_seq": n}, then trace and status messages.
export class Stream {
  constructor({ onTrace, onStatus, onOpen, onClose, onSwitched, sinceSeq }) {
    this.onTrace = onTrace;
    this.onSwitched = onSwitched;      // this engine now serves another demo: the page reloads into it
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
      else if (msg.type === "switched") this.onSwitched?.(msg.scenario);
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
